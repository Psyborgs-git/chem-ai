# Installation and first run

Install the local, single-workspace Studio from the repository root. Core setup
needs no API key, model download, GPU, or laboratory connection. Optional native
engines are installed separately.

## Prerequisites

| Requirement | Default |
|---|---|
| Platform | macOS or Linux with a POSIX shell |
| Python | 3.12; the project requires `>=3.12,<3.13` |
| Python package manager | `uv`, using the committed lockfile |
| JavaScript runtime | Node 24, matching CI |
| JavaScript package manager | pnpm 10.18.3, as pinned in `package.json` |
| Database | Docker with Compose; local PostgreSQL 16.10 container |
| Optional database clients | `pg_dump`/`pg_restore` at least as new as the server, or container fallback |

Check `uv --version`, `node --version`, `pnpm --version`, and
`docker compose version`. Bootstrap installs packages; it does not download
models or accept model licenses. Keep enough free disk for dependencies, the
PostgreSQL volume, vault growth, and an independent backup.

## Install locked dependencies

```sh
uv sync --python 3.12 --group dev --frozen
pnpm install --frozen-lockfile
```

`make bootstrap` runs these same two commands. Keep `.venv`, `node_modules`, and
`.runtime` private and outside any externally served directory.

## Choose the active vault

For a checkout-based installation, use the same vault as `make dev` and the
native launcher:

```sh
export STUDIO_VAULT_ROOT="$PWD/.runtime/vault"
```

Retain that setting in every shell used to run this installation. Starting
Uvicorn directly without it instead selects
`~/.local/share/chemistry-studio/vault`. Reusing the same database with the wrong
vault can make saved files appear missing. See [configuration](configuration.md)
before changing an existing installation's paths.

## Start PostgreSQL and migrate

```sh
docker compose -f infra/local/compose.yaml up -d postgres
docker exec chem-studio-postgres pg_isready -h 127.0.0.1 -U studio -d studio
make migrate
```

Wait for `pg_isready` to succeed before migration. Compose publishes PostgreSQL
only on `127.0.0.1:54329`; its fixed `studio` development credentials are for this
loopback deployment. Never run Compose `down -v` as a startup repair: it removes
the database volume.

## Start the API and browser app

In one terminal, keeping the selected vault setting:

```sh
uv run --group dev uvicorn studio.api.app:create_app   --factory --host 127.0.0.1 --port 8787
```

In another terminal:

```sh
pnpm --filter studio-web dev
```

Open `http://127.0.0.1:5173`. The Vite server proxies API requests to port 8787.
`curl --fail http://127.0.0.1:8787/healthz` should return `{"status":"ok"}`.
Health proves HTTP is running; it does not prove database/schema readiness.
Check migrations and PostgreSQL separately if sign-in fails.

`make dev` combines PostgreSQL readiness, migration, API startup, and Vite,
preserves the installed Python profile, and refuses to replace an existing
listener on ports 8787 or 5173. Stop its foreground process with Control-C.
PostgreSQL remains running; `make db-down` stops Compose without deleting data.

Bind to loopback. Changing Host/Origin settings does not implement secure LAN
hosting, TLS, or a production session design.

## Create the owner and begin using the Studio

Use **Set up Chemistry Studio** to choose a login, display name, and password of
at least ten characters. Setup signs you in and closes after the first owner is
created. Later visits use **Sign in**; an expired session preserves the intended
route. Sessions use an HttpOnly, SameSite=Strict cookie, normally lasting twelve
hours.

Create a project and research task using [getting started](../usage/getting-started.md).
The core records, notebooks, review, and manual lab workflow work without a model.
Open **Help & documentation** after sign-in to browse the manuals offline.

## Optional local molecular calculations

```sh
uv sync --python 3.12 --group dev --extra engines --frozen
make dev
```

This profile installs native RDKit where a compatible wheel exists. In a
molecule task, choose **Run calculation**, enter `CCO`, and select
**Calculate properties**. A successful ethanol result should include `C2H6O`
and molecular weight approximately `46.069`. Reload the saved result to check
persistence. An invalid structure produces a failed run without invented
properties. Computed descriptors do not replace laboratory measurements.

Other optional profiles and images are described in [model operations](model-ops.md),
[private learning](learning-workspace.md), and [polymer simulations](polymer-simulation.md).
`uv sync` reconciles extras: include every extra you intend to retain when
changing the installed profile. `make dev` itself uses the installed `.venv`.

## Verify the installation

```sh
uv sync --python 3.12 --group dev --extra engines --frozen
export UV_NO_SYNC=1
make verify-core
make typecheck
pnpm --filter studio-web test
make test-integration
make test-security
```

These checks exercise different layers. `verify-core` covers lint, contracts,
and unit tests; it is not the full test suite. Integration/security checks need
Docker or their declared database prerequisites. To exercise browser journeys:

```sh
pnpm --filter studio-web exec playwright install chromium
make test-e2e
```

Browser tests create and reset the separate `studio_e2e` database on the local
Compose PostgreSQL service. They use ports 8790/4173 and dedicated test vault
files. Do not point test processes at production or valuable data. Failure
screenshots/traces are under `test-results`. An installed Chromium can be selected
with `STUDIO_BROWSER_EXECUTABLE_PATH`.

`make seed-demo` is blocked because no demo loader is delivered. `make train-smoke`
requires its optional runtime and currently reports a missing smoke harness;
use the [learning workspace](learning-workspace.md) for current learning jobs.
`make eval-smoke` is a fixture-only evaluation, not scientific qualification.

## Upgrade, reset, and uninstall

Use [backup and restore](backup-restore.md) before upgrading, then follow
[recovery](recovery.md). Uninstalling dependencies is separate from deleting
research data. Inventory the database, active vault, retained Downloads,
external models, and credentials before intentionally removing anything.
The application has no universal safe reset command.

For a native Mac package, follow [desktop setup](desktop-macos.md). For errors,
use [troubleshooting](troubleshooting.md).
