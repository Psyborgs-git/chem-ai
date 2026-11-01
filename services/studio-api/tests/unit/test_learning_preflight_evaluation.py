from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from studio.domain.learning.workspace_runtime import worker
from studio.domain.learning.workspace_runtime.data import split_rows, validate_import
from studio.domain.learning.workspace_runtime.evaluation import answer_checks


def test_tool_use_conversations_and_polymer_conditions_survive_dataset_import():
    conversation = [
        {"role": "user", "content": "Read the polymer data"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "lookup",
                    "type": "function",
                    "function": {"name": "read_dataset", "arguments": '{"id":"polymers"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "lookup", "content": "Computed amorphous density only"},
        {"role": "assistant", "content": "Fabric drape remains unmeasured."},
    ]
    rows, report = validate_import(
        {
            "format": "jsonl",
            "content": json.dumps(
                {"messages": conversation, "tools": [], "metadata": {"sample": "one"}}
            ),
        }
    )
    assert report["accepted"] == 1
    assert worker._messages(rows[0]) == conversation
    rows, report = validate_import(
        {
            "format": "csv",
            "content": "PSMILES,density,UUID,temp\n*CC*,1.2,polymer-one,300\n",
            "mapping": {"smiles": "PSMILES", "target": "density", "polymerId": "UUID"},
            "metadataColumns": ["UUID", "temp"],
            "defaults": {
                "property": "density",
                "unit": "g/cm3",
                "method": "RadonPy",
                "conditions": {"temperatureK": 300},
            },
        }
    )
    assert report["accepted"] == 1
    assert rows[0]["originalSmiles"] == "*CC*"
    assert rows[0]["polymerId"] == "polymer-one"
    assert rows[0]["metadata"] == {"UUID": "polymer-one", "temp": "300"}
    assert rows[0]["conditions"] == {"temperatureK": 300}
    assert rows[0]["unit"] == "g/cm3"


def test_orphan_tool_turn_is_rejected_instead_of_training_broken_tool_protocol():
    rows, report = validate_import(
        {
            "format": "jsonl",
            "content": json.dumps(
                {
                    "messages": [
                        {"role": "user", "content": "query"},
                        {"role": "tool", "tool_call_id": "missing", "content": "x"},
                        {"role": "assistant", "content": "answer"},
                    ]
                }
            ),
        }
    )
    assert not rows
    assert "earlier assistant call" in report["rejections"][0]["reason"]


def test_matching_multiturn_questions_cannot_leak_between_training_and_final():
    rows = [
        {
            "id": str(index),
            "messages": [
                {"role": "user", "content": question},
                {"role": "assistant", "content": str(index)},
            ],
        }
        for index, question in enumerate(
            ["same question", "same question", "different one", "different two", "different three"]
        )
    ]
    partitions = split_rows(rows)
    assert partitions["0"] == partitions["1"]
    assert set(partitions.values()) == {"train", "development", "final"}


def test_task_metrics_detect_wrong_units_and_invented_citations():
    row = {
        "evaluation": {
            "requiredFields": ["density", "citations"],
            "allowedCitations": ["real-source"],
            "requiredCitations": ["real-source"],
            "numericTargets": [{"field": "density", "value": 1.3, "unit": "g/cm3"}],
        }
    }
    correct = answer_checks(
        '{"density":{"value":1.3,"unit":"g/cm3"},"citations":["real-source"]}', row
    )
    wrong = answer_checks('{"density":{"value":1.3,"unit":"kg/m3"},"citations":["invented"]}', row)
    assert correct["numericWithUnit0"] and correct["citationIdsSupported"]
    assert not wrong["numericWithUnit0"] and not wrong["citationIdsSupported"]
    assert wrong["unsupportedCitationCount"] == 1


def test_property_evaluation_uses_final_labels_and_a_train_only_baseline(tmp_path, monkeypatch):
    import engine_adapter_chemprop

    model = tmp_path / "model"
    model.mkdir()
    for name in ("model_0.pt", "manifest.json"):
        (model / name).write_bytes(b"fixture")
    (model / "applicability.json").write_text(
        json.dumps({"smiles": ["CC"], "baseline": {"strategy": "training_mean", "value": 2.0}})
    )
    received = []

    def predict(spec, _files):
        received.extend(row.row_id for row in spec.rows)
        return SimpleNamespace(
            model_dump=lambda **_: {"predictions": [{"row_id": "final", "value": 4.0}]}
        )

    monkeypatch.setattr(
        engine_adapter_chemprop, "ChempropAdapter", lambda: SimpleNamespace(predict=predict)
    )
    directory = tmp_path / "evaluation"
    directory.mkdir()
    result = worker._predict(
        {
            "kind": "evaluate",
            "config": {"device": "cpu"},
            "model": {
                "location": str(model),
                "details": {
                    "modelDigest": "a" * 64,
                    "scope": {"name": "density", "unit": "g/cm3", "method": "fixture"},
                    "artifacts": [
                        {"path": "model_0.pt"},
                        {"path": "manifest.json"},
                        {"path": "applicability.json"},
                    ],
                },
            },
            "rows": [
                {"id": "train", "smiles": "CC", "target": 2.0},
                {"id": "final", "smiles": "CO", "target": 5.0},
            ],
            "splits": {"train": "train", "final": "final"},
        },
        directory,
    )
    assert received == ["final"]
    assert result["matchedExamples"] == 1
    assert result["metrics"] == {"mae": 1.0, "rmse": 1.0}
    assert result["baseline"] == {"mae": 3.0, "rmse": 3.0}
    assert (directory / "output/evaluation.json").is_file()


def test_assistant_eval_loads_once_per_model_and_never_supplies_the_final_answer(
    tmp_path, monkeypatch
):
    loads = []
    contexts = []

    def load(_request, *, adapter):
        loads.append(adapter)

        def generate(prompt, *, messages, tools):
            contexts.append((prompt, messages))
            return "candidate" if adapter else "base"

        return generate

    monkeypatch.setattr(worker, "_load_generator", load)
    rows = [
        {
            "id": "one",
            "messages": [
                {"role": "user", "content": "Question one"},
                {"role": "assistant", "content": "SECRET ANSWER"},
            ],
        },
        {"id": "two", "prompt": "Question two", "response": "SECOND ANSWER"},
    ]
    result = worker._evaluate(
        {
            "model": {"backend": "transformers"},
            "rows": rows,
            "splits": {"one": "final", "two": "final"},
        },
        tmp_path,
    )
    assert loads == [False, True]
    assert result["matchedExamples"] == 2
    assert "SECRET ANSWER" not in json.dumps(contexts)
    assert "SECOND ANSWER" not in json.dumps(contexts)


def test_download_requires_pinned_revision_and_verifies_hub_weight_hash(tmp_path, monkeypatch):
    import sys

    huggingface_hub = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "huggingface_hub", huggingface_hub)

    revision = "a" * 40
    weight = b"declared weights"
    actual = hashlib.sha256(weight).hexdigest()
    blob = SimpleNamespace(rfilename="model.safetensors", lfs=SimpleNamespace(sha256=actual))
    template = SimpleNamespace(rfilename="chat_template.jinja", lfs=None)
    api = SimpleNamespace(
        model_info=lambda *_args, **_kwargs: SimpleNamespace(
            sha=revision, siblings=[blob, template]
        )
    )
    monkeypatch.setattr(huggingface_hub, "HfApi", lambda **_kwargs: api, raising=False)
    calls = []

    def download(**kwargs):
        calls.append(kwargs)
        (tmp_path / "model.safetensors").write_bytes(weight)
        (tmp_path / "chat_template.jinja").write_text("{{ messages }}")

    monkeypatch.setattr(huggingface_hub, "snapshot_download", download, raising=False)
    request = {
        "kind": "download_model",
        "config": {
            "backend": "download",
            "repo": "fixture/model",
            "revision": revision,
            "license": "apache-2.0",
        },
        "model": {"location": str(tmp_path)},
    }
    result = worker.execute(request, tmp_path)
    assert calls[0]["revision"] == revision and calls[0]["token"] is False
    assert "chat_template.jinja" in calls[0]["allow_patterns"]
    assert result["manifest"]["files"][0]["sha256"] == actual
    blob.lfs.sha256 = "0" * 64
    with pytest.raises(ValueError, match="SHA-256"):
        worker.execute(request, tmp_path)
    del request["config"]["revision"]
    with pytest.raises(ValueError, match="immutable"):
        worker.execute(request, tmp_path)


def test_reference_json_checks_origin_and_claim_values_not_only_field_presence():
    row = {
        "response": '{"origin":"computed","supportsSilkEquivalence":false}',
        "evaluation": {
            "jsonRequired": True,
            "requiredFields": ["origin", "supportsSilkEquivalence"],
        },
    }
    right = answer_checks('{ "supportsSilkEquivalence": false, "origin": "computed" }', row)
    wrong = answer_checks('{"origin":"experimental","supportsSilkEquivalence":true}', row)
    assert right["structuredJson"] and right["jsonReferenceMatch"]
    assert wrong["structuredJson"] and not wrong["jsonReferenceMatch"]


def test_empty_model_protocol_prefix_is_visible_normalized_but_strict_json_failure_is_kept():
    from studio.domain.learning.workspace_runtime.evaluation import visible_answer

    row = {
        "response": '{"origin":"computed","supportsSilkEquivalence":false}',
        "evaluation": {
            "jsonRequired": True,
            "requiredFields": ["origin", "supportsSilkEquivalence"],
        },
    }
    raw = "<think>\n\n</think>\n\n" + row["response"]
    checks = answer_checks(raw, row)
    assert not checks["strictJsonOnly"]
    assert checks["structuredJson"] and checks["jsonReferenceMatch"]
    assert visible_answer(raw) == row["response"]
    nonempty = "<think>nonempty text</think>" + row["response"]
    assert visible_answer(nonempty) == nonempty
    assert not answer_checks(nonempty, row)["structuredJson"]
