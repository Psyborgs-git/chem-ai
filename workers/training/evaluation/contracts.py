"""Evaluation suite contracts (CS-0803, §18.1).

The suite definition is the *versioned registry entry*: tasks, allowed
context reference, pinned tool catalog, resource budget, scoring spec,
review rules and acceptance thresholds — separate from the optimizer's
reward and stored independently of the hidden targets.

Two deliberate structural rules:

- Definitions carry only a ``target_hash`` per task. Target *values*
  live in the hidden label store (`evaluation_labels`); nothing in
  these contracts can serialize a label back out (AT-0803-2).
- An ``EvalThreshold`` may declare ``value=None`` — an unknown
  scientific acceptance threshold (U14). It is stored as a promotion
  blocker and never filled in (§18.3, AT-0803-3).
"""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

SCHEMA_NAME = "eval_suite_def"
SCHEMA_VERSION = 1

SUITE_KINDS = ("development", "final")
TASK_KINDS = ("task", "safety", "privacy")
TARGET_EXPECTS = ("exact", "contains", "abstain", "json_object", "refusal")
SCORING_METRICS = (
    "correctness",
    "abstention_appropriateness",
    "schema_validity",
    "constraint_compliance",
)


class StrictModel(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}


class EvalMessage(StrictModel):
    """One prompt message shown to the model under test — observable
    input only, never a hidden trace or label."""

    role: Literal["user", "system", "tool"]
    content: str


class EvalTaskDef(StrictModel):
    """The PUBLIC part of one evaluation task.

    ``target_hash`` binds the task to a hidden label without exposing
    it; ``answerable=False`` tasks are the insufficient-evidence probes
    that keep an 'always refuse' policy from winning (§18.2).
    """

    example_id: str = Field(min_length=1, max_length=120)
    kind: Literal["task", "safety", "privacy"] = "task"
    messages: list[EvalMessage] = Field(min_length=1)
    context_refs: list[str] = Field(default_factory=list)
    subgroup: str = Field(default="default", min_length=1, max_length=120)
    answerable: bool = True
    group_keys: list[str] = Field(min_length=1)
    source_record_ids: list[str] = Field(default_factory=list)
    target_hash: str | None = None


class EvalTarget(StrictModel):
    """A hidden label — stored outside the suite definition and read
    only by the evaluation service principal (AT-0803-2).

    ``refusal`` targets score whether a forbidden/confidential request
    is declined; ``forbidden_terms`` are canary strings that must never
    appear in the response (never echoed into reports).
    """

    example_id: str = Field(min_length=1, max_length=120)
    expect: Literal["exact", "contains", "abstain", "json_object", "refusal"]
    value: str = ""
    required_terms: list[str] = Field(default_factory=list)
    forbidden_terms: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _payload_coherent(self) -> Self:
        if self.expect == "contains" and not self.required_terms:
            raise ValueError("contains target requires required_terms")
        if self.expect in ("exact", "abstain") and not self.value and self.expect == "exact":
            raise ValueError("exact target requires value")
        return self


class EvalBudget(StrictModel):
    """Frozen per-example resource envelope — identical for both arms."""

    max_tool_calls: int = Field(default=8, ge=0, le=64)
    max_completion_tokens: int = Field(default=512, ge=1, le=65536)
    wall_seconds: int = Field(default=300, ge=1, le=7200)


class EvalToolVersions(StrictModel):
    """Tool pins recorded at suite freeze: the closed agent-tool
    catalog digest plus each allowed tool's descriptor digest."""

    tools: list[dict[str, str]] = Field(default_factory=list)
    catalog_digest: str = ""


class EvalAllowedContext(StrictModel):
    """Declared frozen evidence/retrieval snapshot reference (digest-
    pinned; the run report echoes it verbatim)."""

    reference: str = ""
    digest: str = ""


class EvalThreshold(StrictModel):
    """One acceptance threshold. ``value=None`` is the U14-honest
    'unknown' — stored as a promotion blocker, never invented."""

    metric: str = Field(min_length=1, max_length=80)
    direction: Literal["min", "max"] = "min"
    value: float | None = None


class EvalReviewRules(StrictModel):
    scientific_review_required: bool = True


class EvalSuiteDef(StrictModel):
    """Versioned evaluation registry entry (§18.1)."""

    schema_name: Literal["eval_suite_def"] = "eval_suite_def"
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=160)
    version: int = Field(ge=1)
    purpose: Literal["assistant_sft", "general"] = "assistant_sft"
    kind: Literal["development", "final"]
    tasks: list[EvalTaskDef] = Field(min_length=1)
    allowed_context: EvalAllowedContext = Field(default_factory=EvalAllowedContext)
    tool_versions: EvalToolVersions = Field(default_factory=EvalToolVersions)
    budget: EvalBudget = Field(default_factory=EvalBudget)
    scoring: dict[str, Any] = Field(default_factory=dict)
    review_rules: EvalReviewRules = Field(default_factory=EvalReviewRules)
    thresholds: list[EvalThreshold] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ids_unique(self) -> Self:
        ids = [t.example_id for t in self.tasks]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate example_id in suite tasks")
        return self


# ------------------------------------------------------------------
# run-time outputs (never contain label values — scores/hashes only)
# ------------------------------------------------------------------


class EvalArmOutput(StrictModel):
    """Whatever the model-under-test produced for one example."""

    text: str
    tool_calls: int = 0
    completion_tokens: int = 0
    budget_exhausted: bool = False
    error: str | None = None


class EvalExampleResult(StrictModel):
    """One scored example for one arm — metrics and pass booleans only,
    never the target payload itself."""

    example_id: str
    arm: Literal["baseline", "candidate"]
    kind: str = "task"
    subgroup: str = "default"
    answerable: bool = True
    invalid_reason: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)


class EvalMetricSummary(StrictModel):
    metric: str
    baseline: float | None = None
    candidate: float | None = None
    delta: float | None = None
    evaluated: int = 0


class EvalSubgroupSummary(StrictModel):
    subgroup: str
    evaluated: int = 0
    baseline: float | None = None
    candidate: float | None = None
    small_sample: bool = True


class EvalThresholdEval(StrictModel):
    metric: str
    direction: str = "min"
    value: float | None = None
    observed: float | None = None
    status: Literal["pass", "fail", "unknown"]


class EvalSafetyRegression(StrictModel):
    """Safety/privacy tasks the candidate newly fails vs baseline."""

    new_failures: list[str] = Field(default_factory=list)
    candidate_failures: list[str] = Field(default_factory=list)


class EvalDenominators(StrictModel):
    expected: dict[str, int] = Field(default_factory=dict)
    evaluated: dict[str, int] = Field(default_factory=dict)
    missing: dict[str, list[str]] = Field(default_factory=dict)
    invalid: dict[str, list[str]] = Field(default_factory=dict)
    small_sample: bool = True


class EvalComparisonReport(StrictModel):
    """§18.2 matched-comparison report — both arms on the SAME
    examples, context snapshot, tool pins and budget; with
    denominators, subgroups and uncertainty, never just an average."""

    schema_name: Literal["eval_comparison_report"] = "eval_comparison_report"
    schema_version: Literal[1] = 1
    suite_digest: str = ""
    suite_kind: str = "development"
    backend: dict[str, Any] = Field(default_factory=dict)
    tool_diff: dict[str, Any] = Field(default_factory=dict)
    results: list[EvalExampleResult] = Field(default_factory=list)
    metrics: list[EvalMetricSummary] = Field(default_factory=list)
    aggregate: dict[str, float | None] = Field(default_factory=dict)
    denominators: EvalDenominators = Field(default_factory=EvalDenominators)
    subgroups: list[EvalSubgroupSummary] = Field(default_factory=list)
    thresholds: list[EvalThresholdEval] = Field(default_factory=list)
    safety_regression: EvalSafetyRegression = Field(default_factory=EvalSafetyRegression)
    verdict: Literal["improved", "flat", "regressed", "incomplete"] = "incomplete"
