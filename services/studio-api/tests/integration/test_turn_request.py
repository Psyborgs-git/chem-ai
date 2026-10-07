"""PAR-08 turn request/cancel — mutation plumbing + cancel semantics.

The composer drives ``research.turnRequest`` (persist the question, run
one bounded turn through the closed tool catalog, return an honest
outcome) and ``research.turnCancel`` (a durable cancel marker the
running turn observes between iterations). ``model_unavailable`` is a
truthful outcome, never a synthesized reply; a cancelled turn leaves
both the user question and the cancellation record in the session.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session
from starlette.testclient import TestClient
from strawberry import relay

from studio.api.app import create_app
from studio.application.agent_tools import AgentTurnRunner
from studio.auth.context import ServiceContext, load_context
from studio.config.settings import Settings
from studio.domain.tasks.memory import TaskMemoryService
from studio.persistence.models import (
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    SessionMessage,
    Workspace,
)

from .test_agent_turn import ScriptedRuntime

pytestmark = pytest.mark.integration

HEADERS = {"origin": "http://127.0.0.1:8787", "host": "127.0.0.1:8787"}


def _client(db_url: str) -> TestClient:
    return TestClient(create_app(Settings(database_url=db_url)))


def _setup_owner(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/setup",
        json={
            "login": "owner",
            "display_name": "Owner",
            "password": "correct horse battery staple",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text


def _gql(client: TestClient, query: str, variables: dict[str, Any] | None = None) -> Any:
    resp = client.post(
        "/graphql",
        json={"query": query, "variables": variables or {}},
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _gid(type_name: str, row_id: uuid.UUID) -> str:
    return str(relay.GlobalID(type_name=type_name, node_id=str(row_id)))


def _principal(session: Session, ws: Workspace, kind: str, role: str, login: str) -> Principal:
    p = Principal(workspace_id=ws.id, kind=kind, login=login, display_name=login)
    session.add(p)
    session.flush()
    for cap in sorted(capabilities_for_role(role)):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=p.id, capability=cap))
    session.flush()
    return p


@pytest.fixture()
def agent_ctx(session: Session) -> ServiceContext:
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    return load_context(session, ws.id, _principal(session, ws, "agent", "agent", "bot").id)


@pytest.fixture()
def task(session: Session, agent_ctx: ServiceContext) -> ResearchTask:
    proj = Project(workspace_id=agent_ctx.workspace_id, slug="p", name="P")
    session.add(proj)
    session.flush()
    t = ResearchTask(
        workspace_id=agent_ctx.workspace_id,
        project_id=proj.id,
        mode="improve",
        title="task",
        workflow_state="active",
    )
    session.add(t)
    session.flush()
    return t


def _task(session: Session, ws: Workspace) -> ResearchTask:
    proj = Project(workspace_id=ws.id, slug="p", name="P")
    session.add(proj)
    session.flush()
    t = ResearchTask(
        workspace_id=ws.id,
        project_id=proj.id,
        mode="improve",
        title="task",
        workflow_state="active",
    )
    session.add(t)
    session.flush()
    return t


def _session_id(client: TestClient, task_gid: str) -> str:
    out = _gql(
        client,
        "mutation($input: SessionStartInput!) { research { "
        "sessionStart(input: $input) { session { id } errors { code message } } } }",
        {"input": {"taskId": task_gid}},
    )
    assert out["data"]["research"]["sessionStart"]["errors"] == []
    return out["data"]["research"]["sessionStart"]["session"]["id"]


TURN_REQUEST = (
    "mutation($input: TurnRequestInput!) { research { "
    "turnRequest(input: $input) { turnId finishedReason toolCalls detail "
    "finalMessage { id role content } errors { code message } } } }"
)
TURN_CANCEL = (
    "mutation($input: TurnCancelInput!) { research { "
    "turnCancel(input: $input) { recorded errors { code message } } } }"
)


def _messages(session: Session, session_uuid: uuid.UUID) -> list[SessionMessage]:
    return (
        session.query(SessionMessage)
        .filter_by(session_id=session_uuid)
        .order_by(SessionMessage.created_at)
        .all()
    )


class TestTurnRequest:
    def test_no_runtime_reports_unavailable_and_persists_question(
        self, db_url: str, session: Session
    ) -> None:
        """PAR-08: composer send → real mutation → honest unavailable
        outcome; the question itself is durable session evidence."""
        client = _client(db_url)
        _setup_owner(client)
        ws = session.query(Workspace).one()
        task = _task(session, ws)
        session.commit()
        sid = _session_id(client, _gid("Task", task.id))

        turn_id = str(uuid.uuid4())
        out = _gql(
            client,
            TURN_REQUEST,
            {"input": {"sessionId": sid, "content": "which evidence exists?", "turnId": turn_id}},
        )
        result = out["data"]["research"]["turnRequest"]
        assert result["errors"] == []
        assert result["turnId"] == turn_id
        assert result["finishedReason"] == "model_unavailable"
        assert "no local model" in result["detail"]

        s_uuid = uuid.UUID(relay.GlobalID.from_id(sid).node_id)
        msgs = _messages(session, s_uuid)
        assert len(msgs) == 1
        assert msgs[0].role == "user"
        assert msgs[0].content == "which evidence exists?"
        assert msgs[0].refs.get("turn_id") == turn_id
        # no fabricated assistant reply was invented to fill the gap
        assert not any(m.role == "assistant" for m in msgs)

    def test_turn_request_idempotent_replay(self, db_url: str, session: Session) -> None:
        """Same turnId + idempotency key replays the stored outcome —
        the user message is not double-posted."""
        client = _client(db_url)
        _setup_owner(client)
        ws = session.query(Workspace).one()
        task = _task(session, ws)
        session.commit()
        sid = _session_id(client, _gid("Task", task.id))

        turn_id = str(uuid.uuid4())
        inp = {
            "sessionId": sid,
            "content": "q",
            "turnId": turn_id,
            "idempotencyKey": "turn-key-1",
        }
        first = _gql(client, TURN_REQUEST, {"input": inp})["data"]["research"]["turnRequest"]
        again = _gql(client, TURN_REQUEST, {"input": inp})["data"]["research"]["turnRequest"]
        assert first["finishedReason"] == again["finishedReason"] == "model_unavailable"
        s_uuid = uuid.UUID(relay.GlobalID.from_id(sid).node_id)
        assert len(_messages(session, s_uuid)) == 1

    def test_turn_on_ended_session_conflicts(self, db_url: str, session: Session) -> None:
        client = _client(db_url)
        _setup_owner(client)
        ws = session.query(Workspace).one()
        task = _task(session, ws)
        session.commit()
        sid = _session_id(client, _gid("Task", task.id))
        end = _gql(
            client,
            "mutation($input: SessionEndInput!) { research { "
            "sessionEnd(input: $input) { session { status } errors { code } } } }",
            {"input": {"sessionId": sid}},
        )
        assert end["data"]["research"]["sessionEnd"]["errors"] == []

        out = _gql(
            client,
            TURN_REQUEST,
            {"input": {"sessionId": sid, "content": "late", "turnId": str(uuid.uuid4())}},
        )
        result = out["data"]["research"]["turnRequest"]
        assert result["finishedReason"] is None
        assert result["errors"][0]["code"] == "CONFLICT"


class TestTurnCancel:
    def test_cancel_marker_is_durable(self, db_url: str, session: Session) -> None:
        client = _client(db_url)
        _setup_owner(client)
        ws = session.query(Workspace).one()
        task = _task(session, ws)
        session.commit()
        sid = _session_id(client, _gid("Task", task.id))
        turn_id = str(uuid.uuid4())

        out = _gql(
            client,
            TURN_CANCEL,
            {"input": {"sessionId": sid, "turnId": turn_id}},
        )
        result = out["data"]["research"]["turnCancel"]
        assert result["errors"] == []
        assert result["recorded"] is True

        s_uuid = uuid.UUID(relay.GlobalID.from_id(sid).node_id)
        markers = [m for m in _messages(session, s_uuid) if m.refs.get("turn_cancel") == turn_id]
        assert len(markers) == 1
        assert markers[0].role == "user"

    def test_cancel_on_ended_session_conflicts(self, db_url: str, session: Session) -> None:
        client = _client(db_url)
        _setup_owner(client)
        ws = session.query(Workspace).one()
        task = _task(session, ws)
        session.commit()
        sid = _session_id(client, _gid("Task", task.id))
        _gql(
            client,
            "mutation($input: SessionEndInput!) { research { "
            "sessionEnd(input: $input) { session { status } errors { code } } } }",
            {"input": {"sessionId": sid}},
        )
        out = _gql(
            client,
            TURN_CANCEL,
            {"input": {"sessionId": sid, "turnId": str(uuid.uuid4())}},
        )
        assert out["data"]["research"]["turnCancel"]["errors"][0]["code"] == "CONFLICT"


class TestRunnerCancellation:
    def test_cancel_check_ends_turn_between_iterations(
        self, session: Session, agent_ctx: ServiceContext, task: ResearchTask
    ) -> None:
        """A pre-recorded cancel marker is observed at the loop head —
        the turn ends as ``cancelled`` with a durable assistant record."""
        mem = TaskMemoryService(session, agent_ctx)
        sess = mem.start_session(task.id)
        turn_id = str(uuid.uuid4())
        runtime = ScriptedRuntime(['{"final": "never reached"}'])
        runner = AgentTurnRunner(session, agent_ctx, runtime=runtime)
        outcome = runner.run_turn(
            sess.id,
            "question",
            turn_id=turn_id,
            cancel_check=lambda: True,
        )
        assert outcome.finished_reason == "cancelled"
        msgs = _messages(session, sess.id)
        cancelled = [m for m in msgs if m.refs.get("cancelled") is True]
        assert len(cancelled) == 1
        assert cancelled[0].role == "assistant"
        assert cancelled[0].refs.get("turn_id") == turn_id
        # the scripted final answer was never emitted
        assert not any(m.content == "never reached" for m in msgs)

    def test_cancel_after_first_tool_call(
        self, session: Session, agent_ctx: ServiceContext, task: ResearchTask
    ) -> None:
        """Cancel lands mid-turn: the second generate never runs."""
        mem = TaskMemoryService(session, agent_ctx)
        sess = mem.start_session(task.id)
        turn_id = str(uuid.uuid4())
        runtime = ScriptedRuntime(
            [
                '{"tool": "summarize_task_evidence", "arguments": {"task_id": "%s"}}'
                % str(task.id),
                '{"final": "should not be emitted"}',
            ]
        )
        calls = {"n": 0}

        def cancel_check() -> bool:
            calls["n"] += 1
            return calls["n"] > 1  # first iteration proceeds, second sees cancel

        runner = AgentTurnRunner(session, agent_ctx, runtime=runtime)
        outcome = runner.run_turn(
            sess.id, "q", turn_id=turn_id, cancel_check=cancel_check
        )
        assert outcome.finished_reason == "cancelled"
        assert outcome.tool_calls == 1
        kinds = [m.kind for m in _messages(session, sess.id)]
        assert "tool_call" in kinds and "tool_result" in kinds
        assert not any(m.content == "should not be emitted" for m in _messages(session, sess.id))
