"""Source revocation, supersession propagation, and lineage impact
reporting (§9.4, §17.5, CS-0305).

Revoking a source propagates honestly:

- the artifact's ``review_state`` becomes ``revoked``;
- its retrieval chunks leave the index (the index version changes,
  so cached results can never serve the revoked content again);
- extracted records from its batches are rejected with a
  ``source_revoked`` flag preserving *why*;
- evidence claims drawn from those batches become ``superseded`` —
  they stay queryable with provenance, never silently deleted;
- downstream artifacts (``source_artifact_ids`` lineage) are marked
  ``retention.lineage_review = "required"`` — reuse is suspended
  until a human re-reviews, per §17.5.

Nothing here claims unlearning: a revoked training source does not
mean a model forgot it. The persisted ``SourceRevocation.report``
names what was marked affected and who was exposed; dataset and
model-release lists are honest empty until those registries exist.
"""

from __future__ import annotations

import uuid
from typing import Any

from chem_studio_policy.capabilities import CAP_MANAGE_SOURCES, CAP_READ_PROJECT
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext
from studio.domain.evidence.retrieval import RetrievalService
from studio.errors import DomainError, ErrorCode, not_found
from studio.events.outbox import publish
from studio.persistence.models import (
    Artifact,
    EvidenceClaim,
    ExtractedRecord,
    ImportBatch,
    RetrievalManifest,
    SourceChunk,
    SourceRevocation,
)


class RevocationService:
    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    def _artifact(self, artifact_id: uuid.UUID) -> Artifact:
        row = self.db.execute(
            select(Artifact).where(
                Artifact.id == artifact_id,
                Artifact.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("artifact")
        return row

    # --------------------------------------------------- impact scan

    def impact(self, ctx: ServiceContext, artifact_id: uuid.UUID) -> dict[str, Any]:
        """Read-only impact preview for a source (§17.5): chunks that
        would leave the index, records/claims affected, derived
        artifacts downstream, and the principals past retrieval
        manifests exposed the chunks to."""
        ctx.require(CAP_READ_PROJECT)
        artifact = self._artifact(artifact_id)
        return self._scan(artifact)

    def _scan(self, artifact: Artifact) -> dict[str, Any]:
        ws = self.ctx.workspace_id
        chunks = self.db.execute(
            select(SourceChunk).where(
                SourceChunk.workspace_id == ws,
                SourceChunk.artifact_id == artifact.id,
            )
        ).scalars()
        chunk_ids = [str(c.id) for c in chunks if c.status == "active"]

        batches = list(
            self.db.execute(
                select(ImportBatch).where(
                    ImportBatch.workspace_id == ws,
                    ImportBatch.artifact_id == artifact.id,
                )
            ).scalars()
        )
        batch_ids = [b.id for b in batches]
        records_affected = 0
        if batch_ids:
            records_affected = len(
                self.db.execute(
                    select(ExtractedRecord).where(
                        ExtractedRecord.workspace_id == ws,
                        ExtractedRecord.batch_id.in_(batch_ids),
                        ExtractedRecord.status != "rejected",
                    )
                )
                .scalars()
                .all()
            )
            claims = list(
                self.db.execute(
                    select(EvidenceClaim).where(
                        EvidenceClaim.workspace_id == ws,
                        EvidenceClaim.source_batch_id.in_(batch_ids),
                        EvidenceClaim.status.in_(["proposed", "accepted"]),
                    )
                ).scalars()
            )
        else:
            claims = []

        # downstream lineage (BFS over source_artifact_ids)
        affected_derived: list[str] = []
        frontier = {str(artifact.id)}
        seen = set(frontier)
        all_artifacts = list(
            self.db.execute(select(Artifact).where(Artifact.workspace_id == ws)).scalars()
        )
        while frontier:
            next_ids = {
                str(a.id) for a in all_artifacts if frontier & set(a.source_artifact_ids or [])
            } - seen
            affected_derived.extend(sorted(next_ids))
            seen |= next_ids
            frontier = next_ids

        # exposure audit: which manifests already served these chunks
        exposed_manifest_ids: list[str] = []
        exposed_principals: set[str] = set()
        if chunk_ids:
            for m in self.db.execute(
                select(RetrievalManifest).where(RetrievalManifest.workspace_id == ws)
            ).scalars():
                if set(m.chunk_ids or []) & set(chunk_ids):
                    exposed_manifest_ids.append(str(m.id))
                    exposed_principals.add(str(m.principal_id))

        return {
            "artifactId": str(artifact.id),
            "chunksRevoked": len(chunk_ids),
            "batchIds": [str(b.id) for b in batches],
            "recordsRejected": records_affected,
            "claimsSuperseded": [str(c.id) for c in claims],
            "affectedDerivedIds": affected_derived,
            "exposedManifestIds": exposed_manifest_ids,
            "exposedPrincipalIds": sorted(exposed_principals),
            # §17.5 — honest until those registries exist
            "affectedDatasetIds": [],
            "affectedModelReleaseIds": [],
            "unlearningGuarantee": False,
        }

    # ----------------------------------------------------- revocation

    def revoke(
        self, ctx: ServiceContext, artifact_id: uuid.UUID, *, reason: str
    ) -> SourceRevocation:
        """Revoke a source and propagate the supersession. A human
        stewardship act — revocation rewrites review state, it is not
        an agent shortcut."""
        ctx.require(CAP_MANAGE_SOURCES)
        if ctx.principal_kind != "user":
            raise DomainError(
                ErrorCode.FORBIDDEN,
                "source revocation requires a human principal",
            )
        if not (reason or "").strip():
            raise DomainError(
                ErrorCode.VALIDATION,
                "a revocation reason is required",
                field_path="input.reason",
            )
        artifact = self._artifact(artifact_id)
        if artifact.review_state == "revoked":
            raise DomainError(
                ErrorCode.CONFLICT,
                "artifact is already revoked",
                field_path="input.artifactId",
            )
        prior = self.db.execute(
            select(SourceRevocation).where(
                SourceRevocation.workspace_id == self.ctx.workspace_id,
                SourceRevocation.artifact_id == artifact.id,
            )
        ).scalar_one_or_none()
        if prior is not None:
            raise DomainError(
                ErrorCode.CONFLICT,
                "artifact already has a revocation record",
                field_path="input.artifactId",
            )

        report = self._scan(artifact)

        artifact.review_state = "revoked"
        revoked_chunks = RetrievalService(self.db).revoke_artifact(ctx, artifact.id)

        batch_ids = [uuid.UUID(b) for b in report["batchIds"]]
        if batch_ids:
            for rec in self.db.execute(
                select(ExtractedRecord).where(
                    ExtractedRecord.workspace_id == self.ctx.workspace_id,
                    ExtractedRecord.batch_id.in_(batch_ids),
                    ExtractedRecord.status != "rejected",
                )
            ).scalars():
                rec.status = "rejected"
                rec.flags = [*rec.flags, "source_revoked"]
            for claim in self.db.execute(
                select(EvidenceClaim).where(
                    EvidenceClaim.workspace_id == self.ctx.workspace_id,
                    EvidenceClaim.source_batch_id.in_(batch_ids),
                    EvidenceClaim.status.in_(["proposed", "accepted"]),
                )
            ).scalars():
                claim.status = "superseded"

        for derived_id in report["affectedDerivedIds"]:
            derived = self.db.get(Artifact, uuid.UUID(derived_id))
            if derived is None:
                continue
            derived.retention = {
                **(derived.retention or {}),
                "lineage_review": "required",
                "lineage_affected_by": str(artifact.id),
            }

        report["chunksRevoked"] = revoked_chunks
        row = SourceRevocation(
            workspace_id=self.ctx.workspace_id,
            artifact_id=artifact.id,
            reason=reason.strip(),
            revoked_by=self.ctx.principal_id,
            report=report,
        )
        self.db.add(row)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="artifact",
            aggregate_id=artifact.id,
            event_type="source.revoked",
            payload={
                "artifactId": str(artifact.id),
                "revocationId": str(row.id),
                "chunksRevoked": revoked_chunks,
            },
        )
        audit_record(
            self.db,
            self.ctx,
            action="source.revoke",
            target_type="artifact",
            target_id=artifact.id,
            detail={"reason": row.reason, "report": report},
        )
        return row

    def revocations(
        self, ctx: ServiceContext, artifact_id: uuid.UUID | None = None
    ) -> list[SourceRevocation]:
        ctx.require(CAP_READ_PROJECT)
        stmt = select(SourceRevocation).where(
            SourceRevocation.workspace_id == self.ctx.workspace_id
        )
        if artifact_id is not None:
            self._artifact(artifact_id)  # 404 on foreign/absent
            stmt = stmt.where(SourceRevocation.artifact_id == artifact_id)
        return list(self.db.execute(stmt.order_by(SourceRevocation.created_at)).scalars())
