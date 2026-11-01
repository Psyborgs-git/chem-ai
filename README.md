# Chemistry Studio

A local-first chemistry research workspace with projects and tasks, notebooks,
source review, manual laboratory records, computed results, private research
agents, and optional learning and simulation runtimes.

Read the [documentation home](docs/README.md) for usage, editing, backend,
operations, and interface reference. After signing in, open **Help & documentation**
(or `/help`) to read the bundled manuals inside the Studio. Repository Markdown
remains available when the backend is down.

## Start locally

Requires Python 3.12 through `uv`, Node 24, pnpm 10.18.3, and Docker with Compose.
From the repository root:

```sh
uv sync --python 3.12 --group dev --frozen
pnpm install --frozen-lockfile
export STUDIO_VAULT_ROOT="$PWD/.runtime/vault"
docker compose -f infra/local/compose.yaml up -d postgres
```

Wait for `docker exec chem-studio-postgres pg_isready -h 127.0.0.1 -U studio -d studio`
to succeed, then:

```sh
make migrate
uv run --group dev uvicorn studio.api.app:create_app   --factory --host 127.0.0.1 --port 8787
```

In a second terminal run `pnpm --filter studio-web dev` and open
`http://127.0.0.1:5173`. Create the first owner through the setup form. A model or
paid provider is unnecessary for core records and manual workflows.
[Installation](docs/operations/installation.md) explains paths, verification,
optional RDKit, and the combined `make dev` launcher.

## Work on the Studio

- [Usage](docs/usage/getting-started.md): projects, notebooks, research, evidence, and editing records.
- [Development](docs/development/local-development.md): architecture, frontend/backend changes, contracts, workers, and tests.
- [Operations](docs/operations/README.md): configuration, desktop packaging, providers, backups, and recovery.
- [Reference](docs/reference/README.md): endpoint, GraphQL operation, and environment inventories.

`make help` lists the command contract. `make verify-core` runs lint, contracts,
and unit tests; prepare the [engine test profile](docs/development/testing-and-docs.md#prepare-the-test-profile) first. `make docs-generate` refreshes the reference; `make docs-check`
checks documentation and source coverage; `pnpm docs:check` runs the frontend
content checks.

## Capability and evidence limits

Core persistence, artifact review, task contracts, manual lab records, and
capability-based access are implemented. Private agents, retained Downloads,
datasets, local training, and polymer simulations have their own optional
runtime and consent requirements. Missing engines report unavailable rather
than fabricated results.

Scientific calculations, training metrics, pilot execution, and synthetic test
data do not establish scientific qualification, experimental outcomes, or
material equivalence. Inspect each result's provenance and validation status.
Confidential cloud science execution and the eLabFTW bridge have no configured
live deployment. This is a trusted-machine loopback deployment; team/LAN hosting
and production distribution remain separate work.

The original handoff, design specifications, historical ticket evidence, and
research pilots remain under `docs/chemistry-studio`, `docs/design`,
`docs/execution`, and `docs/research`. Current manuals distinguish those records
from current usage and operational instructions.

## Repository layout

| Path | Contents |
|---|---|
| `apps/studio-web` | React, TypeScript, Relay, Vite, and Tauri desktop shell |
| `services/studio-api` | FastAPI, Strawberry GraphQL, domain services, and migrations |
| `workers` | Ingestion, inference, chemistry, optimization, learning, and simulation runtimes |
| `packages` | Contracts, policy, and isolated engine adapters |
| `infra` | Local scripts, Compose, image builds, cloud adapters, and CI helpers |
| `tests` | Browser, engine, evaluation, performance, and recovery checks |
| `docs` | Current manuals, generated reference, specifications, and evidence |

Internal proprietary repository. Shipped specification fixtures are synthetic.
