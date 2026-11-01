# Architecture and source ownership

Chemistry Studio is a React web client, a FastAPI service, PostgreSQL records, a content-addressed artifact vault, optional scientific workers and a Tauri Mac shell. The server owns authorization and scientific state transitions. Frontend affordances and agent suggestions do not grant authority or establish a scientific result.

## Repository map

| Area | Source | Responsibility |
| --- | --- | --- |
| Web client | `apps/studio-web/src/` | Routing, feature forms, Relay operations, private REST workspaces, styles |
| Native shell | `apps/studio-web/src-tauri/` | Bundled boot UI, verified loopback runtime, native downloads/window lifecycle |
| API assembly | `services/studio-api/src/studio/api/app.py` | Middleware, REST routers, GraphQL transport, worker lifecycle, optional static frontend |
| Domain services | `services/studio-api/src/studio/domain/` | Business validation, scope checks, scientific revisions and durable jobs |
| Application services | `services/studio-api/src/studio/application/` | Idempotency, approvals, provider runtime and task agent tools |
| Persistence | `services/studio-api/src/studio/persistence/` and domain model modules | SQLAlchemy records and session infrastructure |
| Migrations | `services/studio-api/migrations/` | Single Alembic migration authority |
| Shared policy | `packages/policy/` | Capability vocabulary and principal restrictions |
| Contracts | `packages/contracts/` | Exported GraphQL SDL and mirrored/checksummed JSON schemas |
| Adapters | `packages/engine-adapters/` | Versioned scientific engine contracts and interpretation limits |
| Workers | `workers/` | Bounded execution, training/evaluation, optimization, chemistry and simulation |
| Infrastructure | `infra/local/`, `infra/ci/`, `infra/images/`, `infra/cloud/` | Local commands, validation/exporters, images and separately gated cloud lanes |
| Documentation | `docs/usage/`, `docs/development/`, `docs/operations/`, `docs/reference/` | Current help manuals and generated exhaustive reference |

`docs/chemistry-studio/` is the original implementation/handoff pack. `docs/execution/` holds historical tickets, audits, release evidence and qualification records. Neither replaces current source inspection for changed behavior.

## Request and state flow

In browser development, Vite binds `127.0.0.1:5173` and proxies `/api` and `/graphql` to `127.0.0.1:8787`. In a native release, the verified local API also serves the bundled frontend so credentials and relative requests share one origin.

The entry gate probes setup state, then the viewer. An uninitialized installation shows owner setup; an existing signed-out installation shows sign-in. After sign-in, the shell mounts the Relay environment, work navigation and feature routes. Help uses bundled content inside that authenticated shell.

REST handlers use request-scoped database sessions and `ServiceContext`. GraphQL builds the same service context lazily and creates request-scoped loaders. Services enforce workspace/owner scope and capabilities, perform validation, append revisions or update allowed mutable state, publish audit/outbox events, then the transport commits the request transaction.

The artifact vault holds committed bytes addressed by checksums; database records hold metadata, lineage and references. Staged uploads are not committed artifacts. Keep database and vault recovery together.

## Shared and owner-private domains

Shared task research includes projects, contracts, candidates, lab plans/results, evidence claims, closure packets, task reports and the reviewed model registry. Its queries require the appropriate workspace/project capabilities.

Private Library, app-wide Agent, private learning and simulation domains additionally enforce owner identity. An administrator's workspace read capability is not permission to read another owner's notebook, conversation or job. Private GraphQL roots and REST routes call the same underlying domain services.

Notebook agent access, training rights, provider disclosure and artifact export are separate checks. Revalidate current source rights and page revisions at use, including when replaying saved checkpoints or derived copies.

## Synchronous and durable work

Small deterministic operations can finish within a bounded request. Runs, private agent steps, learning jobs and polymer simulations use durable records, events, checkpoints and leases. The backend owns their lifecycle independently of open browser tabs.

General execution uses `workers/common/` and declared isolation profiles. Private learning dispatch/runtime code lives under `domain/learning/workspace_runtime/`; simulation dispatch lives under `domain/simulations/`; private agent execution lives under `domain/agent_workspace/`.

Transactional outbox delivery is at least once with a consumer deduplication ledger. SSE streams expose bounded current events; snapshots recover authoritative state after gaps. Do not design handlers or clients around an exactly-once network-delivery assumption.

## Scientific integrity boundaries

Contracts and accepted scientific revisions are immutable histories. Measurements are corrected by amendments. The closure evaluator derives its packet from authoritative data and a human records the closure. Agent principals have a capability ceiling that excludes human approval actions.

Optional engine availability is probed, not inferred from a UI toggle. Raw engine success, numerical convergence, training completion, evaluation gates and human scientific review are different states. Every new lane must preserve that distinction in its stored contract and UI.

## Pick the change path

- UI or interaction work: [Editing the Studio](editing-the-studio.md).
- APIs, models, migrations or schemas: [Backend and contracts](backend-and-contracts.md).
- Scientific runtimes, resource limits or remote workers: [Workers and engines](workers-and-engines.md).
- Setup and native builds: [Local development](local-development.md).
- Checks, generated reference and documentation: [Testing and documentation](testing-and-docs.md).
