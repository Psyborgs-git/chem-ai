"""Real HTTP Responses turns through legacy research and durable sidebar workers."""

from __future__ import annotations

import json
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from studio.application.agent_tools.turn import AgentTurnRunner
from studio.application.inference.runtime import RESPONSES_OUTPUT, OpenAICompatibleRuntime
from studio.auth.context import load_context
from studio.config.settings import Settings
from studio.domain.agent_workspace.models import AgentRun, ProviderModel
from studio.domain.agent_workspace.runtime import AgentWorker
from studio.domain.agent_workspace.service import AgentWorkspaceService
from studio.domain.library.models import Notebook
from studio.domain.tasks.memory import TaskMemoryService
from studio.persistence.models import (
    InferenceProvider,
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    SessionMessage,
    Workspace,
)

pytestmark = pytest.mark.integration


@contextmanager
def fixture_endpoint(name, arguments, *, switch_protocol=False):
    requests, failures = [], []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            requests.append({"path": self.path, "body": body})
            if len(requests) == 1:
                result = {
                    "status": "completed",
                    "output": [
                        {
                            "type": "reasoning",
                            "id": "rs-private",
                            "encrypted_content": "opaque-private-fixture",
                            "summary": [
                                {
                                    "type": "summary_text",
                                    "text": "PRIVATE-REASONING-MUST-NOT-APPEAR",
                                }
                            ],
                        },
                        {
                            "type": "function_call",
                            "id": "fc-original",
                            "call_id": "correlated-call",
                            "name": name,
                            "arguments": json.dumps(arguments),
                        },
                    ],
                    "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
                }
            elif switch_protocol:
                if (
                    self.path != "/v1/chat/completions"
                    or RESPONSES_OUTPUT in json.dumps(body)
                    or "opaque-private-fixture" in json.dumps(body)
                ):
                    failures.append("protocol change replayed opaque state or chose wrong endpoint")
                result = {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "Continued with the new model protocol.",
                            }
                        }
                    ]
                }
            else:
                items = body.get("input", [])
                outputs = [item for item in items if item.get("type") == "function_call_output"]
                opaque = [item for item in items if item.get("type") == "reasoning"]
                if (
                    not outputs
                    or outputs[-1].get("call_id") != "correlated-call"
                    or not opaque
                    or opaque[0].get("encrypted_content") != "opaque-private-fixture"
                ):
                    failures.append("Responses reasoning/function correlation was lost")
                actual = json.loads(outputs[-1]["output"]) if outputs else {}
                if not actual.get("ok"):
                    failures.append("the real app tool did not complete")
                result = {
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "id": "msg-final",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "Completed using the persisted app tool result.",
                                }
                            ],
                        }
                    ],
                    "usage": {"input_tokens": 30, "output_tokens": 10, "total_tokens": 40},
                }
            encoded = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", requests, failures
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def owner(session):
    workspace = Workspace(slug="responses-agent", display_name="Responses test")
    session.add(workspace)
    session.flush()
    principal = Principal(
        workspace_id=workspace.id, kind="user", login="owner", display_name="Owner"
    )
    session.add(principal)
    session.flush()
    session.add_all(
        [
            PrincipalCapability(
                workspace_id=workspace.id, principal_id=principal.id, capability=capability
            )
            for capability in capabilities_for_role("owner")
        ]
    )
    session.flush()
    return load_context(session, workspace.id, principal.id)


def provider(session, ctx, url):
    result = InferenceProvider(
        workspace_id=ctx.workspace_id,
        version=1,
        name="Responses HTTP fixture",
        kind="openai",
        base_url=url,
        model="responses-model",
        api_style="responses",
        enabled=True,
        supports_tools=True,
        credential_ref=None,
    )
    session.add(result)
    session.flush()
    return result


def test_legacy_research_preserves_responses_reasoning_and_real_tool_results(session: Session):
    ctx = owner(session)
    project = Project(workspace_id=ctx.workspace_id, slug="task", name="Task")
    session.add(project)
    session.flush()
    task = ResearchTask(
        workspace_id=ctx.workspace_id,
        project_id=project.id,
        title="Response protocol",
        mode="discover",
        workflow_state="active",
    )
    session.add(task)
    session.flush()
    research = TaskMemoryService(session, ctx).start_session(task.id)
    with fixture_endpoint("summarize_task_evidence", {"task_id": str(task.id)}) as (
        url,
        requests,
        failures,
    ):
        row = provider(session, ctx, url)
        outcome = AgentTurnRunner(session, ctx, runtime=OpenAICompatibleRuntime(row)).run_turn(
            research.id, "Read current task evidence"
        )
        assert outcome.finished_reason == "final"
        assert len(requests) == 2
        assert failures == []
    messages = list(
        session.scalars(select(SessionMessage).where(SessionMessage.session_id == research.id))
    )
    assert len(messages) == 4
    assert "PRIVATE-REASONING" not in json.dumps(
        [{"content": message.content, "refs": message.refs} for message in messages]
    )
    assert "opaque-private-fixture" not in json.dumps([message.content for message in messages])


@pytest.mark.parametrize("switch_protocol", [False, True])
def test_sidebar_checkpoint_preserves_opaque_reasoning_and_discards_it_on_protocol_change(
    session: Session, tmp_path, switch_protocol
):
    ctx = owner(session)
    with fixture_endpoint(
        "create_notebook", {"title": "Responses notebook"}, switch_protocol=switch_protocol
    ) as (url, requests, failures):
        destination = provider(session, ctx, url)
        service = AgentWorkspaceService(session, ctx)
        thread = service.create_thread({"title": "Responses thread"})
        created = service.create_run(
            uuid.UUID(thread["id"]),
            {"message": "Create my private research notebook", "providerId": str(destination.id)},
        )
        session.commit()
        factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
        worker = AgentWorker(factory, Settings(vault_root=tmp_path))
        run_id = uuid.UUID(created["id"])
        with factory() as db:
            assert worker._claim(db, run_id)
        assert worker._step(run_id)
        with factory() as db:
            current_ctx = load_context(db, ctx.workspace_id, ctx.principal_id)
            private_api = AgentWorkspaceService(db, current_ctx).run_detail(run_id)
            assert "opaque-private-fixture" not in json.dumps(private_api)
            assert "PRIVATE-REASONING" not in json.dumps(private_api)
            checkpoint = db.get(AgentRun, run_id).checkpoint
            assert (
                checkpoint["messages"][0][RESPONSES_OUTPUT][0]["encrypted_content"]
                == "opaque-private-fixture"
            )
            assert "PRIVATE-REASONING" not in json.dumps(checkpoint)
        assert worker._step(run_id)
        with factory() as db:
            if switch_protocol:
                model = db.scalar(
                    select(ProviderModel).where(ProviderModel.provider_id == destination.id)
                )
                model.api_style = "chat_completions"
            run = db.get(AgentRun, run_id)
            run.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
        recovered = AgentWorker(factory, Settings(vault_root=tmp_path))
        with factory() as db:
            assert recovered._claim(db, run_id)
        assert recovered._step(run_id) is False
        with factory() as db:
            run = db.get(AgentRun, run_id)
            assert run.status == "completed"
            assert (
                len(list(db.scalars(select(Notebook).where(Notebook.owner_id == ctx.principal_id))))
                == 1
            )
        assert len(requests) == 2
        assert failures == []
        worker.stop()
        recovered.stop()
