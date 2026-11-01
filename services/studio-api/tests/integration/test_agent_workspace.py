"""Private workspace ownership, disclosure, model routing and durable real tools."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session, sessionmaker

from studio.auth.context import load_context
from studio.config.settings import Settings
from studio.domain.agent_workspace.models import AgentPolicy, AgentRun
from studio.domain.agent_workspace.runtime import AgentWorker
from studio.domain.agent_workspace.service import AgentWorkspaceService
from studio.errors import DomainError
from studio.persistence.models import InferenceProvider, Principal, PrincipalCapability, Workspace

pytestmark = pytest.mark.integration


def context(db: Session, workspace: Workspace, login: str):
    principal = Principal(workspace_id=workspace.id, kind="user", login=login, display_name=login)
    db.add(principal)
    db.flush()
    for capability in capabilities_for_role("owner"):
        db.add(
            PrincipalCapability(
                workspace_id=workspace.id, principal_id=principal.id, capability=capability
            )
        )
    db.flush()
    return load_context(db, workspace.id, principal.id)


@pytest.fixture()
def setup(session: Session):
    workspace = Workspace(slug="agent-workspace", display_name="Agent workspace")
    session.add(workspace)
    session.flush()
    return context(session, workspace, "owner"), context(session, workspace, "other")


def provider(session: Session, ctx, *, remote: bool = False):
    row = InferenceProvider(
        workspace_id=ctx.workspace_id,
        version=1,
        name="configured provider",
        kind="openai_compatible",
        base_url="https://example.com/v1" if remote else "http://127.0.0.1:9999/v1",
        model="original",
        api_style="chat_completions",
        enabled=True,
        supports_tools=True,
        last_test_status="untested",
    )
    session.add(row)
    session.flush()
    return row


def test_private_thread_and_run_are_owner_only(session: Session, setup):
    owner, other = setup
    service = AgentWorkspaceService(session, owner)
    thread = service.create_thread({"title": "Private ethanol research"})
    run = service.create_run(uuid.UUID(thread["id"]), {"message": "Remember ethanol"})
    outsider = AgentWorkspaceService(session, other)
    assert outsider.list_threads() == []
    for operation in (
        outsider.thread_detail,
        outsider.run_detail,
        outsider.cancel,
        outsider.resume,
    ):
        with pytest.raises(DomainError):
            operation(uuid.UUID(run["id"] if operation != outsider.thread_detail else thread["id"]))


def test_model_children_and_role_routing(session: Session, setup):
    owner, _ = setup
    row = provider(session, owner)
    service = AgentWorkspaceService(session, owner)
    assert service.providers()[0]["models"][0]["modelId"] == "original"
    service.save_model(
        row.id, {"modelId": "small-extractor", "roles": ["extractor"], "supportsTools": True}
    )
    service.save_model(row.id, {"modelId": "original", "roles": ["planner"]})
    thread = service.create_thread({})
    run = service.create_run(
        uuid.UUID(thread["id"]),
        {"message": "Extract molecules", "providerId": str(row.id), "role": "extractor"},
    )
    assert run["modelId"] == "small-extractor"
    assert len(service.providers()[0]["models"]) == 2


def test_remote_disclosures_are_multiple_and_revision_bound(session: Session, setup):
    owner, _ = setup
    first = provider(session, owner, remote=True)
    second = provider(session, owner, remote=True)
    service = AgentWorkspaceService(session, owner)
    with pytest.raises(DomainError):
        service.ensure_disclosure(first)

    service.save_policy(
        {
            "remoteDisclosures": {
                str(row.id): {"providerRevision": 1, "allowPrivate": True}
                for row in (first, second)
            }
        }
    )
    service.ensure_disclosure(first)
    service.ensure_disclosure(second)
    first.version = 2
    with pytest.raises(DomainError):
        service.ensure_disclosure(first)


def test_notebook_link_checks_owner_and_ai_access(session: Session, setup, tmp_path):
    from studio.domain.library.models import Notebook
    from studio.domain.library.service import LibraryService

    owner, other = setup
    library = LibraryService(session, owner, vault_root=tmp_path)
    notebook = library.create_notebook("Private notes")
    with pytest.raises(DomainError):
        AgentWorkspaceService(session, other).create_thread({"notebookId": notebook["id"]})
    row = session.get(Notebook, uuid.UUID(notebook["id"]))
    row.ai_enabled = False
    session.flush()
    with pytest.raises(DomainError):
        AgentWorkspaceService(session, owner).create_thread({"notebookId": notebook["id"]})


def test_manifest_does_not_collect_unrelated_workspace_claims(session: Session, setup):
    from studio.domain.projects.service import ProjectService
    from studio.domain.tasks.memory import TaskMemoryService
    from studio.domain.tasks.service import TaskService
    from studio.persistence.models import EvidenceClaim

    owner, _ = setup
    project = ProjectService(session, owner).create(name="Project", slug="scoped")
    task = TaskService(session, owner).create(project_id=project.id, title="Task", mode="discover")
    unrelated = EvidenceClaim(
        workspace_id=owner.workspace_id,
        kind="inferred_suggestion",
        status="accepted",
        subject={"task_id": str(uuid.uuid4())},
        statement={"text": "unrelated source"},
        conditions={"warning": True},
    )
    related = EvidenceClaim(
        workspace_id=owner.workspace_id,
        kind="inferred_suggestion",
        status="accepted",
        subject={"task_id": str(task.id)},
        statement={"text": "relevant source"},
        conditions={},
    )
    session.add_all([unrelated, related])
    session.flush()
    items, warnings = TaskMemoryService(session, owner).collect_items(task)
    assert str(related.id) in {item.ref_id for item in items}
    assert str(unrelated.id) not in {item.ref_id for item in items + warnings}


def test_persistent_research_schedule_queues_once_when_due(session: Session, setup, tmp_path):
    import copy

    from sqlalchemy import select

    owner, _ = setup
    service = AgentWorkspaceService(session, owner)
    thread = service.create_thread({"title": "Continuing research"})
    service.save_policy({"autopilot": {"enabled": True}})
    saved = service.save_automation(
        uuid.UUID(thread["id"]),
        {
            "enabled": True,
            "researchGoal": "Track ethanol solvent evidence",
            "scheduleHours": 24,
        },
    )
    assert saved["nextWakeAt"]
    policy = session.scalar(select(AgentPolicy).where(AgentPolicy.owner_id == owner.principal_id))
    payload = copy.deepcopy(policy.payload)
    payload["schedules"][thread["id"]]["nextWakeAt"] = (
        datetime.now(UTC) - timedelta(seconds=1)
    ).isoformat()
    policy.payload = payload
    session.commit()
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    worker = AgentWorker(factory, Settings(vault_root=tmp_path))
    worker._schedule()
    worker._schedule()
    session.expire_all()
    detail = service.thread_detail(uuid.UUID(thread["id"]))
    assert len(detail["runs"]) == 1
    assert detail["runs"][0]["autopilot"] is True
    assert detail["automation"]["lastRunId"] == detail["runs"][0]["id"]
    service.save_policy({"autopilot": {"enabled": False}})
    assert service.policy()["schedules"][thread["id"]]["researchGoal"]
    worker.stop()


@pytest.mark.parametrize("selection", ["provider", "private_local"])
def test_worker_commits_tool_events_and_continues_from_checkpoint(
    session: Session, setup, tmp_path, monkeypatch, selection
):
    from studio.domain.agent_workspace import runtime as worker_module

    owner, _ = setup
    row = provider(session, owner)
    service = AgentWorkspaceService(session, owner)
    thread = service.create_thread({"title": "Private notes"})
    payload = {"message": "Create a notebook", "providerId": str(row.id)}
    if selection == "private_local":
        from studio.domain.learning.workspace_runtime.models import LearningModel

        local = LearningModel(
            workspace_id=owner.workspace_id,
            owner_id=owner.principal_id,
            name="Private learned model",
            backend="mlx",
            location=str(tmp_path),
            details={"state": "ready"},
        )
        session.add(local)
        session.flush()
        payload = {"message": "Create a notebook", "localModelId": str(local.id)}
    run = service.create_run(uuid.UUID(thread["id"]), payload)
    session.commit()
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "notebook-1",
                                "type": "function",
                                "function": {
                                    "name": "create_notebook",
                                    "arguments": '{"title":"Ethanol research"}',
                                },
                            }
                        ]
                    }
                }
            ]
        },
        {"choices": [{"message": {"content": "Saved your private research notebook."}}]},
    ]

    class Runtime(worker_module.OpenAICompatibleRuntime):
        def generate(self, *_args, **_kwargs):
            return responses.pop(0)

    monkeypatch.setattr(worker_module, "OpenAICompatibleRuntime", Runtime)
    if selection == "private_local":
        from studio.domain.learning.workspace import LearningWorkspaceService

        monkeypatch.setattr(
            LearningWorkspaceService,
            "infer_model",
            lambda _self, *_args, **_kwargs: responses.pop(0),
        )
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    worker = AgentWorker(factory, Settings(vault_root=tmp_path))
    run_id = uuid.UUID(run["id"])
    with factory() as db:
        assert worker._claim(db, run_id) is not None
    assert worker._step(run_id)
    with factory() as db:
        current = db.get(AgentRun, run_id)
        assert current.checkpoint["pendingCalls"][0]["name"] == "create_notebook"
        detail = AgentWorkspaceService(
            db, load_context(db, owner.workspace_id, owner.principal_id)
        ).run_detail(run_id)
        assert len(detail["toolEvents"]) == 1
    assert worker._step(run_id)
    # A fresh executor recovers the persisted checkpoint; no notebook write repeats.
    replacement = AgentWorker(factory, Settings(vault_root=tmp_path))
    replacement.worker_id = worker.worker_id
    assert replacement._step(run_id) is False
    with factory() as db:
        detail = AgentWorkspaceService(
            db, load_context(db, owner.workspace_id, owner.principal_id)
        ).run_detail(run_id)
        assert detail["status"] == "completed"
        assert detail["progress"]["toolCalls"] == 1
        assert len(detail["toolEvents"]) == 2
        assert "Saved your private" in detail["messages"][-1]["content"]
    worker.stop()
    replacement.stop()


def test_revoked_artifact_is_not_replayed_from_a_saved_tool_checkpoint(
    session: Session, setup, tmp_path, monkeypatch
):
    import json

    from studio.domain.agent_workspace import runtime as worker_module
    from studio.persistence.models import Artifact

    owner, _ = setup
    destination = provider(session, owner)
    service = AgentWorkspaceService(session, owner)
    thread = service.create_thread({"title": "Source revocation"})
    created = service.create_run(
        uuid.UUID(thread["id"]),
        {"message": "Recheck current evidence", "providerId": str(destination.id)},
    )
    artifact = Artifact(
        workspace_id=owner.workspace_id,
        storage_key="test/opaque-source",
        original_name="source.txt",
        media_type="text/plain",
        upload_state="committed",
        review_state="accepted",
        rights={"retrieval": "allowed", "export": "allowed"},
        checksum_sha256="0" * 64,
    )
    session.add(artifact)
    session.flush()
    run = session.get(AgentRun, uuid.UUID(created["id"]))
    run.checkpoint = {
        **run.checkpoint,
        "contextEpoch": worker_module._context_epoch(session, run),
        "messages": [{"role": "user", "content": "Old tool result: NEVER-REPLAY-REVOKED-SOURCE"}],
    }
    session.commit()
    artifact.review_state = "revoked"
    session.commit()

    class Runtime(worker_module.OpenAICompatibleRuntime):
        def generate(self, messages, **_kwargs):
            assert "NEVER-REPLAY-REVOKED-SOURCE" not in json.dumps(messages)
            return {"choices": [{"message": {"content": "I rechecked the current sources."}}]}

    monkeypatch.setattr(worker_module, "OpenAICompatibleRuntime", Runtime)
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    worker = AgentWorker(factory, Settings(vault_root=tmp_path))
    with factory() as db:
        assert worker._claim(db, run.id)
    assert worker._step(run.id) is False
    session.expire_all()
    assert service.run_detail(run.id)["status"] == "completed"
    worker.stop()


def test_local_research_cannot_send_restricted_source_paraphrase_to_a_helper(
    session: Session, setup, tmp_path, monkeypatch
):
    from studio.domain.agent_workspace import runtime as worker_module
    from studio.persistence.models import Artifact

    owner, _ = setup
    provider(session, owner)
    service = AgentWorkspaceService(session, owner)
    service.providers()  # Materialize default role assignments.
    thread = service.create_thread({})
    created = service.create_run(
        uuid.UUID(thread["id"]), {"message": "Review the evidence locally"}
    )
    run = session.get(AgentRun, uuid.UUID(created["id"]))
    artifact = Artifact(
        workspace_id=owner.workspace_id,
        storage_key="test/no-export",
        original_name="private.txt",
        media_type="text/plain",
        upload_state="committed",
        review_state="accepted",
        rights={"retrieval": "allowed", "export": "denied"},
    )
    session.add(artifact)
    session.flush()

    def must_not_send(*_args, **_kwargs):
        pytest.fail("restricted derived content reached an HTTP helper")

    monkeypatch.setattr(worker_module.OpenAICompatibleRuntime, "generate", must_not_send)
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    worker = AgentWorker(factory, Settings(vault_root=tmp_path))
    with pytest.raises(DomainError):
        worker._consult(
            session,
            owner,
            run,
            {"role": "reviewer", "question": "A paraphrase of private source data"},
            {"sourceRefs": [{"kind": "artifact", "id": str(artifact.id)}]},
        )
    worker.stop()
