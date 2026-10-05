"""dataset_snapshots — immutable purpose-specific training manifests
(§17.2, CS-0601). Manifest JSONB carries record ids/hashes/rights/
source classes/exclusion semantics; a frozen snapshot is never
rewritten — drift is detected by re-hashing the source records.

Revision ID: 0020_dataset_snapshots
Revises: 0019_measurement_metric
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_dataset_snapshots"
down_revision: str | None = "0019_measurement_metric"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dataset_snapshots",
        sa.Column("purpose", sa.String(length=48), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("manifest", postgresql.JSONB(), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("frozen_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "purpose IN ('property_prediction','extraction_correction',"
            "'assistant_sft','preference_pairs','rl_tasks')",
            name="dataset_purpose",
        ),
        sa.CheckConstraint("state IN ('draft','frozen')", name="dataset_state"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_dataset_snapshots_scope",
        "dataset_snapshots",
        ["workspace_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_dataset_snapshots_scope", table_name="dataset_snapshots")
    op.drop_table("dataset_snapshots")
