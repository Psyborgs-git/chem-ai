"""Local-infeasibility and fallback decision reports (§20.1-§20.2).

This module is the *decision* surface for protected cloud fallback —
it produces evidence, never bytes on a wire:

1. ``parse_job_spec`` bounds the caller-declared job spec (operation,
   sizes, envelope, bounded estimates, supported local alternatives)
   carried in ``run.request``.
2. ``evaluate_spec`` checks every compatible local configuration
   against observed group capacity minus reserve — a conservative
   compatibility check / bounded estimate, never a full-scale probe
   run to prove OOM. Unobservable capacity is *missing*, never assumed
   sufficient; a currently-busy group is ``busy``, never "impossible"
   — slower is not infeasible (AT-1001-1).
3. ``FeasibilityService.request_fallback`` records the evidence report
   and — only when no approved compatible configuration fits — creates
   an *export review proposal* row. A proposal has zero transfer or
   spending side effects: no payload, recipient, provider call, or
   budget reservation exists in this path (AT-1001-2/3, §20.2). Cloud
   is reported ``not_configured`` because this deployment carries no
   provider, account, or budget settings at all.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from chem_studio_policy.capabilities import CAP_APPROVE_EXPORT, CAP_REQUEST_COMPUTE
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.application.approvals import bound_digest
from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext
from studio.domain.runs.admission import ENVELOPE_FIELDS, AdmissionService, validate_envelope
from studio.domain.runs.queue import RunService
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import (
    Approval,
    ExportProposal,
    Run,
    RunFeasibilityReport,
)

# ------------------------------------------------------------------
# spec contract (bounded metadata inside run.request, §7.4)

ESTIMATE_DIMS = (*ENVELOPE_FIELDS, "wall_seconds")
MAX_SIZES = 16
MAX_ALTERNATIVES = 8
MAX_LABEL = 80
MAX_NOTE = 240
MAX_INT = 2**63 - 1

ALTERNATIVE_KINDS = ("batch_reduction", "accumulation", "precision", "offload", "other")
QUALITY_IMPACTS = ("none", "minor", "material_needs_approval")
ESTIMATE_BASES = ("declared", "estimated", "measured", "bounded_probe", "compatibility_check")

VERDICT_FEASIBLE = "feasible"
VERDICT_INFEASIBLE = "infeasible"

DECISION_LOCAL_FEASIBLE = "local_feasible"
DECISION_EXPORT_PROPOSED = "export_review_proposed"

PROPOSAL_STATUSES = ("proposed", "approved", "rejected", "withdrawn")

REPORT_VERSION = "feasibility-report/v1"


def _fail(message: str, path: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION, message, field_path=path)


def _bounded_int(raw: Any, path: str) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0 or raw > MAX_INT:
        raise _fail(f"{path} must be a non-negative integer", path)
    return raw


def _short_text(raw: Any, path: str, *, limit: int) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or len(raw) > limit:
        raise _fail(f"{path} must be a string of at most {limit} characters", path)
    return raw


@dataclass(frozen=True)
class Bound:
    """A declared estimate range; ``low == high`` is an exact figure."""

    low: int
    high: int

    def to_dict(self) -> dict[str, int]:
        return {"low": self.low, "high": self.high}


@dataclass(frozen=True)
class Candidate:
    """One evaluated local configuration: the approved (declared)
    envelope first, then each supported local alternative."""

    name: str
    kind: str
    quality_impact: str
    compatible: bool
    envelope: dict[str, int]
    estimates: dict[str, Bound]
    uncertainty: dict[str, str]
    basis: str
    note: str | None

    @property
    def requires_quality_approval(self) -> bool:
        return self.quality_impact == "material_needs_approval"


@dataclass(frozen=True)
class JobSpec:
    operation: str
    sizes: dict[str, int]
    uncertainty: dict[str, str]
    basis_note: str | None
    candidates: tuple[Candidate, ...]


@dataclass(frozen=True)
class GroupState:
    """Observed schedulable state of one resource group."""

    name: str
    capacity: dict[str, Any]
    reserve: dict[str, Any]
    reserved: dict[str, Any]


@dataclass
class ConfigVerdict:
    """Evidence for one configuration across every resource group."""

    name: str
    kind: str
    quality_impact: str
    compatible: bool
    requires_quality_approval: bool
    basis: str
    note: str | None
    estimates: dict[str, dict[str, int]]
    uncertainty: dict[str, str]
    groups: dict[str, dict[str, Any]]
    verdict: str  # fits | busy | infeasible | excluded
    detail: str
    fits_group: str | None = None
    busy_groups: list[str] = field(default_factory=list)


@dataclass
class Evaluation:
    verdict: str
    reasons: list[dict[str, Any]]
    missing: list[str]
    configurations: list[ConfigVerdict]


def _parse_bound(raw: Any, path: str) -> Bound:
    if isinstance(raw, int) and not isinstance(raw, bool):
        return Bound(low=_bounded_int(raw, path), high=_bounded_int(raw, path))
    if isinstance(raw, dict):
        low = _bounded_int(raw.get("low"), f"{path}.low")
        high = _bounded_int(raw.get("high"), f"{path}.high")
        if high < low:
            raise _fail(f"{path}.high must be >= {path}.low", path)
        return Bound(low=low, high=high)
    raise _fail(f"{path} must be an integer or {{low, high}}", path)


def _parse_estimates(raw: Any, path: str) -> dict[str, Bound]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise _fail(f"{path} must be an object", path)
    out: dict[str, Bound] = {}
    for key, value in raw.items():
        if key not in ESTIMATE_DIMS:
            raise _fail(f"{path}.{key} is not an estimable dimension", f"{path}.{key}")
        out[key] = _parse_bound(value, f"{path}.{key}")
    return out


def _parse_uncertainty(raw: Any, path: str) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise _fail(f"{path} must be an object", path)
    out: dict[str, str] = {}
    for key, value in raw.items():
        if key not in ESTIMATE_DIMS:
            raise _fail(f"{path}.{key} is not an estimable dimension", f"{path}.{key}")
        if not isinstance(value, str) or value not in ESTIMATE_BASES:
            raise _fail(
                f"{path}.{key} must be one of {sorted(ESTIMATE_BASES)}",
                f"{path}.{key}",
            )
        out[key] = value
    return out


def _resolve_estimates(
    envelope: dict[str, int],
    declared: dict[str, Bound],
    base: dict[str, Bound],
    scale: float,
) -> dict[str, Bound]:
    """Final per-dimension bounds for one configuration.

    Precedence: the configuration's own declared estimate, else the
    job-level estimate scaled by the configuration's ``scale``, else
    the configuration's declared envelope value (an exact claim).
    """
    out: dict[str, Bound] = {}
    for dim in ESTIMATE_DIMS:
        if dim in declared:
            out[dim] = declared[dim]
        elif dim in base:
            out[dim] = Bound(
                low=math.ceil(base[dim].low * scale),
                high=math.ceil(base[dim].high * scale),
            )
        else:
            want = envelope.get(dim, 0)
            out[dim] = Bound(low=want, high=want)
    return out


def _basis_for(estimates: dict[str, Bound]) -> str:
    """Label the evidence honestly: a bare envelope comparison is a
    compatibility check; ranged estimates are bounded estimates."""
    return "compatibility_check"


def parse_job_spec(request: dict[str, Any], *, default_operation: str) -> JobSpec:
    """Validate the bounded feasibility spec inside ``run.request``.

    The request never carries payloads (§7.4): this reads only small
    declared integers and labels. Unknown keys are ignored — the report
    records exactly what was evaluated.
    """
    operation = _short_text(request.get("operation"), "request.operation", limit=MAX_LABEL)
    sizes_raw = request.get("sizes") or {}
    if not isinstance(sizes_raw, dict) or len(sizes_raw) > MAX_SIZES:
        raise _fail("request.sizes must be an object of bounded size", "request.sizes")
    sizes = {str(k): _bounded_int(v, f"request.sizes.{k}") for k, v in sizes_raw.items()}
    uncertainty = _parse_uncertainty(request.get("uncertainty"), "request.uncertainty")
    basis_note = _short_text(request.get("basisNote"), "request.basisNote", limit=MAX_NOTE)

    base_estimates = _parse_estimates(request.get("estimates"), "request.estimates")
    approved_env = validate_envelope(request.get("envelope") or {})
    candidates: list[Candidate] = [
        Candidate(
            name="approved",
            kind="approved",
            quality_impact="none",
            compatible=True,
            envelope=approved_env,
            estimates=_resolve_estimates(approved_env, {}, base_estimates, 1.0),
            uncertainty=uncertainty,
            basis="bounded_estimate" if base_estimates else "compatibility_check",
            note=None,
        )
    ]

    alternatives_raw = request.get("alternatives") or []
    if not isinstance(alternatives_raw, list) or len(alternatives_raw) > MAX_ALTERNATIVES:
        raise _fail(
            f"request.alternatives must be a list of at most {MAX_ALTERNATIVES}",
            "request.alternatives",
        )
    for index, raw in enumerate(alternatives_raw):
        path = f"request.alternatives[{index}]"
        if not isinstance(raw, dict):
            raise _fail(f"{path} must be an object", path)
        name = _short_text(raw.get("name"), f"{path}.name", limit=MAX_LABEL)
        if not name:
            raise _fail(f"{path}.name is required", f"{path}.name")
        kind = raw.get("kind", "other")
        if kind not in ALTERNATIVE_KINDS:
            raise _fail(f"{path}.kind must be one of {sorted(ALTERNATIVE_KINDS)}", f"{path}.kind")
        quality = raw.get("qualityImpact", "none")
        if quality not in QUALITY_IMPACTS:
            raise _fail(
                f"{path}.qualityImpact must be one of {sorted(QUALITY_IMPACTS)}",
                f"{path}.qualityImpact",
            )
        compatible = raw.get("compatible", True)
        if not isinstance(compatible, bool):
            raise _fail(f"{path}.compatible must be a boolean", f"{path}.compatible")
        scale = raw.get("scale", 1.0)
        if not isinstance(scale, (int, float)) or isinstance(scale, bool) or not 0 < scale <= 1:
            raise _fail(f"{path}.scale must be in (0, 1]", f"{path}.scale")
        env = validate_envelope(raw.get("envelope") or {})
        declared = _parse_estimates(raw.get("estimates"), f"{path}.estimates")
        merged_uncertainty = dict(uncertainty)
        merged_uncertainty.update(_parse_uncertainty(raw.get("uncertainty"), f"{path}.uncertainty"))
        candidates.append(
            Candidate(
                name=name,
                kind=kind,
                quality_impact=quality,
                compatible=compatible,
                envelope=env,
                estimates=_resolve_estimates(env, declared, base_estimates, float(scale)),
                uncertainty=merged_uncertainty,
                basis="bounded_estimate" if (declared or base_estimates) else "compatibility_check",
                note=_short_text(raw.get("note"), f"{path}.note", limit=MAX_NOTE),
            )
        )
    return JobSpec(
        operation=operation or default_operation,
        sizes=sizes,
        uncertainty=uncertainty,
        basis_note=basis_note,
        candidates=tuple(candidates),
    )


def _check_group(candidate: Candidate, group: GroupState) -> dict[str, Any]:
    """One configuration against one group's observed capacity.

    ``failures`` = exceeds capacity minus reserve even when idle;
    ``busy`` = fits static capacity but current reservations leave too
    little headroom right now (transient, *not* infeasible);
    ``missing`` = a wanted dimension the group does not observe —
    unobservable is never assumed sufficient.
    """
    failures: list[dict[str, Any]] = []
    busy: list[dict[str, Any]] = []
    missing: list[str] = []
    for dim in ENVELOPE_FIELDS:
        want = candidate.estimates[dim].high  # conservative upper bound
        if want == 0:
            continue
        total = group.capacity.get(dim)
        if total is None:
            missing.append(dim)
            continue
        budget = int(total) - int(group.reserve.get(dim, 0))
        used = int(group.reserved.get(dim, 0))
        if want > budget:
            failures.append(
                {
                    "dimension": dim,
                    "required": want,
                    "capacity": int(total),
                    "reserve": int(group.reserve.get(dim, 0)),
                    "availableWhenIdle": budget,
                }
            )
        elif want > budget - used:
            busy.append(
                {
                    "dimension": dim,
                    "required": want,
                    "availableNow": max(budget - used, 0),
                    "reserved": used,
                }
            )
    concurrency = group.capacity.get("concurrency")
    if concurrency is not None:
        held = int(group.reserved.get("concurrency", 0))
        if held + 1 > int(concurrency):
            busy.append(
                {
                    "dimension": "concurrency",
                    "required": held + 1,
                    "availableNow": max(int(concurrency) - held, 0),
                }
            )
    if failures or missing:
        verdict = "infeasible"
    elif busy:
        verdict = "busy"
    else:
        verdict = "fits"
    return {
        "verdict": verdict,
        "failures": failures,
        "busy": busy,
        "missing": missing,
    }


def evaluate_spec(spec: JobSpec, groups: list[GroupState]) -> Evaluation:
    """Evaluate every candidate configuration against every group.

    Pure: takes observed group state, returns evidence. A candidate is
    usable only when the caller declared it job-compatible AND its
    quality change is not material — material changes need a human
    approval (§20.1) and cannot rescue feasibility on their own.
    """
    evaluations: list[ConfigVerdict] = []
    reasons: list[dict[str, Any]] = []
    missing: set[str] = set()
    for candidate in spec.candidates:
        if not candidate.compatible:
            evaluations.append(
                ConfigVerdict(
                    name=candidate.name,
                    kind=candidate.kind,
                    quality_impact=candidate.quality_impact,
                    compatible=False,
                    requires_quality_approval=candidate.requires_quality_approval,
                    basis=candidate.basis,
                    note=candidate.note,
                    estimates={d: b.to_dict() for d, b in candidate.estimates.items()},
                    uncertainty=candidate.uncertainty,
                    groups={},
                    verdict="excluded",
                    detail="declared incompatible with this operation",
                )
            )
            continue
        group_results = {g.name: _check_group(candidate, g) for g in groups}
        fits = [n for n, r in group_results.items() if r["verdict"] == "fits"]
        busy = [n for n, r in group_results.items() if r["verdict"] == "busy"]
        for r in group_results.values():
            missing.update(r["missing"])
        if candidate.requires_quality_approval:
            verdict = "excluded"
            detail = "fits only with a material quality change — needs human approval"
            if fits or busy:
                reasons.append(
                    {
                        "configuration": candidate.name,
                        "verdict": "requires_quality_approval",
                        "detail": "would fit a group but the quality change is material",
                    }
                )
        elif fits:
            verdict = "fits"
            detail = f"fits group '{fits[0]}'"
        elif busy:
            verdict = "busy"
            detail = f"fits group '{busy[0]}' capacity but it is currently reserved"
        else:
            verdict = "infeasible"
            if not groups:
                detail = "no resource groups configured — no observed capacity exists"
            else:
                dims = sorted(
                    {f["dimension"] for r in group_results.values() for f in r["failures"]}
                )
                detail = "exceeds available capacity on: " + ", ".join(dims or ["capacity"])
            reasons.append(
                {
                    "configuration": candidate.name,
                    "verdict": "infeasible",
                    "detail": detail,
                    "groups": {
                        n: {
                            "failures": r["failures"],
                            "missing": r["missing"],
                        }
                        for n, r in group_results.items()
                    },
                }
            )
        evaluations.append(
            ConfigVerdict(
                name=candidate.name,
                kind=candidate.kind,
                quality_impact=candidate.quality_impact,
                compatible=candidate.compatible,
                requires_quality_approval=candidate.requires_quality_approval,
                basis=candidate.basis,
                note=candidate.note,
                estimates={d: b.to_dict() for d, b in candidate.estimates.items()},
                uncertainty=candidate.uncertainty,
                groups=group_results,
                verdict=verdict,
                detail=detail,
                fits_group=fits[0] if fits else None,
                busy_groups=busy,
            )
        )
    feasible = any(c.verdict in ("fits", "busy") for c in evaluations)
    if feasible:
        reasons.insert(0, {"verdict": VERDICT_FEASIBLE, "detail": "a local path exists"})
    return Evaluation(
        verdict=VERDICT_FEASIBLE if feasible else VERDICT_INFEASIBLE,
        reasons=reasons,
        missing=sorted(missing),
        configurations=evaluations,
    )


def decision_for(evaluation: Evaluation) -> str:
    """Map evidence to the fallback decision. Feasible never routes to
    cloud — 'cloud is faster' is not an input to this function at all
    (AT-1001-1): only proven local infeasibility opens a review."""
    if evaluation.verdict == VERDICT_FEASIBLE:
        return DECISION_LOCAL_FEASIBLE
    return DECISION_EXPORT_PROPOSED


def cloud_capability() -> dict[str, Any]:
    """Honest cloud posture (§20.2): this deployment defines no cloud
    provider, account, or budget surface — the decision path therefore
    cannot submit work or spend anything."""
    return {
        "status": "not_configured",
        "provider": None,
        "account": None,
        "budget": None,
        "egress": "deny",
        "detail": (
            "no cloud provider, account, or budget is configured; "
            "fallback produces a review proposal only — nothing is "
            "submitted, transferred, or spent"
        ),
    }


@dataclass
class FallbackDecision:
    """Result of ``request_fallback`` — evidence ids plus a decision.
    ``cloud_authorized`` is structurally always ``False`` here: nothing
    in this path can authorize an export (§20.2)."""

    decision: str
    report_id: uuid.UUID
    proposal_id: uuid.UUID | None = None
    cloud_authorized: bool = False
    reason: str | None = None


class FeasibilityService:
    """Persisted feasibility evaluation + export-review proposal."""

    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    # -- evaluation ---------------------------------------------------

    def _lock_run(self, run_id: uuid.UUID) -> Run:
        run = self.db.execute(
            select(Run)
            .where(Run.workspace_id == self.ctx.workspace_id, Run.id == run_id)
            .with_for_update()
        ).scalar_one_or_none()
        if run is None:
            raise not_found("run")
        return run

    def _evaluate_locked(
        self,
        run: Run,
        hardware: dict[str, Any] | None,
    ) -> tuple[RunFeasibilityReport, Evaluation]:
        spec = parse_job_spec(run.request, default_operation=run.kind)
        adm = AdmissionService(self.db, self.ctx)
        groups = [
            GroupState(
                name=g.name,
                capacity=dict(g.capacity),
                reserve=dict(g.reserve),
                reserved=adm.utilization(g.name)["reserved"],
            )
            for g in adm.groups()
        ]
        if hardware is None:
            from workers.common.resources import detect

            hardware = detect().to_dict()
        evaluation = evaluate_spec(spec, groups)
        report = RunFeasibilityReport(
            workspace_id=self.ctx.workspace_id,
            run_id=run.id,
            evaluated_by=self.ctx.principal_id,
            operation=spec.operation,
            basis=max(
                (c.basis for c in spec.candidates),
                key=lambda b: 0 if b == "compatibility_check" else 1,
            ),
            sizes=spec.sizes,
            envelope=spec.candidates[0].envelope,
            configurations=[
                {
                    "name": c.name,
                    "kind": c.kind,
                    "qualityImpact": c.quality_impact,
                    "requiresQualityApproval": c.requires_quality_approval,
                    "compatible": c.compatible,
                    "basis": c.basis,
                    "note": c.note,
                    "estimates": c.estimates,
                    "uncertainty": c.uncertainty,
                    "groups": c.groups,
                    "verdict": c.verdict,
                    "detail": c.detail,
                    "fitsGroup": c.fits_group,
                    "busyGroups": c.busy_groups,
                }
                for c in evaluation.configurations
            ],
            uncertainty=spec.uncertainty,
            reasons=evaluation.reasons,
            missing=evaluation.missing,
            hardware=hardware,
            verdict=evaluation.verdict,
        )
        self.db.add(report)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="run.feasibility_evaluated",
            target_type="run",
            target_id=run.id,
            detail={
                "reportId": str(report.id),
                "verdict": evaluation.verdict,
                "operation": spec.operation,
            },
        )
        return report, evaluation

    def evaluate(
        self,
        run_id: uuid.UUID,
        *,
        hardware: dict[str, Any] | None = None,
    ) -> tuple[RunFeasibilityReport, Evaluation]:
        """Evaluate a run's declared spec against observed capacity and
        persist the evidence report (append-only; latest wins)."""
        run = self._lock_run(run_id)
        self.ctx.require(CAP_REQUEST_COMPUTE, run.task_id)
        return self._evaluate_locked(run, hardware)

    # -- fallback decision --------------------------------------------

    def request_fallback(
        self,
        run_id: uuid.UUID,
        *,
        hardware: dict[str, Any] | None = None,
    ) -> FallbackDecision:
        """Evaluate, record, and apply the fallback policy.

        Feasible → the run is left untouched and no proposal exists;
        'prefer cloud' is never an input (AT-1001-1). Infeasible → the
        run is blocked with reasons (when still pending) and an export
        review *proposal* is created. The proposal is inert: it has no
        payload, no recipient, no provider call and no spend (§20.2).
        """
        run = self._lock_run(run_id)
        self.ctx.require(CAP_REQUEST_COMPUTE, run.task_id)
        report, evaluation = self._evaluate_locked(run, hardware)
        if evaluation.verdict == VERDICT_FEASIBLE:
            audit_record(
                self.db,
                self.ctx,
                action="run.fallback_local_feasible",
                target_type="run",
                target_id=run.id,
                detail={"reportId": str(report.id)},
            )
            return FallbackDecision(
                decision=DECISION_LOCAL_FEASIBLE,
                report_id=report.id,
                reason="a compatible local configuration fits — no export review is proposed",
            )

        proposal = self._propose_export(run, report)
        if run.status in ("requested", "awaiting_approval"):
            RunService(self.db, self.ctx).block(
                run.id,
                reason="local_infeasible",
                detail={
                    "reportId": str(report.id),
                    "reasons": evaluation.reasons,
                    "missing": evaluation.missing,
                },
            )
        audit_record(
            self.db,
            self.ctx,
            action="run.export_review_proposed",
            target_type="run",
            target_id=run.id,
            detail={"reportId": str(report.id), "proposalId": str(proposal.id)},
        )
        return FallbackDecision(
            decision=DECISION_EXPORT_PROPOSED,
            report_id=report.id,
            proposal_id=proposal.id,
            reason="no approved compatible local configuration fits",
        )

    def _propose_export(self, run: Run, report: RunFeasibilityReport) -> ExportProposal:
        """Create (or reuse) the inert export-review proposal.

        ``bound_inputs`` bind run identity + request digest + verdict —
        the exact thing a human with ``approve_export`` would later
        approve through the existing approvals machinery. Re-requesting
        fallback for an unchanged request reuses the open proposal.
        """
        bound_inputs = {
            "runId": str(run.id),
            "requestDigest": run.request_digest,
            "operation": report.operation,
            "verdict": report.verdict,
            "proposalVersion": REPORT_VERSION,
        }
        digest = bound_digest(bound_inputs)
        existing = self.db.execute(
            select(ExportProposal)
            .where(
                ExportProposal.workspace_id == self.ctx.workspace_id,
                ExportProposal.run_id == run.id,
                ExportProposal.bound_digest == digest,
                ExportProposal.status == "proposed",
            )
            .order_by(ExportProposal.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            existing.feasibility_report_id = report.id
            self.db.flush()
            return existing
        proposal = ExportProposal(
            workspace_id=self.ctx.workspace_id,
            run_id=run.id,
            feasibility_report_id=report.id,
            proposed_by=self.ctx.principal_id,
            status="proposed",
            bound_inputs=bound_inputs,
            bound_digest=digest,
            required_capability=CAP_APPROVE_EXPORT,
        )
        self.db.add(proposal)
        self.db.flush()
        return proposal

    # -- reads --------------------------------------------------------

    def latest_report(self, run_id: uuid.UUID) -> RunFeasibilityReport | None:
        return self.db.execute(
            select(RunFeasibilityReport)
            .where(
                RunFeasibilityReport.workspace_id == self.ctx.workspace_id,
                RunFeasibilityReport.run_id == run_id,
            )
            .order_by(RunFeasibilityReport.created_at.desc(), RunFeasibilityReport.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    def latest_proposal(self, run_id: uuid.UUID) -> ExportProposal | None:
        return self.db.execute(
            select(ExportProposal)
            .where(
                ExportProposal.workspace_id == self.ctx.workspace_id,
                ExportProposal.run_id == run_id,
            )
            .order_by(ExportProposal.created_at.desc(), ExportProposal.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    def _export_approved(self, proposal: ExportProposal) -> bool:
        """True only when a live, matching-bound-digest ``export``
        approval exists — approval belongs to humans via the approvals
        machinery; this path never creates one."""
        now = datetime.now(UTC)
        rows = (
            self.db.execute(
                select(Approval).where(
                    Approval.workspace_id == self.ctx.workspace_id,
                    Approval.action == "export",
                    Approval.decision == "approved",
                    Approval.bound_digest == proposal.bound_digest,
                    Approval.revoked_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        return any(a.expires_at is None or a.expires_at > now for a in rows)

    def fallback_view(self, run_id: uuid.UUID) -> dict[str, Any]:
        """The whole fallback surface for one run: latest evidence
        report, proposal state (unapproved by default), and the honest
        cloud capability — for the UI and API clients."""
        runs = RunService(self.db, self.ctx)
        run = runs.get(run_id)
        self.ctx.require(CAP_REQUEST_COMPUTE, run.task_id)
        report = self.latest_report(run.id)
        proposal = self.latest_proposal(run.id)
        return {
            "run": {
                "id": str(run.id),
                "kind": run.kind,
                "status": run.status,
                "taskId": str(run.task_id) if run.task_id else None,
                "error": run.error,
            },
            "report": self.report_to_dict(report) if report else None,
            "proposal": self.proposal_to_dict(proposal) if proposal else None,
            "cloud": cloud_capability(),
        }

    def report_to_dict(self, report: RunFeasibilityReport) -> dict[str, Any]:
        return {
            "id": str(report.id),
            "runId": str(report.run_id),
            "evaluatedBy": str(report.evaluated_by),
            "operation": report.operation,
            "verdict": report.verdict,
            "basis": report.basis,
            "sizes": report.sizes,
            "envelope": report.envelope,
            "configurations": report.configurations,
            "uncertainty": report.uncertainty,
            "reasons": report.reasons,
            "missing": report.missing,
            "hardware": report.hardware,
            "createdAt": report.created_at.isoformat() if report.created_at else None,
        }

    def proposal_to_dict(self, proposal: ExportProposal) -> dict[str, Any]:
        return {
            "id": str(proposal.id),
            "runId": str(proposal.run_id),
            "feasibilityReportId": str(proposal.feasibility_report_id),
            "status": proposal.status,
            # Derived from the approvals ledger — a proposal alone is
            # never an approval, and a stored credential is not one
            # either (§20.2, AT-1001-3).
            "approved": self._export_approved(proposal),
            "boundInputs": proposal.bound_inputs,
            "boundDigest": proposal.bound_digest,
            "requiredCapability": proposal.required_capability,
            "sideEffects": "none",
            "createdAt": proposal.created_at.isoformat() if proposal.created_at else None,
        }
