"""Minimal audit trail (§21.3).

One row per audited action: actor, action, target, timestamp and a
small structured detail. Never prompts, formulas, spectra, documents,
tokens or secret material — payloads stay out of the audit log by
contract, not by redaction.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext
from studio.persistence.models import AuditEvent

# Keys that would carry sensitive content if they ever appeared in a
# detail dict — dropped before persist (belt over the "minimal by
# contract" rule).
_SENSITIVE_KEYS = frozenset(
    {"token", "password", "secret", "payload", "document", "formula", "spectrum"}
)


def _clean(detail: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop sensitive keys at ANY depth and scrub NUL bytes out of
    string values — a nested ``{"envelope": {"token": …}}`` is just as
    persisted as a top-level one (CS-1101), and a NUL inside a value
    would crash the jsonb insert."""
    if detail is None:
        return None

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {
                k: walk(v)
                for k, v in node.items()
                if not (isinstance(k, str) and k.lower() in _SENSITIVE_KEYS)
            }
        if isinstance(node, (list, tuple)):
            return type(node)(walk(v) for v in node)
        if isinstance(node, str):
            return node.replace("\x00", "")
        return node

    cleaned = walk(detail)
    return cleaned if isinstance(cleaned, dict) else None


def record(
    db: Session,
    ctx: ServiceContext,
    *,
    action: str,
    target_type: str,
    target_id: uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        workspace_id=ctx.workspace_id,
        actor_id=ctx.principal_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=_clean(detail),
    )
    db.add(event)
    db.flush()
    return event
