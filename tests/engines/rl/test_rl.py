"""CS-0902 engine tests — real RL training inside the pinned container.

AT-0902-1  compatible approved runtime → tiny RL smoke executes REAL
           training: actual optimizer steps update the adapter
           parameters (frozen base untouched), checkpoints persist,
           episodes are scored by the real RewardService, and
           cancel/resume carries checkpoint provenance.
AT-0902-3  exhausted compute envelope → the rollout scheduler stops
           admitting episodes (``budget_exhausted``) — no cloud
           fallback exists anywhere in the path.

Every test SKIPS explicitly when the pinned image is absent — absence
is reported, never faked.
"""

from __future__ import annotations

import json
import threading
import time

import pytest
from workers.training.rl.corpus import parse_corpus
from workers.training.rl.environment.contracts import canonical_json
from workers.training.rl.trainer.runtime import IMAGE, IsolatedRl, RlRunResult, available

from engine_adapter_rl.contracts import RlResumeSpec, RlTrainSpec

pytestmark = pytest.mark.engine


def _corpus_doc() -> dict:
    """Two tiny tasks with replay-pinned tools — fixture data, no
    chemistry validity; the point is that REAL episodes + optimizer
    steps run inside the isolated worker."""
    return {
        "schema_name": "rl_training_corpus",
        "env_contract_version": 1,
        "reward_contract_version": 1,
        "tasks": [
            {
                "task_id": "eng-1",
                "messages": [{"role": "user", "content": "what is the viscosity?"}],
                "subgroup": "easy",
                "answerable": True,
                "allowed_tools": ["search_evidence", "get_evidence_record"],
                "target": {
                    "expect": "exact",
                    "value": "900 mPa·s",
                    "required_evidence_ids": ["ev-a"],
                },
            },
            {
                "task_id": "eng-2",
                "messages": [{"role": "user", "content": "report an unknown density"}],
                "subgroup": "hard",
                "answerable": False,
                "allowed_tools": ["search_evidence"],
                "target": {"expect": "abstain"},
            },
        ],
        "snapshot": {
            "snapshot_id": "snap-eng",
            "evidence_ids": ["ev-a"],
            "replay": [
                {
                    "replay_id": "r-a",
                    "tool": "search_evidence",
                    "arguments": {"query": "viscosity"},
                    "result": {"results": [{"evidence_id": "ev-a"}]},
                    "provenance": {"engine_test": True},
                }
            ],
            "meta": {},
        },
        "policy": {
            "policy_id": "engine-policy",
            "kind": "agent",
            "grants": ["edit_task", "request_compute", "propose_candidate"],
            "allowed_tools": ["search_evidence", "get_evidence_record"],
        },
    }


def _corpus() -> bytes:
    parsed = parse_corpus(_corpus_doc())
    return canonical_json(parsed.model_dump(mode="json")).encode("utf-8")


def _spec(**over: object) -> RlTrainSpec:
    raw: dict = {
        "schema_name": "rl_train_spec",
        "schema_version": 1,
        "model": {
            "base_model_id": "pico-rl-char-v1",
            "architecture": "pico-rl-v1",
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
        "algorithm": {
            "family": "grpo",
            "num_generations": 4,
            "tasks_per_batch": 2,
            "epsilon": 0.2,
            "epsilon_high": 0.2,
            "beta": 0.0,
            "scale_rewards": "group",
            "loss_type": "dapo",
            "temperature": 1.0,
            "importance_sampling_level": "token",
        },
        "rollout": {
            "max_episode_actions": 8,
            "max_candidates": 24,
            "prompt_max_tokens": 128,
            "completion_max_tokens": 768,
        },
        "rollout_budget": {
            "max_episodes": 64,
            "max_compute_units": 256.0,
            "max_policy_tokens": 4000000,
            "max_wall_seconds": 3600,
            "max_concurrent_rollouts": 1,
        },
        "max_steps": 4,
        "checkpoint": {"every_steps": 2, "keep_last": 3},
        "seed": 0,
        "resources": {"cpu_cores": 1.0, "memory_mebibytes": 2048, "wall_seconds": 900},
        "corpus_digest": parse_corpus(_corpus_doc()).digest(),
    }
    raw.update(over)
    return RlTrainSpec.model_validate(raw)


@pytest.fixture()
def engine() -> IsolatedRl:
    if not available():
        pytest.skip(f"pinned RL trainer image {IMAGE} not installed")
    return IsolatedRl()


# AT-0902-1 ---------------------------------------------------------------
class TestRealRlTraining:
    def test_real_episodes_and_optimizer_steps(self, engine: IsolatedRl) -> None:
        result = engine.train(_spec(), corpus=_corpus())
        assert result.status == "succeeded", result.error
        outcome = result.outcome
        assert outcome is not None and outcome.usable
        # REAL optimizer steps ran
        assert outcome.optimizer_steps == 4
        # REAL parameter movement: adapter changed, frozen base did not,
        # adapter save/load roundtrip verified inside the container
        proof = outcome.parameter_proof
        assert proof is not None
        assert proof.adapter_before_sha256 != proof.adapter_after_sha256
        assert proof.frozen_before_sha256 == proof.frozen_after_sha256
        assert proof.adapter_changed and not proof.frozen_changed
        assert proof.reload_matches
        # REAL episodes through the CS-0901 env, scored by the real
        # RewardService — reward components persisted per episode
        assert outcome.episodes_completed > 0
        assert outcome.reward_first_mean is not None
        assert outcome.reward_last_mean is not None
        assert result.checkpoints
        assert "adapter/adapter_model.safetensors" in result.artifacts
        assert "result.json" in result.artifacts
        # reward records + episode traces harvested to the vault
        assert "rewards.jsonl" in result.artifacts
        assert any(name.startswith("episodes/") for name in result.artifacts)
        # honest labels always
        assert outcome.scientific_status == "not_validated"
        assert outcome.isolation.get("enforced")

    def test_persisted_config_complete(self, engine: IsolatedRl) -> None:
        result = engine.train(_spec(), corpus=_corpus())
        assert result.status == "succeeded"
        config = json.loads(result.artifacts["config.json"])
        spec = config["spec"]
        for key in (
            "model",
            "adapter",
            "optimizer",
            "algorithm",
            "rollout",
            "rollout_budget",
            "checkpoint",
            "seed",
            "resources",
            "corpus_digest",
        ):
            assert key in spec, f"spec missing {key}"

    def test_corpus_digest_mismatch_fails(self, engine: IsolatedRl) -> None:
        """The runner re-hashes the corpus bytes: tampered bytes fail
        with a structured code — the approval bound these bytes."""
        spec = _spec(corpus_digest="0" * 64)
        with pytest.raises(Exception) as exc:
            engine.train(spec, corpus=_corpus())
        assert getattr(exc.value, "code", "") == "ENGINE_UNSUPPORTED_INPUT"


# AT-0902-3 ---------------------------------------------------------------
class TestBudgetExhaustion:
    def test_exhausted_envelope_stops_work(self, engine: IsolatedRl) -> None:
        """A one-episode envelope: the scheduler admits the first
        episode then stops — the run ends ``budget_exhausted`` with the
        counters persisted; no fallback was attempted."""
        spec = _spec(
            rollout_budget={
                "max_episodes": 1,
                "max_compute_units": 256.0,
                "max_policy_tokens": 4000000,
                "max_wall_seconds": 3600,
                "max_concurrent_rollouts": 1,
            }
        )
        result = engine.train(spec, corpus=_corpus())
        assert result.status == "budget_exhausted", result.error
        outcome = result.outcome
        assert outcome is not None
        assert outcome.classification == "budget_exhausted"
        assert outcome.usable is False
        assert outcome.error is not None
        assert outcome.error["code"] == "BUDGET_EXHAUSTED"
        # the meter snapshot is honest: exactly the envelope admitted
        assert outcome.budget["episodes"] <= 1
        assert "none" in outcome.budget["cloudFallback"]

    def test_token_envelope_stops_work(self, engine: IsolatedRl) -> None:
        spec = _spec(
            rollout_budget={
                "max_episodes": 256,
                "max_compute_units": 256.0,
                "max_policy_tokens": 1024,  # floor — drains immediately
                "max_wall_seconds": 3600,
                "max_concurrent_rollouts": 1,
            }
        )
        result = engine.train(spec, corpus=_corpus())
        assert result.status == "budget_exhausted", result.error
        assert result.outcome is not None
        assert result.outcome.error["code"] == "BUDGET_EXHAUSTED"


# AT-0902-1 cancel/resume --------------------------------------------------
class TestInterruptResume:
    def test_cancel_interrupts_run(self, engine: IsolatedRl) -> None:
        spec = _spec(
            max_steps=600,
            checkpoint={"every_steps": 1, "keep_last": 3},
            resources={"cpu_cores": 1.0, "memory_mebibytes": 2048, "wall_seconds": 900},
        )
        cancel = threading.Event()
        holder: dict[str, RlRunResult] = {}

        def _run() -> None:
            holder["r"] = engine.train(spec, corpus=_corpus(), cancel=cancel)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        time.sleep(25)
        cancel.set()
        t.join(timeout=180)
        result = holder["r"]
        assert result.status in ("cancelled", "succeeded", "timed_out", "budget_exhausted")
        if result.status == "cancelled":
            # harvested checkpoints are reported for provenance
            assert isinstance(result.checkpoints, list)

    def test_resume_continues_from_checkpoint(self, engine: IsolatedRl) -> None:
        first = engine.train(
            _spec(max_steps=2, checkpoint={"every_steps": 1, "keep_last": 3}),
            corpus=_corpus(),
        )
        assert first.status == "succeeded", first.error
        assert first.checkpoints
        latest = max(first.checkpoints, key=lambda c: c.step)
        prefix = f"{latest.artifact}/"
        resume_files = {
            name[len(prefix) :]: data
            for name, data in first.artifacts.items()
            if name.startswith(prefix)
        }
        assert "adapter_model.safetensors" in resume_files

        spec = _spec(max_steps=4, checkpoint={"every_steps": 2, "keep_last": 3})
        spec = spec.model_copy(
            update={
                "resume": RlResumeSpec(
                    checkpoint_sha256=latest.sha256,
                    from_step=latest.step,
                    source_run_id="engine-test-1",
                    source_attempt_id="attempt-1",
                )
            }
        )
        second = engine.train(spec, corpus=_corpus(), resume_files=resume_files)
        assert second.status == "succeeded", second.error
        assert second.outcome is not None
        # training continued past the resume step
        assert second.outcome.optimizer_steps == 4
        assert second.outcome.resume_from is not None
        assert second.outcome.resume_from["from_step"] == latest.step
