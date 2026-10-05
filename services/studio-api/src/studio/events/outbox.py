"""Transactional outbox (§7.4).

Events are inserted in the *same* transaction as the domain change, so
an effect can never exist without its event (or vice versa). Delivery
is at-least-once: ``deliver_pending`` records each (event, consumer)
in the dedupe ledger inside a savepoint *before* invoking the handler,
and only commits both together — a crash between them redelivers, a
successful delivery never repeats. Exactly-once is not promised.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from studio.persistence.models import OutboxDelivery, OutboxEvent


def publish(
    db: Session,
    workspace_id: uuid.UUID,
    *,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
    command_id: uuid.UUID | None = None,
) -> OutboxEvent:
    event = OutboxEvent(
        workspace_id=workspace_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
        command_id=command_id,
    )
    db.add(event)
    db.flush()
    return event


def deliver_pending(
    db: Session,
    workspace_id: uuid.UUID,
    *,
    consumer: str,
    handler: Callable[[OutboxEvent], None],
    limit: int = 200,
) -> int:
    """Deliver pending events to ``consumer`` in order; each is handled
    at most once. Returns the number delivered this call."""
    events = (
        db.execute(
            select(OutboxEvent)
            .where(OutboxEvent.workspace_id == workspace_id)
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    delivered = 0
    for event in events:
        try:
            with db.begin_nested():
                db.add(OutboxDelivery(event_id=event.id, consumer=consumer))
                db.flush()
                handler(event)
        except IntegrityError:
            continue  # already delivered to this consumer
        delivered += 1
    return delivered


def delivered_to(db: Session, event_id: uuid.UUID, consumer: str) -> bool:
    return (
        db.execute(
            select(OutboxDelivery).where(
                OutboxDelivery.event_id == event_id,
                OutboxDelivery.consumer == consumer,
            )
        ).scalar_one_or_none()
        is not None
    )
