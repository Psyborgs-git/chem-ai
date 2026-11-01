"""Upgrade real pre-Responses rows without changing their opaque credentials."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from studio.persistence.models import InferenceCredential, InferenceProvider, Workspace

pytestmark = pytest.mark.integration


def test_upgrade_0033_preserves_provider_credential_and_defaults_child_protocol(
    db_url, monkeypatch
):
    monkeypatch.setenv("STUDIO_DATABASE_URL", db_url)
    config = Config(str(Path(__file__).resolve().parents[2] / "migrations" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", db_url)
    command.downgrade(config, "0033_learning_workspace")
    engine = create_engine(db_url)
    with Session(engine) as db:
        workspace = Workspace(slug="protocol-migration", display_name="Protocol migration")
        db.add(workspace)
        db.flush()
        credential = InferenceCredential(workspace_id=workspace.id, state="active")
        db.add(credential)
        db.flush()
        provider = InferenceProvider(
            workspace_id=workspace.id,
            version=3,
            name="Existing provider",
            kind="openai",
            base_url="https://api.openai.com/v1",
            model="existing-model",
            api_style="chat_completions",
            enabled=True,
            supports_tools=True,
            credential_ref=credential.id,
        )
        db.add(provider)
        db.flush()
        child_id, provider_id, credential_id = uuid.uuid4(), provider.id, credential.id
        db.execute(
            text(

                    "INSERT INTO agent_provider_models "
                    "(id,workspace_id,provider_id,model_id,label,roles,supports_tools,enabled) "
                    "VALUES (:id,:workspace,:provider,'existing-model','Existing model',"
                    "'[\"planner\"]'::jsonb,true,true)"

            ),
            {"id": child_id, "workspace": workspace.id, "provider": provider_id},
        )
        db.commit()
    command.upgrade(config, "0034_inference_api_styles")
    with engine.begin() as connection:
        provider = connection.execute(
            text("SELECT api_style,credential_ref,version FROM inference_providers WHERE id=:id"),
            {"id": provider_id},
        ).one()
        assert tuple(provider) == ("chat_completions", credential_id, 3)
        assert (
            connection.execute(
                text("SELECT api_style FROM agent_provider_models WHERE id=:id"), {"id": child_id}
            ).scalar_one()
            == "inherit"
        )
        connection.execute(
            text("UPDATE inference_providers SET api_style='responses' WHERE id=:id"),
            {"id": provider_id},
        )
        connection.execute(
            text("UPDATE agent_provider_models SET api_style='chat_completions' WHERE id=:id"),
            {"id": child_id},
        )
    # Downgrade must also use finalized check names under Alembic's convention.
    command.downgrade(config, "0033_learning_workspace")
    command.upgrade(config, "0034_inference_api_styles")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT credential_ref FROM inference_providers WHERE id=:id"),
                {"id": provider_id},
            ).scalar_one()
            == credential_id
        )
        assert (
            connection.execute(
                text("SELECT api_style FROM agent_provider_models WHERE id=:id"), {"id": child_id}
            ).scalar_one()
            == "inherit"
        )
    engine.dispose()
