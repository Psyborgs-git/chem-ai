"""Sequence column on outbox events for resumable streams (§8, CS-0406).

A monotonic ``seq`` lets SSE clients resume with Last-Event-ID —
dedupe on reconnect without skipping live events.

Revision ID: 0016_outbox_seq
Revises: 0015_run_cache
"""

from alembic import op

revision = "0016_outbox_seq"
down_revision = "0015_run_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # BIGSERIAL backfills existing rows in order and stays unique
    op.execute("ALTER TABLE outbox_events ADD COLUMN seq BIGSERIAL UNIQUE")
    op.execute(
        "CREATE INDEX ix_outbox_events_stream ON outbox_events (workspace_id, aggregate_id, seq)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_outbox_events_stream")
    op.execute("ALTER TABLE outbox_events DROP COLUMN IF EXISTS seq")
