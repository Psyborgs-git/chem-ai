"""Evidence claims + support/contradiction links (§10, CS-0302).

Revision ID: 0009_evidence_claims
Revises: 0008_ingestion
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_evidence_claims"
down_revision = "0008_ingestion"
branch_labels = None
depends_on = None

CLAIM_KINDS = ("document_claim", "inferred_suggestion", "measured_outcome")
CLAIM_STATUSES = ("proposed", "accepted", "rejected", "superseded")
CLAIM_RELATIONS = ("supports", "contradicts")


def upgrade() -> None:
    # Scoped composite FK targets.
    op.create_unique_constraint(
        "uq_extracted_records_scope_id",
        "extracted_records",
        ["workspace_id", "id"],
    )
    op.create_table(
        "evidence_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("subject", postgresql.JSONB, nullable=False),
        sa.Column("statement", postgresql.JSONB, nullable=False),
        sa.Column("locator", postgresql.JSONB, nullable=True),
        sa.Column("original_text", sa.Text, nullable=True),
        sa.Column("conditions", postgresql.JSONB, nullable=True),
        sa.Column("source_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "source_record_id"],
            ["extracted_records.workspace_id", "extracted_records.id"],
            name="fk_evidence_claims_scope_record",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "source_batch_id"],
            ["import_batches.workspace_id", "import_batches.id"],
            name="fk_evidence_claims_scope_batch",
        ),
        sa.CheckConstraint(f"kind IN {CLAIM_KINDS!r}", name="claim_kind"),
        sa.CheckConstraint(f"status IN {CLAIM_STATUSES!r}", name="claim_status"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_evidence_claims_scope_id"),
        sa.Index("ix_evidence_claims_scope_list", "workspace_id", "created_at", "id"),
        sa.Index("ix_evidence_claims_kind", "workspace_id", "kind"),
    )
    op.create_table(
        "claim_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relation", sa.String(16), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "from_claim_id"],
            ["evidence_claims.workspace_id", "evidence_claims.id"],
            name="fk_claim_links_scope_from",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "to_claim_id"],
            ["evidence_claims.workspace_id", "evidence_claims.id"],
            name="fk_claim_links_scope_to",
        ),
        sa.CheckConstraint(f"relation IN {CLAIM_RELATIONS!r}", name="claim_relation"),
        sa.CheckConstraint("from_claim_id <> to_claim_id", name="claim_link_distinct"),
        sa.UniqueConstraint(
            "workspace_id",
            "from_claim_id",
            "to_claim_id",
            "relation",
            name="uq_claim_links_edge",
        ),
        sa.Index("ix_claim_links_from", "workspace_id", "from_claim_id"),
        sa.Index("ix_claim_links_to", "workspace_id", "to_claim_id"),
    )


def downgrade() -> None:
    op.drop_table("claim_links")
    op.drop_table("evidence_claims")
    op.drop_constraint("uq_extracted_records_scope_id", "extracted_records", type_="unique")
