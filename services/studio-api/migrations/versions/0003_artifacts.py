"""Private artifact records (§5.2, §9, CS-0103).

Revision ID: 0003_artifacts
Revises: 0002_auth_sessions
Create Date: 2026-10-05

Blob bytes live in the filesystem vault; this table holds the opaque
storage key, integrity metadata, per-use rights decisions and the
quarantine-first review chain.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_artifacts"
down_revision = "0002_auth_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(160), nullable=False),
        sa.Column("media_type", sa.String(200), nullable=False),
        sa.Column("byte_size", sa.BigInteger, nullable=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("declared_checksum", sa.String(64), nullable=True),
        sa.Column("original_name", sa.Text, nullable=False),
        sa.Column("source_kind", sa.String(16), nullable=False, server_default="upload"),
        sa.Column("classification", sa.String(16), nullable=False, server_default="confidential"),
        sa.Column("review_state", sa.String(16), nullable=False, server_default="quarantined"),
        sa.Column("upload_state", sa.String(16), nullable=False, server_default="receiving"),
        sa.Column(
            "rights",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text(
                '\'{"retrieval":"unknown","extraction":"unknown",'
                '"training":"unknown","export":"unknown",'
                '"redistribution":"unknown"}\'::jsonb'
            ),
        ),
        sa.Column("parser_version", sa.String(64), nullable=True),
        sa.Column("access_scope", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("retention", postgresql.JSONB, nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "created_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_artifacts_scope_creator",
        ),
        sa.UniqueConstraint("workspace_id", "storage_key", name="uq_artifacts_scope_key"),
        sa.CheckConstraint(
            "upload_state IN ('receiving','committed','aborted')", name="upload_state"
        ),
        sa.CheckConstraint(
            "review_state IN ('quarantined','parsed','needs_review','accepted','rejected','superseded','revoked')",
            name="review_state",
        ),
        sa.CheckConstraint(
            "classification IN ('internal','confidential','restricted')", name="classification"
        ),
        sa.CheckConstraint("source_kind IN ('upload','import','derived')", name="source_kind"),
    )
    op.create_index("ix_artifacts_workspace_id", "artifacts", ["workspace_id"])
    op.create_index("ix_artifacts_scope_list", "artifacts", ["workspace_id", "created_at", "id"])
    op.create_index("ix_artifacts_checksum", "artifacts", ["workspace_id", "checksum_sha256"])


def downgrade() -> None:
    op.drop_table("artifacts")
