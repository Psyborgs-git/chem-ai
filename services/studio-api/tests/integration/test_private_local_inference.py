from __future__ import annotations

import json
import uuid

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import sessionmaker

from studio.auth.context import load_context
from studio.config.settings import Settings
from studio.domain.agent_workspace.runtime import AgentWorker
from studio.domain.agent_workspace.service import AgentWorkspaceService
from studio.domain.learning.workspace_runtime import dispatcher
from studio.domain.learning.workspace_runtime.models import LearningModel
from studio.persistence.models import Principal, PrincipalCapability, Workspace

pytestmark = pytest.mark.integration


def test_selected_learned_model_structured_answer_completes_and_is_retained(
    session, tmp_path, monkeypatch
):
    workspace = Workspace(slug="local-structured-answer", display_name="Local answer test")
    session.add(workspace)
    session.flush()
    owner = Principal(
        workspace_id=workspace.id,
        kind="user",
        login="local-answer-owner",
        display_name="Local answer owner",
    )
    session.add(owner)
    session.flush()
    for capability in capabilities_for_role("owner"):
        session.add(
            PrincipalCapability(
                workspace_id=workspace.id, principal_id=owner.id, capability=capability
            )
        )
    selected = LearningModel(
        workspace_id=workspace.id,
        owner_id=owner.id,
        name="Selected local LoRA",
        backend="mlx",
        location=str(tmp_path / "adapter"),
        details={"state": "ready", "baseLocation": str(tmp_path / "base")},
    )
    session.add(selected)
    session.flush()
    context = load_context(session, workspace.id, owner.id)
    service = AgentWorkspaceService(session, context)
    thread = service.create_thread({"title": "Synthetic local question"})
    run = service.create_run(
        uuid.UUID(thread["id"]),
        {"message": "What is two plus two?", "localModelId": str(selected.id)},
    )
    session.commit()
    answer = json.dumps({"answer": "4", "citations": []})
    used_models = []

    def preview(model, *_args, **kwargs):
        used_models.append(model.id)
        assert kwargs["tools"]
        assert all(tool["type"] == "function" for tool in kwargs["tools"])
        return {"text": answer}

    monkeypatch.setattr(dispatcher, "run_preview", preview)
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    worker = AgentWorker(factory, Settings(vault_root=tmp_path))
    run_id = uuid.UUID(run["id"])
    try:
        with factory() as db:
            assert worker._claim(db, run_id) is not None
        assert worker._step(run_id) is False
        with factory() as db:
            detail = AgentWorkspaceService(
                db, load_context(db, workspace.id, owner.id)
            ).run_detail(run_id)
        assert used_models == [selected.id]
        assert detail["status"] == "completed"
        assert detail["localModelId"] == str(selected.id)
        assert detail["providerId"] is None
        assert detail["error"] is None
        assert detail["messages"][-1]["content"] == answer
    finally:
        worker.stop()
