# Local development and native builds

Run commands from the repository root unless a command says otherwise. The supported core uses Python 3.12, the locked uv environment and the pnpm workspace. Docker provides the local PostgreSQL service. Optional model/science runtimes are installed separately.

## Install locked dependencies

Check the local toolchain with `uv --version`, `python3.12 --version`, `node --version`, `pnpm --version`, and `docker compose version`. The workspace declares `pnpm@10.18.3`. Use a Node version supported by the locked frontend toolchain; the CI workflow selects Node 24.

```sh
uv sync --python 3.12 --group dev --frozen
pnpm install --frozen-lockfile
```

`make bootstrap` runs these two installation steps for the core. It does not download model weights, accept a license or provision optional scientific software. Do not edit lockfiles indirectly just to make an unrelated UI change build.

For native RDKit where a compatible wheel exists:

```sh
uv sync --python 3.12 --group dev --extra engines --frozen
```

The full unit/integration/browser suites require this engine profile. Set `UV_NO_SYNC=1` after selecting it so later `uv run` commands retain the installed extras; an implicit sync without `--extra engines` can remove them. See [Testing and documentation](testing-and-docs.md#prepare-the-test-profile).

The core must remain importable without optional engines. See [Workers and engines](workers-and-engines.md) before adding MLX, torch, quantum or simulation dependencies.

## Start the local app

```sh
make dev
```

`infra/local/dev.sh` starts PostgreSQL, waits for readiness, upgrades Alembic to head, launches the installed `.venv` API on `127.0.0.1:8787`, then starts Vite on `127.0.0.1:5173`. It uses ignored `.runtime/` cache/vault directories and refuses to replace existing listeners on those app ports. Ctrl-C stops the owned API/web session; PostgreSQL stays available.

For separate terminals or a debugger:

```sh
docker compose -f infra/local/compose.yaml up -d postgres
.venv/bin/alembic -c services/studio-api/migrations/alembic.ini upgrade head
.venv/bin/uvicorn studio.api.app:create_app --factory --host 127.0.0.1 --port 8787
```

```sh
pnpm dev:web
```

When starting the API separately, choose the intended vault explicitly if you want the same location as `make dev`:

```sh
export STUDIO_VAULT_ROOT="$PWD/.runtime/vault"
```

The default database is the local `studio` development database on loopback port 54329. The default compose credentials are development values. Keep test databases separate and use synthetic records for development examples.

## Verify the service and session

```sh
curl --fail http://127.0.0.1:8787/healthz
curl --fail http://127.0.0.1:8787/readyz
```

Health and readiness are separate probes; inspect the returned capability/database details. Open the UI and complete owner setup once, then use sign-in for later sessions. Use the same origin throughout. A session cookie from `localhost` will not authenticate a page opened at `127.0.0.1`.

Vite proxies `/api` and `/graphql`. To target another loopback API, set `VITE_API_TARGET` when starting Vite or preview. This does not alter backend authorization or its Origin policy. Never put API keys in `VITE_` variables: those variables are frontend-build inputs.

## Build and preview the web client

```sh
pnpm build:web
pnpm --filter studio-web preview --host 127.0.0.1 --port 4173
```

Build runs Relay generation, TypeScript project compilation and Vite. Preview serves the compiled `dist` assets and has its own API proxy declaration. Ensure the backend's allowed origins include the exact intended preview origin when testing state changes; the browser suites configure an isolated setup for this.

Do not expose the development server on LAN or use it as a production deployment. Vite has explicit denials for runtime folders, environment files, key material and repository internals; preserve those boundaries when changing its configuration.

## Enable optional lanes deliberately

Profile switches such as `STUDIO_PROFILE_OPTIMIZATION`, `STUDIO_PROFILE_QUANTUM`, `STUDIO_PROFILE_MATERIALS`, `STUDIO_PROFILE_DESIGN`, `STUDIO_PROFILE_SYNTHESIS`, `STUDIO_PROFILE_TRAINING`, and `STUDIO_PROFILE_LOCAL_AI` gate relevant service lanes. A true flag does not create an image, runtime, model or license.

Use isolated `.runtime/learning-mlx`, `.runtime/learning-science`, `.runtime/learning-transformers`, `.runtime/learning-reinvent` and `.runtime/simulation-radonpy` environments for private-learning/simulation execution as documented in their [learning](../operations/learning-workspace.md) and [simulation](../operations/polymer-simulation.md) runbooks. Restart the API after changing process environment or cached settings.

## Build the native Mac shell

Install Rust, Xcode command-line tools, Docker Desktop and the checkout's Python/runtime prerequisites, then:

```sh
pnpm build:desktop
pnpm open:desktop
pnpm test:desktop
```

The shell bundles the built frontend and records the absolute checkout location. Standard outputs are under `apps/studio-web/src-tauri/target/release/bundle/macos/` and `bundle/dmg/`. `CARGO_TARGET_DIR` can choose a separate target tree for build/open/test while another source app is running.

The current package uses an ad-hoc signature and checkout runtime. Moving the checkout requires rebuilding. It does not bundle Python, Docker or scientific model weights, and these commands do not notarize a public release.

The native runtime prefers port 8788, can reuse an exact verified matching desktop backend, and leaves unrelated or older backends untouched. It applies migrations before opening the bundled same-origin frontend. Quit stops only its own backend child. See [Native macOS app](../operations/desktop-macos.md).

## Work on native startup or downloads

Edit boot presentation in `src/features/desktop/NativeBoot.tsx` and runtime behavior under `src-tauri/src/`. Preserve the three fixed boot commands, origin validation, exact build identity, listener ownership and process-tree cleanup. Do not add arbitrary paths, shell arguments or URLs to boot command payloads.

Native downloads must verify the current app origin and authenticated artifact route, bound filenames, and retain collision-safe private file handling. Ordinary external citations open in the system browser rather than gaining native filesystem access.

After a change, run the relevant Rust/backend/frontend tests and rebuild the package. Quit the app before `pnpm smoke:desktop`: the smoke check needs an unused dedicated port and checks cold launch, bundled native handoff, owned cleanup and separately owned backend reuse.

## Fix setup failures without losing records

For occupied ports, inspect the existing service before starting another one. For PostgreSQL startup failures, check Docker and `pg_isready`. For migration failures, inspect the current Alembic revision and use [Recovery](../operations/recovery.md). Do not remove volumes or the vault as a routine troubleshooting step. See [Backup and restore](../operations/backup-restore.md) before destructive reset experiments.
