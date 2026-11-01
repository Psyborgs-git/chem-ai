"""Credential lifecycle, metadata redaction and scoped provider commands."""

from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from studio.application.agent_tools.registry import AgentTool, ToolDispatcher, ToolRegistry
from studio.auth.context import ServiceContext, load_context
from studio.domain.inference.providers import ProviderService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    InferenceCredential,
    InferenceProvider,
    Principal,
    PrincipalCapability,
    Workspace,
)

pytestmark = pytest.mark.integration
SECRET = "fake-provider-credential-sentinel-0123456789"  # noqa: S105 — deliberate leak-test sentinel


class MemorySecretStore:
    """Test-only storage; production has no plaintext fallback."""

    def __init__(self) -> None:
        self.values: dict[tuple[uuid.UUID, uuid.UUID], str] = {}
        self.fail_put = False
        self.fail_delete = False
        self.lock = threading.Lock()

    def put(self, workspace_id: uuid.UUID, reference: uuid.UUID, secret: str) -> None:
        if self.fail_put:
            raise DomainError(
                ErrorCode.CONFLICT, "secure API key storage is unavailable", field_path="apiKey"
            )
        with self.lock:
            self.values[workspace_id, reference] = secret

    def get(self, workspace_id: uuid.UUID, reference: uuid.UUID) -> str:
        with self.lock:
            return self.values[workspace_id, reference]

    def delete(self, workspace_id: uuid.UUID, reference: uuid.UUID) -> None:
        if self.fail_delete:
            raise DomainError(ErrorCode.CONFLICT, "Keychain is locked", field_path="apiKey")
        with self.lock:
            self.values.pop((workspace_id, reference), None)


def _context(db: Session, role: str = "owner", kind: str = "user") -> ServiceContext:
    workspace = Workspace(slug=uuid.uuid4().hex, display_name="Provider tests")
    db.add(workspace)
    db.flush()
    principal = Principal(workspace_id=workspace.id, login="owner", display_name="Owner", kind=kind)
    db.add(principal)
    db.flush()
    for capability in capabilities_for_role(role):
        db.add(
            PrincipalCapability(
                workspace_id=workspace.id, principal_id=principal.id, capability=capability
            )
        )
    db.commit()
    return load_context(db, workspace.id, principal.id)


def _settings(**changes: Any) -> dict[str, Any]:
    return {
        "name": "My local model",
        "kind": "openai_compatible",
        "base_url": "http://127.0.0.1:12345/v1",
        "model": "local-test-model",
        "enabled": True,
        **changes,
    }


def test_create_replay_edit_replace_clear_delete_never_persists_key(session: Session) -> None:
    store = MemorySecretStore()
    service = ProviderService(session, _context(session), store)
    row = service.save(**_settings(api_key=SECRET, client_mutation_id="create-1"))
    original_id, original_ref = row.id, row.credential_ref
    assert store.get(service.ctx.workspace_id, original_ref) == SECRET
    replay = service.save(**_settings(api_key=SECRET, client_mutation_id="create-1"))
    assert replay.id == original_id
    assert len(store.values) == 1
    with pytest.raises(DomainError) as mismatch:
        service.save(**_settings(api_key=SECRET + "changed", client_mutation_id="create-1"))
    assert mismatch.value.code == ErrorCode.IDEMPOTENCY_MISMATCH
    row = service.save(**_settings(provider_id=row.id, expected_revision=1, api_key=""))
    assert row.credential_ref == original_ref
    with pytest.raises(DomainError, match="destination"):
        service.save(
            **_settings(
                provider_id=row.id, expected_revision=2, base_url="http://127.0.0.1:12345/other"
            )
        )
    row = service.save(
        **_settings(provider_id=row.id, expected_revision=2, api_key=SECRET + "-replacement")
    )
    assert row.credential_ref != original_ref
    assert (service.ctx.workspace_id, original_ref) not in store.values
    # Sentinel cannot be found in configuration, audit, idempotency or outbox.
    for table in (
        "inference_providers",
        "inference_credentials",
        "idempotency_records",
        "outbox_events",
        "audit_events",
    ):
        encoded = session.execute(
            text(f"SELECT coalesce(json_agg(t)::text,'') FROM {table} t")  # noqa: S608 — fixed table allowlist
        ).scalar_one()
        assert SECRET not in encoded
    row = service.save(**_settings(provider_id=row.id, expected_revision=3, clear_api_key=True))
    assert row.credential_ref is None
    assert store.values == {}
    assert service.delete(row.id, 4) is False
    assert session.query(InferenceProvider).count() == 0
    assert session.query(InferenceCredential).count() == 0


def test_keychain_write_failure_leaves_no_provider_or_untracked_key(session: Session) -> None:
    store = MemorySecretStore()
    store.fail_put = True
    service = ProviderService(session, _context(session), store)
    with pytest.raises(DomainError) as failure:
        service.save(**_settings(api_key=SECRET))
    assert failure.value.field_path == "apiKey"
    assert SECRET not in str(failure.value)
    assert session.query(InferenceProvider).count() == 0
    assert session.query(InferenceCredential).count() == 0
    assert not store.values


def test_failed_key_write_cleanup_is_visible_and_retryable(session: Session) -> None:
    store = MemorySecretStore()
    service = ProviderService(session, _context(session), store)
    store.fail_put = True
    store.fail_delete = True
    with pytest.raises(DomainError):
        service.save(**_settings(api_key=SECRET))
    assert service.cleanup_pending() is True
    assert session.query(InferenceProvider).count() == 0
    assert session.query(InferenceCredential).one().state == "retired"
    store.fail_delete = False
    assert service.cleanup_credentials() is False
    assert service.cleanup_pending() is False


def test_database_failure_after_keychain_write_is_compensated(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MemorySecretStore()
    service = ProviderService(session, _context(session), store)
    original_commit = session.commit
    calls = 0

    def commit() -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise SQLAlchemyError("injected metadata commit failure")
        original_commit()

    monkeypatch.setattr(session, "commit", commit)
    with pytest.raises(SQLAlchemyError):
        service.save(**_settings(api_key=SECRET))
    assert session.query(InferenceProvider).count() == 0
    assert session.query(InferenceCredential).count() == 0
    assert not store.values


def test_failed_secret_cleanup_remains_durable_and_retryable(session: Session) -> None:
    store = MemorySecretStore()
    service = ProviderService(session, _context(session), store)
    row = service.save(**_settings(api_key=SECRET))
    reference = row.credential_ref
    store.fail_delete = True
    assert service.delete(row.id, row.version) is True
    assert session.query(InferenceProvider).count() == 0
    intent = session.get(InferenceCredential, reference)
    assert intent is not None and intent.state == "retired"
    assert len(store.values) == 1
    assert service.cleanup_pending() is True
    store.fail_delete = False
    assert service.cleanup_credentials() is False
    assert service.cleanup_pending() is False
    assert not store.values
    assert session.query(InferenceCredential).count() == 0


@pytest.mark.parametrize(
    "role,kind", [("researcher", "user"), ("viewer", "user"), ("owner", "agent")]
)
def test_nonadministrator_cannot_mutate_or_test_providers(
    session: Session, role: str, kind: str
) -> None:
    store = MemorySecretStore()
    service = ProviderService(session, _context(session, role, kind), store)
    for operation in (
        lambda: service.save(**_settings(api_key=SECRET)),
        lambda: service.delete(uuid.uuid4(), 1),
        lambda: service.test(uuid.uuid4()),
    ):
        with pytest.raises(DomainError) as denied:
            operation()
        assert denied.value.code == ErrorCode.FORBIDDEN
    assert session.query(InferenceCredential).count() == 0
    assert not store.values


def test_foreign_workspace_cannot_read_provider_or_rebind_credential(session: Session) -> None:
    store = MemorySecretStore()
    service = ProviderService(session, _context(session), store)
    row = service.save(**_settings(api_key=SECRET))
    other = ProviderService(session, _context(session), store)
    assert other.list() == []
    with pytest.raises(DomainError) as missing:
        other.get(row.id)
    assert missing.value.code == ErrorCode.NOT_FOUND
    with pytest.raises(DomainError):
        other.save(**_settings(provider_id=row.id, expected_revision=1, api_key=SECRET))
    assert len(store.values) == 1
    assert next(iter(store.values))[0] == service.ctx.workspace_id


@pytest.mark.parametrize(
    "key",
    ["short", "bad\r\nAuthorization:key", "bad\x00keyvalue", "x" * 8193],
    ids=["too-short", "header-injection", "nul", "oversized"],
)
def test_invalid_credentials_rejected_before_secure_storage(session: Session, key: str) -> None:
    store = MemorySecretStore()
    service = ProviderService(session, _context(session), store)
    with pytest.raises(DomainError) as invalid:
        service.save(**_settings(api_key=key))
    assert invalid.value.code == ErrorCode.VALIDATION
    assert not store.values
    assert session.query(InferenceCredential).count() == 0


def test_concurrent_uncertain_create_replay_creates_one_provider(db_url: str) -> None:
    engine = create_engine(db_url)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as setup:
        ctx = _context(setup)
        workspace_id, principal_id = ctx.workspace_id, ctx.principal_id
    store = MemorySecretStore()

    def save() -> uuid.UUID:
        with factory() as db:
            service = ProviderService(db, load_context(db, workspace_id, principal_id), store)
            return service.save(**_settings(api_key=SECRET, client_mutation_id="same-create")).id

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(lambda _: save(), range(2)))
        assert ids[0] == ids[1]
        with factory() as check:
            assert check.query(InferenceProvider).count() == 1
            assert check.query(InferenceCredential).count() == 1
        assert len(store.values) == 1
        assert SECRET not in json.dumps([str(value) for value in ids])
    finally:
        engine.dispose()


def test_unexpected_tool_failure_rolls_back_partial_writes_and_redacts_error(
    session: Session,
) -> None:
    ctx = _context(session)

    def broken(db: Session, _ctx: ServiceContext, _args: dict[str, Any]) -> dict[str, Any]:
        db.add(
            InferenceProvider(
                workspace_id=ctx.workspace_id,
                name="must roll back",
                kind="openai_compatible",
                base_url="http://127.0.0.1:1234/v1",
                model="fixture",
                enabled=False,
            )
        )
        db.flush()
        raise RuntimeError("private exception echo " + SECRET)

    registry = ToolRegistry(
        [AgentTool("broken_fixture", "Atomic failure test", {"type": "object"}, broken)]
    )
    result = ToolDispatcher(session, ctx, registry=registry).call("broken_fixture", {})
    assert result == {
        "ok": False,
        "error": {
            "code": "TOOL_EXECUTION_FAILED",
            "message": "tool execution failed; no partial changes were applied",
        },
    }
    assert SECRET not in json.dumps(result)
    session.commit()
    assert session.query(InferenceProvider).count() == 0
