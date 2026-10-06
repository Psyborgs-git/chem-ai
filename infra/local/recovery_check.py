"""Post-restore integrity validation for Chemistry Studio (CS-1102, §21.6).

``backup.py`` restores bytes; this command proves the restored
*system* is coherent: schema version, required tables, every committed
artifact row resolving to a vault blob whose bytes still hash to the
recorded checksum, derived/source lineage, model-registry serving
chain (release → adapter/result artifacts → serving pointer → session
pins), permission grants and auth material, approval binding digests,
export proposals, dataset/training lineage, and revocation tombstones.

Every check either passes or appends the exact missing/broken item to
the report — a restore is NEVER reported "ok" with silent gaps.

Usage::

    python infra/local/recovery_check.py --dsn DSN --vault DIR [--json]

Exit 0 = all checks pass; 1 = missing/broken items enumerated on
stdout (and stderr); 2 = usage/environment failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import psycopg

ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = ROOT / "services" / "studio-api" / "migrations" / "alembic.ini"

SERVABLE_STATES = ("validated", "promoted", "superseded")

# Required tables — the populated-install surface a backup must carry.
# CS-1003-era tables are added only when the schema head includes them
# (see _required_tables).
CORE_TABLES = [
    "workspaces",
    "principals",
    "principal_capabilities",
    "auth_sessions",
    "projects",
    "research_tasks",
    "success_contract_revisions",
    "task_decisions",
    "artifacts",
    "approvals",
    "import_batches",
    "extracted_records",
    "evidence_claims",
    "claim_links",
    "source_chunks",
    "source_revocations",
    "outbox_events",
    "runs",
    "dataset_snapshots",
    "training_runs",
    "model_releases",
    "serving_pointers",
    "session_model_pins",
    "export_proposals",
]

# Tables required only when the restored head includes the CS-1003
# privacy broker (kept in sync with the migration chain).
CS1003_TABLES = [
    "export_manifests",
    "export_jobs",
    "export_receipts",
    "export_revocations",
]

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _repo_head() -> str:
    out = subprocess.run(  # noqa: S603 — fixed argv
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "heads"],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    ).stdout.strip()
    return out.splitlines()[-1].split(" ")[0].strip()


def _tables(conn: psycopg.Connection) -> set[str]:
    return {
        r[0]
        for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        )
    }


def check(dsn: str, vault: Path, expect_alembic: str | None) -> dict[str, Any]:
    missing: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    def record(check_id: str, items: list[dict[str, Any]], detail: str = "") -> None:
        checks.append({"id": check_id, "ok": not items, "missing": len(items), "detail": detail})
        missing.extend({"check": check_id, **item} for item in items)

    try:
        conn = psycopg.connect(dsn, autocommit=True)
    except psycopg.OperationalError as exc:
        print(f"FAILED: cannot connect ({exc})", file=sys.stderr)
        raise SystemExit(2) from exc

    with conn:
        present = _tables(conn)

        # -- schema version -------------------------------------------
        rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
        items: list[dict[str, Any]] = []
        if len(rows) != 1:
            items.append({"kind": "alembic_version", "rows": len(rows)})
        else:
            head = expect_alembic or _repo_head()
            if rows[0][0] != head:
                items.append({"kind": "alembic_head", "got": rows[0][0], "want": head})
        record("alembic_head", items, str(rows[0][0]) if rows else "none")

        # -- required tables ------------------------------------------
        required = list(CORE_TABLES)
        if any(t in present for t in CS1003_TABLES) or (rows and str(rows[0][0]) >= "0027"):
            required += CS1003_TABLES
        items = [{"kind": "table", "name": t} for t in required if t not in present]
        record("required_tables", items, f"{len(present)} present")

        def q(sql: str, params: tuple = ()) -> list[tuple]:
            return conn.execute(sql, params).fetchall()

        # -- vault blobs for every committed artifact -----------------
        items = []
        if "artifacts" in present:
            for aid, key, checksum in q(
                "SELECT id, storage_key, checksum_sha256 FROM artifacts "
                "WHERE upload_state='committed' AND checksum_sha256 IS NOT NULL"
            ):
                blob = vault / key
                if not blob.exists():
                    items.append(
                        {"kind": "vault_blob", "artifact_id": str(aid), "storage_key": key}
                    )
                elif _sha256(blob) != checksum:
                    items.append(
                        {"kind": "vault_blob_checksum", "artifact_id": str(aid), "storage_key": key}
                    )
        record("artifact_blobs", items)

        # -- derived-artifact lineage ---------------------------------
        items = []
        if "artifacts" in present:
            for aid, src_ids in q(
                "SELECT id, source_artifact_ids FROM artifacts WHERE source_kind='derived'"
            ):
                for src in src_ids or []:
                    found = q("SELECT 1 FROM artifacts WHERE id=%s", (src,))
                    if not found:
                        items.append(
                            {
                                "kind": "source_artifact",
                                "artifact_id": str(aid),
                                "missing_source": str(src),
                            }
                        )
        record("derived_lineage", items)

        # -- model serving chain ---------------------------------------
        items = []
        if "serving_pointers" in present and "model_releases" in present:
            for pid, rid in q("SELECT id, release_id FROM serving_pointers"):
                if rid is None:
                    continue
                rel = q(
                    "SELECT state, adapter_artifact_id, "
                    "training_run_id FROM model_releases WHERE id=%s",
                    (rid,),
                )
                if not rel:
                    items.append(
                        {
                            "kind": "serving_pointer_release",
                            "pointer_id": str(pid),
                            "release_id": str(rid),
                        }
                    )
                    continue
                state, adapter_art, run_id = rel[0]
                if state not in SERVABLE_STATES:
                    items.append({"kind": "serving_state", "release_id": str(rid), "state": state})
                if adapter_art and not q("SELECT 1 FROM artifacts WHERE id=%s", (adapter_art,)):
                    items.append(
                        {
                            "kind": "adapter_artifact",
                            "release_id": str(rid),
                            "artifact_id": str(adapter_art),
                        }
                    )
                if run_id and not q("SELECT 1 FROM training_runs WHERE id=%s", (run_id,)):
                    items.append(
                        {
                            "kind": "training_run",
                            "release_id": str(rid),
                            "training_run_id": str(run_id),
                        }
                    )
        if "session_model_pins" in present:
            for pin_id, sess, rid in q("SELECT id, session_id, release_id FROM session_model_pins"):
                if not q("SELECT 1 FROM research_sessions WHERE id=%s", (sess,)):
                    items.append(
                        {"kind": "pin_session", "pin_id": str(pin_id), "session_id": str(sess)}
                    )
                if rid and not q("SELECT 1 FROM model_releases WHERE id=%s", (rid,)):
                    items.append(
                        {"kind": "pin_release", "pin_id": str(pin_id), "release_id": str(rid)}
                    )
        record("serving_chain", items)

        # -- training lineage artifacts --------------------------------
        items = []
        if "training_runs" in present:
            for row in q(
                "SELECT id, dataset_artifact_id, config_artifact_id, "
                "adapter_artifact_id, result_artifact_id FROM training_runs"
            ):
                tid, cols = row[0], row[1:]
                for label, art in zip(
                    ("dataset", "config", "adapter", "result"), cols, strict=True
                ):
                    if art and not q("SELECT 1 FROM artifacts WHERE id=%s", (art,)):
                        items.append(
                            {
                                "kind": f"training_{label}_artifact",
                                "training_run_id": str(tid),
                                "artifact_id": str(art),
                            }
                        )
        record("training_lineage", items)

        # -- scopes: capability grants resolve to live principals ------
        items = []
        grants = 0
        if "principal_capabilities" in present:
            for cid, pid in q("SELECT id, principal_id FROM principal_capabilities"):
                grants += 1
                if not q("SELECT 1 FROM principals WHERE id=%s", (pid,)):
                    items.append(
                        {
                            "kind": "capability_principal",
                            "capability_id": str(cid),
                            "principal_id": str(pid),
                        }
                    )
            for pid, wid in q("SELECT id, workspace_id FROM principals"):
                if not q("SELECT 1 FROM workspaces WHERE id=%s", (wid,)):
                    items.append(
                        {
                            "kind": "principal_workspace",
                            "principal_id": str(pid),
                            "workspace_id": str(wid),
                        }
                    )
        record("scopes", items, f"{grants} grants")

        # -- key material (auth lives in the DB) -----------------------
        items = []
        if "principals" in present:
            cred = q("SELECT COUNT(*) FROM principals WHERE credential_hash IS NOT NULL")[0][0]
            if cred == 0:
                items.append({"kind": "credential_material", "count": 0})
        if "auth_sessions" in present:
            for sid, th in q("SELECT id, token_hash FROM auth_sessions"):
                if not th or not _HEX64.match(th):
                    items.append({"kind": "session_token_hash", "session_id": str(sid)})
        record("key_material", items)

        # -- approval binding digests ----------------------------------
        items = []
        if "approvals" in present:
            for aid, digest in q("SELECT id, bound_digest FROM approvals"):
                if not digest or not _HEX64.match(digest):
                    items.append({"kind": "approval_digest", "approval_id": str(aid)})
        record("approvals", items)

        # -- export proposals (pre-CS-1003 surface) --------------------
        items = []
        if "export_proposals" in present:
            for eid, run_id, report_id, digest in q(
                "SELECT id, run_id, feasibility_report_id, bound_digest FROM export_proposals"
            ):
                if not q("SELECT 1 FROM runs WHERE id=%s", (run_id,)):
                    items.append(
                        {"kind": "proposal_run", "proposal_id": str(eid), "run_id": str(run_id)}
                    )
                if not q(
                    "SELECT 1 FROM run_feasibility_reports WHERE id=%s",
                    (report_id,),
                ):
                    items.append(
                        {
                            "kind": "proposal_report",
                            "proposal_id": str(eid),
                            "report_id": str(report_id),
                        }
                    )
                if not digest or not _HEX64.match(digest):
                    items.append({"kind": "proposal_digest", "proposal_id": str(eid)})
        record("export_proposals", items)

        # -- evidence references ----------------------------------------
        items = []
        if "evidence_claims" in present:
            for cid, batch, rec in q(
                "SELECT id, source_batch_id, source_record_id FROM evidence_claims"
            ):
                if batch and not q("SELECT 1 FROM import_batches WHERE id=%s", (batch,)):
                    items.append(
                        {"kind": "claim_batch", "claim_id": str(cid), "batch_id": str(batch)}
                    )
                if rec and not q("SELECT 1 FROM extracted_records WHERE id=%s", (rec,)):
                    items.append(
                        {"kind": "claim_record", "claim_id": str(cid), "record_id": str(rec)}
                    )
        if "source_chunks" in present:
            for sid, art in q("SELECT id, artifact_id FROM source_chunks"):
                if not q("SELECT 1 FROM artifacts WHERE id=%s", (art,)):
                    items.append(
                        {"kind": "chunk_artifact", "chunk_id": str(sid), "artifact_id": str(art)}
                    )
        record("evidence_refs", items)

        # -- revocation tombstones retained -----------------------------
        items = []
        if "source_revocations" in present:
            for rid, art in q("SELECT id, artifact_id FROM source_revocations"):
                if not q("SELECT 1 FROM artifacts WHERE id=%s", (art,)):
                    items.append(
                        {
                            "kind": "revocation_artifact",
                            "revocation_id": str(rid),
                            "artifact_id": str(art),
                        }
                    )
        record("revocation_tombstones", items)

        # -- CS-1003 export broker surface (when the schema has it) -----
        items = []
        if "export_jobs" in present:
            for jid, proposal in q("SELECT id, proposal_id FROM export_jobs"):
                if "export_proposals" in present and not q(
                    "SELECT 1 FROM export_proposals WHERE id=%s", (proposal,)
                ):
                    items.append(
                        {
                            "kind": "export_job_proposal",
                            "job_id": str(jid),
                            "proposal_id": str(proposal),
                        }
                    )
        if "export_receipts" in present:
            for rid, job in q("SELECT id, job_id FROM export_receipts"):
                if "export_jobs" in present and not q(
                    "SELECT 1 FROM export_jobs WHERE id=%s", (job,)
                ):
                    items.append(
                        {"kind": "receipt_job", "receipt_id": str(rid), "job_id": str(job)}
                    )
        record("export_broker", items)

    conn.close()
    return {
        "ok": not missing,
        "checks": checks,
        "missing": missing,
        "total_missing": len(missing),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--vault", type=Path, required=True)
    ap.add_argument("--expect-alembic", default=None)
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    report = check(args.dsn, args.vault, args.expect_alembic)

    if args.as_json:
        print(json.dumps(report, indent=2, default=str))
    else:
        for c in report["checks"]:
            mark = "PASS" if c["ok"] else "FAIL"
            detail = f" ({c['detail']})" if c.get("detail") else ""
            print(f"  {mark} {c['id']}{detail}")
        if report["missing"]:
            print("missing items:")
            for m in report["missing"]:
                print(f"  - {json.dumps(m, default=str)}")
        print(
            f"recovery_check: {'ok' if report['ok'] else 'FAILED'} "
            f"({report['total_missing']} missing)"
        )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
