"""Resource groups + transactional reservations (§13.4, CS-0402).

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_resource_admission"
down_revision = "0013_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resource_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("capacity", postgresql.JSONB(), nullable=False),
        sa.Column("reserve", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("workspace_id", "name", name="uq_resource_groups_name"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_resource_groups_scope_id"),
    )
    op.create_table(
        "resource_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("envelope", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id", "group_id"],
            ["resource_groups.workspace_id", "resource_groups.id"],
            name="fk_reservations_scope_group",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["runs.workspace_id", "runs.id"],
            name="fk_reservations_scope_run",
        ),
        sa.UniqueConstraint("workspace_id", "run_id", name="uq_reservations_run"),
        sa.CheckConstraint("status IN ('active','released','consumed','expired')", name="status"),
    )
    op.create_index(
        "ix_reservations_group_active",
        "resource_reservations",
        ["workspace_id", "group_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("resource_reservations")
    op.drop_table("resource_groups")
