"""Quarantined document/table ingestion (§9, CS-0301).

Flow: authorize → dedup on (scope, checksum, parser_version) → read
bytes from the private vault → inspect + parse behind the worker's
subprocess boundary → persist a batch of *proposed* records. Nothing
here accepts values into production state — review does that, per
record, under ``manage_sources``.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from chem_studio_policy.capabilities import CAP_MANAGE_SOURCES
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from workers.ingestion.limits import IngestionLimits
from workers.ingestion.quarantine import detect_type
from workers.ingestion.runner import run_parse
from workers.ingestion.types import PARSER_VERSION, QuarantineError

from studio.auth.context import ServiceContext
from studio.domain.evidence.vault import Vault
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import (
    Artifact,
    EvidenceClaim,
    ExtractedRecord,
    ImportBatch,
)
from studio.persistence.scrub import pg_clean


class ImportService:
    def __init__(
        self,
        db: Session,
        vault: Vault | None,
        *,
        limits: IngestionLimits | None = None,
        isolate: bool = True,
    ) -> None:
        self.db = db
        self.vault = vault
        self.limits = limits or IngestionLimits()
        self.isolate = isolate

    # ------------------------------------------------------- lookups

    def get_batch(self, ctx: ServiceContext, batch_id: uuid.UUID) -> ImportBatch:
        row = self.db.execute(
            select(ImportBatch).where(
                ImportBatch.id == batch_id,
                ImportBatch.workspace_id == ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("import batch")
        return row

    def get_record(self, ctx: ServiceContext, record_id: uuid.UUID) -> ExtractedRecord:
        row = self.db.execute(
            select(ExtractedRecord).where(
                ExtractedRecord.id == record_id,
                ExtractedRecord.workspace_id == ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("extracted record")
        return row

    def records(self, ctx: ServiceContext, batch_id: uuid.UUID) -> list[ExtractedRecord]:
        batch = self.get_batch(ctx, batch_id)
        return list(
            self.db.execute(
                select(ExtractedRecord).where(
                    ExtractedRecord.workspace_id == ctx.workspace_id,
                    ExtractedRecord.batch_id == batch.id,
                )
            ).scalars()
        )

    # ------------------------------------------------------- import

    def import_artifact(
        self, ctx: ServiceContext, artifact_id: uuid.UUID
    ) -> tuple[ImportBatch, bool]:
        """Run the quarantine pipeline over a committed artifact.
        Returns ``(batch, deduplicated)`` — a repeat import of the same
        bytes with the same parser returns the existing batch without
        duplicating records (AT-0301-3)."""
        artifact = self.db.execute(
            select(Artifact).where(
                Artifact.id == artifact_id,
                Artifact.workspace_id == ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if artifact is None:
            raise not_found("artifact")
        ctx.require(CAP_MANAGE_SOURCES, artifact.access_scope)
        if artifact.upload_state != "committed":
            raise DomainError(
                ErrorCode.CONFLICT,
                f"artifact is {artifact.upload_state} — only committed artifacts can be parsed",
            )
        if artifact.review_state == "revoked":
            raise DomainError(
                ErrorCode.CONFLICT,
                "artifact is revoked — a revoked source cannot re-enter the pipeline",
            )
        rights = artifact.rights or {}
        if rights.get("extraction") == "denied":
            raise DomainError(
                ErrorCode.FORBIDDEN,
                "extraction right is denied for this artifact",
            )

        checksum = artifact.checksum_sha256 or self._checksum(ctx, artifact)
        existing = self.db.execute(
            select(ImportBatch).where(
                ImportBatch.workspace_id == ctx.workspace_id,
                ImportBatch.checksum_sha256 == checksum,
                ImportBatch.parser_version == PARSER_VERSION,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, True

        if self.vault is None:
            raise DomainError(ErrorCode.CONFLICT, "no vault configured for byte reads")
        blob = self.vault.open_blob(ctx.workspace_id, artifact.storage_key)
        with blob:
            data = blob.read()

        findings: list[dict[str, str]] = []
        if rights.get("extraction", "unknown") in ("unknown", None):
            findings.append(
                {
                    "code": "RIGHTS_UNKNOWN",
                    "detail": "extraction right is undecided — records stay quarantined for review",
                }
            )
        detected = detect_type(data, artifact.original_name)
        try:
            report = run_parse(
                data,
                artifact.original_name,
                limits=self.limits,
                isolate=self.isolate,
            )
        except QuarantineError as exc:
            # Typed denial is still recorded — auditable, no records.
            batch = self._new_batch(ctx, artifact, checksum, "quarantined")
            batch.detected_type = detected
            batch.findings = [*findings, {"code": exc.code, "detail": exc.message}]
            self.db.add(batch)
            self.db.flush()
            return batch, False

        findings += report.findings
        status = "parsed" if report.records else "quarantined"
        batch = self._new_batch(ctx, artifact, checksum, status)
        batch.detected_type = detected
        batch.parser_name = report.parser_name
        batch.findings = findings
        batch.record_count = len(report.records)
        self.db.add(batch)
        self.db.flush()
        for rec in report.records:
            # Postgres text/jsonb refuse NUL — scrub at the persistence
            # boundary and flag the record honestly rather than crash
            # the INSERT as a raw driver error (CS-1101).
            locator, s1 = pg_clean(rec.locator)
            text, s2 = pg_clean(rec.original_text)
            payload, s3 = pg_clean(rec.value)
            flags = list(rec.flags or [])
            if s1 or s2 or s3:
                flags = [*flags, "nul_scrubbed"]
            self.db.add(
                ExtractedRecord(
                    workspace_id=ctx.workspace_id,
                    batch_id=batch.id,
                    kind=rec.kind,
                    locator=locator,
                    original_text=text,
                    payload=payload,
                    flags=flags,
                    confidence=rec.confidence,
                )
            )
        artifact.parser_version = PARSER_VERSION
        self.db.flush()
        return batch, False

    def _new_batch(
        self, ctx: ServiceContext, artifact: Artifact, checksum: str, status: str
    ) -> ImportBatch:
        # Same logical document (by name) → same group, next revision;
        # new name → new group, revision 1.
        group_row = self.db.execute(
            select(ImportBatch.document_group, func.max(ImportBatch.source_revision))
            .where(
                ImportBatch.workspace_id == ctx.workspace_id,
                ImportBatch.original_name == artifact.original_name,
            )
            .group_by(ImportBatch.document_group)
            .order_by(func.max(ImportBatch.source_revision).desc())
        ).first()
        group, revision = (
            (group_row[0], int(group_row[1]) + 1) if group_row is not None else (uuid.uuid4(), 1)
        )
        return ImportBatch(
            workspace_id=ctx.workspace_id,
            artifact_id=artifact.id,
            checksum_sha256=checksum,
            original_name=pg_clean(artifact.original_name)[0],
            detected_type="unknown",  # caller sets the inspected type
            parser_name="quarantine",
            parser_version=PARSER_VERSION,
            document_group=group,
            source_revision=revision,
            status=status,
            created_by=ctx.principal_id,
        )

    def _checksum(self, ctx: ServiceContext, artifact: Artifact) -> str:
        if self.vault is None:
            raise DomainError(ErrorCode.CONFLICT, "no vault configured for byte reads")
        blob = self.vault.open_blob(ctx.workspace_id, artifact.storage_key)
        with blob:
            digest = hashlib.sha256()
            for chunk in iter(lambda: blob.read(1024 * 1024), b""):
                digest.update(chunk)
        artifact.checksum_sha256 = digest.hexdigest()
        self.db.flush()
        return artifact.checksum_sha256

    # ------------------------------------------------------- review

    def review_record(
        self,
        ctx: ServiceContext,
        record_id: uuid.UUID,
        decision: str,
    ) -> ExtractedRecord:
        """Accept or reject a proposed record — a human review step,
        never automatic (§9.2)."""
        ctx.require(CAP_MANAGE_SOURCES)
        if ctx.principal_kind != "user":
            raise DomainError(
                ErrorCode.FORBIDDEN,
                "import review requires a human principal",
            )
        if decision not in ("accepted", "rejected"):
            raise DomainError(ErrorCode.VALIDATION, "decision must be accepted|rejected")
        record = self.get_record(ctx, record_id)
        if record.status != "proposed":
            raise DomainError(ErrorCode.CONFLICT, f"record already {record.status}")
        record.status = decision
        record.reviewed_by = ctx.principal_id
        record.reviewed_at = datetime.now(tz=UTC)
        self.db.flush()
        return record

    # -------------------------------------------------- data quality

    def quality_report(self, ctx: ServiceContext) -> dict[str, Any]:
        """Ingestion data-quality rollup (§9.3): received, parsed,
        quarantined, accepted/rejected, ambiguous values, missing
        units, rights-unknown, and duplicates."""
        ctx.require(CAP_MANAGE_SOURCES)
        ws = ctx.workspace_id
        batches = self.db.execute(
            select(ImportBatch.status, func.count())
            .where(ImportBatch.workspace_id == ws)
            .group_by(ImportBatch.status)
        ).all()
        by_status = {s: c for s, c in batches}
        records = self.db.execute(
            select(ExtractedRecord.status, func.count())
            .where(ExtractedRecord.workspace_id == ws)
            .group_by(ExtractedRecord.status)
        ).all()
        rec_status = {s: c for s, c in records}
        flagged = self.db.execute(
            select(ExtractedRecord.flags).where(ExtractedRecord.workspace_id == ws)
        ).scalars()
        flag_counts: dict[str, int] = {}
        for flags in flagged:
            for f in flags or []:
                flag_counts[f] = flag_counts.get(f, 0) + 1
        rights_unknown = self.db.execute(
            select(func.count()).where(
                Artifact.workspace_id == ws,
                Artifact.rights["extraction"].astext == "unknown",
            )
        ).scalar_one()
        return {
            "received": sum(by_status.values()),
            "parsed": by_status.get("parsed", 0),
            "quarantined": by_status.get("quarantined", 0),
            "failed": by_status.get("failed", 0),
            "records_proposed": rec_status.get("proposed", 0),
            "records_accepted": rec_status.get("accepted", 0),
            "records_rejected": rec_status.get("rejected", 0),
            "flags": flag_counts,
            "missing_units": flag_counts.get("unit_unresolved", 0),
            "ambiguous_percent": flag_counts.get("percent_literal_ambiguous", 0)
            + flag_counts.get("percent_format_ambiguous", 0),
            "rights_unknown_artifacts": rights_unknown,
            "training_excluded": self.db.execute(
                select(func.count()).where(
                    Artifact.workspace_id == ws,
                    Artifact.rights["training"].astext != "allowed",
                )
            ).scalar_one(),
            "duplicates": self._duplicate_batches(ws),
            "coverage": self._coverage(ws),
            "outcomes": self._outcomes(ws),
        }

    def batch_quality_report(self, ctx: ServiceContext, batch_id: uuid.UUID) -> dict[str, Any]:
        """Per-batch §9.3 report: record status counts, flag taxonomy,
        coverage + outcome categories scoped to one import."""
        ctx.require(CAP_MANAGE_SOURCES)
        ws = ctx.workspace_id
        batch = self.db.execute(
            select(ImportBatch).where(
                ImportBatch.id == batch_id,
                ImportBatch.workspace_id == ws,
            )
        ).scalar_one_or_none()
        if batch is None:
            raise not_found("import batch")
        records = list(
            self.db.execute(
                select(ExtractedRecord).where(
                    ExtractedRecord.workspace_id == ws,
                    ExtractedRecord.batch_id == batch.id,
                )
            ).scalars()
        )
        by_status: dict[str, int] = {}
        flag_counts: dict[str, int] = {}
        for r in records:
            by_status[r.status] = by_status.get(r.status, 0) + 1
            for f in r.flags or []:
                flag_counts[f] = flag_counts.get(f, 0) + 1
        return {
            "batchId": str(batch.id),
            "artifactId": str(batch.artifact_id),
            "originalName": batch.original_name,
            "status": batch.status,
            "received": len(records),
            "quarantined": by_status.get("proposed", 0),
            "accepted": by_status.get("accepted", 0),
            "rejected": by_status.get("rejected", 0),
            "flags": flag_counts,
            "ambiguous_identities": flag_counts.get("identity_unresolved", 0),
            "missing_units": flag_counts.get("unit_unresolved", 0),
            "unknown_bases": flag_counts.get("basis_unknown", 0),
            "untrusted_formulas": flag_counts.get("untrusted_formula", 0),
            "missing_raw": flag_counts.get("missing_cached_value", 0),
            "coverage": self._coverage(ws, batch_id=batch.id),
            "outcomes": self._outcomes(ws, batch_id=batch.id),
            "findings": batch.findings,
        }

    # ------------------------------------------- report components

    def _duplicate_batches(self, ws: uuid.UUID) -> int:
        """Batches superseded by a later revision of the same document
        group — deduplicated rather than double-counted."""
        groups = self.db.execute(
            select(ImportBatch.document_group, func.max(ImportBatch.source_revision))
            .where(ImportBatch.workspace_id == ws)
            .group_by(ImportBatch.document_group)
            .having(func.count() > 1)
        ).all()
        if not groups:
            return 0
        n = 0
        for group, max_rev in groups:
            n += self.db.execute(
                select(func.count()).where(
                    ImportBatch.workspace_id == ws,
                    ImportBatch.document_group == group,
                    ImportBatch.source_revision < max_rev,
                )
            ).scalar_one()
        return n

    def _coverage(self, ws: uuid.UUID, *, batch_id: uuid.UUID | None = None) -> dict[str, Any]:
        """Coverage matrix (§9.3): claims+records grouped by product
        family, metric, method, and evidence type. Missing dimension
        values land in "unknown" — never dropped."""
        rec_stmt = select(ExtractedRecord).where(ExtractedRecord.workspace_id == ws)
        claim_stmt = select(EvidenceClaim).where(EvidenceClaim.workspace_id == ws)
        if batch_id is not None:
            rec_stmt = rec_stmt.where(ExtractedRecord.batch_id == batch_id)
            claim_stmt = claim_stmt.where(EvidenceClaim.source_batch_id == batch_id)
        dims: dict[str, dict[str, int]] = {
            "byProductFamily": {},
            "byMetric": {},
            "byMethod": {},
            "byEvidenceType": {},
        }

        def bump(dim: str, value: Any) -> None:
            key = str(value).strip() if value is not None else ""
            key = key or "unknown"
            dims[dim][key] = dims[dim].get(key, 0) + 1

        for r in self.db.execute(rec_stmt).scalars():
            p = r.payload or {}
            bump("byProductFamily", p.get("family") or p.get("product_family"))
            bump("byMetric", p.get("metric"))
            bump("byMethod", p.get("method"))
            bump("byEvidenceType", r.kind)
        for c in self.db.execute(claim_stmt).scalars():
            bump("byProductFamily", c.subject.get("family") or c.subject.get("product_family"))
            bump("byMetric", c.statement.get("metric"))
            bump("byMethod", (c.conditions or {}).get("method"))
            bump("byEvidenceType", c.kind)
        return dims

    def _outcomes(self, ws: uuid.UUID, *, batch_id: uuid.UUID | None = None) -> dict[str, Any]:
        """Outcome categories (§9.3, AT-0305-2): original labels are
        preserved inside each category — instrument failures and
        genuine performance misses are never merged into a single
        bucket, and nothing becomes an RL reward by keyword."""
        rec_stmt = select(ExtractedRecord).where(ExtractedRecord.workspace_id == ws)
        claim_stmt = select(EvidenceClaim).where(EvidenceClaim.workspace_id == ws)
        if batch_id is not None:
            rec_stmt = rec_stmt.where(ExtractedRecord.batch_id == batch_id)
            claim_stmt = claim_stmt.where(EvidenceClaim.source_batch_id == batch_id)
        categories: dict[str, dict[str, Any]] = {}
        kinds: dict[str, int] = {}

        def record_outcome(raw: Any) -> None:
            if raw is None:
                return
            if isinstance(raw, dict):
                label = str(raw.get("label") or raw.get("text") or "").strip()
                category = str(raw.get("category") or "unclassified").strip() or "unclassified"
                kind = str(raw.get("kind") or "unclassified").strip() or "unclassified"
            else:
                label, category, kind = str(raw).strip(), "unclassified", "unclassified"
            if not label:
                return
            bucket = categories.setdefault(category, {"count": 0, "kinds": {}, "labels": []})
            bucket["count"] += 1
            bucket["kinds"][kind] = bucket["kinds"].get(kind, 0) + 1
            bucket["labels"].append(label)
            kinds[kind] = kinds.get(kind, 0) + 1

        for r in self.db.execute(rec_stmt).scalars():
            record_outcome((r.payload or {}).get("outcome"))
        for c in self.db.execute(claim_stmt).scalars():
            record_outcome(c.statement.get("outcome"))
            record_outcome((c.conditions or {}).get("outcome"))
        return {"byCategory": categories, "byKind": kinds}
