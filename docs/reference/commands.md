# Development and operations command reference

Run commands from the repository root unless a command says otherwise. The Make and package-script tables below are generated directly from the current manifests; expansions are documentation and are never executed by Help.

## Choosing a check

`make verify-core` runs lint, contract checks and unit tests. It does not run full Python/TypeScript checks, security, integration, browser, engine or native tests. `make contracts-check` regenerates the handoff validation report, so it is not a strictly read-only command. Schema/Relay generation and frontend test/build/typecheck scripts can update generated artifacts.

`make test-integration` uses disposable PostgreSQL test containers. Browser journeys create/reset the dedicated `studio_e2e` database and use API 8790 with frontend preview 4173; they are not the ordinary development database. Tests need Docker and the appropriate installed Playwright browser. Engine/training checks need their optional images, dependencies and hardware and may explicitly report unavailable/blocked.

`make dev` starts local PostgreSQL, upgrades migrations and starts API 8787 plus Vite 5173. It retains the installed optional extras and uses the development vault under `.runtime/vault`; direct API startup has a different default vault. `make db-down` stops the Compose stack but does not request deletion of its named database volume.

## Native and optional services

```bash
pnpm build:desktop
pnpm open:desktop
pnpm test:desktop
pnpm smoke:desktop
bash infra/local/background.sh status
bash infra/local/research-search.sh status
```

Desktop building requires Rust/Tauri/macOS prerequisites. The background service supports `install`, `uninstall`, `status` and `run`; install/uninstall modify the host LaunchAgent. Research search supports `start`, `stop` and `status`; start initializes local SearXNG settings and starts its optional Docker profile.

## Backup, recovery and maintenance CLIs

Use protected paths and supply your own database URL without publishing credentials. Read the operator guide before backup restoration or data maintenance; these commands can write databases and private files.

```bash
uv run python infra/local/backup.py --help
uv run python infra/local/recovery_check.py --help
uv run python infra/local/resumable_backfill.py --help
uv run python infra/local/pilot_gate.py --help
```

The backup CLI supports `create`, `restore` and `verify`. Create needs `--dsn`, `--vault` and `--out`; restore needs `--dsn`, `--vault` and `--backup`, with explicit `--force` only for the documented replace behavior; verify needs `--backup`. Recovery checks take `--dsn`, `--vault`, optional `--expect-alembic` and `--json`. Resumable backfill supports `run`, `status` and `verify` with `--dsn`; run accepts batch-size/max-batches/sleep controls. Pilot-gate export accepts `--out` and writes its generated capability report. Do not run migration downgrades on a populated install.

## Self-hosted learning worker

```bash
uv run python -m workers.training.workspace_worker --help
```

The worker requires `--api`, `--work-dir` and an existing session token in `STUDIO_WORKER_TOKEN`. Optional `--backends` defaults to `transformers,chemprop`; repeated `--model MODEL_ID=/local/path` maps registrations to worker paths; `--once` performs one polling cycle. Remote API URLs require HTTPS, redirects and environment-configured proxies are refused, and model/data egress remains permission-gated. The current loopback host deployment does not become a supported network service simply by starting a remote worker.

## Make targets

| Command | Declared purpose |
| --- | --- |
| `make help` | List targets |
| `make bootstrap` | Install locked deps (core profile only; no models, no licenses) |
| `make dev` | Start postgres + API (loopback) + web dev server |
| `make db-up` | Start local postgres container |
| `make db-down` | Stop local postgres container |
| `make migrate` | Apply database migrations |
| `make seed-demo` | Load SYNTHETIC demo data (labels visible, non-scientific) |
| `make docs-generate` | Regenerate offline API/configuration reference Markdown |
| `make docs-check` | Check reference coverage, article links, and help content boundaries |
| `make lint` | ruff lint |
| `make typecheck` | mypy strict + tsc |
| `make contracts-check` | Validate handoff pack + fixture/schema conformance |
| `make schema-export` | Regenerate committed GraphQL schema from backend defs |
| `make test-unit` | Unit tests (no DB required) |
| `make test-integration` | Integration tests (disposable PG in docker) |
| `make test-security` | Authorization/safety tests |
| `make test-e2e` | Browser journeys (Playwright; reports blocker if absent) |
| `make test-dev-server` | Verify Vite denies private runtime/vault file URLs |
| `make test-engines` | Engine adapter tests; explicit unavailability is honest |
| `make eval-smoke` | Evaluation smoke (fixture-only; non-scientific) |
| `make train-smoke` | Training smoke; blocked without hardware/model (U08/U13) |
| `make backup-test` | Dump+restore cycle on disposable DB |
| `make verify-core` | Deterministic checks, no GPU/net/lab |

## Package scripts: chemistry-studio

| Script | Exact expansion |
| --- | --- |
| `docs:check` | `pnpm --filter studio-web docs:check` |
| `dev:web` | `pnpm --filter studio-web dev` |
| `build:web` | `pnpm --filter studio-web build` |
| `typecheck` | `pnpm --filter studio-web typecheck` |
| `test:web` | `pnpm --filter studio-web test` |
| `relay` | `pnpm --filter studio-web relay` |
| `build:desktop` | `bash infra/local/desktop.sh build` |
| `open:desktop` | `bash infra/local/desktop.sh open` |
| `test:desktop` | `bash infra/local/desktop.sh test` |
| `smoke:desktop` | `node tests/desktop/smoke.mjs` |

## Package scripts: studio-web

| Script | Exact expansion |
| --- | --- |
| `docs:check` | `node scripts/help-content.mjs && node --test scripts/help-content.test.mjs` |
| `dev` | `pnpm relay && vite` |
| `build` | `pnpm relay && tsc -b && vite build` |
| `preview` | `vite preview` |
| `typecheck` | `pnpm relay && tsc -b --pretty` |
| `test` | `pnpm relay && vitest run` |
| `relay` | `node -e "require('fs').mkdirSync('src/__generated__', {recursive:true})" && relay-compiler` |
| `relay:watch` | `relay-compiler --watch` |
