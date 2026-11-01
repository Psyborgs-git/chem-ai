"""Bounded conversation history in durable event order.

Tool outputs, instructions, and previous assistant text are intentionally
excluded: an earlier answer may paraphrase a source whose export rights have
since changed. Session outbox sequence preserves order when the
message timestamps within a single transaction are identical.
"""

from __future__ import annotations

import uuid
from typing import Any

from chem_studio_policy.capabilities import CAP_READ_PROJECT
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext
from studio.domain.tasks.memory import TaskMemoryService
from studio.persistence.models import OutboxEvent

_TRUNCATED = " …[truncated]"
_MAX_SCAN = 200
_MAX_MESSAGE_CHARS = 4000


def recent_conversation(
    db: Session,
    ctx: ServiceContext,
    session_id: uuid.UUID,
    *,
    exclude_message_id: uuid.UUID,
    max_messages: int = 12,
    max_chars: int = 12000,
) -> list[dict[str, str]]:
    """Return recent human messages only, oldest first.

    Newest messages take priority when either budget is reached. The current
    question is passed separately and must never be duplicated here.
    """
    if max_messages <= 0 or max_chars <= len(_TRUNCATED):
        return []
    memory = TaskMemoryService(db, ctx)
    session = memory._session(session_id)
    task = memory._task(session.task_id)
    ctx.require(CAP_READ_PROJECT, task.project_id)
    events = db.scalars(
        select(OutboxEvent)
        .where(
            OutboxEvent.workspace_id == ctx.workspace_id,
            OutboxEvent.aggregate_type == "research_session",
            OutboxEvent.aggregate_id == session_id,
            OutboxEvent.event_type == "session.message.posted",
        )
        .order_by(OutboxEvent.seq.desc())
        .limit(_MAX_SCAN)
    )
    result: list[dict[str, str]] = []
    remaining = max_chars
    for event in events:
        payload: dict[str, Any] = event.payload or {}
        role, content, refs = payload.get("role"), payload.get("content"), payload.get("refs")
        if (
            payload.get("messageId") == str(exclude_message_id)
            or payload.get("kind") != "message"
            or role != "user"
            or not isinstance(content, str)
            or not content.strip()
            or (
                isinstance(refs, dict)
                and (refs.get("turn_cancel") or refs.get("cancelled") or refs.get("error"))
            )
        ):
            continue
        limit = min(remaining, _MAX_MESSAGE_CHARS)
        if limit <= len(_TRUNCATED):
            break
        if len(content) > limit:
            content = content[: limit - len(_TRUNCATED)] + _TRUNCATED
        result.append({"role": role, "content": content})
        remaining -= len(content)
        if len(result) >= max_messages:
            break
    result.reverse()
    return result
