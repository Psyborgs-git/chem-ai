"""AT-1102-1 — populated previous schema + immutable evidence survives
the full alembic upgrade chain (references, hashes, permissions).

Builds a disposable database at ``LEGACY_BASE_REV``, seeds the
immutable-evidence fixture (revisions, claims, artifact checksums,
approval grants, capabilities incl. a revoked one, auth sessions,
outbox events, revocation tombstone), snapshots every row, then runs
``alembic upgrade head`` and asserts:

- every pre-upgrade row still digests identically on its old columns
  (no silent rewrite by any expand/migrate/contract step);
- stored hashes still verify (revision content_hash, approval
  bound_digest, artifact checksum vs vault bytes);
- every seeded reference still resolves through composite FKs;
- permissions remain *valid* (load_context authorizes scoped grants,
  revoked grant stays excluded);
- the chain's populated-data effects landed (outbox seq backfill,
  uq_approvals_scope_id contract step, immutability triggers);
- alembic_version sits at repo head.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.community.postgres import PostgresContainer

from studio.auth.context import load_context
from studio.persistence.revisions import content_hash

from .conftest import (
    LEGACY_BASE_REV,
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


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_populated_upgrade_preserves_evidence(
    pg: PostgresContainer, db_factory, tmp_path: Path
) -> None:
    dsn = db_factory()
    vault = tmp_path / "vault"

    # 1. Sit at the previous schema and populate it.
    alembic_upgrade(dsn, LEGACY_BASE_REV, pg)
    assert alembic_version(dsn) == LEGACY_BASE_REV
    ids = seed_legacy(dsn, vault)
    pre = snapshot(dsn, LEGACY_TABLES)
    cols = pre_columns(pre)

    # 2. Upgrade through the whole chain.
    alembic_upgrade(dsn, "head", pg)
    assert alembic_version(dsn) == alembic_repo_head()

    # 3. No seeded row was dropped or silently rewritten.
    post = snapshot(dsn, LEGACY_TABLES, columns=cols)
    mismatches = compare_snapshots(pre, post)
    assert mismatches == [], f"upgrade rewrote rows: {mismatches}"

    # 4. Stored hashes still verify against stored payloads/blobs.
    rows = fetchall(
        dsn,
        "SELECT id, content_hash, payload FROM success_contract_revisions ORDER BY revision",
    )
    assert len(rows) == 2
    for _, ch, payload in rows:
        assert content_hash(payload) == ch
    for table in (
        "formulation_revisions",
        "process_revisions",
        "candidate_revisions",
    ):
        for _, ch, payload in fetchall(
            dsn,
            f"SELECT id, content_hash, payload FROM {table}",  # noqa: S608
        ):
            assert content_hash(payload) == ch, table
    for aid, digest, inputs in fetchall(
        dsn, "SELECT id, bound_digest, bound_inputs FROM approvals"
    ):
        assert content_hash(inputs) == digest, f"approval {aid}"

    # Artifact checksums still match vault bytes byte-for-byte.
    for aid, key, checksum in fetchall(
        dsn,
        "SELECT id, storage_key, checksum_sha256 FROM artifacts WHERE upload_state='committed'",
    ):
        blob = vault / key
        assert blob.exists(), f"vault blob missing for artifact {aid}"
        assert _sha256(blob.read_bytes()) == checksum

    # 5. References still resolve through the upgraded schema.
    asserts = {
        "claim->batch": (
            "SELECT COUNT(*) FROM evidence_claims c JOIN import_batches b "
            "ON c.source_batch_id=b.id AND c.workspace_id=b.workspace_id "
            "WHERE c.id=%s",
            ids["claim1"],
            1,
        ),
        "claim->record": (
            "SELECT COUNT(*) FROM evidence_claims c JOIN extracted_records r "
            "ON c.source_record_id=r.id AND c.workspace_id=r.workspace_id "
            "WHERE c.id=%s",
            ids["claim1"],
            1,
        ),
        "link->claims": (
            "SELECT COUNT(*) FROM claim_links l JOIN evidence_claims f "
            "ON l.from_claim_id=f.id AND l.workspace_id=f.workspace_id "
            "JOIN evidence_claims t ON l.to_claim_id=t.id "
            "AND l.workspace_id=t.workspace_id WHERE l.id=%s",
            ids["link"],
            1,
        ),
        "chunk->artifact": (
            "SELECT COUNT(*) FROM source_chunks s JOIN artifacts a "
            "ON s.artifact_id=a.id AND s.workspace_id=a.workspace_id "
            "WHERE s.id=%s",
            ids["chunk1"],
            1,
        ),
        "decision->task+decider": (
            "SELECT COUNT(*) FROM task_decisions d JOIN research_tasks t "
            "ON d.task_id=t.id AND d.workspace_id=t.workspace_id "
            "JOIN principals p ON d.decided_by=p.id "
            "AND d.workspace_id=p.workspace_id WHERE d.id=%s",
            ids["decision"],
            1,
        ),
        "capability->principal": (
            "SELECT COUNT(*) FROM principal_capabilities c "
            "JOIN principals p ON c.principal_id=p.id "
            "AND c.workspace_id=p.workspace_id WHERE c.id=%s",
            ids["cap_admin"],
            1,
        ),
        "revocation->artifact": (
            "SELECT COUNT(*) FROM source_revocations r JOIN artifacts a "
            "ON r.artifact_id=a.id AND r.workspace_id=a.workspace_id "
            "WHERE r.id=%s",
            ids["revocation"],
            1,
        ),
        "session->task": (
            "SELECT COUNT(*) FROM research_sessions s JOIN research_tasks t "
            "ON s.task_id=t.id AND s.workspace_id=t.workspace_id "
            "WHERE s.id=%s",
            ids["rsess"],
            1,
        ),
        "candidate->formulation+contract": (
            "SELECT COUNT(*) FROM candidate_revisions c "
            "JOIN formulation_revisions f ON c.entity_revision_id=f.id "
            "JOIN success_contract_revisions s "
            "ON c.contract_revision_id=s.id WHERE c.id=%s",
            ids["cand_r1"],
            1,
        ),
        "summary->contract": (
            "SELECT COUNT(*) FROM task_summaries ts "
            "JOIN success_contract_revisions s "
            "ON ts.contract_revision_id=s.id WHERE ts.id=%s",
            ids["summary"],
            1,
        ),
        "derived->source artifact": (
            "SELECT COUNT(*) FROM artifacts WHERE id=%s AND source_artifact_ids::text LIKE %s",
            (ids["art_derived"], f"%{ids['art_doc']}%"),
            1,
        ),
    }
    for name, (sql, param, want) in asserts.items():
        params = param if isinstance(param, tuple) else (param,)
        got = fetchval(dsn, sql, params)
        assert got == want, f"{name}: got {got}, want {want}"

    # 6. Permissions still authorise — app-level, not just row presence.
    engine = create_engine(dsn)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        ctx = load_context(session, uuid.UUID(ids["ws"]), uuid.UUID(ids["owner"]))
        assert ctx.has("administer_workspace")
        reviewer = load_context(session, uuid.UUID(ids["ws"]), uuid.UUID(ids["reviewer"]))
        assert reviewer.has("approve_experiment")
        # Scoped grant resolves only on its scope.
        assert reviewer.has("review_science", uuid.UUID(ids["proj"]))
        assert not reviewer.has("review_science", uuid.uuid4())
        # The revoked grant stays revoked through the upgrade.
        agent = load_context(session, uuid.UUID(ids["ws"]), uuid.UUID(ids["agent"]))
        assert not agent.has("request_compute")
    engine.dispose()

    # 7. The chain's populated-data effects landed as designed.
    #    0016 backfilled seq on existing outbox rows.
    seqs = fetchall(dsn, "SELECT seq FROM outbox_events ORDER BY seq")
    assert len(seqs) == 4 and all(s[0] is not None for s in seqs)
    assert len({s[0] for s in seqs}) == 4, "seq backfill duplicated"
    #    0017 contracted approvals with the scope-id unique constraint.
    assert (
        fetchval(
            dsn,
            "SELECT COUNT(*) FROM pg_constraint WHERE conname='uq_approvals_scope_id'",
        )
        == 1
    )
    #    0021/0022 immutability triggers exist on the new tables.
    trigger_names = {r[0] for r in fetchall(dsn, "SELECT tgname FROM pg_trigger")}
    assert {
        "optimization_definition_immutable",
        "analytical_series_immutable",
        "analytical_comparison_immutable",
    } <= trigger_names, f"missing immutability triggers: {trigger_names}"

    # 8. Head-era tables were created by the upgrade.
    for table in (
        "runs",
        "measurements",
        "dataset_snapshots",
        "training_runs",
        "model_releases",
        "serving_pointers",
        "session_model_pins",
        "export_proposals",
        "run_cache_entries",
    ):
        assert table_exists(dsn, table), f"missing table {table}"

    # 9. The revoked-source tombstone and its report survived.
    report = fetchval(
        dsn,
        "SELECT report FROM source_revocations WHERE id=%s",
        (ids["revocation"],),
    )
    assert report["policy"] == "retrieval+training denied"
