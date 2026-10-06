"""Resumable, checkpointed evidence-digest backfill (CS-1102, §26.2).

The migration contract requires backfills to be *resumable idempotent
jobs with checkpoints* and to never rewrite an accepted record. This
runner is the canonical local implementation: it walks
``evidence_claims`` (the scientific record surface) in PK order,
computes a sha256 over each row's canonical content, and appends the
digest to ``ops_record_digests`` — an append-only ops table. Emitted
digests are never updated or deleted here: a source row that changed
since its digest was written is *drift*, reported by ``verify``.

Checkpointing is transactional: each batch commits its digest rows and
the checkpoint (``ops_backfill_checkpoints.last_key``) in one commit,
so a kill between batches leaves a consistent resumable state and a
kill mid-batch rolls the whole batch back — resume reprocesses that
batch idempotently (``ON CONFLICT DO NOTHING``).

Usage::

    python infra/local/resumable_backfill.py run --dsn DSN \
        [--batch-size 500] [--max-batches N] [--sleep-ms MS]
    python infra/local/resumable_backfill.py verify --dsn DSN
    python infra/local/resumable_backfill.py status --dsn DSN

Exit codes: ``run`` — 0 done, 3 interrupted (--max-batches reached or
SIGTERM/SIGINT mid-run); ``verify`` — 0 clean, 1 drift/missing; other
errors 1. ``status`` prints checkpoint state and exits 0.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import signal
import sys
import time
from typing import Any

import psycopg

JOB = "evidence-digests-v1"

DDL = (
    """
    CREATE TABLE IF NOT EXISTS ops_backfill_checkpoints (
        job         text PRIMARY KEY,
        last_key    uuid,
        rows_done   bigint NOT NULL DEFAULT 0,
        updated_at  timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ops_record_digests (
        entity_table  text NOT NULL,
        entity_id     uuid NOT NULL,
        workspace_id  uuid NOT NULL,
        digest        char(64) NOT NULL,
        computed_at   timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (entity_table, entity_id)
    )
    """,
)

# Canonical field set per source row — the digest input. Keys are the
# record's identity-bearing, scientific content; volatile bookkeeping
# (updated_at) is excluded on purpose.
_CLAIM_FIELDS = (
    "id",
    "workspace_id",
    "kind",
    "status",
    "subject",
    "statement",
    "locator",
    "original_text",
    "conditions",
    "source_batch_id",
    "source_record_id",
    "reviewed_by",
)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest_row(row: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(row).encode("utf-8")).hexdigest()


def _ensure_tables(conn: psycopg.Connection) -> None:
    for stmt in DDL:
        conn.execute(stmt)


class _Interrupted(Exception):
    pass


def _install_signal_handlers() -> None:
    def _raise(_sig: int, _frame: object) -> None:
        raise _Interrupted

    signal.signal(signal.SIGTERM, _raise)
    signal.signal(signal.SIGINT, _raise)


def cmd_run(dsn: str, batch_size: int, max_batches: int | None, sleep_ms: int) -> int:
    _install_signal_handlers()
    try:
        with psycopg.connect(dsn, autocommit=False) as conn:
            _ensure_tables(conn)
            conn.execute(
                "INSERT INTO ops_backfill_checkpoints (job) "
                "VALUES (%s) ON CONFLICT (job) DO NOTHING",
                (JOB,),
            )
            conn.commit()

            batches = 0
            while True:
                if max_batches is not None and batches >= max_batches:
                    print(
                        f"interrupted: stop after {batches} committed batch(es)",
                        flush=True,
                    )
                    return 3
                if sleep_ms and batches:
                    # A kill lands here: between committed batches —
                    # the checkpoint is already durable.
                    time.sleep(sleep_ms / 1000.0)

                with conn.transaction():
                    last_key = conn.execute(
                        "SELECT last_key FROM ops_backfill_checkpoints WHERE job = %s FOR UPDATE",
                        (JOB,),
                    ).fetchone()[0]
                    fields = ", ".join(_CLAIM_FIELDS)
                    if last_key is None:
                        rows = conn.execute(
                            f"SELECT {fields} FROM evidence_claims "  # noqa: S608
                            "ORDER BY id LIMIT %s",
                            (batch_size,),
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            f"SELECT {fields} FROM evidence_claims "  # noqa: S608
                            "WHERE id > %s ORDER BY id LIMIT %s",
                            (last_key, batch_size),
                        ).fetchall()
                    if not rows:
                        conn.execute(
                            "UPDATE ops_backfill_checkpoints SET updated_at=now() WHERE job=%s",
                            (JOB,),
                        )
                        total = conn.execute(
                            "SELECT rows_done FROM ops_backfill_checkpoints WHERE job=%s",
                            (JOB,),
                        ).fetchone()[0]
                        print(f"done: {JOB} rows_done={total}", flush=True)
                        return 0

                    emitted = 0
                    new_last = last_key
                    for raw in rows:
                        record = dict(zip(_CLAIM_FIELDS, raw, strict=True))
                        digest = _digest_row(record)
                        cur = conn.execute(
                            "INSERT INTO ops_record_digests (entity_table, "
                            "entity_id, workspace_id, digest) "
                            "VALUES ('evidence_claims', %s, %s, %s) "
                            "ON CONFLICT (entity_table, entity_id) "
                            "DO NOTHING",
                            (record["id"], record["workspace_id"], digest),
                        )
                        emitted += cur.rowcount
                        new_last = record["id"]
                    conn.execute(
                        "UPDATE ops_backfill_checkpoints SET last_key=%s, "
                        "rows_done=rows_done+%s, updated_at=now() "
                        "WHERE job=%s",
                        (new_last, emitted, JOB),
                    )
                batches += 1
                print(
                    f"batch {batches}: +{emitted} digest rows (last_key={new_last})",
                    flush=True,
                )
    except _Interrupted:
        print("interrupted: signal received; checkpoint durable", flush=True)
        return 3
    except psycopg.OperationalError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


def cmd_verify(dsn: str) -> int:
    """Recompute every source row and every emitted digest; report
    missing, drifted (source rewritten since emit), and orphan digest
    rows. This is the no-silent-rewrite detector."""
    fields = ", ".join(_CLAIM_FIELDS)
    with psycopg.connect(dsn, autocommit=True) as conn:
        sources = {
            str(r[0]): dict(zip(_CLAIM_FIELDS, r, strict=True))
            for r in conn.execute(
                f"SELECT {fields} FROM evidence_claims"  # noqa: S608
            ).fetchall()
        }
        emitted = conn.execute(
            "SELECT entity_id, digest FROM ops_record_digests WHERE entity_table='evidence_claims'"
        ).fetchall()

    problems: list[str] = []
    emitted_ids = set()
    for entity_id, digest in emitted:
        eid = str(entity_id)
        emitted_ids.add(eid)
        src = sources.get(eid)
        if src is None:
            problems.append(f"orphan digest for deleted claim {eid}")
            continue
        if _digest_row(src) != digest:
            problems.append(f"drift: claim {eid} content changed since emit")
    for eid in sources:
        if eid not in emitted_ids:
            problems.append(f"missing digest for claim {eid}")

    if problems:
        for p in problems:
            print(f"FAIL {p}")
        print(f"verify: FAILED ({len(problems)} problems)")
        return 1
    print(f"verify: ok ({len(sources)} claims digested)")
    return 0


def cmd_status(dsn: str) -> int:
    with psycopg.connect(dsn, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name='ops_backfill_checkpoints')"
        ).fetchone()[0]
        if not exists:
            print("status: no checkpoint table (job never ran)")
            return 0
        row = conn.execute(
            "SELECT last_key, rows_done, updated_at FROM ops_backfill_checkpoints WHERE job=%s",
            (JOB,),
        ).fetchone()
        if row is None:
            print("status: job never ran")
            return 0
        pending = conn.execute(
            "SELECT COUNT(*) FROM evidence_claims " + ("WHERE id > %s" if row[0] else ""),  # noqa: S608
            (row[0],) if row[0] else (),
        ).fetchone()[0]
        print(f"status: last_key={row[0]} rows_done={row[1]} updated_at={row[2]} pending={pending}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "verify", "status"):
        p = sub.add_parser(name)
        p.add_argument("--dsn", required=True)
        if name == "run":
            p.add_argument("--batch-size", type=int, default=500)
            p.add_argument("--max-batches", type=int, default=None)
            p.add_argument("--sleep-ms", type=int, default=0)
    args = ap.parse_args(argv)

    if args.cmd == "run":
        return cmd_run(args.dsn, args.batch_size, args.max_batches, args.sleep_ms)
    if args.cmd == "verify":
        return cmd_verify(args.dsn)
    return cmd_status(args.dsn)


if __name__ == "__main__":
    sys.exit(main())
