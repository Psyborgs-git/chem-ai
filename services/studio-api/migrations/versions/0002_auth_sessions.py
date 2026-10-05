"""Authenticated session records (§21.2).

Revision ID: 0002_auth_sessions
Revises: 0001_initial_core
Create Date: 2026-10-05

Opaque session tokens: only the sha256 hash is stored. Sessions are
workspace+principal scoped via composite FK and carry expiry/revocation.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_auth_sessions"
down_revision = "0001_initial_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id", "principal_id"],
            ["principals.workspace_id", "principals.id"],
            name="fk_auth_sessions_scope_principal",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
    )
    op.create_index("ix_auth_sessions_workspace_id", "auth_sessions", ["workspace_id"])
    op.create_index(
        "ix_auth_sessions_principal",
        "auth_sessions",
        ["workspace_id", "principal_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_table("auth_sessions")
