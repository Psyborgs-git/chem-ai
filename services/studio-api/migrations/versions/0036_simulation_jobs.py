"""Durable private RadonPy/LAMMPS polymer simulation jobs."""

from alembic import op

revision = "0036_simulation_jobs"
down_revision = "0035_learning_preflight"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from studio.domain.simulations.models import SimulationJob

    SimulationJob.__table__.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    from studio.domain.simulations.models import SimulationJob

    SimulationJob.__table__.drop(op.get_bind(), checkfirst=True)
