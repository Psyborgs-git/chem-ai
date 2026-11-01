# Backup and restore

The supplied tool backs up a PostgreSQL dump and the **entire selected vault
tree**, then records file checksums in a manifest. This is the core backup,
not a complete machine or credential backup. Read the [state inventory](configuration.md)
first so the selected database and vault belong to the same running installation.

## Prepare a consistent snapshot

1. Record the application revision, database destination, active vault root,
   Downloads root, and registered external model locations privately.
2. Cancel or finish learning/simulation work and check its terminal state.
   Pause recurring work and disable the optional background service while doing
   maintenance so it cannot restart a writer.
3. Quit the desktop app and stop foreground API processes. Keep PostgreSQL
   running. Stop other workers that could write the same database or files.
4. Choose an empty backup destination outside the vault and outside any served
   frontend directory. Ensure space for a full dump and vault copy.

`pg_dump` gives a database snapshot, but the tool copies vault files separately;
it does not coordinate a live database/filesystem transaction. Quiescing writes
is required for a consistent database/vault pair.

You need host `pg_dump`/`pg_restore` at least as new as the server, or the running
Compose PostgreSQL container. The tool falls back to container clients when
host clients are missing or older. `STUDIO_PGTOOL_CONTAINER` changes the fallback
container name. Never include credentials in screenshots or shared logs.

## Back up and verify

This example assumes the checkout vault selected during installation. Change
`studio_vault` if the installation uses a different path. Supply the actual DSN
through your normal private shell environment when it differs from development.

```sh
studio_vault="$PWD/.runtime/vault"
studio_backup="/path/to/empty-backup-directory"
uv run python infra/local/backup.py backup   --dsn postgresql://studio:studio@127.0.0.1:54329/studio   --vault "$studio_vault" --out "$studio_backup"
uv run python infra/local/backup.py verify --backup "$studio_backup"
```

Successful backup prints `backup ok` with migration revision and file counts.
Verification prints `verify ok`; missing files, unsupported manifest format, or
SHA-256 mismatch fail. A manifest-valid snapshot of the *wrong* vault is still
an incomplete backup, so compare the path and file counts with the installation.
The output directory must be empty; backups never merge manifests.

## What else to preserve

| Item | Recovery action |
|---|---|
| Provider API keys | Not in dump/vault. Keep access to the provider account and re-enter keys through Providers; do not copy plaintext into documentation or backup manifests. |
| Provider metadata and opaque credential references | Included in DB, but do not recreate Keychain items on another machine. |
| Private learning outputs/checkpoints and catalog models inside the vault | Included by a full vault-tree backup; verify their paths and quiesce jobs. |
| Imported external model directories and worker-host files | Copy separately, preserving versions/checksums and licensing; the database stores paths, not all external model bytes. |
| Human-review Downloads outside the vault | Preserve separately if needed. Protected source originals in `private-library` are included in the vault backup. |
| Optional runtime environments | Record requirement/lockfiles and interpreter overrides; rebuild on recovery. |
| Background/search configuration and incident logs | Preserve privately outside the core snapshot, or recreate deliberately. |

The older tool's “no separate key store in the core profile” comment refers to
password/session/capability data, which is in PostgreSQL. Configured inference
providers additionally use macOS Keychain, which this tool does **not** export.

## Restore into clean destinations

Use an **existing empty target database** and an **empty destination vault**.
The tool does not create the target database, clear it, roll back partial
restores, or provide an atomic database/vault restore. It verifies the manifest
before writes, then restores PostgreSQL before copying vault files. An existing
vault file can therefore cause failure after database changes have begun.
`--force` only permits vault overwrites; it does not make a populated database
safe to restore into.

```sh
studio_backup="/path/to/verified-backup-directory"
studio_restore_vault="/path/to/empty-restored-vault"
uv run python infra/local/backup.py verify --backup "$studio_backup"
uv run python infra/local/backup.py restore   --backup "$studio_backup"   --dsn postgresql://studio:studio@127.0.0.1:54329/studio_restore   --vault "$studio_restore_vault"
```

Create the empty `studio_restore` database first using the database
administrator's normal tooling. Restore the application revision compatible
with the snapshot, point its configuration at the new destinations, and run
[recovery checks](recovery.md) before changing any production/primary binding.
For an upgrade, validate the snapshot at its matching revision, then apply the
new revision's migrations deliberately.

## Validate the recovered system

```sh
uv run python infra/local/recovery_check.py   --dsn postgresql://studio:studio@127.0.0.1:54329/studio_restore   --vault "$studio_restore_vault"
```

Review every reported finding. The checker covers core tables, registered
artifact checksums, lineage, permissions, approvals, and older serving records;
it is not a complete validator for private-library copies, newer learning or
simulation state, external model files, Downloads, or Keychain keys. Reopen a
saved source, notebook, result, learning checkpoint/model, and simulation artifact
that matter to this installation, and confirm expected owner isolation.
Re-enter provider keys, check cleanup state, and test only the chosen connection
before authorizing any research send.

`make backup-test` exercises disposable source/destination databases and fixture
files. It proves the tested backup mechanism, not that your current backup
contains every required state store.

## Failures and privacy

| Symptom | Action |
|---|---|
| `BLOCKED: pg_dump unavailable` | Start the expected Compose container or install a compatible client. |
| SHA-256 mismatch/missing file | Reject this copy; obtain a complete verified snapshot before restoring. |
| Target relation already exists | Stop; create a clean target database and restart restore there. |
| Destination vault file exists | Inspect the target; choose a clean vault rather than casually using `--force`. |
| Provider looks configured but key is missing | Re-enter it in Providers; metadata restoration does not restore Keychain. |
| Model cannot be loaded after restore | Recover its external directory or rebuild the exact registered asset location. |

Backups include private research, credentials hashes, sessions, permissions, and
retained revoked content. The tool provides checksums, not backup encryption or
secure erasure. Protect backup storage and copies using the same controls as the
live machine. See [privacy](privacy.md) for revocation and retention limits.
