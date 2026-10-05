"""Keyset cursor codec (§8.1, AT-0104-2).

Cursors are opaque, self-validating and bound to the query they were
issued for: reusing a cursor across a different scope/filter/order is
rejected rather than silently misapplied.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from studio.errors import DomainError, ErrorCode

CURSOR_VERSION = 1


def scope_signature(*parts: Any) -> str:
    """Stable signature binding a cursor to scope + filter + order."""
    raw = json.dumps([str(p) for p in parts], separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def encode_cursor(kind: str, sig: str, key: tuple[datetime, uuid.UUID]) -> str:
    payload = {
        "v": CURSOR_VERSION,
        "k": kind,
        "s": sig,
        "key": [key[0].isoformat(), str(key[1])],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str, *, kind: str, sig: str) -> tuple[datetime, uuid.UUID]:
    """Decode + bind-check a cursor. Mismatched reuse → VALIDATION."""
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if payload.get("v") != CURSOR_VERSION:
            raise ValueError("version")
        if payload.get("k") != kind or payload.get("s") != sig:
            raise ValueError("scope")
        ts = datetime.fromisoformat(payload["key"][0])
        rid = uuid.UUID(payload["key"][1])
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise DomainError(
            ErrorCode.VALIDATION,
            "cursor does not match this query (scope, filter or order changed)",
            field_path="after",
        ) from exc
    return ts, rid
