"""Scoped, persisted run cache (§13.5).

Entries are addressed by the full scientific-context digest computed in
``workers.common.cache`` and are insert-only: a conflicting insert
returns the existing row (idempotent), an invalidation marks rather
than deletes, and an invalidated entry is never served."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext
from studio.persistence.models import RunCacheEntry


class RunCache:
    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    def get(self, key: str) -> RunCacheEntry | None:
        entry = self.db.execute(
            select(RunCacheEntry).where(
                RunCacheEntry.workspace_id == self.ctx.workspace_id,
                RunCacheEntry.key == key,
                RunCacheEntry.status == "valid",
            )
        ).scalar_one_or_none()
        return entry

    def put(
        self,
        *,
        key: str,
        context: dict[str, Any],
        payload: dict[str, Any],
        run_id: uuid.UUID | None = None,
    ) -> tuple[RunCacheEntry, bool]:
        """Insert a completed result; returns (entry, created). An
        identical key returns the stored entry — cache writes are
        idempotent under retry."""
        entry = RunCacheEntry(
            workspace_id=self.ctx.workspace_id,
            key=key,
            context=context,
            payload=payload,
            produced_by_run_id=run_id,
        )
        self.db.add(entry)
        try:
            self.db.flush()
            return entry, True
        except IntegrityError:
            self.db.rollback()
            existing = self.db.execute(
                select(RunCacheEntry).where(
                    RunCacheEntry.workspace_id == self.ctx.workspace_id,
                    RunCacheEntry.key == key,
                )
            ).scalar_one()
            return existing, False

    def invalidate(self, key: str, *, reason: str) -> bool:
        """Mark an entry unservable — provenance is retained, the
        content is never returned by ``get`` again."""
        entry = self.db.execute(
            select(RunCacheEntry).where(
                RunCacheEntry.workspace_id == self.ctx.workspace_id,
                RunCacheEntry.key == key,
            )
        ).scalar_one_or_none()
        if entry is None or entry.status != "valid":
            return False
        entry.status = "invalidated"
        entry.invalidated_at = datetime.now(UTC)
        entry.invalidate_reason = reason
        audit_record(
            self.db,
            self.ctx,
            action="run_cache.invalidated",
            target_type="run_cache_entry",
            target_id=entry.id,
            detail={"key": key, "reason": reason},
        )
        self.db.flush()
        return True
