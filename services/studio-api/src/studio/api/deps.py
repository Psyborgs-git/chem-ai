"""Shared request dependencies: session cookie → ServiceContext."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from studio.auth.context import ServiceContext, load_context
from studio.auth.sessions import authenticate_token
from studio.config.settings import Settings
from studio.errors import DomainError, ErrorCode

SESSION_COOKIE = "studio_session"


def get_session_factory(request: Request) -> sessionmaker[Session]:
    factory: sessionmaker[Session] = request.app.state.session_factory
    return factory


def get_db_session(request: Request) -> Session:
    return get_session_factory(request)()


def db_session(request: Request) -> Iterator[Session]:
    """Request-scoped session with guaranteed close (FastAPI Depends)."""
    db = get_db_session(request)
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(db_session)]


def request_context(request: Request, db: DbSession) -> ServiceContext:
    """FastAPI dependency: authenticated ServiceContext or 401."""
    return build_context(request, db)


Ctx = Annotated[ServiceContext, Depends(request_context)]


def extract_token(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        return token
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def token_workspace(db: Session, token: str) -> uuid.UUID:
    """Internal: resolve workspace for a token before full auth."""
    from sqlalchemy import select

    from studio.auth.sessions import _hash
    from studio.persistence.models import AuthSession

    row = db.execute(
        select(AuthSession.workspace_id).where(AuthSession.token_hash == _hash(token))
    ).scalar_one_or_none()
    if row is None:
        raise DomainError(ErrorCode.UNAUTHENTICATED, "invalid session")
    return row


def build_context(request: Request, db: Session) -> ServiceContext:
    token = extract_token(request)
    if not token:
        raise DomainError(ErrorCode.UNAUTHENTICATED, "session required")
    workspace_id = token_workspace(db, token)
    auth_session = authenticate_token(db, workspace_id, token)
    # Commit the last_seen_at heartbeat immediately. Held open for the
    # whole request transaction it is an exclusive auth_sessions row lock:
    # a second concurrent request from the same principal blocks on it —
    # and since sync DB calls run on the event loop, that wait wedges the
    # server while the first request can never finish serializing.
    db.commit()
    return load_context(
        db,
        workspace_id,
        auth_session.principal_id,
        auth_session_id=auth_session.id,
    )


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings
