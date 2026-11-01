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
