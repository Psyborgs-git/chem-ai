"""Artifact transfer endpoints (upload/download streaming).

These are the deliberate transport exceptions in handoff §8.1 — not a
second CRUD API. Every handler resolves a ServiceContext first and the
service layer re-checks capabilities; the transport only streams bytes.
No filesystem path, SQL trace, or original filename crosses the wire.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

from chem_studio_policy.capabilities import CAP_READ_PROJECT
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from studio.api.deps import Ctx, DbSession
from studio.config.settings import Settings
from studio.domain.evidence.archive import ArchiveLimits
from studio.domain.evidence.service import ArtifactService
from studio.domain.evidence.vault import Vault
from studio.errors import DomainError

transfer_router = APIRouter(tags=["artifacts"])

_CHUNK = 1024 * 1024


def _service(request: Request, db: Session) -> ArtifactService:
    settings: Settings = request.app.state.settings
    return ArtifactService(
        db,
        Vault(settings.vault_root),
        max_bytes=settings.artifact_max_bytes,
        archive_limits=ArchiveLimits(
            max_members=settings.artifact_max_archive_members,
            max_decompressed_bytes=settings.artifact_max_decompressed_bytes,
            max_compression_ratio=float(settings.artifact_max_compression_ratio),
        ),
    )


class InitiateUploadRequest(BaseModel):
    original_name: str = Field(min_length=1, max_length=500)
    media_type: str = Field(min_length=1, max_length=200)
    declared_size: int | None = Field(default=None, ge=0)
    declared_checksum: str | None = Field(default=None, min_length=64, max_length=64)
    access_scope: uuid.UUID | None = None


@transfer_router.post("/uploads")
def initiate_upload(
    body: InitiateUploadRequest, request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    svc = _service(request, db)
    artifact = svc.initiate(
        ctx,
        original_name=body.original_name,
        media_type=body.media_type,
        declared_size=body.declared_size,
        declared_checksum=body.declared_checksum,
        access_scope=body.access_scope,
    )
    db.commit()
    return {
        "artifactId": str(artifact.id),
        "uploadState": artifact.upload_state,
        "maxBytes": svc.max_bytes,
    }


@transfer_router.put("/uploads/{artifact_id}/content")
async def stream_content(
    artifact_id: uuid.UUID, request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    """Append request-body bytes to staging (streaming, size-capped)."""
    svc = _service(request, db)
    staging = svc.staging_path(ctx, artifact_id)
    written = svc.vault.staging_size(staging)
    async for chunk in request.stream():
        svc.check_size_budget(written, len(chunk))
        svc.vault.append_bytes(staging, chunk)
        written += len(chunk)
    return {"bytesReceived": written}


class FinishUploadRequest(BaseModel):
    checksum: str | None = Field(default=None, min_length=64, max_length=64)


@transfer_router.post("/uploads/{artifact_id}/finish")
def finish_upload(
    artifact_id: uuid.UUID,
    request: Request,
    db: DbSession,
    ctx: Ctx,
    body: FinishUploadRequest | None = None,
) -> dict[str, Any]:
    svc = _service(request, db)
    try:
        artifact = svc.finish(ctx, artifact_id, checksum=(body.checksum if body else None))
    except DomainError:
        # Persist aborted/rejected markers — they are the audit trail.
        db.commit()
        raise
    db.commit()
    return {
        "artifactId": str(artifact.id),
        "uploadState": artifact.upload_state,
        "checksumSha256": artifact.checksum_sha256,
        "byteSize": artifact.byte_size,
        "reviewState": artifact.review_state,
    }


@transfer_router.post("/uploads/{artifact_id}/abort")
def abort_upload(
    artifact_id: uuid.UUID, request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    svc = _service(request, db)
    artifact = svc.abort(ctx, artifact_id)
    db.commit()
    return {"artifactId": str(artifact.id), "uploadState": artifact.upload_state}


@transfer_router.get("/{artifact_id}/content")
def download_content(
    artifact_id: uuid.UUID, request: Request, db: DbSession, ctx: Ctx
) -> StreamingResponse:
    svc = _service(request, db)
    artifact, blob = svc.open_download(ctx, artifact_id)

    def _iter() -> Iterator[bytes]:
        try:
            yield from iter(lambda: blob.read(_CHUNK), b"")
        finally:
            blob.close()

    # Opaque filename only — original_name stays private server-side.
    return StreamingResponse(
        _iter(),
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="artifact-{artifact.id}"',
            "X-Content-SHA256": artifact.checksum_sha256 or "",
            "Cache-Control": "private, no-store",
        },
    )


@transfer_router.get("/{artifact_id}")
def artifact_metadata(
    artifact_id: uuid.UUID, request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    svc = _service(request, db)
    artifact = svc.get(ctx, artifact_id)
    ctx.require(CAP_READ_PROJECT, artifact.access_scope)
    return {
        "artifactId": str(artifact.id),
        "mediaType": artifact.media_type,
        "byteSize": artifact.byte_size,
        "checksumSha256": artifact.checksum_sha256,
        "uploadState": artifact.upload_state,
        "reviewState": artifact.review_state,
        "classification": artifact.classification,
        "rights": artifact.rights,
    }
