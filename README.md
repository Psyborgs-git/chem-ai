# Chemistry Studio

A **local-first** chemistry-research workspace: projects, research
tasks with frozen success contracts, quarantined evidence intake,
manual-first lab records, retrieval, scoped optimization/learning
plumbing — all behind capability-based access on a single-machine
PostgreSQL deployment.

## Honest status — read this first

This repository is a **verified pilot + release hardening**, not a
finished scientific platform:

- **Live and verified:** persistence, artifact vault, capabilities +
  loopback auth, GraphQL/Relay UI, import→review→claim pipeline,
  research sessions, lab plans/executions/measurements/corrections,
  evaluator-driven closeout, backup/restore with integrity checks,
  streaming events, export-review machinery.
- **Private research workspace:** tool-using agent sidebar, multiple models per
  provider, private notebooks and sourced memory, retained Downloads, custom
  datasets, durable learning jobs, and recurring research. Native MLX LoRA and
  Chemprop regression/classification have real synthetic-data training smoke
  evidence; this is software verification, not scientific model qualification.
- **Legacy fixture-only / mechanism-verified:** optimization (BayBE), quantum/
  materials/design/synthesis adapters, local inference (2B fixture
  model), SFT/RL training, model registry + promotion gate. All real
  containerized execution, all on synthetic data —
  `scientificStatus = not_validated` everywhere.
- **Not configured / blocked:** cloud science-compute egress (no approved provider —
  U08/U09/U11), eLabFTW bridge (CS-0506, U16), team/LAN deployment
  (U07), real training at scale (U08/U13), scientific thresholds
  (U14), instrument control (by design — none exists).

Full evidence: [`docs/execution/release/release-matrix.md`](docs/execution/release/release-matrix.md)
(per-ticket trace to merge PR + acceptance tests) and
[`docs/execution/release/unknowns-register.md`](docs/execution/release/unknowns-register.md).

## Quick start

Requires Docker, `uv` (Python 3.12), Node ≥ 20 + `pnpm`.

```bash
uv sync --python 3.12 --group dev --frozen
pnpm install --frozen-lockfile
docker compose -f infra/local/compose.yaml up -d postgres
make migrate
uv run --group dev uvicorn studio.api.app:create_app \
  --factory --host 127.0.0.1 --port 8787     # API
pnpm --filter studio-web dev                  # UI → http://127.0.0.1:5173
```

Open the UI and create the first owner account using its setup form.
Subsequent visits show the sign-in form. Details are in
[`docs/operations/installation.md`](docs/operations/installation.md).
`make verify-core` runs the
deterministic check battery; `make help` lists the full command
contract.

For local molecular calculations, install the native RDKit profile:

```bash
uv sync --python 3.12 --group dev --extra engines --frozen
make dev
```

Inside a task, choose **Run calculation**, enter a SMILES structure
(for example, ethanol `CCO`), and select **Calculate properties**.
The saved result includes descriptors, the input digest, engine version,
and execution provenance. These are computed structural descriptors;
laboratory evidence remains a separate class.

## Agent and private library

Open **Agent** in the header to research, use application tools, and manage
learning jobs. Existing provider credentials are reused securely; each connection
can have multiple models and role assignments. Configure private-context consent
and bounded recurring work in Agent settings.

**Notebooks**, **Research library**, **Downloads**, **Research memory**, and
**Local learning** are available in navigation. Research originals and cited files
remain available for human review in the app's dedicated Downloads folder.
See [agentic research](docs/operations/agentic-research.md) and
[local/self-hosted learning](docs/operations/learning-workspace.md) for setup,
ownership, model runtimes, and verification limits.

## Documentation map

- **Runbooks** — [`docs/operations/`](docs/operations/README.md):
  installation, user, scientific, admin, model-ops, privacy,
  backup/restore, recovery, cloud-security posture.
- **Release evidence** — [`docs/execution/release/`](docs/execution/release/):
  release matrix + unknowns register; per-ticket evidence in
  `docs/execution/tickets/`; benchmarks in `docs/execution/benchmarks/`;
  residual security register in `docs/execution/security/`.
- **Specification** — `docs/chemistry-studio/` (handoff pack v1.0.1:
  `CHEMISTRY_STUDIO_HANDOFF.md`, `WORK_PACKAGES.md`, `planning/`,
  `contracts/`, `fixtures/`).

## Layout

| Path | Contents |
|---|---|
| `services/studio-api` | FastAPI + Strawberry GraphQL backend (`studio.*`) |
| `apps/studio-web` | React + TypeScript + Relay web app (Vite) |
| `workers/` | isolated worker packages (ingestion, inference, chemistry adapters, optimization, training) |
| `packages/` | `contracts` (versioned DTOs), `policy` (capability vocabulary), `engine-adapters` |
| `infra/` | `local/` (compose, backup/recovery/backfill tools), `ci/` checks, `cloud/` broker + providers, `images/` engine Dockerfiles |
| `tests/` | e2e (Playwright), engines, eval, performance, recovery |

## License / proprietary note

Internal implementation repository. Specification contents and fixtures
are synthetic — no real formulations or executable procedures ship in
this repo.
