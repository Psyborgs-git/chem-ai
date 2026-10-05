"""Task lifecycle: ownership, mode inputs, evaluation cycles, decisions
(§7.1, §11, CS-0201).

Task decisions record closures and reopens with the exact contract
revision they were made under; reopening increments the evaluation
cycle rather than rewriting history.

Revision ID: 0005_task_lifecycle
Revises: 0004_commands_approvals_outbox
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_task_lifecycle"
down_revision = "0004_commands_approvals_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_tasks",
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "research_tasks",
        sa.Column("mode_inputs", postgresql.JSONB, nullable=False, server_default="{}"),
    )
    op.add_column(
        "research_tasks",
        sa.Column("evaluation_cycle", sa.Integer, nullable=False, server_default="1"),
    )
    op.create_foreign_key(
        "fk_research_tasks_scope_owner",
        "research_tasks",
        "principals",
        ["workspace_id", "owner_id"],
        ["workspace_id", "id"],
    )

    op.create_table(
        "task_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["research_tasks.workspace_id", "research_tasks.id"],
            name="fk_task_decisions_scope_task",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "decided_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_task_decisions_scope_decider",
        ),
        sa.CheckConstraint(
            "kind IN ('closure','reopen','review_return','state_change')", name="kind"
        ),
    )
    op.create_index("ix_task_decisions_workspace_id", "task_decisions", ["workspace_id"])
    op.create_index(
        "ix_task_decisions_task",
        "task_decisions",
        ["workspace_id", "task_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_table("task_decisions")
    op.drop_constraint("fk_research_tasks_scope_owner", "research_tasks", type_="foreignkey")
    op.drop_column("research_tasks", "evaluation_cycle")
    op.drop_column("research_tasks", "mode_inputs")
    op.drop_column("research_tasks", "owner_id")
