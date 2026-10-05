"""Authoritative Run records and queue bookkeeping (§7.3, §7.4, §13).

The Run row — not the queue job — is the record of truth. Queue
payloads carry scoped record IDs only; workers re-load state from the
authoritative rows. Every status change is a compare-and-swap through
``_ALLOWED`` so a late callback can never resurrect a terminal run.
A worker lost mid-run becomes ``interrupted``; reconciliation may
requeue as a *new* attempt only under policy (bounded retries).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from studio.application.idempotency import canonical_json, request_digest
from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext
from studio.errors import DomainError, ErrorCode, not_found
from studio.events.outbox import publish
from studio.persistence.models import (
    RUN_TERMINAL,
    Run,
    RunAttempt,
)

MAX_REQUEST_BYTES = 4096  # scoped IDs + bounded metadata only (§7.4)

TERMINAL = frozenset(RUN_TERMINAL)

# Compare-and-swap transition map (§7.3). Anything not listed is
# rejected; in particular no path leads *out* of a terminal status —
# retry happens via a new attempt, and a blocked run must be
# re-requested explicitly after its inputs are fixed.
_ALLOWED: dict[str, frozenset[str]] = {
    "requested": frozenset(
        {"awaiting_approval", "queued", "blocked", "cancel_requested", "cancelled"}
    ),
    "awaiting_approval": frozenset({"queued", "blocked", "cancel_requested", "cancelled"}),
    "queued": frozenset({"running", "cancel_requested", "cancelled", "interrupted"}),
    "running": frozenset(
        {
            # "queued" re-enters the queue after a classified transient
            # failure — the failed attempt row stays for audit.
            "queued",
            "succeeded",
            "failed",
            "timed_out",
            "cancel_requested",
            "cancelled",
            "interrupted",
        }
    ),
    "cancel_requested": frozenset({"cancelled", "succeeded", "failed", "timed_out"}),
    "interrupted": frozenset({"queued", "cancelled", "failed"}),
    "blocked": frozenset({"requested", "cancelled"}),
}

ATTEMPT_TERMINAL = frozenset({"succeeded", "failed", "timed_out", "cancelled", "interrupted"})


class RunService:
    """Scoped run bookkeeping. All mutations run in the caller's
    transaction alongside outbox events and audit records."""

    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    # -- request ------------------------------------------------------

    def request(
        self,
        *,
        kind: str,
        request: dict[str, Any],
        task_id: uuid.UUID | None = None,
        max_attempts: int = 3,
        deadline_at: datetime | None = None,
        requires_approval: bool = False,
    ) -> Run:
        """Persist a requested run. ``request`` must serialize to at
        most ``MAX_REQUEST_BYTES`` of canonical JSON — it carries
        scoped record IDs and bounded metadata, never payloads."""
        self.ctx.require("request_compute", task_id)
        if not isinstance(request, dict):
            raise DomainError(ErrorCode.VALIDATION, "request must be an object")
        encoded = canonical_json(request).encode()
        if len(encoded) > MAX_REQUEST_BYTES:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"run request exceeds {MAX_REQUEST_BYTES} bytes of bounded metadata",
                field_path="request",
            )
        if task_id is not None:
            from studio.persistence.models import ResearchTask

            task = self.db.execute(
                select(ResearchTask).where(
                    ResearchTask.workspace_id == self.ctx.workspace_id,
                    ResearchTask.id == task_id,
                )
            ).scalar_one_or_none()
            if task is None:
                raise not_found("task")
        run = Run(
            workspace_id=self.ctx.workspace_id,
            task_id=task_id,
            kind=kind,
            status="awaiting_approval" if requires_approval else "requested",
            request=request,
            request_digest=request_digest(request),
            requested_by=self.ctx.principal_id,
            max_attempts=max_attempts,
            deadline_at=deadline_at,
        )
        self.db.add(run)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="run.requested",
            target_type="run",
            target_id=run.id,
            detail={"kind": kind, "digest": run.request_digest},
        )
        return run

    # -- enqueue / accept (queue boundary) ----------------------------

    def enqueue(self, run_id: uuid.UUID, *, queue_name: str = "runs") -> RunAttempt:
        """requested/awaiting_approval/interrupted -> queued; creates the
        next attempt and enqueues ``run.attempt.enqueued`` in the same
        transaction. The event payload is IDs only."""
        run = self._get_for_update(run_id)
        self._transition(run, "queued")
        run.queued_at = datetime.now(UTC)
        attempt = RunAttempt(
            workspace_id=self.ctx.workspace_id,
            run_id=run.id,
            attempt_number=run.attempt_count + 1,
            queue_name=queue_name,
        )
        run.attempt_count += 1
        self.db.add(attempt)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="run",
            aggregate_id=run.id,
            event_type="run.attempt.enqueued",
            payload={
                "runId": str(run.id),
                "taskId": str(run.task_id),
                "attemptId": str(attempt.id),
                "kind": run.kind,
                "queue": queue_name,
            },
        )
        return attempt

    def accept_attempt(
        self,
        *,
        run_id: uuid.UUID,
        attempt_id: uuid.UUID,
        external_id: str,
        worker_id: str | None = None,
    ) -> RunAttempt:
        """Worker-side acceptance — idempotent under at-least-once
        delivery (AT-0401-1). Recording the same ``external_id`` twice
        yields the same attempt row; a *different* external id for an
        already-accepted attempt is rejected, never a second attempt."""
        attempt = self._attempt(run_id, attempt_id)
        if attempt.external_id is not None:
            if attempt.external_id != external_id:
                raise DomainError(
                    ErrorCode.CONFLICT,
                    "attempt already bound to a different external job id",
                    retryable=False,
                )
            return attempt
        attempt.external_id = external_id
        if worker_id:
            attempt.worker_id = worker_id
        try:
            self.db.flush()
        except IntegrityError:
            # The unique constraint on (workspace_id, external_id)
            # fired: another attempt already carries this job id.
            self.db.rollback()
            raise DomainError(
                ErrorCode.CONFLICT,
                "external job id already claimed by another attempt",
                retryable=False,
            ) from None
        return attempt

    # -- execution lifecycle ------------------------------------------

    def start_attempt(
        self, *, run_id: uuid.UUID, attempt_id: uuid.UUID, worker_id: str | None = None
    ) -> RunAttempt:
        run = self._get_for_update(run_id)
        attempt = self._attempt(run_id, attempt_id)
        if attempt.status != "queued" or run.status not in {"queued", "cancel_requested"}:
            raise DomainError(ErrorCode.CONFLICT, "attempt is not startable")
        attempt.status = "running"
        attempt.started_at = datetime.now(UTC)
        if worker_id:
            attempt.worker_id = worker_id
        if run.status == "queued":
            self._transition(run, "running")
            run.started_at = datetime.now(UTC)
        self.db.flush()
        return attempt

    def complete_attempt(
        self,
        *,
        run_id: uuid.UUID,
        attempt_id: uuid.UUID,
        result_summary: dict[str, Any] | None = None,
    ) -> Run:
        """Attempt reported success. A late success after a terminal
        state (e.g. cancelled) is recorded as a callback — never
        applied (AT-0401-3)."""
        run = self._get_for_update(run_id)
        attempt = self._attempt(run_id, attempt_id)
        if run.status in TERMINAL:
            self._late_callback(attempt, "succeeded")
            return run
        if attempt.status != "running":
            self._late_callback(attempt, "succeeded")
            return run
        attempt.status = "succeeded"
        attempt.finished_at = datetime.now(UTC)
        run.result_summary = result_summary or {}
        self._transition(run, "succeeded")
        run.finished_at = datetime.now(UTC)
        self.db.flush()
        return run

    def fail_attempt(
        self,
        *,
        run_id: uuid.UUID,
        attempt_id: uuid.UUID,
        code: str,
        message: str,
        retryable: bool = False,
    ) -> Run:
        """Attempt failed. ``retryable`` marks a classified transient
        infrastructure error; retries are requeued by ``reconcile`` or
        ``retry`` under policy — never automatic, never for scientific
        failures (§13.4)."""
        run = self._get_for_update(run_id)
        attempt = self._attempt(run_id, attempt_id)
        if run.status in TERMINAL:
            self._late_callback(attempt, "failed", {"code": code})
            return run
        if attempt.status not in {"queued", "running"}:
            self._late_callback(attempt, "failed", {"code": code})
            return run
        attempt.status = "failed"
        attempt.finished_at = datetime.now(UTC)
        attempt.error = {"code": code, "message": message, "retryable": retryable}
        run.error = {"code": code, "message": message}
        if retryable and run.attempt_count < run.max_attempts and run.status != "cancel_requested":
            # Classified transient: requeue as a NEW attempt under
            # policy; the run returns to queued rather than failing.
            self._transition(run, "queued")
            nxt = RunAttempt(
                workspace_id=self.ctx.workspace_id,
                run_id=run.id,
                attempt_number=run.attempt_count + 1,
                queue_name=attempt.queue_name,
            )
            run.attempt_count += 1
            self.db.add(nxt)
            self.db.flush()
            publish(
                self.db,
                self.ctx.workspace_id,
                aggregate_type="run",
                aggregate_id=run.id,
                event_type="run.attempt.enqueued",
                payload={
                    "runId": str(run.id),
                    "taskId": str(run.task_id),
                    "attemptId": str(nxt.id),
                    "kind": run.kind,
                    "queue": nxt.queue_name,
                    "retry": True,
                },
            )
        else:
            self._transition(run, "failed")
            run.finished_at = datetime.now(UTC)
        self.db.flush()
        return run

    def timeout_attempt(self, *, run_id: uuid.UUID, attempt_id: uuid.UUID) -> Run:
        run = self._get_for_update(run_id)
        attempt = self._attempt(run_id, attempt_id)
        if run.status in TERMINAL:
            self._late_callback(attempt, "timed_out")
            return run
        if attempt.status in ATTEMPT_TERMINAL:
            self._late_callback(attempt, "timed_out")
            return run
        attempt.status = "timed_out"
        attempt.finished_at = datetime.now(UTC)
        run.error = {"code": "timed_out", "message": "attempt exceeded its envelope"}
        self._transition(run, "timed_out")
        run.finished_at = datetime.now(UTC)
        self.db.flush()
        return run

    # -- cancellation --------------------------------------------------

    def request_cancel(self, run_id: uuid.UUID) -> Run:
        """queued/running -> cancel_requested. Visible until execution
        actually stops; an acknowledgment is not proof the children
        stopped (§7.3)."""
        run = self._get_for_update(run_id)
        self._transition(run, "cancel_requested")
        run.cancel_requested_at = datetime.now(UTC)
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="run",
            aggregate_id=run.id,
            event_type="run.cancel.requested",
            payload={"runId": str(run.id)},
        )
        self.db.flush()
        return run

    def confirm_cancelled(self, run_id: uuid.UUID) -> Run:
        """Terminal cancellation: allowed from any non-terminal status
        once execution has actually stopped (worker reports the process
        tree dead, or a queued attempt is dropped before start)."""
        run = self._get_for_update(run_id)
        self._transition(run, "cancelled")
        run.finished_at = datetime.now(UTC)
        attempt = self._current_attempt(run.id)
        if attempt is not None and attempt.status not in ATTEMPT_TERMINAL:
            attempt.status = "cancelled"
            attempt.finished_at = datetime.now(UTC)
        self.db.flush()
        return run

    # -- reconciliation -------------------------------------------------

    def reconcile(self, *, stale_before: datetime, retry_transient: bool = True) -> list[Run]:
        """Runs whose live attempt has gone silent past ``stale_before``
        become ``interrupted`` — never falsely ``succeeded`` (AT-0401-2).
        Under policy an interrupted run is requeued as a NEW attempt;
        the interrupted attempt row is preserved for audit."""
        stale = (
            self.db.execute(
                select(Run)
                .where(
                    Run.workspace_id == self.ctx.workspace_id,
                    Run.status.in_(["queued", "running"]),
                )
                .with_for_update()
                .order_by(Run.id)
            )
            .scalars()
            .all()
        )
        reconciled: list[Run] = []
        now = datetime.now(UTC)
        for run in stale:
            attempt = self._current_attempt(run.id)
            if attempt is None or attempt.status in ATTEMPT_TERMINAL:
                continue
            marker = attempt.started_at or attempt.enqueued_at
            if marker is None or marker >= stale_before:
                continue
            attempt.status = "interrupted"
            attempt.finished_at = now
            attempt.error = {"code": "worker_lost", "message": "worker heartbeat expired"}
            self._transition(run, "interrupted")
            audit_record(
                self.db,
                self.ctx,
                action="run.interrupted",
                target_type="run",
                target_id=run.id,
                detail={"attemptId": str(attempt.id), "kind": run.kind},
            )
            if retry_transient and run.attempt_count < run.max_attempts:
                self._transition(run, "queued")
                nxt = RunAttempt(
                    workspace_id=self.ctx.workspace_id,
                    run_id=run.id,
                    attempt_number=run.attempt_count + 1,
                    queue_name=attempt.queue_name,
                )
                run.attempt_count += 1
                self.db.add(nxt)
                self.db.flush()
                publish(
                    self.db,
                    self.ctx.workspace_id,
                    aggregate_type="run",
                    aggregate_id=run.id,
                    event_type="run.attempt.enqueued",
                    payload={
                        "runId": str(run.id),
                        "taskId": str(run.task_id),
                        "attemptId": str(nxt.id),
                        "kind": run.kind,
                        "queue": nxt.queue_name,
                        "reconciled": True,
                    },
                )
            reconciled.append(run)
        self.db.flush()
        return reconciled

    def block(self, run_id: uuid.UUID, *, reason: str, detail: dict[str, Any]) -> Run:
        """requested/awaiting_approval -> blocked: the request cannot be
        admitted locally (unsupported engine, insufficient inputs, or no
        compatible resource envelope). Blocked is reported, never
        silently routed elsewhere (§7.3, §20.1)."""
        run = self._get_for_update(run_id)
        self._transition(run, "blocked")
        run.error = {"code": "blocked", "message": reason, "detail": detail}
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="run",
            aggregate_id=run.id,
            event_type="run.blocked",
            payload={"runId": str(run.id), "taskId": str(run.task_id), "reason": reason},
        )
        self.db.flush()
        return run

    # -- internals ------------------------------------------------------

    def get(self, run_id: uuid.UUID) -> Run:
        return self._get(run_id)

    def _get(self, run_id: uuid.UUID) -> Run:
        run = self.db.execute(
            select(Run).where(Run.workspace_id == self.ctx.workspace_id, Run.id == run_id)
        ).scalar_one_or_none()
        if run is None:
            raise not_found("run")
        return run

    def _get_for_update(self, run_id: uuid.UUID) -> Run:
        run = self.db.execute(
            select(Run)
            .where(Run.workspace_id == self.ctx.workspace_id, Run.id == run_id)
            .with_for_update()
        ).scalar_one_or_none()
        if run is None:
            raise not_found("run")
        return run

    def _attempt(self, run_id: uuid.UUID, attempt_id: uuid.UUID) -> RunAttempt:
        attempt = self.db.execute(
            select(RunAttempt).where(
                RunAttempt.workspace_id == self.ctx.workspace_id,
                RunAttempt.run_id == run_id,
                RunAttempt.id == attempt_id,
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise not_found("run attempt")
        return attempt

    def _current_attempt(self, run_id: uuid.UUID) -> RunAttempt | None:
        return self.db.execute(
            select(RunAttempt)
            .where(
                RunAttempt.workspace_id == self.ctx.workspace_id,
                RunAttempt.run_id == run_id,
            )
            .order_by(RunAttempt.attempt_number.desc())
            .limit(1)
        ).scalar_one_or_none()

    def _transition(self, run: Run, to: str) -> None:
        allowed = _ALLOWED.get(run.status, frozenset())
        if to not in allowed:
            raise DomainError(
                ErrorCode.CONFLICT,
                f"run cannot transition {run.status} -> {to}",
                retryable=False,
            )
        run.status = to
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="run",
            aggregate_id=run.id,
            event_type="run.status.changed",
            payload={
                "runId": str(run.id),
                "taskId": str(run.task_id),
                "status": to,
            },
        )

    def _late_callback(
        self, attempt: RunAttempt, outcome: str, extra: dict[str, Any] | None = None
    ) -> None:
        """Preserve a callback that arrived too late to apply — the
        callback itself is evidence (§7.3) but must not mutate state."""
        callbacks = list(attempt.callbacks)
        callbacks.append(
            {
                "outcome": outcome,
                "at": datetime.now(UTC).isoformat(),
                "applied": False,
                **(extra or {}),
            }
        )
        attempt.callbacks = callbacks
        self.db.flush()


__all__ = ["TERMINAL", "RunService"]
