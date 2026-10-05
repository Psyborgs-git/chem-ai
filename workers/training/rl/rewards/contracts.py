"""Reward contracts (CS-0901, §19.3).

Two layers, strictly separated:

- **Eligibility gates** — pass/fail facts about the episode (proper
  termination, pinned task, no denied actions, version match, evidence
  integrity). They sit *outside* the performance trade-off: a failed
  gate makes the episode ineligible, it does not shave the score.
- **Versioned measurable components** — task correctness, supported
  evidence, valid tool execution, calibrated uncertainty/appropriate
  abstention, resource efficiency. Every component records the inputs
  it measured (provenance).

Forbidden as truth signals and therefore absent from every contract
here: novelty, verbosity, citation *counts*, and the model's own
confidence. A model-based judge may assist review but is never the
arbiter — every component derives from the recorded trace.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from ..environment.contracts import StrictModel

REWARD_SUITE_SCHEMA = "rl_reward_suite"
REWARD_RECORD_SCHEMA = "rl_reward_record"

# Gate ids — frozen vocabulary, each computed in service.py.
GATE_IDS = (
    "proper_termination",
    "task_pinned",
    "no_denied_actions",
    "version_match",
    "evidence_integrity",
)

# Component ids — frozen vocabulary (§19.3).
COMPONENT_IDS = (
    "task_correctness",
    "supported_evidence",
    "valid_tool_execution",
    "uncertainty_calibration",
    "resource_efficiency",
)

# Component weights for the scalar (only a convenience ordering —
# gates, not the scalar, decide eligibility).
DEFAULT_WEIGHTS: dict[str, float] = {
    "task_correctness": 3.0,
    "supported_evidence": 1.0,
    "valid_tool_execution": 1.0,
    "uncertainty_calibration": 1.0,
    "resource_efficiency": 0.5,
}


class GateOutcome(StrictModel):
    gate: str
    passed: bool
    detail: str = ""


class ComponentScore(StrictModel):
    """One measured component — ``value=None`` means genuinely not
    measurable for this episode (e.g. zero tool calls for the
    tool-execution component); it is excluded from the weighted scalar
    rather than silently zeroed."""

    component: str
    version: int
    value: float | None = None
    detail: str = ""
    provenance: dict[str, Any] = Field(default_factory=dict)


class RewardRecord(StrictModel):
    """Component-level reward record for one episode, with provenance
    and frozen-version echo (§19.3)."""

    schema_name: Literal["rl_reward_record"] = "rl_reward_record"
    reward_contract_version: int
    env_contract_version: int
    task_id: str
    task_version: int
    snapshot_digest: str
    seed: int
    episode_id: str
    eligible: bool
    gates: list[GateOutcome] = Field(default_factory=list)
    components: list[ComponentScore] = Field(default_factory=list)
    scalar: float | None = None
    task_completed: bool = False
    labels: dict[str, Any] = Field(default_factory=dict)


class RewardExpectation(StrictModel):
    """One suite expectation over an aggregate metric. ``metric`` is a
    key into ``RewardSuiteReport.metrics`` (``eligible_rate``,
    ``task_completion`` or ``component:<id>``)."""

    metric: str = Field(min_length=1, max_length=80)
    direction: Literal["min", "max"] = "min"
    value: float


class RewardSuiteDef(StrictModel):
    """Versioned reward-suite definition — what 'the reward suite
    passes' means for a batch of episodes."""

    schema_name: Literal["rl_reward_suite"] = "rl_reward_suite"
    name: str = Field(min_length=1, max_length=160)
    version: int = Field(ge=1)
    expectations: list[RewardExpectation] = Field(default_factory=list)


class ExpectationEval(StrictModel):
    metric: str
    direction: str = "min"
    value: float
    observed: float | None = None
    status: Literal["pass", "fail"]


class RewardSuiteReport(StrictModel):
    """Aggregate verdict over scored episodes — denominators and
    per-component means, never just a bare scalar average."""

    schema_name: Literal["rl_reward_suite_report"] = "rl_reward_suite_report"
    suite: str
    suite_version: int
    episodes: int = 0
    eligible_episodes: int = 0
    metrics: dict[str, float | None] = Field(default_factory=dict)
    expectations: list[ExpectationEval] = Field(default_factory=list)
    passed: bool = False
    labels: dict[str, Any] = Field(default_factory=dict)
