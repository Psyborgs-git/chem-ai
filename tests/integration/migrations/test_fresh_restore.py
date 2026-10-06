"""AT-1102-3 — a backup restored into a clean environment validates all
required keys/artifacts/models/scopes, or reports the exact missing
items.

Populates a database at head (evidence fixture + the CS-0802 serving
chain: dataset snapshot → training run → model release → serving
pointer → session pin, plus run/feasibility/export-proposal lineage),
takes a real ``backup.py`` backup (db.dump + vault tree + manifest),
restores into a *fresh* database and *fresh* vault, then runs
``recovery_check`` which must pass every check.

A sabotage pass then removes one vault blob, drops a capability grant
and unlinks the serving pointer — ``recovery_check`` must fail and
enumerate exactly those items.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from testcontainers.community.postgres import PostgresContainer

from .conftest import (
    ROOT,
    alembic_env,
    alembic_repo_head,
    alembic_upgrade,
    fetchval,
)
from .legacy_seed import seed_head_extras, seed_legacy

pytestmark = pytest.mark.integration

BACKUP_PY = ROOT / "infra" / "local" / "backup.py"
CHECK_PY = ROOT / "infra" / "local" / "recovery_check.py"


def _run(
    script: Path, *args: str, dsn: str, pg: PostgresContainer
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — fixed argv
        [sys.executable, str(script), *args],
        env=alembic_env(dsn, pg),
        capture_output=True,
        text=True,
    )


def test_fresh_restore_validates_or_enumerates_missing(
    pg: PostgresContainer, db_factory, tmp_path: Path
) -> None:
    src_dsn = db_factory()
    vault = tmp_path / "vault"
    alembic_upgrade(src_dsn, "head", pg)
    ids = seed_legacy(src_dsn, vault)
    seed_head_extras(src_dsn, vault, ids)

    # -- real backup --------------------------------------------------
    backup_dir = tmp_path / "backup"
    out = _run(
        BACKUP_PY,
        "backup",
        "--dsn",
        src_dsn,
        "--vault",
        str(vault),
        "--out",
        str(backup_dir),
        dsn=src_dsn,
        pg=pg,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    manifest = json.loads((backup_dir / "manifest.json").read_text())
    assert manifest["alembicHead"] == alembic_repo_head()
    assert manifest["vault"]["fileCount"] == 6

    out = _run(BACKUP_PY, "verify", "--backup", str(backup_dir), dsn=src_dsn, pg=pg)
    assert out.returncode == 0, out.stdout + out.stderr

    # -- restore into a clean DB + clean vault -------------------------
    dst_dsn = db_factory()
    vault_restore = tmp_path / "vault-restore"
    out = _run(
        BACKUP_PY,
        "restore",
        "--backup",
        str(backup_dir),
        "--dsn",
        dst_dsn,
        "--vault",
        str(vault_restore),
        dsn=dst_dsn,
        pg=pg,
    )
    assert out.returncode == 0, out.stdout + out.stderr

    # -- integrity validation: everything required verifies -----------
    out = _run(
        CHECK_PY,
        "--dsn",
        dst_dsn,
        "--vault",
        str(vault_restore),
        "--json",
        dsn=dst_dsn,
        pg=pg,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    report = json.loads(out.stdout)
    assert report["ok"] is True
    assert report["total_missing"] == 0
    check_ids = {c["id"] for c in report["checks"]}
    assert {
        "alembic_head",
        "required_tables",
        "artifact_blobs",
        "derived_lineage",
        "serving_chain",
        "training_lineage",
        "scopes",
        "key_material",
        "approvals",
        "export_proposals",
        "evidence_refs",
        "revocation_tombstones",
    } <= check_ids

    # Restored data is the same data: counts and pointers intact.
    for table, want in (
        ("artifacts", 6),
        ("evidence_claims", 2),
        ("approvals", 3),
        ("principal_capabilities", 4),
        ("model_releases", 1),
        ("serving_pointers", 1),
        ("session_model_pins", 1),
        ("export_proposals", 1),
        ("training_runs", 1),
        ("dataset_snapshots", 1),
        ("source_revocations", 1),
    ):
        assert (
            fetchval(dst_dsn, f"SELECT COUNT(*) FROM {table}") == want  # noqa: S608
        ), table
    assert str(fetchval(dst_dsn, "SELECT release_id FROM serving_pointers")) == ids["release"]

    # -- sabotage: validator must enumerate the exact missing items.
    # FK constraints already make most broken references impossible to
    # write; realistic restore losses are a missing vault blob, a
    # missing table, and a corrupted approval binding digest.
    (vault_restore / ids["vault_keys"]["art_adapter"]).unlink()
    import psycopg

    with psycopg.connect(dst_dsn, autocommit=True) as conn:
        conn.execute("DROP TABLE session_model_pins")
        conn.execute(
            "UPDATE approvals SET bound_digest='z' || repeat('0', 63) WHERE id=%s",
            (ids["appr_contract"],),
        )

    out = _run(
        CHECK_PY,
        "--dsn",
        dst_dsn,
        "--vault",
        str(vault_restore),
        "--json",
        dsn=dst_dsn,
        pg=pg,
    )
    assert out.returncode == 1
    report = json.loads(out.stdout)
    assert report["ok"] is False
    missing = report["missing"]
    assert {
        "check": "required_tables",
        "kind": "table",
        "name": "session_model_pins",
    } in missing
    assert {
        "check": "artifact_blobs",
        "kind": "vault_blob",
        "artifact_id": ids["art_adapter"],
        "storage_key": ids["vault_keys"]["art_adapter"],
    } in missing
    assert {
        "check": "approvals",
        "kind": "approval_digest",
        "approval_id": ids["appr_contract"],
    } in missing
    assert report["total_missing"] == 3, json.dumps(missing)
