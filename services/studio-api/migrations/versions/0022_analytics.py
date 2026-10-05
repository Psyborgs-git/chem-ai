"""Analytical series + scoped comparisons (CS-0703)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0022_analytics"
down_revision: str | None = "0021_optimization_campaigns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analytical_series",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("sample_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("instrument", pg.JSONB(), nullable=False),
        sa.Column("calibration", pg.JSONB(), nullable=True),
        sa.Column("sample", pg.JSONB(), nullable=False),
        sa.Column("source_format", sa.String(32), nullable=True),
        sa.Column("interpretation_state", sa.String(16), nullable=False),
        sa.Column("raw_artifact_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("processed_artifact_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("transform", pg.JSONB(), nullable=True),
        sa.Column("detail", pg.JSONB(), nullable=False),
        sa.Column("spec_digest", sa.String(64), nullable=False),
        sa.Column("creation_key", sa.String(100), nullable=False),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["research_tasks.workspace_id", "research_tasks.id"],
            name="fk_analytical_series_scope_task",
        ),
        sa.ForeignKeyConstraint(
            ["raw_artifact_id"], ["artifacts.id"], name="fk_analytical_series_raw"
        ),
        sa.ForeignKeyConstraint(
            ["processed_artifact_id"], ["artifacts.id"], name="fk_analytical_series_processed"
        ),
        sa.UniqueConstraint(
            "workspace_id", "task_id", "creation_key", name="uq_analytical_creation"
        ),
        sa.CheckConstraint(
            "interpretation_state IN ('processed', 'unsupported')", name="analytical_interpretation"
        ),
    )
    op.create_index("ix_analytical_series_workspace_id", "analytical_series", ["workspace_id"])
    op.create_index(
        "ix_analytical_series_task",
        "analytical_series",
        ["workspace_id", "task_id", "created_at", "id"],
    )
    op.create_table(
        "analytical_comparisons",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("left_series_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("right_series_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("result_artifact_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("similarity", pg.JSONB(), nullable=False),
        sa.Column("transform", pg.JSONB(), nullable=False),
        sa.Column("spec_digest", sa.String(64), nullable=False),
        sa.Column("creation_key", sa.String(100), nullable=False),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["research_tasks.workspace_id", "research_tasks.id"],
            name="fk_analytical_cmp_scope_task",
        ),
        sa.ForeignKeyConstraint(
            ["left_series_id"], ["analytical_series.id"], name="fk_analytical_cmp_left"
        ),
        sa.ForeignKeyConstraint(
            ["right_series_id"], ["analytical_series.id"], name="fk_analytical_cmp_right"
        ),
        sa.ForeignKeyConstraint(
            ["result_artifact_id"], ["artifacts.id"], name="fk_analytical_cmp_result"
        ),
        sa.UniqueConstraint(
            "workspace_id", "task_id", "creation_key", name="uq_analytical_cmp_creation"
        ),
    )
    op.create_index(
        "ix_analytical_comparisons_workspace_id", "analytical_comparisons", ["workspace_id"]
    )
    op.create_index(
        "ix_analytical_cmp_task",
        "analytical_comparisons",
        ["workspace_id", "task_id", "created_at", "id"],
    )
    op.execute("""
    CREATE FUNCTION protect_analytical_series() RETURNS trigger AS $$
    BEGIN
      IF ROW(NEW.workspace_id, NEW.task_id, NEW.label, NEW.method, NEW.sample_id,
             NEW.instrument, NEW.calibration, NEW.sample, NEW.source_format,
             NEW.interpretation_state, NEW.raw_artifact_id,
             NEW.processed_artifact_id, NEW.transform, NEW.detail, NEW.spec_digest,
             NEW.creation_key, NEW.created_by)
         IS DISTINCT FROM ROW(OLD.workspace_id, OLD.task_id, OLD.label, OLD.method,
             OLD.sample_id, OLD.instrument, OLD.calibration, OLD.sample,
             OLD.source_format, OLD.interpretation_state, OLD.raw_artifact_id,
             OLD.processed_artifact_id, OLD.transform, OLD.detail, OLD.spec_digest,
             OLD.creation_key, OLD.created_by) THEN
        RAISE EXCEPTION 'analytical series records are immutable';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    CREATE TRIGGER analytical_series_immutable BEFORE UPDATE ON analytical_series
      FOR EACH ROW EXECUTE FUNCTION protect_analytical_series();
    CREATE FUNCTION protect_analytical_comparison() RETURNS trigger AS $$
    BEGIN
      IF ROW(NEW.workspace_id, NEW.task_id, NEW.left_series_id, NEW.right_series_id,
             NEW.result_artifact_id, NEW.similarity, NEW.transform, NEW.spec_digest,
             NEW.creation_key, NEW.created_by)
         IS DISTINCT FROM ROW(OLD.workspace_id, OLD.task_id, OLD.left_series_id,
             OLD.right_series_id, OLD.result_artifact_id, OLD.similarity,
             OLD.transform, OLD.spec_digest, OLD.creation_key, OLD.created_by) THEN
        RAISE EXCEPTION 'analytical comparison results are immutable';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    CREATE TRIGGER analytical_comparison_immutable BEFORE UPDATE ON analytical_comparisons
      FOR EACH ROW EXECUTE FUNCTION protect_analytical_comparison();
    """)


def downgrade() -> None:
    op.drop_table("analytical_comparisons")
    op.drop_table("analytical_series")
    op.execute("DROP FUNCTION protect_analytical_series()")
    op.execute("DROP FUNCTION protect_analytical_comparison()")
