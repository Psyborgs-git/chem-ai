"""The egress gate — the single bytes boundary (§20.2, AT-1003-1).

Every outbound byte path in this package funnels through
``EgressGate.emit``. The gate independently re-checks the permit
against the payload it is about to release — payload digest,
recipient, job kind, byte limits and expiry — so a denied transfer
emits *zero* proprietary bytes even if a caller reaches for the
provider directly. A permit is single-use: once emitted, the same
attempt can never emit again; a new attempt needs a fresh permit
inside the same manifest/recipient/expiry/budget bound.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cloud_broker.providers import CloudProvider
from cloud_broker.types import JobHandle, Permit, sha256_bytes, utcnow


class EgressDenied(Exception):
    """Raised at the boundary *before* any byte moves."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class EgressGate:
    """Serializes permit checks and emission. In-memory by design —
    the domain layer persists the attempt ledger it cares about; the
    gate's job is narrower: never let an unpermitted byte through."""

    _spent_permits: set[str] = field(default_factory=set)

    def check(self, permit: Permit, payload: bytes) -> None:
        """Pure validation — used by dry-run so the check path is
        identical to the emit path (no divergent policy)."""
        if permit.permit_id in self._spent_permits:
            raise EgressDenied("permit already spent")
        if permit.expiry <= utcnow():
            raise EgressDenied("permit expired")
        if sha256_bytes(payload) != permit.payload_digest:
            raise EgressDenied("payload digest differs from the approved binding")
        if len(payload) > permit.limits.max_bytes:
            raise EgressDenied("payload exceeds approved byte limit")

    def emit(self, permit: Permit, provider: CloudProvider, payload: bytes) -> JobHandle:
        """Check, then — and only then — hand bytes to the provider.

        The permit is marked spent *before* submit so a failing submit
        can never be silently retried outside the attempt bounds; the
        attempt ledger records the failure honestly instead.
        """
        self.check(permit, payload)
        self._spent_permits.add(permit.permit_id)
        return provider.submit(
            recipient=permit.recipient,
            job=permit.permitted_job,
            payload=payload,
        )
