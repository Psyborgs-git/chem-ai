"""Tool-bound origin enforcement with real private dataset and source persistence."""

from __future__ import annotations

import json
import uuid

import pytest
from chem_studio_policy.capabilities import Grant, capabilities_for_role
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext
from studio.config.settings import Settings
from studio.domain.agent_workspace.tools import execute
from studio.domain.learning.workspace import LearningWorkspaceService
from studio.domain.learning.workspace_runtime.models import LearningDataset, LearningJob
from studio.domain.library.models import LibrarySource
from studio.domain.library.research import Download
from studio.domain.library.service import LibraryService
from studio.errors import DomainError
from studio.persistence.models import Principal, Workspace


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_RESEARCH_DOWNLOADS_ROOT", str(tmp_path / "downloads"))
    engine = create_engine(f"sqlite:///{tmp_path / 'origins.sqlite'}")
    for cls in (Workspace, Principal, LibrarySource, LearningDataset, LearningJob):
        cls.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as db:
        workspace = Workspace(slug="origins", display_name="Dataset origins")
        db.add(workspace)
        db.flush()
        user = Principal(
            workspace_id=workspace.id, kind="user", login="owner", display_name="Owner"
        )
        db.add(user)
        db.flush()
        ctx = ServiceContext(
            session=db,
            workspace_id=workspace.id,
            principal_id=user.id,
            principal_kind="user",
            grants=frozenset(Grant(capability) for capability in capabilities_for_role("owner")),
        )
        settings = Settings(vault_root=tmp_path / "vault")
        yield db, ctx, settings
    engine.dispose()


def payload(**changes):
    return {
        "name": "Agent examples",
        "format": "jsonl",
        "content": json.dumps(
            {"prompt": "Explain this research result", "response": "A generated draft explanation."}
        ),
        "rights": "owned",
        **changes,
    }


def create(env, data):
    db, ctx, settings = env
    return execute(db, ctx, settings, "create_dataset", {"payload": data})


def test_agent_default_is_synthetic_and_cannot_overwrite_scientific_status(env):
    result = create(env, payload(source={"scientificStatus": "experimentally_validated"}))
    assert result["dataKind"] == "synthetic"
    assert result["report"]["scientificStatus"] == "not_validated"
    assert result["source"]["scientificStatus"] == "not_validated"
    assert result["source"]["createdBy"] == "agent"


@pytest.mark.parametrize("kind", ["experimental", "user_authored"])
def test_generated_payload_cannot_claim_measured_or_human_authorship(env, kind):
    with pytest.raises(DomainError, match="cannot be experimental"):
        create(env, payload(dataKind=kind))


def test_manual_experimental_import_is_unchanged(env):
    db, ctx, settings = env
    result = LearningWorkspaceService(db, ctx, settings).import_dataset(
        payload(dataKind="experimental")
    )
    assert result["dataKind"] == "experimental"
    assert result["report"]["scientificStatus"] == "not_validated"


def test_literature_requires_current_owned_source_and_matching_locator(env):
    db, ctx, settings = env
    source = LibraryService(db, ctx, vault_root=settings.vault_root).archive_download(
        Download(
            url="https://example.test/research",
            media_type="text/plain",
            body=b"A published document reports an ethanol descriptor under specified conditions.",
        ),
        title="Research source",
    )
    with pytest.raises(DomainError):
        create(env, payload(dataKind="literature", source={"sourceIds": [source["id"]]}))
    with pytest.raises(DomainError):
        create(
            env,
            payload(
                dataKind="literature",
                source={
                    "sourceRefs": [
                        {
                            "sourceId": source["id"],
                            "locator": {"quote": "A claim the actual source never made."},
                        }
                    ]
                },
            ),
        )
    result = create(
        env,
        payload(
            dataKind="literature",
            source={
                "sourceRefs": [
                    {
                        "sourceId": source["id"],
                        "locator": {
                            "quote": "reports an ethanol descriptor under specified conditions."
                        },
                    }
                ]
            },
        ),
    )
    assert result["dataKind"] == "literature"
    assert result["source"]["sourceRefs"][0]["checksum"] == source["checksum"]
    assert result["report"]["scientificStatus"] == "not_validated"
    with pytest.raises(DomainError):
        create(
            env,
            payload(
                dataKind="literature",
                source={
                    "sourceRefs": [
                        {
                            "sourceId": str(uuid.uuid4()),
                            "locator": {"quote": "reports an ethanol descriptor"},
                        }
                    ]
                },
            ),
        )


def test_computed_requires_owned_completed_engine_result_with_resolvable_path(env):
    db, ctx, _settings = env
    with pytest.raises(DomainError):
        create(env, payload(dataKind="computed", source={"engine": "invented-engine"}))
    job = LearningJob(
        workspace_id=ctx.workspace_id,
        owner_id=ctx.principal_id,
        name="Persisted evaluation",
        kind="evaluate",
        state="completed",
        config={"backend": "chemprop"},
        result={"predictions": [{"value": 1.23}]},
    )
    db.add(job)
    db.flush()
    result = create(
        env,
        payload(
            dataKind="computed",
            source={
                "resultRefs": [{"jobId": str(job.id), "resultPath": ["predictions", 0, "value"]}]
            },
        ),
    )
    assert result["dataKind"] == "computed"
    assert result["source"]["resultRefs"][0]["engine"] == "chemprop"
    assert result["report"]["scientificStatus"] == "not_validated"
    with pytest.raises(DomainError):
        create(
            env,
            payload(
                dataKind="computed",
                source={"resultRefs": [{"jobId": str(job.id), "resultPath": ["invented-value"]}]},
            ),
        )
    job.state = "queued"
    db.flush()
    with pytest.raises(DomainError):
        create(env, payload(dataKind="computed", source={"jobIds": [str(job.id)]}))
