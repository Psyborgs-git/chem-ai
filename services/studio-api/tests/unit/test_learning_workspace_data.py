from __future__ import annotations

import json

import pytest

from studio.domain.learning.workspace_runtime.data import (
    canonical_structure,
    split_rows,
    validate_import,
)


def test_custom_molecule_import_canonicalizes_and_reports_every_rejection() -> None:
    rows, report = validate_import(
        {
            "format": "csv",
            "content": "structure,value\nCCO,1.2\nOCC,1.2\ninvalid,3\nCC,NaN\n",
            "mapping": {"smiles": "structure", "target": "value"},
        }
    )
    assert len(rows) == 1
    assert rows[0]["smiles"] == "CCO"
    assert rows[0]["target"] == 1.2
    assert report["accepted"] == 1
    assert report["duplicates"] == 1
    assert report["rejected"] == 2
    assert [item["row"] for item in report["rejections"]] == [3, 4]
    assert report["scientificStatus"] == "not_validated"


def test_structure_only_data_does_not_invent_a_property_label() -> None:
    rows, report = validate_import({"format": "smi", "content": "CCO ethanol\nCC ethane\n"})
    assert report["accepted"] == 2
    assert all("target" not in row for row in rows)


def test_scaffold_identity_document_groups_cannot_cross_partitions() -> None:
    smiles = ["c1ccccc1O", "c1ccccc1N", "C1CCCCC1", "CCO", "CC", "CCN", "CCC", "CCCC", "CO"]
    rows = [{"id": str(i), **canonical_structure(value)} for i, value in enumerate(smiles)]
    rows[2]["documentId"] = "one-paper"
    rows[3]["documentId"] = "one-paper"
    rows[4]["prompt"] = "same prompt"
    rows[5]["prompt"] = "same prompt"
    split = split_rows(rows, seed=7)
    assert split == split_rows(rows, seed=7)
    assert split["0"] == split["1"]
    assert split["2"] == split["3"]
    assert split["4"] == split["5"]
    assert set(split.values()) == {"train", "development", "final"}


def test_prompt_preferences_and_invalid_json_are_not_silently_accepted() -> None:
    content = "\n".join(
        json.dumps(row)
        for row in [
            {"prompt": "Question", "chosen": "answer", "rejected": "wrong"},
            {"prompt": "Question2", "chosen": "answer"},
        ]
    )
    rows, report = validate_import({"format": "jsonl", "content": content})
    assert len(rows) == 1
    assert report["rejected"] == 1
    with pytest.raises(ValueError, match="Line 1"):
        validate_import({"format": "jsonl", "content": "not-json"})


def test_worker_client_requires_https_for_non_loopback() -> None:
    from workers.training.workspace_worker import Client

    with pytest.raises(ValueError, match="HTTPS"):
        Client("http://studio.example", "test-session")
    Client("http://127.0.0.1:8787", "test-session")
    for value in (
        "https://user:secret@studio.example",
        "https://studio.example?token=x",
        "https://studio.example/#fragment",
        "https://studio.example/%2e%2e/private",
    ):
        with pytest.raises(ValueError):
            Client(value, "test-session")


def test_worker_client_never_forwards_session_token_to_redirect_target(monkeypatch) -> None:
    import http.server
    import threading

    from workers.training.workspace_worker import Client

    received = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            received.append((self.path, self.headers.get("Authorization")))
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:1/token-must-not-arrive")
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
        client = Client(f"http://127.0.0.1:{server.server_port}", "fixture-session")
        with pytest.raises(ValueError, match="redirect"):
            client.request("/worker/lease")
        assert received == [("/api/learning-workspace/worker/lease", "Bearer fixture-session")]
        assert client.opener is not None
    finally:
        server.shutdown()
        server.server_close()


def test_checkpoint_restore_refuses_traversal(tmp_path) -> None:
    import io
    import zipfile

    from workers.training.workspace_worker import _restore

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../../escape", "no")
    with pytest.raises(ValueError, match="Unsafe checkpoint"):
        _restore(buffer.getvalue(), tmp_path)


def test_binary_molecular_classifier_requires_two_classes_and_unscaled_binary_labels() -> None:
    from pydantic import ValidationError

    from engine_adapter_chemprop import TrainSpec

    base = {
        "task_type": "classification",
        "scope": {"name": "label", "unit": "1", "method": "fixture"},
        "context": {"source": "fixture"},
        "seed": 1,
        "rows": [
            {"row_id": "one", "smiles": "CC", "label": 0},
            {"row_id": "two", "smiles": "CCO", "label": 1},
        ],
    }
    assert TrainSpec.model_validate(base).task_type == "classification"
    base["rows"][1]["label"] = 0.5
    with pytest.raises(ValidationError, match="both 0 and 1"):
        TrainSpec.model_validate(base)


def test_dispatcher_kills_training_before_releasing_lease_after_database_failure(
    tmp_path, monkeypatch
) -> None:
    import uuid
    from types import SimpleNamespace

    from studio.config.settings import Settings
    from studio.domain.learning import workspace
    from studio.domain.learning.workspace_runtime import dispatcher

    order = []
    job = SimpleNamespace(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        kind="sft",
        config={"backend": "mlx", "maxSeconds": 30, "rank": 1},
        state="running",
        result={},
        lease_owner="worker",
        lease_expires_at=None,
    )

    class Database:
        def __init__(self):
            self.lookups = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, *_args):
            self.lookups += 1
            if self.lookups == 2:
                raise RuntimeError("database connection lost")
            return job

        def commit(self):
            if job.state == "failed":
                assert "kill" in order
                order.append("lease_released")

    class Process:
        pid = 123

        def poll(self):
            return None if "kill" not in order else -15

    database = Database()
    monkeypatch.setattr(workspace, "storage_preflight", lambda *_args: {"available": True})
    monkeypatch.setattr(dispatcher, "_request", lambda *_args: {"kind": "sft"})
    monkeypatch.setattr(dispatcher.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    monkeypatch.setattr(dispatcher, "_kill", lambda _process: order.append("kill"))
    worker = dispatcher.LearningDispatcher(lambda: database, Settings(vault_root=tmp_path))
    worker._execute(job.id)
    assert job.state == "failed"
    assert order.index("kill") < order.index("lease_released")


def test_chemprop_honors_selected_device_and_refuses_missing_accelerators(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    from engine_adapter_chemprop.adapter import _trainer
    from engine_adapter_chemprop.contracts import EngineFailure

    available = {"cuda": True, "mps": False}
    torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: available["cuda"]),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: available["mps"])),
    )
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(
        sys.modules,
        "lightning",
        SimpleNamespace(pytorch=SimpleNamespace(Trainer=lambda **kwargs: kwargs)),
    )
    assert _trainer(1, "cpu")["accelerator"] == "cpu"
    assert _trainer(1, "cuda")["accelerator"] == "cuda"
    assert _trainer(1, "auto")["accelerator"] == "cuda"
    with pytest.raises(EngineFailure, match="MPS was selected"):
        _trainer(1, "mps")
    available.update(cuda=False, mps=True)
    assert _trainer(1, "mps")["accelerator"] == "mps"
    assert _trainer(1, "auto")["accelerator"] == "mps"
    with pytest.raises(EngineFailure, match="CUDA was selected"):
        _trainer(1, "cuda")
