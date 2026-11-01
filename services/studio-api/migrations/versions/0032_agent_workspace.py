"""Private agent workspace, durable jobs and many models per provider."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0032_agent_workspace"
down_revision = "0031_private_library"
branch_labels = None
depends_on = None


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_inference_providers_scope_id", "inference_providers", ["workspace_id", "id"]
    )
    op.create_table(
        "agent_provider_models",
        *_base(),
        sa.Column("provider_id", UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", sa.String(160), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("roles", JSONB, nullable=False),
        sa.Column("supports_tools", sa.Boolean, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("input_price", sa.Float, nullable=True),
        sa.Column("output_price", sa.Float, nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id", "provider_id"],
            ["inference_providers.workspace_id", "inference_providers.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("workspace_id", "provider_id", "model_id"),
    )
    # Stable UUID derived from the existing provider avoids extension dependencies.
    op.execute(
        'INSERT INTO agent_provider_models (id,workspace_id,provider_id,model_id,label,roles,supports_tools,enabled) SELECT id,workspace_id,id,model,model,\'["planner","researcher","extractor","reviewer"]\'::jsonb,supports_tools,true FROM inference_providers'
    )
    op.create_table(
        "agent_workspace_policies",
        *_base(),
        sa.Column("owner_id", UUID(as_uuid=True), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.UniqueConstraint("workspace_id", "owner_id"),
    )
    op.create_table(
        "agent_workspace_threads",
        *_base(),
        sa.Column("owner_id", UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("task_id", UUID(as_uuid=True), nullable=True),
        sa.Column("notebook_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_table(
        "agent_workspace_runs",
        *_base(),
        sa.Column("owner_id", UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", UUID(as_uuid=True), nullable=True),
        sa.Column("provider_revision", sa.Integer, nullable=True),
        sa.Column("model_id", sa.String(160), nullable=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("autopilot", sa.Boolean, nullable=False),
        sa.Column("checkpoint", JSONB, nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("cancel_requested", sa.Boolean, nullable=False),
        sa.Column("lease_owner", sa.String(100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "agent_workspace_messages",
        *_base(),
        sa.Column("owner_id", UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("refs", JSONB, nullable=False),
    )
    for table in (
        "agent_provider_models",
        "agent_workspace_policies",
        "agent_workspace_threads",
        "agent_workspace_runs",
        "agent_workspace_messages",
    ):
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])
    for table in ("agent_workspace_threads", "agent_workspace_runs"):
        op.create_index(f"ix_{table}_owner_id", table, ["owner_id"])
    for table in ("agent_workspace_runs", "agent_workspace_messages"):
        op.create_index(f"ix_{table}_thread_id", table, ["thread_id"])
    op.create_index("ix_agent_workspace_runs_status", "agent_workspace_runs", ["status"])


def downgrade() -> None:
    for table in (
        "agent_workspace_messages",
        "agent_workspace_runs",
        "agent_workspace_threads",
        "agent_workspace_policies",
        "agent_provider_models",
    ):
        op.drop_table(table)
    op.drop_constraint("uq_inference_providers_scope_id", "inference_providers", type_="unique")
