"""ASGI application factory for the core profile.

Health/readiness endpoints expose no sensitive payload (handoff §8.1).
The GraphQL app is mounted from ``studio.api.graphql``; transfers live
under ``studio.api.transfers``.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from studio.config.settings import Settings, get_settings
from studio.errors import DomainError, ErrorCode


def _status_for(code: ErrorCode) -> int:
    return {
        ErrorCode.UNAUTHENTICATED: 401,
        ErrorCode.FORBIDDEN: 403,
        ErrorCode.NOT_FOUND: 404,
        ErrorCode.REVISION_CONFLICT: 409,
        ErrorCode.IDEMPOTENCY_MISMATCH: 409,
        ErrorCode.APPROVAL_STALE: 409,
        ErrorCode.APPROVAL_EXPIRED: 409,
        ErrorCode.CONFLICT: 409,
        ErrorCode.VALIDATION: 422,
    }.get(code, 422)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Chemistry Studio",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings

    from studio.api.security import LoopbackSecurityMiddleware

    app.add_middleware(LoopbackSecurityMiddleware, settings=settings)

    @app.exception_handler(DomainError)
    async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse({"errors": [exc.to_dict()]}, status_code=_status_for(exc.code))

    @app.middleware("http")
    async def close_request_db(request: Request, call_next):  # type: ignore[no-untyped-def]
        """GraphQL opens a request-scoped session (studio_db); guarantee
        its close whatever the outcome."""
        try:
            return await call_next(request)
        finally:
            db = getattr(request.state, "studio_db", None)
            if db is not None:
                db.close()

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz(request: Request) -> JSONResponse:
        # Readiness reports *capabilities*, never secrets or paths.
        from studio.api.capabilities import collect_capabilities

        caps = collect_capabilities(request.app.state.settings)
        return JSONResponse(
            {
                "status": "ready",
                "profiles": caps["profiles"],
                "database": caps["database"],
            }
        )

    from studio.persistence.engine import make_engine, make_session_factory

    engine = make_engine(settings.database_url)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)

    from studio.api.auth_routes import auth_router

    app.include_router(auth_router)

    from studio.api.graphql.schema import graphql_app

    app.include_router(graphql_app(settings), prefix="/graphql")

    from studio.api.transfers.routes import transfer_router

    app.include_router(transfer_router, prefix="/api/artifacts")

    from studio.api.events.routes import events_router

    app.include_router(events_router, prefix="/api/events")

    return app
