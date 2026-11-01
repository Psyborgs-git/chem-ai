from __future__ import annotations

import json
import sys
import uuid
from types import ModuleType, SimpleNamespace

import pytest

from studio.domain.learning.workspace_runtime import dispatcher, worker


class CachedRows:
    def __init__(self, entries):
        self.entries = entries
        self.visited = []

    def __len__(self):
        return len(self.entries)

    def __getitem__(self, index):
        self.visited.append(index)
        return self.entries[index]


def test_tokenization_preflight_scans_all_cached_training_and_development_rows(tmp_path):
    train = CachedRows([([1] * 16, 8), ([1] * 10, 8)])
    valid = CachedRows([([1] * 14, 5)])
    worker._validate_mlx_tokens({"train": train, "development": valid}, 16, tmp_path)
    assert train.visited == [0, 1]
    assert valid.visited == [0]
    event = json.loads((tmp_path / "events.jsonl").read_text())
    assert event["event"] == "tokenization_preflight" and event["passed"]
    assert event["partitions"][0]["minimumSupervisedTokens"] == 1


def test_all_oversized_development_examples_are_reported_without_silent_truncation(tmp_path):
    valid = CachedRows([([1] * 17, 15), ([1] * 18, 16)])
    with pytest.raises(ValueError, match=r"before optimization.*development row 1.*17 tokens"):
        worker._validate_mlx_tokens(
            {"train": CachedRows([([1] * 8, 3)]), "development": valid}, 16, tmp_path
        )
    assert valid.visited == [0, 1]
    summary = json.loads((tmp_path / "events.jsonl").read_text())
    assert summary["passed"] is False
    assert summary["partitions"][1]["overlongRows"] == 2


def test_prompt_mask_requires_at_least_one_causal_supervised_target_token(tmp_path):
    with pytest.raises(ValueError, match="prompt offset 9 leaves no supervised target tokens"):
        worker._validate_mlx_tokens(
            {"train": CachedRows([([1] * 10, 9)]), "development": CachedRows([([1] * 8, 2)])},
            16,
            tmp_path,
        )


def test_training_export_never_reads_or_loads_final_answers_even_with_an_old_test_file(tmp_path):
    class HeldOut(dict):
        def get(self, *_args, **_kwargs):
            raise AssertionError("Training accessed held-out content")

    data = tmp_path / "data"
    data.mkdir()
    old_test = data / "test.jsonl"
    old_test.write_text("PRIVATE_FINAL_ANSWERS")
    records = worker._mlx_training_records(
        {
            "rows": [
                {"id": "train", "prompt": "Q1", "response": "A1"},
                {"id": "valid", "prompt": "Q2", "response": "A2"},
                HeldOut(id="final", prompt="Do not read", response="PRIVATE_FINAL_ANSWERS"),
            ],
            "splits": {"train": "train", "valid": "development", "final": "final"},
        },
        tmp_path,
    )
    assert set(records) == {"train", "development"}
    assert "PRIVATE_FINAL_ANSWERS" not in json.dumps(records)
    assert old_test.read_text() == "PRIVATE_FINAL_ANSWERS"


def test_assistant_training_dispatch_does_not_send_final_labels_to_the_worker(monkeypatch):
    from studio.auth import context
    from studio.domain.learning.workspace import LearningWorkspaceService

    owner, workspace = uuid.uuid4(), uuid.uuid4()
    dataset = SimpleNamespace(
        id=uuid.uuid4(),
        workspace_id=workspace,
        owner_id=owner,
        state="frozen",
        rights="owned",
        source={},
        digest="frozen-digest",
        rows=[
            {"id": "one", "response": "training"},
            {"id": "two", "response": "development"},
            {"id": "three", "response": "PRIVATE_FINAL_LABEL"},
        ],
        splits={"one": "train", "two": "development", "three": "final"},
    )
    db = SimpleNamespace(get=lambda *_args: dataset)
    job = SimpleNamespace(
        kind="sft",
        dataset_id=dataset.id,
        model_id=None,
        workspace_id=workspace,
        owner_id=owner,
        config={"backend": "mlx"},
    )
    monkeypatch.setattr(context, "load_context", lambda *_args: object())
    monkeypatch.setattr(LearningWorkspaceService, "authorize_dataset_training", lambda *_args: True)
    request = dispatcher._request(db, job)
    assert [row["id"] for row in request["rows"]] == ["one", "two"]
    assert "PRIVATE_FINAL_LABEL" not in json.dumps(request)


def test_invalid_mlx_tokens_stop_before_the_optimizer_is_invoked(tmp_path, monkeypatch):
    modules = {}
    for name in (
        "mlx",
        "mlx.core",
        "mlx.utils",
        "mlx_lm",
        "mlx_lm.lora",
        "mlx_lm.tuner",
        "mlx_lm.tuner.datasets",
        "mlx_lm.utils",
    ):
        module = ModuleType(name)
        module.__path__ = []
        modules[name] = module
        monkeypatch.setitem(sys.modules, name, module)
    modules["mlx"].core = modules["mlx.core"]
    modules["mlx.core"].random = SimpleNamespace(seed=lambda _: None)
    modules["mlx.utils"].tree_flatten = lambda _: []
    modules["mlx_lm.lora"].CONFIG_DEFAULTS = {}
    optimized = []
    modules["mlx_lm.lora"].train_model = lambda *_args: optimized.append(True)
    modules["mlx_lm.utils"].load = lambda *_args, **_kwargs: (object(), object())
    modules["mlx_lm.tuner.datasets"].CacheDataset = lambda rows: rows
    modules["mlx_lm.tuner.datasets"].create_dataset = lambda records, *_: CachedRows(
        [([1] * (17 if row["messages"][0]["content"] == "too long" else 8), 3) for row in records]
    )
    request = {
        "model": {"location": "fixture", "details": {}},
        "config": {
            "maxSteps": 1,
            "batchSize": 1,
            "maxTokens": 16,
            "seed": 0,
            "learningRate": 1e-5,
            "saveEvery": 1,
            "rank": 1,
        },
        "rows": [
            {"id": "one", "prompt": "ok", "response": "answer"},
            {"id": "two", "prompt": "too long", "response": "answer"},
        ],
        "splits": {"one": "train", "two": "development"},
    }
    with pytest.raises(ValueError, match="before optimization"):
        worker._mlx_train(request, tmp_path)
    assert optimized == []
    assert not (tmp_path / "output/adapters.safetensors").exists()


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_worker_rejects_nonfinite_metrics_without_appending_an_invalid_event(tmp_path, bad):
    worker.emit(tmp_path, "training_step", loss=1.25)
    previous = (tmp_path / "events.jsonl").read_bytes()
    with pytest.raises(
        ValueError, match=r"Non-finite numeric metric in validation at metrics\.val_loss"
    ):
        worker.emit(tmp_path, "validation", metrics={"val_loss": bad})
    assert (tmp_path / "events.jsonl").read_bytes() == previous


def test_dispatcher_can_retain_old_nonfinite_events_as_null_with_explicit_metadata(tmp_path):
    raw = '{"event":"validation","val_loss":NaN,"metrics":[Infinity,-Infinity],"iteration":4}\n'
    (tmp_path / "events.jsonl").write_text(raw)
    events = dispatcher._events(tmp_path)
    assert events[0]["val_loss"] is None and events[0]["metrics"] == [None, None]
    assert events[0]["iteration"] == 4
    assert events[0]["metricSanitization"]["nonFinitePaths"] == [
        "val_loss",
        "metrics[0]",
        "metrics[1]",
    ]
    assert events[0]["metricSanitization"]["action"] == "replaced_with_null"
    json.dumps(events, allow_nan=False)
    assert (tmp_path / "events.jsonl").read_text() == raw


def test_nonfinite_worker_result_is_a_failed_job_with_valid_json(tmp_path, monkeypatch):
    (tmp_path / "request.json").write_text('{"kind":"fixture"}')
    monkeypatch.setattr(sys, "argv", ["worker", str(tmp_path)])
    monkeypatch.setattr(worker, "execute", lambda *_args: {"value": float("nan")})
    monkeypatch.chdir(tmp_path)
    assert worker.main() == 2
    result = json.loads((tmp_path / "result.json").read_text())
    assert result["ok"] is False
    assert "non-finite numeric values" in result["error"]
    assert [event["event"] for event in dispatcher._events(tmp_path)] == ["failed"]
    json.dumps(result, allow_nan=False)
