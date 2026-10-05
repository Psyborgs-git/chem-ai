"""Experiment plans — immutable-bound review records (§14.1, CS-0501).

Revision ID: 0017_experiment_plans
Revises: 0016_outbox_seq
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0017_experiment_plans"
down_revision = "0016_outbox_seq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # scope-id unique needed by composite FK (same gap as earlier tables)
    op.execute(
        "ALTER TABLE approvals ADD CONSTRAINT uq_approvals_scope_id UNIQUE (workspace_id, id)"
    )
    op.create_table(
        "experiment_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("bound_inputs", JSONB, nullable=False, server_default="{}"),
        sa.Column("content_digest", sa.String(64), nullable=False, server_default=""),
        sa.Column("blockers", JSONB, nullable=False, server_default="[]"),
        sa.Column("approval_id", UUID(as_uuid=True), nullable=True),
        sa.Column("packet", JSONB, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
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
            name="fk_experiment_plans_scope_task",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "approval_id"],
            ["approvals.workspace_id", "approvals.id"],
            name="fk_experiment_plans_scope_approval",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_experiment_plans_scope_id"),
        sa.CheckConstraint("status IN ('draft','submitted','approved','rejected')", name="status"),
    )
    op.create_index(
        "ix_experiment_plans_scope_task",
        "experiment_plans",
        ["workspace_id", "task_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.execute("ALTER TABLE approvals DROP CONSTRAINT IF EXISTS uq_approvals_scope_id")
    op.drop_index("ix_experiment_plans_scope_task", table_name="experiment_plans")
    op.drop_table("experiment_plans")
