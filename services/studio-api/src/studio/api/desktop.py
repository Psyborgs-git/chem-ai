"""Opt-in same-origin web assets for the machine-local native shell.

Only a built frontend directory is exposed. Existing API routes take
precedence, and their namespace can never fall through to the SPA.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from studio.config.settings import Settings

_API_PREFIXES = {"api", "graphql", "healthz", "readyz"}


def _database_ready(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            # The shell also requires a successful migration command before
            # launch. This probe catches a stopped DB or a missing schema when
            # reusing an already-running desktop API.
            connection.execute(text("SET LOCAL statement_timeout = '2000ms'"))
            return (
                connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
                is not None
            )
    except SQLAlchemyError:
        return False


class DesktopWeb(StaticFiles):
    """StaticFiles' realpath containment plus a restricted HTML fallback."""

    def __init__(self, root: Path) -> None:
        super().__init__(directory=root, html=False, follow_symlink=False)
        self._root = root

    async def get_response(self, path: str, scope: Scope) -> Response:
        # Backslashes are not path separators on macOS, but rejecting them
        # makes containment independent of the platform and proxy decoding.
        path = "" if path == "." else path
        parts = path.split("/")
        if (
            "\\" in path
            or "\x00" in path
            or any(part.startswith(".") for part in parts)
            or parts[0] in _API_PREFIXES
        ):
            raise HTTPException(status_code=404)
        candidate = self._root / path
        try:
            contained = candidate.resolve().is_relative_to(self._root)
        except (OSError, RuntimeError):
            contained = False
        if not contained:
            raise HTTPException(status_code=404)

        requested_index = path in {"", "index.html"}
        try:
            response = await super().get_response("index.html" if requested_index else path, scope)
        except HTTPException as exc:
            accepts = Headers(scope=scope).get("accept", "*/*")
            if (
                exc.status_code != 404
                or Path(path).suffix
                or candidate.is_dir()
                or not ("text/html" in accepts or "*/*" in accepts)
            ):
                raise
            response = await super().get_response("index.html", scope)
            requested_index = True

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        if requested_index:
            response.headers["Cache-Control"] = "no-store"
        return response


def mount_desktop_web(app: FastAPI, settings: Settings) -> None:
    configured = settings.desktop_frontend_dir
    if configured is None:
        return
    if not configured.is_absolute():
        raise ValueError("STUDIO_DESKTOP_FRONTEND_DIR must be an absolute built frontend directory")
    root = configured.resolve()
    vault = settings.vault_root.resolve()
    if root.is_relative_to(vault) or vault.is_relative_to(root):
        raise ValueError("desktop frontend and private vault directories must not overlap")
    index = root / "index.html"
    if not root.is_dir() or not index.is_file() or not index.resolve().is_relative_to(root):
        raise ValueError("desktop frontend directory must contain its own built index.html")

    @app.get("/api/desktop/runtime", include_in_schema=False)
    def desktop_runtime(request: Request) -> JSONResponse:
        # Stable identity probe for the shell; deliberately no local paths,
        # database credentials, session identity, or unverified readiness.
        frontend_available = index.is_file() and index.resolve().is_relative_to(root)
        database_ready = _database_ready(request.app.state.engine)
        payload = {
            "application": "chemistry-studio",
            "desktop": True,
            "frontendAvailable": frontend_available,
            "databaseReady": database_ready,
        }
        if settings.desktop_build_id:
            payload["buildId"] = settings.desktop_build_id
        return JSONResponse(
            payload,
            status_code=200 if frontend_available and database_ready else 503,
            headers={"Cache-Control": "no-store"},
        )

    app.mount("/", DesktopWeb(root), name="desktop-web")
