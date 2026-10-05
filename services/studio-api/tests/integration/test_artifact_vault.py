"""CS-0103 acceptance tests — artifact vault lifecycle.

AT-0103-2  interrupted upload retried with same identity → one committed
           artifact with a verified checksum, no duplicate effects
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from studio.api.app import create_app
from studio.config.settings import Settings

pytestmark = pytest.mark.integration

HEADERS = {"origin": "http://127.0.0.1:8787", "host": "127.0.0.1:8787"}
PAYLOAD = b"sample,result\nA-1,0.42\nB-2,0.98\n"


@pytest.fixture()
def app(db_url: str, tmp_path: Path) -> FastAPI:
    return create_app(Settings(database_url=db_url, vault_root=tmp_path))


@pytest.fixture()
def authed(app: FastAPI) -> TestClient:
    client = TestClient(app)
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


def _initiate(client: TestClient, **kw) -> str:
    body = {"original_name": "results.csv", "media_type": "text/csv"}
    body.update(kw)
    resp = client.post("/api/artifacts/uploads", json=body, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()["artifactId"]


def _finish(client: TestClient, aid: str, **kw) -> dict:
    resp = client.post(f"/api/artifacts/uploads/{aid}/finish", json=kw or {}, headers=HEADERS)
    return resp


class TestIdempotentFinish:
    """AT-0103-2."""

    def test_retried_completion_returns_one_committed_artifact(
        self, authed: TestClient, tmp_path: Path
    ) -> None:
        aid = _initiate(
            authed,
            declared_checksum=hashlib.sha256(PAYLOAD).hexdigest(),
        )
        put = authed.put(f"/api/artifacts/uploads/{aid}/content", content=PAYLOAD, headers=HEADERS)
        assert put.status_code == 200, put.text

        first = _finish(authed, aid)
        assert first.status_code == 200, first.text
        second = _finish(authed, aid)
        assert second.status_code == 200, second.text
        a, b = first.json(), second.json()
        assert a["artifactId"] == b["artifactId"] == aid
        assert a["checksumSha256"] == b["checksumSha256"]
        assert a["checksumSha256"] == hashlib.sha256(PAYLOAD).hexdigest()
        assert a["uploadState"] == "committed"

        # Exactly one committed blob exists in the vault.
        blobs = [p for p in (tmp_path / "blobs").rglob("*") if p.is_file()]
        assert len(blobs) == 1
        assert blobs[0].read_bytes() == PAYLOAD
        # Staging is gone.
        assert list((tmp_path / ".staging").rglob("*.part")) == []

    def test_finish_with_conflicting_checksum_fails(self, authed: TestClient) -> None:
        aid = _initiate(authed)
        authed.put(f"/api/artifacts/uploads/{aid}/content", content=PAYLOAD, headers=HEADERS)
        _finish(authed, aid)
        again = _finish(authed, aid, checksum="0" * 64)
        assert again.status_code == 409


class TestUploadLifecycle:
    def test_bytes_roundtrip_and_checksum_header(self, authed: TestClient) -> None:
        aid = _initiate(authed)
        authed.put(f"/api/artifacts/uploads/{aid}/content", content=PAYLOAD, headers=HEADERS)
        _finish(authed, aid)
        dl = authed.get(f"/api/artifacts/{aid}/content", headers=HEADERS)
        assert dl.status_code == 200, dl.text
        assert dl.content == PAYLOAD
        assert dl.headers["X-Content-SHA256"] == hashlib.sha256(PAYLOAD).hexdigest()
        # Opaque filename — original name not disclosed in disposition.
        assert "report" not in dl.headers["Content-Disposition"]

    def test_declared_checksum_mismatch_aborts(self, authed: TestClient, tmp_path: Path) -> None:
        aid = _initiate(authed, declared_checksum="1" * 64)
        authed.put(f"/api/artifacts/uploads/{aid}/content", content=PAYLOAD, headers=HEADERS)
        resp = _finish(authed, aid)
        assert resp.status_code == 422
        # Staging discarded; nothing committed.
        assert list((tmp_path / ".staging").rglob("*.part")) == []
        meta = authed.get(f"/api/artifacts/{aid}", headers=HEADERS)
        assert meta.json()["uploadState"] == "aborted"

    def test_finish_without_bytes_fails(self, authed: TestClient) -> None:
        aid = _initiate(authed)
        resp = _finish(authed, aid)
        assert resp.status_code == 422

    def test_abort_discards_staging(self, authed: TestClient, tmp_path: Path) -> None:
        aid = _initiate(authed)
        authed.put(f"/api/artifacts/uploads/{aid}/content", content=b"partial", headers=HEADERS)
        resp = authed.post(f"/api/artifacts/uploads/{aid}/abort", headers=HEADERS)
        assert resp.status_code == 200
        assert list((tmp_path / ".staging").rglob("*.part")) == []

    def test_declared_size_over_cap_rejected(self, db_url: str, tmp_path: Path) -> None:
        small = create_app(Settings(database_url=db_url, vault_root=tmp_path, artifact_max_bytes=4))
        client = TestClient(small)
        client.post(
            "/api/auth/setup",
            json={
                "login": "owner",
                "display_name": "Owner",
                "password": "correct horse battery staple",
            },
            headers=HEADERS,
        )
        resp = client.post(
            "/api/artifacts/uploads",
            json={
                "original_name": "big.bin",
                "media_type": "application/octet-stream",
                "declared_size": 10,
            },
            headers=HEADERS,
        )
        assert resp.status_code == 422

    def test_stream_over_cap_aborts_early(self, db_url: str, tmp_path: Path) -> None:
        small = create_app(Settings(database_url=db_url, vault_root=tmp_path, artifact_max_bytes=4))
        client = TestClient(small)
        client.post(
            "/api/auth/setup",
            json={
                "login": "owner",
                "display_name": "Owner",
                "password": "correct horse battery staple",
            },
            headers=HEADERS,
        )
        aid = _initiate(client, original_name="b.bin", media_type="application/octet-stream")
        resp = client.put(
            f"/api/artifacts/uploads/{aid}/content",
            content=b"more than four bytes",
            headers=HEADERS,
        )
        assert resp.status_code == 422

    def test_rights_default_to_unknown(self, authed: TestClient) -> None:
        aid = _initiate(authed)
        meta = authed.get(f"/api/artifacts/{aid}", headers=HEADERS)
        assert meta.status_code == 200
        assert meta.json()["rights"] == {
            "retrieval": "unknown",
            "extraction": "unknown",
            "training": "unknown",
            "export": "unknown",
            "redistribution": "unknown",
        }
        assert meta.json()["reviewState"] == "quarantined"
