"""Consented API turn → real provider HTTP → native tools → durable records.

Only the credential store is in memory. Authentication, provider metadata,
revision/consent/idempotency gates, adapter, executor, and database are real.
The provider is the local deterministic fixture, never a paid endpoint.
"""

from __future__ import annotations

import json
import re
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from strawberry import relay
from workers.inference import LlamaCppRuntime

from studio.auth.context import load_context
from studio.domain.candidates.service import CandidateService
from studio.persistence.models import Principal, SessionMessage, Workspace

from .test_inference_provider_http import (
    MemorySecretStore,
    completion,
    fixture_credential,
    mock_provider,
    native_tool,
)
from .test_turn_request import _client, _gid, _gql, _session_id, _setup_owner, _task

pytestmark = pytest.mark.integration

SAVE = """mutation($i:InferenceProviderSaveInput!){providers{save(input:$i){
  provider{id revision name kind baseUrl model enabled hasApiKey lastTestStatus}
  errors{code message} }}}"""
TEST = """mutation($i:InferenceProviderTestInput!){providers{test(input:$i){
  provider{id revision} status detail errors{code message} }}}"""
TURN = """mutation($i:TurnRequestInput!){research{turnRequest(input:$i){
  turnId finishedReason toolCalls detail finalMessage{id role content refs}
  errors{code message fieldPath} }}}"""


def test_provider_selection_consent_revision_native_tools_and_replay_are_enforced_at_graphql(
    db_url: str,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemorySecretStore()
    monkeypatch.setattr("studio.domain.inference.providers.get_secret_store", lambda: store)
    # The unselected local fallback must also be deterministic; this test
    # must not discover and run a developer's actual model container.
    monkeypatch.setattr(LlamaCppRuntime, "running", lambda _runtime: False)

    with _client(db_url) as client:
        _setup_owner(client)
        ws = session.query(Workspace).one()
        owner = session.query(Principal).filter_by(login="owner").one()
        ctx = load_context(session, ws.id, owner.id)
        task = _task(session, ws)
        candidate = CandidateService(session, ctx).create_candidate(
            task_id=task.id,
            entity_kind="molecule",
            hypothesis="Synthetic API fixture candidate",
        )
        session.commit()
        sid = _session_id(client, _gid("Task", task.id))
        discovered: dict[str, str] = {}

        def inspect_context(body: dict) -> dict:
            system = " ".join(m["content"] for m in body["messages"] if m["role"] == "system")
            match = re.search(r"Task ID:\s*([0-9a-fA-F-]{36})", system)
            assert match is not None
            discovered["task"] = str(uuid.UUID(match.group(1)))
            assert discovered["task"] == str(task.id)
            assert body["messages"][-1]["content"] == "Inspect this task and its current candidate."
            return native_tool(
                "summarize_task_evidence", {"task_id": discovered["task"]}, call_id="discover"
            )

        def read_discovered_candidate(body: dict) -> dict:
            message = body["messages"][-1]
            assert message["role"] == "tool" and message["tool_call_id"] == "discover"
            result = json.loads(message["content"])
            assert result["ok"] is True
            assert result["data"]["claims"] == 0
            assert result["data"]["candidates_total"] == 1
            discovered["candidate"] = result["data"]["candidates"][0]["id"]
            assert discovered["candidate"] == str(candidate.id)
            return native_tool(
                "read_candidate_revision",
                {"candidate_revision_id": discovered["candidate"]},
                call_id="read",
            )

        def conclude_from_actual_record(body: dict) -> dict:
            message = body["messages"][-1]
            assert message["role"] == "tool" and message["tool_call_id"] == "read"
            result = json.loads(message["content"])
            assert result["ok"] is True
            assert result["data"]["id"] == discovered["candidate"]
            assert result["data"]["status"] == "draft"
            return completion(
                "One synthetic draft candidate exists. "
                "No accepted evidence or laboratory outcome exists."
            )

        with mock_provider(
            [inspect_context, read_discovered_candidate, conclude_from_actual_record]
        ) as provider:
            saved = _gql(
                client,
                SAVE,
                {
                    "i": {
                        "name": "Synthetic local protocol provider",
                        "kind": "openai_compatible",
                        "baseUrl": f"{provider.base_url}/v1",
                        "model": "fixture-model",
                        "enabled": True,
                        "supportsTools": True,
                        "apiKey": fixture_credential(),
                        "clientMutationId": "fixture-provider-create",
                    }
                },
            )["data"]["providers"]["save"]
            assert saved["errors"] == []
            configuration = saved["provider"]
            assert configuration["hasApiKey"] is True
            assert configuration["lastTestStatus"] == "untested"
            assert provider.requests == []  # Saving never probes or transmits a prompt.
            assert fixture_credential() not in json.dumps(saved)
            metadata = _gql(client, "query{inferenceProviders{id name hasApiKey baseUrl model}}")
            assert fixture_credential() not in json.dumps(metadata)
            stored = session.execute(
                text("SELECT row_to_json(p)::text FROM inference_providers p")
            ).scalar_one()
            assert fixture_credential() not in stored

            tested = _gql(client, TEST, {"i": {"id": configuration["id"]}})["data"]["providers"][
                "test"
            ]
            assert tested["errors"] == [] and tested["status"] == "reachable"
            assert "not tested" in tested["detail"]
            assert [(request["method"], request["path"]) for request in provider.requests] == [
                ("GET", "/v1/models")
            ]
            assert provider.requests[0]["body"] is None
            assert len(provider.responses) == 3  # The reachability probe never generates text.

            unselected = _gql(
                client,
                TURN,
                {
                    "i": {
                        "sessionId": sid,
                        "content": "Local fallback only",
                        "turnId": "fixture-local-fallback",
                    }
                },
            )["data"]["research"]["turnRequest"]
            assert (
                unselected["errors"] == [] and unselected["finishedReason"] == "model_unavailable"
            )
            assert len(provider.requests) == 1  # An enabled row is never silently selected.

            base_input = {
                "sessionId": sid,
                "content": "Inspect this task and its current candidate.",
                "providerId": configuration["id"],
                "providerRevision": configuration["revision"],
            }
            denied = _gql(client, TURN, {"i": {**base_input, "turnId": "fixture-consent-denied"}})[
                "data"
            ]["research"]["turnRequest"]
            assert denied["errors"][0]["code"] == "FORBIDDEN"
            assert denied["finalMessage"] is None and len(provider.requests) == 1
            stale = _gql(
                client,
                TURN,
                {
                    "i": {
                        **base_input,
                        "turnId": "fixture-stale-provider",
                        "providerRevision": configuration["revision"] + 1,
                        "allowProviderDataTransfer": True,
                    }
                },
            )["data"]["research"]["turnRequest"]
            assert stale["errors"][0]["code"] == "CONFLICT"
            assert stale["errors"][0]["fieldPath"] == "providerRevision"
            assert stale["finalMessage"] is None and len(provider.requests) == 1

            turn_id = "fixture-consented-native-turn"
            request_input = {
                **base_input,
                "turnId": turn_id,
                "allowProviderDataTransfer": True,
                "idempotencyKey": "fixture-turn-key",
            }
            result = _gql(client, TURN, {"i": request_input})["data"]["research"]["turnRequest"]
            assert result["errors"] == [] and result["finishedReason"] == "final"
            assert result["toolCalls"] == 2
            assert "synthetic draft" in result["finalMessage"]["content"]
            assert result["finalMessage"]["refs"]["provider_id"] == configuration["id"]
            assert result["finalMessage"]["refs"]["model"] == "fixture-model"
            assert len(provider.requests) == 4 and provider.responses == []
            assert all(
                request["authorization"] == f"Bearer {fixture_credential()}"
                for request in provider.requests
            )
            replay = _gql(client, TURN, {"i": request_input})["data"]["research"]["turnRequest"]
            assert replay["finalMessage"]["id"] == result["finalMessage"]["id"]
            assert len(provider.requests) == 4
            mismatched = _gql(
                client, TURN, {"i": {**request_input, "content": "A changed question"}}
            )["data"]["research"]["turnRequest"]
            assert mismatched["errors"][0]["code"] == "IDEMPOTENCY_MISMATCH"
            assert len(provider.requests) == 4

        session.expire_all()
        session_uuid = uuid.UUID(relay.GlobalID.from_id(sid).node_id)
        rows = (
            session.query(SessionMessage)
            .filter(
                SessionMessage.session_id == session_uuid,
                SessionMessage.refs["turn_id"].astext == turn_id,
            )
            .all()
        )
        assert len(rows) == 6  # User, two call/result pairs, final.
        assert sum(row.kind == "tool_call" for row in rows) == 2
        assert sum(row.kind == "tool_result" for row in rows) == 2
        assert all(row.refs["provider_id"] == configuration["id"] for row in rows)
        assert not any(fixture_credential() in row.content + json.dumps(row.refs) for row in rows)


def test_concurrent_duplicate_turns_make_one_provider_chain_and_one_durable_result(
    db_url: str,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hashlib
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    import studio.application.agent_tools.requests as turn_requests

    store = MemorySecretStore()
    monkeypatch.setattr("studio.domain.inference.providers.get_secret_store", lambda: store)
    entered = threading.Event()
    release = threading.Event()
    arrival = threading.Barrier(2)
    real_run = turn_requests.run_research_turn

    def synchronized_run(*args, **kwargs):
        arrival.wait(timeout=10)
        return real_run(*args, **kwargs)

    with _client(db_url) as first_client, _client(db_url) as second_client:
        _setup_owner(first_client)
        second_client.cookies.update(first_client.cookies)
        ws = session.query(Workspace).one()
        task = _task(session, ws)
        session.commit()
        sid = _session_id(first_client, _gid("Task", task.id))
        session_uuid = uuid.UUID(relay.GlobalID.from_id(sid).node_id)

        def blocked_first_generation(body: dict) -> dict:
            entered.set()
            assert release.wait(timeout=10), "Concurrent fixture did not release generation"
            system = " ".join(m["content"] for m in body["messages"] if m["role"] == "system")
            match = re.search(r"Task ID:\s*([0-9a-fA-F-]{36})", system)
            assert match is not None
            return native_tool(
                "summarize_task_evidence", {"task_id": match.group(1)}, call_id="single"
            )

        def finish_after_real_tool(body: dict) -> dict:
            message = body["messages"][-1]
            assert message["role"] == "tool" and message["tool_call_id"] == "single"
            result = json.loads(message["content"])
            assert result["ok"] is True and result["data"]["candidates_total"] == 0
            return completion(
                "The synthetic task has zero candidates; this is the one durable reply."
            )

        with mock_provider([blocked_first_generation, finish_after_real_tool]) as provider:
            saved = _gql(
                first_client,
                SAVE,
                {
                    "i": {
                        "name": "Concurrent synthetic provider",
                        "kind": "openai_compatible",
                        "baseUrl": f"{provider.base_url}/v1",
                        "model": "fixture-model",
                        "enabled": True,
                        "apiKey": fixture_credential(),
                        "clientMutationId": "concurrent-provider-create",
                    }
                },
            )["data"]["providers"]["save"]
            assert saved["errors"] == []
            configuration = saved["provider"]
            request_input = {
                "sessionId": sid,
                "content": "One synthetic simultaneous turn",
                "turnId": "concurrent-same-turn",
                "idempotencyKey": "concurrent-same-key",
                "providerId": configuration["id"],
                "providerRevision": configuration["revision"],
                "allowProviderDataTransfer": True,
            }
            monkeypatch.setattr(turn_requests, "run_research_turn", synchronized_run)
            lock_bits = int.from_bytes(
                hashlib.sha256(
                    f"research-turn:{ws.id}:{session_uuid}".encode(),
                ).digest()[:8]
            )
            with ThreadPoolExecutor(max_workers=2) as pool:
                pending = [
                    pool.submit(_gql, client, TURN, {"i": request_input})
                    for client in [first_client, second_client]
                ]
                try:
                    assert entered.wait(timeout=10)
                    deadline = time.monotonic() + 5
                    waiter_seen = False
                    while time.monotonic() < deadline:
                        waiters = session.execute(
                            text(
                                "SELECT count(*) FROM pg_locks WHERE locktype='advisory' "
                                "AND NOT granted AND classid::bigint=:upper "
                                "AND objid::bigint=:lower"
                            ),
                            {"upper": lock_bits >> 32, "lower": lock_bits & 0xFFFFFFFF},
                        ).scalar_one()
                        if waiters:
                            waiter_seen = True
                            break
                        time.sleep(0.01)
                    assert waiter_seen, "Duplicate request must wait before external provider I/O"
                    assert len(provider.requests) == 1
                finally:
                    release.set()
                results = [
                    future.result(timeout=15)["data"]["research"]["turnRequest"]
                    for future in pending
                ]
            assert all(
                result["errors"] == [] and result["finishedReason"] == "final" for result in results
            )
            assert results[0]["finalMessage"]["id"] == results[1]["finalMessage"]["id"]
            assert results[0]["toolCalls"] == results[1]["toolCalls"] == 1
            assert len(provider.requests) == 2 and provider.responses == []
        session.expire_all()
        rows = (
            session.query(SessionMessage)
            .filter(
                SessionMessage.session_id == session_uuid,
                SessionMessage.refs["turn_id"].astext == "concurrent-same-turn",
            )
            .all()
        )
        assert len(rows) == 4
        assert [sum(row.kind == kind for row in rows) for kind in ["tool_call", "tool_result"]] == [
            1,
            1,
        ]
        assert sum(row.role == "user" for row in rows) == 1
