"""Record-derived evidence provenance (PAR-05).

Evidence origin is a per-record attribute derived from the fields the
domain already stores — declared markers, naming conventions, import
provenance and review state — never a packet-level constant. Three
axes stay independent everywhere:

1. **evidence origin** — where the record came from:
   ``synthetic_fixture`` | ``historical_report`` |
   ``lab_observation`` | ``prediction`` | ``unknown``;
2. **engine applicability** — the existing ``applicable``/binding axis,
   unchanged by provenance;
3. **scientific validation** — method validation + independent
   validation. Neither exists today, so the axis always reports
   ``missing``/``not_validated`` (U14 unresolved). A real upload
   upgrades only the first axis.

Derivation order for a measurement — nearest payload to widest:

- a *declared* marker wins (``provenance.origin``,
  ``evidenceOrigin``/``evidence_origin``/``originClass`` keys, or the
  boolean ``fixture``/``synthetic``/``fixture_only`` flags already
  validated on contract payloads); a declared value outside the
  vocabulary resolves to ``unknown`` — never guessed;
- naming markers on ``method``/``metric``/``pipeline_version``
  (``fixture-*``/``*-synthetic-*`` → synthetic; ``prediction-*``/
  ``model:*``-style → prediction) cover every seeded demonstration;
- ``LabExecution.historical`` → ``historical_report`` (imported runs
  carry no preapproval);
- otherwise a recorded lab observation. Old rows missing a field the
  derivation needs report ``unknown`` — they are never mutated.

Synthetic/fixture-marked records can still exist in a corpus — they
are *labeled*, never silent — but a record whose origin cannot be
established (``unknown``) is excluded from corpora at build time and
re-checked live at the run gates; the same plane that already blocks
unresolved training rights (AT-0601-2/AT-0801-2).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from studio.persistence.models import (
    EvidenceClaim,
    ExperimentPlan,
    ExtractedRecord,
    ImportBatch,
    LabBatch,
    LabExecution,
    LabSample,
    Measurement,
    ResearchSession,
)

ORIGIN_SYNTHETIC_FIXTURE = "synthetic_fixture"
ORIGIN_HISTORICAL_REPORT = "historical_report"
ORIGIN_LAB_OBSERVATION = "lab_observation"
ORIGIN_PREDICTION = "prediction"
ORIGIN_UNKNOWN = "unknown"

EVIDENCE_ORIGINS = (
    ORIGIN_SYNTHETIC_FIXTURE,
    ORIGIN_HISTORICAL_REPORT,
    ORIGIN_LAB_OBSERVATION,
    ORIGIN_PREDICTION,
    ORIGIN_UNKNOWN,
)

# Origins that count as real evidence records (not synthetic
# fixtures). A prediction is a real record of generated output — real
# provenance, but never a measured laboratory value.
REAL_ORIGINS = frozenset(
    {ORIGIN_HISTORICAL_REPORT, ORIGIN_LAB_OBSERVATION, ORIGIN_PREDICTION}
)
# Origins that can ground a *scientific* training label / acceptance
# decision — recorded laboratory evidence only. Predictions are model
# output, not measured ground truth.
REAL_EVIDENCE_ORIGINS = frozenset(
    {ORIGIN_HISTORICAL_REPORT, ORIGIN_LAB_OBSERVATION}
)

_COMPOSITIONS = ("none", "synthetic_only", "real_only", "mixed", "unknown_only")

_ORIGIN_ALIASES = {
    "fixture": ORIGIN_SYNTHETIC_FIXTURE,
    "synthetic": ORIGIN_SYNTHETIC_FIXTURE,
    "synthetic_fixture": ORIGIN_SYNTHETIC_FIXTURE,
    "synthetic-fixture": ORIGIN_SYNTHETIC_FIXTURE,
    "demo": ORIGIN_SYNTHETIC_FIXTURE,
    "demonstration": ORIGIN_SYNTHETIC_FIXTURE,
    "historical": ORIGIN_HISTORICAL_REPORT,
    "historical_report": ORIGIN_HISTORICAL_REPORT,
    "historical-report": ORIGIN_HISTORICAL_REPORT,
    "imported": ORIGIN_HISTORICAL_REPORT,
    "import": ORIGIN_HISTORICAL_REPORT,
    "report": ORIGIN_HISTORICAL_REPORT,
    "source_report": ORIGIN_HISTORICAL_REPORT,
    "lab": ORIGIN_LAB_OBSERVATION,
    "lab_observation": ORIGIN_LAB_OBSERVATION,
    "lab-observation": ORIGIN_LAB_OBSERVATION,
    "observation": ORIGIN_LAB_OBSERVATION,
    "measured": ORIGIN_LAB_OBSERVATION,
    "manual": ORIGIN_LAB_OBSERVATION,
    "recorded": ORIGIN_LAB_OBSERVATION,
    "replication": ORIGIN_LAB_OBSERVATION,
    "prediction": ORIGIN_PREDICTION,
    "predicted": ORIGIN_PREDICTION,
    "model": ORIGIN_PREDICTION,
    "model_output": ORIGIN_PREDICTION,
    "physics_prediction": ORIGIN_PREDICTION,
    "learned_prediction": ORIGIN_PREDICTION,
    "unknown": ORIGIN_UNKNOWN,
}

# Declared-marker keys — a record or a record-chain payload may carry
# an explicit provenance declaration. Nested ``provenance`` dicts are
# checked for ``origin``/``kind``/``source``/``class``; top-level keys
# must be unambiguous (``evidenceOrigin``-style) so a payload field
# like ``origin: "warehouse A"`` (physical provenance) is never
# misread as an evidence class.
_DECLARED_NESTED_KEYS = ("origin", "kind", "source", "class", "sourceClass")
_DECLARED_TOP_KEYS = (
    "evidenceOrigin",
    "evidence_origin",
    "originClass",
    "origin_class",
    "evidenceOriginClass",
)
_DECLARED_BOOL_KEYS = ("fixture", "synthetic", "fixture_only", "fixtureOnly")

_FIXTURE_NAME = re.compile(r"fixture|synthetic", re.IGNORECASE)
_PREDICTION_NAME = re.compile(
    r"(?:^|[_\-:.])(prediction|predicted|model|sim|simulation)(?:[_\-:.]|$)",
    re.IGNORECASE,
)

_CLAIM_KIND_ORIGINS = {
    "document_claim": ORIGIN_HISTORICAL_REPORT,
    "inferred_suggestion": ORIGIN_PREDICTION,
    "measured_outcome": ORIGIN_LAB_OBSERVATION,
}


def _normalize(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "_")


def _declared_marker(payloads: Iterable[Any]) -> str | None:
    """An explicit declared origin anywhere in the payload chain wins —
    nearest payload first. A declared value outside the vocabulary
    reports ``unknown``: declared-but-unreadable is honest, guessing is
    not."""
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        prov = payload.get("provenance")
        if isinstance(prov, dict):
            for key in _DECLARED_NESTED_KEYS:
                raw = prov.get(key)
                if isinstance(raw, str) and raw.strip():
                    return _ORIGIN_ALIASES.get(_normalize(raw), ORIGIN_UNKNOWN)
        for key in _DECLARED_TOP_KEYS:
            raw = payload.get(key)
            if isinstance(raw, str) and raw.strip():
                return _ORIGIN_ALIASES.get(_normalize(raw), ORIGIN_UNKNOWN)
        if any(payload.get(k) is True for k in _DECLARED_BOOL_KEYS):
            return ORIGIN_SYNTHETIC_FIXTURE
    return None


def _name_marker(*texts: Any) -> str | None:
    for text in texts:
        if not isinstance(text, str) or not text:
            continue
        if _FIXTURE_NAME.search(text):
            return ORIGIN_SYNTHETIC_FIXTURE
        if _PREDICTION_NAME.search(text):
            return ORIGIN_PREDICTION
    return None


def measurement_origin(
    measurement: Measurement,
    *,
    sample: LabSample | None = None,
    batch: LabBatch | None = None,
    execution: LabExecution | None = None,
    plan: ExperimentPlan | None = None,
) -> dict[str, Any]:
    """Derive a measurement's evidence origin from its stored chain.

    Returns ``{"origin": ..., "via": ...}`` — ``via`` names the signal
    that decided so the packet can say *why* a record is synthetic
    (``declared`` / ``name_marker`` / ``historical_flag`` /
    ``plan_recorded`` / ``kind`` / ``unclassifiable``).
    """
    payloads = [
        measurement.conditions,
        sample.payload if sample is not None else None,
        batch.payload if batch is not None else None,
        execution.actual if execution is not None else None,
        plan.payload if plan is not None else None,
    ]
    declared = _declared_marker(payloads)
    if declared is not None:
        return {"origin": declared, "via": "declared"}
    named = _name_marker(
        measurement.method, measurement.metric, measurement.pipeline_version
    )
    if named is not None:
        return {"origin": named, "via": "name_marker"}
    if execution is None:
        # The chain join guarantees an execution for real rows; a missing
        # one means the provenance basis is unreadable.
        return {"origin": ORIGIN_UNKNOWN, "via": "unclassifiable"}
    if execution.historical:
        return {"origin": ORIGIN_HISTORICAL_REPORT, "via": "historical_flag"}
    return {"origin": ORIGIN_LAB_OBSERVATION, "via": "plan_recorded"}


def claim_origin(
    claim: EvidenceClaim, *, source_resolvable: bool | None
) -> dict[str, Any]:
    """Claims map their kind to an origin class; a document claim whose
    source record/batch can't be resolved reports ``unknown`` — a claim
    without document provenance is unverifiable, not historical."""
    declared = _declared_marker(
        [claim.conditions, claim.subject, claim.statement]
    )
    if declared is not None:
        return {"origin": declared, "via": "declared"}
    named = _name_marker(*(v for v in (claim.subject or {}).values()))
    if named is not None:
        return {"origin": named, "via": "name_marker"}
    origin = _CLAIM_KIND_ORIGINS.get(claim.kind, ORIGIN_UNKNOWN)
    if origin == ORIGIN_HISTORICAL_REPORT and source_resolvable is False:
        return {"origin": ORIGIN_UNKNOWN, "via": "unclassifiable"}
    return {"origin": origin, "via": "kind"}


def session_origin(_session: ResearchSession) -> dict[str, Any]:
    """A research session is generated model/assistant content — real
    provenance of class ``prediction``; it is never a measurement."""
    return {"origin": ORIGIN_PREDICTION, "via": "kind"}


def measurement_chain(
    db: Session, workspace_id: uuid.UUID, measurement: Measurement
) -> tuple[LabSample | None, LabBatch | None, LabExecution | None, ExperimentPlan | None]:
    """Load the sample→batch→execution→plan chain for a measurement —
    the shared lookup for call sites that only hold the row."""
    sample = db.get(LabSample, measurement.sample_id)
    if sample is None or sample.workspace_id != workspace_id:
        return None, None, None, None
    batch = db.get(LabBatch, sample.batch_id)
    if batch is None or batch.workspace_id != workspace_id:
        return sample, None, None, None
    execution = db.get(LabExecution, batch.execution_id)
    if execution is None or execution.workspace_id != workspace_id:
        return sample, batch, None, None
    plan = db.get(ExperimentPlan, execution.plan_id) if execution.plan_id else None
    return sample, batch, execution, plan


def claim_source_resolvable(db: Session, claim: EvidenceClaim) -> bool:
    """Whether a document claim's import chain (record → batch, or at
    least the batch the claim names) can be resolved to a stored row."""
    if claim.source_record_id:
        rec = db.get(ExtractedRecord, claim.source_record_id)
        if rec is not None and db.get(ImportBatch, rec.batch_id) is not None:
            return True
    if claim.source_batch_id:
        return db.get(ImportBatch, claim.source_batch_id) is not None
    return False


def summarize(origins: Iterable[str]) -> dict[str, Any]:
    """Composition over a set of per-record origins."""
    counts: dict[str, int] = {}
    for origin in origins:
        key = origin if origin in EVIDENCE_ORIGINS else ORIGIN_UNKNOWN
        counts[key] = counts.get(key, 0) + 1
    classes = set(counts)
    if not counts:
        composition = "none"
    elif classes == {ORIGIN_SYNTHETIC_FIXTURE}:
        composition = "synthetic_only"
    elif classes == {ORIGIN_UNKNOWN}:
        composition = "unknown_only"
    elif classes <= REAL_ORIGINS:
        composition = "real_only"
    else:
        composition = "mixed"
    return {
        "composition": composition,
        "counts": counts,
        "classesPresent": sorted(classes),
    }


def fixture_only(composition: str) -> bool:
    """The derived ``fixtureOnly`` flag: true only when no real-origin
    evidence exists at all (all-synthetic or empty). ``mixed``,
    ``real_only`` and ``unknown_only`` are all *not* fixture-only —
    honest decomposition, not a green upgrade."""
    return composition in ("synthetic_only", "none")


def corpus_data_status(composition: str | None) -> str:
    """The capability-label ``dataStatus`` for a corpus composition.
    ``None`` (a snapshot whose manifest predates provenance labels)
    reports the conservative fixture-only label — never an upgrade."""
    if composition is None or composition in ("synthetic_only", "none"):
        return "fixture_only"
    if composition == "real_only":
        return "real_unvalidated"
    return "mixed"  # mixed or unknown_only — real and/or unresolved share it


def provenance_block(records: list[dict[str, Any]]) -> dict[str, Any]:
    """The honest three-axis block carried by evaluation reports and
    closeout packets. ``records`` entries: {id, origin, reviewState,
    engineApplicable}. Provenance is real for real-origin evidence but
    scientific validation never upgrades — method validation and
    independent validation are absent (U14)."""
    origins = [str(r.get("origin") or ORIGIN_UNKNOWN) for r in records]
    summary = summarize(origins)
    composition = summary["composition"]
    missing: list[str] = []
    if composition == "real_only":
        origin_status = "real"
        origin_missing = "none — provenance is real; that does not imply validation"
    elif composition == "synthetic_only":
        origin_status = "fixture_synthetic"
        origin_missing = "real-origin evidence (all records are synthetic fixtures)"
    elif composition == "none":
        origin_status = "none"
        origin_missing = "evidence (no records bound)"
    elif composition == "unknown_only":
        origin_status = "unknown"
        origin_missing = "resolvable evidence origin (all records unclassifiable)"
    else:
        origin_status = "mixed"
        origin_missing = (
            "evidence classes are mixed — fixture/unknown records do not become "
            "real by association"
        )
    missing.append(origin_missing)
    missing.append("reviewed method validation record")
    missing.append("independent scientific validation (U14)")
    return {
        "evidenceOrigin": {
            "composition": composition,
            "counts": summary["counts"],
            "classesPresent": summary["classesPresent"],
            "records": records,
        },
        "methodValidation": {
            "status": "missing",
            "detail": "no validated method binding is recorded for this evidence",
        },
        "independentValidation": {
            "status": "not_validated",
            "detail": "independent scientific validation does not exist (U14 unresolved)",
        },
        "readiness": [
            {"axis": "evidence_origin", "status": origin_status},
            {"axis": "engine_applicability", "status": "per_record"},
            {"axis": "method_validation", "status": "missing"},
            {"axis": "independent_validation", "status": "not_validated"},
        ],
        "missingScientificInputs": missing,
    }
