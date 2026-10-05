"""measurements.metric — contract metric attribution for the per-metric
evaluator (§12.3, CS-0503). Nullable: unattributed readings stay honest
and can never satisfy a contract metric.

Revision ID: 0019_measurement_metric
Revises: 0018_lab_measurements
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_measurement_metric"
down_revision: str | None = "0018_lab_measurements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "measurements",
        sa.Column("metric", sa.String(length=300), nullable=True),
    )
    op.create_index(
        "ix_measurements_scope_metric",
        "measurements",
        ["workspace_id", "metric"],
    )


def downgrade() -> None:
    op.drop_index("ix_measurements_scope_metric", table_name="measurements")
    op.drop_column("measurements", "metric")
