"""Task lifecycle service (§7.1, §11).

States: draft -> active -> awaiting_review -> closed; active <-> paused;
draft/active/paused -> cancelled; awaiting_review -> active needs a
review reason. Closure stores a decision (supported_success /
supported_failure / inconclusive / stopped) separately from workflow
state; only an authorized *human* reviewer can close — an agent tool
can never close a task. Reopening records a reopen decision, keeps the
prior closure packet linked to its original contract, and starts a new
evaluation cycle.
"""

from __future__ import annotations

import uuid
from typing import Any

from chem_studio_policy.capabilities import (
    CAP_EDIT_TASK,
    CAP_READ_PROJECT,
    CAP_REVIEW_SCIENCE,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from studio.application.idempotency import request_digest
from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext
from studio.domain.tasks.contract import (
    validate_draft_payload,
    validate_freeze_payload,
)
from studio.errors import DomainError, ErrorCode, forbidden, not_found, revision_conflict
from studio.events.outbox import publish
from studio.persistence.models import (
    DECISION_KINDS,
    TASK_CLOSURES,
    TASK_MODES,
    TASK_STATES,
    ResearchTask,
    SuccessContractRevision,
    TaskDecision,
)
from studio.persistence.revisions import content_hash

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"active", "cancelled"}),
    "active": frozenset({"paused", "awaiting_review", "cancelled"}),
    "paused": frozenset({"active", "cancelled"}),
    # "closed" is reachable only through close() — it needs the
    # closure decision + evidence gates, not a bare transition.
    "awaiting_review": frozenset({"active"}),
    "closed": frozenset(),
    "cancelled": frozenset(),
}

# Fields a mode needs before it can meaningfully activate (§11.2-4).
# Missing entries are unresolved inputs — never fabricated.
MODE_REQUIRED_INPUTS: dict[str, tuple[str, ...]] = {
    "improve": ("baselineRevisionId", "variationScope"),
    "match_reference": ("referenceProductId", "matchScope"),
    "discover": ("targetKind", "objective"),
}

MATCH_SCOPES = ("functional", "analytical", "functional_and_analytical")
TARGET_KINDS = ("formulation", "material", "molecule", "unknown")

# Mode inputs that name authoritative entities — a value that does not
# resolve to a real workspace-scoped row is invalid, never "a baseline"
# (PAR-02 §7: strings like ``baseline-rev-1`` must not count).
_BASELINE_KINDS = (
    "formulation_revisions",
    "reference_product_revisions",
    "candidate_revisions",
)


def unresolved_inputs(task: ResearchTask) -> list[str]:
    """Which mode-required inputs are still unknown (§11)."""
    missing: list[str] = []
    required = MODE_REQUIRED_INPUTS.get(task.mode, ())
    for field in required:
        if field == "targetKind":
            if task.target_kind in (None, "unknown"):
                missing.append("targetKind")
            continue
        if field == "objective":
            if not task.objective:
                missing.append("objective")
            continue
        if not task.mode_inputs.get(field):
            missing.append(field)
    return sorted(missing)


def invalid_inputs(db: Session, task: ResearchTask) -> list[dict[str, str]]:
    """Mode inputs that are present but do not resolve to an existing
    authorized entity (PAR-02 §7). Blank values stay ``unresolved``;
    non-blank garbage like ``baseline-rev-1`` is invalid — it must never
    silently count as a real baseline/reference in calculations."""
    out: list[dict[str, str]] = []
    inputs = task.mode_inputs or {}

    def _resolves(value: Any, tables: tuple[str, ...]) -> bool:
        from studio.persistence.models import (
            CandidateRevision,
            FormulationRevision,
            ReferenceProduct,
            ReferenceProductRevision,
        )

        if not isinstance(value, str):
            return False
        try:
            entity_id = uuid.UUID(value)
        except ValueError:
            return False
        models: dict[str, Any] = {
            "candidate_revisions": CandidateRevision,
            "formulation_revisions": FormulationRevision,
            "reference_products": ReferenceProduct,
            "reference_product_revisions": ReferenceProductRevision,
        }
        for table in tables:
            model: Any = models[table]
            found = db.execute(
                select(model.id).where(
                    model.workspace_id == task.workspace_id,
                    model.id == entity_id,
                ).limit(1)
            ).scalar_one_or_none()
            if found is not None:
                return True
        return False

    baseline = inputs.get("baselineRevisionId")
    if baseline is not None and baseline != "":
        if not _resolves(baseline, _BASELINE_KINDS):
            out.append(
                {
                    "field": "baselineRevisionId",
                    "reason": "does not resolve to an existing revision entity",
                }
            )
    reference = inputs.get("referenceProductId")
    if reference is not None and reference != "":
        if not _resolves(reference, ("reference_products",)):
            out.append(
                {
                    "field": "referenceProductId",
                    "reason": "does not resolve to an existing reference product",
                }
            )
    return out


class TaskService:
    """Workspace-scoped task lifecycle commands."""

    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    # ---------------------------------------------------------- reads

    def _task(self, task_id: uuid.UUID, *, for_update: bool = False) -> ResearchTask:
        stmt = select(ResearchTask).where(
            ResearchTask.id == task_id,
            ResearchTask.workspace_id == self.ctx.workspace_id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        task = self.db.execute(stmt).scalar_one_or_none()
        if task is None:
            raise not_found("task")
        return task

    def get(self, task_id: uuid.UUID) -> ResearchTask:
        self.ctx.require(CAP_READ_PROJECT)
        return self._task(task_id)

    def decisions(self, task_id: uuid.UUID) -> list[TaskDecision]:
        self.ctx.require(CAP_READ_PROJECT)
        task = self._task(task_id)
        return list(
            self.db.execute(
                select(TaskDecision)
                .where(
                    TaskDecision.task_id == task.id,
                    TaskDecision.workspace_id == self.ctx.workspace_id,
                )
                .order_by(TaskDecision.created_at, TaskDecision.id)
            )
            .scalars()
            .all()
        )

    # ------------------------------------------------------- commands

    def create(
        self,
        *,
        project_id: uuid.UUID,
        title: str,
        mode: str,
        objective: str | None = None,
        target_kind: str | None = None,
        mode_inputs: dict[str, Any] | None = None,
    ) -> ResearchTask:
        """Create a draft task. Mode-required inputs may be absent — they
        persist as unresolved, never filled with made-up values (§11)."""
        self.ctx.require(CAP_EDIT_TASK, project_id)
        if mode not in TASK_MODES:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"mode must be one of {', '.join(TASK_MODES)}",
                field_path="input.mode",
            )
        if target_kind is not None and target_kind not in TARGET_KINDS:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"targetKind must be one of {', '.join(TARGET_KINDS)}",
                field_path="input.targetKind",
            )
        scope = (mode_inputs or {}).get("matchScope")
        if scope is not None and scope not in MATCH_SCOPES:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"matchScope must be one of {', '.join(MATCH_SCOPES)}",
                field_path="input.modeInputs.matchScope",
            )
        if not title.strip():
            raise DomainError(ErrorCode.VALIDATION, "title is required", field_path="input.title")
        task = ResearchTask(
            workspace_id=self.ctx.workspace_id,
            project_id=project_id,
            owner_id=self.ctx.principal_id,
            mode=mode,
            target_kind=target_kind or "unknown",
            title=title.strip(),
            objective=objective,
            mode_inputs=mode_inputs or {},
            workflow_state="draft",
            reviewer_id=None,
        )
        self.db.add(task)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="task",
            aggregate_id=task.id,
            event_type="task.created",
            payload={"taskId": str(task.id), "projectId": str(project_id)},
        )
        audit_record(
            self.db,
            self.ctx,
            action="task.create",
            target_type="task",
            target_id=task.id,
            detail={"mode": mode},
        )
        return task

    def transition(
        self,
        *,
        task_id: uuid.UUID,
        to_state: str,
        reason: str | None = None,
        expected_version: int | None = None,
    ) -> ResearchTask:
        """Workflow transition (not closure). Compare-and-swap on
        ``expected_version`` when provided (§5.3)."""
        task = self._task(task_id)
        if to_state == "closed":
            raise DomainError(
                ErrorCode.VALIDATION,
                "closing requires the taskClose command with a closure decision",
                field_path="input.toState",
            )
        if to_state not in TASK_STATES:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"unknown state '{to_state}'",
                field_path="input.toState",
            )
        allowed = ALLOWED_TRANSITIONS[task.workflow_state]
        if to_state not in allowed:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"transition {task.workflow_state} -> {to_state} is not allowed",
                field_path="input.toState",
            )
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if expected_version is not None and task.version != expected_version:
            raise revision_conflict("task")
        kind = "state_change"
        if task.workflow_state == "awaiting_review" and to_state == "active":
            if not reason:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "returning to active requires a review reason",
                    field_path="input.reason",
                )
            kind = "review_return"
        task.workflow_state = to_state
        task.version += 1
        self.db.flush()
        self._decision(task, kind, {"toState": to_state, "reason": reason})
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="task",
            aggregate_id=task.id,
            event_type="task.transitioned",
            payload={
                "taskId": str(task.id),
                "toState": to_state,
                "reason": reason,
            },
        )
        audit_record(
            self.db,
            self.ctx,
            action="task.transition",
            target_type="task",
            target_id=task.id,
            detail={"toState": to_state},
        )
        return task

    def close(
        self,
        *,
        task_id: uuid.UUID,
        closure_decision: str,
        packet: dict[str, Any] | None = None,
        candidate_revision_id: uuid.UUID | None = None,
    ) -> ResearchTask:
        """Close with a recorded closure decision (§7.1).

        Human reviewers only: an agent principal is denied even if it
        somehow holds review_science, and supported_success additionally
        needs the frozen-contract evidence gates. When the task carries
        more than one research-accepted candidate the reviewer must name
        the candidate the close binds to — the evaluator never picks one
        by revision (PAR-02 §5-6).
        """
        task = self._task(task_id)
        if self.ctx.principal_kind != "user":
            raise forbidden("task closure (human review required)")
        self.ctx.require(CAP_REVIEW_SCIENCE)
        if task.workflow_state != "awaiting_review":
            raise DomainError(
                ErrorCode.VALIDATION,
                "task must be awaiting_review to close",
                field_path="input.taskId",
            )
        if closure_decision not in TASK_CLOSURES:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"closureDecision must be one of {', '.join(TASK_CLOSURES)}",
                field_path="input.closureDecision",
            )
        accepted = self._accepted_candidates(task)
        if len(accepted) > 1 and candidate_revision_id is None:
            raise DomainError(
                ErrorCode.VALIDATION,
                "multiple accepted candidates — close requires an explicit "
                "candidateRevisionId binding the report the reviewer saw",
                field_path="input.candidateRevisionId",
                safe_details={
                    "candidateRevisionIds": [str(c.id) for c in accepted]
                },
            )
        bound_packet = self._closeout_packet(
            task, candidate_revision_id=candidate_revision_id
        )
        if closure_decision == "supported_success":
            self._success_evidence_gate(bound_packet)
        elif closure_decision == "supported_failure":
            self._failure_evidence_gate(bound_packet, packet)
        prior_contract = task.current_contract_revision_id
        task.workflow_state = "closed"
        task.closure_decision = closure_decision
        task.version += 1
        self.db.flush()
        self._decision(
            task,
            "closure",
            {
                "closureDecision": closure_decision,
                "contractRevisionId": str(prior_contract) if prior_contract else None,
                "candidateRevisionId": bound_packet.get("candidateRevisionId"),
                "evaluationCycle": task.evaluation_cycle,
                "packet": bound_packet,
                "reviewerPacket": packet or {},
            },
        )
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="task",
            aggregate_id=task.id,
            event_type="task.closed",
            payload={
                "taskId": str(task.id),
                "closureDecision": closure_decision,
                "contractRevisionId": str(prior_contract) if prior_contract else None,
                "evaluationCycle": task.evaluation_cycle,
            },
        )
        audit_record(
            self.db,
            self.ctx,
            action="task.close",
            target_type="task",
            target_id=task.id,
            detail={"closureDecision": closure_decision},
        )
        return task

    def reopen(self, *, task_id: uuid.UUID, reason: str) -> ResearchTask:
        """Reopen a closed task: records the decision, keeps the prior
        closure packet linked to its contract, new evaluation cycle."""
        task = self._task(task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if task.workflow_state != "closed":
            raise DomainError(
                ErrorCode.VALIDATION,
                "only a closed task can be reopened",
                field_path="input.taskId",
            )
        if not reason:
            raise DomainError(
                ErrorCode.VALIDATION,
                "reopening requires a reason",
                field_path="input.reason",
            )
        prior = {
            "closureDecision": task.closure_decision,
            "contractRevisionId": (
                str(task.current_contract_revision_id)
                if task.current_contract_revision_id
                else None
            ),
            "evaluationCycle": task.evaluation_cycle,
        }
        task.workflow_state = "active"
        task.closure_decision = None
        task.evaluation_cycle += 1
        task.version += 1
        self.db.flush()
        self._decision(task, "reopen", {"reason": reason, "priorClosure": prior})
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="task",
            aggregate_id=task.id,
            event_type="task.reopened",
            payload={"taskId": str(task.id), "reason": reason},
        )
        audit_record(
            self.db,
            self.ctx,
            action="task.reopen",
            target_type="task",
            target_id=task.id,
            detail={"reason": reason},
        )
        return task

    # -------------------------------------------------- contract revs

    def draft_contract(
        self, *, task_id: uuid.UUID, payload: dict[str, Any]
    ) -> SuccessContractRevision:
        """New contract draft (rev = max+1). Thresholds live in the
        payload; unresolved fields stay unresolved.

        The canonical contract schema is validated before anything is
        written (PAR-01): malformed vocabulary is rejected, but a draft
        may carry explicit unknown top-level fields for review —
        nothing missing is ever filled with a scientific default."""
        validate_draft_payload(payload)
        # Lock the task row: concurrent draft/freezes must serialize so
        # revision = max+1 cannot race the (task_id, revision) unique
        # constraint into a bare IntegrityError (CS-1201).
        task = self._task(task_id, for_update=True)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        current_max = self.db.execute(
            select(func.max(SuccessContractRevision.revision)).where(
                SuccessContractRevision.task_id == task.id
            )
        ).scalar_one()
        rev = SuccessContractRevision(
            workspace_id=self.ctx.workspace_id,
            task_id=task.id,
            revision=(current_max or 0) + 1,
            status="draft",
            payload=payload,
            content_hash=content_hash(payload),
            created_by=self.ctx.principal_id,
        )
        self.db.add(rev)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="task",
            aggregate_id=task.id,
            event_type="contract.drafted",
            payload={"taskId": str(task.id), "revisionId": str(rev.id)},
        )
        return rev

    def freeze_contract(self, *, revision_id: uuid.UUID) -> SuccessContractRevision:
        """Freeze a draft revision: it becomes the task's current
        contract; any prior frozen revision supersedes (immutable —
        the DB trigger guarantees the status-only transition)."""
        rev = self.db.execute(
            select(SuccessContractRevision).where(
                SuccessContractRevision.id == revision_id,
                SuccessContractRevision.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if rev is None:
            raise not_found("contract revision")
        # Lock the task row (same lock point as draft_contract) so the
        # status check + version bump serialize against concurrent
        # contract writes on this task (CS-1201).
        task = self._task(rev.task_id, for_update=True)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if rev.status != "draft":
            raise DomainError(
                ErrorCode.VALIDATION,
                f"only a draft revision can be frozen (status is '{rev.status}')",
                field_path="input.revisionId",
            )
        # Freeze is the action that binds the contract for evaluation:
        # require the payload to be fully canonical — every resolved
        # metric identified and bound, no declared unknowns, no unknown
        # top-level fields. Anything short stays a draft for review
        # instead of silently freezing (PAR-01).
        validate_freeze_payload(rev.payload)
        prior = self.db.execute(
            select(SuccessContractRevision).where(
                SuccessContractRevision.task_id == task.id,
                SuccessContractRevision.status == "frozen",
            )
        ).scalar_one_or_none()
        if prior is not None:
            prior.status = "superseded"  # the only legal transition
            self.db.flush()
        rev.status = "frozen"
        self.db.flush()
        task.current_contract_revision_id = rev.id
        task.version += 1
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="task",
            aggregate_id=task.id,
            event_type="contract.frozen",
            payload={"taskId": str(task.id), "revisionId": str(rev.id)},
        )
        audit_record(
            self.db,
            self.ctx,
            action="contract.freeze",
            target_type="success_contract_revision",
            target_id=rev.id,
            detail={"revision": rev.revision},
        )
        return rev

    # ------------------------------------------------------- internals

    def _closeout_packet(
        self, task: ResearchTask, *, candidate_revision_id: uuid.UUID | None = None
    ) -> dict[str, Any]:
        """The packet stored on close is always derived server-side by
        the evaluator (§12.3) — the reviewer's packet is kept alongside
        as context, never trusted as the bound evidence record."""
        from studio.domain.tasks.evaluation import TaskEvaluationService

        return TaskEvaluationService(self.db, self.ctx).closeout_packet(
            task.id, candidate_revision_id=candidate_revision_id
        )

    def _accepted_candidates(self, task: ResearchTask) -> list[Any]:
        from studio.persistence.models import CandidateRevision

        return list(
            self.db.execute(
                select(CandidateRevision)
                .where(
                    CandidateRevision.workspace_id == self.ctx.workspace_id,
                    CandidateRevision.task_id == task.id,
                    CandidateRevision.status == "accepted_for_research",
                )
                .order_by(CandidateRevision.revision)
            ).scalars()
        )

    def _success_evidence_gate(self, packet: dict[str, Any]) -> None:
        """supported_success needs the evaluator to report eligibility
        (§7.1, §12.3): frozen contract, all required metrics met by
        accepted applicable evidence, every hard gate passed."""
        if packet.get("contractRevisionId") is None:
            raise DomainError(
                ErrorCode.EVIDENCE_INSUFFICIENT,
                "supported_success requires a frozen success contract",
            )
        if not packet["supportedSuccessEligible"]:
            missing = [
                {"metric": m["metricId"], "verdict": m["verdict"]}
                for m in packet["metrics"]
                if m["required"] and m["verdict"] != "met"
            ]
            gates = [
                {"gate": g["id"], "verdict": g["verdict"]}
                for g in packet["gates"]
                if g["verdict"] != "pass"
            ]
            raise DomainError(
                ErrorCode.EVIDENCE_INSUFFICIENT,
                "supported_success needs every required metric met and every hard gate passed",
                safe_details={
                    "unmet": missing,
                    "unprovenGates": gates,
                    "suggestedDecision": packet["suggestedDecision"],
                },
            )

    def _failure_evidence_gate(
        self, packet: dict[str, Any], reviewer_packet: dict[str, Any] | None
    ) -> None:
        """supported_failure beyond the evaluator's own suggestion is a
        reviewer-recorded outcome — it needs the reviewer's rationale
        plus evidence ids bound into the packet they saw (PAR-04 §6).
        Otherwise the honest closure is inconclusive/stopped — an
        unmeasured or unsupported experiment can never carry a measured
        failure label."""
        if packet.get("suggestedDecision") == "supported_failure":
            return
        reviewer_packet = reviewer_packet or {}
        rationale = str(reviewer_packet.get("rationale") or "").strip()
        cited = {str(e) for e in (reviewer_packet.get("evidenceIds") or [])}
        selection = packet.get("evidenceSelection") or {}
        bound = (
            {str(e) for e in (selection.get("includedIds") or [])}
            | {
                str(e.get("measurementId"))
                for e in (selection.get("exclusions") or [])
                if isinstance(e, dict)
            }
            | {str(e) for e in (packet.get("evidenceIds") or [])}
        )
        unbound = cited - bound
        if not rationale or not cited or unbound:
            raise DomainError(
                ErrorCode.EVIDENCE_INSUFFICIENT,
                "supported_failure beyond the evaluator's suggestion requires "
                "the reviewer's rationale plus evidenceIds bound into the "
                "closeout packet — otherwise close as inconclusive or stopped",
                safe_details={
                    "suggestedDecision": packet.get("suggestedDecision"),
                    "rationaleProvided": bool(rationale),
                    "unboundEvidenceIds": sorted(unbound),
                },
            )

    def _decision(self, task: ResearchTask, kind: str, payload: dict[str, Any]) -> TaskDecision:
        if kind not in DECISION_KINDS:
            raise DomainError(ErrorCode.VALIDATION, f"unknown decision kind '{kind}'")
        decision = TaskDecision(
            workspace_id=self.ctx.workspace_id,
            task_id=task.id,
            kind=kind,
            decided_by=self.ctx.principal_id,
            payload=payload,
        )
        self.db.add(decision)
        self.db.flush()
        return decision


def digest_for_payload(payload: dict[str, Any]) -> str:
    """Convenience re-export for callers needing the contract digest."""
    return request_digest(payload)
