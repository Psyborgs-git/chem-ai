"""Source lineage + revocation impact records (§9.4, §17.5, CS-0305).

Revision ID: 0012_evidence_revocation
Revises: 0011_task_memory
Create Date: 2026-10-08
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_evidence_revocation"
down_revision = "0011_task_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "artifacts",
        sa.Column(
            "source_artifact_ids",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
    )
    op.create_table(
        "source_revocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("revoked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("report", postgresql.JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "artifact_id"],
            ["artifacts.workspace_id", "artifacts.id"],
            name="fk_source_revocations_scope_artifact",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "revoked_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_source_revocations_scope_revoker",
        ),
        sa.UniqueConstraint("workspace_id", "artifact_id", name="uq_source_revocations_artifact"),
        sa.Index("ix_source_revocations_scope_list", "workspace_id", "created_at", "id"),
    )


def downgrade() -> None:
    op.drop_table("source_revocations")
    op.drop_column("artifacts", "source_artifact_ids")
