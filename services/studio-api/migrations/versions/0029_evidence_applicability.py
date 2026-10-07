"""Reviewed evidence→candidate applicability mappings (§12.3, PAR-02).

Revision ID: 0029_evidence_applicability
Revises: 0028_export_jobs
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0029_evidence_applicability"
down_revision = "0028_export_jobs"
branch_labels = None
depends_on = None

EVIDENCE_APPLICABILITY_STATUSES = ("applicable", "not_applicable")


def upgrade() -> None:
    op.create_table(
        "evidence_applicability",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column(
            "measurement_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "candidate_revision_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "contract_revision_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("status", sa.String(24), nullable=False, server_default="applicable"),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column(
            "reviewed_by", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["workspace_id", "measurement_id"],
            ["measurements.workspace_id", "measurements.id"],
            name="fk_evapp_scope_measurement",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "candidate_revision_id"],
            ["candidate_revisions.workspace_id", "candidate_revisions.id"],
            name="fk_evapp_scope_candidate",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "contract_revision_id"],
            ["success_contract_revisions.workspace_id", "success_contract_revisions.id"],
            name="fk_evapp_scope_contract",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "reviewed_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_evapp_scope_reviewer",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "measurement_id",
            "candidate_revision_id",
            name="uq_evapp_pair",
        ),
        sa.CheckConstraint(
            f"status IN {EVIDENCE_APPLICABILITY_STATUSES!r}", name="status"
        ),
    )
    op.create_index(
        "ix_evapp_candidate",
        "evidence_applicability",
        ["workspace_id", "candidate_revision_id"],
    )
    op.create_index(
        "ix_evapp_measurement",
        "evidence_applicability",
        ["workspace_id", "measurement_id"],
    )


def downgrade() -> None:
    op.drop_table("evidence_applicability")
