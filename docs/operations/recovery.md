# Recovery — upgrades, interruption, restore, retention (CS-1102)

Operational contract for schema upgrades, resumable backfills, and
fresh-machine restore for the local/core profile. Everything below is
backed by executed runs (see `docs/execution/tickets/CS-1102.md`);
verify against *your* environment before relying on it operationally.
See `backup-restore.md` (CS-0505) for the per-command backup runbook.

## 1. Upgrade posture (§26.2)

The alembic chain uses **expand → migrate → contract** ordering for
populated installs. `migrations/env.py` wraps each `upgrade` run in a
single transaction (`context.begin_transaction()`), so a killed or
failed upgrade rolls back atomically — there is no half-migrated
schema to repair.

Verified behaviour (AT-1102-1, AT-1102-2 — real runs, testcontainers
`postgres:16.10-alpine`):

- Populated `0012_evidence_revocation` → `head` upgrade preserves every
  pre-existing row byte-for-byte on its projected columns: contract
  `content_hash` values still hash-verify, approval `bound_digest`s are
  intact, artifact checksums still match vault bytes, all FK lineage
  resolves, and capability grants (including revoked ones, which stay
  *denied*) authorize identically via `load_context`.
- Post-upgrade schema deltas land cleanly on populated tables:
  `outbox_events.seq` is backfilled unique non-null on existing rows
  (0016), `uq_approvals_scope_id` is created (0017), and the three
  immutability triggers `optimization_definition_immutable`,
  `analytical_series_immutable`, `analytical_comparison_immutable`
  exist (0021/0022).
- `SIGKILL` of an `alembic upgrade head` process mid-chain leaves
  `alembic_version = 0012_evidence_revocation`, zero post-base objects
  (e.g. no `runs` table), and zero modified seeded rows. Re-running the
  upgrade to `head` then succeeds — resume is **restart**, not
  continuation.

### Rollback

Do **not** run `alembic downgrade` on a populated install. Downgrade
drops columns and constraint coverage added post-release and can
silently orphan data. Rollback = deploy the previous application
version against the current schema where the expand-phase schema is
still compatible, or restore the latest backup. Destructive downgrade
is never the recovery plan (§26.2).

## 2. Interrupted migrations and backfills

Two interruption modes, both exercised against real processes:

- **Migration kill** — atomic rollback (above). Safe to re-run; never
  partial.
- **Backfill kill** — backfills run as *checkpointed idempotent jobs*
  (`infra/local/resumable_backfill.py`), not inside the migration.
  Each batch commits its emitted digests **and** the checkpoint
  (`ops_backfill_checkpoints.last_key`) in one transaction; a kill
  mid-batch rolls the whole batch back, a kill between batches leaves
  a durable checkpoint. Resume re-reads `id > last_key` and emits with
  `INSERT … ON CONFLICT DO NOTHING` — a re-run can only produce
  missing→present, never duplicate or rewritten digest rows.

```bash
uv run python infra/local/resumable_backfill.py run \
  --dsn postgresql://studio:studio@127.0.0.1:54329/studio \
  [--batch-size 500] [--max-batches N] [--sleep-ms MS]
uv run python infra/local/resumable_backfill.py status --dsn DSN
uv run python infra/local/resumable_backfill.py verify --dsn DSN
```

`verify` recomputes every source row's canonical digest and compares
it to the emitted digest — a source row changed since emit is reported
as `drift: claim <id>` (exit 1), a deleted source as `orphan digest`,
a never-emitted one as `missing digest`. Digests are append-only: the
runner never `UPDATE`s `ops_record_digests`.

## 3. Fresh-machine restore (§21.6)

A restore is only "ready" when it validates *as a system*, not when
postgres accepts connections. Sequence:

```bash
# 1. back up (db.dump + vault tree + manifest.json)
uv run python infra/local/backup.py backup --dsn DSN \
  --vault VAULT_DIR --out BACKUP_DIR

# 2. verify manifest checksums without restoring
uv run python infra/local/backup.py verify --backup BACKUP_DIR

# 3. restore into a CLEAN database + CLEAN vault dir
uv run python infra/local/backup.py restore --backup BACKUP_DIR \
  --dsn NEW_DSN --vault NEW_VAULT_DIR

# 4. integrity validation — enumerates every missing/broken item
uv run python infra/local/recovery_check.py \
  --dsn NEW_DSN --vault NEW_VAULT_DIR [--json]
```

`recovery_check.py` runs twelve checks (all must pass, or the exact
missing items are listed with their ids, exit 1):

| check | fails when |
|---|---|
| `alembic_head` | restored schema version ≠ expected head |
| `required_tables` | a required table is absent (incl. CS-0802 serving/`export_proposals`, and CS-1003 export-broker tables when the head carries them) |
| `artifact_blobs` | a committed artifact's vault blob is missing or its sha256 ≠ `checksum_sha256` |
| `derived_lineage` | a `derived` artifact references a `source_artifact_ids` entry absent from `artifacts` |
| `serving_chain` | a `serving_pointers.release_id` has no release, the release is not servable (`validated`/`promoted`/`superseded`), its adapter/training_run is missing, or a `session_model_pins` row references a missing session/release |
| `training_lineage` | a `training_runs` row's dataset/config/adapter/result artifact is missing |
| `scopes` | a capability grant's principal (or a principal's workspace) is absent |
| `key_material` | no `credential_hash` exists at all, or an `auth_sessions.token_hash` is malformed |
| `approvals` | an approval `bound_digest` is absent/malformed |
| `export_proposals` | a proposal's run or feasibility report is missing, or its `bound_digest` malformed |
| `evidence_refs` | a claim's `source_batch_id`/`source_record_id` or a chunk's `artifact_id` is absent |
| `revocation_tombstones` | a `source_revocations` row's artifact is absent |
| `export_broker` | (when present) `export_jobs.proposal_id` / `export_receipts.job_id` dangling |

Executed on the seeded populated fixture (60 seeded objects, 6 vault
blobs, 64 restored tables):

```text
backup ok: …/backup (alembic=0026_feasibility_fallback, db=220167B, vault_files=6)
verify ok: …/backup (6 vault files)
restore ok: db=… alembic=0026_feasibility_fallback vault_files=6 -> …/vault-dst
  PASS alembic_head (0026_feasibility_fallback)
  … (12 checks) …
recovery_check: ok (0 missing)
```

And sabotage is enumerated exactly — deleting one blob, dropping
`session_model_pins`, corrupting an approval digest yields
`recovery_check: FAILED (3 missing)` listing each item with its id.

> `pg_dump`/`pg_restore` must not be older than the server. The tools
> prefer host binaries only when `client_major >= server_major`;
> otherwise they fall back to `docker exec` into the postgres container
> (compose: `chem-studio-postgres`; override with
> `STUDIO_PGTOOL_CONTAINER`). On this box the host clients are 14.x
> while the server is 16.x — the container fallback is used
> automatically.

## 4. Retention and deletion — what is actually kept

Honest inventory of the core profile. **There are no retention-window
policies configured** (§21.6: "supply configuration and explicit
policy placeholders"); nothing ages out on a timer.

| surface | "deletion" actually does | what backups retain |
|---|---|---|
| source artifact revoked | row stays; `review_state='revoked'`; `source_revocations` tombstone rows record the impact report; chunks leave the retrieval index (index version bump); extracted records → `rejected` with `source_revoked`; claims → `superseded` (still queryable with provenance); derived artifacts → `retention.lineage_review='required'` | **everything** — the blob bytes remain in the vault and in every later backup |
| capability grant revoked | row stays; `revoked_at` set; `load_context` excludes it | full grant history incl. revoked rows |
| auth session ended | `revoked_at` set | sessions + token hashes |
| principal disabled | `disabled_at` set; row stays | credentials + grants |
| approval revoked/expired | `revoked_at` / `expires_at`; row stays | approvals + bound digests |
| upload aborted | `upload_state='aborted'`; staging `.part` file discarded by `discard_staging` | nothing — aborted blobs never committed |
| staged uploads | `stale_staging(ttl)` sweep — the only physical cleanup | staging `.part` files older than TTL are purgeable |
| workspace purge | `delete_workspace_tree` — exists but is **retention-lifecycle only, never called from request paths** | n/a |
| vault blob (`remove_blob`) | API exists, **no request-path callers** | blobs are never deleted by the app |

Implications:

- **Revoke ≠ delete.** Revoked content's bytes stay in the vault and
  propagate into backups until someone runs the workspace-purge
  lifecycle tooling (which currently exists only as
  `delete_workspace_tree`/`remove_blob` primitives with no scheduler).
- A backup taken *after* a revocation still carries the revoked bytes
  and their tombstones — correct: the tombstone/report is evidence,
  and the blob is what the tombstone is about.
- `ops_record_digests` (backfill output) is append-only; its `verify`
  is the detector for any source row rewritten under an existing
  digest.
- If a real deletion policy lands later (e.g. GDPR-style purge),
  `recovery_check` must be extended to treat purged items as
  *expected-absent* rather than missing — today nothing is
  expected-absent.

## 5. Non-destructive posture summary

- Upgrades: single-transaction, expand→migrate→contract; kill-safe;
  resume = restart.
- Backfills: out-of-migration, checkpointed, idempotent, append-only.
- Rollback: compatible roll-forward or restore; never `alembic
  downgrade` on populated data.
- Deletion: soft marks everywhere; no scheduled purge; revoked
  evidence stays recoverable — and visible — in backups.
