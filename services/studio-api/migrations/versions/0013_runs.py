"""Run and attempt records — authoritative execution bookkeeping (§7.3).

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_runs"
down_revision = "0012_evidence_revocation"
branch_labels = None
depends_on = None

RUN_STATUSES = (
    "requested",
    "awaiting_approval",
    "queued",
    "running",
    "succeeded",
    "failed",
    "timed_out",
    "cancelled",
    "cancel_requested",
    "blocked",
    "interrupted",
)
RUN_ATTEMPT_STATUSES = (
    "queued",
    "running",
    "succeeded",
    "failed",
    "timed_out",
    "cancelled",
    "interrupted",
)


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="requested"),
        sa.Column("request", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", postgresql.JSONB(), nullable=True),
        sa.Column("result_summary", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["research_tasks.workspace_id", "research_tasks.id"],
            name="fk_runs_scope_task",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "requested_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_runs_scope_requester",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_runs_scope_id"),
        sa.CheckConstraint(f"status IN {RUN_STATUSES!r}", name="status"),
    )
    op.create_index("ix_runs_scope_list", "runs", ["workspace_id", "status", "created_at", "id"])

    op.create_table(
        "run_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("queue_name", sa.String(length=64), nullable=False, server_default="runs"),
        sa.Column("external_id", sa.String(length=160), nullable=True),
        sa.Column("worker_id", sa.String(length=160), nullable=True),
        sa.Column(
            "enqueued_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", postgresql.JSONB(), nullable=True),
        sa.Column("callbacks", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["runs.workspace_id", "runs.id"],
            name="fk_run_attempts_scope_run",
        ),
        sa.UniqueConstraint(
            "workspace_id", "run_id", "attempt_number", name="uq_run_attempts_number"
        ),
        sa.UniqueConstraint("workspace_id", "external_id", name="uq_run_attempts_external"),
        sa.CheckConstraint(f"status IN {RUN_ATTEMPT_STATUSES!r}", name="status"),
    )
    op.create_index(
        "ix_run_attempts_scope_run",
        "run_attempts",
        ["workspace_id", "run_id", "attempt_number"],
    )


def downgrade() -> None:
    op.drop_table("run_attempts")
    op.drop_table("runs")
