"""Agent execution through a deterministic, loopback-only HTTP provider.

The provider is a scripted protocol fixture, never a scientific or model
quality result. HTTP generation, the real runner, dispatcher, domain
services, and PostgreSQL records are exercised together. No request can
reach a paid provider: every runtime below uses this ephemeral loopback
server and the production generate implementation.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session
from workers.inference import LlamaCppRuntime, TurnBudget

from studio.application.agent_tools import AgentTurnRunner, ToolDispatcher
from studio.auth.context import ServiceContext, load_context
from studio.domain.candidates.service import CandidateService
from studio.domain.tasks.memory import TaskMemoryService
from studio.persistence.models import (
    Approval,
    Artifact,
    CandidatePatch,
    CandidateRevision,
    EvidenceClaim,
    Measurement,
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    RetrievalManifest,
    Run,
    SessionMessage,
    SourceChunk,
    Workspace,
)

pytestmark = pytest.mark.integration

Response = dict[str, Any] | tuple[int, dict[str, Any]] | Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class MockProvider:
    responses: list[Response]
    requests: list[dict[str, Any]] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    base_url: str = ""


@contextmanager
def mock_provider(responses: list[Response]) -> Iterator[MockProvider]:
    """Serve only the local fixture; exhausted/unexpected requests fail closed."""
    fixture = MockProvider(list(responses))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: Any) -> None:
            pass

        def do_GET(self) -> None:
            fixture.requests.append(
                {
                    "path": self.path,
                    "method": "GET",
                    "body": None,
                    "authorization": self.headers.get("authorization"),
                }
            )
            if self.path in {"/v1/models", "/models"}:
                self._reply(200, {"data": [{"id": "fixture-model", "object": "model"}]})
            elif self.path == "/health":
                self._reply(200, {"status": "ok"})
            else:
                self._reply(404, {"error": {"message": "unknown fixture path"}})

        def do_POST(self) -> None:
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))))
                fixture.requests.append(
                    {
                        "path": self.path,
                        "method": "POST",
                        "body": body,
                        "authorization": self.headers.get("authorization"),
                    }
                )
                if self.path not in {"/v1/chat/completions", "/chat/completions"}:
                    raise AssertionError(f"unexpected fixture path: {self.path}")
                if not fixture.responses:
                    raise AssertionError("provider fixture responses exhausted")
                response = fixture.responses.pop(0)
                if callable(response):
                    response = response(body)
                status, payload = response if isinstance(response, tuple) else (200, response)
                self._reply(status, payload)
            except Exception as exc:
                fixture.failures.append(str(exc))
                self._reply(500, {"error": {"message": "provider fixture rejected request"}})

        def _reply(self, status: int, payload: dict[str, Any]) -> None:
            encoded = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    fixture.base_url = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield fixture
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()
        assert fixture.failures == [], fixture.failures


class HttpFixtureRuntime(LlamaCppRuntime):
    """Only the Docker availability check is replaced; HTTP transport is real."""

    def __init__(self, provider: MockProvider) -> None:
        super().__init__(container="test-fixture-never-docker")
        self.base_url = provider.base_url

    def running(self) -> bool:
        return True


def completion(content: str) -> dict[str, Any]:
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"completion_tokens": 12, "prompt_tokens": 24, "total_tokens": 36},
    }


def tool(name: str, arguments: Any) -> dict[str, Any]:
    return completion(json.dumps({"tool": name, "arguments": arguments}))


def final(text: str) -> dict[str, Any]:
    return completion(json.dumps({"final": text}))


def last_result(body: dict[str, Any]) -> dict[str, Any]:
    """Read the runner's data envelope, not any scripted expected result."""
    last = body["messages"][-1]
    data = json.loads(last["content"])
    return data if last["role"] == "tool" else data["tool_result"]


@pytest.fixture()
def scenario(session: Session) -> tuple[ServiceContext, ResearchTask]:
    ws = Workspace(slug="http-agent-fixture", display_name="Synthetic agent HTTP test")
    session.add(ws)
    session.flush()
    principal = Principal(
        workspace_id=ws.id, kind="agent", login="fixture-agent", display_name="Fixture"
    )
    session.add(principal)
    session.flush()
    for capability in sorted(capabilities_for_role("agent")):
        session.add(
            PrincipalCapability(
                workspace_id=ws.id,
                principal_id=principal.id,
                capability=capability,
            )
        )
    project = Project(workspace_id=ws.id, slug="http-fixture", name="Synthetic HTTP workflow")
    session.add(project)
    session.flush()
    task = ResearchTask(
        workspace_id=ws.id,
        project_id=project.id,
        title="Synthetic protocol validation",
        mode="discover",
        workflow_state="active",
        target_kind="formulation",
    )
    session.add(task)
    session.flush()
    return load_context(session, ws.id, principal.id), task


def messages(session: Session, session_id: uuid.UUID) -> list[SessionMessage]:
    # The database clock is transaction-stable. Outcome/tool_messages supply
    # causal order; use message IDs for lookup rather than inventing ordering
    # from equal created_at timestamps.
    return session.query(SessionMessage).filter_by(session_id=session_id).all()


def indexed_source(session: Session, ctx: ServiceContext, text: str) -> SourceChunk:
    artifact = Artifact(
        workspace_id=ctx.workspace_id,
        storage_key=f"fixture/{uuid.uuid4().hex}",
        original_name="Synthetic protocol source.txt",
        media_type="text/plain",
        upload_state="committed",
        review_state="accepted",
        rights={"retrieval": "allowed"},
    )
    session.add(artifact)
    session.flush()
    chunk = SourceChunk(
        workspace_id=ctx.workspace_id,
        artifact_id=artifact.id,
        chunk_index=0,
        locator={"page": 7, "section": "Synthetic protocol fixture"},
        original_text=text,
        normalized_text=text,
        extraction_method="fixture-explicit",
        chunking_version="fixture-v1",
        rights={"retrieval": "allowed"},
        status="active",
    )
    session.add(chunk)
    session.flush()
    return chunk


def test_http_chain_repeats_a_tool_with_new_inputs_and_preserves_proposal_provenance(
    session: Session,
    scenario: tuple[ServiceContext, ResearchTask],
) -> None:
    ctx, task = scenario
    first = indexed_source(
        session, ctx, "Synthetic alpha protocol observation; no laboratory claim."
    )
    second = indexed_source(
        session, ctx, "Synthetic beta protocol observation; no laboratory claim."
    )
    candidate = CandidateService(session, ctx).create_candidate(
        task_id=task.id,
        entity_kind="formulation",
        hypothesis="Unvalidated synthetic proposal",
    )
    original_hash = candidate.content_hash
    research = TaskMemoryService(session, ctx).start_session(task.id)

    def after_alpha(body: dict[str, Any]) -> dict[str, Any]:
        result = last_result(body)
        assert result["ok"] is True and result["untrusted"] is True
        hit = result["data"]["results"][0]
        assert hit["chunk_id"] == str(first.id)
        assert hit["artifact_id"] == str(first.artifact_id)
        assert hit["locator"]["page"] == 7
        return tool("search_evidence", {"query": "beta"})

    def after_beta(body: dict[str, Any]) -> dict[str, Any]:
        result = last_result(body)
        assert result["data"]["results"][0]["chunk_id"] == str(second.id)
        return tool(
            "propose_candidate_patch",
            {
                "candidate_id": str(candidate.id),
                "patch": {"hypothesis": "Explicitly unvalidated draft"},
                "reason": "Synthetic protocol test; human review remains required",
            },
        )

    def after_proposal(body: dict[str, Any]) -> dict[str, Any]:
        result = last_result(body)
        assert result["ok"] is True
        assert result["data"]["status"] == "proposed"
        assert uuid.UUID(result["data"]["patch_id"])
        return final(
            "A draft patch was proposed from two synthetic sources; it is not a lab result."
        )

    with mock_provider(
        [tool("search_evidence", {"query": "alpha"}), after_alpha, after_beta, after_proposal]
    ) as provider:
        outcome = AgentTurnRunner(session, ctx, runtime=HttpFixtureRuntime(provider)).run_turn(
            research.id,
            "Compare alpha and beta, then propose a draft patch.",
        )
        assert outcome.finished_reason == "final"
        assert outcome.tool_calls == 3
        assert len(provider.requests) == 4
        assert provider.responses == []

    persisted = [session.get(SessionMessage, row_id) for row_id in outcome.tool_messages]
    assert [message.kind for message in persisted] == ["tool_call", "tool_result"] * 3
    result_rows = [
        json.loads(message.content) for message in persisted if message.kind == "tool_result"
    ]
    assert all(result["ok"] is True for result in result_rows)
    for result, source in zip(result_rows[:2], [first, second], strict=True):
        manifest = session.get(RetrievalManifest, uuid.UUID(result["data"]["manifest_id"]))
        assert manifest.chunk_ids == [str(source.id)]
        assert manifest.principal_id == ctx.principal_id
    session.refresh(candidate)
    assert candidate.status == "draft" and candidate.content_hash == original_hash
    assert session.query(CandidateRevision).count() == 1
    assert session.query(CandidatePatch).one().status == "proposed"
    assert session.query(Approval).count() == 0
    assert session.query(EvidenceClaim).count() == 0
    assert session.query(Measurement).count() == 0


@pytest.mark.parametrize("protocol", ["legacy", "native"])
@pytest.mark.parametrize(
    ("name", "arguments", "code"),
    [
        ("export_vault", {"all": True}, "UNKNOWN_TOOL"),
        ("read_candidate_revision", {"candidate_revision_id": "not-a-uuid"}, "INVALID_INPUT"),
        ("search_evidence", {"query": 7}, "INVALID_INPUT"),
        ("search_evidence", {"query": "alpha", "approve": True}, "INVALID_INPUT"),
        ("search_evidence", ["alpha"], "INVALID_INPUT"),
    ],
)
def test_http_invalid_or_privileged_tool_calls_produce_failure_records(
    session: Session,
    scenario: tuple[ServiceContext, ResearchTask],
    name: str,
    arguments: Any,
    code: str,
    protocol: str,
) -> None:
    ctx, task = scenario
    research = TaskMemoryService(session, ctx).start_session(task.id)

    def decline_after_error(body: dict[str, Any]) -> dict[str, Any]:
        result = last_result(body)
        assert result["ok"] is False and result["error"]["code"] == code
        assert "data" not in result
        text = "The requested tool failed or was refused. No result was produced."
        return completion(text) if protocol == "native" else final(text)

    initial = (
        native_tool(name, arguments, call_id="invalid_call")
        if protocol == "native"
        else tool(name, arguments)
    )
    with mock_provider([initial, decline_after_error]) as provider:
        runtime = (
            configured_runtime(provider, ctx.workspace_id)[0]
            if protocol == "native"
            else HttpFixtureRuntime(provider)
        )
        outcome = AgentTurnRunner(session, ctx, runtime=runtime).run_turn(
            research.id,
            "Synthetic invalid-call test",
        )
        assert outcome.finished_reason == "final"
        assert len(provider.requests) == 2
    results = [m for m in messages(session, research.id) if m.kind == "tool_result"]
    assert len(results) == 1
    assert json.loads(results[0].content)["error"]["code"] == code
    assert session.query(Run).count() == 0
    assert session.query(Approval).count() == 0
    assert session.query(CandidatePatch).count() == 0


@pytest.mark.parametrize("content", ["null", "[]", "42"])
def test_http_non_object_model_output_fails_without_fabricating_an_answer(
    session: Session,
    scenario: tuple[ServiceContext, ResearchTask],
    content: str,
) -> None:
    ctx, task = scenario
    research = TaskMemoryService(session, ctx).start_session(task.id)
    with mock_provider([completion(content)]) as provider:
        outcome = AgentTurnRunner(session, ctx, runtime=HttpFixtureRuntime(provider)).run_turn(
            research.id,
            "Synthetic malformed response test",
        )
        assert outcome.finished_reason == "error"
        assert outcome.final_message_id is None
        assert outcome.detail
    rows = messages(session, research.id)
    assert any(row.role == "user" for row in rows)
    assert not any(row.role == "assistant" and not row.refs.get("error") for row in rows)


def test_http_failure_keeps_the_question_and_never_invents_a_final_result(
    session: Session,
    scenario: tuple[ServiceContext, ResearchTask],
) -> None:
    ctx, task = scenario
    research = TaskMemoryService(session, ctx).start_session(task.id)
    with mock_provider([(503, {"error": {"message": "fixture provider unavailable"}})]) as provider:
        outcome = AgentTurnRunner(session, ctx, runtime=HttpFixtureRuntime(provider)).run_turn(
            research.id,
            "Preserve this question despite provider failure.",
        )
        assert outcome.finished_reason == "error"
        assert outcome.final_message_id is None
    rows = messages(session, research.id)
    questions = [row for row in rows if row.role == "user"]
    assert len(questions) == 1 and "Preserve this question" in questions[0].content
    assert not any(row.role == "assistant" and not row.refs.get("error") for row in rows)
    assert session.query(Run).count() == 0


def test_request_calculation_records_a_request_without_claiming_execution_success(
    session: Session,
    scenario: tuple[ServiceContext, ResearchTask],
) -> None:
    ctx, task = scenario
    research = TaskMemoryService(session, ctx).start_session(task.id)

    def after_request(body: dict[str, Any]) -> dict[str, Any]:
        result = last_result(body)
        assert result["ok"] is True
        assert result["data"]["status"] == "requested"
        assert uuid.UUID(result["data"]["run_id"])
        return final("The run is requested; it has not executed and no calculated result exists.")

    with mock_provider(
        [
            tool(
                "request_calculation",
                {
                    "kind": "simulation",
                    "task_id": str(task.id),
                    "request": {"operation": "synthetic protocol-only request"},
                },
            ),
            after_request,
        ]
    ) as provider:
        outcome = AgentTurnRunner(session, ctx, runtime=HttpFixtureRuntime(provider)).run_turn(
            research.id,
            "Create an explicit synthetic request, and report its actual status.",
        )
        assert outcome.finished_reason == "final"
    run = session.query(Run).one()
    assert run.status == "requested" and run.attempt_count == 0
    assert run.result_summary is None
    assert session.query(Measurement).count() == 0


def test_workspace_and_task_mismatches_are_tool_failures(
    session: Session,
    scenario: tuple[ServiceContext, ResearchTask],
) -> None:
    ctx, task = scenario
    other_workspace = Workspace(slug="other-fixture", display_name="Other")
    session.add(other_workspace)
    session.flush()
    foreign_project = Project(workspace_id=other_workspace.id, slug="foreign", name="Foreign")
    session.add(foreign_project)
    session.flush()
    foreign_task = ResearchTask(
        workspace_id=other_workspace.id,
        project_id=foreign_project.id,
        title="Private foreign task",
        mode="discover",
        workflow_state="active",
    )
    sibling_task = ResearchTask(
        workspace_id=ctx.workspace_id,
        project_id=task.project_id,
        title="Different task",
        mode="discover",
        workflow_state="active",
    )
    session.add_all([foreign_task, sibling_task])
    session.flush()
    foreign_candidate = CandidateRevision(
        workspace_id=other_workspace.id,
        task_id=foreign_task.id,
        revision=1,
        entity_kind="molecule",
        hypothesis="Do not disclose",
        payload={},
        content_hash="f" * 64,
    )
    local_candidate = CandidateService(session, ctx).create_candidate(
        task_id=task.id, entity_kind="molecule", hypothesis="Local fixture candidate"
    )
    session.add(foreign_candidate)
    session.flush()
    research = TaskMemoryService(session, ctx).start_session(task.id)

    def after_foreign_refusal(body: dict[str, Any]) -> dict[str, Any]:
        result = last_result(body)
        assert result["ok"] is False and result["error"]["code"] == "NOT_FOUND"
        assert "Do not disclose" not in json.dumps(body)
        return tool(
            "validate_formulation",
            {"task_id": str(sibling_task.id), "candidate_revision_id": str(local_candidate.id)},
        )

    def after_task_refusal(body: dict[str, Any]) -> dict[str, Any]:
        result = last_result(body)
        assert result["ok"] is False and result["error"]["code"] == "NOT_FOUND"
        return final(
            "Both inaccessible or mismatched references were refused; no validation succeeded."
        )

    with mock_provider(
        [
            tool("read_candidate_revision", {"candidate_revision_id": str(foreign_candidate.id)}),
            after_foreign_refusal,
            after_task_refusal,
        ]
    ) as provider:
        outcome = AgentTurnRunner(session, ctx, runtime=HttpFixtureRuntime(provider)).run_turn(
            research.id,
            "Synthetic scope-boundary test",
        )
        assert outcome.finished_reason == "final" and outcome.tool_calls == 2
    assert session.query(Run).count() == 0


def fixture_credential() -> str:
    return "fixture-only+not/a-real=key"


class MemorySecretStore:
    """The test never reads or writes a person's login Keychain."""

    def __init__(self) -> None:
        self.values: dict[tuple[uuid.UUID, uuid.UUID], str] = {}

    def put(self, workspace_id: uuid.UUID, reference: uuid.UUID, secret: str) -> None:
        self.values[workspace_id, reference] = secret

    def get(self, workspace_id: uuid.UUID, reference: uuid.UUID) -> str:
        return self.values[workspace_id, reference]

    def delete(self, workspace_id: uuid.UUID, reference: uuid.UUID) -> None:
        self.values.pop((workspace_id, reference), None)


def configured_runtime(
    provider: MockProvider, workspace_id: uuid.UUID, *, kind: str = "openai_compatible"
):
    from studio.application.inference.runtime import OpenAICompatibleRuntime
    from studio.persistence.models import InferenceProvider

    store = MemorySecretStore()
    config = InferenceProvider(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        name="Synthetic loopback protocol provider",
        kind=kind,
        base_url=f"{provider.base_url}/v1",
        model="fixture-model",
        api_style="chat_completions",
        enabled=True,
        supports_tools=True,
        credential_ref=uuid.uuid4(),
    )
    store.put(workspace_id, config.credential_ref, fixture_credential())
    return OpenAICompatibleRuntime(config, store), config, store


def native_tool(name: str, arguments: Any, *, call_id: str) -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(arguments),
                            },
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 12, "total_tokens": 62},
    }


@pytest.mark.parametrize("kind", ["openai", "openai_compatible"])
def test_configured_adapter_sends_model_tools_and_auth_without_serializing_the_key(
    kind: str,
) -> None:
    catalog = [
        {
            "name": "read_fixture",
            "description": "Read explicit test data",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        }
    ]
    with mock_provider([completion("Synthetic provider protocol response")]) as provider:
        runtime, config, store = configured_runtime(provider, uuid.uuid4(), kind=kind)
        response = runtime.generate(
            [{"role": "user", "content": "Synthetic protocol request"}],
            max_tokens=27,
            tools=catalog,
            timeout=2,
        )
        assert (
            response["choices"][0]["message"]["content"] == "Synthetic provider protocol response"
        )
        request = provider.requests[0]
        body = request["body"]
        assert request["path"] == "/v1/chat/completions"
        assert (
            request["authorization"]
            == f"Bearer {store.get(config.workspace_id, config.credential_ref)}"
        )
        assert body["model"] == "fixture-model"
        assert body["stream"] is False
        if kind == "openai":
            assert body["store"] is False and body["max_completion_tokens"] == 27
            assert "max_tokens" not in body
        else:
            assert body["max_tokens"] == 27
            assert "max_completion_tokens" not in body
        assert body["tools"][0]["function"]["parameters"] == catalog[0]["input_schema"]
        assert fixture_credential() not in json.dumps(body)
        assert "grammar" not in body


def test_native_tools_discover_context_then_read_and_validate_actual_candidates(
    session: Session,
    scenario: tuple[ServiceContext, ResearchTask],
) -> None:
    ctx, task = scenario
    service = CandidateService(session, ctx)
    first = service.create_candidate(
        task_id=task.id, entity_kind="molecule", hypothesis="Synthetic first"
    )
    second = service.create_candidate(
        task_id=task.id, entity_kind="molecule", hypothesis="Synthetic second"
    )
    research = TaskMemoryService(session, ctx).start_session(task.id)
    discovered: dict[str, str] = {}

    def discover_task(body: dict[str, Any]) -> dict[str, Any]:
        system = " ".join(
            message["content"] for message in body["messages"] if message["role"] == "system"
        )
        match = re.search(r'(?:Task ID|task_id)["\s:=]+([0-9a-fA-F-]{36})', system)
        assert match is not None, "Current task UUID must be present in the scoped context"
        discovered["task_id"] = str(uuid.UUID(match.group(1)))
        assert discovered["task_id"] == str(task.id)
        return native_tool(
            "summarize_task_evidence", {"task_id": discovered["task_id"]}, call_id="discover"
        )

    def correlated_result(body: dict[str, Any], call_id: str) -> dict[str, Any]:
        assert body["messages"][-1]["role"] == "tool"
        assert body["messages"][-1]["tool_call_id"] == call_id
        assert body["messages"][-2]["role"] == "assistant"
        assert body["messages"][-2]["tool_calls"][0]["id"] == call_id
        result = json.loads(body["messages"][-1]["content"])
        assert result["ok"] is True and result["untrusted"] is True
        return result["data"]

    def after_discovery(body: dict[str, Any]) -> dict[str, Any]:
        data = correlated_result(body, "discover")
        assert data["candidates_total"] == 2 and data["candidates_truncated"] is False
        records = data["candidates"]
        assert [record["id"] for record in records] == [str(first.id), str(second.id)]
        discovered["first"] = records[0]["id"]
        discovered["second"] = records[1]["id"]
        return native_tool(
            "read_candidate_revision",
            {"candidate_revision_id": discovered["first"]},
            call_id="read_first",
        )

    def after_first(body: dict[str, Any]) -> dict[str, Any]:
        data = correlated_result(body, "read_first")
        assert data["id"] == discovered["first"] and data["hypothesis"] == "Synthetic first"
        return native_tool(
            "read_candidate_revision",
            {"candidate_revision_id": discovered["second"]},
            call_id="read_second",
        )

    def after_second(body: dict[str, Any]) -> dict[str, Any]:
        data = correlated_result(body, "read_second")
        assert data["id"] == discovered["second"] and data["hypothesis"] == "Synthetic second"
        return native_tool(
            "validate_formulation",
            {"task_id": discovered["task_id"], "candidate_revision_id": discovered["first"]},
            call_id="verify",
        )

    def after_verification(body: dict[str, Any]) -> dict[str, Any]:
        data = correlated_result(body, "verify")
        assert data["candidateRevisionId"] == discovered["first"]
        assert data["closure"]["assessable"] is False
        assert data["closure"]["supportedSuccessEligible"] is False
        return completion(
            "Both synthetic candidates remain draft proposals; no laboratory result is validated."
        )

    with mock_provider(
        [discover_task, after_discovery, after_first, after_second, after_verification]
    ) as provider:
        runtime, config, _store = configured_runtime(provider, ctx.workspace_id)
        # Five generations carry the expanded docs/tool catalog each time.
        # This fixture tests protocol sequencing; budget enforcement has dedicated cases below.
        outcome = AgentTurnRunner(
            session, ctx, runtime=runtime, budget=TurnBudget(max_total_tokens=16_384)
        ).run_turn(
            research.id,
            "Inspect the current task and its candidates, then check what can be validated.",
        )
        assert outcome.finished_reason == "final" and outcome.tool_calls == 4
        assert len(provider.requests) == 5
        assert {entry["function"]["name"] for entry in provider.requests[0]["body"]["tools"]} >= {
            "summarize_task_evidence",
            "read_candidate_revision",
            "validate_formulation",
        }
        assert not any(
            entry["function"]["name"].startswith("approve")
            for entry in provider.requests[0]["body"]["tools"]
        )
    persisted = [session.get(SessionMessage, identifier) for identifier in outcome.tool_messages]
    assert [entry.kind for entry in persisted] == ["tool_call", "tool_result"] * 4
    assert session.query(Approval).count() == 0
    assert session.query(EvidenceClaim).count() == 0
    assert session.query(Measurement).count() == 0
    final_message = session.get(SessionMessage, outcome.final_message_id)
    assert "remain draft" in final_message.content
    assert final_message.refs["provider_id"] == str(config.id)


def test_configured_provider_credential_echo_is_redacted_before_tools_or_session_storage(
    session: Session,
    scenario: tuple[ServiceContext, ResearchTask],
) -> None:
    import base64
    from urllib.parse import quote

    ctx, task = scenario
    research = TaskMemoryService(session, ctx).start_session(task.id)
    echoed = fixture_credential()
    encodings = [echoed, quote(echoed, safe=""), base64.b64encode(echoed.encode()).decode()]
    text = "Synthetic echo: " + " ".join(encodings)
    with mock_provider([completion(text)]) as provider:
        runtime, _config, _store = configured_runtime(provider, ctx.workspace_id)
        outcome = AgentTurnRunner(session, ctx, runtime=runtime).run_turn(research.id, "Echo test")
        assert outcome.finished_reason == "final"
    final_message = session.get(SessionMessage, outcome.final_message_id)
    assert "[REDACTED]" in final_message.content
    assert not any(value in final_message.content for value in encodings)
    assert not any(value in json.dumps(final_message.refs) for value in encodings)


def test_configured_provider_error_body_never_becomes_a_reply_or_public_diagnostic(
    session: Session,
    scenario: tuple[ServiceContext, ResearchTask],
) -> None:
    ctx, task = scenario
    research = TaskMemoryService(session, ctx).start_session(task.id)
    echoed = fixture_credential()
    with mock_provider([(401, {"error": {"message": f"Private echo {echoed}"}})]) as provider:
        runtime, _config, _store = configured_runtime(provider, ctx.workspace_id)
        outcome = AgentTurnRunner(session, ctx, runtime=runtime).run_turn(
            research.id, "Failure test"
        )
        assert outcome.finished_reason == "error" and outcome.final_message_id is None
        assert "401" in outcome.detail
        assert echoed not in outcome.detail and "Private echo" not in outcome.detail
    assert not any(
        row.role == "assistant" and not row.refs.get("error")
        for row in messages(session, research.id)
    )


def test_candidate_discovery_is_bounded_explicit_and_limited_to_the_requested_task(
    session: Session,
    scenario: tuple[ServiceContext, ResearchTask],
) -> None:
    ctx, task = scenario
    service = CandidateService(session, ctx)
    candidates = [
        service.create_candidate(
            task_id=task.id,
            entity_kind="molecule",
            hypothesis=("A" * 140 if index == 0 else f"Fixture {index}"),
        )
        for index in range(12)
    ]
    other_task = ResearchTask(
        workspace_id=ctx.workspace_id,
        project_id=task.project_id,
        title="Unrelated task",
        mode="discover",
        workflow_state="active",
    )
    session.add(other_task)
    session.flush()
    unrelated = service.create_candidate(
        task_id=other_task.id, entity_kind="molecule", hypothesis="Unrelated private fixture"
    )
    result = ToolDispatcher(session, ctx).call("summarize_task_evidence", {"task_id": str(task.id)})
    assert result["ok"] is True
    data = result["data"]
    assert data["candidate_revisions"] == data["candidates_total"] == 12
    assert data["candidates_truncated"] is True
    assert len(data["candidates"]) == 10
    assert [candidate["id"] for candidate in data["candidates"]] == [
        str(c.id) for c in candidates[:10]
    ]
    assert data["candidates"][0]["hypothesis"] == "A" * 100
    assert data["candidates"][0]["hypothesis_truncated"] is True
    assert all(candidate["hypothesis_truncated"] is False for candidate in data["candidates"][1:])
    assert str(unrelated.id) not in json.dumps(data)
    missing = ToolDispatcher(session, ctx).call(
        "summarize_task_evidence", {"task_id": str(uuid.uuid4())}
    )
    assert missing["ok"] is False and missing["error"]["code"] == "NOT_FOUND"


def test_bound_dispatcher_refuses_accessible_candidates_from_a_different_task(
    session: Session,
    scenario: tuple[ServiceContext, ResearchTask],
) -> None:
    ctx, task = scenario
    other = ResearchTask(
        workspace_id=ctx.workspace_id,
        project_id=task.project_id,
        title="Another accessible task",
        mode="discover",
        workflow_state="active",
    )
    session.add(other)
    session.flush()
    service = CandidateService(session, ctx)
    candidate = service.create_candidate(
        task_id=other.id, entity_kind="molecule", hypothesis="Synthetic other-task record"
    )
    assert (
        service.get(candidate.id).id == candidate.id
    )  # Workspace capability alone permits this read.
    bound = ToolDispatcher(session, ctx, task_id=task.id)
    for name, arguments in [
        ("read_candidate_revision", {"candidate_revision_id": str(candidate.id)}),
        (
            "propose_candidate_patch",
            {"candidate_id": str(candidate.id), "patch": {"hypothesis": "Do not apply"}},
        ),
        ("summarize_task_evidence", {"task_id": str(other.id)}),
    ]:
        result = bound.call(name, arguments)
        assert result["ok"] is False and result["error"]["code"] == "NOT_FOUND"
    assert session.query(CandidatePatch).count() == 0
    session.refresh(candidate)
    assert candidate.hypothesis == "Synthetic other-task record"


@pytest.mark.parametrize(
    "calls",
    [
        "not a list",
        [
            {
                "type": "function",
                "id": "",
                "function": {"name": "search_evidence", "arguments": "{}"},
            }
        ],
        [
            {
                "type": "function",
                "id": "x",
                "function": {"name": "search_evidence", "arguments": {"query": "x"}},
            }
        ],
        [{"type": "shell", "id": "x", "function": {"name": "export_vault", "arguments": "{}"}}],
        [
            {
                "type": "function",
                "id": "duplicate",
                "function": {"name": "search_evidence", "arguments": "{}"},
            }
        ]
        * 2,
    ],
)
def test_malformed_native_call_envelopes_do_not_execute_any_tool(
    session: Session,
    scenario: tuple[ServiceContext, ResearchTask],
    calls: Any,
) -> None:
    ctx, task = scenario
    research = TaskMemoryService(session, ctx).start_session(task.id)
    response = completion("")
    response["choices"][0]["message"]["tool_calls"] = calls
    with mock_provider([response]) as provider:
        runtime, _config, _store = configured_runtime(provider, ctx.workspace_id)
        outcome = AgentTurnRunner(session, ctx, runtime=runtime).run_turn(
            research.id, "Malformed envelope test"
        )
        assert outcome.finished_reason == "error" and outcome.final_message_id is None
        assert outcome.tool_calls == 0 and outcome.tool_messages == []
    assert session.query(Run).count() == 0
    assert session.query(CandidatePatch).count() == 0
    assert not any(
        row.kind in {"tool_call", "tool_result"} for row in messages(session, research.id)
    )


def test_provider_key_echo_inside_native_arguments_is_removed_before_dispatch_and_storage(
    session: Session,
    scenario: tuple[ServiceContext, ResearchTask],
) -> None:
    ctx, task = scenario
    research = TaskMemoryService(session, ctx).start_session(task.id)

    def after_redacted_search(body: dict[str, Any]) -> dict[str, Any]:
        result = last_result(body)
        assert result["ok"] is True
        assert fixture_credential() not in json.dumps(body)
        return completion("The synthetic search returned no source data.")

    with mock_provider(
        [
            native_tool("search_evidence", {"query": fixture_credential()}, call_id="echo"),
            after_redacted_search,
        ]
    ) as provider:
        runtime, _config, _store = configured_runtime(provider, ctx.workspace_id)
        outcome = AgentTurnRunner(session, ctx, runtime=runtime).run_turn(
            research.id, "Synthetic credential echo test"
        )
        assert outcome.finished_reason == "final"
    assert session.query(RetrievalManifest).one().query == "[REDACTED]"
    for row in messages(session, research.id):
        assert fixture_credential() not in row.content
        assert fixture_credential() not in json.dumps(row.refs)


def test_configured_provider_receives_only_sources_with_both_current_export_permissions(
    session: Session,
    scenario: tuple[ServiceContext, ResearchTask],
) -> None:
    from studio.domain.evidence.retrieval import RetrievalService

    ctx, task = scenario
    cases = [
        ("EXPORT_ALLOWED_SENTINEL", "allowed", "allowed"),
        ("NEVER_SEND_CHUNK_DENIED_SENTINEL", "allowed", "denied"),
        ("NEVER_SEND_CHUNK_UNKNOWN_SENTINEL", "allowed", None),
        ("NEVER_SEND_ARTIFACT_DENIED_SENTINEL", "denied", "allowed"),
        ("NEVER_SEND_ARTIFACT_UNKNOWN_SENTINEL", None, "allowed"),
        ("NEVER_SEND_CURRENT_REVOKED_ARTIFACT_SENTINEL", "allowed", "allowed"),
    ]
    sources = []
    for sentinel, artifact_export, chunk_export in cases:
        chunk = indexed_source(session, ctx, f"sentinel {sentinel}; synthetic protocol data only")
        artifact = session.get(Artifact, chunk.artifact_id)
        artifact.rights = {
            "retrieval": "allowed",
            **({"export": artifact_export} if artifact_export else {}),
        }
        chunk.rights = {
            "retrieval": "allowed",
            **({"export": chunk_export} if chunk_export else {}),
        }
        sources.append(chunk)
    session.flush()
    # Prime retrieval while every source is indexed; the export gate must
    # recheck authoritative artifact rights even on this later cache hit.
    cached, _manifest = RetrievalService(session).search(ctx, "sentinel")
    assert len(cached) == 6
    revoked = session.get(Artifact, sources[-1].artifact_id)
    revoked.rights = {"retrieval": "allowed", "export": "denied"}
    revoked.review_state = "revoked"
    session.flush()
    assert sources[-1].rights["export"] == "allowed"  # Deliberately stale chunk policy.
    research = TaskMemoryService(session, ctx).start_session(task.id)
    forbidden = (
        [case[0] for case in cases[1:]]
        + [str(row.id) for row in sources[1:]]
        + [str(row.artifact_id) for row in sources[1:]]
    )

    def inspect_export_gate(body: dict[str, Any]) -> dict[str, Any]:
        result = last_result(body)
        assert result["ok"] is True
        assert result["data"]["export_policy"] == "source-export-v1"
        assert result["data"]["withheld_sources"] == 5
        assert result["data"]["omissions"]
        assert [hit["chunk_id"] for hit in result["data"]["results"]] == [str(sources[0].id)]
        assert all(sentinel not in json.dumps(body) for sentinel in forbidden)
        return completion(
            "Only one export-permitted synthetic source is available; five were withheld."
        )

    with mock_provider(
        [
            native_tool("search_evidence", {"query": "sentinel"}, call_id="rights"),
            inspect_export_gate,
        ]
    ) as provider:
        runtime, _config, _store = configured_runtime(provider, ctx.workspace_id)
        outcome = AgentTurnRunner(session, ctx, runtime=runtime).run_turn(
            research.id, "Search the current synthetic sources."
        )
        assert outcome.finished_reason == "final"
        assert len(provider.requests) == 2
    result_row = next(row for row in messages(session, research.id) if row.kind == "tool_result")
    result = json.loads(result_row.content)
    assert all(sentinel not in result_row.content for sentinel in forbidden)
    exposure = session.get(RetrievalManifest, uuid.UUID(result["data"]["manifest_id"]))
    assert exposure.cached is True
    assert exposure.chunk_ids == [str(sources[0].id)]
    assert exposure.policy_version.endswith(";source-export-v1")
    assert session.get(Artifact, sources[-1].artifact_id).rights["export"] == "denied"
    assert "export" not in session.get(Artifact, sources[-2].artifact_id).rights
    # Local llama/direct retrieval keeps its separate retrieval permission.
    local = ToolDispatcher(session, ctx, task_id=task.id).call(
        "search_evidence", {"query": "sentinel"}
    )
    assert len(local["data"]["results"]) == 6


def test_configured_history_omits_all_previous_assistant_source_quotations(
    session: Session,
    scenario: tuple[ServiceContext, ResearchTask],
) -> None:
    ctx, task = scenario
    memory = TaskMemoryService(session, ctx)
    research = memory.start_session(task.id)
    memory.post_message(research.id, role="user", content="Earlier explicit user question")
    memory.post_message(
        research.id, role="assistant", content="NEVER_SEND_LOCAL_DENIED_SOURCE_QUOTATION"
    )
    memory.post_message(
        research.id,
        role="assistant",
        content="NEVER_SEND_LEGACY_PROVIDER_SOURCE_QUOTATION",
        refs={"provider_id": str(uuid.uuid4())},
    )
    memory.post_message(
        research.id,
        role="assistant",
        content="Trusted prior export-gated reply",
        refs={"provider_id": str(uuid.uuid4()), "provider_egress_policy": "source-export-v1"},
    )

    def inspect_history(body: dict[str, Any]) -> dict[str, Any]:
        serialized = json.dumps(body["messages"])
        assert "Earlier explicit user question" in serialized
        assert "Trusted prior export-gated reply" not in serialized
        assert "NEVER_SEND_LOCAL_DENIED_SOURCE_QUOTATION" not in serialized
        assert "NEVER_SEND_LEGACY_PROVIDER_SOURCE_QUOTATION" not in serialized
        assert "omitted" in serialized.lower()
        return completion(
            "Only permitted history was used; no private source quotation was transferred."
        )

    with mock_provider([inspect_history]) as provider:
        runtime, _config, _store = configured_runtime(provider, ctx.workspace_id)
        outcome = AgentTurnRunner(session, ctx, runtime=runtime).run_turn(
            research.id, "Continue with permitted context only."
        )
        assert outcome.finished_reason == "final"
    result = session.get(SessionMessage, outcome.final_message_id)
    assert result.refs["provider_egress_policy"] == "source-export-v1"


@pytest.mark.parametrize(("limit", "expected_requests"), [(1, 0), (8192, 1)])
def test_total_token_budget_stops_before_http_or_before_persisting_an_over_budget_answer(
    session: Session,
    scenario: tuple[ServiceContext, ResearchTask],
    limit: int,
    expected_requests: int,
) -> None:
    from workers.inference import TurnBudget

    ctx, task = scenario
    research = TaskMemoryService(session, ctx).start_session(task.id)
    response = completion("NEVER_PERSIST_OVER_BUDGET_SUCCESS")
    response["usage"]["total_tokens"] = 1_000_000
    with mock_provider([response]) as provider:
        runtime, _config, _store = configured_runtime(provider, ctx.workspace_id)
        outcome = AgentTurnRunner(
            session,
            ctx,
            runtime=runtime,
            budget=TurnBudget(
                max_total_tokens=limit,
            ),
        ).run_turn(research.id, "Explicit token budget test")
        assert outcome.finished_reason == "budget" and outcome.final_message_id is None
        assert len(provider.requests) == expected_requests
    assert not any(
        row.content == "NEVER_PERSIST_OVER_BUDGET_SUCCESS" for row in messages(session, research.id)
    )


def test_native_tool_budget_prevents_a_second_tool_from_creating_a_run(
    session: Session,
    scenario: tuple[ServiceContext, ResearchTask],
) -> None:
    from workers.inference import TurnBudget

    ctx, task = scenario
    research = TaskMemoryService(session, ctx).start_session(task.id)

    def after_first(body: dict[str, Any]) -> dict[str, Any]:
        result = last_result(body)
        assert result["ok"] is True and result["data"]["candidates_total"] == 0
        return native_tool(
            "request_calculation",
            {
                "task_id": str(task.id),
                "kind": "simulation",
                "request": {"operation": "must be prevented by the explicit tool budget"},
            },
            call_id="prevented",
        )

    with mock_provider(
        [
            native_tool("summarize_task_evidence", {"task_id": str(task.id)}, call_id="allowed"),
            after_first,
        ]
    ) as provider:
        runtime, _config, _store = configured_runtime(provider, ctx.workspace_id)
        outcome = AgentTurnRunner(
            session,
            ctx,
            runtime=runtime,
            budget=TurnBudget(
                max_tool_calls=1,
            ),
        ).run_turn(research.id, "Explicit one-tool budget test")
        assert outcome.finished_reason == "budget" and outcome.final_message_id is None
        assert outcome.tool_calls == 1 and len(provider.requests) == 2
    assert session.query(Run).count() == 0
    assert len(outcome.tool_messages) == 2  # Only the first real call/result pair.
