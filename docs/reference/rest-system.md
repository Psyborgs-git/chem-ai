# Health, readiness and desktop API

Unauthenticated machine-local probes. Liveness does not establish scientific or database readiness.

[Shared authentication, errors and transport](rest-overview.md). Examples use synthetic values; replace resource IDs with records from your workspace.

## GET /api/desktop/runtime

Identify the configured desktop runtime and probe its database/frontend availability.

**Access:** No session required; loopback runtime identity probe.

**Request:** No body; route exists only when a built desktop frontend is mounted.

**Response:** application, desktop, frontendAvailable, databaseReady and optional buildId. Returns 503 when frontend/database is unavailable. Default success status: 200. Availability: desktop frontend enabled.

**Failures:** 404 if desktop mode is off; 503 if its frontend/database check fails.

**Request example:**

```http
GET /api/desktop/runtime HTTP/1.1
Host: 127.0.0.1:8787
```

**Success response example:** Desktop frontend is enabled, the bundled index exists, database probe succeeds, and a build marker was configured.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "application": "chemistry-studio",
  "desktop": true,
  "frontendAvailable": true,
  "databaseReady": true,
  "buildId": "example-build-marker"
}
```

**Failure response example:** The conditional desktop route exists, but its database readiness probe fails.

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{
  "application": "chemistry-studio",
  "desktop": true,
  "frontendAvailable": true,
  "databaseReady": false,
  "buildId": "example-build-marker"
}
```

**Exact JSON rules and response serialization:** [desktop_runtime](contracts-system.md#desktop_runtime).

Source: `services/studio-api/src/studio/api/desktop.py:107` (`desktop_runtime`).

## GET /healthz

Check API process liveness.

**Access:** No session required.

**Request:** No body.

**Response:** status=ok. This endpoint does not probe PostgreSQL. Default success status: 200. Availability: core.

**Failures:** Connection failure means the API is not reachable; a 200 does not verify database readiness.

**Request example:**

```http
GET /healthz HTTP/1.1
Host: 127.0.0.1:8787
```

**Success response example:** Core-only settings; readiness capability information does not establish actual database connectivity or scientific qualification.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "status": "ok"
}
```

**Failure response example:** Host is not a permitted loopback host.

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "errors": [
    {
      "code": "FORBIDDEN",
      "message": "host not permitted"
    }
  ]
}
```

**Exact JSON rules and response serialization:** [healthz](contracts-system.md#healthz).

Source: `services/studio-api/src/studio/api/app.py:62` (`healthz`).

## GET /readyz

Read profile and database capability information.

**Access:** No session required.

**Request:** No body.

**Response:** status=ready, profiles and database capability objects. Inspect the database value; status alone is not a successful database probe. Default success status: 200. Availability: core.

**Failures:** Host rules apply. Capability reporting does not establish a model/science qualification.

**Request example:**

```http
GET /readyz HTTP/1.1
Host: 127.0.0.1:8787
```

**Success response example:** Core-only settings; readiness capability information does not establish actual database connectivity or scientific qualification.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "status": "ready",
  "profiles": {
    "core": {
      "status": "available",
      "detail": "manual recordkeeping"
    },
    "local_ai": {
      "status": "disabled",
      "detail": "profile off; set STUDIO_PROFILE_LOCAL_AI=1 after capability/model review"
    },
    "optimization": {
      "status": "disabled",
      "detail": "profile off"
    },
    "quantum": {
      "status": "disabled",
      "detail": "profile off"
    },
    "materials": {
      "status": "disabled",
      "detail": "profile off"
    },
    "training": {
      "status": "disabled",
      "detail": "profile off"
    },
    "design": {
      "status": "disabled",
      "detail": "profile off"
    },
    "synthesis": {
      "status": "disabled",
      "detail": "profile off"
    }
  },
  "database": {
    "status": "unknown",
    "detail": "checked by readiness probe"
  }
}
```

**Failure response example:** Host is not a permitted loopback host.

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "errors": [
    {
      "code": "FORBIDDEN",
      "message": "host not permitted"
    }
  ]
}
```

**Exact JSON rules and response serialization:** [readyz](contracts-system.md#readyz).

Source: `services/studio-api/src/studio/api/app.py:66` (`readyz`).
