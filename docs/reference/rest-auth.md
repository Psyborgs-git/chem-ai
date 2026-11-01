# Session and owner setup API

Bootstrap the single workspace owner, sign in and revoke a session.

[Shared authentication, errors and transport](rest-overview.md). Examples use synthetic values; replace resource IDs with records from your workspace.

## GET /api/auth/setup-needed

Check whether the first owner still needs to be created.

**Access:** No session required.

**Request:** No body or query parameters.

**Response:** setupNeeded boolean. Default success status: 200. Availability: core.

**Failures:** Host/origin transport rules still apply.

**Request example:**

```http
GET /api/auth/setup-needed HTTP/1.1
Host: 127.0.0.1:8787
```

**Success response example:** No workspace owner has been configured.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "setupNeeded": true
}
```

**Failure response example:** Host is a non-loopback host.

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

**Exact JSON rules and response serialization:** [setup_needed](contracts-auth.md#setup_needed).

Source: `services/studio-api/src/studio/api/auth_routes.py:103` (`setup_needed`).

## POST /api/auth/login

Authenticate an existing owner/user.

**Access:** Unauthenticated credentials exchange.

**Request:** LoginRequest JSON: login and password.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `body` (required) | JSON body | `LoginRequest` | `required` |

**Response:** status=authenticated and expiresAt; sets the session cookie. Default success status: 200. Availability: core.

**Failures:** UNAUTHENTICATED for invalid credentials; VALIDATION for invalid fields.

**Request example:**

```http
POST /api/auth/login HTTP/1.1
Host: 127.0.0.1:8787
Content-Type: application/json

{
  "login": "example-owner",
  "password": "documentation-example-only"
}
```

**Success response example:** The synthetic account data is illustrative. On success the real server issues a fresh HttpOnly session cookie; setup additionally requires that no owner already exists.

```http
HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: studio_session=<new-session-token>; HttpOnly; Path=/; SameSite=strict

{
  "status": "authenticated",
  "expiresAt": "2026-11-02T12:00:00Z"
}
```

**Failure response example:** invalid credentials.

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "errors": [
    {
      "code": "UNAUTHENTICATED",
      "message": "invalid credentials",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [login](contracts-auth.md#login), [LoginRequest](contracts-auth.md#loginrequest).

Source: `services/studio-api/src/studio/api/auth_routes.py:80` (`login`).

## POST /api/auth/logout

Revoke the active session and clear its cookie.

**Access:** Authenticated session, resolved inside the handler.

**Request:** No JSON body; requires an existing session.

**Response:** status=logged_out; expired/revoked tokens cannot authenticate later. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/auth/logout HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: studio_session=""; Max-Age=0; Path=/; SameSite=lax

{
  "status": "logged_out"
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

**Exact JSON rules and response serialization:** [logout](contracts-auth.md#logout).

Source: `services/studio-api/src/studio/api/auth_routes.py:93` (`logout`).

## POST /api/auth/setup

Create the first owner and establish its session.

**Access:** Unauthenticated one-time setup; rejected once an owner exists.

**Request:** SetupRequest JSON: login, display_name and password (at least 10 characters).

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `body` (required) | JSON body | `SetupRequest` | `required` |

**Response:** status=owner_configured and expiresAt; sets the HttpOnly, SameSite=Strict studio_session cookie. Default success status: 200. Availability: core.

**Failures:** CONFLICT when an owner already exists; VALIDATION for invalid fields.

**Request example:**

```http
POST /api/auth/setup HTTP/1.1
Host: 127.0.0.1:8787
Content-Type: application/json

{
  "login": "example-owner",
  "display_name": "Example Owner",
  "password": "documentation-example-only"
}
```

**Success response example:** The synthetic account data is illustrative. On success the real server issues a fresh HttpOnly session cookie; setup additionally requires that no owner already exists.

```http
HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: studio_session=<new-session-token>; HttpOnly; Path=/; SameSite=strict

{
  "status": "owner_configured",
  "expiresAt": "2026-11-02T12:00:00Z"
}
```

**Failure response example:** owner already configured.

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "errors": [
    {
      "code": "CONFLICT",
      "message": "owner already configured",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [setup_owner](contracts-auth.md#setup_owner), [SetupRequest](contracts-auth.md#setuprequest).

Source: `services/studio-api/src/studio/api/auth_routes.py:65` (`setup_owner`).
