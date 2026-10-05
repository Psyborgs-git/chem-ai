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


class TaskService:
    """Workspace-scoped task lifecycle commands."""

    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    # ---------------------------------------------------------- reads

    def _task(self, task_id: uuid.UUID) -> ResearchTask:
        task = self.db.execute(
            select(ResearchTask).where(
                ResearchTask.id == task_id,
                ResearchTask.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
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
    ) -> ResearchTask:
        """Close with a recorded closure decision (§7.1).

        Human reviewers only: an agent principal is denied even if it
        somehow holds review_science, and supported_success additionally
        needs the frozen-contract evidence gates.
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
        bound_packet = self._closeout_packet(task)
        if closure_decision == "supported_success":
            self._success_evidence_gate(bound_packet)
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
        payload; unresolved fields stay unresolved."""
        task = self._task(task_id)
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
        task = self._task(rev.task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if rev.status != "draft":
            raise DomainError(
                ErrorCode.VALIDATION,
                f"only a draft revision can be frozen (status is '{rev.status}')",
                field_path="input.revisionId",
            )
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

    def _closeout_packet(self, task: ResearchTask) -> dict[str, Any]:
        """The packet stored on close is always derived server-side by
        the evaluator (§12.3) — the reviewer's packet is kept alongside
        as context, never trusted as the bound evidence record."""
        from studio.domain.tasks.evaluation import TaskEvaluationService

        return TaskEvaluationService(self.db, self.ctx).closeout_packet(task.id)

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
