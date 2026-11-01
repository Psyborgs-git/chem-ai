"""Authenticated owner-private atomistic polymer MD pilot interface."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from studio.api.deps import Ctx, DbSession
from studio.domain.simulations.service import SimulationService

router = APIRouter(prefix="/api/simulations", tags=["simulations"])


def _service(request: Request, db: Any, ctx: Any) -> SimulationService:
    return SimulationService(db, ctx, request.app.state.settings)


@router.get("/capabilities")
def capabilities(request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return _service(request, db, ctx).capabilities()


@router.get("/jobs")
def jobs(
    request: Request, db: DbSession, ctx: Ctx, campaignId: str | None = None
) -> list[dict[str, Any]]:
    return _service(request, db, ctx).list_jobs(campaignId)


@router.post("/jobs")
def create_job(
    payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).create_job(payload)
    db.commit()
    return result


@router.get("/jobs/{identifier}")
def job(identifier: str, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return _service(request, db, ctx).get_job(identifier)


@router.post("/jobs/{identifier}/cancel")
def cancel(identifier: str, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = _service(request, db, ctx).cancel_job(identifier)
    db.commit()
    return result


@router.post("/jobs/{identifier}/resume")
def resume(identifier: str, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = _service(request, db, ctx).resume_job(identifier)
    db.commit()
    return result


@router.get("/jobs/{identifier}/artifacts/{name:path}")
def artifact(identifier: str, name: str, request: Request, db: DbSession, ctx: Ctx) -> FileResponse:
    path = _service(request, db, ctx).artifact_path(identifier, name)
    return FileResponse(path, media_type="application/octet-stream", filename=path.name)
