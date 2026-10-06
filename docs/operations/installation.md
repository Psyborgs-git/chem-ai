# Runbook — installation and profile setup (core profile)

First-time setup for the local-first, single-workspace, loopback
deployment. Every command below was executed on a clean checkout
(Linux x86_64, AT-1104-3 repro, see `docs/execution/tickets/CS-1104.md`).
Where a step depends on hardware/provider prerequisites that are not
configured, it is marked **not_configured** — it must be skipped, never
silently faked (AT-1104-2).

## 1. Prerequisites

| Requirement | Verified version | Check |
|---|---|---|
| Linux or macOS, POSIX shell | Ubuntu / kernel 6.8 x86_64 | — |
| Docker Engine + compose plugin | 29.7.2 | `docker compose version` |
| `uv` (Python package manager) | 0.12.17 | `uv --version` |
| Python 3.12 (uv can fetch it) | 3.12.14 | `uv python list` |
| Node.js ≥ 20 + `pnpm` ≥ 9 | v22.20.0 / 10.18.3 | `node --version`, `pnpm --version` |
| PostgreSQL **client** tools ≥ server major (16) — optional | 14.x host → container fallback used automatically | `pg_dump --version` |
| ~6 GiB disk (deps + dev DB + web build) | — | `df -h` |

No GPU, paid API, real lab, or external network service is required for
the core profile. Bootstrap never downloads models or accepts licenses
(handoff §26.1, AT-0002-2).

## 2. Checkout and dependencies

```bash
git clone <authorized-repo-url> chem-ai && cd chem-ai
git checkout main            # or the release tag being qualified
uv sync --python 3.12 --group dev --frozen
pnpm install --frozen-lockfile
```

Expected: `uv` resolves the locked environment into `.venv/` and pnpm
installs the workspace (`apps/studio-web` + `packages/*`). No models,
licenses, or telemetry are fetched.

Equivalent single step: `make bootstrap` (prints the optional-extras
hint — see §6).

## 3. Database

```bash
docker compose -f infra/local/compose.yaml up -d postgres
make migrate
```

Expected:

- compose: container `chem-studio-postgres` healthy on
  `127.0.0.1:54329` (user `studio`, password `studio`, db `studio`).
  This is a **development credential for loopback only**.
- migrate: alembic chain applies to head. Last lines of output list
  `Running upgrade … -> <rev>` entries ending at the current head.

Failure symptoms:

| Symptom | Cause | Recovery |
|---|---|---|
| `port 54329 already allocated` | another postgres instance holds it | `make db-up` reuses an already-listening 54329 postgres; otherwise stop the conflicting container |
| `connection refused` | container still starting | wait for `docker exec chem-studio-postgres pg_isready -U studio -d studio` to succeed, retry `make migrate` |
| alembic killed mid-upgrade | process interrupted | safe: each upgrade runs in one transaction; re-run `make migrate` (see `recovery.md` §2) |

## 4. API server

```bash
uv run --group dev uvicorn studio.api.app:create_app \
  --factory --host 127.0.0.1 --port 8787
```

Expected: uvicorn logs `Application startup complete`.
Verify from a second shell:

```bash
curl -s http://127.0.0.1:8787/healthz        # {"status":"ok"}
```

Bind host defaults to `127.0.0.1`; the request middleware rejects
non-loopback `Host`/`Origin`. Do **not** put this behind a reverse
proxy or LAN interface: sessions are `secure=False` loopback cookies
(residual risk R4 in `docs/execution/security/cs1101-residual-threat-register.md`).

Optional profile flags (off by default; each enables server-side
commands for that lane — they still fail closed if the lane's engine
image is absent):

```bash
STUDIO_PROFILE_OPTIMIZATION=1 STUDIO_PROFILE_QUANTUM=1 \
STUDIO_PROFILE_MATERIALS=1 STUDIO_PROFILE_DESIGN=1 \
STUDIO_PROFILE_SYNTHESIS=1 STUDIO_PROFILE_TRAINING=1 \
STUDIO_PROFILE_LOCAL_AI=1 \
uv run --group dev uvicorn studio.api.app:create_app --factory \
  --host 127.0.0.1 --port 8787
```

## 5. Web UI

```bash
pnpm --filter studio-web dev    # vite dev server on http://127.0.0.1:5173
```

Expected: vite prints `Local: http://127.0.0.1:5173/`; `/api` and
`/graphql` proxy to `127.0.0.1:8787` (vite config). Open the URL in a
browser; the app shows **"Not signed in"** until §7 creates a session.

For a production-like build (what e2e uses):

```bash
pnpm --filter studio-web build
pnpm --filter studio-web preview --port 4173 --host 127.0.0.1
```

## 6. Optional dependency extras

```bash
uv sync --extra engines        # native rdkit (host wheel availability
                               # permitting — see docs/dependencies.lock.md)
uv sync --extra local_ai       # local inference bindings
uv sync --extra optimization   # optimization worker deps
uv sync --extra quantum        # quantum adapter deps
uv sync --extra training       # torch/trl — heavy; U08/U13 gated
```

The container engines (§"engine images" in `model-ops.md`) are the
qualified execution path; native extras are a convenience for hosts
where wheels exist.

## 7. First sign-in (owner bootstrap)

The SPA has no sign-up form: the first owner is created once over HTTP,
then the endpoint refuses (verified — a second call returns a
domain error).

```bash
curl -s -c /tmp/studio.cookies -X POST http://127.0.0.1:8787/api/auth/setup \
  -H 'Content-Type: application/json' \
  -d '{"login":"owner","display_name":"Owner","password":"<pick ≥10 chars>"}'
```

Expected: `{"ok": true, …}` and a `studio_session` cookie in the jar.
Subsequent logins:

```bash
curl -s -c /tmp/studio.cookies -X POST http://127.0.0.1:8787/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"login":"owner","password":"<same>"}'
```

In the browser (dev server origin): devtools console →

```js
fetch("/api/auth/login", {method:"POST",
  headers:{"Content-Type":"application/json"},
  body: JSON.stringify({login:"owner", password:"<same>"})})
```

then reload. The cookie is `HttpOnly`, `SameSite=Strict`,
workspace-bound, TTL 12 h (`STUDIO_SESSION_TTL_SECONDS`).

`GET /api/auth/setup-needed` reports whether bootstrap is still open —
after owner creation it returns false.

## 8. Smoke the pilot (verification battery)

```bash
make verify-core      # ruff + contracts + unit tests — deterministic,
                      # no GPU/net/lab required
make test-integration # disposable testcontainers PG per test
make test-security    # adversarial/security suite
make backup-test      # dump → restore → integrity check on disposable DBs
make test-e2e         # Playwright journeys (needs browsers, below)
```

Playwright browser install (one-time per machine):

```bash
pnpm --filter studio-web exec playwright install chromium
make test-e2e         # real API subprocess + vite preview + chromium
```

Honestly-reporting targets (exit non-zero with a reason, never a fake
pass):

```bash
make seed-demo    # → BLOCKED: no demo seeder exists (fixture loader was
                  # planned against P02 schema and never landed). Create
                  # data through the UI or GraphQL instead — see user.md.
make test-engines # → UNAVAILABLE unless a pinned engine image or native
                  # rdkit exists; prints the exact build command
make train-smoke  # → BLOCKED without --extra training + hardware (U08/U13)
make eval-smoke   # fixture eval harness; non-scientific by design
```

## 9. Running entirely without a local model (§26.3)

Nothing in §2–§8 requires the llama.cpp model container. With no
`chem-models` volume and no inference image, `capabilities` reports the
local-AI lane `unavailable`/`model_unavailable`, agent runs degrade to
manual workflow, and every records/review/closeout path stays usable —
that is a design requirement of the pilot, exercised in AT-0405-3.

## 10. Uninstall / reset

```bash
docker compose -f infra/local/compose.yaml down -v   # drops dev DB volume
rm -rf .venv node_modules apps/studio-web/node_modules
rm -rf ~/.local/share/chemistry-studio/vault          # artifact blobs
```

## Privacy concerns

- The dev DB credentials are hard-coded loopback values; the vault and
  DB hold all workspace data including auth material — see
  `backup-restore.md` and `privacy.md` before storing real records.
- No at-rest application encryption exists; rely on OS volume
  encryption (pilot-gate "honest gaps").

## Evidence location

- This runbook's commands were executed in the AT-1104-3 repro:
  `docs/execution/tickets/CS-1104.md` §验证命令与结果.
- Ticket-level verification for each feature referenced here:
  `docs/execution/tickets/CS-*.md`; consolidated view:
  `docs/execution/release/release-matrix.md`.
