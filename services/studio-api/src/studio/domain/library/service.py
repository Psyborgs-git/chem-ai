"""Owner-only library services shared by human UI and delegated agent tools.

Private content never enters the project outbox, generic artifact retrieval,
or task summaries. A project link cannot grant access to these records.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar, cast
from urllib.parse import unquote, urlsplit

from pydantic import ValidationError
from sqlalchemy import Select, Text, or_, select, update
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext
from studio.domain.library.contracts import Citation, CreateMemory, PageContent
from studio.domain.library.models import (
    LibraryFolder,
    LibrarySource,
    Notebook,
    NotebookPage,
    PageRevision,
    ResearchMemory,
)
from studio.domain.library.research import (
    MAX_DOWNLOAD_BYTES,
    Download,
    fetch_public,
    public_url,
    readable_text,
)
from studio.errors import DomainError, ErrorCode, not_found, revision_conflict

_T = TypeVar("_T", LibraryFolder, Notebook, NotebookPage, LibrarySource, ResearchMemory)
_MISSING = object()


def _id(value: uuid.UUID | str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise DomainError(ErrorCode.VALIDATION, "invalid library record identifier") from None


def _title(value: str, limit: int = 300) -> str:
    result = value.strip()
    if not result or len(result) > limit:
        raise DomainError(ErrorCode.VALIDATION, f"title must contain 1-{limit} characters")
    return result


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _content(value: dict[str, Any]) -> dict[str, Any]:
    try:
        return PageContent.model_validate(value).model_dump(by_alias=True)
    except ValidationError:
        raise DomainError(
            ErrorCode.VALIDATION, "notebook content does not match its schema"
        ) from None


class LibraryService:
    def __init__(
        self,
        db: Session,
        ctx: ServiceContext,
        *,
        vault_root: Path,
        downloads_root: Path | None = None,
    ) -> None:
        self.db, self.ctx = db, ctx
        self.vault_root = Path(vault_root).expanduser().resolve() / "private-library"
        configured = downloads_root or Path(
            os.environ.get(
                "STUDIO_RESEARCH_DOWNLOADS_ROOT",
                str(Path.home() / "Downloads" / "Chemistry Studio"),
            )
        )
        self.downloads_root = Path(configured).expanduser().resolve()

    @property
    def owner_downloads(self) -> Path:
        return self.downloads_root / str(self.ctx.workspace_id) / str(self.ctx.principal_id)

    def _scope(self, model: Any) -> Select[Any]:
        return select(model).where(
            model.workspace_id == self.ctx.workspace_id,
            model.owner_id == self.ctx.principal_id,
        )

    def _get(self, model: type[_T], ident: uuid.UUID | str, *, deleted: bool = False) -> _T:
        stmt = self._scope(model).where(model.id == _id(ident))
        if model in {NotebookPage, LibrarySource} and not deleted:
            stmt = stmt.where(model.deleted_at.is_(None))  # type: ignore[attr-defined]
        row = self.db.scalar(stmt)
        if row is None:
            raise not_found("private library record")
        if isinstance(row, LibrarySource):
            self._authorize_source(row)
        return cast(_T, row)

    def _authorize_source(self, row: LibrarySource) -> None:
        from studio.domain.library.artifacts import authorize_retained_artifact

        authorize_retained_artifact(self.db, self.ctx, row.citation or {})

    def _source_readable(self, row: LibrarySource) -> bool:
        from studio.domain.library.artifacts import authorize_retained_artifact

        artifact = authorize_retained_artifact(self.db, self.ctx, row.citation or {})
        rights = (
            (artifact.rights or {})
            if artifact is not None
            else (row.citation or {}).get("rights", {})
        )
        return rights.get("extraction") != "denied"

    def _authorize_page_sources(self, row: NotebookPage, *, training: bool = False) -> None:
        from studio.domain.library.artifacts import authorize_retained_artifact

        for citation in row.citations:
            if not citation.get("sourceId"):
                continue
            source = self._get(LibrarySource, citation["sourceId"])
            if not self._source_readable(source):
                raise DomainError(
                    ErrorCode.FORBIDDEN, "current source rights restrict extracted content"
                )
            artifact = authorize_retained_artifact(self.db, self.ctx, source.citation or {})
            if (
                training
                and artifact is not None
                and (artifact.rights or {}).get("training") != "allowed"
            ):
                raise DomainError(
                    ErrorCode.DATA_RIGHTS_UNKNOWN, "cited source is not approved for training"
                )

    def _new(self) -> dict[str, Any]:
        return {"workspace_id": self.ctx.workspace_id, "owner_id": self.ctx.principal_id}

    def _change(self, row: _T, expected: int, **values: Any) -> None:
        if expected < 1:
            raise DomainError(ErrorCode.VALIDATION, "expectedRevision must be positive")
        model = type(row)
        changed = self.db.scalar(
            update(model)
            .where(
                model.id == row.id,
                model.workspace_id == self.ctx.workspace_id,
                model.owner_id == self.ctx.principal_id,
                model.version == expected,
            )
            .values(**values, version=expected + 1, updated_at=datetime.now(UTC))
            .returning(model.id)
        )
        if changed is None:
            raise revision_conflict("private library record")
        self.db.refresh(row)

    def _record(self, row: Any) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": str(row.id),
            "revision": row.version,
            "createdAt": _iso(row.created_at),
            "updatedAt": _iso(row.updated_at),
        }
        if isinstance(row, LibraryFolder):
            result.update(name=row.name, parentId=str(row.parent_id) if row.parent_id else None)
        elif isinstance(row, Notebook):
            result.update(
                title=row.title,
                folderId=str(row.folder_id) if row.folder_id else None,
                aiEnabled=row.ai_enabled,
                trainingEnabled=row.training_enabled,
            )
        elif isinstance(row, NotebookPage):
            result.update(
                title=row.title,
                notebookId=str(row.notebook_id),
                kind=row.kind,
                content=row.content,
                citations=row.citations,
                deletedAt=_iso(row.deleted_at),
            )
        elif isinstance(row, ResearchMemory):
            result.update(
                title=row.title,
                body=row.body,
                sourceRefs=row.source_refs,
                status=row.status,
                generator=row.generator,
            )
        elif isinstance(row, LibrarySource):
            result.update(
                title=row.title,
                url=row.url,
                sourceUrl=row.url,
                mediaType=row.media_type,
                byteSize=row.byte_size,
                checksum=row.checksum,
                citation=row.citation,
                archiveStatus=row.archive_status,
                downloadName=row.download_name,
                originalName=row.download_name,
                originalDownloadUrl=f"/api/library/sources/{row.id}/content?format=original",
                textDownloadUrl=f"/api/library/sources/{row.id}/content?format=text",
                metadataDownloadUrl=f"/api/library/sources/{row.id}/content?format=metadata",
                downloadDirectory=str(self.owner_downloads / str(row.id)),
                extractionStatus="extracted" if row.extracted_text else "no_text",
                deletedAt=_iso(row.deleted_at),
            )
        return result

    def list_all(self, *, for_agent: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "downloadsRoot": str(self.owner_downloads),
            "ownerKey": f"{self.ctx.workspace_id}:{self.ctx.principal_id}",
        }
        for key, model in (
            ("folders", LibraryFolder),
            ("notebooks", Notebook),
            ("pages", NotebookPage),
            ("memory", ResearchMemory),
            ("sources", LibrarySource),
        ):
            stmt = self._scope(model).order_by(model.updated_at.desc())
            if model in {NotebookPage, LibrarySource}:
                stmt = stmt.where(model.deleted_at.is_(None))
            if model is ResearchMemory:
                stmt = stmt.where(ResearchMemory.status != "forgotten")
            rows = list(self.db.scalars(stmt))
            if model is LibrarySource:
                visible = []
                for row in rows:
                    try:
                        self._authorize_source(row)
                        visible.append(row)
                    except DomainError:
                        continue
                rows = visible
            if for_agent and model is Notebook:
                rows = [row for row in rows if row.ai_enabled]
            if for_agent and model is NotebookPage:
                visible = []
                for row in rows:
                    try:
                        if self._get(Notebook, row.notebook_id).ai_enabled:
                            self._authorize_page_sources(row)
                            visible.append(row)
                    except DomainError:
                        continue
                rows = visible
            if for_agent and model is ResearchMemory:
                result[key] = self.active_memory()
            else:
                result[key] = [self._record(row) for row in rows]
        if not for_agent:
            result["trash"] = [
                self._record(row)
                for row in self.db.scalars(
                    self._scope(NotebookPage)
                    .where(NotebookPage.deleted_at.is_not(None))
                    .order_by(NotebookPage.updated_at.desc())
                )
            ]
        return result

    def create_folder(self, name: str, parent_id: uuid.UUID | str | None = None) -> dict[str, Any]:
        parent = self._get(LibraryFolder, parent_id) if parent_id else None
        row = LibraryFolder(
            **self._new(), name=_title(name, 200), parent_id=parent.id if parent else None
        )
        self.db.add(row)
        self.db.flush()
        return self._record(row)

    def update_folder(
        self,
        ident: uuid.UUID | str,
        expected_revision: int,
        *,
        name: str | None = None,
        parent_id: Any = _MISSING,
    ) -> dict[str, Any]:
        row = self._get(LibraryFolder, ident)
        values: dict[str, Any] = {}
        if name is not None:
            values["name"] = _title(name, 200)
        if parent_id is not _MISSING:
            parent = self._get(LibraryFolder, parent_id) if parent_id else None
            current = parent
            seen = {row.id}
            while current:
                if current.id in seen:
                    raise DomainError(ErrorCode.VALIDATION, "folder move would create a cycle")
                seen.add(current.id)
                current = self._get(LibraryFolder, current.parent_id) if current.parent_id else None
            values["parent_id"] = parent.id if parent else None
        self._change(row, expected_revision, **values)
        return self._record(row)

    def delete_folder(self, ident: uuid.UUID | str, expected_revision: int) -> dict[str, bool]:
        row = self._get(LibraryFolder, ident)
        if self.db.scalar(
            self._scope(Notebook).where(Notebook.folder_id == row.id).limit(1)
        ) or self.db.scalar(
            self._scope(LibraryFolder).where(LibraryFolder.parent_id == row.id).limit(1)
        ):
            raise DomainError(ErrorCode.CONFLICT, "move this folder's contents before deleting it")
        self._change(row, expected_revision)
        self.db.delete(row)
        return {"deleted": True}

    def create_notebook(
        self, title: str, folder_id: uuid.UUID | str | None = None
    ) -> dict[str, Any]:
        folder = self._get(LibraryFolder, folder_id) if folder_id else None
        row = Notebook(**self._new(), title=_title(title), folder_id=folder.id if folder else None)
        self.db.add(row)
        self.db.flush()
        return self._record(row)

    def update_notebook(
        self,
        ident: uuid.UUID | str,
        expected_revision: int,
        *,
        title: str | None = None,
        folder_id: Any = _MISSING,
        ai_enabled: bool | None = None,
        training_enabled: bool | None = None,
    ) -> dict[str, Any]:
        row = self._get(Notebook, ident)
        values: dict[str, Any] = {}
        if title is not None:
            values["title"] = _title(title)
        if folder_id is not _MISSING:
            folder = self._get(LibraryFolder, folder_id) if folder_id else None
            values["folder_id"] = folder.id if folder else None
        if ai_enabled is not None:
            values["ai_enabled"] = ai_enabled
        if training_enabled is not None:
            values["training_enabled"] = training_enabled
        self._change(row, expected_revision, **values)
        if ai_enabled is False:
            for page in self.db.scalars(
                self._scope(NotebookPage).where(NotebookPage.notebook_id == row.id)
            ):
                self._invalidate("page", page.id)
        return self._record(row)

    def delete_notebook(self, ident: uuid.UUID | str, expected_revision: int) -> dict[str, bool]:
        row = self._get(Notebook, ident)
        if self.db.scalar(
            self._scope(NotebookPage)
            .where(NotebookPage.notebook_id == row.id)
            .limit(1)
        ):
            raise DomainError(
                ErrorCode.CONFLICT,
                "notebook contains saved or recoverable trashed pages; keep it to preserve history",
            )
        self._change(row, expected_revision)
        self.db.delete(row)
        return {"deleted": True}

    def _citations(self, citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(citations) > 100:
            raise DomainError(ErrorCode.VALIDATION, "too many citations on one page")
        result: list[dict[str, Any]] = []
        for item in citations:
            try:
                parsed = Citation.model_validate(item)
            except ValidationError:
                raise DomainError(ErrorCode.VALIDATION, "invalid notebook citation") from None
            value = parsed.model_dump(by_alias=True, exclude_none=True)
            if parsed.source_id:
                source = self._get(LibrarySource, parsed.source_id)
                value.update(
                    sourceId=str(source.id), url=source.url, archiveStatus=source.archive_status
                )
            elif parsed.artifact_id:
                from studio.config.settings import Settings
                from studio.domain.library.artifacts import archive_artifact

                source_record = archive_artifact(
                    self.db,
                    self.ctx,
                    Settings(vault_root=self.vault_root.parent),
                    parsed.artifact_id,
                )
                value.update(
                    sourceId=source_record["id"],
                    url=source_record["url"],
                    archiveStatus=source_record["archiveStatus"],
                )
            elif parsed.url:
                # Accessible cited originals are archived, not just linked. A failed
                # network fetch must not discard a person's notebook edits.
                public_url(parsed.url)
                try:
                    source_record = self.fetch_source(parsed.url, title=parsed.title)
                    value.update(
                        sourceId=source_record["id"], archiveStatus=source_record["archiveStatus"]
                    )
                except DomainError as exc:
                    if exc.code == ErrorCode.FORBIDDEN:
                        raise
                    value["archiveStatus"] = "unavailable"
            else:
                raise DomainError(
                    ErrorCode.VALIDATION, "a citation needs a sourceId, artifactId or URL"
                )
            result.append(value)
        return result

    def create_page(
        self,
        notebook_id: uuid.UUID | str,
        title: str,
        kind: str = "note",
        content: dict[str, Any] | None = None,
        citations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        notebook = self._get(Notebook, notebook_id)
        if kind not in {"note", "recipe", "formula", "smiles"}:
            raise DomainError(ErrorCode.VALIDATION, "unsupported notebook page kind")
        row = NotebookPage(
            **self._new(),
            notebook_id=notebook.id,
            title=_title(title),
            kind=kind,
            content=_content(content or {}),
            citations=self._citations(citations or []),
        )
        self.db.add(row)
        self.db.flush()
        self._revision(row)
        return self._record(row)

    def _revision(self, row: NotebookPage) -> None:
        self.db.add(
            PageRevision(
                **self._new(),
                page_id=row.id,
                revision=row.version,
                title=row.title,
                content=row.content,
                citations=row.citations,
            )
        )
        self.db.flush()

    def get_page(self, ident: uuid.UUID | str, *, for_agent: bool = False) -> dict[str, Any]:
        row = self._get(NotebookPage, ident)
        if for_agent and not self._get(Notebook, row.notebook_id).ai_enabled:
            raise not_found("private library record")
        if for_agent:
            self._authorize_page_sources(row)
        result = self._record(row)
        if for_agent:
            return result
        rows = self.db.scalars(
            select(PageRevision)
            .where(
                PageRevision.workspace_id == self.ctx.workspace_id,
                PageRevision.owner_id == self.ctx.principal_id,
                PageRevision.page_id == row.id,
            )
            .order_by(PageRevision.revision.desc())
        )
        result["revisions"] = [
            {
                "id": str(r.id),
                "revision": r.revision,
                "title": r.title,
                "content": r.content,
                "citations": r.citations,
                "createdAt": _iso(r.created_at),
            }
            for r in rows
        ]
        return result

    def update_page(
        self,
        ident: uuid.UUID | str,
        expected_revision: int,
        *,
        title: str | None = None,
        content: dict[str, Any] | None = None,
        citations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        row = self._get(NotebookPage, ident)
        if row.version != expected_revision:
            raise revision_conflict("notebook page")
        values: dict[str, Any] = {}
        if title is not None:
            values["title"] = _title(title)
        if content is not None:
            values["content"] = _content(content)
        if citations is not None:
            values["citations"] = self._citations(citations)
        self._change(row, expected_revision, **values)
        self._revision(row)
        self._invalidate("page", row.id)
        return self._record(row)

    def export_training_page(
        self, ident: uuid.UUID | str, *, for_agent: bool = False
    ) -> dict[str, Any]:
        """Export only the current owner-authored revision, never revision history.

        Citation metadata is retained as provenance; this does not grant rights to
        use a cited third-party document as additional training material.
        """
        row = self._get(NotebookPage, ident)
        notebook = self._get(Notebook, row.notebook_id)
        if not notebook.training_enabled:
            raise DomainError(ErrorCode.FORBIDDEN, "training is disabled for this notebook")
        if for_agent and not notebook.ai_enabled:
            raise not_found("private library record")
        self._authorize_page_sources(row, training=True)
        content = row.content
        parts = [content.get("markdown", "")]
        if content.get("ingredients"):
            ingredients = [
                f"- {item['name']}: {item.get('amount', '')} {item.get('unit', '')}".rstrip()
                for item in content["ingredients"]
            ]
            parts.append("Ingredients\n" + "\n".join(ingredients))
        if content.get("steps"):
            parts.append(
                "Method\n"
                + "\n".join(f"{number}. {step}" for number, step in enumerate(content["steps"], 1))
            )
        if content.get("latex"):
            parts.append("Formula: " + content["latex"])
        if content.get("smiles"):
            parts.append("SMILES: " + content["smiles"])
        if content.get("variables"):
            parts.append("Variables: " + json.dumps(content["variables"], ensure_ascii=False))
        body = "\n\n".join(part for part in parts if part).strip()
        if not body:
            raise DomainError(ErrorCode.VALIDATION, "the notebook page has no training content")
        return {
            "id": str(row.id),
            "pageId": str(row.id),
            "notebookId": str(notebook.id),
            "revision": row.version,
            "title": row.title,
            "body": body,
            "kind": row.kind,
            "dataKind": "user_authored",
            "citations": row.citations,
        }

    def delete_page(self, ident: uuid.UUID | str, expected_revision: int) -> dict[str, bool]:
        row = self._get(NotebookPage, ident)
        self._change(row, expected_revision, deleted_at=datetime.now(UTC))
        self._invalidate("page", row.id)
        return {"deleted": True}

    def restore_page(self, ident: uuid.UUID | str, expected_revision: int) -> dict[str, Any]:
        row = self._get(NotebookPage, ident, deleted=True)
        self._get(Notebook, row.notebook_id)
        if row.deleted_at is None:
            raise DomainError(ErrorCode.CONFLICT, "the page is not in trash")
        self._change(row, expected_revision, deleted_at=None)
        self._revision(row)
        return self._record(row)

    def _invalidate(self, kind: str, ident: uuid.UUID) -> None:
        for memory in self.db.scalars(
            self._scope(ResearchMemory).where(ResearchMemory.status == "active")
        ):
            if any(
                ref.get("kind") == kind and ref.get("id") == str(ident)
                for ref in memory.source_refs
            ):
                memory.status = "stale"
                memory.version += 1
        self.db.flush()

    def save_memory(
        self, title: str, body: str, source_refs: list[dict[str, Any]], generator: str = "user"
    ) -> dict[str, Any]:
        try:
            data = CreateMemory(
                title=title, body=body, source_refs=source_refs, generator=generator
            )
        except ValidationError:
            raise DomainError(
                ErrorCode.VALIDATION, "memory requires a title, body and source references"
            ) from None
        refs = []
        for ref in data.source_refs:
            model: Any = NotebookPage if ref.kind == "page" else LibrarySource
            source = self._get(model, ref.id)
            if (
                isinstance(source, NotebookPage)
                and not self._get(Notebook, source.notebook_id).ai_enabled
            ):
                raise DomainError(ErrorCode.FORBIDDEN, "AI access is disabled for this notebook")
            if isinstance(source, NotebookPage):
                self._authorize_page_sources(source)
            elif not self._source_readable(source):
                raise DomainError(
                    ErrorCode.FORBIDDEN, "current source rights restrict extracted content"
                )
            if ref.revision is not None and ref.revision != source.version:
                raise revision_conflict("memory source")
            refs.append({"kind": ref.kind, "id": str(source.id), "revision": source.version})
        row = ResearchMemory(
            **self._new(),
            title=_title(data.title),
            body=data.body.strip(),
            source_refs=refs,
            generator=data.generator,
            status="active",
        )
        self.db.add(row)
        self.db.flush()
        return self._record(row)

    def forget_memory(self, ident: uuid.UUID | str) -> dict[str, bool]:
        row = self._get(ResearchMemory, ident)
        # Actual memory content is removed; source notes remain under owner control.
        row.body, row.title, row.source_refs, row.status = "", "Forgotten memory", [], "forgotten"
        row.version += 1
        self.db.flush()
        return {"forgotten": True}

    def active_memory(self) -> list[dict[str, Any]]:
        result = []
        for row in self.db.scalars(
            self._scope(ResearchMemory).where(ResearchMemory.status == "active")
        ):
            stale = False
            for ref in row.source_refs:
                try:
                    model: Any = NotebookPage if ref["kind"] == "page" else LibrarySource
                    source = self._get(model, ref["id"])
                    if source.version != ref["revision"]:
                        stale = True
                    if (
                        isinstance(source, NotebookPage)
                        and not self._get(Notebook, source.notebook_id).ai_enabled
                    ):
                        stale = True
                    if isinstance(source, NotebookPage):
                        self._authorize_page_sources(source)
                    elif not self._source_readable(source):
                        stale = True
                except (DomainError, KeyError):
                    stale = True
            if stale:
                row.status = "stale"
            else:
                result.append(self._record(row))
        return result

    def search(
        self, query: str, limit: int = 20, *, for_agent: bool = False
    ) -> list[dict[str, Any]]:
        query = query.strip()
        if not query or len(query) > 500:
            raise DomainError(ErrorCode.VALIDATION, "search needs 1-500 characters")
        limit = max(1, min(limit, 50))
        result = []
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        page_stmt = (
            self._scope(NotebookPage)
            .where(
                NotebookPage.deleted_at.is_(None),
                or_(
                    NotebookPage.title.ilike(pattern, escape="\\"),
                    NotebookPage.content.cast(Text).ilike(pattern, escape="\\"),
                ),
            )
            .order_by(NotebookPage.updated_at.desc())
            .limit(limit)
        )
        for row in self.db.scalars(page_stmt):
            if for_agent and not self._get(Notebook, row.notebook_id).ai_enabled:
                continue
            if for_agent:
                try:
                    self._authorize_page_sources(row)
                except DomainError:
                    continue
            result.append(
                {
                    "kind": "page",
                    "id": str(row.id),
                    "title": row.title,
                    "revision": row.version,
                    "notebookId": str(row.notebook_id),
                    "snippet": json.dumps(row.content, ensure_ascii=False)[:1200],
                }
            )
        for row in self.db.scalars(
            self._scope(LibrarySource)
            .where(
                LibrarySource.deleted_at.is_(None),
                or_(
                    LibrarySource.title.ilike(pattern, escape="\\"),
                    LibrarySource.extracted_text.ilike(pattern, escape="\\"),
                ),
            )
            .order_by(LibrarySource.updated_at.desc())
            .limit(limit)
        ):
            try:
                if not self._source_readable(row):
                    continue
            except DomainError:
                continue
            result.append(
                {
                    "kind": "source",
                    "id": str(row.id),
                    "title": row.title,
                    "revision": row.version,
                    "url": row.url,
                    "snippet": row.extracted_text[:1200],
                }
            )
        for memory in self.active_memory():
            if query.casefold() in (memory["title"] + memory["body"]).casefold():
                result.append({"kind": "memory", **memory, "snippet": memory["body"][:1200]})
        return result[:limit]

    def _folder(self, root: Path, ident: uuid.UUID) -> Path:
        target = root / str(self.ctx.workspace_id) / str(self.ctx.principal_id) / str(ident)
        if not target.resolve().is_relative_to(root.resolve()):
            raise DomainError(ErrorCode.FORBIDDEN, "archive directory escapes its configured root")
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not target.resolve().is_relative_to(root.resolve()):
            raise DomainError(ErrorCode.FORBIDDEN, "archive directory escapes its configured root")
        target.chmod(0o700)
        return target

    def _preflight_storage(self, byte_size: int) -> None:
        required = 2 * byte_size + 64 * 1024 * 1024
        for root in (self.vault_root, self.downloads_root):
            probe = root
            while not probe.exists() and probe.parent != probe:
                probe = probe.parent
            try:
                available = shutil.disk_usage(probe).free
            except OSError:
                raise DomainError(
                    ErrorCode.RESOURCE_UNAVAILABLE,
                    "research storage could not be checked; retry when storage is available",
                ) from None
            if available < required:
                raise DomainError(
                    ErrorCode.RESOURCE_UNAVAILABLE,
                    "research downloads are paused: free storage for two file copies plus "
                    "64 MiB, then retry; existing research files are preserved",
                )

    @staticmethod
    def _storage_failure(exc: OSError) -> DomainError:
        if exc.errno in {errno.ENOSPC, errno.EDQUOT}:
            return DomainError(
                ErrorCode.RESOURCE_UNAVAILABLE,
                "research storage is full; free space and retry. "
                "Existing research files are preserved",
            )
        return DomainError(
            ErrorCode.RESOURCE_UNAVAILABLE,
            "the protected research archive could not be written; check storage access and retry",
        )

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def fetch_source(
        self,
        url: str,
        *,
        title: str | None = None,
        citation: dict[str, Any] | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        normalized = public_url(url)
        url_hash = hashlib.sha256(normalized.encode()).hexdigest()
        previous = self.db.scalar(
            self._scope(LibrarySource)
            .where(LibrarySource.url_hash == url_hash, LibrarySource.deleted_at.is_(None))
            .order_by(LibrarySource.created_at.desc())
            .limit(1)
        )
        if previous and not force_refresh:
            return self.get_source(previous.id)
        downloaded = fetch_public(normalized)
        result = self.archive_download(
            downloaded, title=title, citation=citation, url_hash=url_hash, requested_url=normalized
        )
        if previous and result["id"] != str(previous.id):
            self._invalidate("source", previous.id)
        return result

    def archive_download(
        self,
        downloaded: Download,
        *,
        title: str | None = None,
        citation: dict[str, Any] | None = None,
        url_hash: str | None = None,
        requested_url: str | None = None,
        original_name: str | None = None,
    ) -> dict[str, Any]:
        if len(downloaded.body) > MAX_DOWNLOAD_BYTES:
            raise DomainError(ErrorCode.VALIDATION, "resource exceeds the download size limit")
        citation = citation or {}
        rights = citation.get("rights") or {
            "retrieval": "allowed",
            "training": "unknown",
            "export": "unknown",
        }
        if not isinstance(rights, dict):
            raise DomainError(ErrorCode.VALIDATION, "source rights must be a JSON object")
        checksum = hashlib.sha256(downloaded.body).hexdigest()
        url_hash = url_hash or hashlib.sha256(downloaded.url.encode()).hexdigest()
        previous = self.db.scalar(
            self._scope(LibrarySource)
            .where(
                LibrarySource.url_hash == url_hash,
                LibrarySource.checksum == checksum,
                LibrarySource.deleted_at.is_(None),
            )
            .order_by(LibrarySource.created_at.desc())
            .limit(1)
        )
        if previous:
            return self.get_source(previous.id)
        self._preflight_storage(len(downloaded.body))
        text = "" if rights.get("extraction") == "denied" else readable_text(downloaded)
        ident = uuid.uuid4()
        suffix = {
            "application/pdf": ".pdf",
            "text/html": ".html",
            "application/json": ".json",
            "text/plain": ".txt",
            "text/csv": ".csv",
            "application/xml": ".xml",
        }.get(downloaded.media_type, ".bin")
        original_name = (
            original_name or unquote(Path(urlsplit(downloaded.url).path).name) or "resource"
        )
        original_suffix = Path(original_name).suffix.lower()
        if (suffix == ".bin" or downloaded.media_type == "text/plain") and original_suffix in {
            ".sdf",
            ".mol",
            ".mol2",
            ".smi",
            ".smiles",
            ".jsonl",
            ".tsv",
            ".xlsx",
            ".docx",
            ".pdb",
            ".cif",
            ".md",
            ".bib",
            ".ris",
            ".csv",
            ".txt",
            ".json",
        }:
            suffix = original_suffix
        safe_name = (
            re.sub(r"[^A-Za-z0-9._-]+", "-", Path(original_name).stem)[:70].strip(".-")
            or "resource"
        )
        name = safe_name + suffix
        source_title = _title(
            title or original_name or urlsplit(downloaded.url).hostname or "Resource", 500
        )
        metadata = {
            "id": str(ident),
            "title": source_title,
            "sourceUrl": downloaded.url,
            "requestedUrl": requested_url or downloaded.url,
            "checksum": checksum,
            "byteSize": len(downloaded.body),
            "mediaType": downloaded.media_type,
            "downloadedAt": datetime.now(UTC).isoformat(),
            "citation": citation or {},
            "extractionStatus": "extracted" if text else "no_text",
            "rights": rights,
        }
        readable = f"# {source_title}\n\nSource: {downloaded.url}\n\nSHA-256: {checksum}\n\n" + (
            text or "No readable text was extracted. The original file is preserved."
        )
        vault = (
            self.vault_root / str(self.ctx.workspace_id) / str(self.ctx.principal_id) / str(ident)
        )
        copies = (
            self.downloads_root
            / str(self.ctx.workspace_id)
            / str(self.ctx.principal_id)
            / str(ident)
        )
        try:
            vault = self._folder(self.vault_root, ident)
            self._write(vault / name, downloaded.body)
            self._write(vault / "readable.md", readable.encode())
            self._write(
                vault / "metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2).encode()
            )
        except OSError as exc:
            shutil.rmtree(vault, ignore_errors=True)
            raise self._storage_failure(exc) from None
        archive_status = "saved"
        try:
            copies = self._folder(self.downloads_root, ident)
            self._write(copies / name, downloaded.body)
            self._write(copies / "readable.md", readable.encode())
            self._write(
                copies / "metadata.json",
                json.dumps(metadata, ensure_ascii=False, indent=2).encode(),
            )
        except OSError as exc:
            shutil.rmtree(copies, ignore_errors=True)
            if exc.errno in {errno.ENOSPC, errno.EDQUOT}:
                shutil.rmtree(vault, ignore_errors=True)
                raise self._storage_failure(exc) from None
            # The protected original remains available through authenticated downloads.
            archive_status = "copy_pending"
        rel = Path(str(self.ctx.workspace_id)) / str(self.ctx.principal_id) / str(ident)
        row = LibrarySource(
            **self._new(),
            id=ident,
            title=source_title,
            url=downloaded.url,
            url_hash=url_hash,
            media_type=downloaded.media_type,
            checksum=checksum,
            byte_size=len(downloaded.body),
            original_key=str(rel / name),
            text_key=str(rel / "readable.md"),
            extracted_text=text,
            citation=citation or {},
            archive_status=archive_status,
            download_name=name,
        )
        self.db.add(row)
        try:
            self.db.flush()
        except Exception:
            shutil.rmtree(vault, ignore_errors=True)
            shutil.rmtree(copies, ignore_errors=True)
            raise
        return self.get_source(row.id)

    def get_source(self, ident: uuid.UUID | str) -> dict[str, Any]:
        row = self._get(LibrarySource, ident)
        readable = self._source_readable(row)
        return {
            **self._record(row),
            "extractedText": row.extracted_text if readable else "",
            "extractionStatus": ("extracted" if row.extracted_text else "no_text")
            if readable
            else "restricted",
        }

    def source_file(
        self, ident: uuid.UUID | str, format: str = "original"
    ) -> tuple[Path, str, str]:
        row = self._get(LibrarySource, ident)
        if format not in {"original", "text", "metadata"}:
            raise DomainError(ErrorCode.VALIDATION, "unknown source download format")
        if format == "text" and not self._source_readable(row):
            raise DomainError(
                ErrorCode.FORBIDDEN, "current source rights restrict extracted content"
            )
        key = row.original_key if format == "original" else row.text_key
        if format == "metadata":
            key = str(Path(row.text_key).with_name("metadata.json"))
        path = (self.vault_root / key).resolve()
        owner = (
            self.vault_root / str(self.ctx.workspace_id) / str(self.ctx.principal_id)
        ).resolve()
        if (
            not owner.is_relative_to(self.vault_root)
            or not path.is_relative_to(owner)
            or not path.is_file()
        ):
            raise not_found("archived resource")
        media_type = (
            row.media_type
            if format == "original"
            else "application/json"
            if format == "metadata"
            else "text/markdown"
        )
        return path, media_type, row.download_name if format == "original" else path.name

    def delete_source(self, ident: uuid.UUID | str, expected_revision: int) -> dict[str, bool]:
        row = self._get(LibrarySource, ident)
        self._change(row, expected_revision, deleted_at=datetime.now(UTC))
        self._invalidate("source", row.id)
        return {"deleted": True}
