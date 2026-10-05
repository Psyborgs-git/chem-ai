"""Loopback transport security (handoff §21.2, AT-0102-2).

- Host header must identify the configured loopback bind address.
- State-changing methods require an absent, same-origin, or explicitly
  allowlisted Origin — a foreign Origin means rejection with no state
  change.
- Health endpoints stay readable; everything else still requires a
  session at the service layer.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from studio.config.settings import Settings

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def _host_allowed(host_header: str | None, settings: Settings) -> bool:
    if not host_header:
        return False
    host = host_header.split(":", 1)[0].lower()
    if host_header.startswith("[::1]"):
        host = "[::1]"
    return host in _LOOPBACK_HOSTS


def _origin_allowed(origin: str | None, settings: Settings) -> bool:
    if origin is None or origin == "null":
        # Non-browser clients may omit Origin; "null" (sandboxed frames)
        # is treated as absent.
        return True
    return origin in settings.allowed_origins


class LoopbackSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if not _host_allowed(request.headers.get("host"), self._settings):
            return JSONResponse(
                {"errors": [{"code": "FORBIDDEN", "message": "host not permitted"}]},
                status_code=403,
            )
        if request.method not in _SAFE_METHODS:
            origin = request.headers.get("origin")
            if not _origin_allowed(origin, self._settings):
                return JSONResponse(
                    {
                        "errors": [
                            {
                                "code": "FORBIDDEN",
                                "message": "cross-origin commands are rejected",
                            }
                        ]
                    },
                    status_code=403,
                )
        return await call_next(request)
