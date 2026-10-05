"""Quarantined ingestion batches + proposed extracted records
(§9, CS-0301).

Revision ID: 0008_ingestion
Revises: 0007_formulations_candidates
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_ingestion"
down_revision = "0007_formulations_candidates"
branch_labels = None
depends_on = None

IMPORT_STATUSES = ("quarantined", "parsed", "failed")
RECORD_STATUSES = ("proposed", "accepted", "rejected")


def upgrade() -> None:
    # Scoped composite FKs need a unique target on (workspace_id, id).
    op.create_unique_constraint("uq_artifacts_scope_id", "artifacts", ["workspace_id", "id"])
    op.create_table(
        "import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("original_name", sa.Text, nullable=False),
        sa.Column("detected_type", sa.String(16), nullable=False),
        sa.Column("parser_name", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("document_group", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_revision", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("findings", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("record_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "artifact_id"],
            ["artifacts.workspace_id", "artifacts.id"],
            name="fk_import_batches_scope_artifact",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "checksum_sha256",
            "parser_version",
            name="uq_import_batches_dedup",
        ),
        sa.CheckConstraint(f"status IN {IMPORT_STATUSES!r}", name="import_status"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_import_batches_scope_id"),
        sa.Index("ix_import_batches_scope_list", "workspace_id", "created_at", "id"),
        sa.Index("ix_import_batches_group", "workspace_id", "document_group"),
    )
    op.create_table(
        "extracted_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("locator", postgresql.JSONB, nullable=False),
        sa.Column("original_text", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=True),
        sa.Column("flags", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "batch_id"],
            ["import_batches.workspace_id", "import_batches.id"],
            name="fk_extracted_records_scope_batch",
        ),
        sa.CheckConstraint(f"status IN {RECORD_STATUSES!r}", name="record_status"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="record_confidence_range"),
        sa.Index("ix_extracted_records_batch", "workspace_id", "batch_id", "id"),
    )


def downgrade() -> None:
    op.drop_table("extracted_records")
    op.drop_table("import_batches")
    op.drop_constraint("uq_artifacts_scope_id", "artifacts", type_="unique")
