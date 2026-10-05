"""CS-0801 contract tests — SFT dataset + trainer boundary types.

No engine, no database: the contract layer itself must reject hidden
reasoning traces, unlicensed bases, malformed examples, and unsafe
resume members (§17.2-17.4, AT-0801-2's static half).
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile

import pytest
from pydantic import ValidationError
from workers.training.sft.runtime import _pack_resume_tar

from engine_adapter_sft.contracts import (
    BASE_ARCHITECTURES,
    MODEL_LICENSES,
    SftModelSpec,
    SftTrainingExample,
    SftTrainSpec,
    sha256_text,
)


def _example(**over: object) -> dict:
    base = {
        "schema_name": "sft_example",
        "schema_version": 1,
        "example_id": "e1",
        "context": {"task_id": "t", "session_id": "s", "manifest_id": "m"},
        "messages": [{"role": "user", "kind": "message", "content": "q?", "refs": []}],
        "tool_calls": [],
        "tool_results": [],
        "response": {"content": "answer with units 12.5 g/L", "refs": []},
        "provenance": {
            "message_id": "m1",
            "author_principal_id": "p1",
            "reviewed_at": "2026-01-01T00:00:00",
            "kind": "reviewed_response",
        },
        "rights": {"training": "owned", "source_classes": ["research_session"]},
        "partition": "train",
        "group_keys": ["session:s"],
        "example_digest": "d" * 64,
    }
    base.update(over)
    return base


def _spec(**over: object) -> dict:
    raw = json.loads(json.dumps(_SPEC))
    raw.update(over)
    return raw


_SPEC = {
    "schema_name": "sft_train_spec",
    "schema_version": 1,
    "model": {
        "base_model_id": "pico-gpt-char-v1",
        "architecture": "pico-gpt-v1",
        "init_seed": 0,
        "license_id": "fixture-internal",
    },
    "adapter": {
        "method": "lora",
        "rank": 8,
        "alpha": 16,
        "dropout": 0.0,
        "target_modules": ["c_attn", "c_proj"],
    },
    "optimizer": {
        "name": "adamw",
        "learning_rate": 3e-4,
        "scheduler": "linear",
        "warmup_steps": 0,
        "weight_decay": 0.0,
        "max_grad_norm": 1.0,
    },
    "batch_size": 4,
    "grad_accumulation": 1,
    "seq_length": 256,
    "precision": "fp32",
    "max_steps": 20,
    "eval_every": 5,
    "checkpoint": {"every_steps": 5, "keep_last": 3},
    "seed": 0,
    "resources": {"cpu_cores": 1.0, "memory_mebibytes": 1024, "wall_seconds": 600},
    "dataset_digest": "x" * 64,
}


# ---------------------------------------------------------------- examples


def test_valid_example_parses() -> None:
    ex = SftTrainingExample.model_validate(_example())
    assert ex.partition == "train" and ex.example_id == "e1"


def test_example_rejects_hidden_reasoning_trace() -> None:
    """§17.3: a rationale field anywhere in the payload is refused."""
    ex = _example()
    ex["messages"][0]["rationale"] = "secret chain"  # type: ignore[index]
    with pytest.raises(ValidationError):
        SftTrainingExample.model_validate(ex)


def test_example_rejects_nested_cot_key() -> None:
    ex = _example()
    ex["context"]["extras"] = {"nested": [{"chain_of_thought": "x"}]}
    with pytest.raises(ValidationError):
        SftTrainingExample.model_validate(ex)


def test_example_rejects_unknown_partition() -> None:
    with pytest.raises(ValidationError):
        SftTrainingExample.model_validate(_example(partition="production"))


def test_example_digest_payload_is_order_stable() -> None:
    a = {"b": 1, "a": {"z": [1, 2], "y": "x"}}
    b = {"a": {"y": "x", "z": [1, 2]}, "b": 1}
    assert SftTrainingExample.digest_payload(a) == SftTrainingExample.digest_payload(b)


# ---------------------------------------------------------------- spec


def test_spec_digest_stable() -> None:
    s1 = SftTrainSpec.model_validate(_spec())
    s2 = SftTrainSpec.model_validate(_spec())
    assert s1.digest() == s2.digest()
    # spec digests differ when any field changes
    assert SftTrainSpec.model_validate(_spec(seed=1)).digest() != s1.digest()


def test_spec_rejects_unlicensed_architecture() -> None:
    spec = _spec()
    spec["model"]["architecture"] = "does-not-exist"
    with pytest.raises(ValidationError):
        SftTrainSpec.model_validate(spec)


def test_spec_rejects_license_forbidding_training(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        MODEL_LICENSES,
        "no-train",
        {"spdx": None, "training": "denied", "export": "denied"},
    )
    spec = _spec()
    spec["model"]["license_id"] = "no-train"
    with pytest.raises(ValidationError):
        SftModelSpec.model_validate(spec["model"])


def test_spec_rejects_seq_beyond_block() -> None:
    arch = BASE_ARCHITECTURES["pico-gpt-v1"]
    spec = _spec(seq_length=int(arch["block_size"]) + 1)
    with pytest.raises(ValidationError):
        SftTrainSpec.model_validate(spec)


def test_spec_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SftTrainSpec.model_validate(_spec(unexpected="field"))


# ---------------------------------------------------------------- resume tar


def test_resume_tar_roundtrips_flat_names() -> None:
    files = {
        "adapter_model.safetensors": b"\x00" * 16,
        "meta.json": b'{"step": 5}',
        "optimizer.pt": b"\x01" * 8,
    }
    blob = _pack_resume_tar(files)
    with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
        names = sorted(m.name for m in archive.getmembers())
    assert names == ["adapter_model.safetensors", "meta.json", "optimizer.pt"]


def test_resume_tar_drops_traversal_members() -> None:
    files = {"../escape": b"x", "/abs/path": b"y", "ok.txt": b"z"}
    blob = _pack_resume_tar(files)
    with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
        names = [m.name for m in archive.getmembers()]
    assert names == ["ok.txt"]


def test_sha256_text_matches_canonical_json() -> None:
    assert sha256_text('{"a":1}') == hashlib.sha256(b'{"a":1}').hexdigest()
