# Tech specs — Chemistry Studio (implementation-side)

Distilled engineering spec derived from `docs/chemistry-studio/
CHEMISTRY_STUDIO_HANDOFF.md` §4–§8, §13, §21, §26. Where this file and
the handoff disagree, the handoff wins.

## Stack

| Layer | Choice | Pinned in |
|---|---|---|
| Language (backend) | Python 3.12 (core); per-profile interpreters | `pyproject.toml`, `uv.lock`, `docs/dependencies.lock.md` |
| ASGI host | FastAPI + uvicorn | `pyproject.toml` |
| GraphQL | Strawberry (Relay/Node/connections) | `pyproject.toml` |
| Validation | Pydantic v2 | `pyproject.toml` |
| ORM / migrations | SQLAlchemy 2 + Alembic | `pyproject.toml`, `services/studio-api/migrations/` |
| DB | PostgreSQL 16+ (Docker for dev/test) | `infra/local/compose.yaml` |
| Queue | Procrastinate (PostgreSQL) — P04 | `pyproject.toml` extra |
| Vault | private filesystem `ArtifactStore` | `services/studio-api/src/studio/domain/evidence/` |
| Frontend | React 18 + TypeScript + Vite + Relay | `package.json`, `pnpm-lock.yaml` |
| Tests | pytest (+hypothesis later), vitest, Playwright later | `pyproject.toml`, `package.json` |

## Canonical conventions

- **IDs:** UUIDv4 internally; GraphQL global ID =
  `base64("cs:<type>:<uuid>")`, opaque, stable; decoding grants no
  authorization.
- **Revisioned entity:** `(entity_id UUID, revision INT)` unique per
  revision table; `revision_metadata` JSONB holds author/source/created
  at/digest. Accepted ⇒ immutable (DB trigger rejects UPDATE of
  scientific payload columns; supersede instead).
- **Optimistic locking:** mutable headers carry `version INT`; writes
  require `expected_version` (compare-and-swap).
- **Decimals:** `NUMERIC` columns; DTOs use decimal strings matching
  `^-?(0|[1-9][0-9]*)(\.[0-9]+)?$`; NaN/Inf rejected.
- **Scope:** `workspace_id UUID` on every scoped row; project-owned rows
  add `project_id`; composite FKs enforce same-scope references.
- **Commands:** `idempotency_key` + payload digest; unique
  `(workspace_id, operation, idempotency_key)`; result persisted in the
  same transaction as state change + outbox row.
- **Outbox:** `events` table (`schema_version`, `event_id`, scope,
  aggregate, `aggregate_version`, timestamps, actor, correlation,
  causation, classification, payload ref); relay ≥ once; consumers
  dedupe.
- **Errors:** typed `DomainError` list with the §8.3 code set; never raw
  paths/SQL/credentials to clients.
- **States:** task `draft→active→awaiting_review→closed`,
  `active↔paused`, `→cancelled` (+reopen decision). Run
  `requested→awaiting_approval→queued→running→succeeded|failed|
  timed_out|cancelled`, `requested→blocked`, `queued/running→
  cancel_requested`, worker loss ⇒ `interrupted`. Terminal states are
  CAS-protected.

## Runtime profiles

`core` (API, DB, vault, manual workflows) · `local_ai` (model worker —
blocked U08/U13) · `optimization` (BayBE/property — P06) · `quantum`
(xTB/Psi4 — P07) · `training` (PyTorch/PEFT/TRL — P08/P09). Each is an
independent `uv` extra; `import studio` must not import any profile
dependency.

## Security baseline (§21)

Loopback-only default bind; same-origin + Host checks on every request;
capability-based authorization enforced in services (not resolvers);
scoped service contexts carry `principal` + `workspace`; artifacts
streamed only under capability + scope; no telemetry; secrets via env
only, never logged; engine workers credential-free with egress denied
by default (P04).

## Command contract (§26.1)

Implemented in `Makefile`: `bootstrap dev migrate seed-demo lint
typecheck contracts-check test-unit test-integration test-security
test-e2e test-engines eval-smoke train-smoke backup-test verify-core`.
`verify-core` = deterministic, no GPU/paid API/lab/network after deps
installed. Missing prerequisites print explicit blockers, never
success.
