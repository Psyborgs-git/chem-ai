"""Private conversation discovery and bounded chronological message history."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import event
from starlette.testclient import TestClient

from studio.api.agent_workspace import agent_router
from studio.api.deps import db_session, request_context
from studio.auth.context import ServiceContext
from studio.domain.agent_workspace.models import AgentMessage, AgentRun, AgentThread
from studio.domain.agent_workspace.runtime import _message
from studio.domain.agent_workspace.service import AgentWorkspaceService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import Principal, Workspace

pytestmark = pytest.mark.integration
BASE_TIME = datetime(2024, 1, 1, tzinfo=UTC)


@pytest.fixture()
def history(session):
    workspace = Workspace(slug="history-private", display_name="History")
    session.add(workspace)
    session.flush()
    contexts = []
    for name in ("one", "other"):
        owner = Principal(workspace_id=workspace.id, kind="user", login=name, display_name=name)
        session.add(owner)
        session.flush()
        contexts.append(ServiceContext(session, workspace.id, owner.id, "user", frozenset()))
    return contexts


def message(ctx, thread, text, index=0, *, role="assistant", kind="message", **overrides):
    return AgentMessage(
        **{
            "workspace_id": ctx.workspace_id,
            "owner_id": ctx.principal_id,
            "thread_id": thread.id,
            "role": role,
            "kind": kind,
            "content": text,
            "refs": {},
            "created_at": BASE_TIME + timedelta(seconds=index),
            **overrides,
        }
    )


def test_thread_search_metadata_is_private_and_visible_only(session, history):
    owner, other = history
    service = AgentWorkspaceService(session, owner)
    own = AgentThread(
        workspace_id=owner.workspace_id, owner_id=owner.principal_id, title="Owned conversation"
    )
    unrelated = AgentThread(
        workspace_id=owner.workspace_id, owner_id=other.principal_id, title="Foreign needle"
    )
    another_workspace = Workspace(slug="other-history-space", display_name="Other")
    session.add_all([own, unrelated, another_workspace])
    session.flush()
    session.add_all(
        [
            message(owner, own, "Silk properties", role="user"),
            message(owner, own, "Visible reply " + "a" * 200, 1),
            message(owner, own, "TOOL_ONLY_SENTINEL", 2, role="tool", kind="tool_result"),
            message(owner, own, "SYSTEM_ONLY_SENTINEL", 3, role="system"),
            message(owner, own, "STATUS_ONLY_SENTINEL", 4, kind="status"),
            message(other, own, "FOREIGN_OWNER_SENTINEL", 100),
            message(
                owner, own, "FOREIGN_WORKSPACE_SENTINEL", 101, workspace_id=another_workspace.id
            ),
        ]
    )
    session.add_all(
        [
            AgentRun(
                workspace_id=owner.workspace_id,
                owner_id=owner.principal_id,
                thread_id=own.id,
                prompt="Own",
                status="completed",
                checkpoint={},
                created_at=BASE_TIME,
            ),
            AgentRun(
                workspace_id=owner.workspace_id,
                owner_id=other.principal_id,
                thread_id=own.id,
                prompt="Foreign",
                status="running",
                checkpoint={},
                created_at=BASE_TIME + timedelta(days=1),
            ),
            AgentRun(
                workspace_id=another_workspace.id,
                owner_id=owner.principal_id,
                thread_id=own.id,
                prompt="Other workspace",
                status="failed",
                checkpoint={},
                created_at=BASE_TIME + timedelta(days=2),
            ),
        ]
    )
    session.flush()
    page = service.list_threads_page(q="ViSiBlE RePlY")
    assert page["ownerScope"] == f"{owner.workspace_id}:{owner.principal_id}"
    assert len(page["threads"]) == 1
    summary = page["threads"][0]
    assert summary["id"] == str(own.id)
    assert summary["messageCount"] == 2
    assert summary["lastMessagePreview"] == ("Visible reply " + "a" * 200)[:160]
    assert summary["lastRunStatus"] == "completed"
    for query in (
        "FOREIGN_OWNER_SENTINEL",
        "FOREIGN_WORKSPACE_SENTINEL",
        "TOOL_ONLY_SENTINEL",
        "SYSTEM_ONLY_SENTINEL",
        "STATUS_ONLY_SENTINEL",
        "Foreign needle",
    ):
        assert service.list_threads_page(q=query)["threads"] == []


def test_literal_search_pagination_and_rest_owner_scope_beyond_one_hundred_threads(
    session, history
):
    owner, _other = history
    for index in range(125):
        session.add(
            AgentThread(
                workspace_id=owner.workspace_id,
                owner_id=owner.principal_id,
                title=f"Thread {index:03}",
                created_at=BASE_TIME,
                updated_at=BASE_TIME + timedelta(seconds=index),
            )
        )
    session.flush()
    service = AgentWorkspaceService(session, owner)
    pages = [service.list_threads_page(offset=offset, limit=50) for offset in (0, 50, 100)]
    assert [len(page["threads"]) for page in pages] == [50, 50, 25]
    assert [page["nextOffset"] for page in pages] == [50, 100, None]
    identifiers = [thread["id"] for page in pages for thread in page["threads"]]
    assert len(set(identifiers)) == 125
    assert pages[-1]["threads"][-1]["title"] == "Thread 000"
    assert len(service.list_threads()) == 100
    special = service.create_thread({"title": r"Ratio 100%_\literal"})
    for query in ("%", "_", chr(92), "%_" + chr(92)):
        assert [thread["id"] for thread in service.list_threads_page(q=query)["threads"]] == [
            special["id"]
        ]
    queries = []
    bind = session.get_bind()

    def count_query(_conn, _cursor, statement, *_args):
        queries.append(statement)

    event.listen(bind, "before_cursor_execute", count_query)
    try:
        service.list_threads_page(limit=50)
    finally:
        event.remove(bind, "before_cursor_execute", count_query)
    assert len(queries) == 1
    app = FastAPI()
    app.include_router(agent_router, prefix="/api/agent-workspace")
    app.dependency_overrides[db_session] = lambda: session
    app.dependency_overrides[request_context] = lambda: owner
    with TestClient(app) as client:
        response = client.get(
            "/api/agent-workspace/threads", params={"q": "%_" + chr(92), "limit": 1}
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["threads"][0]["id"] == special["id"]
        assert response.json()["ownerScope"] == f"{owner.workspace_id}:{owner.principal_id}"
        assert client.get("/api/agent-workspace/threads?limit=101").status_code == 422


def test_history_loads_latest_and_earlier_without_foreign_cursors(session, history):
    owner, other = history
    service = AgentWorkspaceService(session, owner)
    thread = AgentThread(
        workspace_id=owner.workspace_id, owner_id=owner.principal_id, title="Long history"
    )
    another = AgentThread(
        workspace_id=owner.workspace_id, owner_id=owner.principal_id, title="Other history"
    )
    session.add_all([thread, another])
    session.flush()
    session.add_all([message(owner, thread, str(index), index) for index in range(1005)])
    foreign = message(other, thread, "Other owner's message", 2000)
    other_thread = message(owner, another, "Different thread", 2001)
    session.add_all([foreign, other_thread])
    session.flush()
    current = service.thread_detail(thread.id)
    assert len(current["messages"]) == 1000
    assert current["messages"][0]["content"] == "5"
    assert current["messages"][-1]["content"] == "1004"
    assert current["hasEarlierMessages"]
    older = service.thread_detail(thread.id, before=uuid.UUID(current["oldestMessageId"]))
    assert [item["content"] for item in older["messages"]] == [str(index) for index in range(5)]
    assert older["hasEarlierMessages"] is False
    for cursor in (foreign.id, other_thread.id, uuid.uuid4()):
        with pytest.raises(DomainError) as denied:
            service.thread_detail(thread.id, before=cursor)
        assert denied.value.code == ErrorCode.NOT_FOUND


def test_assistant_activity_updates_only_the_owned_thread_and_not_tool_polls(session, history):
    owner, other = history
    thread = AgentThread(
        workspace_id=owner.workspace_id,
        owner_id=owner.principal_id,
        title="History",
        updated_at=BASE_TIME,
    )
    session.add(thread)
    session.flush()
    run = AgentRun(
        workspace_id=owner.workspace_id,
        owner_id=owner.principal_id,
        thread_id=thread.id,
        prompt="Query",
        status="running",
        checkpoint={},
    )
    session.add(run)
    session.flush()
    _message(session, run, "assistant", "message", "Answer")
    session.flush()
    session.refresh(thread)
    updated = thread.updated_at
    assert updated > BASE_TIME
    _message(session, run, "tool", "tool_result", "Polling result")
    session.flush()
    session.refresh(thread)
    assert thread.updated_at == updated
    run.owner_id = other.principal_id
    _message(session, run, "assistant", "status", "Other owner's status")
    session.flush()
    session.refresh(thread)
    assert thread.updated_at == updated


def test_message_cursor_keeps_equal_timestamp_rows_without_duplicates_or_gaps(session, history):
    owner, _other = history
    service = AgentWorkspaceService(session, owner)
    thread = AgentThread(
        workspace_id=owner.workspace_id, owner_id=owner.principal_id, title="Tied timestamps"
    )
    session.add(thread)
    session.flush()
    for index in (1, 2, 3):
        session.add(message(owner, thread, str(index), id=uuid.UUID(int=index)))
    session.flush()
    latest = service.thread_detail(thread.id, limit=1)
    middle = service.thread_detail(thread.id, before=uuid.UUID(latest["oldestMessageId"]), limit=1)
    oldest = service.thread_detail(thread.id, before=uuid.UUID(middle["oldestMessageId"]), limit=1)
    assert [
        [item["content"] for item in page["messages"]] for page in (latest, middle, oldest)
    ] == [["3"], ["2"], ["1"]]
    assert [page["hasEarlierMessages"] for page in (latest, middle, oldest)] == [True, True, False]


def test_new_tool_messages_keep_clock_order_even_when_uuid_order_is_reversed(
    session, history, monkeypatch
):
    from studio.domain.agent_workspace import runtime

    owner, _other = history
    thread = AgentThread(
        workspace_id=owner.workspace_id, owner_id=owner.principal_id, title="Tool sequence"
    )
    session.add(thread)
    session.flush()
    run = AgentRun(
        workspace_id=owner.workspace_id,
        owner_id=owner.principal_id,
        thread_id=thread.id,
        prompt="Lookup",
        status="running",
        checkpoint={},
    )
    session.add(run)
    session.flush()
    moments = iter([BASE_TIME, BASE_TIME + timedelta(microseconds=1)])
    identifiers = iter([uuid.UUID(int=2), uuid.UUID(int=1)])

    class Clock(datetime):
        @classmethod
        def now(cls, _tz=None):
            return next(moments)

    def create_message(**values):
        return AgentMessage(**{**values, "id": next(identifiers)})

    monkeypatch.setattr(runtime, "datetime", Clock)
    monkeypatch.setattr(runtime, "AgentMessage", create_message)
    runtime._message(session, run, "assistant", "tool_call", "Lookup request")
    runtime._message(session, run, "tool", "tool_result", "Lookup response")
    session.flush()
    detail = AgentWorkspaceService(session, owner).thread_detail(thread.id)
    assert [item["content"] for item in detail["messages"]] == ["Lookup request", "Lookup response"]
    assert [item["id"] for item in detail["messages"]] == [
        str(uuid.UUID(int=2)),
        str(uuid.UUID(int=1)),
    ]
    assert detail["messages"][0]["createdAt"] != detail["messages"][1]["createdAt"]
