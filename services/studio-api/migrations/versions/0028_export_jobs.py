"""Export broker jobs, attempts, callbacks and receipts (§20.2-20.5, CS-1003).

Revision ID: 0028_export_jobs
Revises: 0027_export_transform
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0028_export_jobs"
down_revision = "0027_export_transform"
branch_labels = None
depends_on = None

EXPORT_JOB_STATUSES = (
    "pending",
    "transferring",
    "transferred",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "reconciling",
    "deleted",
    "denied",
)
EXPORT_ATTEMPT_OUTCOMES = (
    "validated",
    "denied",
    "transferred",
    "failed",
    "cancelled",
)
EXPORT_RECEIPT_KINDS = ("reconcile", "deletion", "cancellation")


def upgrade() -> None:
    op.create_table(
        "export_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("payload_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_job_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("manifest_digest", sa.String(length=64), nullable=False),
        sa.Column("payload_digest", sa.String(length=64), nullable=False),
        sa.Column("recipient", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "permitted_job",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bytes_transferred", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("artifact_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "seen_callback_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("last_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exposed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "external_state",
            sa.String(length=24),
            nullable=False,
            server_default="submitted",
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "payload_id"],
            ["export_transformed_payloads.workspace_id", "export_transformed_payloads.id"],
            name="fk_export_jobs_scope_payload",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "approval_id"],
            ["approvals.workspace_id", "approvals.id"],
            name="fk_export_jobs_scope_approval",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_export_jobs_scope_id"),
        sa.UniqueConstraint(
            "workspace_id",
            "payload_id",
            "manifest_digest",
            name="uq_export_jobs_manifest",
        ),
        sa.CheckConstraint(f"status IN {EXPORT_JOB_STATUSES!r}", name="ck_export_jobs_status"),
    )
    op.create_index("ix_export_jobs_scope_payload", "export_jobs", ["workspace_id", "payload_id"])
    op.create_index("ix_export_jobs_external", "export_jobs", ["external_job_id"])

    op.create_table(
        "export_job_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_key", sa.String(length=96), nullable=False),
        sa.Column("outcome", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("bytes_emitted", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("external_job_id", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "job_id"],
            ["export_jobs.workspace_id", "export_jobs.id"],
            name="fk_export_attempts_scope_job",
        ),
        sa.UniqueConstraint("workspace_id", "attempt_key", name="uq_export_attempts_key"),
        sa.CheckConstraint(
            f"outcome IN {EXPORT_ATTEMPT_OUTCOMES!r}",
            name="ck_export_attempts_outcome",
        ),
    )
    op.create_index(
        "ix_export_attempts_scope_job",
        "export_job_attempts",
        ["workspace_id", "job_id"],
    )

    op.create_table(
        "export_callbacks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("callback_id", sa.String(length=128), nullable=False),
        sa.Column("event", sa.String(length=40), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("artifacts", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "job_id"],
            ["export_jobs.workspace_id", "export_jobs.id"],
            name="fk_export_callbacks_scope_job",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "job_id",
            "callback_id",
            name="uq_export_callbacks_dedupe",
        ),
    )

    op.create_table(
        "export_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("receipt_ref", sa.String(length=128), nullable=True),
        sa.Column("bytes_transferred", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("artifact_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "unresolved_retention",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("exposed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("raw", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "job_id"],
            ["export_jobs.workspace_id", "export_jobs.id"],
            name="fk_export_receipts_scope_job",
        ),
        sa.CheckConstraint(f"kind IN {EXPORT_RECEIPT_KINDS!r}", name="ck_export_receipts_kind"),
    )
    op.create_index("ix_export_receipts_scope_job", "export_receipts", ["workspace_id", "job_id"])


def downgrade() -> None:
    op.drop_index("ix_export_receipts_scope_job", table_name="export_receipts")
    op.drop_table("export_receipts")
    op.drop_table("export_callbacks")
    op.drop_index("ix_export_attempts_scope_job", table_name="export_job_attempts")
    op.drop_table("export_job_attempts")
    op.drop_index("ix_export_jobs_external", table_name="export_jobs")
    op.drop_index("ix_export_jobs_scope_payload", table_name="export_jobs")
    op.drop_table("export_jobs")
