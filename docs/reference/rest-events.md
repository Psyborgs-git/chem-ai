# Event stream API

Authorized task/session snapshots and resumable outbox event streams.

[Shared authentication, errors and transport](rest-overview.md). Examples use synthetic values; replace resource IDs with records from your workspace.

## GET /api/events/snapshot

Read an authorized task/session event snapshot.

**Access:** Authenticated session; channel-specific task/project/session authorization is checked before reading events.

**Request:** channel (task/session) and id UUID query parameters; stream optionally resumes using its accepted sequence header/query. See the source signature and validation for exact spelling.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `channel` (required) | query | `str` | `required` |
| `id` (required) | query | `uuid.UUID` | `required` |

**Response:** Channel-specific JSON snapshot with the sequence needed for subsequent streaming. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/events/snapshot?channel=task&id=00000000-0000-4000-8000-000000000023 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** The task is accessible and has no run events yet.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "runs": [],
  "maxSeq": 0,
  "channel": "task"
}
```

**Failure response example:** The session cookie is omitted and no Bearer session token is supplied.

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "errors": [
    {
      "code": "UNAUTHENTICATED",
      "message": "session required",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [snapshot](contracts-events.md#snapshot).

Source: `services/studio-api/src/studio/api/events/routes.py:204` (`snapshot`).

## GET /api/events/stream

Stream authorized persisted outbox events.

**Access:** Authenticated session; channel-specific task/project/session authorization is checked before reading events.

**Request:** channel (task/session) and id UUID query parameters; stream optionally resumes using its accepted sequence header/query. See the source signature and validation for exact spelling.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `channel` (required) | query | `str` | `required` |
| `id` (required) | query | `uuid.UUID` | `required` |
| `since` (optional) | query | `int` | `0` |

**Response:** text/event-stream; event id is the persisted sequence, data is JSON. Heartbeats/reconnect boundaries are transport events, not new scientific evidence. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/events/stream?channel=task&id=00000000-0000-4000-8000-000000000023&since=0 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Accept: text/event-stream
Last-Event-ID: 0
```

**Success response example:** No new outbox event is ready, so this frame is a heartbeat without an event ID. Last-Event-ID overrides since.

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no

event: heartbeat
data: {}


```

**Failure response example:** unknown channel.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "errors": [
    {
      "code": "VALIDATION",
      "message": "unknown channel",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [stream](contracts-events.md#stream).

Source: `services/studio-api/src/studio/api/events/routes.py:257` (`stream`).
