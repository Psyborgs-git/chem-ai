"""Same-origin native navigation retains authenticated durable API access."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from studio.api.app import create_app
from studio.config.settings import Settings

pytestmark = pytest.mark.integration


def test_native_same_origin_session_and_foreign_origin_denial(db_url: str, tmp_path: Path) -> None:
    frontend = tmp_path / "dist"
    frontend.mkdir()
    (frontend / "index.html").write_text("<html>Built app</html>")
    app = create_app(
        Settings(
            database_url=db_url,
            vault_root=tmp_path / "vault",
            desktop_frontend_dir=frontend,
            port=8788,
            allowed_origins=("http://127.0.0.1:8788",),
        )
    )
    with TestClient(app, base_url="http://127.0.0.1:8788") as client:
        readiness = client.get("/api/desktop/runtime")
        assert readiness.status_code == 200
        assert readiness.json()["databaseReady"] is True
        setup = client.post(
            "/api/auth/setup",
            json={
                "login": "native-owner",
                "display_name": "Native owner",
                "password": "local-test-password",
            },
            headers={"origin": "http://127.0.0.1:8788"},
        )
        assert setup.status_code == 200, setup.text
        cookie = setup.headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "samesite=strict" in cookie
        assert "path=/" in cookie
        assert client.get("/runs/persisted-run", headers={"accept": "text/html"}).status_code == 200
        viewer = client.post(
            "/graphql",
            json={"query": "{ viewer { displayName } }"},
            headers={"origin": "http://127.0.0.1:8788"},
        )
        assert viewer.status_code == 200
        assert viewer.json() == {"data": {"viewer": {"displayName": "Native owner"}}}
        # A hostile page cannot revoke a local native session using its cookie.
        denied = client.post("/api/auth/logout", headers={"origin": "https://attacker.example"})
        assert denied.status_code == 403
        assert (
            client.post("/graphql", json={"query": "{ viewer { displayName } }"}).json()
            == viewer.json()
        )
