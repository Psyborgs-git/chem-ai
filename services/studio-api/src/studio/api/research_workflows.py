"""Human-created public-source workflows; agents cannot expand their budgets."""

import uuid
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select

from studio.api.deps import Ctx, DbSession
from studio.domain.agent_workspace.workflows import ResearchWorkflow, WorkflowService

router = APIRouter(prefix="/api/research-workflows", tags=["research-workflows"])


@router.get("")
def workflows(db: DbSession, ctx: Ctx) -> list[dict[str, Any]]:
    service = WorkflowService(db, ctx)
    return [
        service.describe(row)
        for row in db.scalars(
            select(ResearchWorkflow)
            .where(
                ResearchWorkflow.workspace_id == ctx.workspace_id,
                ResearchWorkflow.owner_id == ctx.principal_id,
            )
            .order_by(ResearchWorkflow.created_at.desc())
        )
    ]


@router.post("")
def create(body: dict[str, Any], request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = WorkflowService(db, ctx).create(body, request.app.state.settings)
    db.commit()
    return result


@router.get("/{identifier}")
def detail(identifier: uuid.UUID, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    service = WorkflowService(db, ctx)
    return service.describe(service.get(identifier))
