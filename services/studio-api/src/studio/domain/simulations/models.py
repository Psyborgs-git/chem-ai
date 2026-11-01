"""Durable owner-private all-atom simulation jobs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKeyConstraint, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from studio.persistence.base import Base, Timestamped, UUIDPrimaryKey, WorkspaceScoped

_JSON = JSON().with_variant(JSONB(), "postgresql")


class SimulationJob(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped):
    __tablename__ = "simulation_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "owner_id"], ["principals.workspace_id", "principals.id"]
        ),
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    config: Mapped[dict[str, Any]] = mapped_column(_JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(_JSON, default=dict)
    events: Mapped[list[dict[str, Any]]] = mapped_column(_JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    elapsed_seconds: Mapped[float] = mapped_column(default=0.0)
