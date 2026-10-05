# Runbook — local backup, restore, and privacy checks (CS-0505)

Covers the core profile's two state stores: the PostgreSQL database
and the artifact vault. Auth material (sessions, token hashes,
capabilities) lives **inside** the DB dump — there is no separate key
store in the core profile. If one is added, extend
`infra/local/backup.py` before claiming recovery readiness (§21.6).

## Prerequisites

- `pg_dump`/`pg_restore` on PATH **or** the compose postgres container
  running (the tools inside `chem-studio-postgres` are used as a
  fallback automatically).
- `make db-up` for the dev database.
- Enough disk for the dump + a full copy of the vault.

## Backup

```bash
uv run python infra/local/backup.py backup \
  --dsn postgresql://studio:studio@127.0.0.1:54329/studio \
  --vault "$HOME/.local/share/chemistry-studio/vault" \
  --out /path/to/backup-dir
```

Expected output: `backup ok: <dir> (alembic=<rev>, db=<n>B, vault_files=<n>)`.

The output dir must be empty — backups never mix manifests.

## Verify a backup without restoring

```bash
uv run python infra/local/backup.py verify --backup /path/to/backup-dir
```

Expected: `verify ok: <dir> (<n> vault files)`. Any sha256 mismatch,
missing file, or unsupported manifest format exits 1 and prints `FAILED:`.

## Restore

```bash
# target DB must already exist (createdb or compose)
uv run python infra/local/backup.py restore \
  --backup /path/to/backup-dir \
  --dsn postgresql://studio:studio@127.0.0.1:54329/studio \
  --vault "$HOME/.local/share/chemistry-studio/vault"
```

Expected: `restore ok: db=<dsn> alembic=<rev> vault_files=<n> -> <vault>`.

- The manifest is verified **before** anything is written.
- Vault files are re-hashed after copy; a checksum mismatch aborts.
- Existing vault files are never overwritten without `--force`.

## Automated check (AT-0505-1)

```bash
make backup-test
```

Seeds fixture rows + a vault blob into a disposable DB
(`studio_backup_src`), backs up, restores into `studio_backup_dst`,
and asserts: row references survive, permission rows survive, the
restored blob is byte-identical, manifest checksums match, and the
alembic head is preserved. Prints `backup_restore_check: OK`.

## Privacy check (AT-0505-2)

```bash
uv run python tests/integration/recovery/no_egress_check.py
```

Static-scans `services/studio-api/src` for outbound-capable client
imports and runs an in-process app under a loopback-only socket guard.
Expected: `no_egress_check: OK`.

## Pilot gate report (AT-0505-3)

```bash
uv run python infra/local/pilot_gate.py
```

Regenerates `docs/operations/pilot-gate.md` — the live/fixture/blocked
capability matrix with scientific status kept explicitly separate.

## Failure symptoms and recovery

| Symptom | Cause | Recovery |
|---|---|---|
| `BLOCKED: pg_dump unavailable…` | no host tools, container down | install `postgresql` client or `make db-up` |
| `FAILED: sha256 mismatch` | corrupt/partial backup copy | re-copy the backup dir; never restore a mismatched manifest |
| `FAILED: <vault path> exists` | vault already populated | inspect first; use `--force` only intentionally |
| `pg_restore` errors on extensions/owners | restored as non-superuser | dump/restore run with `--no-owner --no-privileges`; remaining errors are real — report them |

## Privacy concerns

- Backups contain **all** workspace data including token hashes —
  store them with the same protections as the vault (§21.3).
- Backup encryption/key recovery is not implemented; encrypt the
  backup dir at rest via OS volume encryption before claiming
  recovery readiness for sensitive deployments.
- Secure erasure of SSD/cloud copies is not promised (§21.6).
