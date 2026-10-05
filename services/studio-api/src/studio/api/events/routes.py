"""Bounded event streams with sequence IDs (§8, CS-0406).

``/api/events/stream`` is an SSE channel over the transactional outbox:
every event carries a monotonic ``seq``; clients resume with
``Last-Event-ID`` (or ``since=``) and dedupe client-side, so a
disconnect + reconnect never duplicates messages/actions. Streams are
bounded — max events and max wall-time per connection — then the
client auto-reconnects.

``/api/events/snapshot`` returns authoritative current state for a
channel — the fallback when a client can't trust its cursor (fresh
load, gap detected, or stream dropped before any event).

Both endpoints resolve a ServiceContext and re-check project read
capability; the stream only carries aggregates in scope.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from chem_studio_policy.capabilities import CAP_READ_PROJECT
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from studio.api.deps import get_session_factory
from studio.auth.context import ServiceContext
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import (
    OutboxEvent,
    ResearchSession,
    ResearchTask,
    Run,
    RunAttempt,
    SessionMessage,
)

events_router = APIRouter(tags=["events"])

_MAX_EVENTS = 500
# per-connection lifetime bound (§8) — a tunable, not a correctness
# invariant; e2e shortens it so reconnect cycles are exercised
_MAX_SECONDS = float(os.environ.get("STUDIO_EVENT_MAX_SECONDS", "55"))
_POLL_INTERVAL = 0.5
_BATCH = 200

CHANNELS = ("session", "task")


def _project_id(db: Session, ctx: ServiceContext, channel: str, ident: uuid.UUID) -> uuid.UUID:
    """Resolve the owning project for a channel target — authz anchor."""
    if channel == "task":
        task = db.execute(
            select(ResearchTask).where(
                ResearchTask.workspace_id == ctx.workspace_id, ResearchTask.id == ident
            )
        ).scalar_one_or_none()
        if task is None:
            raise not_found("task")
        return task.project_id
    if channel == "session":
        session = db.execute(
            select(ResearchSession).where(
                ResearchSession.workspace_id == ctx.workspace_id,
                ResearchSession.id == ident,
            )
        ).scalar_one_or_none()
        if session is None:
            raise not_found("session")
        task = db.execute(
            select(ResearchTask).where(
                ResearchTask.workspace_id == ctx.workspace_id,
                ResearchTask.id == session.task_id,
            )
        ).scalar_one_or_none()
        if task is None:
            raise not_found("task")
        return task.project_id
    raise DomainError(ErrorCode.VALIDATION, "unknown channel")


def _authorize(db: Session, ctx: ServiceContext, channel: str, ident: uuid.UUID) -> None:
    ctx.require(CAP_READ_PROJECT, _project_id(db, ctx, channel, ident))


def _event_filter(channel: str, ident: uuid.UUID) -> Any:
    """WHERE clause over outbox for a channel. ``task`` fans out to any
    aggregate whose payload names the task (runs, sessions, messages)."""
    if channel == "session":
        return OutboxEvent.aggregate_id == ident
    return or_(
        OutboxEvent.aggregate_id == ident,
        OutboxEvent.payload["taskId"].as_string() == str(ident),
    )


def _fetch_batch(
    db: Session, ctx: ServiceContext, channel: str, ident: uuid.UUID, since: int
) -> list[OutboxEvent]:
    return list(
        db.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.workspace_id == ctx.workspace_id,
                _event_filter(channel, ident),
                OutboxEvent.seq > since,
            )
            .order_by(OutboxEvent.seq)
            .limit(_BATCH)
        ).scalars()
    )


def _format(row: OutboxEvent) -> str:
    data = {
        "seq": row.seq,
        "type": row.event_type,
        "aggregate": row.aggregate_type,
        "payload": row.payload,
        "at": row.created_at.isoformat(),
    }
    return f"id: {row.seq}\nevent: {row.event_type}\ndata: {json.dumps(data)}\n\n"


def _session_snapshot(db: Session, ctx: ServiceContext, ident: uuid.UUID) -> dict[str, Any]:
    messages = db.execute(
        select(SessionMessage)
        .where(
            SessionMessage.workspace_id == ctx.workspace_id,
            SessionMessage.session_id == ident,
        )
        .order_by(SessionMessage.created_at, SessionMessage.id)
    ).scalars()
    return {
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "kind": m.kind,
                "content": m.content,
                "refs": m.refs,
            }
            for m in messages
        ]
    }


def _task_snapshot(db: Session, ctx: ServiceContext, ident: uuid.UUID) -> dict[str, Any]:
    runs = db.execute(
        select(Run)
        .where(Run.workspace_id == ctx.workspace_id, Run.task_id == ident)
        .order_by(Run.created_at, Run.id)
    ).scalars()
    attempts = db.execute(
        select(RunAttempt).where(RunAttempt.workspace_id == ctx.workspace_id)
    ).scalars()
    by_run: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for a in attempts:
        by_run.setdefault(a.run_id, []).append(
            {
                "id": str(a.id),
                "status": a.status,
                "workerId": a.worker_id,
                "startedAt": a.started_at.isoformat() if a.started_at else None,
                "finishedAt": a.finished_at.isoformat() if a.finished_at else None,
                "error": a.error,
            }
        )
    return {
        "runs": [
            {
                "id": str(r.id),
                "kind": r.kind,
                "status": r.status,
                "attemptCount": r.attempt_count,
                "error": r.error,
                "resultSummary": r.result_summary,
                "attempts": by_run.get(r.id, []),
            }
            for r in runs
        ]
    }


def _max_seq(db: Session, ctx: ServiceContext, channel: str, ident: uuid.UUID) -> int:
    value = db.execute(
        select(func.coalesce(func.max(OutboxEvent.seq), 0)).where(
            OutboxEvent.workspace_id == ctx.workspace_id,
            _event_filter(channel, ident),
        )
    ).scalar_one()
    return int(value)


@events_router.get("/snapshot")
def snapshot(request: Request, channel: str, id: uuid.UUID) -> dict[str, Any]:
    """Authoritative current state + the stream cursor it corresponds to."""
    from studio.api.deps import build_context

    db: Session = get_session_factory(request)()
    try:
        ctx = build_context(request, db)
        _authorize(db, ctx, channel, id)
        db.commit()
        state = (
            _session_snapshot(db, ctx, id) if channel == "session" else _task_snapshot(db, ctx, id)
        )
        state["maxSeq"] = _max_seq(db, ctx, channel, id)
        state["channel"] = channel
        return state
    finally:
        db.close()


async def _stream(
    request: Request,
    factory: sessionmaker[Session],
    ctx: ServiceContext,
    channel: str,
    ident: uuid.UUID,
    since: int,
) -> AsyncIterator[str]:
    """Bounded SSE generator: poll outbox for seq > cursor until the
    event/time bound, heartbeat, then close — client reconnects."""
    sent = 0
    started = time.monotonic()
    while sent < _MAX_EVENTS and time.monotonic() - started < _MAX_SECONDS:
        db = factory()
        try:
            rows = _fetch_batch(db, ctx, channel, ident, since)
        finally:
            db.close()
        for row in rows:
            yield _format(row)
            since = row.seq
            sent += 1
            if sent >= _MAX_EVENTS:
                break
        if sent >= _MAX_EVENTS:
            break
        # named heartbeat frame (no `id:` — the resume cursor must not
        # move) so clients can watchdog stream liveness; an SSE comment
        # is invisible to EventSource
        yield "event: heartbeat\ndata: {}\n\n"
        await asyncio.sleep(_POLL_INTERVAL)


@events_router.get("/stream")
def stream(
    request: Request,
    channel: str,
    id: uuid.UUID,
    since: int = 0,
) -> StreamingResponse:
    """SSE endpoint. ``Last-Event-ID`` wins over ``since`` on reconnect.

    The auth context is resolved on a short-lived session that is
    committed and closed BEFORE the response starts streaming — the
    ``authenticate_token`` last-seen UPDATE must never pin a row lock
    for the lifetime of an SSE connection."""
    if channel not in CHANNELS:
        raise DomainError(ErrorCode.VALIDATION, "unknown channel")
    last_id = request.headers.get("last-event-id")
    if last_id is not None:
        try:
            since = int(last_id)
        except ValueError:
            since = 0
    from studio.api.deps import build_context

    factory = get_session_factory(request)
    db = factory()
    try:
        ctx = build_context(request, db)
        _authorize(db, ctx, channel, id)
        db.commit()
    finally:
        db.close()
    return StreamingResponse(
        _stream(request, factory, ctx, channel, id, since),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
