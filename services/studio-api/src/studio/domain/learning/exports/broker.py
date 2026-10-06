"""Approved-export broker: revocation + receipts (§20.2, §20.5, CS-1003).

The cloud egress broker (``infra/cloud/broker``) is the ONLY outbound
path — this service wires it to the persisted manifest, the approvals
ledger and the vault:

- **Bind.** The approval binds ``ExportTransformedPayload.bound_inputs``
  digest-for-digest; ``require_valid`` runs *immediately before* every
  transfer attempt (§20.2). The broker then checks the identical
  digest + recipient + job + limits + expiry against the order — field
  similarity is never enough (AT-1003-1).
- **Single egress.** ``submit``/``dry_run``/``cancel``/``reconcile``/
  ``delete_remote`` route through the broker; a denied attempt emits
  zero bytes and still lands on the attempts ledger.
- **Revocation.** ``revoke`` revokes the approval, blocks the binding
  inside the broker, cancels in-flight jobs and reconciles honestly —
  bytes already sent stay recorded as ``exposed``; nothing claims
  unseen data was unseen (AT-1003-2).
- **Untrusted returns.** Provider callbacks dedupe through the
  ``export_callbacks`` ledger + lineage fold (AT-1003-3). Returned
  checkpoints/logs are confidential AND untrusted until locally
  validated — ``import_returned_artifact`` verifies the declared
  digest, quarantines the artifact and only then commits it to the
  vault. Nothing is ever published to a model hub.

No real provider exists: production providers stay ``not_configured``
and every path runs against the in-process ``ProviderDouble``.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from chem_studio_policy.capabilities import CAP_REVIEW_EXPORT
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cloud_broker import (
    ApprovedBinding,
    EgressBroker,
    Recipient,
    TransferLimits,
    TransferOrder,
)
from cloud_broker.types import (
    CallbackEvent,
    DeletionReceipt,
    JobLineage,
    ReconcileReport,
    sha256_bytes,
)
from studio.application import approvals
from studio.application.idempotency import canonical_json as _canon
from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext
from studio.domain.evidence.vault import Vault
from studio.errors import DomainError, ErrorCode, forbidden, not_found
from studio.events.outbox import publish
from studio.persistence.models import (
    Approval,
    Artifact,
    ExportCallback,
    ExportJob,
    ExportJobAttempt,
    ExportReceipt,
    ExportTransformedPayload,
)

APPROVAL_ACTION = "export"
# Provider events folded into ExportJob.status (job.status describes
# the transfer lifecycle; the raw provider state lives in
# external_state).
_PROVIDER_STATE_TO_JOB = {
    "submitted": "transferred",
    "queued": "transferred",
    "running": "running",
    "succeeded": "succeeded",
    "failed": "failed",
    "cancelled": "cancelled",
    "deleted": "deleted",
}
_LINEAGE_STATES = set(_PROVIDER_STATE_TO_JOB)
_JOB_LIVE_STATES = {"pending", "transferring", "transferred", "running", "reconciling"}
# Bound, not fabricated: a permit lives only inside the permitted
# window — when neither the manifest nor the approval declares an
# expiry, the attempt is bounded by this wall-clock cap.
_DEFAULT_PERMIT_SECONDS = 3600.0
_MAX_RETURNED_ARTIFACT_BYTES = 64 * 1024 * 1024


class ExportBrokerService:
    """Domain wiring for the single egress broker (CS-1003)."""

    def __init__(
        self,
        db: Session,
        ctx: ServiceContext,
        *,
        broker: EgressBroker | None = None,
        vault: Vault | None = None,
    ) -> None:
        self.db = db
        self.ctx = ctx
        self.broker = broker or EgressBroker()
        self.vault = vault

    # ------------------------------------------------------------ helpers

    def _payload(self, payload_id: uuid.UUID) -> ExportTransformedPayload:
        row = self.db.execute(
            select(ExportTransformedPayload).where(
                ExportTransformedPayload.id == payload_id,
                ExportTransformedPayload.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("export payload")
        return row

    def _job(self, job_id: uuid.UUID) -> ExportJob:
        row = self.db.execute(
            select(ExportJob).where(
                ExportJob.id == job_id,
                ExportJob.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("export job")
        return row

    def _payload_bytes(self, row: ExportTransformedPayload) -> bytes:
        """Canonical payload bytes — digest-verified against the
        manifest before anything may reference them (§20.2)."""
        data = _canon(row.payload).encode("utf-8")
        if hashlib.sha256(data).hexdigest() != row.payload_digest:
            raise DomainError(
                ErrorCode.CONFLICT,
                "payload bytes no longer match the approved payload digest",
            )
        return data

    def _recipient(self, row: ExportTransformedPayload) -> Recipient:
        r = row.manifest.get("recipient") or {}
        env = row.manifest.get("environment") or {}
        return Recipient(
            provider=r.get("provider") or "unconfigured",
            account=r.get("account") or "",
            region=r.get("region") or "",
            environment=env.get("containerDigest") or "unconfigured",
        )

    def _limits(self, row: ExportTransformedPayload) -> TransferLimits:
        lim = row.manifest.get("limits") or {}
        ret = row.manifest.get("retention") or {}
        return TransferLimits(
            max_bytes=int(lim.get("maxBytes") or 0),
            max_artifacts=int(lim.get("maxRecords") or 0),
            wall_seconds=_DEFAULT_PERMIT_SECONDS,
            retention_expectation=str(ret.get("expectation") or "unspecified"),
            deletion_required=bool(ret.get("deletionExpectation")),
        )

    def _expiry(self, row: ExportTransformedPayload, approval: Approval | None) -> datetime:
        """The operative permit bound: the earliest declared expiry —
        manifest expiry, then approval expiry, then the wall-clock
        bound of the permitted window."""
        candidates: list[datetime] = []
        raw = row.manifest.get("expiry")
        if isinstance(raw, str) and raw:
            parsed = datetime.fromisoformat(raw)
            candidates.append(parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC))
        if approval is not None and approval.expires_at is not None:
            exp = approval.expires_at
            candidates.append(exp if exp.tzinfo else exp.replace(tzinfo=UTC))
        if candidates:
            return min(candidates)
        return datetime.now(UTC) + timedelta(seconds=_DEFAULT_PERMIT_SECONDS)

    def _binding(
        self,
        row: ExportTransformedPayload,
        approval: Approval | None,
    ) -> ApprovedBinding:
        """Rebuild the approved bound document — ``bound_doc`` pins the
        ledger's canonical ``bound_inputs`` so the binding digest is
        byte-identical to ``row.bound_digest`` (AT-1003-1)."""
        m = row.manifest
        job = m.get("permittedJob") or {}
        return ApprovedBinding(
            manifest_digest=row.bound_digest,
            payload_digest=row.payload_digest,
            payload_fields=tuple(str(f) for f in row.payload_fields),
            source_digests=((m.get("snapshot") or {}).get("digest") or "",),
            transformation_version=row.transformation_version,
            classification=row.classification,
            recipient=self._recipient(row),
            runtime_digest=str(
                (m.get("environment") or {}).get("containerDigest")
                or (m.get("environment") or {}).get("runtime", {}).get("transform")
                or "unconfigured"
            ),
            permitted_job=_canon(job),
            limits=self._limits(row),
            expiry=self._expiry(row, approval),
            approver=str(approval.decided_by) if approval is not None else "",
            bound_doc=row.bound_inputs,
        )

    def _order(
        self,
        binding: ApprovedBinding,
        *,
        attempt_key: str,
        requested_recipient: Recipient | None = None,
        requested_job: str | None = None,
        requested_digest: str | None = None,
        approval_digest: str | None = None,
    ) -> TransferOrder:
        """A transfer order whose defaults are the approved manifest
        verbatim — any caller-supplied drift fails the broker's digest
        checks (AT-1003-1)."""
        return TransferOrder(
            approved=binding,
            requested_digest=requested_digest or binding.digest(),
            requested_recipient=requested_recipient or binding.recipient,
            requested_job=requested_job or binding.permitted_job,
            approval_digest=approval_digest or binding.digest(),
            attempt_key=attempt_key,
        )

    def _approval_for(self, row: ExportTransformedPayload) -> Approval:
        """Revalidate immediately before a transfer attempt (§20.2):
        revoked → FORBIDDEN, expired → APPROVAL_EXPIRED, bound-input
        drift → APPROVAL_STALE."""
        return approvals.require_valid(
            self.db, self.ctx, action=APPROVAL_ACTION, bound_inputs=row.bound_inputs
        )

    def _job_for(
        self,
        row: ExportTransformedPayload,
        approval: Approval | None,
    ) -> ExportJob:
        """One job row per (payload, manifest bound digest) — retries
        within the same manifest/recipient/expiry reuse it (§20.2); the
        unique constraint makes convergence physical (AT-1003-3)."""
        existing = self.db.execute(
            select(ExportJob).where(
                ExportJob.workspace_id == self.ctx.workspace_id,
                ExportJob.payload_id == row.id,
                ExportJob.manifest_digest == row.bound_digest,
            )
        ).scalar_one_or_none()
        if existing is not None:
            if approval is not None:
                existing.approval_id = approval.id
            return existing
        job = ExportJob(
            workspace_id=self.ctx.workspace_id,
            payload_id=row.id,
            approval_id=approval.id if approval is not None else None,
            status="pending",
            manifest_digest=row.bound_digest,
            payload_digest=row.payload_digest,
            recipient=(row.manifest.get("recipient") or {}),
            permitted_job=dict(row.manifest.get("permittedJob") or {}),
            expires_at=self._expiry(row, approval),
            bytes_transferred=0,
            artifact_ids=[],
            seen_callback_ids=[],
            last_seq=0,
            exposed=0,
            external_state="submitted",
        )
        self.db.add(job)
        self.db.flush()
        return job

    def _record_attempt(
        self,
        job: ExportJob,
        *,
        attempt_key: str,
        outcome: str,
        reason: str | None,
        bytes_emitted: int,
        external_job_id: str | None,
    ) -> ExportJobAttempt:
        attempt = ExportJobAttempt(
            workspace_id=self.ctx.workspace_id,
            job_id=job.id,
            attempt_key=attempt_key,
            outcome=outcome,
            reason=reason,
            bytes_emitted=bytes_emitted,
            external_job_id=external_job_id,
        )
        self.db.add(attempt)
        self.db.flush()
        return attempt

    def _record_receipt(
        self,
        job: ExportJob,
        *,
        kind: str,
        receipt_ref: str | None,
        report: ReconcileReport | None = None,
        receipt: DeletionReceipt | None = None,
    ) -> ExportReceipt:
        unresolved = (
            list(report.unresolved_retention)
            if report is not None
            else (list(receipt.unresolved) if receipt is not None else [])
        )
        row = ExportReceipt(
            workspace_id=self.ctx.workspace_id,
            job_id=job.id,
            kind=kind,
            receipt_ref=receipt_ref,
            bytes_transferred=job.bytes_transferred,
            artifact_ids=list(job.artifact_ids or []),
            unresolved_retention=unresolved,
            exposed=job.exposed,
            raw={
                "jobId": str(job.id),
                "externalJobId": job.external_job_id,
                "state": report.state if report is not None else None,
                "deleted": receipt.deleted if receipt is not None else None,
            },
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _lineage_for(self, job: ExportJob) -> JobLineage | None:
        """The broker lineage for a job — restored from the persisted
        row after a process restart so callback folding survives."""
        if job.external_job_id is None:
            return None
        lineage = self.broker.lineage(job.external_job_id)
        if lineage is None:
            lineage = JobLineage(
                job_id=job.external_job_id,
                state=(
                    job.external_state if job.external_state in _LINEAGE_STATES else "submitted"
                ),
                bytes_transferred=job.bytes_transferred,
                artifact_ids=list(job.artifact_ids or []),
                seen_callback_ids=set(job.seen_callback_ids or []),
                last_seq=job.last_seq or None,
                exposed=job.exposed > 0,
            )
            self.broker.seed_lineage(lineage)
        return lineage

    def _apply_lineage(self, job: ExportJob, lineage: JobLineage) -> None:
        job.external_state = lineage.state
        job.status = _PROVIDER_STATE_TO_JOB.get(lineage.state, job.status)
        job.bytes_transferred = max(job.bytes_transferred, lineage.bytes_transferred)
        job.exposed = max(job.exposed, lineage.bytes_transferred)
        job.artifact_ids = sorted(set(job.artifact_ids or []) | set(lineage.artifact_ids))
        job.seen_callback_ids = sorted(
            set(job.seen_callback_ids or []) | set(lineage.seen_callback_ids)
        )
        job.last_seq = max(job.last_seq or 0, lineage.last_seq or 0)

    def _apply_report(self, job: ExportJob, report: ReconcileReport) -> None:
        if report.state in _PROVIDER_STATE_TO_JOB:
            job.external_state = report.state
            job.status = _PROVIDER_STATE_TO_JOB[report.state]
        job.bytes_transferred = max(job.bytes_transferred, report.bytes_transferred)
        job.exposed = max(job.exposed, report.bytes_transferred)
        job.artifact_ids = sorted(set(job.artifact_ids or []) | set(report.artifact_ids))

    # ------------------------------------------------------------ dry-run

    def dry_run(self, payload_id: uuid.UUID, *, attempt_key: str | None = None) -> dict[str, Any]:
        """Full validation, zero provider contact: the identical checks
        a real transfer runs — a denied dry-run still lands an attempt
        row so the ledger is complete (AT-1003-1)."""
        self.ctx.require(CAP_REVIEW_EXPORT)
        row = self._payload(payload_id)
        approval = self._approval_for(row)
        binding = self._binding(row, approval)
        job = self._job_for(row, approval)
        key = attempt_key or f"dryrun-{uuid.uuid4()}"
        report = self.broker.dry_run(
            self._order(binding, attempt_key=key), self._payload_bytes(row)
        )
        self._record_attempt(
            job,
            attempt_key=key,
            outcome="validated" if report.ok else "denied",
            reason=None if report.ok else "dry-run validation failed",
            bytes_emitted=0,
            external_job_id=None,
        )
        if not report.ok and job.status == "pending":
            job.status = "denied"
        audit_record(
            self.db,
            self.ctx,
            action="export.dry_run",
            target_type="export_job",
            target_id=job.id,
            detail={"ok": report.ok},
        )
        self.db.flush()
        return {
            "jobId": str(job.id),
            "ok": report.ok,
            "checks": [[name, ok, detail] for name, ok, detail in report.checks],
        }

    # ------------------------------------------------------------ submit

    def submit(
        self,
        payload_id: uuid.UUID,
        *,
        attempt_key: str | None = None,
        requested_recipient: dict[str, str] | None = None,
        requested_job: str | None = None,
        requested_digest: str | None = None,
    ) -> dict[str, Any]:
        """Attempt the approved transfer — the ONLY path bytes can
        leave. The approval is revalidated immediately before emit
        (§20.2); a denied order emits ZERO proprietary bytes and the
        attempt still lands on the ledger (AT-1003-1)."""
        self.ctx.require(CAP_REVIEW_EXPORT)
        row = self._payload(payload_id)
        # approval revalidation — immediately before every attempt
        approval = self._approval_for(row)
        binding = self._binding(row, approval)
        job = self._job_for(row, approval)
        key = attempt_key or f"attempt-{uuid.uuid4()}"
        order = self._order(
            binding,
            attempt_key=key,
            requested_recipient=(Recipient(**requested_recipient) if requested_recipient else None),
            requested_job=requested_job,
            requested_digest=requested_digest,
        )
        handle = self.broker.transfer(order, self._payload_bytes(row))
        rec = next(a for a in reversed(self.broker.attempts) if a.attempt_key == key)
        self._record_attempt(
            job,
            attempt_key=key,
            outcome=rec.outcome,
            reason=rec.reason,
            bytes_emitted=rec.bytes_emitted,
            external_job_id=rec.job_id,
        )
        if rec.outcome == "transferred" and handle is not None:
            job.external_job_id = handle.job_id
            job.status = "transferred"
            job.bytes_transferred = rec.bytes_emitted
            job.exposed = rec.bytes_emitted
        elif job.status == "pending":
            job.status = "denied" if rec.outcome == "denied" else "failed"
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="export_job",
            aggregate_id=job.id,
            event_type=f"export.attempt.{rec.outcome}",
            payload={"jobId": str(job.id), "payloadId": str(row.id)},
        )
        audit_record(
            self.db,
            self.ctx,
            action="export.attempt",
            target_type="export_job",
            target_id=job.id,
            detail={
                "outcome": rec.outcome,
                "bytesEmitted": rec.bytes_emitted,
                "boundDigest": row.bound_digest,
            },
        )
        self.db.flush()
        return self.job_view(job.id)

    # ------------------------------------------------- cancel / revoke

    def cancel(self, job_id: uuid.UUID) -> dict[str, Any]:
        """§20.5 during execution: request provider cancellation, then
        reconcile what was actually transferred — recorded as exposed,
        never claimed unseen (AT-1003-2)."""
        self.ctx.require(CAP_REVIEW_EXPORT)
        job = self._job(job_id)
        if job.external_job_id is None:
            job.status = "cancelled"
            self._record_receipt(job, kind="cancellation", receipt_ref=None)
            self.db.flush()
            return self.job_view(job.id)
        report = self.broker.cancel(job.external_job_id)
        self._apply_report(job, report)
        # status records our action; external_state keeps the provider's
        # own reported state — honest reconcile, never a claim (§20.5).
        job.status = "cancelled"
        self._record_receipt(job, kind="cancellation", receipt_ref=None, report=report)
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="export_job",
            aggregate_id=job.id,
            event_type="export.cancelled",
            payload={"jobId": str(job.id)},
        )
        audit_record(
            self.db,
            self.ctx,
            action="export.cancelled",
            target_type="export_job",
            target_id=job.id,
            detail={
                "bytesTransferred": report.bytes_transferred,
                "exposed": report.exposed,
                "unresolvedRetention": list(report.unresolved_retention),
            },
        )
        self.db.flush()
        return self.job_view(job.id)

    def revoke(self, payload_id: uuid.UUID, *, reason: str) -> dict[str, Any]:
        """§20.5 full revocation — a human act only:

        revoke the approval, block the binding inside the broker (any
        later attempt is denied before the boundary), cancel every live
        job at the provider and reconcile honestly — already-exposed
        bytes stay recorded as exposed (AT-1003-2)."""
        if self.ctx.principal_kind != "user":
            raise forbidden("export revocation requires a human principal")
        row = self._payload(payload_id)
        approval = self.db.execute(
            select(Approval)
            .where(
                Approval.workspace_id == self.ctx.workspace_id,
                Approval.action == APPROVAL_ACTION,
                Approval.bound_digest == row.bound_digest,
            )
            .order_by(Approval.created_at.desc(), Approval.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if approval is not None and approval.revoked_at is None:
            approvals.revoke(self.db, self.ctx, approval_id=approval.id)
        self.broker.revoke_binding(row.bound_digest)
        jobs = (
            self.db.execute(
                select(ExportJob).where(
                    ExportJob.workspace_id == self.ctx.workspace_id,
                    ExportJob.payload_id == row.id,
                    ExportJob.manifest_digest == row.bound_digest,
                )
            )
            .scalars()
            .all()
        )
        for job in jobs:
            if job.status not in _JOB_LIVE_STATES:
                continue
            if job.external_job_id is not None:
                report = self.broker.cancel(job.external_job_id)
                self._apply_report(job, report)
                self._record_receipt(job, kind="cancellation", receipt_ref=None, report=report)
            else:
                self._record_receipt(job, kind="cancellation", receipt_ref=None)
            job.status = "cancelled"
        audit_record(
            self.db,
            self.ctx,
            action="export.revoked",
            target_type="export_transformed_payload",
            target_id=row.id,
            detail={
                "reason": reason,
                "jobsCancelled": len(jobs),
                "exposed": sum(j.exposed for j in jobs),
            },
        )
        self.db.flush()
        return {
            "payloadId": str(row.id),
            "revoked": True,
            "jobsCancelled": len(jobs),
            "exposed": sum(j.exposed for j in jobs),
        }

    # ------------------------------------------------- reconcile / delete

    def reconcile(self, job_id: uuid.UUID) -> dict[str, Any]:
        """Drain pending callbacks + read the provider's actual state —
        the receipt records what it *still retains*, unresolved
        retention items listed never dropped (§20.5)."""
        self.ctx.require(CAP_REVIEW_EXPORT)
        job = self._job(job_id)
        if job.external_job_id is None:
            return self.job_view(job.id)
        report = self.broker.reconcile(job.external_job_id)
        self._apply_report(job, report)
        self._record_receipt(job, kind="reconcile", receipt_ref=None, report=report)
        audit_record(
            self.db,
            self.ctx,
            action="export.reconciled",
            target_type="export_job",
            target_id=job.id,
            detail={
                "state": report.state,
                "unresolvedRetention": list(report.unresolved_retention),
            },
        )
        self.db.flush()
        return self.job_view(job.id)

    def delete_remote(self, job_id: uuid.UUID) -> dict[str, Any]:
        """Request provider-side deletion; the actual receipt — not a
        claim — is recorded (§20.5)."""
        self.ctx.require(CAP_REVIEW_EXPORT)
        job = self._job(job_id)
        if job.external_job_id is None:
            raise DomainError(ErrorCode.CONFLICT, "job was never transferred")
        receipt = self.broker.delete(job.external_job_id)
        if receipt.deleted:
            job.status = "deleted"
            job.external_state = "deleted"
        self._record_receipt(job, kind="deletion", receipt_ref=receipt.receipt_ref, receipt=receipt)
        audit_record(
            self.db,
            self.ctx,
            action="export.delete_requested",
            target_type="export_job",
            target_id=job.id,
            detail={"receiptRef": receipt.receipt_ref, "deleted": receipt.deleted},
        )
        self.db.flush()
        return self.job_view(job.id)

    # ------------------------------------------------- provider callbacks

    def handle_callback(
        self,
        job_id: uuid.UUID,
        *,
        callback_id: str,
        event: str,
        seq: int = 0,
        artifacts: list[str] | None = None,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Fold one (untrusted) provider callback into the lineage.

        Dedupe is enforced by the ``export_callbacks`` unique row
        inside a savepoint — a replay rolls back to the recorded
        state; crossed/reordered events converge via the lineage fold
        (AT-1003-3)."""
        self.ctx.require(CAP_REVIEW_EXPORT)
        job = self._job(job_id)
        cb = CallbackEvent(
            callback_id=callback_id,
            job_id=job.external_job_id or "",
            event=event,
            seq=seq,
            artifacts=tuple(artifacts or ()),
            detail=str(detail or ""),
        )
        if not cb.callback_id or not cb.job_id:
            return {"jobId": str(job.id), "applied": False, "reason": "foreign_or_malformed"}
        nested = self.db.begin_nested()
        try:
            self.db.add(
                ExportCallback(
                    workspace_id=self.ctx.workspace_id,
                    job_id=job.id,
                    callback_id=cb.callback_id,
                    event=event,
                    seq=seq,
                    artifacts=list(artifacts or []),
                    detail=detail or {},
                )
            )
            self.db.flush()
        except IntegrityError:
            nested.rollback()
            return {"jobId": str(job.id), "applied": False, "reason": "duplicate"}
        changed = self.broker.handle_callback(cb)
        lineage = self._lineage_for(job)
        if lineage is not None:
            self._apply_lineage(job, lineage)
        self.db.flush()
        return {"jobId": str(job.id), "applied": changed}

    # -------------------------------------------- returned artifacts (§20.5)

    def import_returned_artifact(
        self,
        job_id: uuid.UUID,
        *,
        data: bytes,
        declared_digest: str,
        kind: str,
        original_name: str | None = None,
    ) -> Artifact:
        """Stage a provider-returned artifact into the vault.

        Returned checkpoints/logs/weights are confidential AND
        untrusted derived data until locally validated: the declared
        digest is verified against the actual bytes, the artifact is
        persisted quarantined+confidential, and only then committed —
        never published to a model hub."""
        self.ctx.require(CAP_REVIEW_EXPORT)
        job = self._job(job_id)
        if not data:
            raise DomainError(ErrorCode.VALIDATION, "empty returned artifact")
        if len(data) > _MAX_RETURNED_ARTIFACT_BYTES:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"returned artifact exceeds {_MAX_RETURNED_ARTIFACT_BYTES} bytes",
            )
        if sha256_bytes(data) != declared_digest:
            raise DomainError(
                ErrorCode.VALIDATION,
                "returned artifact bytes differ from the declared digest",
            )
        if self.vault is None:
            raise DomainError(ErrorCode.VALIDATION, "no vault configured")
        artifact = Artifact(
            workspace_id=self.ctx.workspace_id,
            storage_key="",
            media_type="application/octet-stream",
            original_name=original_name or f"export-return-{kind}-{job.external_job_id}",
            declared_checksum=declared_digest,
            source_kind="derived",
            classification="confidential",
            review_state="quarantined",
            upload_state="receiving",
            rights={
                "source": "provider_return",
                "exportJobId": str(job.id),
                "kind": kind,
                "publishable": False,
                "validatedLocally": True,
            },
            retention={
                "confidential": True,
                "untrustedDerived": True,
                "publishable": False,
                "exportJobId": str(job.id),
            },
            source_artifact_ids=[],
            created_by=self.ctx.principal_id,
        )
        self.db.add(artifact)
        self.db.flush()
        artifact.storage_key = f"pending/{artifact.id}"
        staging = self.vault.begin_staging(self.ctx.workspace_id, artifact.id)
        self.vault.append_bytes(staging, data)
        key, size = self.vault.commit(self.ctx.workspace_id, artifact.id, declared_digest)
        artifact.storage_key = key
        artifact.byte_size = size
        artifact.checksum_sha256 = declared_digest
        artifact.upload_state = "committed"
        artifact.committed_at = datetime.now(UTC)
        audit_record(
            self.db,
            self.ctx,
            action="export.returned_artifact_imported",
            target_type="export_job",
            target_id=job.id,
            detail={"artifactId": str(artifact.id), "kind": kind},
        )
        self.db.flush()
        return artifact

    # ------------------------------------------------------------ views

    def job_view(self, job_id: uuid.UUID) -> dict[str, Any]:
        self.ctx.require(CAP_REVIEW_EXPORT)
        job = self._job(job_id)
        return {
            "id": str(job.id),
            "payloadId": str(job.payload_id),
            "status": job.status,
            "externalJobId": job.external_job_id,
            "externalState": job.external_state,
            "bytesTransferred": job.bytes_transferred,
            "artifactIds": list(job.artifact_ids or []),
            "exposed": job.exposed,
            "lastError": job.last_error,
        }
