# Background service API

Explicit host-owner controls for the fixed optional macOS LaunchAgent.

[Shared authentication, errors and transport](rest-overview.md). Examples use synthetic values; replace resource IDs with records from your workspace.

## GET /api/agent-workspace/background

Inspect the fixed optional macOS background research service.

**Access:** Provider administrator/host-owner gate, not arbitrary workspace membership.

**Request:** No body.

**Response:** supported, installed and running booleans; non-macOS returns all false. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/agent-workspace/background HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** A human administrator is inspecting a macOS host before installation.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "supported": true,
  "installed": false,
  "running": false
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

**Exact JSON rules and response serialization:** [background_status](contracts-background.md#background_status).

Source: `services/studio-api/src/studio/api/background.py:33` (`background_status`).

## POST /api/agent-workspace/background

Install or uninstall the fixed macOS LaunchAgent.

**Access:** Provider administrator/host-owner gate.

**Request:** JSON action enum install/uninstall. This changes the local host service.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `data` (required) | JSON body | `BackgroundChange` | `required` |

**Response:** The same supported/installed/running status object. Default success status: 200. Availability: core.

**Failures:** ENGINE_UNAVAILABLE off macOS or without the launcher; RESOURCE_UNAVAILABLE if launchctl/script fails.

**Request example:**

```http
POST /api/agent-workspace/background HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "action": "install"
}
```

**Success response example:** An authorized human administrator explicitly installs the fixed LaunchAgent on macOS.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "supported": true,
  "installed": true,
  "running": true
}
```

**Failure response example:** macOS background service is unavailable.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "errors": [
    {
      "code": "ENGINE_UNAVAILABLE",
      "message": "macOS background service is unavailable",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [background_change](contracts-background.md#background_change), [BackgroundChange](contracts-background.md#backgroundchange).

Source: `services/studio-api/src/studio/api/background.py:50` (`background_change`).
