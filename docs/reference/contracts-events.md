# Event stream API — JSON contract details

These excerpts are generated from the implementation without importing it. They specify accepted fields, conditional validation, defaults and response construction for flexible JSON interfaces. They complement the endpoint prose; implementation expressions refer to the named source service rather than a live execution.

## snapshot

Source: `services/studio-api/src/studio/api/events/routes.py:snapshot`.

```python
@events_router.get("/snapshot")
def snapshot(request: Request, channel: str, id: uuid.UUID) -> dict[str, Any]:
    """Authoritative current state + the stream cursor it corresponds to."""
    from studio.api.deps import build_context

    db: Session = get_session_factory(request)()
    try:
        ctx = build_context(request, db)
        _authorize(db, ctx, channel, id)
        db.commit()
        state = (
            _session_snapshot(db, ctx, id) if channel == "session" else _task_snapshot(db, ctx, id)
        )
        state["maxSeq"] = _max_seq(db, ctx, channel, id)
        state["channel"] = channel
        return state
    finally:
        db.close()
```

## stream

Source: `services/studio-api/src/studio/api/events/routes.py:stream`.

```python
@events_router.get("/stream")
def stream(
    request: Request,
    channel: str,
    id: uuid.UUID,
    since: int = 0,
) -> StreamingResponse:
    """SSE endpoint. ``Last-Event-ID`` wins over ``since`` on reconnect.

    The auth context is resolved on a short-lived session that is
    committed and closed BEFORE the response starts streaming — the
    ``authenticate_token`` last-seen UPDATE must never pin a row lock
    for the lifetime of an SSE connection."""
    if channel not in CHANNELS:
        raise DomainError(ErrorCode.VALIDATION, "unknown channel")
    last_id = request.headers.get("last-event-id")
    if last_id is not None:
        try:
            since = int(last_id)
        except ValueError:
            since = 0
    from studio.api.deps import build_context

    factory = get_session_factory(request)
    db = factory()
    try:
        ctx = build_context(request, db)
        _authorize(db, ctx, channel, id)
        db.commit()
    finally:
        db.close()
    return StreamingResponse(
        _stream(request, factory, ctx, channel, id, since),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```
