"""Authenticated REST interface for private custom datasets and local training."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, Response

from studio.api.deps import Ctx, DbSession
from studio.domain.learning.workspace import LearningWorkspaceService
from studio.domain.learning.workspace_runtime.data import MAX_DATASET_BYTES
from studio.errors import DomainError, ErrorCode

router = APIRouter(prefix="/api/learning-workspace", tags=["learning-workspace"])


def _service(request: Request, db: Any, ctx: Any) -> LearningWorkspaceService:
    return LearningWorkspaceService(db, ctx, request.app.state.settings)


@router.get("/capabilities")
def capabilities(request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return _service(request, db, ctx).catalog()


@router.get("/datasets")
def datasets(request: Request, db: DbSession, ctx: Ctx) -> list[dict[str, Any]]:
    return _service(request, db, ctx).list_datasets()


@router.post("/datasets/import")
def import_dataset(
    payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).import_dataset(payload)
    db.commit()
    return result


@router.post("/datasets/upload")
async def upload_dataset(
    request: Request,
    db: DbSession,
    ctx: Ctx,
    file: Annotated[UploadFile, File()],
    metadata: str = Form("{}"),
) -> dict[str, Any]:
    content = await file.read(MAX_DATASET_BYTES + 1)
    if len(content) > MAX_DATASET_BYTES:
        raise DomainError(ErrorCode.VALIDATION, "Dataset exceeds the 20 MiB import limit")
    try:
        payload = json.loads(metadata)
        if not isinstance(payload, dict):
            raise ValueError("metadata must be a JSON object")
        payload["content"] = content.decode("utf-8-sig")
    except (ValueError, UnicodeDecodeError) as exc:
        raise DomainError(
            ErrorCode.VALIDATION, "Upload requires UTF-8 content and JSON metadata"
        ) from exc
    payload.setdefault("name", file.filename or "Imported dataset")
    payload.setdefault("format", (file.filename or "data.csv").rsplit(".", 1)[-1])
    result = _service(request, db, ctx).import_dataset(payload)
    db.commit()
    return result


@router.get("/datasets/{identifier}")
def dataset(identifier: str, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return _service(request, db, ctx).get_dataset(identifier)


@router.post("/datasets/{identifier}/freeze")
def freeze_dataset(identifier: str, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = _service(request, db, ctx).freeze_dataset(identifier)
    db.commit()
    return result


@router.get("/models")
def models(request: Request, db: DbSession, ctx: Ctx) -> list[dict[str, Any]]:
    return _service(request, db, ctx).list_models()


@router.post("/models")
def register_model(
    payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).register_model(payload)
    db.commit()
    return result


@router.post("/models/{identifier}/preview")
def preview(
    identifier: str, payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    return _service(request, db, ctx).preview_model(identifier, payload)


@router.get("/models/{identifier}")
def model(identifier: str, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return _service(request, db, ctx).get_model(identifier)


@router.post("/models/{identifier}/activate")
def activate_model(
    identifier: str, payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).activate_model(identifier, payload)
    db.commit()
    return result


@router.post("/models/{identifier}/chat")
def model_chat(
    identifier: str, payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    return _service(request, db, ctx).infer_model(
        identifier,
        payload.get("messages", []),
        payload.get("tools"),
        int(payload.get("maxTokens", 2048)),
    )


@router.get("/jobs")
def jobs(request: Request, db: DbSession, ctx: Ctx) -> list[dict[str, Any]]:
    return _service(request, db, ctx).list_jobs()


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


@router.get("/jobs/{identifier}/artifacts/{name:path}")
def artifact(identifier: str, name: str, request: Request, db: DbSession, ctx: Ctx) -> FileResponse:
    path = _service(request, db, ctx).artifact_path(identifier, name)
    return FileResponse(path, media_type="application/octet-stream", filename=path.name)


@router.post("/jobs/{identifier}/resume")
def resume(identifier: str, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = _service(request, db, ctx).resume_job(identifier)
    db.commit()
    return result


@router.post("/datasets/from-notebook")
def notebook_dataset(
    payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).import_notebook(payload)
    db.commit()
    return result


@router.post("/worker/lease")
def worker_lease(
    payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    from studio.domain.learning.workspace_runtime.remote import lease

    result = lease(_service(request, db, ctx), payload)
    db.commit()
    return result


@router.post("/worker/jobs/{identifier}/heartbeat")
def worker_heartbeat(
    identifier: str, payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    from studio.domain.learning.workspace_runtime.remote import heartbeat

    result = heartbeat(_service(request, db, ctx), identifier, payload)
    db.commit()
    return result


@router.get("/worker/jobs/{identifier}/checkpoint")
def worker_checkpoint(
    identifier: str, workerId: str, request: Request, db: DbSession, ctx: Ctx
) -> Response:
    from studio.domain.learning.workspace_runtime.remote import checkpoint_archive

    return Response(
        checkpoint_archive(_service(request, db, ctx), identifier, workerId),
        media_type="application/zip",
    )


@router.post("/worker/jobs/{identifier}/complete")
async def worker_complete(
    identifier: str,
    request: Request,
    db: DbSession,
    ctx: Ctx,
    file: Annotated[UploadFile, File()],
    metadata: str = Form(...),
) -> dict[str, Any]:
    from studio.domain.learning.workspace_runtime.remote import MAX_ARTIFACT_BYTES, complete

    content = await file.read(MAX_ARTIFACT_BYTES + 1)
    try:
        payload = json.loads(metadata)
        if not isinstance(payload, dict):
            raise ValueError("metadata must be a JSON object")
    except ValueError as exc:
        raise DomainError(ErrorCode.VALIDATION, "Invalid worker completion metadata") from exc
    result = complete(_service(request, db, ctx), identifier, payload, content)
    db.commit()
    return result


@router.get("/worker/jobs/{identifier}/model")
def worker_model(
    identifier: str, workerId: str, request: Request, db: DbSession, ctx: Ctx
) -> Response:
    from studio.domain.learning.workspace_runtime.remote import model_archive

    return Response(
        model_archive(_service(request, db, ctx), identifier, workerId),
        media_type="application/zip",
    )
