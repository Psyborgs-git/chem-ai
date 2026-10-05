"""Formulation/process/candidate revisions + proposal patches
(§5, §6.2, §7.2, CS-0204).

The immutable-revision guard is extended: 'accepted_for_research'
candidate content joins 'accepted'/'frozen' as immutable — the only
permitted transition from an immutable row is to 'superseded'.

Revision ID: 0007_formulations_candidates
Revises: 0006_materials_registry
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_formulations_candidates"
down_revision = "0006_materials_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "formulation_families",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_formulation_families_scope_id"),
    )
    op.create_index(
        "ix_formulation_families_scope_list",
        "formulation_families",
        ["workspace_id", "created_at", "id"],
    )

    op.create_table(
        "formulation_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("parent_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "family_id"],
            ["formulation_families.workspace_id", "formulation_families.id"],
            name="fk_formulation_revisions_scope_family",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "parent_revision_id"],
            ["formulation_revisions.workspace_id", "formulation_revisions.id"],
            name="fk_formulation_revisions_scope_parent",
        ),
        sa.UniqueConstraint("family_id", "revision", name="uq_formulation_family_revision"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_formulation_revisions_scope_id"),
        sa.CheckConstraint("status IN ('draft','accepted','superseded')", name="status"),
    )
    op.create_index(
        "ix_formulation_revisions_family",
        "formulation_revisions",
        ["workspace_id", "family_id", "revision"],
    )

    op.create_table(
        "process_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
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
            ["workspace_id", "family_id"],
            ["formulation_families.workspace_id", "formulation_families.id"],
            name="fk_process_revisions_scope_family",
        ),
        sa.UniqueConstraint("family_id", "revision", name="uq_process_family_revision"),
        sa.CheckConstraint("status IN ('draft','accepted','superseded')", name="status"),
    )
    op.create_index(
        "ix_process_revisions_family",
        "process_revisions",
        ["workspace_id", "family_id", "revision"],
    )

    # CS-0101 created success_contract_revisions without a scope
    # unique constraint — the composite FK below needs it.
    op.create_unique_constraint(
        "uq_contract_revisions_scope_id",
        "success_contract_revisions",
        ["workspace_id", "id"],
    )

    op.create_table(
        "candidate_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("eligibility", sa.String(40), nullable=False, server_default="not_assessed"),
        sa.Column("entity_kind", sa.String(24), nullable=False),
        sa.Column("entity_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parent_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("contract_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("hypothesis", sa.Text, nullable=True),
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
            name="fk_candidate_revisions_scope_task",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "contract_revision_id"],
            ["success_contract_revisions.workspace_id", "success_contract_revisions.id"],
            name="fk_candidate_revisions_scope_contract",
        ),
        sa.UniqueConstraint("task_id", "revision", name="uq_candidate_task_revision"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_candidate_revisions_scope_id"),
        sa.CheckConstraint(
            "status IN ('draft','submitted','accepted_for_research','rejected')", name="status"
        ),
        sa.CheckConstraint(
            "eligibility IN ('not_assessed','eligible_for_computation','needs_review','blocked','eligible_for_approved_experiment')",
            name="eligibility",
        ),
        sa.CheckConstraint(
            "entity_kind IN ('formulation','molecule','material')", name="entity_kind"
        ),
    )
    op.create_index(
        "ix_candidate_revisions_task",
        "candidate_revisions",
        ["workspace_id", "task_id", "revision"],
    )

    op.create_table(
        "candidate_patches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("patch", postgresql.JSONB, nullable=False),
        sa.Column("proposed_by", sa.String(80), nullable=False, server_default="user"),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id", "candidate_id"],
            ["candidate_revisions.workspace_id", "candidate_revisions.id"],
            name="fk_candidate_patches_scope_candidate",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "reviewed_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_candidate_patches_scope_reviewer",
        ),
        sa.CheckConstraint("status IN ('proposed','accepted','rejected')", name="status"),
    )
    op.create_index(
        "ix_candidate_patches_scope_list",
        "candidate_patches",
        ["workspace_id", "created_at", "id"],
    )

    # Formulation/process revisions reuse the CS-0101 immutable guard:
    # 'accepted' content may only transition to 'superseded'.
    op.execute(
        """
        CREATE TRIGGER trg_formulation_revision_guard
        BEFORE UPDATE OR DELETE ON formulation_revisions
        FOR EACH ROW EXECUTE FUNCTION cs_revision_guard('family_id');
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_process_revision_guard
        BEFORE UPDATE OR DELETE ON process_revisions
        FOR EACH ROW EXECUTE FUNCTION cs_revision_guard('family_id');
        """
    )
    # Candidate revisions get a dedicated guard: accepted content is
    # immutable per §7.2, but *eligibility* is a separate assessment
    # axis and may move while every content column stays frozen.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION cs_candidate_revision_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.status = 'accepted_for_research' THEN
                    RAISE EXCEPTION 'immutable_revision: accepted candidate % cannot be deleted', OLD.id;
                END IF;
                RETURN OLD;
            END IF;
            IF TG_OP = 'UPDATE' AND OLD.status = 'accepted_for_research' THEN
                IF NEW.status = 'superseded' OR NEW.status = OLD.status THEN
                    IF NEW.payload IS NOT DISTINCT FROM OLD.payload
                       AND NEW.revision IS NOT DISTINCT FROM OLD.revision
                       AND NEW.content_hash IS NOT DISTINCT FROM OLD.content_hash
                       AND NEW.hypothesis IS NOT DISTINCT FROM OLD.hypothesis
                       AND NEW.entity_kind IS NOT DISTINCT FROM OLD.entity_kind
                       AND NEW.entity_revision_id IS NOT DISTINCT FROM OLD.entity_revision_id
                       AND NEW.parent_revision_id IS NOT DISTINCT FROM OLD.parent_revision_id
                       AND NEW.contract_revision_id IS NOT DISTINCT FROM OLD.contract_revision_id
                       AND NEW.workspace_id IS NOT DISTINCT FROM OLD.workspace_id
                       AND NEW.task_id IS NOT DISTINCT FROM OLD.task_id
                       AND NEW.created_by IS NOT DISTINCT FROM OLD.created_by
                       AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at THEN
                        RETURN NEW;
                    END IF;
                END IF;
                RAISE EXCEPTION 'immutable_revision: accepted candidate % content cannot be modified; eligibility may move freely', OLD.id;
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_candidate_revision_guard
        BEFORE UPDATE OR DELETE ON candidate_revisions
        FOR EACH ROW EXECUTE FUNCTION cs_candidate_revision_guard();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_candidate_revision_guard ON candidate_revisions")
    op.execute("DROP FUNCTION IF EXISTS cs_candidate_revision_guard()")
    op.execute("DROP TRIGGER IF EXISTS trg_process_revision_guard ON process_revisions")
    op.execute("DROP TRIGGER IF EXISTS trg_formulation_revision_guard ON formulation_revisions")
    op.drop_table("candidate_patches")
    op.drop_table("candidate_revisions")
    op.drop_constraint(
        "uq_contract_revisions_scope_id", "success_contract_revisions", type_="unique"
    )
    op.drop_table("process_revisions")
    op.drop_table("formulation_revisions")
    op.drop_table("formulation_families")
