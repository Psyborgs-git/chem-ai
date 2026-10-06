"""The egress broker — the only outbound path (§20.2, §20.5).

Responsibilities, in the ticket's order:

1. **Binding.** ``_validate`` requires the attempted transfer's digest
   to equal the approved binding's digest *and* the approval digest —
   exact payload/provider/account/region/environment/limits/expiry,
   never field similarity (AT-1003-1). Revalidation happens
   immediately before every emit attempt, and retries are only within
   the same manifest, recipient, expiry and budget.
2. **Single egress.** ``transfer`` is the only way bytes can leave;
   ``dry_run`` runs the identical validation with zero provider
   contact. ``cancel``, ``reconcile`` and ``delete`` return real
   receipts — what the provider actually holds, transferred or
   deleted, with unresolved retention items listed.
3. **Untrusted returns.** Provider callbacks are normalized and folded
   into one lineage idempotently (AT-1003-3); returned artifacts are
   references to confidential, unvalidated derived data — the domain
   layer stages them into the vault only after local validation.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from cloud_broker.double import ProviderDouble
from cloud_broker.gate import EgressDenied, EgressGate
from cloud_broker.providers import CloudProvider, get_provider
from cloud_broker.types import (
    AttemptRecord,
    CallbackEvent,
    DeletionReceipt,
    JobHandle,
    JobLineage,
    Permit,
    ReconcileReport,
    TransferOrder,
    utcnow,
)

# Provider-event ordering for lineage convergence. Terminal states are
# absorbing — a replayed or crossed callback can add artifact lineage
# but can never regress a finished job or duplicate it.
_EVENT_RANK = {
    "submitted": 1,
    "queued": 2,
    "running": 3,
    "succeeded": 4,
    "failed": 4,
    "cancelled": 4,
    "deleted": 5,
}
_TERMINAL = {"succeeded", "failed", "cancelled", "deleted"}


@dataclass(frozen=True)
class ValidationReport:
    """Dry-run outcome: every check that ran, all pass/fail — no bytes."""

    ok: bool
    checks: tuple[tuple[str, bool, str], ...]


class TransferDenied(Exception):
    """A binding/policy check failed before the boundary — zero bytes
    were emitted. The reason is recorded on the attempt ledger."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class EgressBroker:
    """One broker, one gate, honest ledgers."""

    def __init__(
        self,
        *,
        providers: dict[str, CloudProvider] | None = None,
        gate: EgressGate | None = None,
    ) -> None:
        self._providers = providers if providers is not None else {}
        self._gate = gate or EgressGate()
        self._permit_ids = itertools.count(1)
        self._attempt_ids = itertools.count(1)
        self._attempts: list[AttemptRecord] = []
        self._lineages: dict[str, JobLineage] = {}
        self._handles: dict[str, JobHandle] = {}
        self._job_attempts: dict[str, str] = {}
        self._revoked_digests: set[str] = set()

    # ------------------------------------------------------------ reads

    @property
    def attempts(self) -> list[AttemptRecord]:
        return list(self._attempts)

    def lineage(self, job_id: str) -> JobLineage | None:
        return self._lineages.get(job_id)

    def seed_lineage(self, lineage: JobLineage) -> JobLineage:
        """Restore a persisted lineage (e.g. after a process restart)
        so callback folding continues where the ledger left off — the
        seeded state is a floor: real callbacks only advance it."""
        existing = self._lineages.get(lineage.job_id)
        if existing is not None:
            return existing
        self._lineages[lineage.job_id] = lineage
        return lineage

    # -------------------------------------------------------- validation

    def _checks(self, order: TransferOrder, payload: bytes) -> list[tuple[str, bool, str]]:
        """Every binding check, always all of them — a dry-run shows the
        caller exactly what would pass and what would not."""
        from cloud_broker.types import sha256_bytes

        approved = order.approved
        checks: list[tuple[str, bool, str]] = []

        def check(name: str, ok: bool, detail: str) -> None:
            checks.append((name, ok, detail))

        check(
            "approval_digest_matches_binding",
            order.approval_digest == approved.digest(),
            "approval must bind this exact manifest binding",
        )
        check(
            "requested_digest_matches_approved",
            order.requested_digest == approved.digest(),
            "attempted payload/recipient differs from approval",
        )
        check(
            "recipient_matches",
            order.requested_recipient == approved.recipient,
            "attempted recipient differs from approval",
        )
        check(
            "job_matches",
            order.requested_job == approved.permitted_job,
            "attempted job is not the permitted job",
        )
        check(
            "payload_digest_matches",
            sha256_bytes(payload) == approved.payload_digest,
            "payload bytes differ from the approved payload",
        )
        check(
            "within_byte_limit",
            len(payload) <= approved.limits.max_bytes,
            "payload exceeds the approved byte limit",
        )
        check(
            "not_expired",
            approved.expiry > utcnow(),
            "approved binding expired",
        )
        check(
            "binding_not_revoked",
            order.approval_digest not in self._revoked_digests,
            "approval was revoked",
        )
        return checks

    def _validate_or_raise(self, order: TransferOrder, payload: bytes) -> None:
        failures = [
            f"{name}: {detail}" for name, ok, detail in self._checks(order, payload) if not ok
        ]
        if failures:
            raise TransferDenied("; ".join(failures))

    # ------------------------------------------------------------- API

    def dry_run(self, order: TransferOrder, payload: bytes) -> ValidationReport:
        """Full validation with zero provider contact — the preview a
        reviewer gets before a transfer is ever attempted."""
        checks = tuple(self._checks(order, payload))
        self._record(
            order, "validated" if all(ok for _, ok, _ in checks) else "denied", "dry-run", 0, None
        )
        return ValidationReport(ok=all(ok for _, ok, _ in checks), checks=checks)

    def transfer(
        self,
        order: TransferOrder,
        payload: bytes,
        *,
        provider: CloudProvider | None = None,
    ) -> JobHandle | None:
        """Attempt one outbound transfer.

        Denied orders emit *zero* bytes — validation completes before
        the gate is even reached, and the gate itself re-checks digest,
        recipient and expiry at the boundary. Every attempt lands on
        the ledger with its outcome and the bytes that actually moved.
        """
        try:
            self._validate_or_raise(order, payload)
        except TransferDenied as exc:
            self._record(order, "denied", exc.reason, 0, None)
            return None

        try:
            target = (
                provider
                or self._providers.get(order.approved.recipient.provider)
                or get_provider(order.approved.recipient.provider)
            )
        except Exception as exc:
            # No adapter under the approved name — production providers
            # stay ``not_configured`` and that lands honestly on the
            # ledger as a failed attempt, never an exception silently
            # crossing the boundary.
            self._record(order, "failed", f"{type(exc).__name__}: {exc}", 0, None)
            return None
        permit = Permit(
            permit_id=f"permit-{next(self._permit_ids)}",
            attempt_key=order.attempt_key,
            payload_digest=order.approved.payload_digest,
            recipient=order.approved.recipient,
            permitted_job=order.approved.permitted_job,
            limits=order.approved.limits,
            expiry=order.approved.expiry,
        )
        try:
            handle = self._gate.emit(permit, target, payload)
        except EgressDenied as exc:
            self._record(order, "denied", exc.reason, 0, None)
            return None
        except Exception as exc:  # provider-side failure, honestly recorded
            self._record(order, "failed", f"{type(exc).__name__}: {exc}", 0, None)
            return None

        self._handles[handle.job_id] = handle
        self._job_attempts[handle.job_id] = order.attempt_key
        self._lineages[handle.job_id] = JobLineage(
            job_id=handle.job_id,
            state="submitted",
            bytes_transferred=len(payload),
            exposed=len(payload) > 0,
        )
        self._record(
            order, "transferred", "payload accepted by provider", len(payload), handle.job_id
        )
        # Fold any callbacks the provider has already queued — the
        # lineage starts converging from the first poll.
        for cb in target.drain_callbacks(handle):
            self.handle_callback(cb)
        return handle

    def cancel(self, job_id: str) -> ReconcileReport:
        """Best-effort cancel + honest reconcile (§20.5): what was
        already transferred is recorded as exposed — never 'unseen'."""
        provider = self._provider_for(job_id)
        provider.cancel(self._handles[job_id])
        return self.reconcile(job_id)

    def reconcile(self, job_id: str) -> ReconcileReport:
        """Fold pending callbacks, then report the provider's actual
        state — bytes it holds, artifacts it returned, retention items
        still unresolved."""
        provider = self._provider_for(job_id)
        handle = self._handles[job_id]
        for cb in provider.drain_callbacks(handle):
            self.handle_callback(cb)
        status = provider.status(handle)
        lineage = self._lineages[job_id]
        if status.state == "deleted":
            lineage.state = "deleted"
        unresolved: list[str] = []
        if status.state != "deleted" and status.bytes_received > 0:
            unresolved.append("provider still retains submitted payload bytes")
        return ReconcileReport(
            job_id=job_id,
            state=status.state,
            bytes_transferred=status.bytes_received,
            artifact_ids=list(lineage.artifact_ids),
            deletion_receipts=[],
            unresolved_retention=unresolved,
            exposed=lineage.exposed,
        )

    def delete(self, job_id: str) -> DeletionReceipt:
        """Request deletion and record the actual receipt (§20.5)."""
        provider = self._provider_for(job_id)
        receipt = provider.delete(self._handles[job_id])
        for cb in provider.drain_callbacks(self._handles[job_id]):
            self.handle_callback(cb)
        lineage = self._lineages[job_id]
        if receipt.deleted:
            lineage.state = "deleted"
        return receipt

    # ----------------------------------------------------- revocation

    def revoke_binding(self, approval_digest: str) -> None:
        """Mark an approval binding revoked: every later transfer
        attempt carrying it is denied before the boundary (§20.5 —
        'before transfer, revocation blocks the job')."""
        self._revoked_digests.add(approval_digest)

    # ----------------------------------------------------- callbacks

    def handle_callback(self, cb: CallbackEvent) -> bool:
        """Fold one provider callback into the job lineage.

        Idempotent (AT-1003-3): a repeated callback id is dropped;
        reordered or crossed events converge on the same terminal
        state; artifact lineage unions by id and never duplicates.
        Returns True when the callback changed the lineage.
        """
        lineage = self._lineages.get(cb.job_id)
        if lineage is None:
            return False
        if cb.callback_id in lineage.seen_callback_ids:
            return False
        lineage.seen_callback_ids.add(cb.callback_id)
        rank = _EVENT_RANK.get(cb.event, 0)
        current = _EVENT_RANK.get(lineage.state, 0)
        if lineage.state not in _TERMINAL and rank > current:
            lineage.state = cb.event
        if cb.seq is not None:
            lineage.last_seq = max(lineage.last_seq or 0, cb.seq)
        for artifact in cb.artifacts:
            if artifact not in lineage.artifact_ids:
                lineage.artifact_ids.append(artifact)
        return True

    # -------------------------------------------------------- internals

    def _provider_for(self, job_id: str) -> CloudProvider:
        handle = self._handles.get(job_id)
        if handle is None:
            raise KeyError(f"unknown external job {job_id}")
        provider = self._providers.get(handle.provider)
        if provider is None:
            provider = get_provider(handle.provider)
        return provider

    def _record(
        self,
        order: TransferOrder,
        outcome: str,
        reason: str,
        bytes_emitted: int,
        job_id: str | None,
    ) -> None:
        self._attempts.append(
            AttemptRecord(
                attempt_id=f"attempt-{next(self._attempt_ids)}",
                attempt_key=order.attempt_key,
                outcome=outcome,
                reason=reason,
                bytes_emitted=bytes_emitted,
                job_id=job_id,
                created_at=utcnow().isoformat(),
            )
        )


__all__ = [
    "EgressBroker",
    "ProviderDouble",
    "TransferDenied",
    "ValidationReport",
]
