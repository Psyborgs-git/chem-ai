"""The prompt catalog and executable catalog are the same closed set.

These dispatcher boundary tests use no database or inference provider.
Domain authorization and durable effects are exercised by integration tests.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.orm import Session

from studio.application.agent_tools.registry import AgentTool, ToolDispatcher, ToolRegistry
from studio.auth.context import ServiceContext
from studio.errors import DomainError, ErrorCode


def _context() -> ServiceContext:
    return ServiceContext(
        session=Session(),
        workspace_id=uuid.uuid4(),
        principal_id=uuid.uuid4(),
        principal_kind="agent",
        grants=frozenset(),
    )


def test_dispatcher_executes_only_the_injected_catalog() -> None:
    ctx = _context()
    seen: list[tuple[Any, Any, Any]] = []

    def handler(db: Session, actual_ctx: ServiceContext, args: dict[str, Any]) -> dict[str, Any]:
        seen.append((db, actual_ctx, args))
        return {"count": args["count"]}

    registry = ToolRegistry(
        [
            AgentTool(
                "count_fixture",
                "A deterministic test fixture",
                {
                    "type": "object",
                    "properties": {"count": {"type": "integer"}},
                    "required": ["count"],
                    "additionalProperties": False,
                },
                handler,
            ),
        ]
    )
    dispatcher = ToolDispatcher(ctx.session, ctx, registry=registry)
    assert registry.names() == ["count_fixture"]
    result = dispatcher.call("count_fixture", {"count": 0})
    assert result == {"ok": True, "untrusted": True, "data": {"count": 0}}
    assert seen == [(ctx.session, ctx, {"count": 0})]
    # A name known to the default catalog is still forbidden when it
    # was not exposed in this turn's catalog.
    hidden = dispatcher.call("search_evidence", {"query": "anything"})
    assert hidden["error"]["code"] == "UNKNOWN_TOOL"
    assert dispatcher.usage.calls == 1


def test_an_empty_injected_catalog_does_not_fall_back_to_defaults() -> None:
    ctx = _context()
    result = ToolDispatcher(ctx.session, ctx, registry=ToolRegistry([])).call(
        "request_calculation", {"kind": "simulation", "request": {}}
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "UNKNOWN_TOOL"


@pytest.mark.parametrize(
    "arguments",
    [
        None,
        [],
        "not an object",
        {"revision_id": "not-a-uuid", "count": 1},
        {"revision_id": str(uuid.uuid4()), "count": True},
        {"revision_id": str(uuid.uuid4()), "count": "1"},
        {"revision_id": str(uuid.uuid4()), "count": 1, "approve": True},
        {"revision_id": str(uuid.uuid4())},
    ],
)
def test_invalid_arguments_never_reach_the_handler(arguments: Any) -> None:
    ctx = _context()
    calls: list[Any] = []
    registry = ToolRegistry(
        [
            AgentTool(
                "strict_fixture",
                "UUID and numeric types are not coerced",
                {
                    "type": "object",
                    "properties": {
                        "revision_id": {"type": "string", "format": "uuid"},
                        "count": {"type": "integer"},
                    },
                    "required": ["revision_id", "count"],
                    "additionalProperties": False,
                },
                lambda _db, _ctx, args: calls.append(args) or {},
            ),
        ]
    )
    dispatcher = ToolDispatcher(ctx.session, ctx, registry=registry)
    result = dispatcher.call("strict_fixture", arguments)
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"
    assert calls == []
    assert dispatcher.usage.calls == 0


def test_domain_refusal_is_a_failure_result_and_not_a_success_payload() -> None:
    ctx = _context()

    def refuse(_db: Session, _ctx: ServiceContext, _args: dict[str, Any]) -> dict[str, Any]:
        raise DomainError(ErrorCode.FORBIDDEN, "fixture operation requires permission")

    registry = ToolRegistry(
        [
            AgentTool("restricted_fixture", "Must refuse", {"type": "object"}, refuse),
        ]
    )
    result = ToolDispatcher(ctx.session, ctx, registry=registry).call("restricted_fixture", {})
    assert result == {
        "ok": False,
        "error": {
            "code": "FORBIDDEN",
            "message": "fixture operation requires permission",
        },
    }
    assert "data" not in result


def test_session_bound_catalog_and_dispatch_agree_on_required_task_attribution() -> None:
    ctx = _context()
    task_id = uuid.uuid4()
    seen: list[dict[str, Any]] = []
    schema = {
        "type": "object",
        "properties": {
            "kind": {"type": "string"},
            "request": {"type": "object"},
            "task_id": {"type": "string", "format": "uuid"},
        },
        "required": ["kind", "request"],
        "additionalProperties": False,
    }
    registry = ToolRegistry(
        [
            AgentTool(
                "request_calculation",
                "Explicit fixture request",
                schema,
                lambda _db, _ctx, args: seen.append(args) or {"status": "requested"},
            )
        ]
    )
    dispatcher = ToolDispatcher(ctx.session, ctx, registry=registry, task_id=task_id)
    assert "task_id" not in registry.catalog()[0]["input_schema"]["required"]
    assert "task_id" in dispatcher.registry.catalog()[0]["input_schema"]["required"]
    missing = dispatcher.call("request_calculation", {"kind": "fixture", "request": {}})
    assert missing["error"]["code"] == "INVALID_INPUT" and seen == []
    foreign = dispatcher.call(
        "request_calculation",
        {
            "kind": "fixture",
            "request": {},
            "task_id": str(uuid.uuid4()),
        },
    )
    assert foreign["error"]["code"] == "NOT_FOUND" and seen == []
    bound = dispatcher.call(
        "request_calculation",
        {
            "kind": "fixture",
            "request": {},
            "task_id": str(task_id),
        },
    )
    assert bound["ok"] is True
    assert seen[0]["task_id"] == str(task_id)
