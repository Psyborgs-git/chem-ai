"""Experiment plans (§14.1, CS-0501).

A plan drafts references to *immutable* revisions — candidate,
contract, process, method — never to mutable rows. The scientific
reviewer sees the diff, unknown inputs, hazard notes, resource needs,
sample plan and acceptance criteria; approval binds the exact
bound-input digest. Editing any bound content afterwards makes the
release approval stale — packet export re-verifies the digest at
execution time (AT-0501-1).

Missing inputs are surfaced as review blockers, never invented
(AT-0501-2): unknown material identities, a missing required method,
and the task's own unresolved mode inputs are listed explicitly.

The exported packet is a manual-execution document (AT-0501-3) —
the system does not start equipment.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from chem_studio_policy.capabilities import (
    CAP_APPROVE_EXPERIMENT,
    CAP_EDIT_TASK,
    CAP_READ_PROJECT,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.application.approvals import bound_digest, grant
from studio.application.idempotency import request_digest
from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext
from studio.domain.tasks.service import unresolved_inputs
from studio.errors import DomainError, ErrorCode, not_found
from studio.events.outbox import publish
from studio.persistence.models import (
    Approval,
    CandidateRevision,
    ExperimentPlan,
    FormulationRevision,
    MaterialIdentity,
    ResearchTask,
)

RELEASE_ACTION = "experiment_release"
_EDITABLE = {"draft", "submitted", "approved"}

MANUAL_EXECUTION_LABEL = (
    "MANUAL EXECUTION — qualified operator required; the system does not start equipment"
)


def _payload_digest(payload: dict[str, Any]) -> str:
    return request_digest(payload)


class LabPlanService:
    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    # ---------------------------------------------------------- queries

    def list_for_task(self, task_id: uuid.UUID) -> list[ExperimentPlan]:
        task = self._task(task_id)
        self.ctx.require(CAP_READ_PROJECT, task.project_id)
        return list(
            self.db.execute(
                select(ExperimentPlan)
                .where(
                    ExperimentPlan.workspace_id == self.ctx.workspace_id,
                    ExperimentPlan.task_id == task_id,
                )
                .order_by(ExperimentPlan.created_at, ExperimentPlan.id)
            ).scalars()
        )

    def get(self, plan_id: uuid.UUID) -> ExperimentPlan:
        plan = self._plan(plan_id)
        task = self._task(plan.task_id)
        self.ctx.require(CAP_READ_PROJECT, task.project_id)
        return plan

    # ---------------------------------------------------------- drafting

    def create(self, task_id: uuid.UUID, *, title: str, payload: dict[str, Any]) -> ExperimentPlan:
        task = self._task(task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if not (title or "").strip():
            raise DomainError(ErrorCode.VALIDATION, "title is required", field_path="title")
        if not isinstance(payload, dict):
            raise DomainError(ErrorCode.VALIDATION, "payload must be an object")
        plan = ExperimentPlan(
            workspace_id=self.ctx.workspace_id,
            task_id=task_id,
            title=title.strip(),
            status="draft",
            payload=payload,
            created_by=self.ctx.principal_id,
        )
        self._rebind(plan)
        plan.blockers = self._compute_blockers(task, payload)
        self.db.add(plan)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="experiment_plan.created",
            target_type="experiment_plan",
            target_id=plan.id,
            detail={"taskId": str(task_id)},
        )
        return plan

    def update(self, plan_id: uuid.UUID, *, payload: dict[str, Any]) -> ExperimentPlan:
        """Editing an approved plan is allowed — it shifts the content
        digest, so the previously granted release approval becomes
        stale at packet export (§14.1, AT-0501-1)."""
        plan = self._plan(plan_id)
        task = self._task(plan.task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if plan.status not in _EDITABLE:
            raise DomainError(ErrorCode.CONFLICT, f"plan in '{plan.status}' cannot be edited")
        if not isinstance(payload, dict):
            raise DomainError(ErrorCode.VALIDATION, "payload must be an object")
        plan.payload = payload
        self._rebind(plan)
        plan.blockers = self._compute_blockers(task, payload)
        plan.packet = None
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="experiment_plan",
            aggregate_id=plan.id,
            event_type="experiment_plan.updated",
            payload={
                "planId": str(plan.id),
                "taskId": str(plan.task_id),
                "contentDigest": plan.content_digest,
            },
        )
        return plan

    # ---------------------------------------------------------- review

    def submit(self, plan_id: uuid.UUID) -> ExperimentPlan:
        plan = self._plan(plan_id)
        task = self._task(plan.task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if plan.status != "draft":
            raise DomainError(ErrorCode.CONFLICT, "only a draft can be submitted")
        plan.status = "submitted"
        plan.blockers = self._compute_blockers(task, plan.payload)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="experiment_plan",
            aggregate_id=plan.id,
            event_type="experiment_plan.submitted",
            payload={
                "planId": str(plan.id),
                "taskId": str(plan.task_id),
                "blockers": plan.blockers,
            },
        )
        return plan

    def review(
        self, plan_id: uuid.UUID, *, decision: str, rationale: str | None = None
    ) -> ExperimentPlan:
        """Scientific review (§14.1/§21.5): only a principal holding
        ``approve_experiment`` (a human role — never an agent) may
        decide. Open blockers must be resolved before approval; the
        system lists them instead of inventing input (AT-0501-2)."""
        plan = self._plan(plan_id)
        task = self._task(plan.task_id)
        self.ctx.require(CAP_APPROVE_EXPERIMENT, task.project_id)
        if plan.status != "submitted":
            raise DomainError(ErrorCode.CONFLICT, "only a submitted plan can be reviewed")
        if decision not in ("approved", "rejected"):
            raise DomainError(ErrorCode.VALIDATION, "decision must be approved|rejected")
        blockers = self._compute_blockers(task, plan.payload)
        plan.blockers = blockers
        if decision == "approved" and blockers:
            raise DomainError(
                ErrorCode.CONFLICT,
                "plan has unresolved blockers",
                safe_details={"blockers": blockers},
            )
        approval = grant(
            self.db,
            self.ctx,
            action=RELEASE_ACTION,
            bound_inputs=self._bound_inputs(plan),
            decision=decision,
            rationale=rationale,
        )
        plan.approval_id = approval.id
        plan.status = decision
        plan.packet = None
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="experiment_plan",
            aggregate_id=plan.id,
            event_type="experiment_plan.reviewed",
            payload={
                "planId": str(plan.id),
                "taskId": str(plan.task_id),
                "decision": decision,
                "approvalId": str(approval.id),
            },
        )
        return plan

    # ---------------------------------------------------------- packet

    def export_packet(self, plan_id: uuid.UUID) -> dict[str, Any]:
        """Manual execution packet (§14.1, AT-0501-3): requires a valid
        approval bound to the *current* bound inputs — a stale digest,
        revocation or expiry blocks the export (AT-0501-1)."""
        plan = self._plan(plan_id)
        task = self._task(plan.task_id)
        self.ctx.require(CAP_READ_PROJECT, task.project_id)
        if plan.status != "approved":
            raise DomainError(ErrorCode.CONFLICT, "only an approved plan can produce a packet")
        approval = self.verify_release_approval(plan)
        packet = {
            "planId": str(plan.id),
            "taskId": str(plan.task_id),
            "title": plan.title,
            "executionMode": "manual",
            "label": MANUAL_EXECUTION_LABEL,
            "revisions": {
                "candidateRevisionId": plan.payload.get("candidateRevisionId"),
                "contractRevisionId": plan.payload.get("contractRevisionId"),
                "processRevisionId": plan.payload.get("processRevisionId"),
            },
            "method": plan.payload.get("method"),
            "samplePlan": plan.payload.get("samplePlan"),
            "acceptanceCriteria": plan.payload.get("acceptanceCriteria"),
            "hazardNotes": plan.payload.get("hazardNotes"),
            "resourceNeeds": plan.payload.get("resourceNeeds"),
            "approval": {
                "id": str(approval.id),
                "decidedBy": str(approval.decided_by),
                "decidedAt": approval.created_at.isoformat(),
            },
            "contentDigest": plan.content_digest,
            "exportedAt": datetime.now(UTC).isoformat(),
        }
        plan.packet = packet
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="experiment_plan.packet_exported",
            target_type="experiment_plan",
            target_id=plan.id,
            detail={"approvalId": str(approval.id)},
        )
        return packet

    # ---------------------------------------------------------- internals

    def _bound_inputs(self, plan: ExperimentPlan) -> dict[str, Any]:
        """What the release approval binds: plan id + content digest —
        exact, never a mutable reference."""
        return {
            "planId": str(plan.id),
            "taskId": str(plan.task_id),
            "contentDigest": plan.content_digest,
        }

    def _rebind(self, plan: ExperimentPlan) -> None:
        plan.content_digest = _payload_digest(plan.payload)
        plan.bound_inputs = {
            "planId": str(plan.id),
            "taskId": str(plan.task_id),
            "contentDigest": plan.content_digest,
        }

    def verify_release_approval(self, plan: ExperimentPlan) -> Approval:
        if plan.approval_id is None:
            raise DomainError(ErrorCode.FORBIDDEN, "no release approval on record")
        approval = self.db.execute(
            select(Approval).where(
                Approval.workspace_id == self.ctx.workspace_id,
                Approval.id == plan.approval_id,
            )
        ).scalar_one_or_none()
        if approval is None or approval.decision != "approved":
            raise DomainError(ErrorCode.FORBIDDEN, "release approval missing")
        if approval.revoked_at is not None:
            raise DomainError(ErrorCode.FORBIDDEN, "release approval was revoked")
        expires = approval.expires_at
        if expires is not None:
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if expires <= datetime.now(UTC):
                raise DomainError(
                    ErrorCode.APPROVAL_EXPIRED,
                    "release approval expired; request a new review",
                    retryable=False,
                )
        if approval.bound_digest != bound_digest(self._bound_inputs(plan)):
            raise DomainError(
                ErrorCode.APPROVAL_STALE,
                "plan changed since approval; request a fresh review",
                safe_details={"approvalId": str(approval.id)},
            )
        return approval

    def _compute_blockers(
        self, task: ResearchTask, payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Unknown inputs the reviewer must see — never invented
        (§21.5, AT-0501-2)."""
        blockers: list[dict[str, Any]] = []
        for name in unresolved_inputs(task):
            blockers.append(
                {"kind": "unresolved_task_input", "text": f"task input '{name}' unresolved"}
            )
        if not str(payload.get("method") or "").strip():
            blockers.append({"kind": "missing_method", "text": "required method not specified"})
        blockers.extend(self._material_blockers(payload))
        return blockers

    def _material_blockers(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Ingredients the lab will weigh must resolve to registered
        material identities — unknown identity is a blocker, not a
        guess (§21.5)."""
        out: list[dict[str, Any]] = []
        cand_id = payload.get("candidateRevisionId")
        if not cand_id:
            return out
        cand = self.db.execute(
            select(CandidateRevision).where(
                CandidateRevision.workspace_id == self.ctx.workspace_id,
                CandidateRevision.id == _as_uuid(cand_id),
            )
        ).scalar_one_or_none()
        if cand is None:
            return [{"kind": "missing_reference", "text": "candidate revision not found"}]
        if cand.entity_kind != "formulation" or cand.entity_revision_id is None:
            return out
        rev = self.db.execute(
            select(FormulationRevision).where(
                FormulationRevision.workspace_id == self.ctx.workspace_id,
                FormulationRevision.id == cand.entity_revision_id,
            )
        ).scalar_one_or_none()
        if rev is None:
            return [{"kind": "missing_reference", "text": "formulation revision not found"}]
        known = {
            str(r)
            for r in self.db.execute(
                select(MaterialIdentity.id).where(
                    MaterialIdentity.workspace_id == self.ctx.workspace_id
                )
            ).scalars()
        }
        for line in rev.payload.get("ingredients") or []:
            if not isinstance(line, dict):
                continue
            mid = line.get("materialId")
            name = line.get("name") or "?"
            if mid is None:
                out.append(
                    {
                        "kind": "material_identity_missing",
                        "text": f"ingredient '{name}' has no linked material identity",
                    }
                )
            elif str(mid) not in known:
                out.append(
                    {
                        "kind": "material_identity_missing",
                        "text": f"ingredient '{name}' references unknown material '{mid}'",
                    }
                )
        return out

    def _task(self, task_id: uuid.UUID) -> ResearchTask:
        task = self.db.execute(
            select(ResearchTask).where(
                ResearchTask.workspace_id == self.ctx.workspace_id,
                ResearchTask.id == task_id,
            )
        ).scalar_one_or_none()
        if task is None:
            raise not_found("task")
        return task

    def _plan(self, plan_id: uuid.UUID) -> ExperimentPlan:
        plan = self.db.execute(
            select(ExperimentPlan).where(
                ExperimentPlan.workspace_id == self.ctx.workspace_id,
                ExperimentPlan.id == plan_id,
            )
        ).scalar_one_or_none()
        if plan is None:
            raise not_found("experiment plan")
        return plan


def _as_uuid(value: Any) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
