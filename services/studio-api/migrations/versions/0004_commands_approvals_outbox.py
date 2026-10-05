"""Commands, approvals, outbox, audit (§7.4, §21.3, CS-0105).

Idempotency outcomes persist in the same transaction as the domain
change and its outbox events; deliveries deduplicate per consumer;
approvals bind an exact canonical digest; audit rows carry minimal
metadata only.

Revision ID: 0004_commands_approvals_outbox
Revises: 0003_artifacts
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_commands_approvals_outbox"
down_revision = "0003_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(120), nullable=False),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("response", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="succeeded"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id", "principal_id"],
            ["principals.workspace_id", "principals.id"],
            name="fk_idempotency_scope_principal",
        ),
        sa.UniqueConstraint("workspace_id", "operation", "key", name="uq_idempotency_scope_op_key"),
        sa.CheckConstraint("status IN ('succeeded','failed')", name="status"),
    )
    op.create_index("ix_idempotency_records_workspace_id", "idempotency_records", ["workspace_id"])

    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_outbox_events_workspace_id", "outbox_events", ["workspace_id"])
    op.create_index(
        "ix_outbox_events_pending", "outbox_events", ["workspace_id", "created_at", "id"]
    )

    op.create_table(
        "outbox_deliveries",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consumer", sa.String(80), primary_key=True),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["outbox_events.id"],
            ondelete="CASCADE",
            name="fk_outbox_deliveries_event",
        ),
    )

    op.create_table(
        "approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bound_digest", sa.String(64), nullable=False),
        sa.Column("bound_inputs", postgresql.JSONB, nullable=False),
        sa.Column("policy_version", sa.String(40), nullable=False),
        sa.Column("envelope", postgresql.JSONB, nullable=True),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "decided_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_approvals_scope_decider",
        ),
        sa.CheckConstraint("decision IN ('approved','rejected')", name="decision"),
    )
    op.create_index("ix_approvals_workspace_id", "approvals", ["workspace_id"])
    op.create_index(
        "ix_approvals_scope_action", "approvals", ["workspace_id", "action", "created_at"]
    )

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("target_type", sa.String(80), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("detail", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "actor_id"],
            ["principals.workspace_id", "principals.id"],
            name="fk_audit_scope_actor",
        ),
    )
    op.create_index("ix_audit_events_workspace_id", "audit_events", ["workspace_id"])
    op.create_index(
        "ix_audit_events_scope_list", "audit_events", ["workspace_id", "created_at", "id"]
    )
    op.create_index(
        "ix_audit_events_target", "audit_events", ["workspace_id", "target_type", "target_id"]
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("approvals")
    op.drop_table("outbox_deliveries")
    op.drop_table("outbox_events")
    op.drop_table("idempotency_records")
