"""No plaintext fallback or credential-bearing diagnostics."""

from __future__ import annotations

import uuid

import pytest

from studio.application.inference.secrets import UnavailableSecretStore, get_secret_store
from studio.errors import DomainError, ErrorCode


def test_unsupported_platform_fails_explicitly_without_plaintext_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("studio.application.inference.secrets.platform.system", lambda: "Linux")
    get_secret_store.cache_clear()
    try:
        store = get_secret_store()
        assert isinstance(store, UnavailableSecretStore)
        workspace_id, reference = uuid.uuid4(), uuid.uuid4()
        for operation in (
            lambda: store.put(workspace_id, reference, "deliberately-fake-key-for-test"),
            lambda: store.get(workspace_id, reference),
            lambda: store.delete(workspace_id, reference),
        ):
            with pytest.raises(DomainError) as denied:
                operation()
            assert denied.value.code == ErrorCode.CONFLICT
            assert denied.value.field_path == "apiKey"
            assert "deliberately-fake-key" not in str(denied.value)
    finally:
        get_secret_store.cache_clear()
