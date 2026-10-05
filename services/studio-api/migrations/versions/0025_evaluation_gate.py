"""evaluation registry + hidden labels + runs + promotion decisions (§18, CS-0803).

``evaluation_suites`` holds the versioned PUBLIC suite contract —
tasks, allowed-context reference, pinned tool catalog, budget,
scoring, review rules, acceptance thresholds — never the hidden
targets. ``evaluation_labels`` is the hidden store reachable only via
the evaluation service principal's ``read_eval_labels`` grant
(AT-0803-2). ``evaluation_runs`` records matched-comparison reports
and ``promotion_decisions`` the gate's verdict, blockers, model card
and decision digest.

Revision ID: 0025_evaluation_gate
Revises: 0024_model_registry
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0025_evaluation_gate"
down_revision: str | None = "0024_model_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SUITE_STATES = "'draft','frozen'"
_SUITE_KINDS = "'development','final'"
_RUN_STATES = "'running','completed','failed'"


def upgrade() -> None:
    op.create_table(
        "evaluation_suites",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("definition", pg.JSONB(), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("capability", pg.JSONB(), nullable=False),
        sa.Column("provenance", pg.JSONB(), nullable=False),
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
            name="fk_evaluation_suites_scope_task",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "created_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_evaluation_suites_scope_creator",
        ),
        sa.UniqueConstraint("workspace_id", "name", "version", name="uq_evaluation_suites_version"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_evaluation_suites_scope_id"),
        sa.CheckConstraint(f"state IN ({_SUITE_STATES})", name="eval_suite_state"),
        sa.CheckConstraint(f"kind IN ({_SUITE_KINDS})", name="eval_suite_kind"),
    )
    op.create_index(
        "ix_evaluation_suites_scope",
        "evaluation_suites",
        ["workspace_id", "task_id", "created_at", "id"],
    )

    op.create_table(
        "evaluation_labels",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("suite_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("example_id", sa.String(length=120), nullable=False),
        sa.Column("target", pg.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "suite_id"],
            ["evaluation_suites.workspace_id", "evaluation_suites.id"],
            ondelete="CASCADE",
            name="fk_evaluation_labels_scope_suite",
        ),
        sa.UniqueConstraint("suite_id", "example_id", name="uq_evaluation_labels_example"),
    )
    op.create_index(
        "ix_evaluation_labels_suite",
        "evaluation_labels",
        ["workspace_id", "suite_id"],
    )

    op.create_table(
        "evaluation_runs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("suite_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("suite_digest", sa.String(length=64), nullable=False),
        sa.Column("model_release_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("baseline_release_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("backend", pg.JSONB(), nullable=False),
        sa.Column("comparison", pg.JSONB(), nullable=False),
        sa.Column("contamination", pg.JSONB(), nullable=False),
        sa.Column("blockers", pg.JSONB(), nullable=False),
        sa.Column("report_artifact_id", pg.UUID(as_uuid=True), nullable=True),
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
            ["workspace_id", "suite_id"],
            ["evaluation_suites.workspace_id", "evaluation_suites.id"],
            name="fk_evaluation_runs_scope_suite",
        ),
        sa.ForeignKeyConstraint(
            ["model_release_id"], ["model_releases.id"], name="fk_evaluation_runs_release"
        ),
        sa.ForeignKeyConstraint(
            ["baseline_release_id"], ["model_releases.id"], name="fk_evaluation_runs_baseline"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "created_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_evaluation_runs_scope_creator",
        ),
        sa.CheckConstraint(f"state IN ({_RUN_STATES})", name="eval_run_state"),
    )
    op.create_index(
        "ix_evaluation_runs_release",
        "evaluation_runs",
        ["workspace_id", "model_release_id", "created_at", "id"],
    )

    op.create_table(
        "promotion_decisions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("model_release_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_run_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        sa.Column("blockers", pg.JSONB(), nullable=False),
        sa.Column("model_card", pg.JSONB(), nullable=False),
        sa.Column("decision_digest", sa.String(length=64), nullable=False),
        sa.Column("approval_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["model_release_id"],
            ["model_releases.id"],
            name="fk_promotion_decisions_release",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"], ["evaluation_runs.id"], name="fk_promotion_decisions_run"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "created_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_promotion_decisions_scope_creator",
        ),
    )
    op.create_index(
        "ix_promotion_decisions_release",
        "promotion_decisions",
        ["workspace_id", "model_release_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_promotion_decisions_release", table_name="promotion_decisions")
    op.drop_table("promotion_decisions")
    op.drop_index("ix_evaluation_runs_release", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_index("ix_evaluation_labels_suite", table_name="evaluation_labels")
    op.drop_table("evaluation_labels")
    op.drop_index("ix_evaluation_suites_scope", table_name="evaluation_suites")
    op.drop_table("evaluation_suites")
