"""Owner scoped agent conversations, durable executions and model choices."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from studio.persistence.base import Base, Timestamped, UUIDPrimaryKey, WorkspaceScoped


class ProviderModel(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped):
    __tablename__ = "agent_provider_models"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "provider_id"],
            ["inference_providers.workspace_id", "inference_providers.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("workspace_id", "provider_id", "model_id"),
        CheckConstraint(
            "api_style IN ('inherit','chat_completions','responses')", name="api_style"
        ),
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    model_id: Mapped[str] = mapped_column(String(160), nullable=False)
    api_style: Mapped[str] = mapped_column(
        String(32), nullable=False, default="inherit", server_default="inherit"
    )
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    roles: Mapped[list[str]] = mapped_column(JSONB, default=list)
    supports_tools: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    input_price: Mapped[float | None] = mapped_column(nullable=True)
    output_price: Mapped[float | None] = mapped_column(nullable=True)


class AgentPolicy(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped):
    __tablename__ = "agent_workspace_policies"
    __table_args__ = (UniqueConstraint("workspace_id", "owner_id"),)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class AgentThread(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped):
    __tablename__ = "agent_workspace_threads"
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    notebook_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class AgentRun(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped):
    __tablename__ = "agent_workspace_runs"
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    provider_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="planner")
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    autopilot: Mapped[bool] = mapped_column(Boolean, default=False)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    lease_owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentMessage(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped):
    __tablename__ = "agent_workspace_messages"
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="message")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    refs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
