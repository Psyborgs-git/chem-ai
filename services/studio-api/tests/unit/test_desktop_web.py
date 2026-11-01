"""The native UI shares loopback auth without exposing a filesystem root."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from studio.api.app import create_app
from studio.config.settings import Settings, get_settings, reset_settings_cache


@pytest.fixture(autouse=True)
def database_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    # Static/auth-transport tests need no DB; real connectivity is covered by
    # the companion desktop-auth integration test.
    monkeypatch.setattr("studio.api.desktop._database_ready", lambda engine: True)


@pytest.fixture()
def frontend(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    root.mkdir()
    (root / "index.html").write_text('<html><script src="/assets/app-123.js"></script></html>')
    (root / "assets").mkdir()
    (root / "assets" / "app-123.js").write_text("window.builtFrontend = true;")
    return root


def _client(frontend: Path | None, tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                desktop_frontend_dir=frontend,
                vault_root=tmp_path / "vault",
                port=8788,
                allowed_origins=("http://127.0.0.1:8788", "http://localhost:8788"),
            )
        ),
        base_url="http://127.0.0.1:8788",
    )


def test_desktop_mount_is_opt_in(tmp_path: Path) -> None:
    with _client(None, tmp_path) as client:
        assert client.get("/").status_code == 404
        assert client.get("/api/desktop/runtime").status_code == 404
        assert client.get("/healthz").json() == {"status": "ok"}


def test_built_ui_deep_links_and_assets(frontend: Path, tmp_path: Path) -> None:
    with _client(frontend, tmp_path) as client:
        for path in ("/", "/index.html", "/runs/saved-id", "/projects/a/tasks/b"):
            result = client.get(path, headers={"accept": "text/html"})
            assert result.status_code == 200
            assert result.text == (frontend / "index.html").read_text()
            assert result.headers["content-type"].startswith("text/html")
            assert result.headers["cache-control"] == "no-store"
            assert result.headers["x-content-type-options"] == "nosniff"
            assert result.headers["cross-origin-resource-policy"] == "same-origin"
        asset = client.get("/assets/app-123.js")
        assert asset.status_code == 200
        assert asset.text == "window.builtFrontend = true;"
        assert "javascript" in asset.headers["content-type"]
        assert client.head("/").status_code == 200


def test_identity_is_explicit_and_contains_no_paths(frontend: Path, tmp_path: Path) -> None:
    with _client(frontend, tmp_path) as client:
        result = client.get("/api/desktop/runtime")
        assert result.status_code == 200
        assert result.json() == {
            "application": "chemistry-studio",
            "desktop": True,
            "frontendAvailable": True,
            "databaseReady": True,
        }
        (frontend / "index.html").unlink()
        assert client.get("/api/desktop/runtime").json()["frontendAvailable"] is False


def test_identity_reports_database_failure_without_diagnostics(
    frontend: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("studio.api.desktop._database_ready", lambda engine: False)
    with _client(frontend, tmp_path) as client:
        result = client.get("/api/desktop/runtime")
        assert result.status_code == 503
        assert result.json() == {
            "application": "chemistry-studio",
            "desktop": True,
            "frontendAvailable": True,
            "databaseReady": False,
        }
        assert result.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "path",
    [
        "/api/missing",
        "/graphql/missing",
        "/healthz/missing",
        "/readyz/missing",
        "/assets/missing.js",
    ],
)
def test_spa_does_not_swallow_api_or_missing_assets(
    frontend: Path, tmp_path: Path, path: str
) -> None:
    with _client(frontend, tmp_path) as client:
        result = client.get(path, headers={"accept": "text/html"})
        assert result.status_code == 404
        assert "<html>" not in result.text
        assert client.get("/runs/a", headers={"accept": "application/json"}).status_code == 404
        assert client.get("/assets").status_code == 404


def test_private_files_and_symlink_escape_are_never_served(frontend: Path, tmp_path: Path) -> None:
    (tmp_path / "private.txt").write_text("private marker")
    (frontend / ".env").write_text("private marker")
    (frontend / "assets" / "outside.txt").symlink_to(tmp_path / "private.txt")
    (frontend / "outside").symlink_to(tmp_path)
    with _client(frontend, tmp_path) as client:
        for path in (
            "/%2e%2e/private.txt",
            "/assets/%2e%2e/%2e%2e/private.txt",
            "/.env",
            "/assets/outside.txt",
            "/outside/private.txt",
            "/assets%5c..%5c..%5cprivate.txt",
        ):
            result = client.get(path)
            assert result.status_code == 404, (path, result.text)
            assert "private marker" not in result.text


def test_static_mount_keeps_api_origin_and_host_checks(frontend: Path, tmp_path: Path) -> None:
    with _client(frontend, tmp_path) as client:
        assert client.get("/", headers={"host": "attacker.example"}).status_code == 403
        assert (
            client.post(
                "/api/auth/login", json={}, headers={"origin": "https://attacker.example"}
            ).status_code
            == 403
        )
        # Validation on the original auth route proves the accepted local
        # origin was neither rejected nor handled as a frontend navigation.
        assert (
            client.post(
                "/api/auth/login", json={}, headers={"origin": "http://127.0.0.1:8788"}
            ).status_code
            == 422
        )
        assert client.post("/runs/a", json={}).status_code == 405


def test_invalid_or_overlapping_static_root_refuses_startup(frontend: Path, tmp_path: Path) -> None:
    for root in (Path("relative-dist"), tmp_path / "missing", tmp_path):
        with pytest.raises(ValueError):
            _client(root, tmp_path)
    with pytest.raises(ValueError, match="must not overlap"):
        create_app(Settings(desktop_frontend_dir=frontend, vault_root=frontend / "vault"))
    (frontend / "index.html").unlink()
    (frontend / "index.html").symlink_to(tmp_path / "outside.html")
    (tmp_path / "outside.html").write_text("private marker")
    with pytest.raises(ValueError, match="own built index"):
        _client(frontend, tmp_path)


def test_desktop_frontend_environment_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "STUDIO_DESKTOP_FRONTEND_DIR", "/Applications/Chemistry Studio.app/Contents/dist"
    )
    reset_settings_cache()
    try:
        assert get_settings().desktop_frontend_dir == Path(
            "/Applications/Chemistry Studio.app/Contents/dist"
        )
    finally:
        reset_settings_cache()


def test_native_build_identity_distinguishes_an_old_api(frontend: Path, tmp_path: Path) -> None:
    settings = Settings(
        desktop_frontend_dir=frontend, desktop_build_id="provider-build-001",
        vault_root=tmp_path / "vault",
    )
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8788") as client:
        result = client.get("/api/desktop/runtime")
        assert result.status_code == 200
        assert result.json()["buildId"] == "provider-build-001"
