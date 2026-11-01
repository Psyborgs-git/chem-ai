"""Private records deliberately do not inherit workspace-wide read privileges."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKeyConstraint, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from studio.persistence.base import (
    Base,
    OptimisticLock,
    Timestamped,
    UUIDPrimaryKey,
    WorkspaceScoped,
)

_JSON = JSON().with_variant(JSONB(), "postgresql")


class PrivateOwned:
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)


def _owner_constraint(name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["workspace_id", "owner_id"],
        ["principals.workspace_id", "principals.id"],
        name=f"fk_{name}_private_owner",
    )


class LibraryFolder(
    Base, UUIDPrimaryKey, WorkspaceScoped, PrivateOwned, Timestamped, OptimisticLock
):
    __tablename__ = "library_folders"
    __table_args__ = (_owner_constraint(__tablename__),)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Notebook(Base, UUIDPrimaryKey, WorkspaceScoped, PrivateOwned, Timestamped, OptimisticLock):
    __tablename__ = "private_notebooks"
    __table_args__ = (_owner_constraint(__tablename__),)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ai_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    training_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class NotebookPage(
    Base, UUIDPrimaryKey, WorkspaceScoped, PrivateOwned, Timestamped, OptimisticLock
):
    __tablename__ = "notebook_pages"
    __table_args__ = (
        _owner_constraint(__tablename__),
        Index("ix_notebook_pages_owner_notebook", "workspace_id", "owner_id", "notebook_id"),
    )
    notebook_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="note")
    content: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False, default=dict)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(_JSON, nullable=False, default=list)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PageRevision(Base, UUIDPrimaryKey, WorkspaceScoped, PrivateOwned, Timestamped):
    __tablename__ = "notebook_page_revisions"
    __table_args__ = (
        _owner_constraint(__tablename__),
        Index("ix_notebook_page_revisions_page", "workspace_id", "owner_id", "page_id", "revision"),
    )
    page_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(_JSON, nullable=False, default=list)


class LibrarySource(
    Base, UUIDPrimaryKey, WorkspaceScoped, PrivateOwned, Timestamped, OptimisticLock
):
    __tablename__ = "library_sources"
    __table_args__ = (
        _owner_constraint(__tablename__),
        Index("ix_library_sources_owner_url", "workspace_id", "owner_id", "url_hash"),
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str] = mapped_column(String(160), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(nullable=False)
    original_key: Mapped[str] = mapped_column(String(200), nullable=False)
    text_key: Mapped[str] = mapped_column(String(200), nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    citation: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False, default=dict)
    archive_status: Mapped[str] = mapped_column(String(24), nullable=False, default="saved")
    download_name: Mapped[str] = mapped_column(String(200), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchMemory(
    Base, UUIDPrimaryKey, WorkspaceScoped, PrivateOwned, Timestamped, OptimisticLock
):
    __tablename__ = "private_research_memory"
    __table_args__ = (_owner_constraint(__tablename__),)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source_refs: Mapped[list[dict[str, Any]]] = mapped_column(_JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    generator: Mapped[str] = mapped_column(String(160), nullable=False, default="user")
