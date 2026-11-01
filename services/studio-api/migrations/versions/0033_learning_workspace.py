"""Owner-private custom datasets, local models and durable training jobs."""

from alembic import op

revision = "0033_learning_workspace"
down_revision = "0032_agent_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from studio.domain.learning.workspace_runtime.models import (
        LearningDataset,
        LearningJob,
        LearningModel,
    )

    for model in (LearningDataset, LearningModel, LearningJob):
        model.__table__.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    from studio.domain.learning.workspace_runtime.models import (
        LearningDataset,
        LearningJob,
        LearningModel,
    )

    for model in (LearningJob, LearningModel, LearningDataset):
        model.__table__.drop(op.get_bind(), checkfirst=True)
