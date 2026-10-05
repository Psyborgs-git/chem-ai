"""Idempotent command execution (§7.4).

A mutating command accepts an ``idempotency_key``. Its outcome is
persisted in the *same* transaction as the domain change and any
outbox events, so a retry can never re-apply effects: replaying the
same key + payload returns the stored original response; replaying the
key with a different payload fails with ``IDEMPOTENCY_MISMATCH``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import IdempotencyRecord


def canonical_json(payload: Any) -> str:
    """Canonical serialization: sorted keys, tight separators, so a
    digest is stable across dict orderings and serializations."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def request_digest(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def run_idempotent(
    db: Session,
    ctx: ServiceContext,
    *,
    operation: str,
    key: str,
    payload: Any,
    fn: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Run ``fn`` at most once per (workspace, operation, key).

    ``fn`` executes in the caller's transaction: its domain effects,
    outbox events and this record commit or roll back together.
    """
    if not key or len(key) > 200:
        raise DomainError(
            ErrorCode.VALIDATION,
            "idempotency_key must be 1-200 characters",
            field_path="input.idempotencyKey",
        )
    digest = request_digest(payload)
    existing = db.execute(
        select(IdempotencyRecord)
        .where(
            IdempotencyRecord.workspace_id == ctx.workspace_id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.key == key,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if existing is not None:
        if existing.request_digest != digest:
            raise DomainError(
                ErrorCode.IDEMPOTENCY_MISMATCH,
                "idempotency key was already used with a different payload",
            )
        if existing.status != "succeeded" or existing.response is None:
            raise DomainError(
                ErrorCode.CONFLICT,
                "a prior attempt with this key did not complete; use a new key",
                retryable=False,
            )
        return dict(existing.response)

    response = fn()
    record = IdempotencyRecord(
        workspace_id=ctx.workspace_id,
        principal_id=ctx.principal_id,
        operation=operation,
        key=key,
        request_digest=digest,
        response=response,
        status="succeeded",
        completed_at=datetime.now(UTC),
    )
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        # A concurrent request with the same key won the unique race.
        # Roll back this attempt's effects and return the winner's
        # original result — that is the §7.4 contract.
        db.rollback()
        winner = db.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.workspace_id == ctx.workspace_id,
                IdempotencyRecord.operation == operation,
                IdempotencyRecord.key == key,
            )
        ).scalar_one_or_none()
        if winner is not None and winner.request_digest == digest and winner.response:
            return dict(winner.response)
        raise DomainError(
            ErrorCode.CONFLICT,
            "concurrent command with the same idempotency key; retry",
            retryable=True,
        ) from None
    return response
