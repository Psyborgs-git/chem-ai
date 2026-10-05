"""CS-0401 integration tests — authoritative Run records + queue.

AT-0401-1  outbox event delivered twice → one logical run, idempotent attempts
AT-0401-2  worker dies mid-run → interrupted/reconciled, never falsely succeeded
AT-0401-3  canceled run + late success callback → terminal cancellation holds
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session
from workers.common.queue import AttemptRunner, defer_attempt, make_app

from studio.auth.context import load_context
from studio.domain.runs.queue import RunService
from studio.errors import DomainError, ErrorCode
from studio.events.outbox import deliver_pending
from studio.persistence.models import (
    OutboxEvent,
    Principal,
    PrincipalCapability,
    Run,
    RunAttempt,
    Workspace,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def env(session: Session):
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    user = Principal(workspace_id=ws.id, kind="user", login="r", display_name="r")
    session.add(user)
    session.flush()
    for cap in sorted(capabilities_for_role("researcher")):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=user.id, capability=cap))
    session.flush()
    ctx = load_context(session, ws.id, user.id)
    return {"ws": ws, "ctx": ctx, "svc": RunService(session, ctx)}


def _queued(env) -> tuple[Run, RunAttempt]:
    run = env["svc"].request(kind="simulation", request={"candidateRevisionId": str(uuid.uuid4())})
    attempt = env["svc"].enqueue(run.id)
    return run, attempt


def _defer(env, attempt: RunAttempt) -> str:
    """Enqueue onto a real Procrastinate connector and return the job id."""
    app = make_app()
    return defer_attempt(
        app,
        workspace_id=env["ws"].id,
        run_id=attempt.run_id,
        attempt_id=attempt.id,
    )


# AT-0401-1 -----------------------------------------------------------


def test_duplicate_delivery_one_logical_run(env, session: Session) -> None:
    """The outbox event is delivered twice (at-least-once); the worker
    still binds a single attempt and executes it once."""
    run, attempt = _queued(env)
    events = (
        session.execute(select(OutboxEvent).where(OutboxEvent.event_type == "run.attempt.enqueued"))
        .scalars()
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload
    # Queue payloads are scoped IDs + bounded metadata only.
    assert payload["runId"] == str(run.id)
    assert payload["attemptId"] == str(attempt.id)
    assert len(str(payload)) < 512

    external_id = _defer(env, attempt)
    calls: list[tuple] = []
    runner = AttemptRunner(
        env["svc"], executor=lambda rid, att: calls.append((rid, att.id)) or {"ok": True}
    )

    # First delivery: accept → start → succeed.
    runner.handle(
        workspace_id=env["ws"].id,
        run_id=run.id,
        attempt_id=attempt.id,
        external_id=external_id,
    )
    session.flush()
    session.refresh(run)
    assert run.status == "succeeded"
    assert run.attempt_count == 1
    assert len(calls) == 1

    # Second delivery of the same event: redelivery is a no-op —
    # same attempt row, executor never invoked again.
    runner.handle(
        workspace_id=env["ws"].id,
        run_id=run.id,
        attempt_id=attempt.id,
        external_id=external_id,
    )
    session.flush()
    session.refresh(run)
    attempts = (
        session.execute(select(RunAttempt).where(RunAttempt.run_id == run.id)).scalars().all()
    )
    assert len(attempts) == 1
    assert attempts[0].external_id == external_id
    assert len(calls) == 1
    assert run.status == "succeeded"


def test_accept_rejects_conflicting_external_id(env) -> None:
    """A *different* job id for the same attempt is a conflict, never a
    second attempt (reconcile-before-retry, §7.4)."""
    run, attempt = _queued(env)
    env["svc"].accept_attempt(run_id=run.id, attempt_id=attempt.id, external_id="job-1")
    with pytest.raises(DomainError) as exc:
        env["svc"].accept_attempt(run_id=run.id, attempt_id=attempt.id, external_id="job-2")
    assert exc.value.code == ErrorCode.CONFLICT


def test_outbox_delivery_ledger_dedupes(env, session: Session) -> None:
    """deliver_pending itself only hands each event to a consumer once."""
    _queued(env)
    seen: list[uuid.UUID] = []
    first = deliver_pending(
        session,
        env["ws"].id,
        consumer="run-queue",
        handler=lambda e: seen.append(e.id),
    )
    second = deliver_pending(
        session,
        env["ws"].id,
        consumer="run-queue",
        handler=lambda e: seen.append(e.id),
    )
    assert first >= 1
    assert second == 0


# AT-0401-2 -----------------------------------------------------------


def test_dead_worker_reconciled_not_succeeded(env, session: Session) -> None:
    """A worker that dies mid-run leaves the attempt running; after the
    heartbeat expires, reconciliation marks it interrupted and requeues
    a NEW attempt under policy — it can never be reported succeeded."""
    run, attempt = _queued(env)
    env["svc"].accept_attempt(run_id=run.id, attempt_id=attempt.id, external_id="job-9")
    env["svc"].start_attempt(run_id=run.id, attempt_id=attempt.id, worker_id="w-1")
    session.flush()

    # Worker dies — no callback ever arrives. Reconcile with a stale
    # threshold after the attempt's timestamps.
    stale = datetime.now(UTC) + timedelta(seconds=1)
    reconciled = env["svc"].reconcile(stale_before=stale)
    session.flush()
    session.refresh(run)
    session.refresh(attempt)

    assert run in reconciled
    assert attempt.status == "interrupted"
    # Policy requeued a fresh attempt: run is queued again, attempt 2 exists.
    assert run.status == "queued"
    assert run.attempt_count == 2
    retry = (
        session.execute(
            select(RunAttempt).where(RunAttempt.run_id == run.id, RunAttempt.attempt_number == 2)
        )
        .scalars()
        .one()
    )
    assert retry.status == "queued"


def test_interrupted_run_can_cancel(env) -> None:
    run, attempt = _queued(env)
    env["svc"].start_attempt(run_id=run.id, attempt_id=attempt.id)
    env["svc"].reconcile(stale_before=datetime.now(UTC) + timedelta(seconds=1))
    run = env["svc"].request_cancel(run.id)
    run = env["svc"].confirm_cancelled(run.id)
    assert run.status == "cancelled"


# AT-0401-3 -----------------------------------------------------------


def test_late_success_cannot_overwrite_cancellation(env, session: Session) -> None:
    """Terminal cancellation is final: a late success callback from the
    subprocess is recorded as a callback, never applied (§7.3)."""
    run, attempt = _queued(env)
    env["svc"].accept_attempt(run_id=run.id, attempt_id=attempt.id, external_id="job-late")
    env["svc"].start_attempt(run_id=run.id, attempt_id=attempt.id)

    run = env["svc"].request_cancel(run.id)
    assert run.status == "cancel_requested"
    run = env["svc"].confirm_cancelled(run.id)
    assert run.status == "cancelled"
    session.refresh(attempt)
    assert attempt.status == "cancelled"

    # The late success callback arrives — state must not move.
    run = env["svc"].complete_attempt(
        run_id=run.id, attempt_id=attempt.id, result_summary={"ok": True}
    )
    session.flush()
    session.refresh(run)
    session.refresh(attempt)
    assert run.status == "cancelled"
    assert run.result_summary is None
    assert attempt.status == "cancelled"
    assert attempt.callbacks[-1]["outcome"] == "succeeded"
    assert attempt.callbacks[-1]["applied"] is False


def test_terminal_run_rejects_late_failure_and_success(env) -> None:
    run, attempt = _queued(env)
    env["svc"].start_attempt(run_id=run.id, attempt_id=attempt.id)
    env["svc"].complete_attempt(run_id=run.id, attempt_id=attempt.id, result_summary={"ok": True})
    run = env["svc"].fail_attempt(
        run_id=run.id, attempt_id=attempt.id, code="late", message="late fail"
    )
    assert run.status == "succeeded"
    assert attempt.callbacks[-1]["outcome"] == "failed"
    assert attempt.callbacks[-1]["applied"] is False


# Bounded request + transitions ----------------------------------------


def test_request_bounded_metadata(env) -> None:
    """The queue/run request carries IDs and bounded metadata only —
    oversized payloads are refused before persistence (§7.4)."""
    with pytest.raises(DomainError) as exc:
        env["svc"].request(kind="simulation", request={"blob": "x" * 8192})
    assert exc.value.code == ErrorCode.VALIDATION


def test_transient_failure_requeues_under_policy(env) -> None:
    """A classified transient infra error requeues as a NEW attempt;
    the failed attempt row is preserved (§13.4)."""
    run, attempt = _queued(env)
    env["svc"].start_attempt(run_id=run.id, attempt_id=attempt.id)
    run = env["svc"].fail_attempt(
        run_id=run.id,
        attempt_id=attempt.id,
        code="node_evicted",
        message="worker evicted",
        retryable=True,
    )
    assert run.status == "queued"
    assert run.attempt_count == 2
    assert attempt.status == "failed"
    # A permanent failure is terminal instead.
    run2, att2 = _queued(env)
    env["svc"].start_attempt(run_id=run2.id, attempt_id=att2.id)
    run2 = env["svc"].fail_attempt(
        run_id=run2.id, attempt_id=att2.id, code="nonconverged", message="no convergence"
    )
    assert run2.status == "failed"
