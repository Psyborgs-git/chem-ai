"""CS-0902 contracts — RL training spec, run-level budget envelope, outcome.

Mirrors the SFT adapter: pure pydantic, no torch/trl imports at module
level — the host can import this without the training stack. Anything
the trainer does not understand raises ``TrainerFailure``; the runner
turns that into the structured ``{"code","message"}`` error the
executor relays back to the caller.

Algorithm selection (§19.4 — verified against the pinned trl==1.14.1,
not assumed): the only supported seam that can drive CS-0901's typed
multi-step ``ResearchRlEnvironment`` is ``GRPOTrainer(rollout_func=…)``.
``environment_factory`` and ``tools`` both require the policy to emit
parseable tool calls through a tool-calling chat template — a
random-init char-level fixture cannot do that, so they are rejected,
not faked. With ``rollout_func`` the driver enumerates the legal typed
actions from the observation's ``constraints``, scores each candidate
under the model (teacher-forced logprobs over its canonical action
marker), softmax-samples and executes it through the real ``env.step``.
The completion interleaves action tokens (``env_mask=1``) with
observation tokens (``env_mask=0``) so the trainer's recomputed
logprobs condition on exactly what the policy saw. GRPO with
``num_iterations=1`` + ``steps_per_generation=1`` is strictly
on-policy; beta=0 drops the KL reference (unsupported for this
environment-form anyway).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TrainerFailure(Exception):
    """Structured trainer failure — (code, message) into result.json."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


# ------------------------------------------------------------------
# model / adapter / optimizer (§19.4 persisted config)
# ------------------------------------------------------------------

RL_ARCHITECTURES = {
    # Tiny CPU-compatible causal LM for RL rollouts (U08 unknown).
    # Same pico-class transformer as CS-0801's base with a larger
    # block so multi-step episode transcripts fit; deterministic init
    # from ``model.init_seed``. Honest capability: a fixture policy,
    # never an LLM with scientific competence.
    "pico-rl-v1": {
        "n_layer": 4,
        "n_head": 4,
        "n_embd": 128,
        "block_size": 1024,
        "vocab_size": 96,
        "tie_weights": True,
    }
}

# Same license vocabulary as the SFT lane — only the locally
# constructed fixture base may bind to an RL run.
RL_MODEL_LICENSES: dict[str, dict[str, Any]] = {
    "fixture-internal": {
        "spdx": None,
        "training": "allowed",
        "export": "denied",
        "note": "locally constructed fixture policy; vault-scoped",
    },
}

REWARD_CONTRACT_VERSION = 1
ENV_CONTRACT_VERSION = 1


class RlModelSpec(StrictModel):
    base_model_id: str
    architecture: str
    init_seed: int = Field(ge=0)
    license_id: str

    @field_validator("architecture")
    @classmethod
    def _architecture_known(cls, value: str) -> str:
        if value not in RL_ARCHITECTURES:
            raise ValueError(f"unsupported architecture {value!r}")
        return value

    @field_validator("license_id")
    @classmethod
    def _license_known(cls, value: str) -> str:
        if value not in RL_MODEL_LICENSES:
            raise ValueError(f"unknown license {value!r}")
        return value

    @model_validator(mode="after")
    def _license_allows_training(self) -> Self:
        if RL_MODEL_LICENSES[self.license_id].get("training") != "allowed":
            raise ValueError(f"license {self.license_id} does not allow training")
        return self


class RlAdapterConfig(StrictModel):
    """LoRA adapter on the fixture base — the trained artifact is a
    real ``adapter_model.safetensors`` that flows through the CS-0802
    registry/serve-compat machinery unchanged."""

    method: Literal["lora"] = "lora"
    rank: int = Field(default=8, ge=1, le=64)
    alpha: int = Field(default=16, ge=1, le=256)
    dropout: float = Field(default=0.0, ge=0.0, le=0.5)
    target_modules: list[str] = Field(default_factory=lambda: ["c_attn", "c_proj"], min_length=1)


class RlOptimizerSpec(StrictModel):
    name: Literal["adamw"] = "adamw"
    learning_rate: float = Field(default=3e-4, gt=0.0, le=0.1)
    scheduler: Literal["linear", "constant"] = "linear"
    warmup_steps: int = Field(default=0, ge=0)
    weight_decay: float = Field(default=0.0, ge=0.0, le=10.0)
    max_grad_norm: float = Field(default=1.0, gt=0.0, le=100.0)


class RlAlgorithmSpec(StrictModel):
    """GRPO family — the only pinned-TRL-supported algorithm for this
    environment shape (see module docstring). ``num_iterations=1`` and
    ``steps_per_generation=1`` keep the run strictly on-policy; a
    non-zero ``beta`` KL reference is unsupported and rejected."""

    family: Literal["grpo"] = "grpo"
    num_generations: int = Field(default=4, ge=2, le=32)
    tasks_per_batch: int = Field(default=2, ge=1, le=16)
    epsilon: float = Field(default=0.2, gt=0.0, le=1.0)
    epsilon_high: float = Field(default=0.2, gt=0.0, le=1.0)
    # Pinned to 0 (no KL term) — floats are not legal Literal args
    beta: float = Field(default=0.0, ge=0.0, le=0.0)
    scale_rewards: Literal["group", "batch", "none"] = "group"
    loss_type: Literal["dapo", "grpo", "bnpo", "dr_grpo", "luspo"] = "dapo"
    temperature: float = Field(default=1.0, gt=0.0, le=4.0)
    importance_sampling_level: Literal["token", "sequence"] = "token"


class RlRolloutSpec(StrictModel):
    """Episode-driver bounds inside one rollout — sequence length and
    step caps that keep every episode inside the model's block and the
    task's own budget."""

    max_episode_actions: int = Field(default=12, ge=1, le=64)
    max_candidates: int = Field(default=24, ge=2, le=64)
    prompt_max_tokens: int = Field(default=128, ge=16, le=512)
    completion_max_tokens: int = Field(default=896, ge=32, le=2048)


class RlRolloutBudget(StrictModel):
    """The run-level compute envelope (§19.4, AT-0902-3): the rollout
    scheduler admits episodes only while every meter stays inside the
    envelope; the first admission that would exceed it raises
    ``BUDGET_EXHAUSTED`` and the run STOPS — there is no cloud
    fallback path by design (P10 remains disabled).

    ``max_concurrent_rollouts`` declares the concurrency ceiling the
    scheduler must honor; the v1 driver runs episodes sequentially so
    the enforced in-flight count is 1 — the bound is recorded, never
    exceeded."""

    max_episodes: int = Field(default=256, ge=1, le=100000)
    max_compute_units: float = Field(default=256.0, gt=0.0, le=1e6)
    max_policy_tokens: int = Field(default=4_000_000, ge=1024, le=10**9)
    max_wall_seconds: int = Field(default=3600, ge=30, le=86400)
    max_concurrent_rollouts: int = Field(default=1, ge=1, le=8)


class RlCheckpointPolicy(StrictModel):
    every_steps: int = Field(default=4, ge=1, le=1000)
    keep_last: int = Field(default=3, ge=1, le=20)


class RlResourceEnvelope(StrictModel):
    """Approved resource envelope — admission checks it BEFORE the
    run is admitted (§13.6, §17.4)."""

    cpu_cores: float = Field(default=1.0, gt=0.0, le=16.0)
    memory_mebibytes: int = Field(default=1024, ge=128, le=32768)
    wall_seconds: int = Field(default=600, ge=30, le=14400)


class RlResumeSpec(StrictModel):
    """Resume provenance — the checkpoint the run continues from and
    where it came from (mirrors AT-0801-3)."""

    checkpoint_sha256: str
    from_step: int = Field(ge=0)
    source_run_id: str
    source_attempt_id: str


class RlTrainSpec(StrictModel):
    """The complete persisted RL training config: base/tokenizer
    identity, adapter, optimizer, algorithm family + its hyperparams,
    the run-level rollout envelope, checkpoint policy, seeds, resource
    envelope and the frozen corpus digest the approval binds to.

    ``corpus_digest`` is the sha256 of the canonical corpus document —
    ``{tasks: [RlTaskDef], snapshot: EvidenceSnapshot,
    policy: RlPolicyRef, rewardContractVersion, envContractVersion}``
    — validated inside the runner by the REAL CS-0901 contracts; the
    spec itself never duplicates those shared models."""

    schema_name: Literal["rl_train_spec"] = "rl_train_spec"
    schema_version: Literal[1] = 1
    model: RlModelSpec
    adapter: RlAdapterConfig = RlAdapterConfig()
    optimizer: RlOptimizerSpec = RlOptimizerSpec()
    algorithm: RlAlgorithmSpec = RlAlgorithmSpec()
    rollout: RlRolloutSpec = RlRolloutSpec()
    rollout_budget: RlRolloutBudget = RlRolloutBudget()
    max_steps: int = Field(default=8, ge=1, le=5000)
    checkpoint: RlCheckpointPolicy = RlCheckpointPolicy()
    seed: int = Field(default=0, ge=0)
    resources: RlResourceEnvelope = RlResourceEnvelope()
    corpus_digest: str
    reward_contract_version: int = Field(default=REWARD_CONTRACT_VERSION, ge=1)
    resume: RlResumeSpec | None = None

    def digest(self) -> str:
        return sha256_text(_canonical_json(self.model_dump(mode="json")))


# ------------------------------------------------------------------
# outcome (telemetry + AT-0902-1 proof)
# ------------------------------------------------------------------


class RlCheckpoint(StrictModel):
    step: int
    sha256: str
    artifact: str
    optimizer_sha256: str | None = None


class RlParameterProof(StrictModel):
    """AT-0902-1: real weight updates. The adapter tensor hash changes
    under a real optimizer step; the frozen base hash does not (PEFT
    did not touch it). The persisted adapter file is reloaded and
    verified — a real checkpoint save/load roundtrip."""

    adapter_before_sha256: str
    adapter_after_sha256: str
    frozen_before_sha256: str
    frozen_after_sha256: str
    adapter_changed: bool
    frozen_changed: bool
    reload_sha256: str | None = None
    reload_matches: bool = False


class RlEpisodeSummary(StrictModel):
    """Per-episode provenance row (telemetry, not capability)."""

    episode_id: str
    task_id: str
    seed: int
    eligible: bool
    scalar: float | None = None
    task_completed: bool = False
    outcome_reason: str | None = None
    steps: int = 0
    tool_calls: int = 0
    compute_units: float = 0.0
    policy_tokens: int = 0
    artifact: str | None = None


class RlOutcome(StrictModel):
    """What the runner reports — honest classification, never
    scientific validation (§19.4/§18.4). ``budget_exhausted`` is a
    terminal classification: the rollout scheduler stopped admitting
    episodes because the compute envelope drained (AT-0902-3)."""

    status: Literal[
        "succeeded", "failed", "cancelled", "timed_out", "budget_exhausted", "interrupted"
    ]
    usable: bool
    classification: Literal[
        "completed",
        "budget_exhausted",
        "no_checkpoint",
        "incomplete_run",
        "cancelled",
        "timed_out",
        "malformed_result",
        "unavailable",
    ]
    base_model_id: str | None = None
    base_sha256: str | None = None
    tokenizer_sha256: str | None = None
    adapter_sha256: str | None = None
    config_digest: str | None = None
    corpus_digest: str | None = None
    optimizer_steps: int = 0
    episodes_completed: int = 0
    reward_first_mean: float | None = None
    reward_last_mean: float | None = None
    budget: dict[str, Any] = Field(default_factory=dict)
    episodes: list[RlEpisodeSummary] = Field(default_factory=list)
    parameter_proof: RlParameterProof | None = None
    checkpoints: list[RlCheckpoint] = Field(default_factory=list)
    telemetry_tail: list[dict[str, Any]] = Field(default_factory=list)
    resume_from: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    scientific_status: Literal["not_validated"] = "not_validated"
    isolation: dict[str, Any] = Field(default_factory=dict)
