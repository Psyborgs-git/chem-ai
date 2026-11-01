# REST transport, authentication and errors

This is the shared contract for the generated REST endpoint articles. Each endpoint also lists its exact parameters, side effects, output and source-defined JSON rules. Examples are synthetic documentation; the Help reader never sends them.

## Origins and sessions

The supported deployment is one trusted local machine. The Host header must identify a loopback host. State-changing requests require an absent/null Origin or one of the exact configured allowed origins. Changing a profile or allowlist does not establish supported LAN/TLS deployment.

Create the first owner through `/api/auth/setup`, then use `/api/auth/login`. The response establishes `studio_session`, an HttpOnly cookie with SameSite=Strict and path `/`. Loopback HTTP cookies are not Secure. Session lifetime defaults to 12 hours. Logout revokes the session and clears the cookie.

Authenticated requests may instead provide `Authorization: Bearer <session-token>`; a session cookie takes precedence when both are present. Do not embed tokens in URLs or source files. Capabilities, workspace, user ownership, revoked grants and disabled principals are evaluated server-side. An authenticated session alone is insufficient for an approval or administrator command. Agent principals cannot acquire approval/service capabilities through forged grants.

The setup-needed, health, readiness and conditional desktop identity probes are intentionally available without a session. The other data APIs authenticate before exposing private records. Private library and agent responses use cache-control protections. Operator status fields do not establish scientific qualification.

## Request forms and responses

Most commands use JSON. Artifact content upload uses raw body bytes. Dataset/source upload and remote-worker completion use multipart form data. Artifact/source/checkpoint downloads return binary content; event streaming returns `text/event-stream`. Do not JSON-decode these binary/streaming endpoints.

Tables preserve source annotation and default/constraint expressions. Parameters named by path placeholders are path values. Remaining scalar fields are query values; body models and `body`/`payload`/`data` are JSON bodies. Library request models accept camelCase aliases and Python field names, forbid unknown keys, and reject non-finite numbers. Flexible JSON services have their own explicit accepted keys and checks in the linked contract appendices; they are not blanket permission to send arbitrary keys.

Library updates/deletes often require `expectedRevision`; reload the record after a conflict. Legacy GraphQL mutations use their declared idempotency/version inputs; do not assume every REST command provides automatic idempotency. Repeating a creation request can create another record.

## Typed domain errors

REST domain errors have this envelope. Values below are illustrative:

```json
{
  "errors": [{
    "code": "REVISION_CONFLICT",
    "message": "record changed since the expected version; reload and retry",
    "fieldPath": null,
    "retryable": true,
    "safeDetails": {}
  }]
}
```

| HTTP status | Domain codes / behavior |
| --- | --- |
| 401 | `UNAUTHENTICATED`: missing, expired, revoked or invalid session |
| 403 | `FORBIDDEN`: capability/ownership/host/origin rejection |
| 404 | `NOT_FOUND`: record missing or inaccessible; also unavailable conditional routes |
| 409 | `REVISION_CONFLICT`, `IDEMPOTENCY_MISMATCH`, `APPROVAL_STALE`, `APPROVAL_EXPIRED`, `CONFLICT` |
| 422 | Other domain errors, including validation, engine availability, resource, provenance, unit, approval and model-promotion failures |

FastAPI parameter/body validation can instead return the framework `detail` validation array. Middleware host/origin errors use a reduced `errors` envelope. Binary/probe endpoints may have endpoint-specific statuses, such as desktop runtime 503. A transport 200 from GraphQL or a queued/cancel acknowledgment is not proof that work completed.

## Streams and long work

Event snapshot/stream channels are `task` and `session`, scoped to accessible records. On `/api/events/stream`, the integer `Last-Event-ID` header takes precedence over the `since` query cursor. Invalid header integers fall back to zero. A heartbeat has no event ID and must not advance the cursor. Streams reconnect at their bounded lifetime; the persisted outbox is authoritative.

Agent, learning and simulation jobs are distinct durable systems with their own status and lease behavior. Cancellation is a request until the worker records termination; resumption rechecks access, source rights and configuration. Legacy runs require their explicit reconciliation path. None of these statuses upgrades synthetic/computational output into laboratory evidence.

## Full endpoint inventory

- [Session setup and login](rest-auth.md)
- [Health, readiness and native probes](rest-system.md)
- [Private library](rest-library.md)
- [Private agent](rest-agent.md)
- [Learning and self-hosted workers](rest-learning.md)
- [Polymer simulation](rest-simulations.md)
- [Public-source workflows](rest-workflows.md)
- [Artifact transfers](rest-artifacts.md)
- [Event snapshots and streams](rest-events.md)
- [Host background service](rest-background.md)

The framework-generated [GraphQL transport](graphql-overview.md) is cataloged separately. The static desktop SPA mount is an asset surface, not another data API.
