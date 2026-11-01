# Configuration and stored state

Use this inventory before moving a checkout, changing a runtime, or making a
backup. The [generated reference](../reference/README.md) enumerates environment
options directly from source; this page explains their operational relationships.
Restart the API after changing settings: core settings are cached per process.

## Processes and ports

| Process | Default | Ownership |
|---|---|---|
| PostgreSQL | `127.0.0.1:54329` | Compose service and persistent named volume |
| Browser development API | `127.0.0.1:8787` | Foreground Uvicorn or `make dev` |
| Vite development UI | `127.0.0.1:5173` | Foreground pnpm process; proxies API calls |
| Native desktop API/UI | Prefer `127.0.0.1:8788`; verified compatible 8787 may be reused | Desktop-owned child or verified existing backend |
| Optional background API | `127.0.0.1:8787` | Opt-in macOS LaunchAgent |
| Optional SearXNG | `127.0.0.1:8088` | Compose `research` profile |
| E2E API/UI | `127.0.0.1:8790` and `127.0.0.1:4173` | Test subprocesses using resettable `studio_e2e` DB |

The native app verifies its build identity and frontend/database readiness before
reusing a backend. `/healthz` alone does not prove compatibility or database
health. A background launcher waits for a healthy service on 8787 to finish;
it does not replace that process. Keep one authoritative backend per active
installation when changing configuration or performing maintenance.

## Select the right configuration

| Setting | Meaning and default |
|---|---|
| `STUDIO_DATABASE_URL` | SQLAlchemy/PostgreSQL connection; default local Compose `studio` database |
| `STUDIO_VAULT_ROOT` | Base of all Studio-managed artifact files; raw API default `~/.local/share/chemistry-studio/vault` |
| `STUDIO_RESEARCH_DOWNLOADS_ROOT` | Human-review source copies; default `~/Downloads/Chemistry Studio` |
| `STUDIO_ALLOWED_ORIGINS` | Comma-separated explicit local browser origins; not a LAN-hosting switch |
| `STUDIO_SESSION_TTL_SECONDS` | Session lifetime; default 43200 seconds |
| `STUDIO_ARTIFACT_MAX_BYTES` | Streaming artifact size cap; default 512 MiB |
| `STUDIO_PROFILE_*` | Optional older engine lanes; false unless explicitly enabled |
| `VITE_API_TARGET` | Vite development/preview proxy destination; default local API on 8787 |
| `STUDIO_SEARXNG_URL` | Trusted search service endpoint used for optional web discovery |
| `STUDIO_*_PYTHON` | Administrator-selected optional runtime interpreter paths |
| `STUDIO_LAMMPS_EXEC` | Trusted native LAMMPS executable for simulations |

`STUDIO_BIND_HOST` and `STUDIO_PORT` inform application settings; direct Uvicorn
binding is selected by its `--host` and `--port` arguments. The desktop launcher
sets both consistently. Some `Settings` fields are constants and have no
environment override; use the generated inventory rather than inventing names.

`make dev`, desktop launch, and the background script select checkout
`.runtime/vault`. A directly launched API without `STUDIO_VAULT_ROOT` selects the
home-directory default. Confirm the actual launch command and environment;
never infer the active vault from a successful health request. The legacy name
`STUDIO_DOWNLOADS_ROOT` is not the private library's Downloads override.

## State locations and backup coverage

| State | Location | Included by database plus full active-vault backup? |
|---|---|---|
| Shared records, notebooks, private conversations/memory, datasets, jobs, permissions, audit, sessions, provider metadata | PostgreSQL | Yes, in the database dump |
| Committed artifacts and upload-related state | Active vault; DB carries references | Committed files and DB rows are included; pause writes for consistency |
| Protected retained research originals/text | Active vault `private-library` subtree | Yes, when the entire vault is copied |
| Human-review Downloads | Downloads root plus workspace/owner subdirectories | No; copy separately if retaining these copies matters |
| Local learning job outputs, adapters, checkpoints, and previews | Active vault under workspace/`learning`/owner | Yes, when inside the selected vault; stop jobs before copying |
| Catalog model downloads | Learning job output/model location, normally under active vault | Yes for vault-contained files; verify each model's registered location |
| Imported existing models | Administrator-selected local model directory | Only if physically inside the backed-up vault; external paths need separate copies |
| Simulation inputs, stages, logs, trajectories, and checkpoints | Active vault under workspace/`simulations`/owner | Yes for the full tree; quiesce running jobs |
| Remote-worker checkpoints/models/work directories | Worker host `--work-dir` and explicit model mappings | No; server receives only uploaded artifacts/checkpoints |
| Provider API keys | macOS login Keychain | No; re-enter keys through Providers on recovery |
| Optional Python runtimes, Python/JS/Rust packages | `.venv`, `node_modules`, `.runtime/learning-*`, `.runtime/simulation-radonpy`, build caches | No; recreate using lockfiles and documented requirements |
| SearXNG settings | `.runtime/research-search` | No; preserve separately or recreate with the launcher |
| Desktop/background logs | `.runtime/desktop`, `.runtime/background` | No; preserve separately for incident evidence |
| Background LaunchAgent | User Library LaunchAgents, fixed Chemistry Studio label | No; reinstall explicitly from the recovered checkout |

The PostgreSQL data volume is not a replacement for a dump. Keep backups outside
the active vault and outside served frontend roots. Do not publish runtime paths,
credentials, private files, or model artifacts in docs assets.

## Optional runtime profiles

The default dependency profile starts without scientific engines or model
libraries. Native RDKit uses the `engines` extra. Older adapter lanes use
`local_ai`, `optimization`, `quantum`, `materials`, or `training` extras plus
appropriate images and flags. Private learning uses separate detected
interpreters or explicit backend overrides and is enabled independently of the
older training profile. [Learning setup](learning-workspace.md) explains the
interpreter precedence and compatible data contracts.

Provider metadata is workspace-scoped; API keys are write-only Keychain items.
An empty key edit retains the current key. Changing provider destinations with
an existing key requires explicit replacement/removal. See [providers](inference-providers.md)
for consent, revision binding, cleanup, and Linux secure-storage limitations.

Use [backup and restore](backup-restore.md) before path changes and
[troubleshooting](troubleshooting.md) when records or models appear missing.
