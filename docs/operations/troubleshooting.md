# Troubleshooting

Begin with the process, state path, and saved error for the failing operation.
Preserve private diagnostics; remove tokens, passwords, private text, and
connection strings before sharing them. [Configuration](configuration.md) lists
ports and data locations; [recovery](recovery.md) covers interrupted work.

## Startup and sign-in

| Symptom | Check and recovery |
|---|---|
| Docker cannot be reached | Start Docker Desktop/daemon, confirm `docker info`, then retry startup. |
| PostgreSQL connection refused | Confirm Compose is up and TCP `pg_isready` succeeds on the expected container. |
| Port 54329 already allocated | Inspect the listener/container. Do not delete its volume or silently use another database. |
| API/Vite port occupied | Open the existing local UI or identify its owner; `make dev` deliberately refuses replacement. |
| `/healthz` works but sign-in fails | Check database connectivity, applied migrations, selected vault, and Host/Origin configuration. |
| First-run setup is no longer shown | An owner exists. Sign in using that owner's chosen login; setup is one-time. |
| Session expired | Sign in again. An expired route should remain the destination. |
| `FORBIDDEN` | Check capability, principal kind, owner-private scope, and revoked grants. Administrator grants do not expose another author's private library. |
| Native build launches old UI | Rebuild and reopen the intended app bundle; an existing process retains its original frontend/build identity. |
| Native launch cannot access checkout | Allow the macOS Documents permission when appropriate; do not move/delete the installed runtime to bypass it. |

The database password is not the Studio account password. There is no delivered
password-reset screen; account repair is an owner-controlled service-layer
maintenance action requiring a backup and identity verification.

## Saved content and edits

| Symptom | Check and recovery |
|---|---|
| Saved attachment or calculation file is missing | Confirm the API uses the same database and active vault as when it was saved. Check a verified backup before changing records. |
| Notebook revision conflict | Preserve the local draft, reload the current revision, compare, then save a deliberate merged edit. Do not overwrite another update blindly. |
| Source cannot be opened or reused | Review current source rights, revocation, notebook opt-outs, and original checksum. Earlier access does not imply current permission. |
| Downloads folder is unexpected | Use `STUDIO_RESEARCH_DOWNLOADS_ROOT`; review copies are distinct from protected vault originals. |
| Task closeout is blocked | Read the evaluator's missing/failed checks, contract revision, applicable reviewed measurements, and required metrics. |
| Measurement value needs correction | Add an amendment with its reason; preserve the original observation and provenance. |

## Providers and research

| Symptom | Check and recovery |
|---|---|
| Provider key cannot be saved | Unlock macOS login Keychain. Unsupported storage has no plaintext fallback. |
| Pending credential cleanup | Use **Retry key cleanup** after unlocking Keychain; unlocking alone does not perform deletion. |
| Destination edit rejected | Replace or explicitly remove the existing key before changing its provider/destination. |
| Provider selection became stale | Reload metadata and authorize the current revision before sending. |
| Connection test passes but research fails | The test only fetches the model list; generation, tools, protocol, model access, and budgets are separate. |
| Private context omitted | Check owner disclosure consent, current source export/AI/training rights, and provider revision. |
| Recurring work does not run | Check autopilot, due interval, resource/pricing budgets, and the backend process. Sleep/power-off suspends work. |
| Agent is cancelled but training continues | Cancel the learning job separately; the conversation and compute job have separate lifecycles. |

Do not retry a potentially charged provider request by repeatedly starting new
runs. Inspect the persisted run, error, and recorded usage first.

## Engines, learning, simulations, and storage

| Symptom | Check and recovery |
|---|---|
| `ENGINE_UNAVAILABLE` | Check the requested profile, pinned image or optional interpreter, dependency probe, and hardware availability. |
| MLX unavailable on a Mac | It requires Apple Silicon, the MLX environment, and Metal accessible to that process. |
| Preflight blocks training | Resolve data rights, grouped partitions, model/backend compatibility, device, or disk findings before recreating the job. |
| Imported model fails after moving/restoring | Recover its registered external path or deliberately register the correct compatible asset. |
| Job interrupted after API restart | Inspect lease/checkpoint state, then use the job's resume action. |
| Simulation resume exhausts time | Its wall-clock budget is cumulative across attempts; resume does not reset it. |
| Out of disk space | Free unrelated space or expand storage. Do not delete active vault files, checkpoints, or retained originals behind the database. |
| Restore checksum mismatch | Reject the damaged copy; restore from an intact verified backup into clean destinations. |

Native logs are under `.runtime/desktop/runtime.log`; optional background logs
are under `.runtime/background/service.log`. Browser test traces are under
`test-results`. Logs and job artifacts may contain research data even when
credential redaction is implemented.

## Local LoRA answers and tool calls

A selected LoRA uses its saved base-model directory and adapter files. Selection does not activate, replace, or retrain a model. Keep the compatible base files and the optional MLX/Transformers runtime available; an adapter is not a standalone model.

For a failed question, inspect the saved run error, then test that candidate through **Local learning → Models → Preview**. Structured JSON answers and the application's native tool schemas are supported. After updating the backend, restart the process that serves the app so it loads the new parser and tool handling; a process already running keeps its imported code.

Runtime readiness and answer quality are separate. An adapter trained for a narrow format can still repeat text, omit an answer, or keep requesting tools under the broader Agent prompt. Compare it with its unchanged base using a separate explicit selection, inspect held-out evaluation, and choose a compatible model. The app does not silently fall back to the base when the selected adapter behaves poorly.

Documentation tools read static manuals. They do not inspect model quality or retrain a candidate. See [learning and models](../usage/learning-and-models.md) and [the model glossary](../usage/chemistry-glossary.md).

## Documentation and build errors

For documentation edits, run `make docs-generate`, `make docs-check`, and
`pnpm docs:check` as described in [testing and docs](../development/testing-and-docs.md).
Do not widen Vite filesystem access or publish `.runtime` to resolve a broken
help link. Current bundled manuals use an explicit manifest; historical sources
are repository references rather than automatically served files.
