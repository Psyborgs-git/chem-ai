"""Authenticated JSON interface for the private research library."""

from __future__ import annotations

import subprocess
import sys
import uuid
from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse

from studio.api.deps import Ctx, DbSession
from studio.domain.library.contracts import (
    ArchiveArtifact,
    CreateFolder,
    CreateMemory,
    CreateNotebook,
    CreatePage,
    FetchSource,
    RestorePage,
    UpdateFolder,
    UpdateNotebook,
    UpdatePage,
)
from studio.domain.library.research import MAX_DOWNLOAD_BYTES, Download, search_resources
from studio.domain.library.service import LibraryService
from studio.errors import DomainError, ErrorCode


def _private_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"


library_router = APIRouter(
    prefix="/api/library", tags=["private-library"], dependencies=[Depends(_private_headers)]
)


def _service(request: Request, db: DbSession, ctx: Ctx) -> LibraryService:
    return LibraryService(db, ctx, vault_root=request.app.state.settings.vault_root)


@library_router.get("")
def library(request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = _service(request, db, ctx).list_all()
    db.commit()
    return result


@library_router.post("/folders", status_code=201)
def folder_create(data: CreateFolder, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = _service(request, db, ctx).create_folder(**data.model_dump())
    db.commit()
    return result


@library_router.patch("/folders/{ident}")
def folder_update(
    ident: uuid.UUID, data: UpdateFolder, request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).update_folder(ident, **data.model_dump(exclude_unset=True))
    db.commit()
    return result


@library_router.delete("/folders/{ident}")
def folder_delete(
    ident: uuid.UUID,
    request: Request,
    db: DbSession,
    ctx: Ctx,
    expected_revision: int = Query(alias="expectedRevision", ge=1),
) -> dict[str, bool]:
    result = _service(request, db, ctx).delete_folder(ident, expected_revision)
    db.commit()
    return result


@library_router.post("/notebooks", status_code=201)
def notebook_create(
    data: CreateNotebook, request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).create_notebook(**data.model_dump())
    db.commit()
    return result


@library_router.patch("/notebooks/{ident}")
def notebook_update(
    ident: uuid.UUID, data: UpdateNotebook, request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).update_notebook(
        ident, **data.model_dump(exclude_unset=True)
    )
    db.commit()
    return result


@library_router.delete("/notebooks/{ident}")
def notebook_delete(
    ident: uuid.UUID,
    request: Request,
    db: DbSession,
    ctx: Ctx,
    expected_revision: int = Query(alias="expectedRevision", ge=1),
) -> dict[str, bool]:
    result = _service(request, db, ctx).delete_notebook(ident, expected_revision)
    db.commit()
    return result


@library_router.post("/pages", status_code=201)
def page_create(data: CreatePage, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    values = data.model_dump(by_alias=False)
    result = _service(request, db, ctx).create_page(**values)
    db.commit()
    return result


@library_router.get("/pages/{ident}")
def page_get(ident: uuid.UUID, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return _service(request, db, ctx).get_page(ident)


@library_router.patch("/pages/{ident}")
def page_update(
    ident: uuid.UUID, data: UpdatePage, request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).update_page(ident, **data.model_dump(exclude_unset=True))
    db.commit()
    return result


@library_router.delete("/pages/{ident}")
def page_delete(
    ident: uuid.UUID,
    request: Request,
    db: DbSession,
    ctx: Ctx,
    expected_revision: int = Query(alias="expectedRevision", ge=1),
) -> dict[str, bool]:
    result = _service(request, db, ctx).delete_page(ident, expected_revision)
    db.commit()
    return result


@library_router.get("/search")
def search(
    request: Request,
    db: DbSession,
    ctx: Ctx,
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, Any]:
    result = _service(request, db, ctx).search(q, limit)
    db.commit()
    return {"results": result}


@library_router.post("/pages/{ident}/restore")
def page_restore(
    ident: uuid.UUID, data: RestorePage, request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).restore_page(ident, data.expected_revision)
    db.commit()
    return result


@library_router.post("/memory", status_code=201)
def memory_create(data: CreateMemory, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = _service(request, db, ctx).save_memory(**data.model_dump())
    db.commit()
    return result


@library_router.delete("/memory/{ident}")
def memory_forget(ident: uuid.UUID, request: Request, db: DbSession, ctx: Ctx) -> dict[str, bool]:
    result = _service(request, db, ctx).forget_memory(ident)
    db.commit()
    return result


@library_router.get("/research/search")
def research_search(
    ctx: Ctx,
    connector: Literal["openalex", "crossref", "pubchem", "web"],
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=10, ge=1, le=20),
) -> dict[str, Any]:
    return {"results": search_resources(connector, q, limit)}


@library_router.post("/sources/fetch", status_code=201)
def source_fetch(data: FetchSource, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = _service(request, db, ctx).fetch_source(**data.model_dump())
    db.commit()
    return result


@library_router.get("/sources/{ident}")
def source_get(ident: uuid.UUID, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return _service(request, db, ctx).get_source(ident)


@library_router.post("/sources/upload", status_code=201)
def source_upload(
    request: Request,
    db: DbSession,
    ctx: Ctx,
    file: Annotated[UploadFile, File()],
    title: str | None = Form(default=None, max_length=500),
) -> dict[str, Any]:
    body = file.file.read(MAX_DOWNLOAD_BYTES + 1)
    if not body or len(body) > MAX_DOWNLOAD_BYTES:
        raise DomainError(ErrorCode.VALIDATION, "upload a nonempty research file up to 24 MiB")
    media_type = (file.content_type or "application/octet-stream").split(";", 1)[0][:160]
    if body.startswith(b"%PDF-"):
        media_type = "application/pdf"
    name = (file.filename or "Research file")[:300]
    result = _service(request, db, ctx).archive_download(
        Download(f"upload:{uuid.uuid4()}", media_type, body),
        title=title or name,
        original_name=name,
        citation={
            "sourceKind": "private_upload",
            "originalName": name,
            "rights": {
                "retrieval": "allowed",
                "extraction": "allowed",
                "training": "unknown",
                "export": "unknown",
            },
        },
    )
    db.commit()
    return result


@library_router.post("/sources/artifact", status_code=201)
def source_artifact(
    data: ArchiveArtifact, request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    from studio.domain.library.artifacts import archive_artifact

    result = archive_artifact(db, ctx, request.app.state.settings, data.artifact_id)
    db.commit()
    return result


@library_router.get("/sources/{ident}/content")
def source_content(
    ident: uuid.UUID,
    request: Request,
    db: DbSession,
    ctx: Ctx,
    format: Literal["original", "text", "metadata"] = "original",
) -> FileResponse:
    path, media_type, filename = _service(request, db, ctx).source_file(ident, format)
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Cross-Origin-Resource-Policy": "same-origin",
        },
    )


@library_router.delete("/sources/{ident}")
def source_delete(
    ident: uuid.UUID,
    request: Request,
    db: DbSession,
    ctx: Ctx,
    expected_revision: int = Query(alias="expectedRevision", ge=1),
) -> dict[str, bool]:
    result = _service(request, db, ctx).delete_source(ident, expected_revision)
    db.commit()
    return result


@library_router.get("/structures/preview")
def structure_preview(
    ctx: Ctx, smiles: str = Query(min_length=1, max_length=10_000)
) -> dict[str, Any]:
    try:
        from rdkit import Chem
        from rdkit.Chem import Draw, rdMolDescriptors
    except ImportError:
        return {"smiles": smiles, "error": "RDKit is unavailable in this runtime"}
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return {"smiles": smiles, "error": "The supplied SMILES could not be parsed"}
    draw_svg: Callable[..., str] = Draw.MolsToGridImage
    return {
        "smiles": smiles,
        "canonicalSmiles": Chem.MolToSmiles(molecule),
        "formula": rdMolDescriptors.CalcMolFormula(molecule),
        "svg": draw_svg(
            [molecule], molsPerRow=1, subImgSize=(420, 300), useSVG=True
        ),
    }


@library_router.post("/downloads/reveal")
def downloads_reveal(request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    """Open only the authenticated owner's fixed research folder."""
    if sys.platform != "darwin":
        raise DomainError(ErrorCode.ENGINE_UNAVAILABLE, "folder reveal is available on macOS")
    service = _service(request, db, ctx)
    directory = service.owner_downloads
    try:
        if not directory.resolve().is_relative_to(service.downloads_root):
            raise DomainError(ErrorCode.FORBIDDEN, "download folder escapes its configured root")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory.chmod(0o700)
        subprocess.run(  # noqa: S603 - fixed executable and authenticated owner directory only
            ["/usr/bin/open", str(directory)], check=True, timeout=5, capture_output=True
        )
    except (OSError, subprocess.SubprocessError):
        raise DomainError(
            ErrorCode.RESOURCE_UNAVAILABLE, "the research folder could not be opened"
        ) from None
    return {"opened": True, "directory": str(directory)}
