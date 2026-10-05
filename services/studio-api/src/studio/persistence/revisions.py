"""Revision machinery helpers (handoff §5.1, §7.4, E08).

- Canonical content hashes over the stored payload.
- Next-revision allocation inside the entity row's transaction.
- Optimistic compare-and-swap for mutable headers.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from studio.errors import revision_conflict


def canonical_json(payload: dict[str, Any]) -> str:
    """Deterministic serialization for hashing (sorted keys, no spaces)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def content_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def next_revision(
    session: Session, revision_table: Any, entity_column: str, entity_id: uuid.UUID
) -> int:
    """Allocate the next revision number for an entity (1-based)."""
    current = session.execute(
        select(func.max(revision_table.revision)).where(
            getattr(revision_table, entity_column) == entity_id
        )
    ).scalar_one()
    return (current or 0) + 1


def compare_and_swap(
    session: Session,
    table: Any,
    row_id: uuid.UUID,
    expected_version: int,
    values: dict[str, Any],
) -> None:
    """Optimistic-lock update. Raises REVISION_CONFLICT on stale writers."""
    result = session.execute(
        update(table)
        .where(table.id == row_id, table.version == expected_version)
        .values(**values, version=table.version + 1)
    )
    if cast("CursorResult[Any]", result).rowcount != 1:
        raise revision_conflict(table.__tablename__)
