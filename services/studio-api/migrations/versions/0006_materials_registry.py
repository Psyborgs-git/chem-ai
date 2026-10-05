"""Materials registry: identities, proposed matches, grades, lots,
reference products and their revisions (§5, CS-0203).

Reference-product revisions reuse the CS-0101 immutable-revision
guard: once frozen, only a status transition to 'superseded' is
permitted — corrections create new revisions.

Revision ID: 0006_materials_registry
Revises: 0005_task_lifecycle
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_materials_registry"
down_revision = "0005_task_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "material_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("identifiers", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("structure", sa.Text, nullable=True),
        sa.Column("structure_format", sa.String(24), nullable=True),
        sa.Column("structure_status", sa.String(16), nullable=False, server_default="none"),
        sa.Column("aliases", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("confidentiality", sa.String(24), nullable=False, server_default="internal"),
        sa.Column("evidence_status", sa.String(24), nullable=False, server_default="unverified"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_material_identities_scope_id"),
        sa.CheckConstraint(
            "kind IN ('defined_molecule','polymer','commercial_mixture','substance_class','unknown')",
            name="kind",
        ),
        sa.CheckConstraint(
            "evidence_status IN ('unverified','documented','reviewed')",
            name="evidence_status",
        ),
        sa.CheckConstraint(
            "structure_status IN ('none','unreviewed','reviewed')", name="structure_status"
        ),
        sa.CheckConstraint(
            "confidentiality IN ('public','internal','confidential')", name="confidentiality"
        ),
    )
    op.create_index(
        "ix_material_identities_scope_list",
        "material_identities",
        ["workspace_id", "created_at", "id"],
    )

    op.create_table(
        "identity_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("proposed_by", sa.String(80), nullable=False, server_default="user"),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id", "source_identity_id"],
            ["material_identities.workspace_id", "material_identities.id"],
            name="fk_identity_matches_scope_source",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "candidate_identity_id"],
            ["material_identities.workspace_id", "material_identities.id"],
            name="fk_identity_matches_scope_candidate",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "reviewed_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_identity_matches_scope_reviewer",
        ),
        sa.CheckConstraint("status IN ('proposed','accepted','rejected')", name="status"),
    )
    op.create_index(
        "ix_identity_matches_scope_list",
        "identity_matches",
        ["workspace_id", "created_at", "id"],
    )

    op.create_table(
        "material_grades",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier", sa.String(300), nullable=False),
        sa.Column("grade_name", sa.String(300), nullable=False),
        sa.Column("active_content", postgresql.JSONB, nullable=True),
        sa.Column("specifications", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("reconciled_into", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "material_id"],
            ["material_identities.workspace_id", "material_identities.id"],
            name="fk_material_grades_scope_material",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_material_grades_scope_id"),
    )
    op.create_index(
        "ix_material_grades_scope_list",
        "material_grades",
        ["workspace_id", "material_id", "created_at", "id"],
    )

    op.create_table(
        "material_lots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grade_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lot_number", sa.String(120), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "certificate_artifact_ids", postgresql.JSONB, nullable=False, server_default="[]"
        ),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "grade_id"],
            ["material_grades.workspace_id", "material_grades.id"],
            name="fk_material_lots_scope_grade",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_material_lots_scope_id"),
    )
    op.create_index(
        "ix_material_lots_scope_list",
        "material_lots",
        ["workspace_id", "grade_id", "created_at", "id"],
    )

    op.create_table(
        "reference_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("aliases", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("supplier", sa.String(300), nullable=True),
        sa.Column("category", sa.String(160), nullable=True),
        sa.Column("composition_knowledge", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column(
            "documentation_artifact_ids", postgresql.JSONB, nullable=False, server_default="[]"
        ),
        sa.Column("current_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_reference_products_scope_id"),
        sa.CheckConstraint(
            "composition_knowledge IN ('known','partial','unknown')",
            name="composition_knowledge",
        ),
    )
    op.create_index(
        "ix_reference_products_scope_list",
        "reference_products",
        ["workspace_id", "created_at", "id"],
    )

    op.create_table(
        "reference_product_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
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
            ["workspace_id", "product_id"],
            ["reference_products.workspace_id", "reference_products.id"],
            name="fk_reference_product_revisions_scope_product",
        ),
        sa.UniqueConstraint("product_id", "revision", name="uq_refprod_product_revision"),
        sa.CheckConstraint("status IN ('draft','frozen','superseded')", name="status"),
    )
    op.create_index(
        "ix_reference_product_revisions_product",
        "reference_product_revisions",
        ["workspace_id", "product_id", "revision"],
    )
    op.execute(
        """
        CREATE TRIGGER trg_refprod_revision_guard
        BEFORE UPDATE OR DELETE ON reference_product_revisions
        FOR EACH ROW EXECUTE FUNCTION cs_revision_guard('product_id');
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_refprod_revision_guard ON reference_product_revisions")
    op.drop_table("reference_product_revisions")
    op.drop_table("reference_products")
    op.drop_table("material_lots")
    op.drop_table("material_grades")
    op.drop_table("identity_matches")
    op.drop_table("material_identities")
