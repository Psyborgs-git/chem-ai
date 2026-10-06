"""Feasibility evidence reports + inert export-review proposals (§20.1-20.2, CS-1001).

Revision ID: 0026
Revises: 0025
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026_feasibility_fallback"
down_revision = "0025_evaluation_gate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_feasibility_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("basis", sa.String(length=40), nullable=False),
        sa.Column("sizes", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("envelope", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("configurations", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("uncertainty", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("reasons", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("missing", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("hardware", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["runs.workspace_id", "runs.id"],
            name="fk_feasibility_scope_run",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "evaluated_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_feasibility_scope_evaluator",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_feasibility_scope_id"),
        sa.CheckConstraint("verdict IN ('feasible','infeasible')", name="verdict"),
    )
    op.create_index(
        "ix_feasibility_scope_run",
        "run_feasibility_reports",
        ["workspace_id", "run_id", "created_at", "id"],
    )
    op.create_table(
        "export_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feasibility_report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposed_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="proposed"),
        sa.Column("bound_inputs", postgresql.JSONB(), nullable=False),
        sa.Column("bound_digest", sa.String(length=64), nullable=False),
        sa.Column("required_capability", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["runs.workspace_id", "runs.id"],
            name="fk_export_proposals_scope_run",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "feasibility_report_id"],
            ["run_feasibility_reports.workspace_id", "run_feasibility_reports.id"],
            name="fk_export_proposals_scope_report",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "proposed_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_export_proposals_scope_proposer",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_export_proposals_scope_id"),
        sa.CheckConstraint(
            "status IN ('proposed','approved','rejected','withdrawn')", name="status"
        ),
    )
    op.create_index(
        "ix_export_proposals_scope_run",
        "export_proposals",
        ["workspace_id", "run_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_table("export_proposals")
    op.drop_table("run_feasibility_reports")
