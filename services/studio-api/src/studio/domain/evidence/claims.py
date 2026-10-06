"""Evidence claims with provenance (§10, CS-0302).

Three distinct kinds stay distinct: ``document_claim`` (parsed from
a source), ``inferred_suggestion`` (tool output), ``measured_outcome``
(lab result). Extraction review promotes an ``ExtractedRecord`` to a
proposed claim carrying the source locator + original text; science
review accepts or rejects the claim itself. Contradiction links keep
both sides visible — linking never demotes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from chem_studio_policy.capabilities import CAP_MANAGE_SOURCES, CAP_REVIEW_SCIENCE
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext
from studio.domain.evidence.imports import ImportService
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import (
    CLAIM_KINDS,
    CLAIM_RELATIONS,
    CLAIM_STATUSES,
    ClaimLink,
    EvidenceClaim,
)
from studio.persistence.scrub import pg_clean


class ClaimService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------- lookups

    def get(self, ctx: ServiceContext, claim_id: uuid.UUID) -> EvidenceClaim:
        row = self.db.execute(
            select(EvidenceClaim).where(
                EvidenceClaim.id == claim_id,
                EvidenceClaim.workspace_id == ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("evidence claim")
        return row

    def claims(
        self,
        ctx: ServiceContext,
        *,
        kind: str | None = None,
        status: str | None = None,
    ) -> list[EvidenceClaim]:
        stmt = select(EvidenceClaim).where(EvidenceClaim.workspace_id == ctx.workspace_id)
        if kind is not None:
            if kind not in CLAIM_KINDS:
                raise DomainError(ErrorCode.VALIDATION, f"unknown claim kind {kind}")
            stmt = stmt.where(EvidenceClaim.kind == kind)
        if status is not None:
            if status not in CLAIM_STATUSES:
                raise DomainError(ErrorCode.VALIDATION, f"unknown claim status {status}")
            stmt = stmt.where(EvidenceClaim.status == status)
        return list(self.db.execute(stmt.order_by(EvidenceClaim.created_at)).scalars())

    def links_for(self, ctx: ServiceContext, claim_id: uuid.UUID) -> list[ClaimLink]:
        claim = self.get(ctx, claim_id)
        return list(
            self.db.execute(
                select(ClaimLink).where(
                    ClaimLink.workspace_id == ctx.workspace_id,
                    or_(
                        ClaimLink.from_claim_id == claim.id,
                        ClaimLink.to_claim_id == claim.id,
                    ),
                )
            ).scalars()
        )

    # ------------------------------------------------------- create

    def promote_record(
        self,
        ctx: ServiceContext,
        record_id: uuid.UUID,
        *,
        subject: dict[str, Any],
        statement: dict[str, Any],
        conditions: dict[str, Any] | None = None,
    ) -> EvidenceClaim:
        """Extraction review: propose an evidence claim from an
        extracted record. The record is marked accepted (field-level
        acceptance); the *claim* still starts ``proposed`` — ambiguity
        is never auto-accepted (AT-0302-1)."""
        ctx.require(CAP_MANAGE_SOURCES)
        importer = ImportService(self.db, vault=None)  # lookups only
        record = importer.get_record(ctx, record_id)
        if record.status == "rejected":
            raise DomainError(ErrorCode.CONFLICT, "a rejected record cannot be promoted")
        if record.status == "proposed":
            record.status = "accepted"
            record.reviewed_by = ctx.principal_id
            record.reviewed_at = datetime.now(tz=UTC)
        claim = EvidenceClaim(
            workspace_id=ctx.workspace_id,
            kind="document_claim",
            status="proposed",
            subject=pg_clean(subject)[0],
            statement=pg_clean(statement)[0],
            locator=record.locator,
            original_text=record.original_text,
            conditions=pg_clean(conditions)[0],
            source_batch_id=record.batch_id,
            source_record_id=record.id,
            created_by=ctx.principal_id,
        )
        self.db.add(claim)
        self.db.flush()
        return claim

    def create_claim(
        self,
        ctx: ServiceContext,
        *,
        kind: str,
        subject: dict[str, Any],
        statement: dict[str, Any],
        locator: dict[str, Any] | None = None,
        original_text: str | None = None,
        conditions: dict[str, Any] | None = None,
    ) -> EvidenceClaim:
        """Non-record claims — inferred suggestions and measured
        outcomes enter proposed and carry their own provenance."""
        ctx.require(CAP_MANAGE_SOURCES)
        if kind not in CLAIM_KINDS:
            raise DomainError(ErrorCode.VALIDATION, f"unknown claim kind {kind}")
        # pg_clean at the persistence boundary — a NUL byte in any
        # caller-supplied text would otherwise crash the INSERT as a
        # raw driver error rather than a clean record (CS-1101).
        claim = EvidenceClaim(
            workspace_id=ctx.workspace_id,
            kind=kind,
            status="proposed",
            subject=pg_clean(subject)[0],
            statement=pg_clean(statement)[0],
            locator=pg_clean(locator)[0],
            original_text=pg_clean(original_text)[0],
            conditions=pg_clean(conditions)[0],
            created_by=ctx.principal_id,
        )
        self.db.add(claim)
        self.db.flush()
        return claim

    # ------------------------------------------------------- review

    def review(self, ctx: ServiceContext, claim_id: uuid.UUID, decision: str) -> EvidenceClaim:
        """Science review accepts or rejects a proposed claim — a
        human judgment, so agent principals are blocked."""
        ctx.require(CAP_REVIEW_SCIENCE)
        if ctx.principal_kind != "user":
            raise DomainError(ErrorCode.FORBIDDEN, "evidence review requires a human principal")
        if decision not in ("accepted", "rejected"):
            raise DomainError(ErrorCode.VALIDATION, "decision must be accepted|rejected")
        claim = self.get(ctx, claim_id)
        if claim.status != "proposed":
            raise DomainError(ErrorCode.CONFLICT, f"claim already {claim.status}")
        claim.status = decision
        claim.reviewed_by = ctx.principal_id
        claim.reviewed_at = datetime.now(tz=UTC)
        self.db.flush()
        return claim

    # ------------------------------------------------------- links

    def link(
        self,
        ctx: ServiceContext,
        from_claim_id: uuid.UUID,
        to_claim_id: uuid.UUID,
        relation: str,
        *,
        note: str | None = None,
    ) -> ClaimLink:
        """Record support or contradiction between two claims. A
        contradiction keeps both claims fully visible — neither is
        demoted or hidden (AT-0302-2)."""
        ctx.require(CAP_REVIEW_SCIENCE)
        if relation not in CLAIM_RELATIONS:
            raise DomainError(ErrorCode.VALIDATION, f"relation must be one of {CLAIM_RELATIONS}")
        src = self.get(ctx, from_claim_id)
        dst = self.get(ctx, to_claim_id)
        existing = self.db.execute(
            select(ClaimLink).where(
                ClaimLink.workspace_id == ctx.workspace_id,
                ClaimLink.from_claim_id == src.id,
                ClaimLink.to_claim_id == dst.id,
                ClaimLink.relation == relation,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing  # linking is idempotent
        edge = ClaimLink(
            workspace_id=ctx.workspace_id,
            from_claim_id=src.id,
            to_claim_id=dst.id,
            relation=relation,
            note=note,
            created_by=ctx.principal_id,
        )
        self.db.add(edge)
        self.db.flush()
        return edge
