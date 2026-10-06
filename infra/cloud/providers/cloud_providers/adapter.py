"""ConfidentialExecutionAdapter — the CS-1004 provider-neutral adapter.

Upward it is a ``cloud_broker`` ``CloudProvider``: every approved byte
still traverses the egress broker's permit gate. Downward it drives a
``ConfidentialBackend`` through the confidential-execution lifecycle:

    attestation verify (fail closed) -> ephemeral key release ->
    confidential submit -> callbacks/status -> cancel -> delete ->
    storage probe -> output import (confidential/untrusted until
    validated).

Without an owner approval the adapter cannot exist — the registry
refuses to build one — and the capability surface reports
``not_configured``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from cloud_broker.types import (
    CallbackEvent,
    DeletionReceipt,
    JobHandle,
    JobStatus,
    Recipient,
    sha256_bytes,
)
from cloud_providers.attestation import verify_attestation
from cloud_providers.backend import ConfidentialBackend
from cloud_providers.types import (
    ApprovalRef,
    ApprovedEnvironment,
    AttestationVerdict,
    ConfidentialJobSpec,
    ConfidentialReconcile,
    ImportedOutputs,
    KeyReleaseRequest,
    KeyReleaseTicket,
    ProviderObservation,
    StorageVerification,
    utcnow,
)


class ConfidentialDenied(Exception):
    """Base refusal raised before any payload or key material moves."""

    def __init__(self, reason: str, *, detail: Any = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


class AttestationRefused(ConfidentialDenied):
    """Attestation failed closed — no key release, no payload handoff."""

    def __init__(self, verdict: AttestationVerdict) -> None:
        super().__init__(
            f"attestation refused: {', '.join(verdict.failures)}",
            detail=verdict.to_dict(),
        )
        self.verdict = verdict


class ProvenanceRefused(ConfidentialDenied):
    """A real-provenance job reached a synthetic-only environment."""


class ImportRefused(ConfidentialDenied):
    """Provider returned artifacts violating private/short-lived access."""


class ConfidentialExecutionAdapter:
    """Provider-neutral confidential-execution adapter.

    Implements the broker's ``CloudProvider`` surface so approved
    transfers traverse the CS-1003 gate, and adds the
    confidential-execution surface (attest / release_key /
    submit_confidential / import_outputs / reconcile / observation).
    """

    def __init__(
        self,
        *,
        backend: ConfidentialBackend,
        environment: ApprovedEnvironment,
        approval: ApprovalRef,
    ) -> None:
        self._backend = backend
        self._spec = environment
        self._approval = approval
        self._jobs: dict[str, dict[str, Any]] = {}
        self.refusals: list[AttestationVerdict] = []
        self.key_releases: list[KeyReleaseTicket] = []
        self.imports: list[ImportedOutputs] = []
        self.storage_probes: list[StorageVerification] = []

    # -- CloudProvider surface (broker-facing) -------------------------------

    @property
    def name(self) -> str:
        return self._backend.name

    @property
    def kind(self) -> str:
        """Honest label: "synthetic" doubles never report live capability."""
        return self._backend.kind

    def submit(self, *, recipient: Recipient, job: str, payload: bytes) -> JobHandle:
        self._require_recipient(recipient)
        ticket = self._prepare(job_ref=job)
        # This deployment is synthetic-only: the only payloads an approval
        # can bind here are approved synthetic smoke payloads. A live
        # approval binding real data would register a spec without the
        # synthetic-only flag and flow through submit_confidential().
        spec = ConfidentialJobSpec(
            job=job,
            job_ref=job,
            payload_digest=sha256_bytes(payload),
            classification="confidential",
            provenance="synthetic",
            manifest_digest=None,
            runtime_digest=self._spec.measurement,
        )
        return self._dispatch(spec, payload, ticket)

    def status(self, handle: JobHandle) -> JobStatus:
        status = self._backend.status(handle)
        self._record_event(handle, status.state)
        return status

    def cancel(self, handle: JobHandle) -> JobStatus:
        status = self._backend.cancel(handle)
        self._record_event(handle, status.state)
        return status

    def delete(self, handle: JobHandle) -> DeletionReceipt:
        receipt = self._backend.delete(handle)
        self._record_event(handle, "deleted")
        return receipt

    def drain_callbacks(self, handle: JobHandle) -> list[CallbackEvent]:
        events = self._backend.drain_callbacks(handle)
        for event in events:
            self._record_event(handle, event.event, artifacts=event.artifacts)
        return events

    # -- Confidential-execution surface --------------------------------------

    def attest(self, *, now: datetime | None = None) -> AttestationVerdict:
        """Fetch provider evidence and verify it against the approved spec."""
        doc = self._backend.attestation_document()
        verdict = verify_attestation(doc, self._spec, now=now)
        if not verdict.ok:
            self.refusals.append(verdict)
        return verdict

    def release_key(self, request: KeyReleaseRequest) -> KeyReleaseTicket:
        """Release ephemeral key material — attestation verified inline.

        A caller-supplied verdict is never trusted: every release
        re-verifies the environment now, so key material cannot leave
        against a stale or forged verdict.
        """
        verdict = self.attest()
        if not verdict.ok:
            raise AttestationRefused(verdict)
        if request.ttl_seconds > self._spec.max_access_ttl_seconds:
            raise ConfidentialDenied(
                f"requested key ttl {request.ttl_seconds}s exceeds the "
                f"approved maximum {self._spec.max_access_ttl_seconds}s",
            )
        ticket = self._backend.release_key(request)
        self.key_releases.append(ticket)
        return ticket

    def submit_confidential(
        self,
        *,
        job: str,
        payload: bytes,
        provenance: str,
        manifest_digest: str | None = None,
        runtime_digest: str | None = None,
        job_ref: str | None = None,
    ) -> JobHandle:
        """Direct confidential submission with explicit provenance.

        ``provenance="approved_real"`` is refused while the environment is
        registered synthetic-only — the honest state of this deployment.
        """
        if provenance == "approved_real" and self._spec.synthetic_only:
            raise ProvenanceRefused(
                "environment is registered synthetic-only; real-provenance "
                "payloads require an owner-approved live binding",
            )
        ref = job_ref or job
        ticket = self._prepare(job_ref=ref)
        spec = ConfidentialJobSpec(
            job=job,
            job_ref=ref,
            payload_digest=sha256_bytes(payload),
            classification="confidential",
            provenance=provenance,
            manifest_digest=manifest_digest,
            runtime_digest=runtime_digest,
        )
        return self._dispatch(spec, payload, ticket)

    def reconcile(self, handle: JobHandle) -> ConfidentialReconcile:
        """Reconcile termination + storage deletion honestly."""
        status = self._backend.status(handle)
        terminated = status.state in (
            "succeeded",
            "failed",
            "cancelled",
            "deleted",
        )
        probe = self.verify_storage_deleted(handle)
        unresolved: list[str] = []
        if not terminated:
            unresolved.append(f"job still running ({status.state})")
        if not probe.verified:
            unresolved.append(probe.detail)
        return ConfidentialReconcile(
            job_id=handle.job_id,
            state=status.state,
            terminated=terminated,
            storage_deleted=probe.verified,
            retained_bytes=probe.retained_bytes,
            unresolved=tuple(unresolved),
        )

    def verify_storage_deleted(self, handle: JobHandle) -> StorageVerification:
        """Probe what the provider still retains — never assume clean."""
        retained = self._backend.retained_bytes(handle)
        probe = StorageVerification(
            job_id=handle.job_id,
            verified=retained == 0,
            retained_bytes=retained,
            detail="storage verified empty"
            if retained == 0
            else f"provider still retains {retained} bytes for the job",
        )
        self.storage_probes.append(probe)
        return probe

    def import_outputs(self, handle: JobHandle) -> ImportedOutputs:
        """Import job outputs — always confidential + untrusted."""
        raw = self._backend.import_outputs(handle)
        violations = [
            a.artifact_id
            for a in raw
            if not a.private or a.access_ttl_seconds > self._spec.max_access_ttl_seconds
        ]
        if violations:
            raise ImportRefused(
                "provider returned artifacts violating the private or "
                f"access-ttl policy: {', '.join(violations)}",
            )
        outputs = ImportedOutputs(
            job_id=handle.job_id,
            classification="confidential",
            trusted=False,
            validated=False,
            artifacts=tuple(raw),
            imported_at=utcnow(),
        )
        self.imports.append(outputs)
        return outputs

    def observation(self, job_id: str) -> ProviderObservation:
        """What the provider could still observe about this job."""
        record = self._jobs.get(job_id, {})
        return ProviderObservation(
            job_id=job_id,
            provider=self._spec.provider,
            account=self._spec.account,
            region=self._spec.region,
            environment=self._spec.environment,
            payload_bytes=record.get("payload_bytes", 0),
            submitted_at=record.get("submitted_at"),
            last_event_at=record.get("last_event_at"),
            artifact_ids=tuple(sorted(record.get("artifact_ids", set()))),
            artifact_bytes=record.get("artifact_bytes", 0),
            endpoints=tuple(record.get("endpoints", ())),
            detail=(
                "provider can observe job metadata, timing, payload/artifact "
                "sizes and network endpoints; content secrecy is not claimed "
                "against a compromised guest or side channels"
            ),
        )

    @property
    def approval(self) -> ApprovalRef:
        return self._approval

    @property
    def environment(self) -> ApprovedEnvironment:
        return self._spec

    # -- internals ------------------------------------------------------------

    def _require_recipient(self, recipient: Recipient) -> None:
        """The adapter only ever serves its approved environment identity."""
        if (
            recipient.provider != self._spec.provider
            or recipient.account != self._spec.account
            or recipient.region != self._spec.region
            or recipient.environment != self._spec.environment
        ):
            raise ConfidentialDenied(
                "transfer recipient does not match the approved environment "
                f"{self._spec.provider}/{self._spec.account}/"
                f"{self._spec.region}/{self._spec.environment}",
                detail={
                    "recipient": {
                        "provider": recipient.provider,
                        "account": recipient.account,
                        "region": recipient.region,
                        "environment": recipient.environment,
                    }
                },
            )

    def _prepare(self, *, job_ref: str) -> KeyReleaseTicket:
        """Attest (fail closed) then release an ephemeral job key."""
        request = KeyReleaseRequest(
            job_ref=job_ref,
            ttl_seconds=self._spec.max_access_ttl_seconds,
        )
        return self.release_key(request)

    def _dispatch(
        self,
        spec: ConfidentialJobSpec,
        payload: bytes,
        ticket: KeyReleaseTicket,
    ) -> JobHandle:
        handle = self._backend.submit_confidential(job=spec, payload=payload, key=ticket)
        self._jobs[handle.job_id] = {
            "spec": spec,
            "payload_bytes": len(payload),
            "submitted_at": utcnow(),
            "last_event_at": None,
            "artifact_ids": set(),
            "artifact_bytes": 0,
            "endpoints": getattr(self._backend, "endpoints", (self.name,)),
        }
        self._record_event(handle, "submitted")
        return handle

    def _record_event(
        self,
        handle: JobHandle,
        event: str,
        *,
        artifacts: tuple[str, ...] | None = None,
    ) -> None:
        record = self._jobs.setdefault(
            handle.job_id,
            {
                "payload_bytes": 0,
                "submitted_at": None,
                "last_event_at": None,
                "artifact_ids": set(),
                "artifact_bytes": 0,
                "endpoints": (),
            },
        )
        record["last_event_at"] = utcnow()
        if artifacts:
            record["artifact_ids"].update(artifacts)


__all__ = [
    "AttestationRefused",
    "ConfidentialDenied",
    "ConfidentialExecutionAdapter",
    "ImportRefused",
    "ProvenanceRefused",
]
