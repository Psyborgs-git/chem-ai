"""Initial core schema: scope, principals, projects, tasks, contracts.

Revision ID: 0001_initial_core
Revises:
Create Date: 2026-10-05

Covers handoff §26.2 groups 1-2: principals/workspaces/projects and
core task/contract revisions. Establishes scoped IDs, composite scope
FKs (AT-0101-3), optimistic locking columns, and the immutable-accepted
revision guard (AT-0101-1).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial_core"
down_revision = None
branch_labels = None
depends_on = None

TASK_STATES = ("draft", "active", "paused", "awaiting_review", "closed", "cancelled")
TASK_MODES = ("improve", "match_reference", "discover")
TASK_CLOSURES = ("supported_success", "supported_failure", "inconclusive", "stopped")
CONTRACT_STATUSES = ("draft", "frozen", "superseded")


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "principals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("login", sa.String(120), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("credential_hash", sa.Text, nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("kind IN ('user','agent','service')", name="kind"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_principals_scope_id"),
        sa.UniqueConstraint("workspace_id", "login", name="uq_principals_scope_login"),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], name="fk_principals_workspace_id_workspaces"
        ),
    )
    op.create_index("ix_principals_workspace_id", "principals", ["workspace_id"])

    op.create_table(
        "principal_capabilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("scope_ref", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id", "principal_id"],
            ["principals.workspace_id", "principals.id"],
            name="fk_principal_capabilities_scope",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "principal_id",
            "capability",
            "scope_ref",
            name="uq_principal_capabilities_grant",
        ),
    )

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], name="fk_projects_workspace_id_workspaces"
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_projects_scope_id"),
    )
    op.create_index("ix_projects_workspace_id", "projects", ["workspace_id"])
    op.create_index("ix_projects_scope_list", "projects", ["workspace_id", "created_at", "id"])

    op.create_table(
        "research_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mode", sa.String(24), nullable=False),
        sa.Column("target_kind", sa.String(24), nullable=False, server_default="unknown"),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("objective", sa.Text, nullable=True),
        sa.Column("workflow_state", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("closure_decision", sa.String(24), nullable=True),
        sa.Column("current_contract_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "project_id"],
            ["projects.workspace_id", "projects.id"],
            name="fk_research_tasks_scope_project",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "reviewer_id"],
            ["principals.workspace_id", "principals.id"],
            name="fk_research_tasks_scope_reviewer",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_research_tasks_scope_id"),
        sa.CheckConstraint(f"workflow_state IN {TASK_STATES!r}", name="workflow_state"),
        sa.CheckConstraint(f"mode IN {TASK_MODES!r}", name="mode"),
        sa.CheckConstraint(
            f"closure_decision IS NULL OR closure_decision IN {TASK_CLOSURES!r}",
            name="closure_decision",
        ),
    )
    op.create_index("ix_research_tasks_workspace_id", "research_tasks", ["workspace_id"])
    op.create_index(
        "ix_research_tasks_scope_list",
        "research_tasks",
        ["workspace_id", "project_id", "created_at", "id"],
    )

    op.create_table(
        "success_contract_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["research_tasks.workspace_id", "research_tasks.id"],
            name="fk_success_contract_revisions_scope_task",
        ),
        sa.UniqueConstraint("task_id", "revision", name="uq_contract_task_revision"),
        sa.CheckConstraint(f"status IN {CONTRACT_STATUSES!r}", name="status"),
    )
    op.create_index(
        "ix_success_contract_revisions_workspace_id", "success_contract_revisions", ["workspace_id"]
    )
    op.create_index(
        "ix_success_contract_revisions_task",
        "success_contract_revisions",
        ["workspace_id", "task_id", "revision"],
    )

    # ---- immutable accepted-revision guard (AT-0101-1) ----
    # Once a revision is accepted/frozen, the ONLY permitted update is a
    # status transition to 'superseded'; every other column must remain
    # identical and deletes are rejected outright. TG_ARGV[0] names the
    # entity-FK column so one function serves every revision table.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION cs_revision_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            entity_col text := TG_ARGV[0];
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.status IN ('accepted','frozen') THEN
                    RAISE EXCEPTION 'immutable_revision: accepted revision % cannot be deleted', OLD.id;
                END IF;
                RETURN OLD;
            END IF;
            IF TG_OP = 'UPDATE' AND OLD.status IN ('accepted','frozen') THEN
                IF NEW.status = 'superseded'
                   AND NEW.payload IS NOT DISTINCT FROM OLD.payload
                   AND NEW.revision IS NOT DISTINCT FROM OLD.revision
                   AND NEW.content_hash IS NOT DISTINCT FROM OLD.content_hash
                   AND NEW.workspace_id IS NOT DISTINCT FROM OLD.workspace_id
                   AND NEW.created_by IS NOT DISTINCT FROM OLD.created_by
                   AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at
                   AND (to_jsonb(NEW) ->> entity_col)
                       IS NOT DISTINCT FROM (to_jsonb(OLD) ->> entity_col) THEN
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION 'immutable_revision: accepted revision % cannot be modified; create a superseding revision', OLD.id;
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_contract_revision_guard
        BEFORE UPDATE OR DELETE ON success_contract_revisions
        FOR EACH ROW EXECUTE FUNCTION cs_revision_guard('task_id');
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_contract_revision_guard ON success_contract_revisions")
    op.execute("DROP FUNCTION IF EXISTS cs_revision_guard()")
    op.drop_table("success_contract_revisions")
    op.drop_table("research_tasks")
    op.drop_table("projects")
    op.drop_table("principal_capabilities")
    op.drop_table("principals")
    op.drop_table("workspaces")
