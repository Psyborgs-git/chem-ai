"""CS-0405 integration tests — agent turn plumbing + degraded mode.

AT-0405-1 (plumbing tier): a scripted runtime drives the same runner —
tool_call + tool_result + final assistant message persist, in order,
with real dispatcher output.
AT-0405-3: no model runtime → ``model_unavailable`` — and the manual
workflow (sessions, messages, questions, proposals) stays fully usable.
The live-model half of AT-0405-1 runs in tests/engines/ against the
real llama.cpp container — never simulated.
"""

from __future__ import annotations

import json
import uuid

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session
from workers.inference import LlamaCppRuntime

from studio.application.agent_tools import AgentTurnRunner, ToolDispatcher
from studio.auth.context import ServiceContext, load_context
from studio.domain.tasks.memory import TaskMemoryService
from studio.persistence.models import (
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    SessionMessage,
    Workspace,
)

pytestmark = pytest.mark.integration


class ScriptedRuntime(LlamaCppRuntime):
    """Deterministic stand-in for the *runner plumbing only* — queued
    canned responses. The live-model assertions live in
    tests/engines/test_inference.py; nothing here is claimed as a
    model result."""

    def __init__(self, outputs: list[str]) -> None:
        super().__init__(container="none")
        self._outputs = list(outputs)

    def running(self) -> bool:
        return True

    def generate(self, messages, **kwargs):  # type: ignore[override]
        return {
            "choices": [{"message": {"content": self._outputs.pop(0)}}],
            "usage": {"completion_tokens": 12},
        }


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


def _kinds(session: Session, session_id: uuid.UUID) -> list[str]:
    rows = (
        session.query(SessionMessage)
        .filter_by(session_id=session_id)
        .order_by(SessionMessage.created_at)
        .all()
    )
    return [r.kind for r in rows]


class TestTurnPlumbing:
    def test_tool_turn_persists_observable_messages(
        self, session: Session, agent_ctx: ServiceContext, task: ResearchTask
    ) -> None:
        """AT-0405-1 plumbing: call → result → final, all persisted."""
        mem = TaskMemoryService(session, agent_ctx)
        sess = mem.start_session(task.id)
        runtime = ScriptedRuntime(
            [
                json.dumps(
                    {
                        "tool": "summarize_task_evidence",
                        "arguments": {"task_id": str(task.id)},
                    }
                ),
                json.dumps({"final": "no claims yet — zero candidates"}),
            ]
        )
        runner = AgentTurnRunner(session, agent_ctx, runtime=runtime)
        outcome = runner.run_turn(sess.id, "how much evidence do we have?")
        assert outcome.finished_reason == "final"
        assert outcome.tool_calls == 1
        kinds = _kinds(session, sess.id)
        assert kinds == ["message", "tool_call", "tool_result", "message"]
        result = (
            session.query(SessionMessage).filter_by(session_id=sess.id, kind="tool_result").one()
        )
        data = json.loads(result.content)
        assert data["ok"] is True
        assert data["data"]["claims"] == 0
        final = session.get(SessionMessage, outcome.final_message_id)
        assert final.role == "assistant"
        assert "zero" in final.content

    def test_unstructured_response_kept_verbatim(
        self, session: Session, agent_ctx: ServiceContext, task: ResearchTask
    ) -> None:
        mem = TaskMemoryService(session, agent_ctx)
        sess = mem.start_session(task.id)
        runtime = ScriptedRuntime(["I'm not emitting JSON — keep me as-is."])
        outcome = AgentTurnRunner(session, agent_ctx, runtime=runtime).run_turn(sess.id, "hello")
        assert outcome.finished_reason == "final"
        final = session.get(SessionMessage, outcome.final_message_id)
        assert "not emitting JSON" in final.content
        assert final.refs.get("unstructured") is True


class TestModelUnavailable:
    def test_no_runtime_reports_unavailable_and_manual_works(
        self, session: Session, agent_ctx: ServiceContext, task: ResearchTask
    ) -> None:
        """AT-0405-3: explicit degraded state; manual path intact."""
        mem = TaskMemoryService(session, agent_ctx)
        sess = mem.start_session(task.id)
        runtime = LlamaCppRuntime(container="definitely-not-running-x")
        runner = AgentTurnRunner(session, agent_ctx, runtime=runtime)
        outcome = runner.run_turn(sess.id, "analyze this")
        assert outcome.finished_reason == "model_unavailable"
        assert "no local model" in outcome.detail
        # Manual workflow continues: messages, questions, proposals.
        mem.post_message(sess.id, role="user", content="manual note")
        q = mem.raise_question(task.id, question="which tackifier grade?", blocking=False)
        assert q.status == "open"
        msgs = mem.messages(sess.id)
        assert any(m.content == "manual note" for m in msgs)


class TestDispatcherContract:
    def test_unknown_and_forbidden_tool_names(
        self, session: Session, agent_ctx: ServiceContext
    ) -> None:
        d = ToolDispatcher(session, agent_ctx)
        for verb in ("export_vault", "approve_experiment", "promote_model", "close_task"):
            res = d.call(verb, {})
            assert res["ok"] is False
            assert res["error"]["code"] == "UNKNOWN_TOOL"

    def test_budget_exhaustion(
        self, session: Session, agent_ctx: ServiceContext, task: ResearchTask
    ) -> None:
        d = ToolDispatcher(session, agent_ctx, max_calls=1)
        args = {"task_id": str(task.id)}
        first = d.call("summarize_task_evidence", args)
        assert first["ok"] is True
        res = d.call("summarize_task_evidence", args)
        assert res["error"]["code"] == "BUDGET_EXHAUSTED"

    def test_schema_validation(self, session: Session, agent_ctx: ServiceContext) -> None:
        d = ToolDispatcher(session, agent_ctx)
        res = d.call("search_evidence", {"query": 42})
        assert res["ok"] is False
        assert res["error"]["code"] == "INVALID_INPUT"
