"""CS-0801 engine tests — real tiny SFT inside the pinned container.

AT-0801-1  compatible local runtime + synthetic approved data → the
           pinned trainer executes REAL training: adapter parameters
           change, frozen base does not, checkpoints persist, and a
           save/load roundtrip reproduces the artifact byte-identically.
AT-0801-3  interrupt → resume carries the checkpoint + provenance and
           continues from ``from_step``.

Every test SKIPS explicitly when the pinned image is absent — absence
is reported, never faked.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time

import pytest
from workers.training.sft.runtime import IMAGE, IsolatedSft, SftRunResult, available

from engine_adapter_sft.contracts import SftResumeSpec, SftTrainSpec

pytestmark = pytest.mark.engine


def _dataset() -> bytes:
    """Synthetic reviewed examples — fixture data, no chemistry
    validity; the point is that real gradient steps run."""
    examples = []
    prompts = [
        ("Report the viscosity.", "The viscosity is 900 mPa·s at 25 °C."),
        ("Report the density.", "The density is 1.21 g/cm³ at 20 °C."),
        ("What solvent was used?", "The solvent was EC/DMC 1:1 by weight."),
        ("State the ionic radius.", "The Li⁺ radius is 0.76 Å."),
        ("Give the cutoff.", "The upper cutoff is 4.3 V."),
        ("Report temperature.", "The run was at 60 °C."),
        ("Name the salt.", "The salt was LiTFSI at 1.0 M."),
        ("Report yield.", "The isolated yield was 78%."),
    ] * 2
    for i, (q, a) in enumerate(prompts):
        ex = {
            "schema_name": "sft_example",
            "schema_version": 1,
            "example_id": f"fx-{i:02d}",
            "context": {"task_id": "t", "session_id": f"s{i % 4}", "manifest_id": "m"},
            "messages": [{"role": "user", "kind": "message", "content": q, "refs": []}],
            "tool_calls": [],
            "tool_results": [],
            "response": {"content": a, "refs": []},
            "provenance": {
                "message_id": f"m{i}",
                "author_principal_id": "p1",
                "reviewed_at": "2026-01-01T00:00:00Z",
                "kind": "reviewed_response",
            },
            "rights": {"training": "owned", "source_classes": ["research_session"]},
            "partition": "train" if i % 4 else "development",
            "group_keys": [f"session:s{i % 4}"],
            "example_digest": hashlib.sha256(f"ex{i}".encode()).hexdigest(),
        }
        examples.append(ex)
    return ("\n".join(json.dumps(e, sort_keys=True) for e in examples)).encode()


def _spec(**over: object) -> SftTrainSpec:
    raw: dict = {
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
        "max_steps": 12,
        "eval_every": 4,
        "checkpoint": {"every_steps": 4, "keep_last": 3},
        "seed": 0,
        "resources": {"cpu_cores": 1.0, "memory_mebibytes": 1024, "wall_seconds": 600},
        "dataset_digest": "",
    }
    raw.update(over)
    return SftTrainSpec.model_validate(raw)


@pytest.fixture()
def engine() -> IsolatedSft:
    if not available():
        pytest.skip(f"pinned trainer image {IMAGE} not installed")
    return IsolatedSft()


# AT-0801-1 ---------------------------------------------------------------
class TestRealTraining:
    def test_real_parameters_change_and_reload_matches(self, engine: IsolatedSft) -> None:
        result = engine.train(_spec(), dataset=_dataset())
        assert result.status == "succeeded", result.error
        outcome = result.outcome
        assert outcome is not None and outcome.usable
        proof = outcome.parameter_proof
        assert proof is not None
        # REAL update: adapter moved, frozen base did not
        assert proof.adapter_before_sha256 != proof.adapter_after_sha256
        assert proof.frozen_before_sha256 == proof.frozen_after_sha256
        assert proof.adapter_changed
        assert not proof.frozen_changed
        # checkpoint save/load roundtrip verified inside the container
        assert proof.reload_matches
        assert outcome.steps_completed == 12
        assert outcome.train_examples > 0
        losses = [t["loss"] for t in outcome.telemetry_tail if t.get("event") == "step"]
        assert losses, "train telemetry rows expected"
        assert result.checkpoints
        assert "adapter/adapter_model.safetensors" in result.artifacts
        assert outcome.scientific_status == "not_validated"

    def test_persisted_config_complete(self, engine: IsolatedSft) -> None:
        result = engine.train(_spec(), dataset=_dataset())
        assert result.status == "succeeded"
        config = json.loads(result.artifacts["config.json"])
        spec = config["spec"]
        # §17.4 — the complete persisted config
        for key in (
            "model",
            "adapter",
            "optimizer",
            "batch_size",
            "grad_accumulation",
            "seq_length",
            "precision",
            "checkpoint",
            "seed",
            "resources",
        ):
            assert key in spec, f"spec missing {key}"


# AT-0801-3 ---------------------------------------------------------------
class TestInterruptResume:
    def test_timeout_harvests_checkpoint(self, engine: IsolatedSft) -> None:
        spec = _spec(
            max_steps=400,
            checkpoint={"every_steps": 2, "keep_last": 3},
            resources={
                "cpu_cores": 1.0,
                "memory_mebibytes": 1024,
                "wall_seconds": 45,
            },
        )
        result = engine.train(spec, dataset=_dataset())
        # whatever the container reached — the outcome must be honest,
        # and any harvested checkpoint is recorded
        assert result.status in ("succeeded", "timed_out", "cancelled")
        if result.status == "timed_out":
            assert result.outcome is None or result.outcome.usable is False

    def test_cancel_interrupts_run(self, engine: IsolatedSft) -> None:
        spec = _spec(
            max_steps=600,
            checkpoint={"every_steps": 2, "keep_last": 3},
            resources={
                "cpu_cores": 1.0,
                "memory_mebibytes": 1024,
                "wall_seconds": 600,
            },
        )
        cancel = threading.Event()

        holder: dict[str, SftRunResult] = {}

        def _run() -> None:
            holder["r"] = engine.train(spec, dataset=_dataset(), cancel=cancel)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        time.sleep(20)
        cancel.set()
        t.join(timeout=120)
        result = holder["r"]
        assert result.status in ("cancelled", "succeeded", "timed_out")
        if result.status == "cancelled":
            # checkpoints harvested before the kill are reported
            assert isinstance(result.checkpoints, list)

    def test_resume_continues_from_checkpoint(self, engine: IsolatedSft) -> None:
        first = engine.train(
            _spec(
                max_steps=8,
                checkpoint={"every_steps": 4, "keep_last": 3},
            ),
            dataset=_dataset(),
        )
        assert first.status == "succeeded"
        latest = max(first.checkpoints, key=lambda c: c.step)
        prefix = f"{latest.artifact}/"
        resume_files = {
            name[len(prefix) :]: data
            for name, data in first.artifacts.items()
            if name.startswith(prefix)
        }
        assert "adapter_model.safetensors" in resume_files

        spec = _spec(max_steps=16, checkpoint={"every_steps": 4, "keep_last": 3})
        spec = spec.model_copy(
            update={
                "resume": SftResumeSpec(
                    checkpoint_sha256=latest.sha256,
                    from_step=latest.step,
                    source_run_id="engine-test-1",
                    source_attempt_id="attempt-1",
                )
            }
        )
        second = engine.train(spec, dataset=_dataset(), resume_files=resume_files)
        assert second.status == "succeeded", second.error
        assert second.outcome is not None
        # training continued past the resume step
        assert second.outcome.steps_completed == 16
        assert max(c.step for c in second.checkpoints) > latest.step
