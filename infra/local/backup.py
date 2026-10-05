"""Local backup / restore for Chemistry Studio (CS-0505, §21.6, §26).

Covers the two real state stores in the core profile:

- PostgreSQL database (via ``pg_dump``/``pg_restore`` custom format).
- The artifact vault tree (sha256-manifested file copy).

There is no separate key store in the core profile — auth material
(token hashes, sessions, capabilities) lives inside the database dump.
If a key store is introduced later it MUST be added here before
recovery readiness can be claimed (§21.6).

Every backup writes ``manifest.json`` (format version, alembic head,
per-component sha256 + byte counts, per-vault-file sha256). Restore
verifies the manifest before writing anything and re-verifies vault
checksums after copying. Restore never overwrites an existing vault
file without ``--force``.

Usage::

    python infra/local/backup.py backup  --dsn postgresql://... --vault DIR --out DIR
    python infra/local/backup.py verify  --backup DIR
    python infra/local/backup.py restore --backup DIR --dsn postgresql://... --vault DIR [--force]

Exit codes: 0 ok, 2 usage/unavailable tool, 1 verification/restore failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

MANIFEST = "manifest.json"
DB_DUMP = "db.dump"
VAULT_DIR = "vault"
FORMAT_VERSION = 1


def _sha256(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    n = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


_CONTAINER = "chem-studio-postgres"


def _pg_tool(name: str) -> list[str]:
    """argv prefix for a postgres client tool.

    Prefers host binaries; falls back to the compose container's tools
    (``docker exec chem-studio-postgres <name>``) so the dev profile
    works without a host postgres install.
    """
    tool = shutil.which(name)
    if tool is not None:
        return [tool]
    if shutil.which("docker") is not None:
        probe = subprocess.run(  # noqa: S603 — fixed argv
            ["docker", "exec", _CONTAINER, "which", name],  # noqa: S607
            capture_output=True,
        )
        if probe.returncode == 0:
            return ["docker", "exec", "-i", _CONTAINER, name]
    raise SystemExit(
        f"BLOCKED: `{name}` unavailable on PATH and in {_CONTAINER}; "
        "install postgresql client tools or start compose postgres"
    )


def _container_dsn(dsn: str) -> str:
    """Rewrite a host DSN for use inside the postgres container."""
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(dsn)
    return urlunsplit(parts._replace(netloc="studio:studio@127.0.0.1:5432"))


def _alembic_head(dsn: str) -> str:
    import psycopg

    try:
        with psycopg.connect(dsn) as conn:
            rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
    except Exception as exc:  # pragma: no cover - diagnostic path
        raise SystemExit(f"FAILED: cannot read alembic_version ({exc})") from exc
    if len(rows) != 1:
        raise SystemExit(f"FAILED: expected 1 alembic_version row, got {len(rows)}")
    return str(rows[0][0])


def _via_container(tool: list[str]) -> bool:
    return tool[0] == "docker"


def cmd_backup(dsn: str, vault: Path, out: Path) -> int:
    pg_dump = _pg_tool("pg_dump")
    out = out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"FAILED: backup dir {out} is not empty (refuse to mix manifests)")
    out.mkdir(parents=True, exist_ok=True)

    head = _alembic_head(dsn)
    dump_path = out / DB_DUMP
    # Stream stdout to the file ourselves so the container fallback
    # (which cannot see host paths) works identically to host tools.
    tool_dsn = _container_dsn(dsn) if _via_container(pg_dump) else dsn
    with dump_path.open("wb") as fh:
        subprocess.run(  # noqa: S603 — pg tool argv, no shell
            [*pg_dump, "--format=custom", "--compress=6", tool_dsn],
            check=True,
            stdout=fh,
        )
    dump_hash, dump_bytes = _sha256(dump_path)

    vault_files: list[dict[str, object]] = []
    vault_out = out / VAULT_DIR
    if vault.exists():
        for src in sorted(p for p in vault.rglob("*") if p.is_file()):
            rel = src.relative_to(vault).as_posix()
            digest, size = _sha256(src)
            dst = vault_out / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            vault_files.append({"path": rel, "sha256": digest, "bytes": size})

    manifest = {
        "format": FORMAT_VERSION,
        "createdAt": datetime.now(UTC).isoformat(),
        "alembicHead": head,
        "db": {"file": DB_DUMP, "sha256": dump_hash, "bytes": dump_bytes},
        "vault": {"fileCount": len(vault_files), "files": vault_files},
        "notes": (
            "fixture/software status only; contains no scientific validation. "
            "Auth material lives inside the db dump (no separate key store "
            "exists in the core profile)."
        ),
    }
    (out / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"backup ok: {out} (alembic={head}, db={dump_bytes}B, vault_files={len(vault_files)})")
    return 0


def _load_manifest(backup: Path) -> dict[str, object]:
    path = backup / MANIFEST
    if not path.exists():
        raise SystemExit(f"FAILED: no manifest at {path}")
    m: dict[str, object] = json.loads(path.read_text())
    if m.get("format") != FORMAT_VERSION:
        raise SystemExit(f"FAILED: unsupported manifest format {m.get('format')}")
    return m


def _entries(m: dict[str, object], key: str) -> list[dict[str, object]]:
    section = m.get(key)
    if not isinstance(section, dict):
        raise SystemExit(f"FAILED: manifest section '{key}' missing")
    files = section.get("files") or []
    if not isinstance(files, list):
        raise SystemExit(f"FAILED: manifest '{key}.files' malformed")
    out: list[dict[str, object]] = []
    for entry in files:
        if not isinstance(entry, dict):
            raise SystemExit(f"FAILED: malformed entry in '{key}.files'")
        out.append(entry)
    return out


def _db_section(m: dict[str, object]) -> dict[str, object]:
    db = m.get("db")
    if not isinstance(db, dict):
        raise SystemExit("FAILED: manifest section 'db' missing")
    return db


def _check_file(path: Path, expected: str, what: str) -> None:
    if not path.exists():
        raise SystemExit(f"FAILED: missing {what}: {path}")
    digest, _ = _sha256(path)
    if digest != expected:
        raise SystemExit(f"FAILED: sha256 mismatch for {what}: {path}")


def cmd_verify(backup: Path) -> int:
    m = _load_manifest(backup)
    db = _db_section(m)
    _check_file(backup / str(db["file"]), str(db["sha256"]), "db dump")
    files = _entries(m, "vault")
    for entry in files:
        _check_file(
            backup / VAULT_DIR / str(entry["path"]),
            str(entry["sha256"]),
            "vault file",
        )
    print(f"verify ok: {backup} ({len(files)} vault files)")
    return 0


def cmd_restore(backup: Path, dsn: str, vault: Path, force: bool) -> int:
    pg_restore = _pg_tool("pg_restore")
    backup = backup.resolve()
    # Verify BEFORE writing anything.
    cmd_verify(backup)
    m = _load_manifest(backup)

    db = _db_section(m)
    tool_dsn = _container_dsn(dsn) if _via_container(pg_restore) else dsn
    # Stream the dump on stdin for the same reason as backup: the
    # container cannot see host paths.
    with (backup / str(db["file"])).open("rb") as fh:
        subprocess.run(  # noqa: S603 — pg tool argv, no shell
            [
                *pg_restore,
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                f"--dbname={tool_dsn}",
            ],
            check=True,
            stdin=fh,
        )

    vault = vault.resolve()
    files = _entries(m, "vault")
    restored = 0
    for entry in files:
        rel = str(entry["path"])
        src = backup / VAULT_DIR / rel
        dst = (vault / rel).resolve()
        if dst != vault and vault not in dst.parents:
            raise SystemExit(f"FAILED: vault path escapes root: {rel}")
        if dst.exists() and not force:
            raise SystemExit(f"FAILED: {dst} exists (use --force to overwrite)")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        _check_file(dst, str(entry["sha256"]), "restored vault file")
        restored += 1
    print(f"restore ok: db={dsn} alembic={m['alembicHead']} vault_files={restored} -> {vault}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("backup", "restore"):
        p = sub.add_parser(name)
        p.add_argument("--dsn", required=True)
        p.add_argument("--vault", type=Path, required=True)
        if name == "backup":
            p.add_argument("--out", type=Path, required=True)
        else:
            p.add_argument("--backup", type=Path, required=True)
            p.add_argument("--force", action="store_true")
    p = sub.add_parser("verify")
    p.add_argument("--backup", type=Path, required=True)
    args = ap.parse_args(argv)

    if args.cmd == "backup":
        return cmd_backup(args.dsn, args.vault, args.out)
    if args.cmd == "verify":
        return cmd_verify(args.backup)
    return cmd_restore(args.backup, args.dsn, args.vault, args.force)


if __name__ == "__main__":
    sys.exit(main())
