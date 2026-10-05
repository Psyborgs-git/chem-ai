"""CS-0405 engine tests — the real local model (AT-0405-1, live tier).

These exercise the actual llama.cpp container + pinned GGUF — never
simulated. If the runtime is absent the test skips honestly; a green
run here means a real model handshake and real generations.
"""

from __future__ import annotations

import json

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session
from workers.inference import LlamaCppRuntime
from workers.inference.runtime import MODEL_SHA256, TURN_GRAMMAR

from studio.application.agent_tools import AgentTurnRunner
from studio.auth.context import load_context
from studio.domain.tasks.memory import TaskMemoryService
from studio.persistence.models import (
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    SessionMessage,
    Workspace,
)

pytestmark = pytest.mark.engine


@pytest.fixture(scope="module")
def runtime() -> LlamaCppRuntime:
    rt = LlamaCppRuntime()
    if not rt.running():
        if not rt.start() or not rt.wait_ready(240):
            pytest.skip("local model runtime not installed (image/volume absent)")
    return rt


class TestHandshake:
    def test_executed_handshake(self, runtime: LlamaCppRuntime) -> None:
        rep = runtime.handshake()
        assert rep.model_sha256_verified is True
        assert rep.chat_template_ok is True
        assert rep.structured_output_ok is True
        assert rep.available is True
        assert rep.runtime_version
        assert rep.license_id == "gemma-terms-of-use"
        assert rep.context_size and rep.context_size >= 1024

    def test_pinned_sha(self, runtime: LlamaCppRuntime) -> None:
        assert runtime.spec.sha256 == MODEL_SHA256
        assert runtime._verify_hash() is True

    def test_structured_turn_shape(self, runtime: LlamaCppRuntime) -> None:
        """The grammar constrains output to the turn protocol."""
        out = runtime.generate(
            [{"role": "user", "content": "Answer with the final word DONE."}],
            max_tokens=32,
            grammar=TURN_GRAMMAR,
        )
        content = out["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        assert "final" in parsed or "tool" in parsed


# ------------------------------------------------------------------
# AT-0405-1 live tier: a real tool turn against the real model.
# ------------------------------------------------------------------


@pytest.fixture()
def agent_ctx(session: Session):
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    p = Principal(workspace_id=ws.id, kind="agent", login="bot", display_name="bot")
    session.add(p)
    session.flush()
    for cap in sorted(capabilities_for_role("agent")):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=p.id, capability=cap))
    session.flush()
    return load_context(session, ws.id, p.id)


def test_live_tool_turn_persists(session: Session, agent_ctx, runtime: LlamaCppRuntime) -> None:
    """AT-0405-1 (live): the real model calls a real tool; the
    tool_call, tool_result, and final message persist.

    A 2B model is nondeterministic — a turn may stall. That is model
    variance, not a pipeline error, so up to 3 real turns run and the
    system must have completed call->result->final at least once."""
    proj = Project(workspace_id=agent_ctx.workspace_id, slug="p", name="P")
    session.add(proj)
    session.flush()
    task = ResearchTask(
        workspace_id=agent_ctx.workspace_id,
        project_id=proj.id,
        mode="improve",
        title="coating task",
        workflow_state="active",
    )
    session.add(task)
    session.flush()
    mem = TaskMemoryService(session, agent_ctx)
    # The runner decodes greedily (temperature 0), so repeating one
    # prompt would just replay the same answer — rotate phrasings so
    # each attempt is a genuinely different real turn.
    prompts = [
        "Llama a la herramienta summarize_task_evidence con "
        f'task_id "{task.id}" — es obligatorio usar la herramienta — '
        "y despues responde en una frase.",
        'First call the tool summarize_task_evidence with task_id '
        f'"{task.id}" — you must call the tool before answering — '
        "then reply in one sentence.",
        "Use summarize_task_evidence now with "
        f'{{"task_id": "{task.id}"}}; after the tool result, '
        "give a one-line answer.",
    ]
    completed = False
    last_kinds: list[str] = []
    for prompt in prompts:
        sess = mem.start_session(task.id)
        outcome = AgentTurnRunner(session, agent_ctx, runtime=runtime).run_turn(sess.id, prompt)
        kinds = [
            m.kind
            for m in session.query(SessionMessage)
            .filter_by(session_id=sess.id)
            .order_by(SessionMessage.created_at)
        ]
        last_kinds = kinds
        if (
            "tool_call" in kinds
            and "tool_result" in kinds
            and kinds[-1] == "message"
            and outcome.finished_reason == "final"
            and outcome.final_message_id is not None
        ):
            completed = True
            tr = (
                session.query(SessionMessage)
                .filter_by(session_id=sess.id, kind="tool_result")
                .first()
            )
            assert json.loads(tr.content)["ok"] in (True, False)
            break
        mem.end_session(sess.id)
    assert completed, f"3 real turns, none completed call->result->final; last kinds: {last_kinds}"
