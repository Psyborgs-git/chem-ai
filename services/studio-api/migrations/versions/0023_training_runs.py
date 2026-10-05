"""training_runs — local SFT training lifecycle (§17.5, CS-0801).

Separate state machine from ``runs.status``: a training run holds
dataset_validated/awaiting_approval/evaluating/candidate_release states
an execution record never has. ``run_id`` links to the newest
execution Run for queue bookkeeping; resume provenance lives in
``resume_from``/``provenance``. All artifact references are
vault-scoped and confidential.

Revision ID: 0023_training_runs
Revises: 0022_analytics
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0023_training_runs"
down_revision: str | None = "0022_analytics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATES = (
    "'draft','dataset_validated','awaiting_approval','queued','running',"
    "'completed','evaluating','candidate_release','promoted','rejected',"
    "'failed','cancelled','blocked'"
)


def upgrade() -> None:
    op.create_table(
        "training_runs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("snapshot_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_digest", sa.String(length=64), nullable=False),
        sa.Column("spec", pg.JSONB(), nullable=False),
        sa.Column("spec_digest", sa.String(length=64), nullable=False),
        sa.Column("dataset_artifact_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("dataset_digest", sa.String(length=64), nullable=True),
        sa.Column("dataset_manifest", pg.JSONB(), nullable=False),
        sa.Column("config_artifact_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("adapter_artifact_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("result_artifact_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("run_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("approval_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("bound_digest", sa.String(length=64), nullable=True),
        sa.Column("telemetry", pg.JSONB(), nullable=False),
        sa.Column("checkpoints", pg.JSONB(), nullable=False),
        sa.Column("resume_from", pg.JSONB(), nullable=True),
        sa.Column("provenance", pg.JSONB(), nullable=False),
        sa.Column("capability", pg.JSONB(), nullable=False),
        sa.Column("error", pg.JSONB(), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["research_tasks.workspace_id", "research_tasks.id"],
            name="fk_training_runs_scope_task",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["dataset_snapshots.id"],
            name="fk_training_runs_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "created_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_training_runs_scope_creator",
        ),
        sa.CheckConstraint(f"state IN ({_STATES})", name="training_run_state"),
    )
    op.create_index(
        "ix_training_runs_scope",
        "training_runs",
        ["workspace_id", "state", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_training_runs_scope", table_name="training_runs")
    op.drop_table("training_runs")
