"""RL training corpus contract + canonical digest (CS-0902, §19.4).

Importable on the host AND inside the pinned trainer image — pure
pydantic over the CS-0901 environment contracts, no torch. The corpus
is the approval-bound input to a run: the task registry, the frozen
evidence snapshot the tools replay from, the policy principal the
environment checks grants for, and the contract versions pinned for
the run. Its digest is stamped into ``RlTrainSpec.corpus_digest`` and
re-verified inside the container before a single episode starts.
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import Field, field_validator

from .environment.contracts import (
    ENV_CONTRACT_VERSION,
    REWARD_CONTRACT_VERSION,
    EvidenceSnapshot,
    RlPolicyRef,
    RlTaskDef,
    StrictModel,
    canonical_json,
)

RL_CORPUS_SCHEMA = "rl_training_corpus"


class RlCorpus(StrictModel):
    """The complete, digestible corpus document for one RL run."""

    schema_name: Literal["rl_training_corpus"] = "rl_training_corpus"
    env_contract_version: int = Field(default=ENV_CONTRACT_VERSION, ge=1)
    reward_contract_version: int = Field(default=REWARD_CONTRACT_VERSION, ge=1)
    tasks: list[RlTaskDef] = Field(min_length=1)
    snapshot: EvidenceSnapshot
    policy: RlPolicyRef

    @field_validator("tasks")
    @classmethod
    def _unique_task_ids(cls, value: list[RlTaskDef]) -> list[RlTaskDef]:
        ids = [t.task_id for t in value]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate task_id in corpus")
        return value

    def digest(self) -> str:
        """Canonical sha256 — the digest the approval binds to and the
        container re-verifies."""
        return hashlib.sha256(
            canonical_json(self.model_dump(mode="json")).encode("utf-8")
        ).hexdigest()


def parse_corpus(payload: dict[str, Any]) -> RlCorpus:
    """Validate the raw corpus document against the real contracts."""
    return RlCorpus.model_validate(payload)
