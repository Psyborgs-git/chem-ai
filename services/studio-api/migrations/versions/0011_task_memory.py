"""Durable task memory: sessions, manifests, messages, questions, summaries (§10.1, CS-0304).

Revision ID: 0011_task_memory
Revises: 0010_retrieval
Create Date: 2026-10-07
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_task_memory"
down_revision = "0010_retrieval"
branch_labels = None
depends_on = None

SESSION_STATUSES = ("active", "ended")
MESSAGE_ROLES = ("user", "assistant", "system", "tool")
MESSAGE_KINDS = ("message", "proposal", "tool_call", "tool_result", "rationale")
QUESTION_STATUSES = ("open", "resolved")


def upgrade() -> None:
    op.create_table(
        "context_manifests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("compiler_version", sa.String(32), nullable=False),
        sa.Column("token_budget", sa.Integer, nullable=False),
        sa.Column("token_estimate", sa.Integer, nullable=False),
        sa.Column("over_budget", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("items", postgresql.JSONB, nullable=False),
        sa.Column("omitted", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("warnings", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["research_tasks.workspace_id", "research_tasks.id"],
            name="fk_context_manifests_scope_task",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "contract_revision_id"],
            ["success_contract_revisions.workspace_id", "success_contract_revisions.id"],
            name="fk_context_manifests_scope_contract",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_context_manifests_scope_id"),
        sa.Index("ix_context_manifests_task", "workspace_id", "task_id", "created_at", "id"),
    )
    op.create_table(
        "research_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start_manifest_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("start_contract_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("started_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("end_snapshot", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["research_tasks.workspace_id", "research_tasks.id"],
            name="fk_research_sessions_scope_task",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "start_manifest_id"],
            ["context_manifests.workspace_id", "context_manifests.id"],
            name="fk_research_sessions_scope_manifest",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "started_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_research_sessions_scope_starter",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_research_sessions_scope_id"),
        sa.CheckConstraint(f"status IN {SESSION_STATUSES!r}", name="session_status"),
        sa.Index("ix_research_sessions_task", "workspace_id", "task_id", "created_at", "id"),
    )
    op.create_table(
        "session_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="message"),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("refs", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id"],
            ["research_sessions.workspace_id", "research_sessions.id"],
            name="fk_session_messages_scope_session",
        ),
        sa.CheckConstraint(f"role IN {MESSAGE_ROLES!r}", name="message_role"),
        sa.CheckConstraint(f"kind IN {MESSAGE_KINDS!r}", name="message_kind"),
        sa.Index(
            "ix_session_messages_session",
            "workspace_id",
            "session_id",
            "created_at",
            "id",
        ),
    )
    op.create_table(
        "task_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("blocking", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("resolution", sa.Text, nullable=True),
        sa.Column("raised_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["research_tasks.workspace_id", "research_tasks.id"],
            name="fk_task_questions_scope_task",
        ),
        sa.CheckConstraint(f"status IN {QUESTION_STATUSES!r}", name="question_status"),
        sa.Index("ix_task_questions_task", "workspace_id", "task_id", "created_at", "id"),
    )
    op.create_table(
        "task_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("source_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("coverage", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("generator", sa.String(120), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["research_tasks.workspace_id", "research_tasks.id"],
            name="fk_task_summaries_scope_task",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "contract_revision_id"],
            ["success_contract_revisions.workspace_id", "success_contract_revisions.id"],
            name="fk_task_summaries_scope_contract",
        ),
        sa.Index("ix_task_summaries_task", "workspace_id", "task_id", "created_at", "id"),
    )


def downgrade() -> None:
    op.drop_table("task_summaries")
    op.drop_table("task_questions")
    op.drop_table("session_messages")
    op.drop_table("research_sessions")
    op.drop_table("context_manifests")
