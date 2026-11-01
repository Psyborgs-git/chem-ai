"""A migrated PostgreSQL library survives app restart and enforces private auth."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from starlette.testclient import TestClient

from studio.api.app import create_app
from studio.auth.sessions import issue_session
from studio.config.settings import Settings
from studio.domain.library import service
from studio.domain.library.research import Download
from studio.persistence.models import Principal, PrincipalCapability, Workspace

pytestmark = pytest.mark.integration


def test_library_persistence_auth_download_and_no_shared_events(
    db_url: str, tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setenv("STUDIO_RESEARCH_DOWNLOADS_ROOT", str(tmp_path / "downloads"))
    monkeypatch.setattr(
        service,
        "fetch_public",
        lambda url: Download(url, "text/plain", b"An archived research source with CCO."),
    )
    settings = Settings(database_url=db_url, vault_root=tmp_path / "vault")
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1:8787") as client:
        assert client.get("/api/library").status_code == 401
        setup = client.post(
            "/api/auth/setup",
            json={
                "login": "library-owner",
                "display_name": "Library owner",
                "password": "test-library-password",
            },
        )
        assert setup.status_code == 200, setup.text
        token = client.cookies.get("studio_session")
        folder = client.post("/api/library/folders", json={"name": "Private recipes"}).json()
        notebook = client.post(
            "/api/library/notebooks", json={"title": "Research over time", "folderId": folder["id"]}
        ).json()
        created = client.post(
            "/api/library/pages",
            json={
                "notebookId": notebook["id"],
                "title": "Ethanol source",
                "kind": "smiles",
                "content": {"markdown": "Private sentinel note", "smiles": "CCO"},
            },
        )
        assert created.status_code == 201, created.text
        page = created.json()
        source = client.post(
            "/api/library/sources/fetch",
            json={"url": "https://example.org/chemistry.txt", "title": "Research source"},
        ).json()
        memory = client.post(
            "/api/library/memory",
            json={
                "title": "Resume context",
                "body": "Continue the ethanol research",
                "sourceRefs": [{"kind": "page", "id": page["id"], "revision": 1}],
            },
        )
        assert memory.status_code == 201, memory.text
        assert (
            client.get(source["originalDownloadUrl"]).content
            == b"An archived research source with CCO."
        )
        assert client.get("/api/library").headers["cache-control"] == "no-store"
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8787") as restarted:
        restarted.cookies.set("studio_session", token)
        resumed = restarted.get(f"/api/library/pages/{page['id']}")
        assert resumed.status_code == 200
        assert resumed.json()["content"]["smiles"] == "CCO"
        assert restarted.get("/api/library").json()["memory"][0]["body"].startswith("Continue")
        # A second owner/admin has workspace-wide permissions but no private access.
        with app.state.session_factory() as db:
            workspace = db.scalar(select(Workspace))
            principal = Principal(
                workspace_id=workspace.id,
                kind="user",
                login="other-owner",
                display_name="Other owner",
            )
            db.add(principal)
            db.flush()
            for capability in capabilities_for_role("owner"):
                db.add(
                    PrincipalCapability(
                        workspace_id=workspace.id, principal_id=principal.id, capability=capability
                    )
                )
            other = issue_session(db, workspace.id, principal, 3600)
            from studio.persistence.models import OutboxEvent

            assert all(
                "Private sentinel" not in str(event.payload)
                for event in db.scalars(select(OutboxEvent))
            )
            db.commit()
        restarted.cookies.set("studio_session", other.token)
        assert restarted.get(f"/api/library/pages/{page['id']}").status_code == 404
        assert restarted.get(source["originalDownloadUrl"]).status_code == 404
        assert restarted.get("/api/library").json()["pages"] == []
