"""Lab executions, batches, samples, measurements and amendments —
manual-first recording with immutable originals (§6.3, §14.2, CS-0502).

Revision ID: 0018_lab_measurements
Revises: 0017_experiment_plans
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0018_lab_measurements"
down_revision = "0017_experiment_plans"
branch_labels = None
depends_on = None

_VERSION_COL = sa.Column("version", sa.Integer(), nullable=False, server_default="1")
_TS_COLS = (
    sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    ),
)


def upgrade() -> None:
    op.create_table(
        "lab_executions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", UUID(as_uuid=True), nullable=True),
        sa.Column("task_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="in_progress"),
        sa.Column("historical", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("actual", JSONB, nullable=False, server_default="{}"),
        sa.Column("deviations", JSONB, nullable=False, server_default="[]"),
        sa.Column("observations", sa.Text(), nullable=True),
        sa.Column("opened_by", UUID(as_uuid=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        *_TS_COLS,
        _VERSION_COL,
        sa.ForeignKeyConstraint(
            ["workspace_id", "plan_id"],
            ["experiment_plans.workspace_id", "experiment_plans.id"],
            name="fk_lab_executions_scope_plan",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_lab_executions_scope_id"),
        sa.CheckConstraint("status IN ('in_progress','completed','stopped')", name="status"),
    )
    op.create_index(
        "ix_lab_executions_scope_plan",
        "lab_executions",
        ["workspace_id", "plan_id", "created_at", "id"],
    )

    op.create_table(
        "lab_batches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        *_TS_COLS,
        _VERSION_COL,
        sa.ForeignKeyConstraint(
            ["workspace_id", "execution_id"],
            ["lab_executions.workspace_id", "lab_executions.id"],
            name="fk_lab_batches_scope_execution",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_lab_batches_scope_id"),
    )
    op.create_index(
        "ix_lab_batches_scope_execution",
        "lab_batches",
        ["workspace_id", "execution_id", "created_at", "id"],
    )

    op.create_table(
        "lab_samples",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="aliquot"),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        *_TS_COLS,
        _VERSION_COL,
        sa.ForeignKeyConstraint(
            ["workspace_id", "batch_id"],
            ["lab_batches.workspace_id", "lab_batches.id"],
            name="fk_lab_samples_scope_batch",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_lab_samples_scope_id"),
        sa.CheckConstraint("kind IN ('aliquot','timepoint','whole')", name="kind"),
    )
    op.create_index(
        "ix_lab_samples_scope_batch",
        "lab_samples",
        ["workspace_id", "batch_id", "created_at", "id"],
    )

    op.create_table(
        "measurements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("sample_id", UUID(as_uuid=True), nullable=False),
        sa.Column("method", sa.String(300), nullable=False),
        sa.Column("repeat_type", sa.String(32), nullable=False),
        sa.Column("value_type", sa.String(24), nullable=False),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("conditions", JSONB, nullable=False, server_default="{}"),
        sa.Column("applicable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("applicability_note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by", UUID(as_uuid=True), nullable=True),
        sa.Column("pipeline_version", sa.String(120), nullable=True),
        sa.Column("artifact_id", UUID(as_uuid=True), nullable=True),
        sa.Column("superseded_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        *_TS_COLS,
        _VERSION_COL,
        sa.ForeignKeyConstraint(
            ["workspace_id", "sample_id"],
            ["lab_samples.workspace_id", "lab_samples.id"],
            name="fk_measurements_scope_sample",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_measurements_scope_id"),
        sa.CheckConstraint(
            "status IN ('proposed','accepted','rejected','superseded')", name="status"
        ),
        sa.CheckConstraint(
            "repeat_type IN ('same_sample','independent_batch','independent_operator','timepoint')",
            name="repeat_type",
        ),
        sa.CheckConstraint(
            "value_type IN ('numeric','interval','below_detection','above_quantification','ordinal','categorical','missing')",
            name="value_type",
        ),
    )
    op.create_index(
        "ix_measurements_scope_sample",
        "measurements",
        ["workspace_id", "sample_id", "created_at", "id"],
    )

    op.create_table(
        "measurement_amendments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("measurement_id", UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("conditions", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "measurement_id"],
            ["measurements.workspace_id", "measurements.id"],
            name="fk_amendments_scope_measurement",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_amendments_scope_id"),
    )
    op.create_index(
        "ix_amendments_scope_measurement",
        "measurement_amendments",
        ["workspace_id", "measurement_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_amendments_scope_measurement", table_name="measurement_amendments")
    op.drop_table("measurement_amendments")
    op.drop_index("ix_measurements_scope_sample", table_name="measurements")
    op.drop_table("measurements")
    op.drop_index("ix_lab_samples_scope_batch", table_name="lab_samples")
    op.drop_table("lab_samples")
    op.drop_index("ix_lab_batches_scope_execution", table_name="lab_batches")
    op.drop_table("lab_batches")
    op.drop_index("ix_lab_executions_scope_plan", table_name="lab_executions")
    op.drop_table("lab_executions")
