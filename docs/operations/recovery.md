# Recovery and upgrades

Recovery combines a compatible database, the correct full vault tree, optional
external model files, credentials, and runtime dependencies. A healthy HTTP
process alone is not a recovered Studio. Start with [backup and restore](backup-restore.md)
and the [state inventory](configuration.md).

## Upgrade an existing installation

1. Record the currently running revision and make a verified, quiesced backup.
2. Read changes to dependencies, migrations, profiles, and native packaging.
3. Stop foreground/native/background API processes and external writers.
4. Install the new revision's locked Python and pnpm dependencies, retaining
   required extras or recreating optional isolated environments.
5. Run migration against the intended database, then rebuild the frontend or
   native app and restart the backend with its existing vault configuration.
6. Check sign-in, representative saved records/files, and any enabled optional
   runtime before resuming recurring or expensive work.

```sh
uv sync --python 3.12 --group dev --frozen
pnpm install --frozen-lockfile
make migrate
pnpm build:web
```

Include `--extra engines` or other required extras in the `uv sync` command when
that installation uses them. A normal web build does not update an installed
native bundle; use [desktop rebuild](desktop-macos.md).

Migrations are defined under `services/studio-api/migrations`. Use `upgrade head`
rather than copying a historical revision number. Inspect migration compatibility
for the versions involved; old ticket evidence is not proof of an arbitrary
future rollback path.

## Interrupted migration

The migration environment wraps PostgreSQL upgrades in a transaction. If a
process fails or is killed, inspect its exit/log and current Alembic revision,
resolve the underlying problem, and rerun `make migrate`. Do not manually mark a
failed migration applied or delete tables to make startup pass.

```sh
uv run alembic -c services/studio-api/migrations/alembic.ini current
uv run alembic -c services/studio-api/migrations/alembic.ini heads
make migrate
```

Do not run `alembic downgrade` on populated research data as a recovery shortcut.
Prefer a verified compatible application revision against the expanded schema,
a forward fix, or a restore to clean destinations from a matching backup.

## Resumable maintenance backfills

`infra/local/resumable_backfill.py` runs an explicit checkpointed, append-only
record-digest backfill. This is a maintenance tool, not a universal job-recovery
command. Use the intended DSN and inspect status first:

```sh
uv run python infra/local/resumable_backfill.py status   --dsn postgresql://studio:studio@127.0.0.1:54329/studio
uv run python infra/local/resumable_backfill.py run   --dsn postgresql://studio:studio@127.0.0.1:54329/studio --batch-size 500
uv run python infra/local/resumable_backfill.py verify   --dsn postgresql://studio:studio@127.0.0.1:54329/studio
```

Each batch commits emitted digests and its checkpoint together. Restarting emits
missing records idempotently. Verification reports missing digests, drift, or
orphan digests; do not overwrite historical digests to hide a mismatch.

## Recover interrupted research and compute

| Work | Recovery behavior |
|---|---|
| Private agent run | Durable step checkpoints and worker leases recover after backend restart; inspect persisted state and events before resending. |
| Recurring private research | Requires enabled owner autopilot, limits, and a running backend; disabling autopilot prevents further scheduling. |
| Private local learning | Expired leases leave interrupted work; use the job's resume action. Transformers resumes optimizer checkpoints; MLX resumes adapters as a warm start. |
| Remote learning worker | Lease/heartbeat expiry records interruption. Restore worker model mappings and uploaded checkpoint availability before resuming. |
| Polymer simulation | Resume completed stage/seed checkpoints within the original cumulative wall-clock cap; an interrupted stage reruns. |
| Older generic task run | Caller-driven reconciliation remains separate from the private agent/learning/simulation supervisors. Inspect that run's cancellation/reconciliation state. |

Cancelling an agent run stops further agent steps. A separately created learning
or simulation job has its own lifecycle and cancellation control. Preserve
completed outputs and check the corresponding job rather than assuming the
conversation cancellation terminated every child activity.

## Restore validation

Restore into clean destinations as described in [backup and restore](backup-restore.md).
Use the application's matching revision to validate a snapshot before upgrading
it. `infra/local/recovery_check.py` compares the schema head to the checked-out
application by default; `--expect-alembic` selects an explicitly expected revision.

The checker inspects required core tables, artifact checksums, derived lineage,
older model serving/training references, capabilities, password/session material,
approval digests, evidence references, source tombstones, and optional broker
references. It does not prove all newer private-state or external-runtime
recovery. Add manual checks for this installation's notebooks, protected sources,
Downloads, models, checkpoints, simulations, and provider Keychain credentials.

If a restore attempt partially fails, retain diagnostics, abandon that target,
and repeat using new empty destinations. Avoid mixing a partial restore with
live data. Switch the real installation to restored state only after validation.

## Retention and deletion

There is no configured universal age-based retention or secure-purge policy.
Source revocation removes access/retrieval and marks derived impact while
preserving source bytes, tombstones, and historical records. Capability/session
revocation preserves history. Notebook trash and source/memory deletion have
record-specific behavior; forgetting a memory does not undo past model training.

A fresh backup may still include revoked/private bytes and old revisions.
Physical cleanup, deletion of exported copies, model unlearning, and secure SSD
or cloud erasure are separate concerns. See [privacy](privacy.md) before treating
a UI deletion or a source revocation as a complete data-erasure action.
