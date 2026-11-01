"""Disposable browser-test API with process-only synthetic provider credentials.

Production deliberately requires macOS Keychain. Browser journeys instead use
this entry point on every platform; nothing here is packaged with the app.
"""

from __future__ import annotations

import os
import sys
import threading
import uuid
from unittest.mock import patch
from urllib.parse import urlsplit


class MemorySecretStore:
    """A workspace-scoped fixture whose contents disappear with this process."""

    def __init__(self) -> None:
        self._values: dict[tuple[uuid.UUID, uuid.UUID], str] = {}
        self._lock = threading.Lock()

    def put(self, workspace_id: uuid.UUID, reference: uuid.UUID, secret: str) -> None:
        with self._lock:
            self._values[workspace_id, reference] = secret

    def get(self, workspace_id: uuid.UUID, reference: uuid.UUID) -> str:
        with self._lock:
            value = self._values.get((workspace_id, reference))
        if value is None:
            from studio.errors import DomainError, ErrorCode

            raise DomainError(
                ErrorCode.CONFLICT, "synthetic test credential is unavailable", field_path="apiKey"
            )
        return value

    def delete(self, workspace_id: uuid.UUID, reference: uuid.UUID) -> None:
        with self._lock:
            self._values.pop((workspace_id, reference), None)


def require_disposable_database(database_url: str) -> None:
    """Reject user databases and DSN query options that could override the target."""
    message = "E2E API requires a loopback PostgreSQL database at port 54329 named studio_e2e"
    try:
        target = urlsplit(database_url)
        allowed = (
            target.scheme in {"postgresql", "postgresql+psycopg"}
            and target.hostname in {"127.0.0.1", "localhost", "::1"}
            and target.port == 54329
            and target.path == "/studio_e2e"
            and not target.query
            and not target.fragment
        )
    except ValueError:
        raise RuntimeError(message) from None
    if not allowed:
        raise RuntimeError(message)


def main() -> None:
    require_disposable_database(os.environ.get("STUDIO_DATABASE_URL", ""))
    consumers = (
        "studio.api.app",
        "studio.application.inference.runtime",
        "studio.domain.inference.providers",
    )
    if any(name in sys.modules for name in consumers):
        raise RuntimeError("E2E credentials must be installed before importing the API")

    import uvicorn

    from studio.application.inference import secrets

    # A single worker keeps the credential lifetime identical to the API process.
    # No reload subprocess may re-import the production credential factory.
    store = MemorySecretStore()
    with patch.object(secrets, "get_secret_store", new=lambda: store):
        uvicorn.run(
            "studio.api.app:create_app",
            factory=True,
            host="127.0.0.1",
            port=8790,
            workers=1,
            reload=False,
        )


if __name__ == "__main__":
    main()
