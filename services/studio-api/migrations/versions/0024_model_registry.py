"""model registry + serving pointer + session pins (§17.5/§18.4, CS-0802).

``model_releases`` records the full serving lineage (dataset snapshot →
training run → adapter → release), base/tokenizer identities, the
adapter's training-time base binding, derived serving-format conversion
artifacts with own checksums + parity verdicts, and the latest
validation report. ``serving_pointers`` is one row per workspace —
promotion and rollback are single-row atomic moves that never mutate
existing session pins. ``session_model_pins`` freezes each research
session's release at start (AT-0802-2).

Revision ID: 0024_model_registry
Revises: 0023_training_runs
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0024_model_registry"
down_revision: str | None = "0023_training_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATES = "'registered','validated','promoted','superseded','rejected','revoked'"


def upgrade() -> None:
    op.create_table(
        "model_releases",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("snapshot_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("training_run_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("adapter_artifact_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("base_model_id", sa.String(length=120), nullable=False),
        sa.Column("architecture", sa.String(length=80), nullable=False),
        sa.Column("init_seed", sa.BigInteger(), nullable=False),
        sa.Column("base_sha256", sa.String(length=64), nullable=False),
        sa.Column("license_id", sa.String(length=120), nullable=False),
        sa.Column("parameter_count", sa.BigInteger(), nullable=True),
        sa.Column("tokenizer_kind", sa.String(length=80), nullable=False),
        sa.Column("tokenizer_sha256", sa.String(length=64), nullable=False),
        sa.Column("adapter_sha256", sa.String(length=64), nullable=False),
        sa.Column("adapter_method", sa.String(length=40), nullable=False),
        sa.Column("adapter_config", pg.JSONB(), nullable=False),
        sa.Column("adapter_base_sha256", sa.String(length=64), nullable=False),
        sa.Column("adapter_tokenizer_sha256", sa.String(length=64), nullable=False),
        sa.Column("adapter_architecture", sa.String(length=80), nullable=False),
        sa.Column("serving_format", sa.String(length=80), nullable=False),
        sa.Column("conversions", pg.JSONB(), nullable=False),
        sa.Column("validation", pg.JSONB(), nullable=False),
        sa.Column("capability", pg.JSONB(), nullable=False),
        sa.Column("approval_id", pg.UUID(as_uuid=True), nullable=True),
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
            name="fk_model_releases_scope_task",
        ),
        sa.ForeignKeyConstraint(
            ["training_run_id"], ["training_runs.id"], name="fk_model_releases_run"
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["dataset_snapshots.id"], name="fk_model_releases_snapshot"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "created_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_model_releases_scope_creator",
        ),
        sa.CheckConstraint(f"state IN ({_STATES})", name="model_release_state"),
    )
    op.create_index(
        "ix_model_releases_scope",
        "model_releases",
        ["workspace_id", "state", "created_at", "id"],
    )

    op.create_table(
        "serving_pointers",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("release_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("updated_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("workspace_id", name="uq_serving_pointer_scope"),
        sa.ForeignKeyConstraint(
            ["release_id"], ["model_releases.id"], name="fk_serving_pointer_release"
        ),
    )

    op.create_table(
        "session_model_pins",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("release_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("workspace_id", "session_id", name="uq_session_model_pin"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id"],
            ["research_sessions.workspace_id", "research_sessions.id"],
            name="fk_session_pins_scope_session",
        ),
        sa.ForeignKeyConstraint(
            ["release_id"], ["model_releases.id"], name="fk_session_pins_release"
        ),
    )
    op.create_index(
        "ix_session_model_pins_release",
        "session_model_pins",
        ["workspace_id", "release_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_session_model_pins_release", table_name="session_model_pins")
    op.drop_table("session_model_pins")
    op.drop_table("serving_pointers")
    op.drop_index("ix_model_releases_scope", table_name="model_releases")
    op.drop_table("model_releases")
