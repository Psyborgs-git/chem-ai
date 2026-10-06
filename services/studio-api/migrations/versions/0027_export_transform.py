"""Minimal transformed export payloads + disclosure review (§20.2-20.3, CS-1002).

Revision ID: 0027
Revises: 0026
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0027_export_transform"
down_revision = "0026_feasibility_fallback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE export_payloads_seq")
    op.create_table(
        "export_transformed_payloads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # "latest payload" ordering survives identical transaction
        # timestamps — seq, not created_at.
        sa.Column(
            "seq",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("nextval('export_payloads_seq')"),
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Frozen dataset snapshot the records were drawn from (no FK —
        # dataset_snapshots has no scope unique key).
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=48), nullable=False),
        sa.Column("transformation_version", sa.String(length=64), nullable=False),
        sa.Column("classification", sa.String(length=16), nullable=False),
        sa.Column("source_classification", sa.String(length=16), nullable=False),
        sa.Column("classification_review", postgresql.JSONB(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_digest", sa.String(length=64), nullable=False),
        sa.Column("payload_fields", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("redaction_report", postgresql.JSONB(), nullable=False),
        sa.Column("residual_report", postgresql.JSONB(), nullable=False),
        sa.Column("manifest", postgresql.JSONB(), nullable=False),
        sa.Column("bound_inputs", postgresql.JSONB(), nullable=False),
        sa.Column("bound_digest", sa.String(length=64), nullable=False),
        # LOCAL-ONLY alias decode table — never part of the payload, its
        # digest, or any API response.
        sa.Column("local_alias_map", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "proposal_id"],
            ["export_proposals.workspace_id", "export_proposals.id"],
            name="fk_export_payloads_scope_proposal",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "created_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_export_payloads_scope_creator",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_export_payloads_scope_id"),
        sa.CheckConstraint(
            "classification IN ('internal','confidential','restricted')",
            name="classification",
        ),
    )
    op.create_index(
        "ix_export_payloads_scope_proposal",
        "export_transformed_payloads",
        ["workspace_id", "proposal_id", "seq"],
    )


def downgrade() -> None:
    op.drop_table("export_transformed_payloads")
    op.execute("DROP SEQUENCE export_payloads_seq")
