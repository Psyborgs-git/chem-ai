"""AT-1102-2 — an interrupted migration/backfill resumes without
duplicate or silently rewritten scientific records.

Two exercises:

* ``test_migration_kill_leaves_atomic_state`` — SIGKILLs an in-flight
  ``alembic upgrade head`` on a populated LEGACY_BASE_REV database. The
  upgrade runs inside one transaction (env.py wraps run_migrations in
  ``context.begin_transaction``), so the kill must leave the database
  exactly at the base revision — same version row, no partial objects,
  no touched data. Re-running to head then succeeds and preserves the
  fixture (no resume-doubling).

* ``test_backfill_kill_resume_no_duplicates`` — runs the checkpointed
  ``infra/local/resumable_backfill.py`` job over seeded
  evidence_claims, SIGKILLs it between committed batches, resumes to
  completion, and asserts: digest-row count equals claim count, no
  duplicate digests, every digest recomputes against the live source
  (``verify``), a full re-run is a no-op, and a post-hoc source edit is
  reported as drift rather than absorbed silently.
"""

from __future__ import annotations

import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from testcontainers.community.postgres import PostgresContainer

from .conftest import (
    LEGACY_BASE_REV,
    ROOT,
    alembic_env,
    alembic_repo_head,
    alembic_upgrade,
    alembic_version,
    fetchall,
    fetchval,
    table_exists,
)
from .legacy_seed import (
    LEGACY_TABLES,
    compare_snapshots,
    pre_columns,
    seed_legacy,
    snapshot,
)

pytestmark = pytest.mark.integration

BACKFILL = ROOT / "infra" / "local" / "resumable_backfill.py"


def _backfill(dsn: str, pg: PostgresContainer, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(  # noqa: S603 — fixed argv
        [sys.executable, str(BACKFILL), *args, "--dsn", dsn],
        env=alembic_env(dsn, pg),
        capture_output=True,
        text=True,
    )


def _seed_extra_claims(dsn: str, ids: dict[str, str], n: int) -> list[str]:
    """Add n more proposed claims so the backfill spans many batches."""
    import psycopg

    new_ids = []
    with psycopg.connect(dsn, autocommit=True) as conn:
        for i in range(n):
            cid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"extra-claim-{i}-{ids['ws']}"))
            conn.execute(
                "INSERT INTO evidence_claims (id, workspace_id, kind, "
                "status, subject, statement, created_by) "
                "VALUES (%s,%s,'inferred_suggestion','proposed',%s,%s,%s)",
                (
                    cid,
                    ids["ws"],
                    f'{{"entity":"extra-{i}"}}',
                    f'{{"predicate":"fixture","value":{i}}}',
                    ids["agent"],
                ),
            )
            new_ids.append(cid)
    return new_ids


def test_migration_kill_leaves_atomic_state(
    pg: PostgresContainer, db_factory, tmp_path: Path
) -> None:
    dsn = db_factory()
    alembic_upgrade(dsn, LEGACY_BASE_REV, pg)
    seed_legacy(dsn, tmp_path / "vault")
    pre = snapshot(dsn, LEGACY_TABLES)
    cols = pre_columns(pre)

    proc = subprocess.Popen(  # noqa: S603 — fixed argv
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ROOT / "services/studio-api/migrations/alembic.ini"),
            "upgrade",
            "head",
        ],
        env=alembic_env(dsn, pg),
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Kill the upgrade while it is almost certainly mid-transaction.
    time.sleep(0.15)
    proc.send_signal(signal.SIGKILL)
    proc.wait(timeout=30)
    assert proc.returncode != 0

    # The interrupted upgrade committed nothing: version is the base
    # rev and no post-base object (runs) exists.
    assert alembic_version(dsn) == LEGACY_BASE_REV
    assert not table_exists(dsn, "runs")

    # Seeded rows untouched by the killed upgrade.
    mid = snapshot(dsn, LEGACY_TABLES, columns=cols)
    assert compare_snapshots(pre, mid) == []

    # Re-run to completion; the fixture still verifies end-to-end.
    alembic_upgrade(dsn, "head", pg)
    assert alembic_version(dsn) == alembic_repo_head()
    post = snapshot(dsn, LEGACY_TABLES, columns=cols)
    assert compare_snapshots(pre, post) == []
    assert table_exists(dsn, "runs")
    assert table_exists(dsn, "serving_pointers")


def test_backfill_kill_resume_no_duplicates(
    pg: PostgresContainer, db_factory, tmp_path: Path
) -> None:
    dsn = db_factory()
    alembic_upgrade(dsn, "head", pg)
    ids = seed_legacy(dsn, tmp_path / "vault")
    claim_ids = _seed_extra_claims(dsn, ids, 23)  # +2 seeded = 25 claims
    total = fetchval(dsn, "SELECT COUNT(*) FROM evidence_claims")
    assert total == 25

    # Deterministic interrupt: commit exactly one batch then stop.
    with subprocess.Popen(  # noqa: S603 — fixed argv
        [
            sys.executable,
            str(BACKFILL),
            "run",
            "--dsn",
            dsn,
            "--batch-size",
            "8",
            "--sleep-ms",
            "4000",
        ],
        env=alembic_env(dsn, pg),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    ) as proc:
        assert proc.stdout is not None
        # Wait for the first committed batch, then SIGKILL — the kill
        # lands inside the inter-batch sleep, after batch 1 committed.
        first = proc.stdout.readline()
        assert "batch 1" in first, first
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=30)
        assert proc.returncode == -signal.SIGKILL

    done = fetchval(
        dsn,
        "SELECT rows_done FROM ops_backfill_checkpoints WHERE job='evidence-digests-v1'",
    )
    assert done == 8
    assert fetchval(dsn, "SELECT COUNT(*) FROM ops_record_digests") == 8

    # Resume to completion.
    out = _backfill(dsn, pg, "run", "--batch-size", "8")
    assert out.returncode == 0, out.stdout + out.stderr
    assert "done:" in out.stdout

    # Exactly one digest per claim — no duplicates possible (PK) and
    # none observed.
    rows = fetchall(
        dsn,
        "SELECT entity_id, digest FROM ops_record_digests WHERE entity_table='evidence_claims'",
    )
    assert len(rows) == total
    assert len({str(r[0]) for r in rows}) == total
    digested = {str(r[0]) for r in rows}
    assert set(claim_ids) <= digested

    # Every digest still recomputes from the live source — nothing was
    # silently rewritten while resuming.
    out = _backfill(dsn, pg, "verify")
    assert out.returncode == 0, out.stdout + out.stderr

    # A full re-run is a no-op (idempotent resume posture).
    out = _backfill(dsn, pg, "run", "--batch-size", "8")
    assert out.returncode == 0 and "rows_done=25" in out.stdout
    assert fetchval(dsn, "SELECT COUNT(*) FROM ops_record_digests") == 25

    # Silent rewrites are detected, not absorbed: edit a source row and
    # verify must flag drift for exactly that claim.
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(
            'UPDATE evidence_claims SET statement=\'{"predicate":"tampered"}\'::jsonb WHERE id=%s',
            (claim_ids[0],),
        )
    out = _backfill(dsn, pg, "verify")
    assert out.returncode == 1
    assert claim_ids[0] in out.stdout
    assert "drift" in out.stdout
