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
export UV_CACHE_DIR="$PWD/.runtime/uv-cache"
export UV_PYTHON_INSTALL_DIR="$PWD/.runtime/python"
export STUDIO_VAULT_ROOT="$PWD/.runtime/vault"
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
browser. A fresh installation shows **Set up Chemistry Studio**; an
existing installation shows the sign-in form.

After installing dependencies, `make dev` starts PostgreSQL, waits for
readiness, applies migrations, and runs both loopback servers. It keeps
the installed native RDKit profile and uses ignored `.runtime/` vault
and cache directories. Stop it with Ctrl-C; the database container stays available.

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

Use **Set up Chemistry Studio** in the browser to choose a login, display
name, and password of at least ten characters. Creating the first owner
signs in immediately. Subsequent visits use **Sign in**; session expiry
keeps the intended destination. The setup form and endpoint close once
an owner exists.

The equivalent HTTP bootstrap is available for scripted setup:

```bash
curl -s -c /tmp/studio.cookies -X POST http://127.0.0.1:8787/api/auth/setup \
  -H 'Content-Type: application/json' \
  -d '{"login":"owner","display_name":"Owner","password":"<pick ≥10 chars>"}'
```

Expected: `{"status":"owner_configured","expiresAt":"…"}` and a
`studio_session` cookie in the jar. A second `/api/auth/setup` call
returns `{"errors":[{"code":"CONFLICT","message":"owner already
configured"}]}` — verified.
Subsequent logins:

```bash
curl -s -c /tmp/studio.cookies -X POST http://127.0.0.1:8787/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"login":"owner","password":"<same>"}'
```

The browser sign-in form is the normal login path. For transport debugging,
the equivalent request from the dev-server origin is:

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

The accessibility helpers now use the same `e2e-owner` account as the
other browser suites. A fresh full-suite run is the acceptance gate;
standalone success does not replace that check. Browser tests use the
separate `studio_e2e` database, never the development `studio` database.

For an installed system Chromium, set `STUDIO_BROWSER_EXECUTABLE_PATH`
to its executable; otherwise Playwright uses its downloaded Chromium.
Failure screenshots and retained traces are written under `test-results/`.

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

## 9. Local molecular calculations

On Apple Silicon, the locked engines extra includes a native RDKit wheel:

```bash
uv sync --python 3.12 --group dev --extra engines --frozen
make dev
```

Create a project and a discover task with target kind **molecule**. Choose
**Run calculation**, enter `CCO`, and select **Calculate properties**.
The real ethanol result should show formula `C2H6O`, molecular weight
approximately `46.069`, one hydrogen-bond donor, one acceptor, and three
heavy atoms. Open the saved result and reload it to verify persistence.
An invalid structure produces a saved failed run with the engine's typed
error and no fabricated descriptors.

Calculation inputs are immutable checksum-verified vault artifacts. Runs
retain the actual engine version, method, execution profile and elapsed
time. Requests are task-scoped and idempotent; execution is bounded to
60 seconds, with one attempt and resource admission. Computed descriptors
do not satisfy required laboratory measurements. Closed and cancelled
tasks retain their results and reject new calculations.

## 10. Running entirely without a local model (§26.3)

Nothing in §2–§8 requires the llama.cpp model container. With no
`chem-models` volume and no inference image, `capabilities` reports the
local-AI lane `unavailable`/`model_unavailable`, agent runs degrade to
manual workflow, and every records/review/closeout path stays usable —
that is a design requirement of the pilot, exercised in AT-0405-3.

## 11. Uninstall / reset

```bash
docker compose -f infra/local/compose.yaml down -v   # drops dev DB volume
rm -rf .venv node_modules apps/studio-web/node_modules
rm -rf ~/.local/share/chemistry-studio/vault          # artifact blobs
rm -rf .runtime/vault                              # make dev's local vault
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
