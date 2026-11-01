"""Owner-private public-source campaigns with cumulative resource limits."""

from alembic import op

revision = "0037_research_workflows"
down_revision = "0036_simulation_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from studio.domain.agent_workspace.workflows import ResearchWorkflow

    ResearchWorkflow.__table__.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    from studio.domain.agent_workspace.workflows import ResearchWorkflow

    ResearchWorkflow.__table__.drop(op.get_bind(), checkfirst=True)
