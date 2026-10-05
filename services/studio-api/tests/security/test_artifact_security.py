"""CS-0103 security acceptance — artifact vault boundary.

AT-0103-1  traversal/symlink archive → rejected outside the vault
AT-0103-3  unauthenticated artifact URL → no bytes, no private path
"""

from __future__ import annotations

import io
import tarfile
import uuid
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from studio.api.app import create_app
from studio.api.deps import SESSION_COOKIE
from studio.auth.sessions import issue_session
from studio.auth.setup import create_owner, grant_capabilities
from studio.config.settings import Settings
from studio.domain.evidence.vault import Vault
from studio.errors import DomainError
from studio.persistence.models import Principal, Workspace

pytestmark = pytest.mark.security

HEADERS = {"origin": "http://127.0.0.1:8787", "host": "127.0.0.1:8787"}


@pytest.fixture()
def app(db_url: str, tmp_path: Path) -> FastAPI:
    return create_app(Settings(database_url=db_url, vault_root=tmp_path))


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture()
def authed(client: TestClient) -> TestClient:
    resp = client.post(
        "/api/auth/setup",
        json={
            "login": "owner",
            "display_name": "Owner",
            "password": "correct horse battery staple",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    return client


def _traversal_tar() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        info = tarfile.TarInfo("../evil.txt")
        data = b"escape payload"
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
        ok = tarfile.TarInfo("fine.txt")
        ok.size = 1
        tf.addfile(ok, io.BytesIO(b"x"))
    return buf.getvalue()


def _traversal_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.txt", b"escape payload")
    return buf.getvalue()


def _upload(client: TestClient, name: str, media: str, payload: bytes) -> dict:
    init = client.post(
        "/api/artifacts/uploads",
        json={"original_name": name, "media_type": media},
        headers=HEADERS,
    )
    assert init.status_code == 200, init.text
    aid = init.json()["artifactId"]
    put = client.put(f"/api/artifacts/uploads/{aid}/content", content=payload, headers=HEADERS)
    assert put.status_code == 200, put.text
    return {"id": aid, "init": init.json()}


class TestUnsafeArchives:
    """AT-0103-1: unsafe payloads never reach the vault blob store."""

    def test_traversal_tar_rejected_outside_vault(self, authed: TestClient, tmp_path: Path) -> None:
        up = _upload(authed, "bundle.tar", "application/x-tar", _traversal_tar())
        fin = authed.post(f"/api/artifacts/uploads/{up['id']}/finish", json={}, headers=HEADERS)
        assert fin.status_code == 422
        # Nothing committed into the blob tree; staging discarded.
        blobs = list((tmp_path / "blobs").rglob("*")) if (tmp_path / "blobs").exists() else []
        assert blobs == []
        assert list((tmp_path / ".staging").rglob("*.part")) == []

    def test_traversal_zip_rejected_outside_vault(self, authed: TestClient, tmp_path: Path) -> None:
        up = _upload(authed, "bundle.zip", "application/zip", _traversal_zip())
        fin = authed.post(f"/api/artifacts/uploads/{up['id']}/finish", json={}, headers=HEADERS)
        assert fin.status_code == 422
        assert not (tmp_path / "blobs").exists() or not list((tmp_path / "blobs").rglob("*"))

    def test_mislabeled_archive_still_rejected(self, authed: TestClient, tmp_path: Path) -> None:
        # A zip uploaded as text/plain is detected by magic bytes.
        up = _upload(authed, "notes.txt", "text/plain", _traversal_zip())
        fin = authed.post(f"/api/artifacts/uploads/{up['id']}/finish", json={}, headers=HEADERS)
        assert fin.status_code == 422


class TestDownloadBoundary:
    """AT-0103-3: no bytes or private path without authorization."""

    def _committed_artifact(self, authed: TestClient) -> str:
        up = _upload(authed, "report.csv", "text/csv", b"a,b\n1,2\n")
        fin = authed.post(f"/api/artifacts/uploads/{up['id']}/finish", json={}, headers=HEADERS)
        assert fin.status_code == 200, fin.text
        return up["id"]

    def test_unauthenticated_download_returns_nothing(
        self, app: FastAPI, authed: TestClient, tmp_path: Path
    ) -> None:
        aid = self._committed_artifact(authed)
        anon = TestClient(app)
        resp = anon.get(f"/api/artifacts/{aid}/content", headers=HEADERS)
        assert resp.status_code == 401
        assert b"a,b" not in resp.content
        # Response must not leak the vault path or storage key.
        assert str(tmp_path) not in resp.text
        assert "storage" not in resp.text.lower()

    def test_cross_workspace_download_is_uniform_not_found(
        self, app: FastAPI, authed: TestClient, session: Session
    ) -> None:
        aid = self._committed_artifact(authed)
        # A second workspace with its own authenticated principal.
        ws_b = Workspace(slug="ws-b", display_name="B")
        session.add(ws_b)
        session.flush()
        owner_b = create_owner(session, ws_b, "owner-b", "OB", "long-password-123")
        issued = issue_session(session, ws_b.id, owner_b, 3600)
        session.commit()

        other = TestClient(app)
        other.cookies.set(SESSION_COOKIE, issued.token)
        resp = other.get(f"/api/artifacts/{aid}/content", headers=HEADERS)
        assert resp.status_code == 404
        assert "a,b" not in resp.text

    def test_viewer_cannot_upload(self, app: FastAPI, authed: TestClient, session: Session) -> None:
        # the HTTP-setup workspace is the only one
        ws = session.execute(select(Workspace)).scalar_one()
        viewer = Principal(workspace_id=ws.id, kind="user", login="viewer", display_name="V")
        session.add(viewer)
        session.flush()
        grant_capabilities(session, ws.id, viewer, "viewer", granted_by=None)
        issued = issue_session(session, ws.id, viewer, 3600)
        session.commit()

        v = TestClient(app)
        v.cookies.set(SESSION_COOKIE, issued.token)
        resp = v.post(
            "/api/artifacts/uploads",
            json={"original_name": "x.txt", "media_type": "text/plain"},
            headers=HEADERS,
        )
        assert resp.status_code == 403

    def test_unauthenticated_upload_rejected(self, client: TestClient) -> None:
        resp = client.post(
            "/api/artifacts/uploads",
            json={"original_name": "x.txt", "media_type": "text/plain"},
            headers=HEADERS,
        )
        assert resp.status_code == 401


class TestVaultDirect:
    """Vault-level containment (no HTTP)."""

    def test_open_blob_never_leaves_root(self, tmp_path: Path) -> None:
        v = Vault(tmp_path)
        with pytest.raises(DomainError):
            v.open_blob(uuid.uuid4(), "../escape")
        with pytest.raises(DomainError):
            v.blob_path(uuid.uuid4(), "..")
