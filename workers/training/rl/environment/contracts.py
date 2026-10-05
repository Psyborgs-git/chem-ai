"""RL environment contracts (CS-0901, §19.2).

Pure pydantic (``extra="forbid"``, frozen) — the same structural style
as the CS-0803 evaluation contracts. Three deliberate rules mirror
the handoff:

- The policy-facing surface is a *separate* model set
  (``RlTaskPublic`` / ``Observation``). Reward-side data
  (``RlTaskTarget``) lives only on the internal task definition and
  can never serialize into an observation.
- Every episode pins task version, environment contract version,
  reward contract version and the evidence-snapshot digest at
  ``reset`` — versions are frozen within a run (§19.3).
- Replay outputs are *identified as replay* with provenance; an
  unmatched action yields an explicit ``unavailable`` status, never an
  invented oracle (AT-0901-3).
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

# --- versions -----------------------------------------------------

ENV_CONTRACT_VERSION = 1
REWARD_CONTRACT_VERSION = 1
TASK_DEF_SCHEMA = "rl_task_def"
EPISODE_SCHEMA = "rl_episode_record"

ACTION_TYPES = ("tool_call", "final_answer", "abstain", "switch_task", "terminate")

# Observable step/episode statuses.
STATUSES = (
    "ready",  # reset observation
    "ok",  # tool executed (live or replay match)
    "unavailable",  # replay miss / tool temporarily unavailable (AT-0901-3)
    "unknown_tool",  # unregistered name — closed catalog
    "denied",  # forbidden verb / missing capability / task scope breach
    "invalid_action",  # malformed action payload
    "budget_exhausted",  # a hard budget hit zero — episode ends
    "finished",  # final answer / abstain recorded
)


class StrictModel(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}


def canonical_json(payload: object) -> str:
    """Stable canonical form — used for replay matching and digests."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EnvConfigError(Exception):
    """Refused environment configuration — (code, message)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --- actions ------------------------------------------------------


class ActionUsage(StrictModel):
    """Policy-reported generation usage for one action. The env only
    *counts* it — the hard token budget is enforced env-side."""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)


class ToolCallAction(StrictModel):
    type: Literal["tool_call"] = "tool_call"
    tool: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)
    usage: ActionUsage | None = None


class FinalAnswerAction(StrictModel):
    """A terminal answer. ``citations`` names snapshot evidence ids the
    policy claims support the answer — fabricated ids are an integrity
    gate violation, not a reward strategy (§19.3)."""

    type: Literal["final_answer"] = "final_answer"
    answer: str = Field(max_length=20000)
    citations: list[str] = Field(default_factory=list, max_length=64)
    usage: ActionUsage | None = None


class AbstainAction(StrictModel):
    type: Literal["abstain"] = "abstain"
    reason: str = Field(default="", max_length=2000)
    usage: ActionUsage | None = None


class SwitchTaskAction(StrictModel):
    """Mid-episode task switching is expressible so the environment can
    *deny it explicitly* — an 'easier task' move is a scope violation,
    never a silent retarget (§19.3)."""

    type: Literal["switch_task"] = "switch_task"
    task_id: str = Field(min_length=1, max_length=120)
    usage: ActionUsage | None = None


class TerminateAction(StrictModel):
    type: Literal["terminate"] = "terminate"
    reason: str = Field(default="policy_terminate", max_length=200)
    usage: ActionUsage | None = None


RlAction = Annotated[
    ToolCallAction | FinalAnswerAction | AbstainAction | SwitchTaskAction | TerminateAction,
    Field(discriminator="type"),
]


# --- policy reference ---------------------------------------------


class RlPolicyRef(StrictModel):
    """Who the policy is, for permission purposes.

    ``kind`` must be ``agent`` — a user/service principal is not a
    trainable policy. ``grants`` are capability names re-checked by the
    environment through the shared policy vocabulary: approval and
    service-only capabilities are stripped exactly as the server does,
    so a policy can never hold ``approve_*`` or label access.
    """

    policy_id: str = Field(min_length=1, max_length=120)
    kind: Literal["agent"] = "agent"
    grants: list[str] = Field(default_factory=list)
    allowed_tools: list[str] | None = None  # None = full permitted catalog


# --- tasks --------------------------------------------------------


class RlMessage(StrictModel):
    role: Literal["user", "system", "tool"]
    content: str


class BudgetEnvelope(StrictModel):
    """Hard per-episode budgets — enforced by the environment,
    independently of the model (§19.2)."""

    max_steps: int = Field(default=16, ge=1, le=512)
    max_tool_calls: int = Field(default=8, ge=0, le=128)
    max_wall_seconds: float = Field(default=300.0, gt=0, le=7200)
    max_policy_tokens: int = Field(default=4096, ge=1, le=1_000_000)
    max_compute_units: float = Field(default=16.0, gt=0, le=10_000)


class RlTaskTarget(StrictModel):
    """Reward-side task data — NEVER observable by the policy.

    Semantics mirror the evaluation targets (exact/contains/abstain/
    json_object/refusal) so reward scoring stays honest and binary.
    ``required_evidence_ids`` are snapshot evidence ids a supported
    answer must cite.
    """

    expect: Literal["exact", "contains", "abstain", "json_object", "refusal"]
    value: str = ""
    required_terms: list[str] = Field(default_factory=list)
    forbidden_terms: list[str] = Field(default_factory=list)
    required_evidence_ids: list[str] = Field(default_factory=list)


class RlTaskDef(StrictModel):
    """Versioned training task definition (reward contract data
    included — it is the *environment's own* reward input, wholly
    separate from the held-out evaluation label store)."""

    schema_name: Literal["rl_task_def"] = "rl_task_def"
    task_id: str = Field(min_length=1, max_length=120)
    task_version: int = Field(default=1, ge=1)
    kind: Literal["task", "safety", "privacy"] = "task"
    messages: list[RlMessage] = Field(min_length=1)
    context_refs: list[str] = Field(default_factory=list)
    subgroup: str = Field(default="default", min_length=1, max_length=120)
    answerable: bool = True
    allowed_tools: list[str] = Field(default_factory=list)
    budgets: BudgetEnvelope | None = None
    target: RlTaskTarget | None = None

    def public(self) -> RlTaskPublic:
        """The policy-visible projection — target stripped."""
        return RlTaskPublic(
            task_id=self.task_id,
            task_version=self.task_version,
            kind=self.kind,
            messages=self.messages,
            context_refs=self.context_refs,
            subgroup=self.subgroup,
            answerable=self.answerable,
            allowed_tools=self.allowed_tools,
            budgets=self.budgets,
        )


class RlTaskPublic(StrictModel):
    """Everything the policy may know about its task."""

    task_id: str
    task_version: int
    kind: str
    messages: list[RlMessage]
    context_refs: list[str]
    subgroup: str
    answerable: bool
    allowed_tools: list[str]
    budgets: BudgetEnvelope | None


# --- evidence snapshot / replay -----------------------------------


class ReplayEntry(StrictModel):
    """One recorded tool outcome pinned inside the snapshot."""

    replay_id: str = Field(min_length=1, max_length=120)
    tool: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)

    def key(self) -> str:
        return f"{self.tool}:{canonical_json(self.arguments)}"


class EvidenceSnapshot(StrictModel):
    """The frozen replay/evidence view for one batch of episodes.

    ``evidence_ids`` is the authoritative set of citable evidence —
    citations naming anything else are fabricated (§19.3)."""

    snapshot_id: str = Field(min_length=1, max_length=120)
    replay: list[ReplayEntry] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)

    def digest(self) -> str:
        body = {
            "snapshot_id": self.snapshot_id,
            "evidence_ids": sorted(self.evidence_ids),
            "replay": sorted(e.key() for e in self.replay),
        }
        return sha256_text(canonical_json(body))

    def lookup(self, tool: str, arguments: dict[str, Any]) -> ReplayEntry | None:
        key = f"{tool}:{canonical_json(arguments)}"
        for entry in self.replay:
            if entry.key() == key:
                return entry
        return None

    def evidence_set(self) -> frozenset[str]:
        return frozenset(self.evidence_ids)


# --- observations (policy-visible ONLY) ----------------------------


class Observation(StrictModel):
    """The ONLY structure a policy ever receives.

    It carries task public data, tool result payloads (marked replay),
    remaining budgets and status — never hidden labels, reward-only
    metadata, credentials or evaluator-only outputs.
    """

    status: Literal[
        "ready",
        "ok",
        "unavailable",
        "unknown_tool",
        "denied",
        "invalid_action",
        "budget_exhausted",
        "finished",
    ]
    step_index: int = 0
    done: bool = False
    task: RlTaskPublic | None = None
    result: dict[str, Any] | None = None
    replay: bool = False
    replay_id: str | None = None
    budgets_remaining: dict[str, float] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, str] | None = None


# --- costs / step records / episodes -------------------------------


class RlCost(StrictModel):
    steps: int = 0
    tool_calls: int = 0
    compute_units: float = 0.0
    policy_tokens: int = 0
    wall_seconds: float = 0.0


class RlStep(StrictModel):
    """One trace entry — action, policy-visible observation, cost and
    the raw measurable *reward components* (signals) §19.2 requires
    ``step`` to return. Components are trace data; the policy only
    ever sees ``observation``."""

    index: int
    action_type: str
    tool: str | None = None
    status: str
    done: bool
    observation: Observation
    cost: RlCost = Field(default_factory=RlCost)
    components: dict[str, float] = Field(default_factory=dict)
    error_code: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class EpisodeOutcome(StrictModel):
    reason: Literal["final_answer", "abstain", "policy_terminate", "budget_exhausted", "error"]
    final_answer: str | None = None
    abstained: bool = False
    citations: list[str] = Field(default_factory=list)
    detail: str = ""


class EpisodeRecord(StrictModel):
    """The complete, immutable episode trace — input to the reward
    service and to CS-0902's trainer."""

    schema_name: Literal["rl_episode_record"] = "rl_episode_record"
    episode_id: str
    task_id: str
    task_version: int
    seed: int
    env_contract_version: int
    reward_contract_version: int
    snapshot_digest: str
    policy_id: str
    steps: list[RlStep] = Field(default_factory=list)
    outcome: EpisodeOutcome | None = None
    totals: RlCost = Field(default_factory=RlCost)
    denied_attempts: int = 0
    invalid_actions: int = 0
    unavailable_results: int = 0
    scope_violations: int = 0
    replay_hits: int = 0
    capability: dict[str, Any] = Field(default_factory=dict)
