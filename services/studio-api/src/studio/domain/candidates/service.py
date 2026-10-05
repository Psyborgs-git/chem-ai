"""Candidate revisions + proposal patches (§5, §7.2).

A candidate's *content* lives on immutable revisions: status moves
draft → submitted → accepted_for_research | rejected through human
review, while eligibility is a separate assessment axis that never
mutates content. Patches are the only content-mutation path —
accepting one creates a *new* draft revision (parent-linked);
rejecting one leaves the target untouched and retains the reason.
Rankings and measurements attach elsewhere; they never mutate a
candidate row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from chem_studio_policy.capabilities import (
    CAP_PROPOSE_CANDIDATE,
    CAP_READ_PROJECT,
    CAP_REVIEW_SCIENCE,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext
from studio.errors import DomainError, ErrorCode, not_found
from studio.events.outbox import publish
from studio.persistence.models import (
    CANDIDATE_ELIGIBILITY,
    ENTITY_KINDS,
    CandidatePatch,
    CandidateRevision,
    ResearchTask,
)
from studio.persistence.revisions import content_hash


def _require_human(ctx: ServiceContext) -> None:
    if ctx.principal_kind != "user":
        raise DomainError(
            ErrorCode.FORBIDDEN,
            "candidate review requires a human reviewer",
        )


class CandidateService:
    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    # ---------------------------------------------------------- reads

    def get(self, candidate_id: uuid.UUID) -> CandidateRevision:
        self.ctx.require(CAP_READ_PROJECT)
        return self._candidate(candidate_id)

    def list_for_task(self, task_id: uuid.UUID) -> list[CandidateRevision]:
        self.ctx.require(CAP_READ_PROJECT)
        return list(
            self.db.execute(
                select(CandidateRevision)
                .where(
                    CandidateRevision.task_id == task_id,
                    CandidateRevision.workspace_id == self.ctx.workspace_id,
                )
                .order_by(CandidateRevision.revision)
            ).scalars()
        )

    def get_patch(self, patch_id: uuid.UUID) -> CandidatePatch:
        self.ctx.require(CAP_READ_PROJECT)
        return self._patch(patch_id)

    # --------------------------------------------------- candidates

    def create_candidate(
        self,
        *,
        task_id: uuid.UUID,
        entity_kind: str,
        entity_revision_id: uuid.UUID | None = None,
        hypothesis: str | None = None,
        proposed_differences: list[dict[str, Any]] | None = None,
        evidence_ids: list[str] | None = None,
        contract_revision_id: uuid.UUID | None = None,
        parent_revision_id: uuid.UUID | None = None,
    ) -> CandidateRevision:
        """Agents and users may propose; review stays human."""
        self.ctx.require(CAP_PROPOSE_CANDIDATE)
        task = self.db.execute(
            select(ResearchTask).where(
                ResearchTask.id == task_id,
                ResearchTask.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if task is None:
            raise not_found("task")
        if entity_kind not in ENTITY_KINDS:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"entity_kind must be one of {ENTITY_KINDS}",
                field_path="input.entityKind",
            )
        if parent_revision_id is not None:
            parent = self._candidate(parent_revision_id)
            if parent.task_id != task.id:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "parent candidate belongs to a different task",
                    field_path="input.parentRevisionId",
                )
        payload: dict[str, Any] = {
            "proposedDifferences": proposed_differences or [],
            "evidenceIds": evidence_ids or [],
        }
        current_max = self.db.execute(
            select(func.max(CandidateRevision.revision)).where(CandidateRevision.task_id == task.id)
        ).scalar_one()
        row = CandidateRevision(
            workspace_id=self.ctx.workspace_id,
            task_id=task.id,
            revision=(current_max or 0) + 1,
            status="draft",
            eligibility="not_assessed",
            entity_kind=entity_kind,
            entity_revision_id=entity_revision_id,
            parent_revision_id=parent_revision_id,
            contract_revision_id=contract_revision_id,
            hypothesis=hypothesis,
            payload=payload,
            content_hash=content_hash(
                {
                    **payload,
                    "entityKind": entity_kind,
                    "entityRevisionId": str(entity_revision_id or ""),
                    "hypothesis": hypothesis or "",
                }
            ),
            created_by=self.ctx.principal_id,
        )
        self.db.add(row)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="research_task",
            aggregate_id=task.id,
            event_type="candidate.created",
            payload={
                "taskId": str(task.id),
                "candidateId": str(row.id),
                "entityKind": entity_kind,
            },
        )
        return row

    def submit_candidate(self, *, candidate_id: uuid.UUID) -> CandidateRevision:
        self.ctx.require(CAP_PROPOSE_CANDIDATE)
        cand = self._candidate(candidate_id)
        if cand.status != "draft":
            raise DomainError(
                ErrorCode.VALIDATION,
                f"only a draft candidate can be submitted ('{cand.status}')",
                field_path="input.candidateId",
            )
        cand.status = "submitted"
        self.db.flush()
        return cand

    def review_candidate(self, *, candidate_id: uuid.UUID, accept: bool) -> CandidateRevision:
        """Human-only scientific review: submitted → accepted_for_research
        | rejected."""
        self.ctx.require(CAP_REVIEW_SCIENCE)
        _require_human(self.ctx)
        cand = self._candidate(candidate_id)
        if cand.status != "submitted":
            raise DomainError(
                ErrorCode.VALIDATION,
                f"only a submitted candidate can be reviewed ('{cand.status}')",
                field_path="input.candidateId",
            )
        cand.status = "accepted_for_research" if accept else "rejected"
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="candidate_revision",
            aggregate_id=cand.id,
            event_type="candidate.reviewed",
            payload={
                "candidateId": str(cand.id),
                "decision": cand.status,
            },
        )
        audit_record(
            self.db,
            self.ctx,
            action="candidate.review",
            target_type="candidate_revision",
            target_id=cand.id,
            detail={"decision": cand.status},
        )
        return cand

    def set_eligibility(self, *, candidate_id: uuid.UUID, eligibility: str) -> CandidateRevision:
        """Eligibility is an assessment axis, not content — it may
        move on any status, including accepted rows (the guard
        freezes content columns only)."""
        self.ctx.require(CAP_REVIEW_SCIENCE)
        _require_human(self.ctx)
        if eligibility not in CANDIDATE_ELIGIBILITY:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"eligibility must be one of {CANDIDATE_ELIGIBILITY}",
                field_path="input.eligibility",
            )
        cand = self._candidate(candidate_id)
        cand.eligibility = eligibility
        self.db.flush()
        return cand

    # ------------------------------------------------------ patches

    def propose_patch(
        self,
        *,
        candidate_id: uuid.UUID,
        patch: dict[str, Any],
        reason: str | None = None,
    ) -> CandidatePatch:
        """Propose a content patch — explicit and reviewable. Agents
        may propose; applying still requires human review."""
        self.ctx.require(CAP_PROPOSE_CANDIDATE)
        cand = self._candidate(candidate_id)
        if not patch:
            raise DomainError(
                ErrorCode.VALIDATION,
                "patch must not be empty",
                field_path="input.patch",
            )
        row = CandidatePatch(
            workspace_id=self.ctx.workspace_id,
            candidate_id=cand.id,
            status="proposed",
            patch={"ops": patch, "reason": reason} if reason else {"ops": patch},
            proposed_by=self.ctx.principal_kind,
        )
        self.db.add(row)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="candidate_revision",
            aggregate_id=cand.id,
            event_type="candidate.patch_proposed",
            payload={"candidateId": str(cand.id), "patchId": str(row.id)},
        )
        return row

    def review_patch(
        self,
        *,
        patch_id: uuid.UUID,
        accept: bool,
        rejection_reason: str | None = None,
    ) -> CandidatePatch:
        """Human review of a patch (AT-0204-2).

        Reject: patch marked rejected with the reason retained; the
        target candidate's content is *not* touched.
        Accept: a new draft CandidateRevision is created with the
        patched payload — the target row itself stays immutable.
        """
        self.ctx.require(CAP_REVIEW_SCIENCE)
        _require_human(self.ctx)
        patch = self._patch(patch_id)
        if patch.status != "proposed":
            raise DomainError(
                ErrorCode.VALIDATION,
                f"only a proposed patch can be reviewed ('{patch.status}')",
                field_path="input.patchId",
            )
        patch.reviewed_by = self.ctx.principal_id
        patch.reviewed_at = datetime.now(UTC)
        if not accept:
            if not (rejection_reason or "").strip():
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "a rejection reason is required",
                    field_path="input.rejectionReason",
                )
            patch.status = "rejected"
            patch.rejection_reason = rejection_reason
            self.db.flush()
            audit_record(
                self.db,
                self.ctx,
                action="candidate.patch.reject",
                target_type="candidate_patch",
                target_id=patch.id,
                detail={"reason": rejection_reason},
            )
            return patch
        # apply → new revision on the same candidate lineage
        cand = self._candidate(patch.candidate_id)
        ops = patch.patch.get("ops", patch.patch)
        new_payload = self._apply_ops(cand.payload, ops)
        current_max = self.db.execute(
            select(func.max(CandidateRevision.revision)).where(
                CandidateRevision.task_id == cand.task_id
            )
        ).scalar_one()
        new_rev = CandidateRevision(
            workspace_id=self.ctx.workspace_id,
            task_id=cand.task_id,
            revision=(current_max or 0) + 1,
            status="draft",
            eligibility="not_assessed",
            entity_kind=cand.entity_kind,
            entity_revision_id=cand.entity_revision_id,
            parent_revision_id=cand.id,
            contract_revision_id=cand.contract_revision_id,
            hypothesis=cand.hypothesis,
            payload=new_payload,
            content_hash=content_hash(
                {
                    **new_payload,
                    "entityKind": cand.entity_kind,
                    "entityRevisionId": str(cand.entity_revision_id or ""),
                    "hypothesis": cand.hypothesis or "",
                }
            ),
            created_by=self.ctx.principal_id,
        )
        self.db.add(new_rev)
        patch.status = "accepted"
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="candidate_revision",
            aggregate_id=cand.id,
            event_type="candidate.patch_applied",
            payload={
                "candidateId": str(cand.id),
                "patchId": str(patch.id),
                "newRevisionId": str(new_rev.id),
            },
        )
        audit_record(
            self.db,
            self.ctx,
            action="candidate.patch.apply",
            target_type="candidate_patch",
            target_id=patch.id,
            detail={"newRevisionId": str(new_rev.id)},
        )
        return patch

    # ----------------------------------------------------- internals

    def _candidate(self, candidate_id: uuid.UUID) -> CandidateRevision:
        row = self.db.execute(
            select(CandidateRevision).where(
                CandidateRevision.id == candidate_id,
                CandidateRevision.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("candidate")
        return row

    def _patch(self, patch_id: uuid.UUID) -> CandidatePatch:
        row = self.db.execute(
            select(CandidatePatch).where(
                CandidatePatch.id == patch_id,
                CandidatePatch.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("candidate patch")
        return row

    @staticmethod
    def _apply_ops(payload: dict[str, Any], ops: dict[str, Any]) -> dict[str, Any]:
        """Merge explicit, reviewable patch ops. ``ops`` maps payload
        keys to replacement values — no schema-driven magic, no
        silent inference."""
        merged = dict(payload)
        for key, value in ops.items():
            if key in {"payload", "status", "eligibility", "revision"}:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    f"patch may not overwrite '{key}'",
                    field_path=f"input.patch.{key}",
                )
            merged[key] = value
        return merged
