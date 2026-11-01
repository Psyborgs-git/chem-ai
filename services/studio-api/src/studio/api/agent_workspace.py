"""Private agent workspace HTTP boundary."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response

from studio.api.deps import Ctx, DbSession
from studio.domain.agent_workspace.service import AgentWorkspaceService


def _private_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


agent_router = APIRouter(tags=["private-agent-workspace"], dependencies=[Depends(_private_headers)])


@agent_router.get("/tools")
def tool_catalog(ctx: Ctx) -> dict[str, Any]:
    from studio.domain.agent_workspace.tools import catalog

    if ctx.principal_kind != "user":
        from studio.errors import DomainError, ErrorCode

        raise DomainError(ErrorCode.FORBIDDEN, "private tools require a user")
    return {"tools": catalog()}


@agent_router.get("/providers")
def providers(db: DbSession, ctx: Ctx) -> dict[str, Any]:
    rows = AgentWorkspaceService(db, ctx).providers()
    db.commit()
    return {"providers": rows}


@agent_router.post("/providers/{provider_id}/models")
def save_model(
    provider_id: uuid.UUID, db: DbSession, ctx: Ctx, body: dict[str, Any]
) -> dict[str, Any]:
    result = AgentWorkspaceService(db, ctx).save_model(provider_id, body)
    db.commit()
    return result


@agent_router.post("/providers/{provider_id}/discover")
def discover(provider_id: uuid.UUID, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return AgentWorkspaceService(db, ctx).discover(provider_id)


@agent_router.get("/policies")
def policy(db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return AgentWorkspaceService(db, ctx).policy()


@agent_router.put("/policies")
def save_policy(db: DbSession, ctx: Ctx, body: dict[str, Any]) -> dict[str, Any]:
    result = AgentWorkspaceService(db, ctx).save_policy(body)
    db.commit()
    return result


@agent_router.get("/threads")
def threads(
    db: DbSession,
    ctx: Ctx,
    q: str = Query(default="", max_length=200),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    return AgentWorkspaceService(db, ctx).list_threads_page(q=q, offset=offset, limit=limit)


@agent_router.post("/threads")
def create_thread(db: DbSession, ctx: Ctx, body: dict[str, Any]) -> dict[str, Any]:
    result = AgentWorkspaceService(db, ctx).create_thread(body)
    db.commit()
    return result


@agent_router.get("/threads/{thread_id}")
def thread(
    thread_id: uuid.UUID,
    db: DbSession,
    ctx: Ctx,
    before: uuid.UUID | None = None,
    limit: int = Query(default=1000, ge=1, le=1000),
) -> dict[str, Any]:
    return AgentWorkspaceService(db, ctx).thread_detail(thread_id, before=before, limit=limit)


@agent_router.put("/threads/{thread_id}/automation")
def automation(
    thread_id: uuid.UUID, db: DbSession, ctx: Ctx, body: dict[str, Any]
) -> dict[str, Any]:
    result = AgentWorkspaceService(db, ctx).save_automation(thread_id, body)
    db.commit()
    return result


@agent_router.post("/threads/{thread_id}/runs")
def create_run(
    thread_id: uuid.UUID, db: DbSession, ctx: Ctx, body: dict[str, Any]
) -> dict[str, Any]:
    result = AgentWorkspaceService(db, ctx).create_run(thread_id, body)
    db.commit()
    return result


@agent_router.get("/runs/{run_id}")
def run(run_id: uuid.UUID, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return AgentWorkspaceService(db, ctx).run_detail(run_id)


@agent_router.post("/runs/{run_id}/cancel")
def cancel(run_id: uuid.UUID, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = AgentWorkspaceService(db, ctx).cancel(run_id)
    db.commit()
    return result


@agent_router.post("/runs/{run_id}/resume")
def resume(run_id: uuid.UUID, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = AgentWorkspaceService(db, ctx).resume(run_id)
    db.commit()
    return result
