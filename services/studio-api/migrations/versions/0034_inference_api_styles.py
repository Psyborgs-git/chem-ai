"""Responses transport and per-model API selection under a shared provider."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034_inference_api_styles"
down_revision = "0033_learning_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_inference_providers_api_style"), "inference_providers", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_inference_providers_api_style"),
        "inference_providers",
        "api_style IN ('chat_completions','responses')",
    )
    op.add_column(
        "agent_provider_models",
        sa.Column("api_style", sa.String(32), nullable=False, server_default="inherit"),
    )
    op.create_check_constraint(
        op.f("ck_agent_provider_models_api_style"),
        "agent_provider_models",
        "api_style IN ('inherit','chat_completions','responses')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_agent_provider_models_api_style"), "agent_provider_models", type_="check"
    )
    op.drop_column("agent_provider_models", "api_style")
    op.execute(
        "UPDATE inference_providers SET api_style='chat_completions' WHERE api_style='responses'"
    )
    op.drop_constraint(
        op.f("ck_inference_providers_api_style"), "inference_providers", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_inference_providers_api_style"),
        "inference_providers",
        "api_style = 'chat_completions'",
    )
