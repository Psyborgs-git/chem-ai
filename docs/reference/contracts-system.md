# Health, readiness and desktop API — JSON contract details

These excerpts are generated from the implementation without importing it. They specify accepted fields, conditional validation, defaults and response construction for flexible JSON interfaces. They complement the endpoint prose; implementation expressions refer to the named source service rather than a live execution.

## healthz

Source: `services/studio-api/src/studio/api/app.py:healthz`.

```python
    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}
```

## readyz

Source: `services/studio-api/src/studio/api/app.py:readyz`.

```python
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
```

## desktop_runtime

Source: `services/studio-api/src/studio/api/desktop.py:desktop_runtime`.

```python
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
```
