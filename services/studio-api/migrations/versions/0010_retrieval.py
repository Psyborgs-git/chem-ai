"""Scoped retrieval index + manifests (§9.4, §10, CS-0303).

Revision ID: 0010_retrieval
Revises: 0009_evidence_claims
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_retrieval"
down_revision = "0009_evidence_claims"
branch_labels = None
depends_on = None

CHUNK_STATUSES = ("active", "superseded", "revoked")


def upgrade() -> None:
    op.create_table(
        "source_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("locator", postgresql.JSONB, nullable=False),
        sa.Column("original_text", sa.Text, nullable=False),
        sa.Column("normalized_text", sa.Text, nullable=False),
        sa.Column("extraction_method", sa.String(64), nullable=False),
        sa.Column("uncertainty", sa.Float, nullable=True),
        sa.Column("chunking_version", sa.String(32), nullable=False),
        sa.Column("rights", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("acl_scope", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("eval_allowed", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
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
            name="fk_source_chunks_scope_artifact",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "batch_id"],
            ["import_batches.workspace_id", "import_batches.id"],
            name="fk_source_chunks_scope_batch",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "record_id"],
            ["extracted_records.workspace_id", "extracted_records.id"],
            name="fk_source_chunks_scope_record",
        ),
        sa.CheckConstraint(f"status IN {CHUNK_STATUSES!r}", name="chunk_status"),
        sa.Index("ix_source_chunks_scope_list", "workspace_id", "created_at", "id"),
        sa.Index("ix_source_chunks_artifact", "workspace_id", "artifact_id"),
        sa.Index("ix_source_chunks_status", "workspace_id", "status"),
    )
    # Full-text index for the lexical-first retrieval path (§10).
    op.execute(
        "CREATE INDEX ix_source_chunks_fts ON source_chunks "
        "USING gin (to_tsvector('english', normalized_text))"
    )
    op.create_table(
        "retrieval_manifests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("query_kind", sa.String(32), nullable=False),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("source_index_version", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("eval_context", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("chunk_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("cached", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Index("ix_retrieval_manifests_scope", "workspace_id", "created_at", "id"),
    )
    op.create_table(
        "retrieval_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("chunk_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("workspace_id", "cache_key", name="uq_retrieval_cache_key"),
    )


def downgrade() -> None:
    op.drop_table("retrieval_cache")
    op.drop_table("retrieval_manifests")
    op.execute("DROP INDEX IF EXISTS ix_source_chunks_fts")
    op.drop_table("source_chunks")
