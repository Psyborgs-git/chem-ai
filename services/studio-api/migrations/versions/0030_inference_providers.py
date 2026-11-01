"""Explicit inference providers and opaque Keychain cleanup intents.

Revision ID: 0030_inference_providers
Revises: 0029_evidence_applicability
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0030_inference_providers"
down_revision = "0029_evidence_applicability"
branch_labels = None
depends_on = None


def _base_columns() -> list[sa.Column]:
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
    op.create_table(
        "inference_credentials",
        *_base_columns(),
        sa.Column("state", sa.String(16), nullable=False),
        sa.UniqueConstraint("workspace_id", "id", name="uq_inference_credentials_scope_id"),
        sa.CheckConstraint("state IN ('pending','active','retired')", name="state"),
    )
    op.create_index(
        "ix_inference_credentials_workspace_id", "inference_credentials", ["workspace_id"]
    )
    op.create_table(
        "inference_providers",
        *_base_columns(),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("api_style", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("supports_tools", sa.Boolean(), nullable=False),
        sa.Column("credential_ref", UUID(as_uuid=True), nullable=True),
        sa.Column("last_test_status", sa.String(24), nullable=False),
        sa.Column("last_test_detail", sa.Text(), nullable=True),
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id", "credential_ref"],
            ["inference_credentials.workspace_id", "inference_credentials.id"],
            name="fk_inference_provider_credential_scope",
        ),
        sa.CheckConstraint("kind IN ('openai','openai_compatible')", name="kind"),
        sa.CheckConstraint("api_style = 'chat_completions'", name="api_style"),
    )
    op.create_index("ix_inference_providers_workspace_id", "inference_providers", ["workspace_id"])


def downgrade() -> None:
    op.drop_table("inference_providers")
    op.drop_table("inference_credentials")
