"""Session endpoints (transport-level, §21.2).

Session establishment/teardown is intentionally a narrow HTTP surface —
domain operations go through GraphQL commands.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.api.deps import SESSION_COOKIE, DbSession, build_context
from studio.auth.sessions import issue_session, revoke_session
from studio.auth.setup import (
    authenticate_password,
    create_owner,
    workspace_has_owner,
)
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import Workspace

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


class SetupRequest(BaseModel):
    login: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=10)


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1)


def _default_workspace(db: Session) -> Workspace:
    """Single-workspace loopback deployment (E04): the only workspace is
    created at bootstrap; multi-workspace is a later, reviewed change."""
    ws = db.execute(select(Workspace).order_by(Workspace.created_at).limit(1)).scalar_one_or_none()
    if ws is None:
        ws = Workspace(slug="default", display_name="Chemistry Studio")
        db.add(ws)
        db.flush()
    return ws


def _set_cookie(response: Response, token: str, expires_at: datetime) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        expires=expires_at,
        httponly=True,
        secure=False,  # loopback http; TLS deployments flip this on
        samesite="strict",
        path="/",
    )


@auth_router.post("/setup")
def setup_owner(
    body: SetupRequest, request: Request, response: Response, db: DbSession
) -> dict[str, Any]:
    settings = request.app.state.settings
    ws = _default_workspace(db)
    if workspace_has_owner(db, ws.id):
        raise DomainError(ErrorCode.CONFLICT, "owner already configured")
    principal = create_owner(db, ws, body.login, body.display_name, body.password)
    issued = issue_session(db, ws.id, principal, settings.session_ttl_seconds)
    db.commit()
    _set_cookie(response, issued.token, issued.expires_at)
    return {"status": "owner_configured", "expiresAt": issued.expires_at}


@auth_router.post("/login")
def login(
    body: LoginRequest, request: Request, response: Response, db: DbSession
) -> dict[str, Any]:
    settings = request.app.state.settings
    ws = _default_workspace(db)
    principal = authenticate_password(db, ws.id, body.login, body.password)
    issued = issue_session(db, ws.id, principal, settings.session_ttl_seconds)
    db.commit()
    _set_cookie(response, issued.token, issued.expires_at)
    return {"status": "authenticated", "expiresAt": issued.expires_at}


@auth_router.post("/logout")
def logout(request: Request, response: Response, db: DbSession) -> dict[str, Any]:
    ctx = build_context(request, db)
    if ctx.auth_session_id is not None:
        revoke_session(db, ctx.workspace_id, ctx.auth_session_id)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "logged_out"}


@auth_router.get("/setup-needed")
def setup_needed(request: Request, db: DbSession) -> dict[str, Any]:
    ws = db.execute(select(Workspace).order_by(Workspace.created_at).limit(1)).scalar_one_or_none()
    needed = ws is None or not workspace_has_owner(db, ws.id)
    return {"setupNeeded": needed}
