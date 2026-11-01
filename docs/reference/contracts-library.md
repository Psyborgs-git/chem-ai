# Private library API — JSON contract details

These excerpts are generated from the implementation without importing it. They specify accepted fields, conditional validation, defaults and response construction for flexible JSON interfaces. They complement the endpoint prose; implementation expressions refer to the named source service rather than a live execution.

## downloads_reveal

Source: `services/studio-api/src/studio/api/library.py:downloads_reveal`.

```python
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
```

## folder_create

Source: `services/studio-api/src/studio/api/library.py:folder_create`.

```python
@library_router.post("/folders", status_code=201)
def folder_create(data: CreateFolder, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = _service(request, db, ctx).create_folder(**data.model_dump())
    db.commit()
    return result
```

## folder_delete

Source: `services/studio-api/src/studio/api/library.py:folder_delete`.

```python
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
```

## folder_update

Source: `services/studio-api/src/studio/api/library.py:folder_update`.

```python
@library_router.patch("/folders/{ident}")
def folder_update(
    ident: uuid.UUID, data: UpdateFolder, request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).update_folder(ident, **data.model_dump(exclude_unset=True))
    db.commit()
    return result
```

## library

Source: `services/studio-api/src/studio/api/library.py:library`.

```python
@library_router.get("")
def library(request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = _service(request, db, ctx).list_all()
    db.commit()
    return result
```

## memory_create

Source: `services/studio-api/src/studio/api/library.py:memory_create`.

```python
@library_router.post("/memory", status_code=201)
def memory_create(data: CreateMemory, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = _service(request, db, ctx).save_memory(**data.model_dump())
    db.commit()
    return result
```

## memory_forget

Source: `services/studio-api/src/studio/api/library.py:memory_forget`.

```python
@library_router.delete("/memory/{ident}")
def memory_forget(ident: uuid.UUID, request: Request, db: DbSession, ctx: Ctx) -> dict[str, bool]:
    result = _service(request, db, ctx).forget_memory(ident)
    db.commit()
    return result
```

## notebook_create

Source: `services/studio-api/src/studio/api/library.py:notebook_create`.

```python
@library_router.post("/notebooks", status_code=201)
def notebook_create(
    data: CreateNotebook, request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).create_notebook(**data.model_dump())
    db.commit()
    return result
```

## notebook_delete

Source: `services/studio-api/src/studio/api/library.py:notebook_delete`.

```python
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
```

## notebook_update

Source: `services/studio-api/src/studio/api/library.py:notebook_update`.

```python
@library_router.patch("/notebooks/{ident}")
def notebook_update(
    ident: uuid.UUID, data: UpdateNotebook, request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).update_notebook(
        ident, **data.model_dump(exclude_unset=True)
    )
    db.commit()
    return result
```

## page_create

Source: `services/studio-api/src/studio/api/library.py:page_create`.

```python
@library_router.post("/pages", status_code=201)
def page_create(data: CreatePage, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    values = data.model_dump(by_alias=False)
    result = _service(request, db, ctx).create_page(**values)
    db.commit()
    return result
```

## page_delete

Source: `services/studio-api/src/studio/api/library.py:page_delete`.

```python
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
```

## page_get

Source: `services/studio-api/src/studio/api/library.py:page_get`.

```python
@library_router.get("/pages/{ident}")
def page_get(ident: uuid.UUID, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return _service(request, db, ctx).get_page(ident)
```

## page_restore

Source: `services/studio-api/src/studio/api/library.py:page_restore`.

```python
@library_router.post("/pages/{ident}/restore")
def page_restore(
    ident: uuid.UUID, data: RestorePage, request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).restore_page(ident, data.expected_revision)
    db.commit()
    return result
```

## page_update

Source: `services/studio-api/src/studio/api/library.py:page_update`.

```python
@library_router.patch("/pages/{ident}")
def page_update(
    ident: uuid.UUID, data: UpdatePage, request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).update_page(ident, **data.model_dump(exclude_unset=True))
    db.commit()
    return result
```

## research_search

Source: `services/studio-api/src/studio/api/library.py:research_search`.

```python
@library_router.get("/research/search")
def research_search(
    ctx: Ctx,
    connector: Literal["openalex", "crossref", "pubchem", "web"],
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=10, ge=1, le=20),
) -> dict[str, Any]:
    return {"results": search_resources(connector, q, limit)}
```

## search

Source: `services/studio-api/src/studio/api/library.py:search`.

```python
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
```

## source_artifact

Source: `services/studio-api/src/studio/api/library.py:source_artifact`.

```python
@library_router.post("/sources/artifact", status_code=201)
def source_artifact(
    data: ArchiveArtifact, request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    from studio.domain.library.artifacts import archive_artifact

    result = archive_artifact(db, ctx, request.app.state.settings, data.artifact_id)
    db.commit()
    return result
```

## source_content

Source: `services/studio-api/src/studio/api/library.py:source_content`.

```python
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
```

## source_delete

Source: `services/studio-api/src/studio/api/library.py:source_delete`.

```python
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
```

## source_fetch

Source: `services/studio-api/src/studio/api/library.py:source_fetch`.

```python
@library_router.post("/sources/fetch", status_code=201)
def source_fetch(data: FetchSource, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = _service(request, db, ctx).fetch_source(**data.model_dump())
    db.commit()
    return result
```

## source_get

Source: `services/studio-api/src/studio/api/library.py:source_get`.

```python
@library_router.get("/sources/{ident}")
def source_get(ident: uuid.UUID, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return _service(request, db, ctx).get_source(ident)
```

## source_upload

Source: `services/studio-api/src/studio/api/library.py:source_upload`.

```python
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
```

## structure_preview

Source: `services/studio-api/src/studio/api/library.py:structure_preview`.

```python
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
    return {
        "smiles": smiles,
        "canonicalSmiles": Chem.MolToSmiles(molecule),
        "formula": rdMolDescriptors.CalcMolFormula(molecule),
        "svg": Draw.MolsToGridImage(  # type: ignore[no-untyped-call]
            [molecule], molsPerRow=1, subImgSize=(420, 300), useSVG=True
        ),
    }
```

## ArchiveArtifact

Source: `services/studio-api/src/studio/domain/library/contracts.py:ArchiveArtifact`.

```python
class ArchiveArtifact(Contract):
    artifact_id: str
```

## Citation

Source: `services/studio-api/src/studio/domain/library/contracts.py:Citation`.

```python
class Citation(Contract):
    source_id: str | None = None
    artifact_id: str | None = None
    url: str | None = Field(default=None, max_length=6000)
    title: str | None = Field(default=None, max_length=500)
    locator: dict[str, Any] = Field(default_factory=dict)
    archive_status: str | None = None
```

## Contract

Source: `services/studio-api/src/studio/domain/library/contracts.py:Contract`.

```python
class Contract(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", allow_inf_nan=False
    )
```

## CreateFolder

Source: `services/studio-api/src/studio/domain/library/contracts.py:CreateFolder`.

```python
class CreateFolder(Contract):
    name: str = Field(min_length=1, max_length=200)
    parent_id: str | None = None
```

## CreateMemory

Source: `services/studio-api/src/studio/domain/library/contracts.py:CreateMemory`.

```python
class CreateMemory(Contract):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=100_000)
    source_refs: list[SourceRef] = Field(min_length=1, max_length=100)
    generator: str = Field(default="user", max_length=160)
```

## CreateNotebook

Source: `services/studio-api/src/studio/domain/library/contracts.py:CreateNotebook`.

```python
class CreateNotebook(Contract):
    title: str = Field(min_length=1, max_length=300)
    folder_id: str | None = None
```

## CreatePage

Source: `services/studio-api/src/studio/domain/library/contracts.py:CreatePage`.

```python
class CreatePage(Contract):
    notebook_id: str
    title: str = Field(min_length=1, max_length=300)
    kind: Literal["note", "recipe", "formula", "smiles"] = "note"
    content: PageContent = Field(default_factory=PageContent)
    citations: list[Citation] = Field(default_factory=list, max_length=100)
```

## FetchSource

Source: `services/studio-api/src/studio/domain/library/contracts.py:FetchSource`.

```python
class FetchSource(Contract):
    url: str = Field(min_length=1, max_length=6000)
    title: str | None = Field(default=None, max_length=500)
    citation: dict[str, Any] = Field(default_factory=dict)
    force_refresh: bool = False
```

## Ingredient

Source: `services/studio-api/src/studio/domain/library/contracts.py:Ingredient`.

```python
class Ingredient(Contract):
    name: str = Field(max_length=300)
    amount: str | float = ""
    unit: str = Field(default="", max_length=100)
```

## PageContent

Source: `services/studio-api/src/studio/domain/library/contracts.py:PageContent`.

```python
class PageContent(Contract):
    markdown: str = Field(default="", max_length=500_000)
    ingredients: list[Ingredient] = Field(default_factory=list, max_length=500)
    steps: list[str] = Field(default_factory=list, max_length=500)
    latex: str = Field(default="", max_length=20_000)
    smiles: str = Field(default="", max_length=10_000)
    variables: dict[str, str | float] = Field(default_factory=dict, max_length=100)
```

## RestorePage

Source: `services/studio-api/src/studio/domain/library/contracts.py:RestorePage`.

```python
class RestorePage(Contract):
    expected_revision: int = Field(ge=1)
```

## SourceRef

Source: `services/studio-api/src/studio/domain/library/contracts.py:SourceRef`.

```python
class SourceRef(Contract):
    kind: Literal["page", "source"]
    id: str
    revision: int | None = Field(default=None, ge=1)
```

## UpdateFolder

Source: `services/studio-api/src/studio/domain/library/contracts.py:UpdateFolder`.

```python
class UpdateFolder(Contract):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: str | None = None
    expected_revision: int = Field(ge=1)
```

## UpdateNotebook

Source: `services/studio-api/src/studio/domain/library/contracts.py:UpdateNotebook`.

```python
class UpdateNotebook(Contract):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    folder_id: str | None = None
    ai_enabled: bool | None = None
    training_enabled: bool | None = None
    expected_revision: int = Field(ge=1)
```

## UpdatePage

Source: `services/studio-api/src/studio/domain/library/contracts.py:UpdatePage`.

```python
class UpdatePage(Contract):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: PageContent | None = None
    citations: list[Citation] | None = Field(default=None, max_length=100)
    expected_revision: int = Field(ge=1)
```

## LibraryService._record

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService._record`.

```python
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
```

## LibraryService.archive_download

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.archive_download`.

```python
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
```

## LibraryService.create_folder

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.create_folder`.

```python
    def create_folder(self, name: str, parent_id: uuid.UUID | str | None = None) -> dict[str, Any]:
        parent = self._get(LibraryFolder, parent_id) if parent_id else None
        row = LibraryFolder(
            **self._new(), name=_title(name, 200), parent_id=parent.id if parent else None
        )
        self.db.add(row)
        self.db.flush()
        return self._record(row)
```

## LibraryService.create_notebook

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.create_notebook`.

```python
    def create_notebook(
        self, title: str, folder_id: uuid.UUID | str | None = None
    ) -> dict[str, Any]:
        folder = self._get(LibraryFolder, folder_id) if folder_id else None
        row = Notebook(**self._new(), title=_title(title), folder_id=folder.id if folder else None)
        self.db.add(row)
        self.db.flush()
        return self._record(row)
```

## LibraryService.create_page

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.create_page`.

```python
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
```

## LibraryService.delete_folder

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.delete_folder`.

```python
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
```

## LibraryService.delete_notebook

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.delete_notebook`.

```python
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
```

## LibraryService.delete_page

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.delete_page`.

```python
    def delete_page(self, ident: uuid.UUID | str, expected_revision: int) -> dict[str, bool]:
        row = self._get(NotebookPage, ident)
        self._change(row, expected_revision, deleted_at=datetime.now(UTC))
        self._invalidate("page", row.id)
        return {"deleted": True}
```

## LibraryService.delete_source

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.delete_source`.

```python
    def delete_source(self, ident: uuid.UUID | str, expected_revision: int) -> dict[str, bool]:
        row = self._get(LibrarySource, ident)
        self._change(row, expected_revision, deleted_at=datetime.now(UTC))
        self._invalidate("source", row.id)
        return {"deleted": True}
```

## LibraryService.fetch_source

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.fetch_source`.

```python
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
```

## LibraryService.forget_memory

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.forget_memory`.

```python
    def forget_memory(self, ident: uuid.UUID | str) -> dict[str, bool]:
        row = self._get(ResearchMemory, ident)
        # Actual memory content is removed; source notes remain under owner control.
        row.body, row.title, row.source_refs, row.status = "", "Forgotten memory", [], "forgotten"
        row.version += 1
        self.db.flush()
        return {"forgotten": True}
```

## LibraryService.get_page

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.get_page`.

```python
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
```

## LibraryService.get_source

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.get_source`.

```python
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
```

## LibraryService.list_all

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.list_all`.

```python
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
```

## LibraryService.restore_page

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.restore_page`.

```python
    def restore_page(self, ident: uuid.UUID | str, expected_revision: int) -> dict[str, Any]:
        row = self._get(NotebookPage, ident, deleted=True)
        self._get(Notebook, row.notebook_id)
        if row.deleted_at is None:
            raise DomainError(ErrorCode.CONFLICT, "the page is not in trash")
        self._change(row, expected_revision, deleted_at=None)
        self._revision(row)
        return self._record(row)
```

## LibraryService.save_memory

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.save_memory`.

```python
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
```

## LibraryService.search

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.search`.

```python
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
```

## LibraryService.source_file

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.source_file`.

```python
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
```

## LibraryService.update_folder

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.update_folder`.

```python
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
```

## LibraryService.update_notebook

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.update_notebook`.

```python
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
```

## LibraryService.update_page

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.update_page`.

```python
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
```
