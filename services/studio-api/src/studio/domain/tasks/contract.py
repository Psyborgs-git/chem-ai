"""Canonical success-contract payload schema (PAR-01).

One versioned vocabulary shared by draft validation, freeze gating,
GraphQL hydration, fixtures and the evaluator — the original pack's
``SuccessContract``/``Metric``/``HardConstraint`` defs
(``docs/chemistry-studio/contracts/domain.schema.json``).

* A *draft* is a working document: it is validated structurally but
  may preserve explicit unknown top-level fields; nothing missing is
  ever filled with a scientifically meaningful default.
* A *freeze* is the action that binds the contract for evaluation:
  it requires the payload to be fully canonical — every resolved
  metric carrying an identifier and a parseable bound, no declared
  ``unknowns``, no unknown top-level fields. Anything short stays a
  draft for review instead of silently freezing into a contract that
  looks assessable but is not.
* Pre-PAR-01 UI payloads written as ``requiredMetrics`` get an
  explicit *legacy read path*: they are translated into canonical
  metrics for evaluation (never rewritten in place), and any entry
  that cannot be translated produces a review issue rather than being
  dropped. A payload carrying both vocabularies resolves ``metrics``
  as authoritative.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from studio.domain.lab.units import metric_bound
from studio.errors import DomainError, ErrorCode

CONTRACT_SCHEMA_VERSION = "1.0.0"
SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0.0"})

# pre-PAR-01 studio-web emitted ``requiredMetrics`` instead of the
# canonical ``metrics`` — the legacy vocabulary that must keep
# evaluating (read path only; new writes are canonical).
LEGACY_REQUIRED_METRICS_KEY = "requiredMetrics"

# Revision-envelope fields owned by the SuccessContractRevision row
# itself. A payload must not carry them — a stored id/revision would
# be a conflicting identity claim, not contract content.
ROW_OWNED_FIELDS = frozenset(
    {
        "id",
        "task_id",
        "revision",
        "status",
        "content_hash",
        "created_at",
        "created_by",
        "updated_at",
    }
)

# Payload-side vocabulary of the pack SuccessContract (the envelope's
# row-owned fields excluded) plus the evaluator's own tolerated
# aliases (hardConstraints, requiredMetrics legacy).
KNOWN_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "mode",
        "target_kind",
        "objective",
        "baseline_revision_id",
        "reference_revision_id",
        "matching_scope",
        "metrics",
        "hard_constraints",
        "hardConstraints",
        # Persisted pre-PAR-01 vocabulary: 'constraints' is the seeded
        # gate list (evaluated as hard constraints), 'warnings' a
        # display annotation the task-memory surface renders — both
        # preserved verbatim, both known.
        "constraints",
        "warnings",
        "unknowns",
        "review_rules",
        "scope",
        "budget",
        "approval_id",
        "fixture_only",
        LEGACY_REQUIRED_METRICS_KEY,
    }
)

CONTRACT_MODES = frozenset({"improve", "match_reference", "discover"})
CONTRACT_TARGET_KINDS = frozenset({"formulation", "material", "molecule", "unknown"})
CONTRACT_MATCH_SCOPES = frozenset(
    {"functional", "analytical", "functional_and_analytical"}
)

# Metric vocabulary: canonical pack operators plus the symbol aliases
# the evaluator's ``metric_bound`` already maps (>=, <=, >, <, =).
# Anything else is rejected at write time instead of freezing into an
# operator the evaluator can only report as unparseable.
METRIC_OPERATORS = frozenset(
    {
        "gte",
        "gt",
        "lte",
        "lt",
        "eq",
        "between",
        "within_tolerance",
        "categorical_match",
        ">=",
        "<=",
        ">",
        "<",
        "=",
    }
)

METRIC_VALUE_KINDS = frozenset({"numeric", "ordinal", "categorical"})

EVIDENCE_CLASSES = frozenset(
    {
        "lab_measurement",
        "replication",
        "source_report",
        "physics_prediction",
        "learned_prediction",
    }
)

CONSTRAINT_KINDS = frozenset(
    {
        "composition",
        "ingredient_exclusion",
        "process_limit",
        "identity",
        "safety_review",
        "rights",
        "custom_registered",
    }
)

_UUID_FIELDS = frozenset(
    {
        "method_revision_id",
        "substrate_revision_id",
        "rule_revision_id",
        "baseline_revision_id",
        "reference_revision_id",
        "approval_id",
    }
)


class ContractConditions(BaseModel):
    """Canonical metric conditions (pack ``Metric.conditions``)."""

    model_config = ConfigDict(extra="forbid")
    substrate_revision_id: str | None = None
    description: str | None = None


class ContractMetric(BaseModel):
    """Canonical contract metric (pack ``Metric``).

    Every field is optional at the DTO level — a missing entry stays a
    missing entry. Nothing here invents a bound, a unit or an evidence
    class; completeness is enforced by the freeze gate, not by silent
    defaults. ``name``, ``target`` and the camelCase keys are the
    loose-but-persisted shapes already in the database and tolerated
    by the evaluator, so they are declared vocabulary rather than
    rejected extras.
    """

    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    name: str | None = None
    label: str | None = None
    required: bool | None = None
    value_kind: str | None = None
    operator: str | None = None
    target_values: list[str] | None = None
    targetValues: list[str] | None = None
    target: str | None = None
    unit: str | None = None
    method_revision_id: str | None = None
    conditions: ContractConditions | None = None
    required_evidence: list[str] | None = None
    requiredEvidence: list[str] | None = None
    aggregation: str | None = None
    replication_rule: str | dict[str, Any] | None = None
    replicationRule: str | dict[str, Any] | None = None


class ContractHardConstraint(BaseModel):
    """Canonical hard constraint (pack ``HardConstraint``) plus the
    evaluator's persisted ``text``/``check`` shape."""

    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    kind: str | None = None
    description: str | None = None
    rule_revision_id: str | None = None
    text: str | None = None
    check: dict[str, Any] | None = None


def _err(path: str, message: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION, message, field_path=path)


def _check_uuid(value: Any, path: str) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise _err(path, f"{path} must be a uuid string or null")
    try:
        uuid.UUID(value)
    except ValueError:
        raise _err(path, f"{path} is not a uuid: {value!r}") from None


def _validate_metric(raw: Any, path: str) -> None:
    if not isinstance(raw, dict):
        raise _err(path, f"{path} must be an object")
    try:
        metric = ContractMetric.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(part) for part in first["loc"])
        raise _err(
            f"{path}.{loc}" if loc else path,
            f"contract metric invalid ({loc or 'payload'}): {first['msg']}",
        ) from None
    for key in _UUID_FIELDS:
        _check_uuid(getattr(metric, key, None), f"{path}.{key}")
    if metric.operator is not None and metric.operator not in METRIC_OPERATORS:
        raise _err(
            f"{path}.operator",
            f"unknown metric operator {metric.operator!r}",
        )
    if metric.value_kind is not None and metric.value_kind not in METRIC_VALUE_KINDS:
        raise _err(
            f"{path}.value_kind",
            f"unknown metric value_kind {metric.value_kind!r}",
        )
    for key in ("required_evidence", "requiredEvidence"):
        evidence = getattr(metric, key)
        if evidence is None:
            continue
        bad = [e for e in evidence if e not in EVIDENCE_CLASSES]
        if bad:
            raise _err(
                f"{path}.{key}",
                f"unknown evidence class(es) {bad} — declared classes are "
                f"{sorted(EVIDENCE_CLASSES)}",
            )


def _validate_constraint(raw: Any, path: str) -> None:
    if isinstance(raw, str):
        return  # bare text constraints are persisted vocabulary
    if not isinstance(raw, dict):
        raise _err(path, f"{path} must be an object or a text string")
    try:
        constraint = ContractHardConstraint.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(part) for part in first["loc"])
        raise _err(
            f"{path}.{loc}" if loc else path,
            f"hard constraint invalid ({loc or 'payload'}): {first['msg']}",
        ) from None
    _check_uuid(constraint.rule_revision_id, f"{path}.rule_revision_id")
    if constraint.kind is not None and constraint.kind not in CONSTRAINT_KINDS:
        raise _err(
            f"{path}.kind",
            f"unknown constraint kind {constraint.kind!r}",
        )


def validate_draft_payload(payload: Any) -> None:
    """Structural validation for a contract *draft* (§11.1).

    Rejects malformed known vocabulary and revision-identity keys.
    Unknown top-level fields are preserved on the draft — they are
    explicit unknowns for review, not silently evaluable content.
    Raises ``DomainError`` with a client-safe field path.
    """
    path = "input.payload"
    if not isinstance(payload, dict):
        raise _err(path, "contract payload must be an object")
    owned = sorted(k for k in payload if k in ROW_OWNED_FIELDS)
    if owned:
        raise _err(
            f"{path}.{owned[0]}",
            "payload must not carry revision identity fields "
            f"({', '.join(owned)}) — the service assigns them",
        )
    version = payload.get("schema_version")
    if version is not None and (
        not isinstance(version, str) or version not in SUPPORTED_SCHEMA_VERSIONS
    ):
        raise _err(
            f"{path}.schema_version",
            f"unsupported contract schema_version {version!r}; "
            f"this service writes {sorted(SUPPORTED_SCHEMA_VERSIONS)}",
        )

    mode = payload.get("mode")
    if mode is not None and (not isinstance(mode, str) or mode not in CONTRACT_MODES):
        raise _err(f"{path}.mode", f"unknown contract mode {mode!r}")
    target_kind = payload.get("target_kind")
    if target_kind is not None and (
        not isinstance(target_kind, str) or target_kind not in CONTRACT_TARGET_KINDS
    ):
        raise _err(
            f"{path}.target_kind", f"unknown contract target_kind {target_kind!r}"
        )
    scope = payload.get("matching_scope")
    if scope is not None and (
        not isinstance(scope, str) or scope not in CONTRACT_MATCH_SCOPES
    ):
        raise _err(
            f"{path}.matching_scope",
            f"unknown contract matching_scope {scope!r}",
        )
    for key in ("baseline_revision_id", "reference_revision_id", "approval_id"):
        _check_uuid(payload.get(key), f"{path}.{key}")
    if "objective" in payload and payload["objective"] is not None and not isinstance(
        payload["objective"], str
    ):
        raise _err(f"{path}.objective", "objective must be a string")
    if "fixture_only" in payload and not isinstance(payload["fixture_only"], bool):
        raise _err(f"{path}.fixture_only", "fixture_only must be a boolean")

    metrics = payload.get("metrics")
    if metrics is not None:
        if not isinstance(metrics, list):
            raise _err(f"{path}.metrics", "metrics must be a list")
        for i, raw in enumerate(metrics):
            _validate_metric(raw, f"{path}.metrics[{i}]")

    legacy = payload.get(LEGACY_REQUIRED_METRICS_KEY)
    if legacy is not None and not isinstance(legacy, list):
        raise _err(
            f"{path}.{LEGACY_REQUIRED_METRICS_KEY}",
            "legacy requiredMetrics must be a list",
        )

    for key in ("hard_constraints", "hardConstraints", "constraints"):
        gates = payload.get(key)
        if gates is None:
            continue
        if not isinstance(gates, list):
            raise _err(f"{path}.{key}", f"{key} must be a list")
        for i, raw in enumerate(gates):
            _validate_constraint(raw, f"{path}.{key}[{i}]")

    warnings = payload.get("warnings")
    if warnings is not None and (
        not isinstance(warnings, list)
        or any(not isinstance(w, str) for w in warnings)
    ):
        raise _err(f"{path}.warnings", "warnings must be a list of strings")

    unknowns = payload.get("unknowns")
    if unknowns is not None and (
        not isinstance(unknowns, list)
        or any(not isinstance(u, str) for u in unknowns)
    ):
        raise _err(f"{path}.unknowns", "unknowns must be a list of strings")


def validate_freeze_payload(payload: Any) -> None:
    """The gate freeze actually needs (§11.1, pack SuccessContract
    frozen rules): a fully canonical payload — every resolved metric
    identified and bound, no declared unknowns, no unknown top-level
    fields. Unknown content stays a draft for review instead of
    freezing into a contract that only looks assessable."""
    validate_draft_payload(payload)
    path = "input.payload"
    unknown_fields = sorted(
        k for k in payload if k not in KNOWN_TOP_LEVEL_FIELDS
    )
    if unknown_fields:
        raise _err(
            f"{path}.{unknown_fields[0]}",
            "unknown contract field(s) cannot be frozen silently "
            f"({', '.join(unknown_fields)}) — review them or save a "
            "successor draft",
        )
    declared_unknowns = payload.get("unknowns") or []
    if declared_unknowns:
        raise _err(
            f"{path}.unknowns",
            "a contract with declared unknowns cannot be frozen — "
            f"resolve: {', '.join(declared_unknowns)}",
        )
    resolved = resolve_metrics(payload)
    if not resolved.metrics:
        raise _err(
            f"{path}.metrics",
            "a contract without evaluable metrics cannot be frozen",
        )
    for i, metric in enumerate(resolved.metrics):
        ident = metric.get("id") or metric.get("name") or metric.get("label")
        if not ident:
            raise _err(
                f"{path}.metrics[{i}]",
                "a frozen metric needs an id, name or label",
            )
        try:
            bound = metric_bound(metric)
        except DomainError as exc:
            raise _err(
                f"{path}.metrics[{i}]",
                f"metric {ident!r} bound is not parseable: {exc.message}",
            ) from None
        if bound is None:
            raise _err(
                f"{path}.metrics[{i}]",
                f"metric {ident!r} carries no bound — a contract clause "
                "must state operator and target (missing stays missing; "
                "it is never defaulted)",
            )


@dataclass
class ResolvedContract:
    """The evaluator-facing view of a stored contract payload."""

    metrics: list[dict[str, Any]] = field(default_factory=list)
    gates: list[Any] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    legacy: bool = False


def _translate_legacy_metric(entry: Any) -> tuple[dict[str, Any] | None, str | None]:
    """One pre-PAR-01 ``requiredMetrics`` entry → canonical metric.

    ``{"name": str, "operator": ">="|"<="|"target", "target":
    {"value": str, "unit": str}}`` maps to the canonical
    ``id/label/operator/target_values/unit`` shape. Anything that does
    not translate cleanly stays a boundless metric shell plus a review
    issue — reported as inconclusive, never silently dropped and never
    re-interpreted into a scientific default.
    """
    if not isinstance(entry, dict):
        return None, "entry is not an object — needs review or a successor revision"
    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        return None, "entry carries no metric name — cannot translate"
    metric: dict[str, Any] = {
        "id": name.strip(),
        "label": name.strip(),
        "required": bool(entry.get("required", True)),
        "legacy": True,
    }
    raw_op = entry.get("operator")
    target = entry.get("target")
    value: str | None = None
    unit: str | None = None
    if isinstance(target, dict):
        raw_value = target.get("value")
        if raw_value is not None:
            value = str(raw_value)
        raw_unit = target.get("unit")
        if raw_unit is not None:
            unit = str(raw_unit)
    if raw_op == ">=":
        metric["operator"] = "gte"
    elif raw_op == "<=":
        metric["operator"] = "lte"
    elif raw_op is not None:
        return (
            metric,
            f"legacy operator {raw_op!r} has no canonical equivalent — "
            "metric kept without a bound for human review",
        )
    if value is None:
        return (
            metric,
            "legacy entry records no target value — metric kept without "
            "a bound for human review",
        )
    metric["target_values"] = [value]
    metric["unit"] = unit
    return metric, None


def resolve_metrics(payload: dict[str, Any] | None) -> ResolvedContract:
    """Resolve the stored payload to canonical metrics + gates.

    ``metrics`` is authoritative when present; ``requiredMetrics`` is
    the explicit legacy fallback. Translation issues are surfaced for
    review — a missing or ambiguous metric never becomes a scientific
    default and never disappears silently.
    """
    resolved = ResolvedContract()
    if not isinstance(payload, dict):
        resolved.issues.append("contract payload is not an object")
        return resolved
    # Gate resolution mirrors the metric one: canonical
    # 'hard_constraints' (or its camelCase alias) wins; a persisted
    # 'constraints' list is the same clause vocabulary under an older
    # key and evaluates as-is — a constraint that cannot evaluate is
    # reported not_evaluated, not dropped.
    gates = payload.get("hard_constraints")
    dual = False
    if gates is None:
        gates = payload.get("hardConstraints")
    if gates is None:
        gates = payload.get("constraints")
    else:
        dual = payload.get("constraints") is not None
    if isinstance(gates, list):
        resolved.gates = gates
        if dual:
            resolved.issues.append(
                "payload carries both canonical 'hard_constraints' and "
                "legacy 'constraints' — canonical gates evaluated; the "
                "legacy entries need a successor revision or removal"
            )
    elif gates is not None:
        resolved.issues.append("contract hard constraints are not a list")

    if "metrics" in payload:
        raw = payload["metrics"]
        if not isinstance(raw, list):
            resolved.issues.append("contract 'metrics' is not a list")
            return resolved
        resolved.metrics = [m for m in raw if isinstance(m, dict)]
        for i, m in enumerate(raw):
            if not isinstance(m, dict):
                resolved.issues.append(
                    f"metrics[{i}] is not an object — entry ignored for "
                    "evaluation and needs review"
                )
        if LEGACY_REQUIRED_METRICS_KEY in payload:
            resolved.issues.append(
                "payload carries both 'metrics' and legacy "
                "'requiredMetrics' — canonical 'metrics' evaluated; the "
                "legacy entries need a successor revision or removal"
            )
        return resolved

    legacy = payload.get(LEGACY_REQUIRED_METRICS_KEY)
    if legacy is None:
        return resolved
    resolved.legacy = True
    if not isinstance(legacy, list):
        resolved.issues.append(
            "legacy 'requiredMetrics' is not a list — payload needs "
            "review or a successor revision"
        )
        return resolved
    for i, entry in enumerate(legacy):
        metric, issue = _translate_legacy_metric(entry)
        if issue is not None:
            resolved.issues.append(f"requiredMetrics[{i}]: {issue}")
        if metric is not None:
            resolved.metrics.append(metric)
    return resolved
