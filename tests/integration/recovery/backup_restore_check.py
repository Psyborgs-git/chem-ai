"""AT-0505-1 — backup/restore check against the disposable compose DB.

Seed fixture rows (workspace, principal + capability, project,
artifact row + vault blob), run ``infra/local/backup.py`` into a temp
dir, restore into a **fresh** database on the same server, then verify:

- row references survive (artifact → workspace, capability → principal)
- vault blob sha256 matches the manifest after restore
- permission rows (principal_capabilities) survive intact
- restored schema reports the same alembic head

This checks software recovery only — fixture data, no scientific claim.

Run: ``uv run python tests/integration/recovery/backup_restore_check.py``
(requires compose postgres at 127.0.0.1:54329 — ``make db-up``).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[3]
BACKUP_PY = ROOT / "infra" / "local" / "backup.py"
ADMIN_DSN = "postgresql://studio:studio@127.0.0.1:54329/postgres"
SRC_DB = "studio_backup_src"
DST_DB = "studio_backup_dst"
DSN_TMPL = "postgresql://studio:studio@127.0.0.1:54329/{db}"


def _exec(sql: str, dsn: str = ADMIN_DSN, params: tuple = ()) -> list[tuple]:
    with psycopg.connect(dsn, autocommit=True) as conn:
        cur = conn.execute(sql, params)
        return cur.fetchall() if cur.description else []


def _fresh_db(name: str) -> None:
    _exec(f'DROP DATABASE IF EXISTS "{name}"')
    _exec(f'CREATE DATABASE "{name}"')


def _migrate(dsn: str) -> None:
    env = dict(os.environ, STUDIO_DATABASE_URL=dsn)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ROOT / "services/studio-api/migrations/alembic.ini"),
            "upgrade",
            "head",
        ],
        check=True,
        env=env,
        cwd=ROOT,
        capture_output=True,
    )


def _seed(dsn: str, vault: Path) -> dict[str, str]:
    ids = {k: str(uuid.uuid4()) for k in ("ws", "user", "cap", "proj", "art")}
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO workspaces (id, slug, display_name) VALUES (%s, %s, %s)",
            (ids["ws"], "backup-check", "Backup Check"),
        )
        conn.execute(
            "INSERT INTO principals (id, workspace_id, kind, login, "
            "display_name) VALUES (%s, %s, 'user', %s, %s)",
            (ids["user"], ids["ws"], "backup-check-owner", "Check Owner"),
        )
        conn.execute(
            "INSERT INTO principal_capabilities (id, workspace_id, "
            "principal_id, capability) VALUES (%s, %s, %s, %s)",
            (ids["cap"], ids["ws"], ids["user"], "administer_workspace"),
        )
        conn.execute(
            "INSERT INTO projects (id, workspace_id, slug, name) "
            "VALUES (%s, %s, %s, %s)",
            (ids["proj"], ids["ws"], "backup-proj", "Backup Project"),
        )
        conn.execute(
            "INSERT INTO artifacts (id, workspace_id, storage_key, media_type, "
            "byte_size, checksum_sha256, original_name, upload_state) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, 'committed')",
            (
                ids["art"],
                ids["ws"],
                "ff/" + "f" * 62,
                "text/plain",
                12,
                "f" * 64,
                "fixture.txt",
            ),
        )
    blob = vault / "ff" / ("f" * 62)
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(b"fixture-blob!")
    return ids


def main() -> int:
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
        if not ok:
            failures.append(name)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        vault = tmp / "vault"
        backup_dir = tmp / "backup"
        vault_restore = tmp / "vault-restore"

        print("== seed source db ==")
        _fresh_db(SRC_DB)
        src_dsn = DSN_TMPL.format(db=SRC_DB)
        _migrate(src_dsn)
        ids = _seed(src_dsn, vault)

        print("== backup ==")
        subprocess.run(
            [
                sys.executable,
                str(BACKUP_PY),
                "backup",
                "--dsn",
                src_dsn,
                "--vault",
                str(vault),
                "--out",
                str(backup_dir),
            ],
            check=True,
        )
        subprocess.run(
            [sys.executable, str(BACKUP_PY), "verify", "--backup", str(backup_dir)],
            check=True,
        )

        print("== restore into clean db ==")
        _fresh_db(DST_DB)
        dst_dsn = DSN_TMPL.format(db=DST_DB)
        subprocess.run(
            [
                sys.executable,
                str(BACKUP_PY),
                "restore",
                "--backup",
                str(backup_dir),
                "--dsn",
                dst_dsn,
                "--vault",
                str(vault_restore),
            ],
            check=True,
        )

        print("== AT-0505-1 assertions ==")
        rows = _exec(
            "SELECT storage_key FROM artifacts WHERE id = %s", dst_dsn, (ids["art"],)
        )
        check("artifact row survives", rows == [("ff/" + "f" * 62,)], str(rows))

        rows = _exec(
            "SELECT capability FROM principal_capabilities WHERE principal_id = %s",
            dst_dsn,
            (ids["user"],),
        )
        check("permission row survives", rows == [("administer_workspace",)], str(rows))

        rows = _exec(
            "SELECT slug FROM projects WHERE workspace_id = %s", dst_dsn, (ids["ws"],)
        )
        check("project→workspace reference survives", rows == [("backup-proj",)])

        blob = vault_restore / "ff" / ("f" * 62)
        check(
            "vault blob restored byte-identical",
            blob.exists() and blob.read_bytes() == b"fixture-blob!",
        )

        import hashlib
        import json

        manifest = json.loads((backup_dir / MANIFEST_NAME).read_text())
        blob_hash = hashlib.sha256(blob.read_bytes()).hexdigest()
        expected = {
            f["path"]: f["sha256"] for f in manifest["vault"]["files"]
        }
        check(
            "manifest checksums match restored vault",
            expected.get("ff/" + "f" * 62) == blob_hash,
        )

        head_src = _exec("SELECT version_num FROM alembic_version", src_dsn)
        head_dst = _exec("SELECT version_num FROM alembic_version", dst_dsn)
        check("alembic head preserved", head_src == head_dst, str(head_dst))

        _exec(f'DROP DATABASE IF EXISTS "{SRC_DB}"')
        _exec(f'DROP DATABASE IF EXISTS "{DST_DB}"')

    if failures:
        print(f"backup_restore_check: FAILED ({len(failures)} checks)")
        return 1
    print("backup_restore_check: OK")
    return 0


MANIFEST_NAME = "manifest.json"

if __name__ == "__main__":
    sys.exit(main())
