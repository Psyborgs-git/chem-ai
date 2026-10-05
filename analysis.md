# Analysis — Chemistry Studio implementation

Execution-state file required by CS-0001. Canonical specification:
`docs/chemistry-studio/` (handoff pack v1.0.0 content + v1.0.1
packaging README). Do not fork this analysis into a competing spec.

## Situation

Greenfield workspace, no VCS, no code. The full handoff package is
extracted to `docs/chemistry-studio/` and its offline validator passes
(52 tickets, 156 acceptance cases, 20/20 fixture expectations).

## What is being built

A standalone, local-first chemistry research application (locked
decision D01): projects → scoped research tasks (improve /
match_reference / discover, D02) → versioned success contracts,
sessions, candidates, runs, experiments, evidence, decisions (D03).
Workflow-first (D05); manual lab approval/execution (D06); local-first
with dynamic capability detection (D07); cloud only as an explicitly
approved export fallback (D08); 16 unknowns stay unknown (D09);
promotion requires independent evaluation (D10).

## Architecture (handoff §4, engineering defaults E01–E08)

- Modular Python backend: FastAPI (ASGI) + Strawberry GraphQL +
  Pydantic + SQLAlchemy/Alembic on PostgreSQL.
- React + TypeScript + Vite + Relay web client on loopback.
- Private filesystem artifact vault behind `ArtifactStore`.
- Procrastinate (PostgreSQL) job queue — reused, not reimplemented.
- Isolated worker profiles: `core`, `local_ai`, `optimization`,
  `quantum`, `training`; core must start with none of them.
- Runtime profiles installable independently; the core never imports
  GPU/science dependencies at startup.

## Key invariants driving design (handoff §5–§8, §12)

1. Immutable accepted revisions; corrections = superseding revisions.
   Optimistic locking via `expected_version`; `(entity_id, revision)`
   unique.
2. Decimals as `NUMERIC`/decimal strings; units + basis mandatory;
   no silent normalization or mass↔volume conversion without density
   evidence; distinct measured-value kinds incl. missing/censored.
3. Idempotent commands: `(workspace, idempotency_key, operation)`
   unique, outcome persisted in the same transaction as state + outbox.
4. Approvals bind exact content digests/scope/expiry; stale ⇒ blocked.
5. Scope integrity: every record carries `workspace_id` (+
   `project_id` where project-owned); cross-workspace references fail.
6. Capability-based authorization server-side; loopback same-origin
   enforcement; no existence leak across scopes.
7. Outbox ≥ once delivery; consumers deduplicate; `Run` state machine
   with CAS transitions and terminal-state protection.
8. Artifact vault: opaque keys, outside repo/web roots, checksums,
   quarantine, size/path/decompression limits, no unauthenticated
   download.

## Risks mapped to plan

- **Disk ~9.9 GiB**: dev Postgres volume and vault kept bounded; CI
  uses ephemeral containers.
- **Python 3.14 too new for science deps**: profiles pin their own
  interpreter via `uv`; core targets a broadly supported 3.12.
- **No PostgreSQL on host**: Docker daemon verified; `infra/local/`
  provides a compose file; tests use disposable databases.
- **macOS x86_64, not the Linux CI reference**: isolation claims are
  per-platform; unsupported controls report unavailable rather than
  claiming security.
- **16 unknowns**: only dependent live actions are blocked; all
  synthetic/deterministic work proceeds. See `docs/execution/tickets/`
  for per-ticket blocked-capability status.

## Evidence conventions

Each completed ticket gets `docs/execution/tickets/CS-XXXX.md` with
changed files, commands+exit codes, outputs, AT-ID → test mapping, and
live/fixture/blocked status. `docs/execution/trace.md` maintains
requirement → ticket → code → test → evidence trace.
