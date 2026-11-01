"""The browser fixture must never enable an insecure production secret store."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from studio.errors import DomainError, ErrorCode

ROOT = Path(__file__).resolve().parents[2]
ENTRY = ROOT / "tests/e2e/serve_api.py"
SPEC = importlib.util.spec_from_file_location("e2e_serve_api", ENTRY)
assert SPEC and SPEC.loader
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "[::1]"])
@pytest.mark.parametrize("scheme", ["postgresql", "postgresql+psycopg"])
def test_e2e_server_accepts_only_explicit_disposable_targets(host, scheme):
    fixture.require_disposable_database(f"{scheme}://studio:fixture@{host}:54329/studio_e2e")


@pytest.mark.parametrize(
    "database_url",
    [
        "",
        "sqlite:///studio_e2e",
        "postgresql://studio:fixture@127.0.0.1:54329/studio",
        "postgresql://studio:fixture@127.0.0.1:54329/studio_e2e_backup",
        "postgresql://studio:fixture@remote.example:54329/studio_e2e",
        "postgresql://studio:fixture@127.0.0.2:54329/studio_e2e",
        "postgresql://studio:fixture@127.0.0.1/studio_e2e",
        "postgresql://studio:fixture@127.0.0.1:5432/studio_e2e",
        "postgresql://studio:fixture@127.0.0.1:invalid/studio_e2e",
        "postgresql://studio:fixture@127.0.0.1:54329/studio_e2e?dbname=studio",
        "postgresql://studio:fixture@127.0.0.1:54329/studio_e2e?host=remote.example",
        "postgresql://studio:fixture@127.0.0.1:54329/studio_e2e#fragment",
    ],
)
def test_e2e_server_rejects_other_databases_without_echoing_dsn(database_url):
    with pytest.raises(RuntimeError, match="loopback PostgreSQL") as denied:
        fixture.require_disposable_database(database_url)
    assert "fixture@" not in str(denied.value)
    assert "remote.example" not in str(denied.value)


def test_memory_credentials_are_workspace_scoped_ephemeral_and_idempotently_deleted():
    store = fixture.MemorySecretStore()
    workspace, other_workspace, reference = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    store.put(workspace, reference, "synthetic-key")
    assert store.get(workspace, reference) == "synthetic-key"
    for missing in ((other_workspace, reference), (workspace, uuid.uuid4())):
        with pytest.raises(DomainError) as denied:
            store.get(*missing)
        assert denied.value.code == ErrorCode.CONFLICT
        assert "synthetic-key" not in str(denied.value)
    with pytest.raises(DomainError):
        fixture.MemorySecretStore().get(workspace, reference)
    store.delete(workspace, reference)
    store.delete(workspace, reference)
    with pytest.raises(DomainError):
        store.get(workspace, reference)


def test_entry_installs_same_store_before_both_consumers_and_never_uses_keychain():
    # A fresh interpreter proves the import order used by the actual shell entry;
    # running in pytest's process could hide already-bound production factories.
    program = '''
import runpy, sys, types, uuid
from studio.application.inference import secrets
def forbidden():
    raise AssertionError("production secret factory was called")
secrets.get_secret_store = forbidden
def run(app, **options):
    assert app == "studio.api.app:create_app"
    assert options == dict(factory=True, host="127.0.0.1", port=8790, workers=1, reload=False)
    import studio.api.app
    from studio.application.inference import runtime
    from studio.domain.inference import providers
    store = secrets.get_secret_store()
    assert runtime.get_secret_store() is store
    assert providers.get_secret_store() is store
    workspace, reference = uuid.uuid4(), uuid.uuid4()
    store.put(workspace, reference, "synthetic-key")
    assert runtime.get_secret_store().get(workspace, reference) == "synthetic-key"
    providers.get_secret_store().delete(workspace, reference)
sys.modules["uvicorn"] = types.SimpleNamespace(run=run)
runpy.run_path(sys.argv[1], run_name="__main__")
assert secrets.get_secret_store is forbidden
'''
    result = subprocess.run(  # noqa: S603 — fixed interpreter, inline fixture and repository path
        [sys.executable, "-c", program, str(ENTRY)],
        env={
            **os.environ,
            "STUDIO_DATABASE_URL": "postgresql://studio:fixture@127.0.0.1:54329/studio_e2e",
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_entry_refuses_already_imported_consumers(monkeypatch):
    monkeypatch.setenv(
        "STUDIO_DATABASE_URL", "postgresql://studio:fixture@127.0.0.1:54329/studio_e2e"
    )
    monkeypatch.setitem(sys.modules, "studio.domain.inference.providers", object())
    with pytest.raises(RuntimeError, match="before importing the API"):
        fixture.main()
