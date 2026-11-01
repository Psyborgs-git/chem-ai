# Environment and build configuration reference

This inventory lists names found in first-party sources, including test and build settings. It reads source text only. No value is read from your environment, Keychain, runtime files or credentials. Unset/default descriptions below are static code behavior. Never paste secrets into source or Help.

## Build and development

### CARGO_BUILD_JOBS

Maximum concurrent native Cargo build jobs.

**Default / unset behavior:** 4 in desktop.sh.

**Type and constraints:** Positive integer understood by Cargo.

Source: `infra/local/desktop.sh`.

### CARGO_TARGET_DIR

Native build output directory.

**Default / unset behavior:** apps/studio-web/src-tauri/target.

**Type and constraints:** Directory; desktop.sh reuses the supplied target location.

Source: `infra/local/desktop.sh`, `tests/desktop/smoke.mjs`.

### PNPM

Override the pnpm executable used by Make.

**Default / unset behavior:** pnpm.

**Type and constraints:** Executable/command understood by Make recipes.

Source: `Makefile`.

### UV

Override the uv executable used by Make.

**Default / unset behavior:** uv.

**Type and constraints:** Executable/command understood by Make recipes.

Source: `Makefile`.

### UV_CACHE_DIR

uv dependency cache location used by make dev.

**Default / unset behavior:** Repository .runtime/uv-cache in dev.sh.

**Type and constraints:** Directory; inherited override supported.

Source: `infra/local/dev.sh`.

### UV_PYTHON_INSTALL_DIR

uv managed Python installation directory in make dev.

**Default / unset behavior:** Repository .runtime/python.

**Type and constraints:** Directory; inherited override supported.

Source: `infra/local/dev.sh`.

### VITE_API_TARGET

Vite development proxy target for /graphql and /api.

**Default / unset behavior:** http://127.0.0.1:8787.

**Type and constraints:** Build/dev-server environment setting; does not expose a production API base URL to application code.

Source: `apps/studio-web/vite.config.ts`.

## Desktop

### STUDIO_DESKTOP_BUILD_ID

Identity label returned by the desktop runtime probe.

**Default / unset behavior:** Unset outside native startup; native launcher injects its build ID.

**Type and constraints:** Nonsecret build label, not a credential or readiness guarantee.

Source: `apps/studio-web/src-tauri/src/runtime.rs`, `services/studio-api/src/studio/config/settings.py`, `tests/desktop/smoke.mjs`.

### STUDIO_DESKTOP_FRONTEND_DIR

Enable the API-hosted built frontend and desktop runtime probe.

**Default / unset behavior:** Unset; ordinary API does not serve frontend files.

**Type and constraints:** Absolute built frontend directory containing index.html; cannot overlap the private vault.

Source: `apps/studio-web/src-tauri/src/runtime.rs`, `infra/local/background.sh`, `services/studio-api/src/studio/api/desktop.py`, `services/studio-api/src/studio/config/settings.py`, `services/studio-api/tests/unit/test_desktop_web.py`, `tests/desktop/smoke.mjs`.

## Operations

### STUDIO_PGTOOL_CONTAINER

Container used for pg_dump/pg_restore when local PostgreSQL tools are unavailable.

**Default / unset behavior:** chem-studio-postgres.

**Type and constraints:** Existing container name; used by backup tools, not by API request routing.

Source: `infra/local/backup.py`, `tests/integration/migrations/conftest.py`.

## Optional integrations

### STUDIO_ELN_API_TOKEN

eLabFTW API credential.

**Default / unset behavior:** Unset; no default credential.

**Type and constraints:** Secret; sent as Authorization only by the explicitly configured bridge.

Source: `packages/engine-adapters/elabftw/engine_adapter_elabftw/contracts.py`, `services/studio-api/tests/security/test_eln_bridge_security.py`, `services/studio-api/tests/unit/test_eln_bridge.py`.

### STUDIO_ELN_BASE_URL

eLabFTW instance base URL.

**Default / unset behavior:** Unset; bridge reports unconfigured.

**Type and constraints:** Remote instance URL; activation remains gated.

Source: `packages/engine-adapters/elabftw/engine_adapter_elabftw/contracts.py`, `services/studio-api/tests/security/test_eln_bridge_security.py`, `services/studio-api/tests/unit/test_eln_bridge.py`.

### STUDIO_ELN_ENABLED

Explicit eLabFTW remote bridge activation.

**Default / unset behavior:** False.

**Type and constraints:** 1/true/yes/on. Configuration without this switch remains configured_disabled.

Source: `packages/engine-adapters/elabftw/engine_adapter_elabftw/adapter.py`, `packages/engine-adapters/elabftw/engine_adapter_elabftw/contracts.py`, `services/studio-api/tests/security/test_eln_bridge_security.py`, `services/studio-api/tests/unit/test_eln_bridge.py`.

### STUDIO_ELN_TIMEOUT_SECONDS

eLabFTW request timeout.

**Default / unset behavior:** 10 seconds.

**Type and constraints:** Integer seconds; invalid text falls back to 10 and values below 1 clamp to 1.

Source: `packages/engine-adapters/elabftw/engine_adapter_elabftw/contracts.py`, `services/studio-api/tests/security/test_eln_bridge_security.py`.

### STUDIO_ELN_VERIFY_TLS

Verify eLabFTW TLS certificates.

**Default / unset behavior:** True.

**Type and constraints:** Boolean true-set; disabling removes TLS verification and is unsuitable for a trusted remote connection.

Source: `packages/engine-adapters/elabftw/engine_adapter_elabftw/contracts.py`.

## Optional science and learning

### STUDIO_CHEMPROP_PYTHON

Choose the chemprop runtime Python interpreter.

**Default / unset behavior:** Backend-specific interpreter; optional app-local .runtime environment when present, with the implemented fallback.

**Type and constraints:** Executable path; keep optional ML/science dependencies separate from the API environment. Backend-specific training overrides precede STUDIO_TRAINING_PYTHON.

Source: `services/studio-api/src/studio/domain/learning/workspace.py`.

### STUDIO_LAMMPS_EXEC

Select the LAMMPS executable for the isolated polymer simulation runtime.

**Default / unset behavior:** Runtime probes its supported LAMMPS installation.

**Type and constraints:** Executable path in the simulation environment; not an arbitrary user request option.

Source: `services/studio-api/src/studio/domain/simulations/dispatcher.py`, `services/studio-api/tests/unit/test_simulations.py`, `workers/simulation/radonpy_worker.py`.

### STUDIO_MLX_PYTHON

Choose the mlx runtime Python interpreter.

**Default / unset behavior:** Backend-specific interpreter; optional app-local .runtime environment when present, with the implemented fallback.

**Type and constraints:** Executable path; keep optional ML/science dependencies separate from the API environment. Backend-specific training overrides precede STUDIO_TRAINING_PYTHON.

Source: `services/studio-api/src/studio/domain/learning/workspace.py`.

### STUDIO_PROFILE_DESIGN

Enable the design capability profile.

**Default / unset behavior:** False (off).

**Type and constraints:** Case-insensitive 1/true/yes/on enables. Required extras/images/models and policy checks still apply; enabling a flag alone does not install an engine.

Source: `services/studio-api/src/studio/config/settings.py`, `services/studio-api/src/studio/domain/chemistry/design.py`.

### STUDIO_PROFILE_LOCAL_AI

Enable the local ai capability profile.

**Default / unset behavior:** False (off).

**Type and constraints:** Case-insensitive 1/true/yes/on enables. Required extras/images/models and policy checks still apply; enabling a flag alone does not install an engine.

Source: `services/studio-api/src/studio/api/capabilities.py`, `services/studio-api/src/studio/config/settings.py`.

### STUDIO_PROFILE_MATERIALS

Enable the materials capability profile.

**Default / unset behavior:** False (off).

**Type and constraints:** Case-insensitive 1/true/yes/on enables. Required extras/images/models and policy checks still apply; enabling a flag alone does not install an engine.

Source: `services/studio-api/src/studio/config/settings.py`, `services/studio-api/src/studio/domain/chemistry/materials.py`.

### STUDIO_PROFILE_OPTIMIZATION

Enable the optimization capability profile.

**Default / unset behavior:** False (off).

**Type and constraints:** Case-insensitive 1/true/yes/on enables. Required extras/images/models and policy checks still apply; enabling a flag alone does not install an engine.

Source: `services/studio-api/src/studio/config/settings.py`.

### STUDIO_PROFILE_QUANTUM

Enable the quantum capability profile.

**Default / unset behavior:** False (off).

**Type and constraints:** Case-insensitive 1/true/yes/on enables. Required extras/images/models and policy checks still apply; enabling a flag alone does not install an engine.

Source: `services/studio-api/src/studio/config/settings.py`, `services/studio-api/src/studio/domain/chemistry/quantum.py`.

### STUDIO_PROFILE_SYNTHESIS

Enable the synthesis capability profile.

**Default / unset behavior:** False (off).

**Type and constraints:** Case-insensitive 1/true/yes/on enables. Required extras/images/models and policy checks still apply; enabling a flag alone does not install an engine.

Source: `services/studio-api/src/studio/config/settings.py`, `services/studio-api/src/studio/domain/chemistry/synthesis.py`.

### STUDIO_PROFILE_TRAINING

Enable the training capability profile.

**Default / unset behavior:** False (off).

**Type and constraints:** Case-insensitive 1/true/yes/on enables. Required extras/images/models and policy checks still apply; enabling a flag alone does not install an engine.

Source: `services/studio-api/src/studio/config/settings.py`, `services/studio-api/src/studio/domain/learning/rl.py`, `services/studio-api/src/studio/domain/learning/sft.py`.

### STUDIO_REINVENT_PYTHON

Choose the reinvent runtime Python interpreter.

**Default / unset behavior:** Backend-specific interpreter; optional app-local .runtime environment when present, with the implemented fallback.

**Type and constraints:** Executable path; keep optional ML/science dependencies separate from the API environment. Backend-specific training overrides precede STUDIO_TRAINING_PYTHON.

Source: `services/studio-api/src/studio/domain/learning/workspace.py`.

### STUDIO_SIMULATION_PYTHON

Choose the simulation runtime Python interpreter.

**Default / unset behavior:** Backend-specific interpreter; optional app-local .runtime environment when present, with the implemented fallback.

**Type and constraints:** Executable path; keep optional ML/science dependencies separate from the API environment. Backend-specific training overrides precede STUDIO_TRAINING_PYTHON.

Source: `services/studio-api/src/studio/domain/simulations/service.py`.

### STUDIO_TRAINING_PYTHON

Choose the training runtime Python interpreter.

**Default / unset behavior:** Backend-specific interpreter; optional app-local .runtime environment when present, with the implemented fallback.

**Type and constraints:** Executable path; keep optional ML/science dependencies separate from the API environment. Backend-specific training overrides precede STUDIO_TRAINING_PYTHON.

Source: `services/studio-api/src/studio/domain/learning/workspace.py`.

### STUDIO_TRANSFORMERS_PYTHON

Choose the transformers runtime Python interpreter.

**Default / unset behavior:** Backend-specific interpreter; optional app-local .runtime environment when present, with the implemented fallback.

**Type and constraints:** Executable path; keep optional ML/science dependencies separate from the API environment. Backend-specific training overrides precede STUDIO_TRAINING_PYTHON.

Source: `services/studio-api/src/studio/domain/learning/workspace.py`.

## Research connectors

### STUDIO_OPENALEX_API_KEY

Optional OpenAlex connector credential.

**Default / unset behavior:** Unset; connector attempts its supported unauthenticated behavior.

**Type and constraints:** Secret API key; never put a real value in documentation or commit it.

Source: `services/studio-api/src/studio/domain/library/research.py`.

### STUDIO_SEARXNG_URL

Local SearXNG JSON search endpoint.

**Default / unset behavior:** http://127.0.0.1:8088.

**Type and constraints:** Origin URL; start optional research-search service. Connector failures are explicit.

Source: `infra/local/background.sh`, `services/studio-api/src/studio/domain/library/research.py`, `services/studio-api/tests/unit/test_library_research.py`.

## Runtime

### STUDIO_ALLOWED_ORIGINS

Browser Origin allowlist for state-changing requests.

**Default / unset behavior:** Loopback origins at API 8787 and Vite 5173.

**Type and constraints:** Comma-separated exact origins; this does not enable LAN hosting or TLS.

Source: `apps/studio-web/src-tauri/src/runtime.rs`, `services/studio-api/src/studio/config/settings.py`, `tests/desktop/smoke.mjs`, `tests/e2e/serve.sh`, `tests/performance/test_cs1103_benchmark.py`.

### STUDIO_ARTIFACT_MAX_BYTES

Maximum streamed/committed artifact bytes.

**Default / unset behavior:** 536870912 (512 MiB).

**Type and constraints:** Integer byte count; archive member/decompression/ratio ceilings are separate fixed Settings fields, not environment overrides.

Source: `services/studio-api/src/studio/config/settings.py`.

### STUDIO_BIND_HOST

Settings value describing the loopback bind host.

**Default / unset behavior:** 127.0.0.1.

**Type and constraints:** String. Explicit uvicorn --host controls its listener; middleware still restricts allowed Host headers to loopback.

Source: `services/studio-api/src/studio/config/settings.py`.

### STUDIO_DATABASE_URL

PostgreSQL connection URL shared by API and Alembic.

**Default / unset behavior:** Local Compose development database on 127.0.0.1:54329/studio.

**Type and constraints:** PostgreSQL URL; treat configured credentials as secrets. Alembic environment overrides the ini URL.

Source: `services/studio-api/migrations/env.py`, `services/studio-api/src/studio/config/settings.py`, `services/studio-api/tests/conftest.py`, `services/studio-api/tests/integration/test_inference_style_migration.py`, `tests/e2e/serve.sh`, `tests/e2e/serve_api.py`, `tests/integration/migrations/conftest.py`, `tests/integration/recovery/backup_restore_check.py`, `tests/integration/recovery/no_egress_check.py`, `tests/performance/conftest.py`, `tests/performance/test_cs1103_benchmark.py`, `tests/unit/test_e2e_server.py`.

### STUDIO_EVENT_MAX_SECONDS

Maximum lifetime for an individual SSE connection before reconnect.

**Default / unset behavior:** 55 seconds.

**Type and constraints:** Float seconds read at module import; reconnect using persisted sequence semantics.

Source: `services/studio-api/src/studio/api/events/routes.py`, `tests/e2e/par-08a.spec.ts`, `tests/e2e/serve.sh`, `tests/performance/test_cs1103_benchmark.py`.

### STUDIO_PORT

Settings value describing the API port.

**Default / unset behavior:** 8787; native launcher supplies its chosen desktop port (normally 8788).

**Type and constraints:** Integer; explicit uvicorn --port controls listener startup.

Source: `apps/studio-web/src-tauri/src/runtime.rs`, `services/studio-api/src/studio/config/settings.py`, `tests/desktop/smoke.mjs`.

### STUDIO_RESEARCH_DOWNLOADS_ROOT

Base directory for retained owner-private research files.

**Default / unset behavior:** App-specific Chemistry Studio research Downloads under the user Downloads directory.

**Type and constraints:** Filesystem directory; owner/workspace subdirectories remain private. It is separate from normal arbitrary web downloads.

Source: `services/studio-api/src/studio/domain/library/service.py`, `services/studio-api/tests/integration/test_private_library.py`, `services/studio-api/tests/integration/test_research_workflows.py`, `services/studio-api/tests/integration/test_retained_artifact_archive.py`, `services/studio-api/tests/unit/test_agent_dataset_origin.py`, `services/studio-api/tests/unit/test_private_library.py`, `tests/e2e/serve.sh`.

### STUDIO_SESSION_TTL_SECONDS

Issued session lifetime.

**Default / unset behavior:** 43200 seconds (12 hours).

**Type and constraints:** Integer seconds; expired/revoked sessions are rejected.

Source: `services/studio-api/src/studio/config/settings.py`.

### STUDIO_VAULT_ROOT

Private artifact/checkpoint/job vault.

**Default / unset behavior:** Direct API: ~/.local/share/chemistry-studio/vault. make dev, background and native launch: repository .runtime/vault unless their supported override applies.

**Type and constraints:** Directory resolved to an absolute path. Preserve the matching database and vault in backups; do not put it inside a served web root.

Source: `apps/studio-web/src-tauri/src/runtime.rs`, `apps/studio-web/src/features/help/HelpPage.test.tsx`, `infra/local/background.sh`, `infra/local/dev.sh`, `infra/local/pilot_gate.py`, `services/studio-api/src/studio/config/settings.py`, `services/studio-api/tests/unit/test_studio_docs.py`, `tests/desktop/smoke.mjs`, `tests/e2e/help.spec.ts`, `tests/e2e/serve.sh`, `tests/performance/test_cs1103_benchmark.py`.

## Self-hosted worker

### STUDIO_WORKER_TOKEN

Existing owner/user session token for authenticated training-worker requests.

**Default / unset behavior:** No default; workspace_worker exits with an argument error if absent.

**Type and constraints:** Secret token via environment on a trusted worker. Never returned to trainer subprocesses or forwarded through redirects.

Source: `workers/training/workspace_worker.py`.

## Test-only

### STUDIO_BROWSER_EXECUTABLE_PATH

Use an installed Chromium executable for browser acceptance tests.

**Default / unset behavior:** Unset; Playwright uses its managed browser.

**Type and constraints:** Executable path, passed to Playwright launchOptions. Does not affect the application runtime.

Source: `tests/e2e/playwright.config.ts`, `tests/native-ui/playwright.config.ts`.

### STUDIO_SIMULATION_REAL_TEST

Opt in to physical native polymer MD integration checks.

**Default / unset behavior:** Unset; the real-runtime test is skipped.

**Type and constraints:** Set exactly 1 only when the isolated simulation runtime is installed. This does not enable production capabilities.

Source: `services/studio-api/tests/integration/test_simulations.py`.

## Worker-controlled environment

Learning workers construct a scrubbed environment: PATH, LANG, LC_ALL, SYSTEMROOT and TMPDIR may be inherited; HF_HOME and XDG_CACHE_HOME point to the per-job cache; PYTHONPATH is restricted to repository source paths; PYTHONUNBUFFERED=1, PYTHONDONTWRITEBYTECODE=1, TOKENIZERS_PARALLELISM=false, HF_HUB_DISABLE_TELEMETRY=1, DO_NOT_TRACK=1, WANDB_MODE=disabled, OMP_NUM_THREADS=2 and MKL_NUM_THREADS=2 are set. Normal training is HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1; the approved model-download job is the exception. Simulation builds its own environment and forwards the explicitly configured LAMMPS path. Native build scripts set CARGO_HOME, CARGO_INCREMENTAL and CARGO_PROFILE_RELEASE_DEBUG themselves. These are implementation-controlled values, not additional Studio configuration switches; generic upstream library environment variables are outside the application settings contract. CI sets UV_FROZEN=1 in its workflow to enforce the committed dependency lock; this is a workflow-controlled build value. Generic CI-provider environment variables are not additional Studio runtime settings.
