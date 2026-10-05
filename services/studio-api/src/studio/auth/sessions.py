"""Session issuance and verification (§21.2).

Tokens are opaque (URL-safe random); only their sha256 hash is stored.
No credentials are ever logged. Sessions expire and can be revoked.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from studio.errors import DomainError, ErrorCode
from studio.persistence.models import AuthSession, Principal


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IssuedSession:
    session_id: uuid.UUID
    token: str  # returned exactly once to the caller
    expires_at: datetime


def issue_session(
    db: Session,
    workspace_id: uuid.UUID,
    principal: Principal,
    ttl_seconds: int,
) -> IssuedSession:
    token = secrets.token_urlsafe(32)
    row = AuthSession(
        workspace_id=workspace_id,
        principal_id=principal.id,
        token_hash=_hash(token),
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
    )
    db.add(row)
    db.flush()
    return IssuedSession(session_id=row.id, token=token, expires_at=row.expires_at)


def authenticate_token(db: Session, workspace_id: uuid.UUID, token: str) -> AuthSession:
    """Resolve a bearer/cookie token to a live session in this workspace."""
    now = datetime.now(UTC)
    row = db.execute(
        select(AuthSession).where(
            AuthSession.token_hash == _hash(token),
            AuthSession.workspace_id == workspace_id,
            AuthSession.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    if row is None:
        raise DomainError(ErrorCode.UNAUTHENTICATED, "invalid session")
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires <= now:
        raise DomainError(ErrorCode.UNAUTHENTICATED, "session expired")
    db.execute(update(AuthSession).where(AuthSession.id == row.id).values(last_seen_at=now))
    return row


def revoke_session(db: Session, workspace_id: uuid.UUID, session_id: uuid.UUID) -> None:
    db.execute(
        update(AuthSession)
        .where(
            AuthSession.id == session_id,
            AuthSession.workspace_id == workspace_id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
