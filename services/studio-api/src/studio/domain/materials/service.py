"""Material, grade, lot and reference registry (§5, CS-0203).

Identities carry kind + sourced identifiers; a structure is only
usable by structure-required tools once its provenance is reviewed —
a proposed registry match never unblocks it. Commercial grades and
lots are distinct records even when they share a chemical identifier;
reconciliation is an explicit reviewed action. Reference products
record claimed vs measured properties separately and keep
`composition_knowledge` honest — an unknown composition has no
ingredient list at all.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from chem_studio_policy.capabilities import (
    CAP_MANAGE_SOURCES,
    CAP_READ_PROJECT,
    CAP_REVIEW_SCIENCE,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext
from studio.domain.materials.quantities import Quantity
from studio.errors import DomainError, ErrorCode, forbidden, not_found
from studio.events.outbox import publish
from studio.persistence.models import (
    COMPOSITION_KNOWLEDGE,
    CONFIDENTIALITY,
    MATERIAL_KINDS,
    IdentityMatch,
    MaterialGrade,
    MaterialIdentity,
    MaterialLot,
    ReferenceProduct,
    ReferenceProductRevision,
)
from studio.persistence.revisions import content_hash


class MaterialService:
    """Workspace-scoped materials-registry commands."""

    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    # ---------------------------------------------------------- reads

    def _identity(self, identity_id: uuid.UUID) -> MaterialIdentity:
        row = self.db.execute(
            select(MaterialIdentity).where(
                MaterialIdentity.id == identity_id,
                MaterialIdentity.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("material identity")
        return row

    def _grade(self, grade_id: uuid.UUID) -> MaterialGrade:
        row = self.db.execute(
            select(MaterialGrade).where(
                MaterialGrade.id == grade_id,
                MaterialGrade.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("material grade")
        return row

    def _product(self, product_id: uuid.UUID) -> ReferenceProduct:
        row = self.db.execute(
            select(ReferenceProduct).where(
                ReferenceProduct.id == product_id,
                ReferenceProduct.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("reference product")
        return row

    def require_structure(self, identity_id: uuid.UUID) -> str:
        """The gate structure-required tools call (AT-0203-3).

        Only a *reviewed* structure comes back. Missing, unreviewed
        (import/match-proposed) or unknown-identity structures raise
        MISSING_IDENTITY — the tool learns *that* identity data is
        missing, never a fabricated structure.
        """
        identity = self._identity(identity_id)
        if (
            not identity.structure
            or identity.structure_status != "reviewed"
            or identity.kind == "unknown"
        ):
            raise DomainError(
                ErrorCode.MISSING_IDENTITY,
                "structure-required tool input needs a reviewed identity "
                "structure; this identity's structure is missing or unreviewed",
                safe_details={
                    "identityId": str(identity.id),
                    "kind": identity.kind,
                    "structureStatus": identity.structure_status,
                },
            )
        return identity.structure

    # ------------------------------------------------------ identities

    def create_identity(
        self,
        *,
        kind: str,
        name: str,
        identifiers: list[dict[str, Any]] | None = None,
        structure: str | None = None,
        structure_format: str | None = None,
        aliases: list[dict[str, Any]] | None = None,
        confidentiality: str = "internal",
    ) -> MaterialIdentity:
        """Register an identity. A structure entered here is
        *unreviewed* — it cannot feed structure-required tools until
        ``review_structure`` (or an accepted match path) marks it."""
        self.ctx.require(CAP_MANAGE_SOURCES)
        if kind not in MATERIAL_KINDS:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"kind must be one of {', '.join(MATERIAL_KINDS)}",
                field_path="input.kind",
            )
        if not name.strip():
            raise DomainError(ErrorCode.VALIDATION, "name is required", field_path="input.name")
        if confidentiality not in CONFIDENTIALITY:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"confidentiality must be one of {', '.join(CONFIDENTIALITY)}",
                field_path="input.confidentiality",
            )
        for ident in identifiers or []:
            if not ident.get("scheme") or not ident.get("value"):
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "each identifier needs a scheme and a value",
                    field_path="input.identifiers",
                )
        status = "unreviewed" if structure else "none"
        row = MaterialIdentity(
            workspace_id=self.ctx.workspace_id,
            kind=kind,
            name=name.strip(),
            identifiers=identifiers or [],
            structure=structure,
            structure_format=structure_format if structure else None,
            structure_status=status,
            aliases=aliases or [],
            confidentiality=confidentiality,
        )
        self.db.add(row)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="material_identity",
            aggregate_id=row.id,
            event_type="material.identity_created",
            payload={"identityId": str(row.id), "kind": kind},
        )
        audit_record(
            self.db,
            self.ctx,
            action="material.identity.create",
            target_type="material_identity",
            target_id=row.id,
            detail={"kind": kind},
        )
        return row

    def review_structure(self, *, identity_id: uuid.UUID) -> MaterialIdentity:
        """Mark an identity's structure reviewed (human science review)
        — after this, structure-required tools may consume it."""
        if self.ctx.principal_kind != "user":
            raise forbidden("structure review (human review required)")
        self.ctx.require(CAP_REVIEW_SCIENCE)
        row = self._identity(identity_id)
        if not row.structure:
            raise DomainError(
                ErrorCode.MISSING_IDENTITY,
                "no structure to review",
                safe_details={"identityId": str(identity_id)},
            )
        row.structure_status = "reviewed"
        row.evidence_status = "reviewed"
        row.version += 1
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="material.identity.review_structure",
            target_type="material_identity",
            target_id=row.id,
        )
        return row

    # -------------------------------------------------------- matches

    def propose_match(
        self,
        *,
        source_identity_id: uuid.UUID,
        candidate_identity_id: uuid.UUID,
        confidence: Decimal | str | None = None,
        rationale: str | None = None,
        proposed_by: str = "user",
    ) -> IdentityMatch:
        """A registry match is always a *proposal* first — imports and
        agents may propose; only review accepts (§5)."""
        self.ctx.require(CAP_MANAGE_SOURCES)
        self._identity(source_identity_id)
        self._identity(candidate_identity_id)
        if source_identity_id == candidate_identity_id:
            raise DomainError(ErrorCode.VALIDATION, "an identity cannot match itself")
        row = IdentityMatch(
            workspace_id=self.ctx.workspace_id,
            source_identity_id=source_identity_id,
            candidate_identity_id=candidate_identity_id,
            status="proposed",
            confidence=Decimal(confidence) if confidence is not None else None,
            rationale=rationale,
            proposed_by=proposed_by,
        )
        self.db.add(row)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="material_identity",
            aggregate_id=source_identity_id,
            event_type="material.match_proposed",
            payload={
                "matchId": str(row.id),
                "sourceIdentityId": str(source_identity_id),
                "candidateIdentityId": str(candidate_identity_id),
            },
        )
        return row

    def review_match(
        self, *, match_id: uuid.UUID, decision: str, rationale: str | None = None
    ) -> IdentityMatch:
        """Accept or reject a proposed match — human science review
        only."""
        if self.ctx.principal_kind != "user":
            raise forbidden("identity-match review (human review required)")
        self.ctx.require(CAP_REVIEW_SCIENCE)
        row = self.db.execute(
            select(IdentityMatch).where(
                IdentityMatch.id == match_id,
                IdentityMatch.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("identity match")
        if decision not in ("accepted", "rejected"):
            raise DomainError(
                ErrorCode.VALIDATION,
                "decision must be accepted or rejected",
                field_path="input.decision",
            )
        if row.status != "proposed":
            raise DomainError(
                ErrorCode.VALIDATION,
                f"match is already '{row.status}'",
                field_path="input.matchId",
            )
        row.status = decision
        row.reviewed_by = self.ctx.principal_id
        row.reviewed_at = datetime.now(UTC)
        row.rationale = rationale or row.rationale
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="material_identity",
            aggregate_id=row.source_identity_id,
            event_type="material.match_reviewed",
            payload={"matchId": str(row.id), "decision": decision},
        )
        audit_record(
            self.db,
            self.ctx,
            action="material.match.review",
            target_type="identity_match",
            target_id=row.id,
            detail={"decision": decision},
        )
        return row

    # ------------------------------------------------- grades and lots

    def create_grade(
        self,
        *,
        material_id: uuid.UUID,
        supplier: str,
        grade_name: str,
        active_content: dict[str, Any] | None = None,
        specifications: dict[str, Any] | None = None,
    ) -> MaterialGrade:
        """Register a commercial grade. ``active_content`` is a
        Quantity DTO — its basis is validated, never assumed."""
        self.ctx.require(CAP_MANAGE_SOURCES)
        self._identity(material_id)
        if not supplier.strip() or not grade_name.strip():
            raise DomainError(
                ErrorCode.VALIDATION,
                "supplier and grade_name are required",
                field_path="input.gradeName",
            )
        if active_content is not None:
            # validates unit + required basis inside the DTO
            Quantity.from_dto(active_content)
        row = MaterialGrade(
            workspace_id=self.ctx.workspace_id,
            material_id=material_id,
            supplier=supplier.strip(),
            grade_name=grade_name.strip(),
            active_content=active_content,
            specifications=specifications or {},
        )
        self.db.add(row)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="material_grade",
            aggregate_id=row.id,
            event_type="material.grade_created",
            payload={"gradeId": str(row.id), "materialId": str(material_id)},
        )
        audit_record(
            self.db,
            self.ctx,
            action="material.grade.create",
            target_type="material_grade",
            target_id=row.id,
        )
        return row

    def find_shared_identifier_grades(self) -> list[dict[str, Any]]:
        """Dedup *report*: grades whose materials share an identifier
        scheme+value. Returns groups for human reconciliation —
        nothing is merged here (AT-0203-2)."""
        self.ctx.require(CAP_READ_PROJECT)
        rows = self.db.execute(
            select(MaterialGrade, MaterialIdentity)
            .join(
                MaterialIdentity,
                (MaterialIdentity.id == MaterialGrade.material_id)
                & (MaterialIdentity.workspace_id == self.ctx.workspace_id),
            )
            .where(MaterialGrade.workspace_id == self.ctx.workspace_id)
        ).all()
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for grade, identity in rows:
            for ident in identity.identifiers or []:
                key = (str(ident.get("scheme")), str(ident.get("value")))
                groups.setdefault(key, []).append(
                    {
                        "gradeId": str(grade.id),
                        "gradeName": grade.grade_name,
                        "supplier": grade.supplier,
                        "materialId": str(identity.id),
                        "materialName": identity.name,
                        "reconciled": grade.reconciled_into is not None,
                    }
                )
        return [
            {
                "scheme": scheme,
                "value": value,
                "grades": members,
                # unresolved while more than one live (unmerged) grade
                # remains — a reconcile target legitimately stays distinct
                "unresolved": sum(1 for m in members if not m["reconciled"]) > 1,
            }
            for (scheme, value), members in groups.items()
            if len(members) > 1
        ]

    def reconcile_grades(
        self, *, keep_grade_id: uuid.UUID, merge_grade_id: uuid.UUID, reason: str
    ) -> MaterialGrade:
        """The *only* merge path: an explicit reviewed reconciliation
        that records where the merged grade now points."""
        if self.ctx.principal_kind != "user":
            raise forbidden("grade reconciliation (human review required)")
        self.ctx.require(CAP_REVIEW_SCIENCE)
        if not reason:
            raise DomainError(
                ErrorCode.VALIDATION,
                "reconciliation requires a reason",
                field_path="input.reason",
            )
        keep = self._grade(keep_grade_id)
        merge = self._grade(merge_grade_id)
        merge.reconciled_into = keep.id
        merge.version += 1
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="material.grade.reconcile",
            target_type="material_grade",
            target_id=merge.id,
            detail={"into": str(keep.id), "reason": reason},
        )
        return merge

    def create_lot(
        self,
        *,
        grade_id: uuid.UUID,
        lot_number: str | None = None,
        received_at: datetime | None = None,
        expires_at: datetime | None = None,
        certificate_artifact_ids: list[str] | None = None,
        notes: str | None = None,
    ) -> MaterialLot:
        self.ctx.require(CAP_MANAGE_SOURCES)
        self._grade(grade_id)
        row = MaterialLot(
            workspace_id=self.ctx.workspace_id,
            grade_id=grade_id,
            lot_number=lot_number,
            received_at=received_at,
            expires_at=expires_at,
            certificate_artifact_ids=certificate_artifact_ids or [],
            notes=notes,
        )
        self.db.add(row)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="material.lot.create",
            target_type="material_lot",
            target_id=row.id,
        )
        return row

    # ------------------------------------------------ reference products

    def create_reference_product(
        self,
        *,
        name: str,
        supplier: str | None = None,
        category: str | None = None,
        composition_knowledge: str = "unknown",
        aliases: list[dict[str, Any]] | None = None,
        documentation_artifact_ids: list[str] | None = None,
    ) -> ReferenceProduct:
        self.ctx.require(CAP_MANAGE_SOURCES)
        if composition_knowledge not in COMPOSITION_KNOWLEDGE:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"composition_knowledge must be one of {', '.join(COMPOSITION_KNOWLEDGE)}",
                field_path="input.compositionKnowledge",
            )
        if not name.strip():
            raise DomainError(ErrorCode.VALIDATION, "name is required", field_path="input.name")
        row = ReferenceProduct(
            workspace_id=self.ctx.workspace_id,
            name=name.strip(),
            supplier=supplier,
            category=category,
            composition_knowledge=composition_knowledge,
            aliases=aliases or [],
            documentation_artifact_ids=documentation_artifact_ids or [],
        )
        self.db.add(row)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="reference_product",
            aggregate_id=row.id,
            event_type="material.reference_created",
            payload={"productId": str(row.id)},
        )
        audit_record(
            self.db,
            self.ctx,
            action="material.reference.create",
            target_type="reference_product",
            target_id=row.id,
        )
        return row

    def draft_reference_revision(
        self, *, product_id: uuid.UUID, payload: dict[str, Any]
    ) -> ReferenceProductRevision:
        """New content revision. When composition is unknown the
        payload must not carry an ingredient list — a purchased
        product with no recipe has *no* composition (AT-0203-1)."""
        self.ctx.require(CAP_MANAGE_SOURCES)
        product = self._product(product_id)
        knowledge = payload.get("compositionKnowledge", product.composition_knowledge)
        composition = payload.get("composition")
        if knowledge == "unknown" and composition:
            raise DomainError(
                ErrorCode.VALIDATION,
                "compositionKnowledge is 'unknown' — an ingredient list "
                "cannot be recorded; leave composition empty",
                field_path="input.payload.composition",
            )
        current_max = self.db.execute(
            select(func.max(ReferenceProductRevision.revision)).where(
                ReferenceProductRevision.product_id == product.id
            )
        ).scalar_one()
        row = ReferenceProductRevision(
            workspace_id=self.ctx.workspace_id,
            product_id=product.id,
            revision=(current_max or 0) + 1,
            status="draft",
            payload=payload,
            content_hash=content_hash(payload),
            created_by=self.ctx.principal_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def freeze_reference_revision(self, *, revision_id: uuid.UUID) -> ReferenceProductRevision:
        """Freeze a draft revision: becomes the product's current
        revision; any prior frozen revision supersedes (the DB
        trigger's only legal transition)."""
        self.ctx.require(CAP_MANAGE_SOURCES)
        rev = self.db.execute(
            select(ReferenceProductRevision).where(
                ReferenceProductRevision.id == revision_id,
                ReferenceProductRevision.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if rev is None:
            raise not_found("reference product revision")
        product = self._product(rev.product_id)
        if rev.status != "draft":
            raise DomainError(
                ErrorCode.VALIDATION,
                f"only a draft revision can be frozen (status is '{rev.status}')",
                field_path="input.revisionId",
            )
        prior = self.db.execute(
            select(ReferenceProductRevision).where(
                ReferenceProductRevision.product_id == product.id,
                ReferenceProductRevision.status == "frozen",
            )
        ).scalar_one_or_none()
        if prior is not None:
            prior.status = "superseded"
            self.db.flush()
        rev.status = "frozen"
        self.db.flush()
        product.current_revision_id = rev.id
        product.composition_knowledge = rev.payload.get(
            "compositionKnowledge", product.composition_knowledge
        )
        product.version += 1
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="material.reference.freeze",
            target_type="reference_product_revision",
            target_id=rev.id,
            detail={"revision": rev.revision},
        )
        return rev

    def reference_composition(self, *, product_id: uuid.UUID) -> dict[str, Any] | None:
        """The composition a caller may rely on — ``None`` when the
        product's composition is unknown (no invented list)."""
        self.ctx.require(CAP_READ_PROJECT)
        product = self._product(product_id)
        if product.composition_knowledge == "unknown" or product.current_revision_id is None:
            return None
        rev = self.db.get(ReferenceProductRevision, product.current_revision_id)
        if rev is None:
            return None
        return rev.payload.get("composition")
