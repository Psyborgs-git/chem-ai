"""Ownership, autosave, source archival and forget behavior without live services."""

from __future__ import annotations

import errno
import hashlib
import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from chem_studio_policy.capabilities import Grant, capabilities_for_role
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import JSON, Column, MetaData, Table, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from studio.api import library as library_api
from studio.api.deps import db_session, request_context
from studio.api.library import library_router
from studio.auth.context import ServiceContext
from studio.domain.library import service as library_module
from studio.domain.library.models import (
    LibraryFolder,
    LibrarySource,
    Notebook,
    NotebookPage,
    PageRevision,
    ResearchMemory,
)
from studio.domain.library.research import Download
from studio.domain.library.service import LibraryService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import Artifact, Principal, Workspace


@pytest.fixture
def libraries(tmp_path: Path):  # type: ignore[no-untyped-def]
    engine = create_engine(f"sqlite:///{tmp_path / 'library.sqlite'}")
    for model in (
        Workspace,
        Principal,
        LibraryFolder,
        Notebook,
        NotebookPage,
        PageRevision,
        LibrarySource,
        ResearchMemory,
    ):
        model.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as db:
        workspace = Workspace(slug="private-library", display_name="Library")
        db.add(workspace)
        db.flush()
        owners = []
        for name in ("alice", "admin"):
            principal = Principal(
                workspace_id=workspace.id, kind="user", login=name, display_name=name
            )
            db.add(principal)
            db.flush()
            ctx = ServiceContext(
                session=db,
                workspace_id=workspace.id,
                principal_id=principal.id,
                principal_kind="user",
                grants=frozenset(Grant(capability=c) for c in capabilities_for_role("owner")),
            )
            owners.append(
                LibraryService(
                    db, ctx, vault_root=tmp_path / "vault", downloads_root=tmp_path / "downloads"
                )
            )
        db.commit()
        yield db, owners[0], owners[1]
    engine.dispose()


def test_private_owner_boundary_includes_admin_and_parent_links(libraries: Any) -> None:
    db, alice, admin = libraries
    folder = alice.create_folder("Private formulations")
    notebook = alice.create_notebook("Solvent notes", folder["id"])
    page = alice.create_page(notebook["id"], "Ethanol", content={"markdown": "Private CCO recipe"})
    db.commit()
    assert admin.list_all()["pages"] == []
    assert admin.search("Private") == []
    for operation in (
        lambda: admin.get_page(page["id"]),
        lambda: admin.create_notebook("Cross-owner", folder["id"]),
        lambda: admin.create_page(notebook["id"], "Cross-owner"),
        lambda: admin.save_memory("Leak", "Private", [{"kind": "page", "id": page["id"]}]),
    ):
        with pytest.raises(DomainError) as denied:
            operation()
        assert denied.value.code == ErrorCode.NOT_FOUND
    assert db.scalar(select(NotebookPage)).owner_id == alice.ctx.principal_id


def test_autosave_revisions_stale_memory_and_real_forget(libraries: Any) -> None:
    db, alice, _ = libraries
    notebook = alice.create_notebook("Recipe book")
    page = alice.create_page(
        notebook["id"],
        "First",
        "recipe",
        {
            "markdown": "Original",
            "ingredients": [{"name": "water", "amount": 5, "unit": "mL"}],
            "steps": ["Mix"],
            "latex": "c=n/V",
            "smiles": "O",
        },
    )
    memory = alice.save_memory(
        "Water recipe", "Use five millilitres", [{"kind": "page", "id": page["id"], "revision": 1}]
    )
    updated = alice.update_page(page["id"], 1, content={"markdown": "Revised"})
    assert updated["revision"] == 2
    assert alice.active_memory() == []
    with pytest.raises(DomainError) as conflict:
        alice.update_page(page["id"], 1, content={"markdown": "Lost update"})
    assert conflict.value.code == ErrorCode.REVISION_CONFLICT
    revisions = alice.get_page(page["id"])["revisions"]
    assert [r["revision"] for r in revisions] == [2, 1]
    assert revisions[1]["content"]["ingredients"][0]["amount"] == 5
    alice.forget_memory(memory["id"])
    forgotten = db.get(ResearchMemory, uuid.UUID(memory["id"]))
    assert forgotten.body == "" and forgotten.source_refs == []
    assert alice.list_all()["memory"] == []
    assert all(r["kind"] != "memory" for r in alice.search("five"))


def test_folder_cycles_and_disabled_notebook_never_reach_agent(libraries: Any) -> None:
    _, alice, _ = libraries
    parent = alice.create_folder("Root")
    child = alice.create_folder("Child", parent["id"])
    with pytest.raises(DomainError, match="cycle"):
        alice.update_folder(parent["id"], 1, parent_id=child["id"])
    notebook = alice.create_notebook("Hidden from AI", child["id"])
    page = alice.create_page(notebook["id"], "Secret", content={"markdown": "Keep solvent context"})
    alice.save_memory("Context", "Solvent", [{"kind": "page", "id": page["id"]}])
    alice.update_notebook(notebook["id"], 1, ai_enabled=False)
    assert alice.list_all(for_agent=True)["pages"] == []
    assert alice.search("solvent", for_agent=True) == []
    with pytest.raises(DomainError):
        alice.get_page(page["id"], for_agent=True)
    assert alice.get_page(page["id"])["content"]["markdown"] == "Keep solvent context"
    with pytest.raises(DomainError, match="contents"):
        alice.delete_folder(parent["id"], 1)


def test_training_export_uses_current_structured_page_and_honors_toggle(libraries: Any) -> None:
    _, alice, _ = libraries
    notebook = alice.create_notebook("Training recipes")
    page = alice.create_page(
        notebook["id"],
        "Water",
        "recipe",
        {
            "markdown": "Source-authored note",
            "ingredients": [{"name": "water", "amount": 5, "unit": "mL"}],
            "steps": ["Mix"],
            "latex": "c=n/V",
            "smiles": "O",
        },
    )
    exported = alice.export_training_page(page["id"])
    assert exported["revision"] == 1 and exported["dataKind"] == "user_authored"
    assert "water: 5.0 mL" in exported["body"]
    assert "1. Mix" in exported["body"] and "SMILES: O" in exported["body"]
    alice.update_notebook(notebook["id"], 1, training_enabled=False)
    with pytest.raises(DomainError, match="training is disabled"):
        alice.export_training_page(page["id"])


def test_trash_restore_keeps_immutable_revisions_and_owner_scope(libraries: Any) -> None:
    _, alice, admin = libraries
    notebook = alice.create_notebook("Restore notes")
    page = alice.create_page(
        notebook["id"], "Recover me", content={"markdown": "Retained original"}
    )
    alice.update_page(page["id"], 1, content={"markdown": "Current note"})
    alice.delete_page(page["id"], 2)
    assert alice.list_all()["pages"] == []
    trashed = alice.list_all()["trash"][0]
    with pytest.raises(DomainError, match="recoverable trashed pages"):
        alice.delete_notebook(notebook["id"], notebook["revision"])
    with pytest.raises(DomainError):
        admin.restore_page(page["id"], trashed["revision"])
    restored = alice.restore_page(page["id"], trashed["revision"])
    assert restored["content"]["markdown"] == "Current note"
    assert [row["revision"] for row in alice.get_page(page["id"])["revisions"]] == [4, 2, 1]
    assert alice.list_all()["trash"] == []


def test_refresh_retains_changed_source_versions_and_reuses_identical_bytes(
    libraries: Any, monkeypatch: Any
) -> None:
    _, alice, _ = libraries
    body = [b"Original paper text"]
    monkeypatch.setattr(
        library_module, "fetch_public", lambda url: Download(url, "text/plain", body[0])
    )
    first = alice.fetch_source("https://example.org/versioned.txt")
    same = alice.fetch_source("https://example.org/versioned.txt", force_refresh=True)
    assert first["id"] == same["id"]
    body[0] = b"Revised paper text"
    second = alice.fetch_source("https://example.org/versioned.txt", force_refresh=True)
    assert second["id"] != first["id"] and second["checksum"] != first["checksum"]
    assert alice.source_file(first["id"])[0].read_bytes() == b"Original paper text"
    assert alice.source_file(second["id"])[0].read_bytes() == b"Revised paper text"


def test_storage_pressure_preserves_prior_files_and_removes_failed_new_copies(
    libraries: Any, monkeypatch: Any
) -> None:
    db, alice, _ = libraries
    prior = alice.archive_download(Download("https://example.org/old.txt", "text/plain", b"Kept"))
    protected = alice.source_file(prior["id"])[0]
    monkeypatch.setattr(library_module.shutil, "disk_usage", lambda path: SimpleNamespace(free=1))
    with pytest.raises(DomainError) as low_storage:
        alice.archive_download(Download("https://example.org/new.txt", "text/plain", b"New"))
    assert low_storage.value.code == ErrorCode.RESOURCE_UNAVAILABLE
    assert protected.read_bytes() == b"Kept"
    monkeypatch.setattr(
        library_module.shutil, "disk_usage", lambda path: SimpleNamespace(free=1024**3)
    )
    original_write = alice._write

    def full_during_copy(path: Path, body: bytes) -> None:
        if path.is_relative_to(alice.downloads_root):
            raise OSError(errno.ENOSPC, "disk full")
        original_write(path, body)

    monkeypatch.setattr(alice, "_write", full_during_copy)
    with pytest.raises(DomainError) as full:
        alice.archive_download(Download("https://example.org/new.txt", "text/plain", b"New"))
    assert full.value.code == ErrorCode.RESOURCE_UNAVAILABLE
    assert protected.read_bytes() == b"Kept"
    assert len(db.scalars(select(LibrarySource)).all()) == 1
    assert [path.name for path in protected.parent.parent.iterdir()] == [prior["id"]]


def test_long_source_name_fits_postgres_storage_key_contract(libraries: Any) -> None:
    db, alice, _ = libraries
    source = alice.archive_download(
        Download("upload:long-name", "text/plain", b"CCO"), original_name="chemistry-" * 25 + ".smi"
    )
    row = db.get(LibrarySource, uuid.UUID(source["id"]))
    assert len(row.original_key) <= 200
    assert source["originalName"].endswith(".smi")


def test_retained_artifact_copies_preserve_live_rights_and_revocation(
    libraries: Any, monkeypatch: Any
) -> None:
    from studio.config.settings import Settings
    from studio.domain.evidence.vault import Vault
    from studio.domain.library.artifacts import archive_artifact

    db, alice, admin = libraries
    monkeypatch.setenv("STUDIO_RESEARCH_DOWNLOADS_ROOT", str(alice.downloads_root))
    # Portable copy of the Artifact columns; service queries exercise real SQL.
    Table(
        "artifacts",
        MetaData(),
        *[
            Column(
                column.name,
                JSON() if isinstance(column.type, JSONB) else column.type,
                primary_key=column.primary_key,
                nullable=column.nullable,
                server_default=column.server_default,
            )
            for column in Artifact.__table__.columns
        ],
    ).create(db.get_bind())
    body = b"Cited original CCO data"
    checksum = hashlib.sha256(body).hexdigest()
    artifact_id = uuid.uuid4()
    vault = Vault(alice.vault_root.parent)
    staging = vault.begin_staging(alice.ctx.workspace_id, artifact_id)
    vault.append_bytes(staging, body)
    storage_key, _ = vault.commit(alice.ctx.workspace_id, artifact_id, checksum)
    artifact = Artifact(
        id=artifact_id,
        workspace_id=alice.ctx.workspace_id,
        storage_key=storage_key,
        original_name="Cited data.txt",
        media_type="text/plain",
        byte_size=len(body),
        checksum_sha256=checksum,
        upload_state="committed",
        review_state="accepted",
        rights={
            "retrieval": "allowed",
            "extraction": "allowed",
            "training": "allowed",
            "export": "denied",
        },
        created_by=alice.ctx.principal_id,
    )
    db.add(artifact)
    db.flush()
    settings = Settings(vault_root=alice.vault_root.parent)
    source = archive_artifact(db, alice.ctx, settings, artifact_id)
    assert source["extractedText"] == body.decode()
    assert source["citation"]["rights"]["export"] == "denied"
    assert alice.source_file(source["id"])[0].read_bytes() == body
    with pytest.raises(DomainError):
        admin.get_source(source["id"])
    alice.save_memory("Cited finding", "CCO", [{"kind": "source", "id": source["id"]}])
    artifact.rights = {**artifact.rights, "extraction": "denied"}
    db.flush()
    assert alice.get_source(source["id"])["extractedText"] == ""
    assert alice.search("Cited original") == []
    assert alice.active_memory() == []
    with pytest.raises(DomainError):
        alice.source_file(source["id"], "text")
    assert alice.source_file(source["id"], "original")[0].read_bytes() == body
    artifact.review_state = "revoked"
    db.flush()
    with pytest.raises(DomainError):
        alice.source_file(source["id"], "original")


def test_archive_symlink_cannot_create_directories_outside_root(
    libraries: Any, tmp_path: Path
) -> None:
    _, alice, _ = libraries
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "symlink-root"
    root.mkdir()
    (root / str(alice.ctx.workspace_id)).symlink_to(outside, target_is_directory=True)
    with pytest.raises(DomainError, match="escapes"):
        alice._folder(root, uuid.uuid4())
    assert list(outside.iterdir()) == []


def test_original_readable_citation_archive_and_owner_download(
    libraries: Any, monkeypatch: Any
) -> None:
    db, alice, admin = libraries
    calls = []

    def downloaded(url: str) -> Download:
        calls.append(url)
        return Download(url, "text/html", b"<h1>Paper</h1><script>bad()</script><p>CCO data</p>")

    monkeypatch.setattr(library_module, "fetch_public", downloaded)
    source = alice.fetch_source(
        "https://example.org/paper", title="A paper", citation={"doi": "10.x/a"}
    )
    assert source["extractedText"] == "Paper\nCCO data"
    original, _, name = alice.source_file(source["id"])
    assert original.read_bytes().startswith(b"<h1>")
    assert name.endswith(".html")
    metadata_file, _, _ = alice.source_file(source["id"], "metadata")
    metadata = json.loads(metadata_file.read_text())
    assert metadata["checksum"] == source["checksum"]
    copies = Path(source["downloadDirectory"])
    assert (copies / name).read_bytes() == original.read_bytes()
    assert "CCO data" in (copies / "readable.md").read_text()
    assert "bad()" not in (copies / "readable.md").read_text()
    with pytest.raises(DomainError):
        admin.source_file(source["id"])
    notebook = alice.create_notebook("Citations")
    page = alice.create_page(notebook["id"], "Sourced", citations=[{"url": source["url"]}])
    assert page["citations"][0]["sourceId"] == source["id"]
    assert len(calls) == 1
    memory = alice.save_memory(
        "Paper context", "Extracted data", [{"kind": "source", "id": source["id"]}]
    )
    alice.delete_source(source["id"], 1)
    assert alice.active_memory() == []
    assert db.get(ResearchMemory, uuid.UUID(memory["id"])).status == "stale"
    with pytest.raises(DomainError):
        alice.source_file(source["id"])


def test_json_api_revisions_validation_and_owner_isolation(
    libraries: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    db, alice, admin = libraries
    monkeypatch.setenv("STUDIO_RESEARCH_DOWNLOADS_ROOT", str(tmp_path / "downloads"))
    current = [alice.ctx]
    app = FastAPI()
    app.state.settings = SimpleNamespace(vault_root=tmp_path / "vault")
    app.include_router(library_router)
    app.dependency_overrides[db_session] = lambda: db
    app.dependency_overrides[request_context] = lambda: current[0]

    @app.exception_handler(DomainError)
    def errors(request: Any, exc: DomainError) -> JSONResponse:
        status = 409 if exc.code == ErrorCode.REVISION_CONFLICT else 404
        return JSONResponse({"errors": [exc.to_dict()]}, status_code=status)

    with TestClient(app) as client:
        notebook = client.post("/api/library/notebooks", json={"title": "Test"})
        assert notebook.status_code == 201, notebook.text
        response = client.post(
            "/api/library/pages",
            json={
                "notebookId": notebook.json()["id"],
                "title": "Formula",
                "kind": "formula",
                "content": {"latex": "c=n/V", "markdown": "Concentration"},
            },
        )
        assert response.status_code == 201, response.text
        page = response.json()
        uploaded = client.post(
            "/api/library/sources/upload",
            files={"file": ("custom.smi", b"CCO ethanol\nO water\n", "text/plain")},
            data={"title": "Custom SMILES"},
        )
        assert uploaded.status_code == 201, uploaded.text
        assert uploaded.json()["originalName"] == "custom.smi"
        assert (
            client.get(uploaded.json()["originalDownloadUrl"]).content == b"CCO ethanol\nO water\n"
        )
        updated = client.patch(
            f"/api/library/pages/{page['id']}",
            json={
                "expectedRevision": 1,
                "content": {"markdown": "Saved"},
            },
        )
        assert updated.status_code == 200 and updated.json()["revision"] == 2
        assert (
            client.patch(
                f"/api/library/pages/{page['id']}",
                json={
                    "expectedRevision": 1,
                    "title": "Stale",
                },
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/api/library/notebooks", json={"title": "X", "ownerId": "intruder"}
            ).status_code
            == 422
        )
        current[0] = admin.ctx
        assert client.get(f"/api/library/pages/{page['id']}").status_code == 404
        assert client.get("/api/library").json()["pages"] == []


def test_folder_reveal_uses_only_fixed_owner_directory(
    libraries: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    db, alice, _ = libraries
    calls = []
    monkeypatch.setenv("STUDIO_RESEARCH_DOWNLOADS_ROOT", str(tmp_path / "downloads"))
    monkeypatch.setattr(library_api, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(library_api.subprocess, "run", lambda args, **kw: calls.append(args))
    app = FastAPI()
    app.state.settings = SimpleNamespace(vault_root=tmp_path / "vault")
    app.include_router(library_router)
    app.dependency_overrides[db_session] = lambda: db
    app.dependency_overrides[request_context] = lambda: alice.ctx
    with TestClient(app) as client:
        assert not calls
        response = client.post("/api/library/downloads/reveal", json={"path": "/untrusted"})
        assert response.status_code == 200
        expected = str(alice.owner_downloads)
        assert calls == [["/usr/bin/open", expected]]
        assert response.json() == {"opened": True, "directory": expected}
