"""Value types for the confidential-execution adapter (CS-1004).

Everything is plain data — the same honest-ledger idiom as
``cloud_broker.types``. No I/O and no provider SDKs live here: real
providers plug in behind the ``ConfidentialBackend`` protocol and are
bound to an owner-approved ``ApprovedEnvironment`` plus an explicit
``ApprovalRef``. Until that approval exists the whole surface reports
``not_configured`` and stays inert.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from cloud_broker.types import digest_doc

ATTESTATION_STATUSES = ("verified", "refused")

# A confidential job only ever accepts payloads whose provenance was
# approved by an owner. In this deployment no owner approval exists
# (U08/U09/U11 open), so every environment is registered synthetic-only.
PAYLOAD_PROVENANCE = ("synthetic", "approved_real")


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ApprovalRef:
    """Reference to an owner approval binding this adapter.

    The approval itself is minted by the approvals domain service — the
    adapter never approves anything. This record binds a concrete
    provider/account/region/environment to the approval digest an owner
    produced. Registration refuses missing, expired, or
    wrongly-capability-scoped references.
    """

    digest: str
    approver: str
    capability: str  # must be "approve_export"
    bound: str  # approval subject, e.g. "cloud_provider:aws/123/us-east-1/enclave-a"
    expiry: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "digest": self.digest,
            "approver": self.approver,
            "capability": self.capability,
            "bound": self.bound,
            "expiry": self.expiry.isoformat(),
        }


@dataclass(frozen=True)
class ApprovedEnvironment:
    """The exact environment identity + policy an owner approved.

    Every field is asserted against attestation evidence before any key
    release or payload handoff; a single mismatch refuses (fail closed).
    Fields exist for the §20.4 requirements even when the provider
    cannot yet prove them — ``None`` in the document is a refusal, never
    a pass.
    """

    provider: str
    account: str
    region: str
    environment: str  # approved TEE environment identity
    measurement: str  # expected enclave measurement / PCR-set digest
    firmware: str | None  # expected TEE firmware version (None = not pinned)
    gpu_confidential: bool  # approved GPU coverage must be present (absent = fail)
    image_digest: str  # pinned code/container digest
    model_digest: str | None  # pinned model dependency digest
    network: str  # "restricted" | "deny_outbound"
    operator_access: str  # "deny" | "breakglass"
    telemetry_disabled: bool
    content_logging_disabled: bool
    ephemeral_credentials: bool
    private_artifacts: bool
    max_access_ttl_seconds: int
    deletion_required: bool
    synthetic_only: bool  # this deployment: synthetic payloads only
    expiry: datetime  # the approval's validity window

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "account": self.account,
            "region": self.region,
            "environment": self.environment,
            "measurement": self.measurement,
            "firmware": self.firmware,
            "gpu_confidential": self.gpu_confidential,
            "image_digest": self.image_digest,
            "model_digest": self.model_digest,
            "network": self.network,
            "operator_access": self.operator_access,
            "telemetry_disabled": self.telemetry_disabled,
            "content_logging_disabled": self.content_logging_disabled,
            "ephemeral_credentials": self.ephemeral_credentials,
            "private_artifacts": self.private_artifacts,
            "max_access_ttl_seconds": self.max_access_ttl_seconds,
            "deletion_required": self.deletion_required,
            "synthetic_only": self.synthetic_only,
            "expiry": self.expiry.isoformat(),
        }

    def digest(self) -> str:
        return digest_doc(self.to_dict())


@dataclass(frozen=True)
class AttestationDocument:
    """Provider-supplied evidence for the environment under execution.

    ``signature`` is a digest over the canonical document content: the
    skeleton models tamper-detection honestly. A real provider signs
    with the TEE root — the verifier stays all-or-nothing either way.
    """

    provider: str
    account: str
    region: str
    environment: str
    measurement: str
    firmware: str | None
    gpu_confidential: bool | None  # None = provider does not report coverage
    image_digest: str
    model_digest: str | None
    network: str
    operator_access: str
    telemetry_enabled: bool
    content_logging_enabled: bool
    ephemeral_credentials: bool
    private_artifacts: bool
    issued_at: datetime
    expiry: datetime
    signature: str

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "account": self.account,
            "region": self.region,
            "environment": self.environment,
            "measurement": self.measurement,
            "firmware": self.firmware,
            "gpu_confidential": self.gpu_confidential,
            "image_digest": self.image_digest,
            "model_digest": self.model_digest,
            "network": self.network,
            "operator_access": self.operator_access,
            "telemetry_enabled": self.telemetry_enabled,
            "content_logging_enabled": self.content_logging_enabled,
            "ephemeral_credentials": self.ephemeral_credentials,
            "private_artifacts": self.private_artifacts,
            "issued_at": self.issued_at.isoformat(),
            "expiry": self.expiry.isoformat(),
        }

    def doc_digest(self) -> str:
        return digest_doc(self.unsigned_dict())

    def to_dict(self) -> dict[str, Any]:
        out = self.unsigned_dict()
        out["signature"] = self.signature
        return out


@dataclass(frozen=True)
class AttestationCheck:
    """One named attestation comparison and its outcome."""

    name: str
    ok: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass(frozen=True)
class AttestationVerdict:
    """All-or-nothing attestation result — fails closed."""

    status: Literal["verified", "refused"]
    checks: tuple[AttestationCheck, ...]
    environment_digest: str
    document_digest: str | None

    @property
    def ok(self) -> bool:
        return self.status == "verified"

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.checks if not c.ok)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checks": [c.to_dict() for c in self.checks],
            "failures": list(self.failures),
            "environment_digest": self.environment_digest,
            "document_digest": self.document_digest,
        }


@dataclass(frozen=True)
class KeyReleaseRequest:
    """Ask the environment's key machinery for an ephemeral job key."""

    job_ref: str
    ttl_seconds: int
    scope: str = "job"


@dataclass(frozen=True)
class KeyReleaseTicket:
    """Ephemeral key material released to the verified environment.

    ``key_material`` never leaves the backend for an attestation that
    failed — the ticket only exists after a verified verdict.
    """

    key_id: str
    job_ref: str
    ttl_seconds: int
    issued_at: datetime
    ephemeral: bool
    key_material: bytes = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "job_ref": self.job_ref,
            "ttl_seconds": self.ttl_seconds,
            "issued_at": self.issued_at.isoformat(),
            "ephemeral": self.ephemeral,
            "key_material_sha256": digest_doc({"material": self.key_material.hex()}),
        }


@dataclass(frozen=True)
class ConfidentialJobSpec:
    """What the confidential backend is asked to run."""

    job: str
    job_ref: str
    payload_digest: str
    classification: str
    provenance: str  # "synthetic" | "approved_real"
    manifest_digest: str | None
    runtime_digest: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job": self.job,
            "job_ref": self.job_ref,
            "payload_digest": self.payload_digest,
            "classification": self.classification,
            "provenance": self.provenance,
            "manifest_digest": self.manifest_digest,
            "runtime_digest": self.runtime_digest,
        }


@dataclass(frozen=True)
class ImportedArtifact:
    """One output artifact returned by the confidential environment."""

    artifact_id: str
    media: str
    byte_size: int
    sha256: str
    private: bool
    access_ttl_seconds: int
    content: bytes = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "media": self.media,
            "byte_size": self.byte_size,
            "sha256": self.sha256,
            "private": self.private,
            "access_ttl_seconds": self.access_ttl_seconds,
        }


@dataclass(frozen=True)
class ImportedOutputs:
    """Confidential job output — always imported confidential + untrusted.

    ``validated`` only ever flips in the domain layer after the artifact
    is checked against the approved manifest. The adapter never marks an
    output trusted.
    """

    job_id: str
    classification: str  # always "confidential"
    trusted: bool  # always False
    validated: bool  # always False at import
    artifacts: tuple[ImportedArtifact, ...]
    imported_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "classification": self.classification,
            "trusted": self.trusted,
            "validated": self.validated,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "imported_at": self.imported_at.isoformat(),
        }


@dataclass(frozen=True)
class ProviderObservation:
    """What the provider can still observe about one job.

    The honest accounting of residual visibility: metadata, timing,
    payload size, artifact sizes, network endpoints. Content is never
    claimed hidden.
    """

    job_id: str
    provider: str
    account: str
    region: str
    environment: str
    payload_bytes: int
    submitted_at: datetime | None
    last_event_at: datetime | None
    artifact_ids: tuple[str, ...]
    artifact_bytes: int
    endpoints: tuple[str, ...]
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "provider": self.provider,
            "account": self.account,
            "region": self.region,
            "environment": self.environment,
            "payload_bytes": self.payload_bytes,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
            "artifact_ids": list(self.artifact_ids),
            "artifact_bytes": self.artifact_bytes,
            "endpoints": list(self.endpoints),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ConfidentialReconcile:
    """End-of-job reconciliation for the confidential environment.

    Combines the job's terminal state, the deletion receipts, and a
    storage probe. ``unresolved`` lists anything the provider still
    retains — the honest answer, never assumed clean.
    """

    job_id: str
    state: str
    terminated: bool
    storage_deleted: bool
    retained_bytes: int
    unresolved: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "state": self.state,
            "terminated": self.terminated,
            "storage_deleted": self.storage_deleted,
            "retained_bytes": self.retained_bytes,
            "unresolved": list(self.unresolved),
        }


@dataclass(frozen=True)
class StorageVerification:
    """Probe result after a deletion request."""

    job_id: str
    verified: bool
    retained_bytes: int
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "verified": self.verified,
            "retained_bytes": self.retained_bytes,
            "detail": self.detail,
        }
