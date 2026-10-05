"""Content-addressed run cache entries (§13.5, CS-0403).

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_run_cache"
down_revision = "0014_resource_admission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_cache_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("produced_by_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="valid"),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidate_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("workspace_id", "key", name="uq_run_cache_key"),
        sa.CheckConstraint("status IN ('valid','invalidated')", name="status"),
    )
    op.create_index("ix_run_cache_scope", "run_cache_entries", ["workspace_id", "created_at", "id"])


def downgrade() -> None:
    op.drop_table("run_cache_entries")
