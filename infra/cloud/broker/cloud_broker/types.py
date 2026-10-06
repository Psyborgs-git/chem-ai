"""Shared value types for the cloud egress broker (handoff §20.2, §20.5).

These types are plain data — the broker and the domain layer pass them
across the approval/transfer boundary. Nothing here performs I/O or
makes an authorization decision; that lives in ``broker.py``/``gate.py``
and the studio domain service respectively.

The ``approved`` half of a :class:`TransferOrder` is exactly what an
export manifest + its approval envelope bind (§20.2): source/payload
digests, transformation version, recipient/account/region/environment,
container/runtime digest, permitted job, limits, retention/deletion
expectations, expiry and approver. The ``requested`` half is what a
caller *attempted*. The broker emits bytes only when the two halves
are equal in every bound field — a digest match, never a field
similarity match.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(doc: Mapping[str, Any]) -> str:
    """Deterministic JSON rendering used for bound-input digests
    (sorted keys, compact separators) — byte-identical to
    ``studio.application.idempotency.canonical_json`` so a binding
    digest equals the ledger's ``bound_digest`` exactly."""
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), default=str)


def digest_doc(doc: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(doc).encode("utf-8"))


@dataclass(frozen=True)
class Recipient:
    """The approved destination of an export (§20.2).

    ``environment`` is the approved execution environment identity —
    for the provider-double it is ``double``; production providers stay
    ``not_configured`` until CS-1004 wires a real adapter.
    """

    provider: str
    account: str
    region: str
    environment: str

    def to_dict(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "account": self.account,
            "region": self.region,
            "environment": self.environment,
        }


@dataclass(frozen=True)
class TransferLimits:
    """Bounded transfer envelope and retention expectations (§20.2).

    Every dimension is explicit; the broker refuses a transfer whose
    payload exceeds ``max_bytes`` or whose wall clock exceeds
    ``wall_seconds`` — it never silently widens the approved envelope.
    """

    max_bytes: int
    max_artifacts: int
    wall_seconds: float
    # What the provider is expected to retain and for how long, plus
    # the deletion evidence the reconciler must collect (§20.5).
    retention_expectation: str = "none"
    deletion_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "maxBytes": self.max_bytes,
            "maxArtifacts": self.max_artifacts,
            "wallSeconds": self.wall_seconds,
            "retentionExpectation": self.retention_expectation,
            "deletionRequired": self.deletion_required,
        }


@dataclass(frozen=True)
class ApprovedBinding:
    """The bound-input document an export approval is over (§20.2).

    ``digest()`` over this document is the only comparison the broker
    accepts — field similarity is never enough (AT-1003-1). When the
    caller already holds the ledger's canonical bound-input document
    (e.g. CS-1002's ``bound_inputs``), pass it as ``bound_doc`` so
    ``digest()`` equals the approvals-ledger digest byte-for-byte.
    """

    manifest_digest: str
    payload_digest: str
    payload_fields: tuple[str, ...]
    source_digests: tuple[str, ...]
    transformation_version: str
    classification: str
    recipient: Recipient
    runtime_digest: str
    permitted_job: str
    limits: TransferLimits
    expiry: datetime
    approver: str
    bound_doc: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifestDigest": self.manifest_digest,
            "payloadDigest": self.payload_digest,
            "payloadFields": list(self.payload_fields),
            "sourceDigests": list(self.source_digests),
            "transformationVersion": self.transformation_version,
            "classification": self.classification,
            "recipient": self.recipient.to_dict(),
            "runtimeDigest": self.runtime_digest,
            "permittedJob": self.permitted_job,
            "limits": self.limits.to_dict(),
            "expiry": self.expiry.isoformat(),
            "approver": self.approver,
        }

    def digest(self) -> str:
        if self.bound_doc is not None:
            return digest_doc(self.bound_doc)
        return digest_doc(self.to_dict())


@dataclass(frozen=True)
class TransferOrder:
    """One attempted outbound transfer presented to the broker.

    ``approved`` comes from the manifest+approval; ``requested`` is the
    caller's attempt. The broker compares digests — ``approved.digest()``
    must equal ``requested_digest`` *and* the digest of the presented
    request — before any byte may move.
    """

    approved: ApprovedBinding
    requested_digest: str
    requested_recipient: Recipient
    requested_job: str
    approval_digest: str
    attempt_key: str


@dataclass(frozen=True)
class Permit:
    """A one-shot egress permit issued after successful revalidation.

    The gate accepts a permit exactly once — retries are only ever
    within the same manifest, recipient, expiry and budget (§20.2), so
    each attempt carries its own ``attempt_key`` and the broker refuses
    to re-issue outside those bounds.
    """

    permit_id: str
    attempt_key: str
    payload_digest: str
    recipient: Recipient
    permitted_job: str
    limits: TransferLimits
    expiry: datetime


# ---- attempt + lineage records (all honest, none flattering) --------

ATTEMPT_OUTCOMES = (
    "validated",  # dry-run: fully validated, zero provider contact
    "denied",  # binding/policy check failed BEFORE any byte moved
    "transferred",  # payload bytes accepted by the provider
    "failed",  # provider-side failure after emit
    "cancelled",  # cancel observed before/at emit
)


@dataclass
class AttemptRecord:
    """Append-only lineage of every outbound attempt (§20.2)."""

    attempt_id: str
    attempt_key: str
    outcome: str
    reason: str
    bytes_emitted: int
    job_id: str | None
    created_at: str


@dataclass(frozen=True)
class JobHandle:
    job_id: str
    provider: str
    external_ref: str


@dataclass(frozen=True)
class JobStatus:
    """Provider-reported state — untrusted input folded into lineage."""

    job_id: str
    state: str  # queued|running|succeeded|failed|cancelled|deleted
    bytes_received: int
    artifacts: tuple[str, ...] = ()
    detail: str = ""


@dataclass(frozen=True)
class DeletionReceipt:
    """Actual deletion evidence — only what the provider really
    confirmed (§20.5); unresolved retention items are listed, never
    smoothed over."""

    job_id: str
    deleted: bool
    receipt_ref: str
    unresolved: tuple[str, ...] = ()


@dataclass
class CallbackEvent:
    """One normalized provider callback (untrusted input, AT-1003-3).

    ``callback_id`` is the provider's own delivery identity; ``seq`` is
    its monotonically increasing event number when the provider
    supplies one. Reordering and duplication converge on the same
    recorded lineage — never on duplicated jobs or artifacts.
    """

    callback_id: str
    job_id: str
    event: str
    seq: int | None
    artifacts: tuple[str, ...] = ()
    detail: str = ""


@dataclass
class JobLineage:
    """The single external job/artifact lineage a job converges to."""

    job_id: str
    state: str
    bytes_transferred: int
    artifact_ids: list[str] = field(default_factory=list)
    seen_callback_ids: set[str] = field(default_factory=set)
    last_seq: int | None = None
    exposed: bool = False


@dataclass
class ReconcileReport:
    """What actually happened at the provider — used by cancellation,
    revocation and deletion reconcile paths alike (§20.5)."""

    job_id: str
    state: str
    bytes_transferred: int
    artifact_ids: list[str]
    deletion_receipts: list[DeletionReceipt]
    unresolved_retention: list[str]
    # Already-exposed data is recorded as exposed — reconcile can
    # never truthfully claim it was unseen (AT-1003-2).
    exposed: bool


def utcnow() -> datetime:
    return datetime.now(UTC)
