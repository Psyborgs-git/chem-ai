"""CS-0801 contracts — SFT training spec, dataset example shape, outcome.

Mirrors the qcengine adapter: pure pydantic, no science/trainer imports
at module level — the host can import this without torch. Anything the
trainer does not understand raises ``TrainerFailure``; the runner turns
that into the structured ``{"code","message"}`` error the executor
relays back to the caller.

The dataset contract encodes §17.2-17.3:
- an example carries context, observable messages/tool calls/results,
  the reviewed response, label provenance, rights and a split
  partition — never a hidden reasoning trace;
- only ``train``-partition examples may enter the loss; ``development``
  is eval telemetry only; ``calibration``/``final`` stay untouched.
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
# dataset example (§17.2-17.3)
# ------------------------------------------------------------------

PARTITIONS = ("train", "development", "calibration", "final")
MESSAGE_ROLES = ("user", "assistant", "system", "tool")

# Keys that would smuggle a hidden reasoning trace into the dataset
# (§17.3). Checked recursively at validation so nothing internal can
# leak into the training bytes.
_FORBIDDEN_TRACE_KEYS = (
    "rationale",
    "reasoning",
    "chain_of_thought",
    "chainOfThought",
    "hidden_reasoning",
    "cot",
    "internal_thought",
)


def _scan_forbidden_keys(value: Any, path: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            where = f"{path}.{key}" if path else str(key)
            if str(key).lower() in {k.lower() for k in _FORBIDDEN_TRACE_KEYS}:
                hits.append(where)
            hits.extend(_scan_forbidden_keys(item, where))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hits.extend(_scan_forbidden_keys(item, f"{path}[{index}]"))
    return hits


class SftContext(StrictModel):
    task_id: str | None = None
    session_id: str | None = None
    manifest_id: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class SftMessage(StrictModel):
    """One observable conversation entry — never a hidden trace."""

    role: Literal["user", "assistant", "system", "tool"]
    kind: Literal["message", "tool_call", "tool_result"] = "message"
    content: str
    refs: list[str] = Field(default_factory=list)


class SftToolCall(StrictModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = None


class SftToolResult(StrictModel):
    name: str
    call_id: str | None = None
    content: str


class SftResponse(StrictModel):
    content: str
    refs: list[str] = Field(default_factory=list)


class SftLabelProvenance(StrictModel):
    """Where the supervision signal came from (§17.3)."""

    message_id: str | None = None
    author_principal_id: str | None = None
    reviewed_at: str | None = None
    kind: str = "reviewed_response"
    reason: str | None = None
    criterion: str | None = None


class SftRights(StrictModel):
    training: str = "unknown"
    source_classes: list[str] = Field(default_factory=list)


class SftTrainingExample(StrictModel):
    """One reviewed training example (§17.2).

    ``partition`` decides use: ``train`` enters the loss,
    ``development`` is eval telemetry only, ``calibration``/``final``
    are held out untouched.
    """

    schema_name: Literal["sft_example"] = "sft_example"
    schema_version: Literal[1] = 1
    example_id: str
    context: SftContext
    messages: list[SftMessage] = Field(min_length=1)
    tool_calls: list[SftToolCall] = Field(default_factory=list)
    tool_results: list[SftToolResult] = Field(default_factory=list)
    response: SftResponse
    provenance: SftLabelProvenance
    rights: SftRights
    partition: Literal["train", "development", "calibration", "final"]
    group_keys: list[str] = Field(min_length=1)
    example_digest: str

    @model_validator(mode="after")
    def _no_hidden_traces(self) -> Self:
        hits = _scan_forbidden_keys(self.model_dump())
        if hits:
            raise ValueError(
                "hidden reasoning trace keys forbidden in training examples: " + ",".join(hits)
            )
        return self

    @classmethod
    def digest_payload(cls, example: dict[str, Any]) -> str:
        """Content digest over the supervision payload (§17.3
        deduplication key — context+messages+tools+response)."""
        return sha256_text(
            _canonical_json(
                {
                    "context": example.get("context"),
                    "messages": example.get("messages"),
                    "tool_calls": example.get("tool_calls"),
                    "tool_results": example.get("tool_results"),
                    "response": example.get("response"),
                }
            )
        )


# ------------------------------------------------------------------
# model / adapter / optimizer config (§17.4 persisted config)
# ------------------------------------------------------------------

BASE_ARCHITECTURES = {
    # Tiny CPU-friendly pico-GPT constructed locally (U08/U13 unknown):
    # deterministic init from `model.init_seed`; ~0.86M parameters at
    # default dims. Honest capability: a fixture base, never an LLM
    # with scientific competence.
    "pico-gpt-v1": {
        "n_layer": 4,
        "n_head": 4,
        "n_embd": 128,
        "block_size": 256,
        "vocab_size": 96,
        "tie_weights": True,
    }
}

# Licenses the workspace may bind to a run via approval (§17.4).
# `fixture-internal` is the locally-constructed pico base — it cannot
# leave the vault and is never marketed as a real model.
MODEL_LICENSES: dict[str, dict[str, Any]] = {
    "fixture-internal": {
        "spdx": None,
        "training": "allowed",
        "export": "denied",
        "note": "locally constructed fixture base; vault-scoped",
    },
}


class SftModelSpec(StrictModel):
    base_model_id: str
    architecture: str
    init_seed: int = Field(ge=0)
    license_id: str
    base_sha256: str | None = None
    tokenizer_sha256: str | None = None

    @field_validator("architecture")
    @classmethod
    def _architecture_known(cls, value: str) -> str:
        if value not in BASE_ARCHITECTURES:
            raise ValueError(f"unsupported architecture {value!r}")
        return value

    @field_validator("license_id")
    @classmethod
    def _license_known(cls, value: str) -> str:
        if value not in MODEL_LICENSES:
            raise ValueError(f"unknown license {value!r}")
        return value

    @model_validator(mode="after")
    def _license_allows_training(self) -> Self:
        if MODEL_LICENSES[self.license_id].get("training") != "allowed":
            raise ValueError(f"license {self.license_id} does not allow training")
        return self


class SftAdapterConfig(StrictModel):
    method: Literal["lora"] = "lora"
    rank: int = Field(default=8, ge=1, le=64)
    alpha: int = Field(default=16, ge=1, le=256)
    dropout: float = Field(default=0.0, ge=0.0, le=0.5)
    target_modules: list[str] = Field(default_factory=lambda: ["c_attn", "c_proj"], min_length=1)


class SftOptimizerSpec(StrictModel):
    name: Literal["adamw"] = "adamw"
    learning_rate: float = Field(default=3e-4, gt=0.0, le=0.1)
    scheduler: Literal["linear", "constant"] = "linear"
    warmup_steps: int = Field(default=0, ge=0)
    weight_decay: float = Field(default=0.0, ge=0.0, le=10.0)
    max_grad_norm: float = Field(default=1.0, gt=0.0, le=100.0)


class SftCheckpointPolicy(StrictModel):
    every_steps: int = Field(default=5, ge=1, le=1000)
    keep_last: int = Field(default=3, ge=1, le=20)


class SftResourceEnvelope(StrictModel):
    """Approved resource envelope — admission checks it BEFORE the
    run is admitted (§13.6, §17.4)."""

    cpu_cores: float = Field(default=1.0, gt=0.0, le=16.0)
    memory_mebibytes: int = Field(default=1024, ge=128, le=32768)
    wall_seconds: int = Field(default=600, ge=30, le=14400)


class SftResumeSpec(StrictModel):
    """Resume provenance — the checkpoint the run continues from and
    where it came from (AT-0801-3)."""

    checkpoint_sha256: str
    from_step: int = Field(ge=0)
    source_run_id: str
    source_attempt_id: str


class SftTrainSpec(StrictModel):
    """The complete persisted training config (§17.4): base/tokenizer
    hashes, adapter, preprocessing, seeds, optimizer/scheduler, batch
    shape, sequence length, precision, checkpoint policy and the
    approved resource envelope."""

    schema_name: Literal["sft_train_spec"] = "sft_train_spec"
    schema_version: Literal[1] = 1
    model: SftModelSpec
    adapter: SftAdapterConfig = SftAdapterConfig()
    optimizer: SftOptimizerSpec = SftOptimizerSpec()
    batch_size: int = Field(default=4, ge=1, le=64)
    grad_accumulation: int = Field(default=1, ge=1, le=64)
    seq_length: int = Field(default=256, ge=32, le=2048)
    precision: Literal["fp32"] = "fp32"
    max_steps: int = Field(default=20, ge=1, le=5000)
    eval_every: int = Field(default=5, ge=1, le=1000)
    checkpoint: SftCheckpointPolicy = SftCheckpointPolicy()
    seed: int = Field(default=0, ge=0)
    resources: SftResourceEnvelope = SftResourceEnvelope()
    dataset_digest: str
    resume: SftResumeSpec | None = None

    @model_validator(mode="after")
    def _seq_length_fits_block(self) -> Self:
        arch = BASE_ARCHITECTURES[self.model.architecture]
        if self.seq_length > int(arch["block_size"]):
            raise ValueError(
                f"seq_length {self.seq_length} exceeds {self.model.architecture} "
                f"block_size {arch['block_size']}"
            )
        return self

    def digest(self) -> str:
        return sha256_text(_canonical_json(self.model_dump(mode="json")))


# ------------------------------------------------------------------
# outcome (§17.4 telemetry + AT-0801-1 proof)
# ------------------------------------------------------------------


class SftCheckpoint(StrictModel):
    step: int
    sha256: str
    artifact: str
    optimizer_sha256: str | None = None


class SftParameterProof(StrictModel):
    """AT-0801-1: real weight updates. The adapter tensor hash changes;
    the frozen base hash does not (PEFT did not touch the base). The
    persisted adapter file is reloaded and verified byte-identical —
    a real checkpoint save/load roundtrip."""

    adapter_before_sha256: str
    adapter_after_sha256: str
    frozen_before_sha256: str
    frozen_after_sha256: str
    adapter_changed: bool
    frozen_changed: bool
    reload_sha256: str | None = None
    reload_matches: bool = False


class SftOutcome(StrictModel):
    """What the runner reports — honest classification, never
    scientific validation (§17.4/§18.4)."""

    status: Literal["succeeded", "failed", "cancelled", "timed_out", "interrupted"]
    usable: bool
    classification: Literal[
        "completed",
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
    steps_completed: int = 0
    train_examples: int = 0
    eval_examples: int = 0
    final_train_loss: float | None = None
    final_eval_loss: float | None = None
    parameter_proof: SftParameterProof | None = None
    checkpoints: list[SftCheckpoint] = Field(default_factory=list)
    telemetry_tail: list[dict[str, Any]] = Field(default_factory=list)
    resume_from: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    scientific_status: Literal["not_validated"] = "not_validated"
    isolation: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "BASE_ARCHITECTURES",
    "MODEL_LICENSES",
    "PARTITIONS",
    "SftAdapterConfig",
    "SftCheckpoint",
    "SftCheckpointPolicy",
    "SftContext",
    "SftLabelProvenance",
    "SftMessage",
    "SftModelSpec",
    "SftOptimizerSpec",
    "SftOutcome",
    "SftParameterProof",
    "SftResourceEnvelope",
    "SftResponse",
    "SftResumeSpec",
    "SftRights",
    "SftToolCall",
    "SftToolResult",
    "SftTrainSpec",
    "SftTrainingExample",
    "StrictModel",
    "TrainerFailure",
    "sha256_bytes",
    "sha256_text",
]
