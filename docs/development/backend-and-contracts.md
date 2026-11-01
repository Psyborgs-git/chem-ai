# Backend, API contracts and migrations

The FastAPI service exposes authenticated REST workspaces and a Strawberry/Relay GraphQL schema over shared domain services. Change the owning service first, then the transport/schema, persistence migration, client and documentation together.

## Find the API boundary

`services/studio-api/src/studio/api/app.py` creates the application, adds loopback security and exception handling, registers REST/GraphQL routes, starts durable worker lifecycles and finally mounts the optional native frontend.

REST groups include authentication, artifact transfer, event streams, private Library, private Agent/background service, private learning, research workflows and simulations. Shared scientific work largely uses GraphQL. The Reference section inventories every registered endpoint and GraphQL field; do not maintain a second handwritten exhaustive endpoint list in feature prose.

Add a new router to app assembly explicitly. Keep API routes ahead of the optional frontend mount. A missing API route must remain a typed/HTTP error rather than falling through to the SPA HTML document.

## Authentication and authorization

Use `Ctx` and `DbSession` from `studio.api.deps` for ordinary REST handlers. The session cookie is `studio_session`; existing integrations can also authenticate with a bearer session token. Do not add token values to examples, URL parameters, logs or returned error messages.

`build_context` authenticates the session, commits its last-seen heartbeat separately to avoid request-spanning auth-row locks, then loads `ServiceContext`. Domain code calls `ctx.require(...)` and scopes queries to the current workspace. Owner-private resources additionally constrain the owner identity; copying a shared reader capability check is insufficient for private data.

GraphQL gets its context through `studio.api.graphql.context`, resolves the service context lazily and creates loaders per request. Never cache a principal's authorized rows or loaders globally.

The shared policy package defines capabilities and agent restrictions. Human scientific approval, credential administration and model activation must remain unavailable to agent/service principals where the policy excludes them. Test rejected direct API calls as well as hidden buttons.

## Implement a domain command

Follow the nearest domain service's transaction and error conventions:

1. Validate the principal/capability and load the authorized aggregate.
2. Validate typed input, scientific units/bases/lineage and current state.
3. Check expected revisions or lock contested rows for concurrency-sensitive changes.
4. Append an immutable revision/amendment or perform the explicitly permitted mutable transition.
5. Write audit and transactional outbox records alongside the domain effect.
6. Let the transport commit the intended transaction and serialize only safe results.

Services such as `domain/projects/service.py` demonstrate workspace-scoped lookup, deliberate validation, outbox publish and audit recording. Private Library and learning services demonstrate owner checks and provenance revalidation. Reuse them from both REST and GraphQL; do not duplicate business rules in resolvers.

Raise `DomainError` with an `ErrorCode`, safe message and field path. Useful distinctions include `UNAUTHENTICATED`, `FORBIDDEN`, `NOT_FOUND`, `REVISION_CONFLICT`, `IDEMPOTENCY_MISMATCH`, `ENGINE_UNAVAILABLE`, `EVIDENCE_INSUFFICIENT` and `VALIDATION`. Do not return raw SQL errors, provider response bodies, process stdout, credentials or private local paths.

## Handle retries and events

For an idempotent mutating command, use the existing `run_idempotent` contract or its feature-specific stronger credential-safe implementation. Keep effects, response replay and outbox events in one transaction. Reusing a key with a different payload must fail; an uncertain response should not cause a duplicate scientific run.

Provider writes require their existing Keychain/database compensation and cleanup-intent protocol. Do not reuse a generic payload digest that stores key-derived secret verifiers or put the key inside an audit/idempotency payload.

Outbox consumers run at least once with deduplication. Keep handlers safe under redelivery. Task/session SSE carries sequence IDs and supports snapshot recovery. A reconnect must not reapply an action merely because its event was delivered again.

## Extend REST inputs and outputs

Use the nearest typed Pydantic request contract and explicit response shapes. Preserve camelCase wire aliases where the existing interface uses them, validated bounds, optional-vs-unset behavior and expected-revision fields. Private responses use the existing no-store and same-origin headers.

Uploads have a staged create/bytes/finish flow; only finished verified bytes become committed artifacts. File and artifact routes enforce ownership, bounded member names and safe output paths. A caller-supplied filesystem path must not become an arbitrary file read.

When extending a worker endpoint, preserve authentication, owner scope, lease binding, heartbeat and cancellation. Remote workers receive bounded authorized payloads, not the server's model paths or inherited credentials.

## Extend GraphQL and Relay

The executable schema is assembled in `studio/api/graphql/schema.py`, with node types, loaders, IDs and private workspace roots in adjacent modules. The committed `packages/contracts/schema.graphql` is generated from those Python definitions.

Use a typed Relay GlobalID for the expected node kind, authorize it before resolution, and preserve cursor/pagination scope. Do not pass a raw UUID where the schema requires a global ID. Do not decode a global ID and use its UUID before verifying the expected type/scope.

A small authenticated read is:

```graphql
query ExampleViewer {
  viewer {
    id
    displayName
    kind
  }
}
```

After schema edits:

```sh
make schema-export
pnpm relay
uv run python infra/ci/export_schema.py --check
uv run python infra/ci/check_relay_boundaries.py
pnpm typecheck
```

Inspect both schema and generated client diffs. Preserve existing fields and wire behavior unless the change explicitly includes a migration/compatibility plan. Update clients and generated reference before shipping a removed/renamed operation.

## Change JSON domain contracts

The canonical original JSON schemas are under `docs/chemistry-studio/contracts/`. `packages/contracts/` mirrors them with checksums; edit the authority, then synchronize:

```sh
uv run python packages/contracts/sync_contracts.py
uv run python packages/contracts/sync_contracts.py --check
```

Update valid and invalid fixtures that demonstrate the actual changed contract. Do not hand-edit mirrored schemas or checksum manifests to suppress a drift failure. GraphQL SDL export and JSON-schema mirroring are separate generation steps.

## Add a database migration

SQLAlchemy base metadata lives under `studio.persistence`; private domain model modules also register tables. Alembic's environment imports those model modules. Register a new model module there when required so autogeneration sees it.

Check the existing head, then create one additive revision from the current chain:

```sh
.venv/bin/alembic -c services/studio-api/migrations/alembic.ini heads
.venv/bin/alembic -c services/studio-api/migrations/alembic.ini revision --autogenerate -m "add synthetic example metadata"
```

Review generated SQL operations, constraint names, indexes, defaults and downgrade behavior. Existing revision numbers are historical authority; do not rewrite a migration already used by an installation. Preserve a single head unless the change intentionally reconciles a known parallel branch.

For required data, stage the column/backfill/constraint so an existing installation upgrades safely. Bound large backfills and make interruption/retry behavior explicit. Avoid inventing scientific values as defaults for missing historical data.

Verify fresh-database upgrade, existing-record upgrade, data retention and the intended rollback/recovery behavior on disposable databases. Then apply locally:

```sh
.venv/bin/alembic -c services/studio-api/migrations/alembic.ini upgrade head
```

`STUDIO_DATABASE_URL` selects the target. Confirm it before migration tests. Never point destructive database tests at the user's development workspace. See [Recovery](../operations/recovery.md).

## Extend runtime configuration

Core settings are resolved in `studio/config/settings.py`; other engine/worker/script options have their own owners. Keep defaults and validation at the owning boundary. `get_settings` is cached per process; tests can use `reset_settings_cache`, and a running deployment needs a restart for changed process environment.

Separate frontend-build inputs from backend secrets. Optional lanes must remain disabled/unavailable honestly when prerequisites are absent. New environment reads must appear in the generated environment reference with reviewed purpose, default and sensitivity metadata.

## Verify and document the change

Use unit tests for contract/state logic, PostgreSQL integration for transactions/concurrency/migrations, security tests for scope/capability boundaries, and a focused browser test when user behavior changes. Include stale writer, repeated command, foreign owner, missing prerequisite and safe error cases appropriate to the change.

Regenerate the API/config reference using `make docs-generate`, run `make docs-check`, and update the user/operations guide for the actual new workflow. See [Testing and documentation](testing-and-docs.md).
