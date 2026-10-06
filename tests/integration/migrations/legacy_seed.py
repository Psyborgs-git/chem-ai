"""Populated previous-schema fixture for CS-1102 (§26.2).

``seed_legacy`` builds a database at ``LEGACY_BASE_REV`` containing the
immutable-evidence surface of a real populated install: workspaces,
principals + credential hashes, capabilities (active, scoped and
revoked), auth sessions, tasks, contract/decision/formulation/process/
candidate revisions with canonical content hashes, artifacts + vault
blobs, import batches/records, evidence claims + links + source chunks,
a revocation tombstone, retrieval manifests/cache, sessions/messages/
questions/summaries, context manifests and outbox events (whose ``seq``
the 0016 migration must backfill).

``seed_head_extras`` adds the head-era lineage needed by the recovery
acceptance case: run + feasibility report + export proposal, dataset
snapshot, training run, model release, serving pointer and session pin.

Snapshot/compare helpers take a per-row canonical digest of every row
in the seeded tables; after an upgrade or restore the same digest must
recompute — that is the no-silent-rewrite check (AT-1102-1/-2/-3).

Fixture data only — no scientific validation claim.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

import psycopg

from studio.persistence.revisions import canonical_json, content_hash

# Tables populated by seed_legacy, in FK-safe insertion order.
LEGACY_TABLES = [
    "workspaces",
    "principals",
    "principal_capabilities",
    "auth_sessions",
    "projects",
    "research_tasks",
    "success_contract_revisions",
    "task_decisions",
    "artifacts",
    "import_batches",
    "extracted_records",
    "evidence_claims",
    "claim_links",
    "source_chunks",
    "source_revocations",
    "retrieval_manifests",
    "retrieval_cache",
    "research_sessions",
    "session_messages",
    "task_questions",
    "task_summaries",
    "context_manifests",
    "formulation_families",
    "formulation_revisions",
    "process_revisions",
    "candidate_revisions",
    "approvals",
    "outbox_events",
]

# Tables populated by seed_head_extras.
HEAD_EXTRA_TABLES = [
    "runs",
    "run_feasibility_reports",
    "export_proposals",
    "dataset_snapshots",
    "training_runs",
    "model_releases",
    "serving_pointers",
    "session_model_pins",
]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _vault_put(vault: Path, key: str, data: bytes) -> str:
    """Write a vault blob at its opaque key; return its sha256."""
    blob = vault / key
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(data)
    return _sha256_bytes(data)


def seed_legacy(dsn: str, vault: Path) -> dict[str, Any]:
    """Populate a database sitting at LEGACY_BASE_REV. Returns ids."""
    ids = {
        k: str(uuid.uuid4())
        for k in (
            "ws",
            "owner",
            "reviewer",
            "agent",
            "cap_admin",
            "cap_review",
            "cap_scoped",
            "cap_revoked",
            "sess1",
            "sess2",
            "proj",
            "task",
            "contract_r1",
            "contract_r2",
            "decision",
            "art_src",
            "art_doc",
            "art_revoked",
            "art_derived",
            "batch",
            "rec1",
            "rec2",
            "claim1",
            "claim2",
            "link",
            "chunk1",
            "chunk2",
            "revocation",
            "retr_man",
            "retr_cache",
            "rsess",
            "msg1",
            "msg2",
            "question",
            "summary",
            "ctxman",
            "family",
            "form_r1",
            "form_r2",
            "proc_r1",
            "cand_r1",
            "appr_contract",
            "appr_form",
            "appr_rejected",
            "out1",
            "out2",
            "out3",
            "out4",
        )
    }

    # Vault blobs for the artifact rows — sha256 recorded on the row.
    blob_src = b"fixture-source-bytes:revoked-soon\n"
    blob_doc = b"record_id,field,value\nr1,yield,0.71\nr2,yield,0.64\n"
    blob_revoked = b"fixture-revoked-blob\n"
    blob_derived = b"fixture-derived-normalized\n"
    vault.mkdir(parents=True, exist_ok=True)
    key_src = "aa/" + "a" * 62
    key_doc = "bb/" + "b" * 62
    key_revoked = "cc/" + "c" * 62
    key_derived = "dd/" + "d" * 62
    sum_src = _vault_put(vault, key_src, blob_src)
    sum_doc = _vault_put(vault, key_doc, blob_doc)
    sum_revoked = _vault_put(vault, key_revoked, blob_revoked)
    sum_derived = _vault_put(vault, key_derived, blob_derived)

    # Contract payloads + canonical hashes (the domain's own helper).
    contract_p1 = {
        "metrics": [{"name": "yield", "target": ">=0.65", "unit": "fraction"}],
        "budget": {"runsMax": 4},
    }
    contract_p2 = {
        "metrics": [{"name": "yield", "target": ">=0.70", "unit": "fraction"}],
        "budget": {"runsMax": 6},
    }
    form_p1 = {"components": [{"ref": "solvent-A", "mol_fraction": 0.9}]}
    form_p2 = {"components": [{"ref": "solvent-A", "mol_fraction": 0.8}]}
    proc_p1 = {"steps": [{"op": "heat", "to_C": 60, "hold_min": 30}]}
    cand_p1 = {"entity": {"family": "f1"}, "rationale": "screen"}

    appr_contract_inputs = {
        "action": "contract.freeze",
        "taskId": ids["task"],
        "contractRevisionId": ids["contract_r1"],
        "payloadDigest": content_hash(contract_p1),
    }
    appr_form_inputs = {
        "action": "formulation.revision.accept",
        "familyId": ids["family"],
        "revisionId": ids["form_r1"],
        "payloadDigest": content_hash(form_p1),
    }
    appr_rejected_inputs = {
        "action": "export.review",
        "taskId": ids["task"],
        "proposalDigest": content_hash({"draft": True}),
    }

    j = canonical_json
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO workspaces (id, slug, display_name) VALUES (%s,%s,%s)",
            (ids["ws"], "legacy-ws", "Legacy Workspace"),
        )
        conn.execute(
            "INSERT INTO principals (id, workspace_id, kind, login, "
            "display_name, credential_hash) VALUES (%s,%s,'user',%s,%s,%s)",
            (ids["owner"], ids["ws"], "owner", "Owner", _sha256_bytes(b"owner-pw")),
        )
        conn.execute(
            "INSERT INTO principals (id, workspace_id, kind, login, "
            "display_name, credential_hash) VALUES (%s,%s,'user',%s,%s,%s)",
            (ids["reviewer"], ids["ws"], "reviewer", "Reviewer", _sha256_bytes(b"rev-pw")),
        )
        conn.execute(
            "INSERT INTO principals (id, workspace_id, kind, login, "
            "display_name) VALUES (%s,%s,'service',%s,%s)",
            (ids["agent"], ids["ws"], "agent-worker", "Agent Worker"),
        )
        # Permissions: one workspace-wide, one scoped to the project,
        # one already-revoked grant (retention evidence).
        conn.execute(
            "INSERT INTO principal_capabilities (id, workspace_id, "
            "principal_id, capability, granted_by) VALUES (%s,%s,%s,%s,%s)",
            (ids["cap_admin"], ids["ws"], ids["owner"], "administer_workspace", ids["owner"]),
        )
        conn.execute(
            "INSERT INTO principal_capabilities (id, workspace_id, "
            "principal_id, capability, granted_by) VALUES (%s,%s,%s,%s,%s)",
            (ids["cap_review"], ids["ws"], ids["reviewer"], "approve_experiment", ids["owner"]),
        )
        conn.execute(
            "INSERT INTO principal_capabilities (id, workspace_id, "
            "principal_id, capability, scope_ref, granted_by) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (
                ids["cap_scoped"],
                ids["ws"],
                ids["reviewer"],
                "review_science",
                ids["proj"],
                ids["owner"],
            ),
        )
        conn.execute(
            "INSERT INTO principal_capabilities (id, workspace_id, "
            "principal_id, capability, granted_by, revoked_at) "
            "VALUES (%s,%s,%s,%s,%s, now())",
            (ids["cap_revoked"], ids["ws"], ids["agent"], "request_compute", ids["owner"]),
        )
        # Auth material lives in the DB (no separate key store).
        conn.execute(
            "INSERT INTO auth_sessions (id, workspace_id, principal_id, "
            "token_hash, expires_at) VALUES (%s,%s,%s,%s, now()+interval '1 day')",
            (ids["sess1"], ids["ws"], ids["owner"], _sha256_bytes(b"token-owner")),
        )
        conn.execute(
            "INSERT INTO auth_sessions (id, workspace_id, principal_id, "
            "token_hash, expires_at, revoked_at) "
            "VALUES (%s,%s,%s,%s, now()+interval '1 day', now())",
            (ids["sess2"], ids["ws"], ids["reviewer"], _sha256_bytes(b"token-rev")),
        )
        conn.execute(
            "INSERT INTO projects (id, workspace_id, slug, name) VALUES (%s,%s,%s,%s)",
            (ids["proj"], ids["ws"], "legacy-proj", "Legacy Project"),
        )
        conn.execute(
            "INSERT INTO research_tasks (id, workspace_id, project_id, "
            "reviewer_id, owner_id, mode, target_kind, title, objective, "
            "workflow_state, mode_inputs) "
            "VALUES (%s,%s,%s,%s,%s,'improve','formulation',%s,%s,'active',%s)",
            (
                ids["task"],
                ids["ws"],
                ids["proj"],
                ids["reviewer"],
                ids["owner"],
                "Legacy improve task",
                "raise yield",
                j({"baselineRevisionId": None}),
            ),
        )
        conn.execute(
            "INSERT INTO success_contract_revisions (id, workspace_id, "
            "task_id, revision, status, payload, content_hash, approval_id, "
            "created_by) VALUES (%s,%s,%s,1,'frozen',%s,%s,%s,%s)",
            (
                ids["contract_r1"],
                ids["ws"],
                ids["task"],
                j(contract_p1),
                content_hash(contract_p1),
                ids["appr_contract"],
                ids["owner"],
            ),
        )
        conn.execute(
            "INSERT INTO success_contract_revisions (id, workspace_id, "
            "task_id, revision, status, payload, content_hash, created_by) "
            "VALUES (%s,%s,%s,2,'draft',%s,%s,%s)",
            (
                ids["contract_r2"],
                ids["ws"],
                ids["task"],
                j(contract_p2),
                content_hash(contract_p2),
                ids["owner"],
            ),
        )
        conn.execute(
            "INSERT INTO task_decisions (id, workspace_id, task_id, kind, "
            "decided_by, payload) VALUES (%s,%s,%s,'closure',%s,%s)",
            (
                ids["decision"],
                ids["ws"],
                ids["task"],
                ids["reviewer"],
                j(
                    {
                        "closureDecision": "supported_success",
                        "contractRevisionId": ids["contract_r1"],
                        "evaluationCycle": 1,
                        "reason": "fixture",
                    }
                ),
            ),
        )
        # Artifacts: accepted doc, soon-revoked source, derived blob.
        conn.execute(
            "INSERT INTO artifacts (id, workspace_id, storage_key, "
            "media_type, byte_size, checksum_sha256, declared_checksum, "
            "original_name, source_kind, classification, review_state, "
            "upload_state, rights, parser_version, created_by, "
            "committed_at) VALUES (%s,%s,%s,'text/csv',%s,%s,%s,'runs.csv',"
            "'upload','confidential','accepted','committed',%s,'csv-v1',%s,"
            "now())",
            (
                ids["art_doc"],
                ids["ws"],
                key_doc,
                len(blob_doc),
                sum_doc,
                sum_doc,
                j(
                    {
                        "retrieval": "allowed",
                        "extraction": "allowed",
                        "training": "allowed",
                        "export": "review",
                        "redistribution": "denied",
                    }
                ),
                ids["owner"],
            ),
        )
        conn.execute(
            "INSERT INTO artifacts (id, workspace_id, storage_key, "
            "media_type, byte_size, checksum_sha256, original_name, "
            "source_kind, classification, review_state, upload_state, "
            "created_by, committed_at) VALUES (%s,%s,%s,'text/plain',%s,%s,"
            "'source.txt','upload','restricted','revoked','committed',%s,"
            "now())",
            (
                ids["art_revoked"],
                ids["ws"],
                key_revoked,
                len(blob_revoked),
                sum_revoked,
                ids["owner"],
            ),
        )
        conn.execute(
            "INSERT INTO artifacts (id, workspace_id, storage_key, "
            "media_type, byte_size, checksum_sha256, original_name, "
            "source_kind, classification, review_state, upload_state, "
            "source_artifact_ids, created_by, committed_at) "
            "VALUES (%s,%s,%s,'text/plain',%s,%s,'normalized.txt',"
            "'derived','confidential','accepted','committed',%s,%s,now())",
            (
                ids["art_derived"],
                ids["ws"],
                key_derived,
                len(blob_derived),
                sum_derived,
                j([ids["art_doc"]]),
                ids["agent"],
            ),
        )
        conn.execute(
            "INSERT INTO artifacts (id, workspace_id, storage_key, "
            "media_type, byte_size, checksum_sha256, original_name, "
            "source_kind, classification, review_state, upload_state, "
            "created_by, committed_at) VALUES (%s,%s,%s,'application/pdf',"
            "%s,%s,'paper.pdf','upload','confidential','parsed','committed',"
            "%s,now())",
            (ids["art_src"], ids["ws"], key_src, len(blob_src), sum_src, ids["owner"]),
        )
        conn.execute(
            "INSERT INTO import_batches (id, workspace_id, artifact_id, "
            "checksum_sha256, original_name, detected_type, parser_name, "
            "parser_version, document_group, source_revision, status, "
            "record_count, created_by) "
            "VALUES (%s,%s,%s,%s,'runs.csv','csv','csv-parser','1.0',%s,1,"
            "'parsed',2,%s)",
            (ids["batch"], ids["ws"], ids["art_doc"], sum_doc, str(uuid.uuid4()), ids["agent"]),
        )
        for i, rec in enumerate(("rec1", "rec2"), start=1):
            conn.execute(
                "INSERT INTO extracted_records (id, workspace_id, "
                "batch_id, kind, locator, original_text, payload, "
                "confidence, status, reviewed_by, reviewed_at) "
                "VALUES (%s,%s,%s,'measurement',%s,%s,%s,0.9,'accepted',%s,"
                "now())",
                (
                    ids[rec],
                    ids["ws"],
                    ids["batch"],
                    j({"row": i}),
                    f"r{i},yield,0.7{i}",
                    j({"yield": 0.70 + i / 100}),
                    ids["reviewer"],
                ),
            )
        conn.execute(
            "INSERT INTO evidence_claims (id, workspace_id, kind, status, "
            "subject, statement, locator, original_text, conditions, "
            "source_batch_id, source_record_id, created_by, reviewed_by, "
            "reviewed_at) VALUES (%s,%s,'document_claim','accepted',%s,%s,"
            "%s,%s,%s,%s,%s,%s,%s,now())",
            (
                ids["claim1"],
                ids["ws"],
                j({"entity": "candidate-1"}),
                j({"predicate": "has_yield", "value": 0.71, "unit": "fraction"}),
                j({"batchId": ids["batch"], "recordId": ids["rec1"], "row": 1}),
                "yield = 0.71",
                j({"basis": "lab-run-7"}),
                ids["batch"],
                ids["rec1"],
                ids["agent"],
                ids["reviewer"],
            ),
        )
        conn.execute(
            "INSERT INTO evidence_claims (id, workspace_id, kind, status, "
            "subject, statement, locator, original_text, created_by) "
            "VALUES (%s,%s,'inferred_suggestion','proposed',%s,%s,%s,%s,%s)",
            (
                ids["claim2"],
                ids["ws"],
                j({"entity": "candidate-2"}),
                j({"predicate": "may_improve", "value": "raise temp"}),
                j({"note": "model suggestion"}),
                "raise temp",
                ids["agent"],
            ),
        )
        conn.execute(
            "INSERT INTO claim_links (id, workspace_id, from_claim_id, "
            "to_claim_id, relation, note, created_by) "
            "VALUES (%s,%s,%s,%s,'supports',%s,%s)",
            (
                ids["link"],
                ids["ws"],
                ids["claim1"],
                ids["claim2"],
                "r1 supports suggestion",
                ids["reviewer"],
            ),
        )
        conn.execute(
            "INSERT INTO source_chunks (id, workspace_id, artifact_id, "
            "batch_id, record_id, chunk_index, locator, original_text, "
            "normalized_text, extraction_method, chunking_version, rights, "
            "status) VALUES (%s,%s,%s,%s,%s,0,%s,%s,%s,'csv-rows','v1',%s,"
            "'active')",
            (
                ids["chunk1"],
                ids["ws"],
                ids["art_doc"],
                ids["batch"],
                ids["rec1"],
                j({"row": 1}),
                "r1,yield,0.71",
                "r1 yield 0.71",
                j({"retrieval": "allowed"}),
            ),
        )
        conn.execute(
            "INSERT INTO source_chunks (id, workspace_id, artifact_id, "
            "batch_id, record_id, chunk_index, locator, original_text, "
            "normalized_text, extraction_method, chunking_version, rights, "
            "status) VALUES (%s,%s,%s,%s,%s,1,%s,%s,%s,'csv-rows','v1',%s,"
            "'revoked')",
            (
                ids["chunk2"],
                ids["ws"],
                ids["art_doc"],
                ids["batch"],
                ids["rec2"],
                j({"row": 2}),
                "r2,yield,0.64",
                "r2 yield 0.64",
                j({"retrieval": "denied"}),
            ),
        )
        conn.execute(
            "INSERT INTO source_revocations (id, workspace_id, artifact_id, "
            "reason, revoked_by, report) VALUES (%s,%s,%s,%s,%s,%s)",
            (
                ids["revocation"],
                ids["ws"],
                ids["art_revoked"],
                "rights withdrawn by owner",
                ids["owner"],
                j(
                    {
                        "chunksMarkedRevoked": 0,
                        "claimsFlagged": 0,
                        "policy": "retrieval+training denied",
                    }
                ),
            ),
        )
        conn.execute(
            "INSERT INTO retrieval_manifests (id, workspace_id, "
            "principal_id, query, query_kind, cache_key, "
            "source_index_version, policy_version, chunk_ids, cached) "
            "VALUES (%s,%s,%s,'yield > 0.6','review',%s,'idx-v1','pol-v1',"
            "%s,true)",
            (
                ids["retr_man"],
                ids["ws"],
                ids["owner"],
                _sha256_bytes(b"query:yield>0.6"),
                j([ids["chunk1"]]),
            ),
        )
        conn.execute(
            "INSERT INTO retrieval_cache (id, workspace_id, cache_key, "
            "chunk_ids) VALUES (%s,%s,%s,%s)",
            (ids["retr_cache"], ids["ws"], _sha256_bytes(b"query:yield>0.6"), j([ids["chunk1"]])),
        )
        conn.execute(
            "INSERT INTO research_sessions (id, workspace_id, task_id, "
            "start_contract_revision_id, status, started_by, ended_at, "
            "end_snapshot) VALUES (%s,%s,%s,%s,'ended',%s,now(),%s)",
            (
                ids["rsess"],
                ids["ws"],
                ids["task"],
                ids["contract_r1"],
                ids["owner"],
                j({"summary": "closed on rev1"}),
            ),
        )
        conn.execute(
            "INSERT INTO session_messages (id, workspace_id, session_id, "
            "role, kind, content, refs, created_by) "
            "VALUES (%s,%s,%s,'user','message',%s,%s,%s)",
            (
                ids["msg1"],
                ids["ws"],
                ids["rsess"],
                "propose next runs",
                j({"taskId": ids["task"]}),
                ids["owner"],
            ),
        )
        conn.execute(
            "INSERT INTO session_messages (id, workspace_id, session_id, "
            "role, kind, content, refs, created_by) "
            "VALUES (%s,%s,%s,'assistant','rationale',%s,%s,%s)",
            (
                ids["msg2"],
                ids["ws"],
                ids["rsess"],
                "grounded on claim1",
                j({"claimIds": [ids["claim1"]]}),
                ids["agent"],
            ),
        )
        conn.execute(
            "INSERT INTO task_questions (id, workspace_id, task_id, "
            "question, blocking, status, resolution, raised_by, "
            "resolved_at) VALUES (%s,%s,%s,%s,true,'resolved',%s,%s,now())",
            (
                ids["question"],
                ids["ws"],
                ids["task"],
                "is the solvent lot expired?",
                "lot ok per batch record",
                ids["owner"],
            ),
        )
        conn.execute(
            "INSERT INTO task_summaries (id, workspace_id, task_id, "
            "contract_revision_id, body, source_ids, coverage, generator, "
            "created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,'sum-v1',%s)",
            (
                ids["summary"],
                ids["ws"],
                ids["task"],
                ids["contract_r1"],
                "yield 0.71 supported by r1",
                j([ids["claim1"]]),
                j({"claimsCited": 1}),
                ids["agent"],
            ),
        )
        conn.execute(
            "INSERT INTO context_manifests (id, workspace_id, task_id, "
            "contract_revision_id, compiler_version, token_budget, "
            "token_estimate, items, created_by) "
            "VALUES (%s,%s,%s,%s,'cmp-v1',4000,1200,%s,%s)",
            (
                ids["ctxman"],
                ids["ws"],
                ids["task"],
                ids["contract_r1"],
                j([{"kind": "claim", "id": ids["claim1"]}]),
                ids["agent"],
            ),
        )
        conn.execute(
            "INSERT INTO formulation_families (id, workspace_id, name, "
            "description) VALUES (%s,%s,'family-1','fixture family')",
            (ids["family"], ids["ws"]),
        )
        conn.execute(
            "INSERT INTO formulation_revisions (id, workspace_id, "
            "family_id, revision, status, payload, content_hash, "
            "approval_id, created_by) VALUES (%s,%s,%s,1,'accepted',%s,%s,"
            "%s,%s)",
            (
                ids["form_r1"],
                ids["ws"],
                ids["family"],
                j(form_p1),
                content_hash(form_p1),
                ids["appr_form"],
                ids["owner"],
            ),
        )
        conn.execute(
            "INSERT INTO formulation_revisions (id, workspace_id, "
            "family_id, revision, status, parent_revision_id, payload, "
            "content_hash, created_by) VALUES (%s,%s,%s,2,'draft',%s,%s,%s,"
            "%s)",
            (
                ids["form_r2"],
                ids["ws"],
                ids["family"],
                ids["form_r1"],
                j(form_p2),
                content_hash(form_p2),
                ids["owner"],
            ),
        )
        conn.execute(
            "INSERT INTO process_revisions (id, workspace_id, family_id, "
            "revision, status, payload, content_hash, created_by) "
            "VALUES (%s,%s,%s,1,'accepted',%s,%s,%s)",
            (
                ids["proc_r1"],
                ids["ws"],
                ids["family"],
                j(proc_p1),
                content_hash(proc_p1),
                ids["owner"],
            ),
        )
        conn.execute(
            "INSERT INTO candidate_revisions (id, workspace_id, task_id, "
            "revision, status, eligibility, entity_kind, "
            "entity_revision_id, contract_revision_id, hypothesis, "
            "payload, content_hash, created_by) "
            "VALUES (%s,%s,%s,1,'accepted_for_research',"
            "'eligible_for_approved_experiment',"
            "'formulation',%s,%s,'higher yield at 60C',%s,%s,%s)",
            (
                ids["cand_r1"],
                ids["ws"],
                ids["task"],
                ids["form_r1"],
                ids["contract_r1"],
                j(cand_p1),
                content_hash(cand_p1),
                ids["owner"],
            ),
        )
        # Approval grants — the permissions AT-1102-1 must see survive.
        for aid, action, inputs, decision in (
            (ids["appr_contract"], "contract.freeze", appr_contract_inputs, "approved"),
            (ids["appr_form"], "formulation.revision.accept", appr_form_inputs, "approved"),
            (ids["appr_rejected"], "export.review", appr_rejected_inputs, "rejected"),
        ):
            conn.execute(
                "INSERT INTO approvals (id, workspace_id, action, decision, "
                "decided_by, bound_digest, bound_inputs, policy_version, "
                "rationale) VALUES (%s,%s,%s,%s,%s,%s,%s,'pol-v1','fixture')",
                (
                    aid,
                    ids["ws"],
                    action,
                    decision,
                    ids["reviewer"],
                    content_hash(inputs),
                    j(inputs),
                ),
            )
        # Outbox events — 0016 must backfill seq on these rows.
        for i, oid in enumerate(("out1", "out2", "out3", "out4"), start=1):
            conn.execute(
                "INSERT INTO outbox_events (id, workspace_id, "
                "aggregate_type, aggregate_id, event_type, payload) "
                "VALUES (%s,%s,'research_task',%s,%s,%s)",
                (ids[oid], ids["ws"], ids["task"], f"task.event.{i}", j({"n": i})),
            )

    ids["vault_keys"] = {
        "art_doc": key_doc,
        "art_revoked": key_revoked,
        "art_derived": key_derived,
        "art_src": key_src,
    }
    return ids


def seed_head_extras(dsn: str, vault: Path, ids: dict[str, Any]) -> None:
    """Head-era lineage: run, feasibility report, export proposal,
    dataset snapshot, training run, model release, pointer and pin."""
    extra = {
        k: str(uuid.uuid4())
        for k in (
            "run",
            "attempt",
            "feasibility",
            "proposal",
            "snapshot",
            "training",
            "release",
            "pointer",
            "pin",
        )
    }
    ids.update(extra)
    j = canonical_json
    ws, task, owner, reviewer = (
        ids["ws"],
        ids["task"],
        ids["owner"],
        ids["reviewer"],
    )

    adapter_bytes = b"fixture-adapter-weights\n"
    result_bytes = b'{"result":"fixture","adapter_sha256":"%s"}\n' % (
        _sha256_bytes(adapter_bytes).encode()
    )
    adapter_key = "ee/" + "e" * 62
    result_key = "ef/" + "e" * 62
    sum_adapter = _vault_put(vault, adapter_key, adapter_bytes)
    sum_result = _vault_put(vault, result_key, result_bytes)
    doc_blob = (vault / ids["vault_keys"]["art_doc"]).read_bytes()
    sum_doc = _sha256_bytes(doc_blob)
    art_adapter, art_result = str(uuid.uuid4()), str(uuid.uuid4())
    ids["art_adapter"], ids["art_result"] = art_adapter, art_result
    ids["vault_keys"]["art_adapter"] = adapter_key
    ids["vault_keys"]["art_result"] = result_key

    request = {"kind": "optimization.screen", "taskId": task}
    bound = {"runId": extra["run"], "requestDigest": content_hash(request), "verdict": "infeasible"}
    manifest = {
        "entries": [
            {
                "recordId": ids["rec1"],
                "recordKind": "measurement",
                "sourceClass": "lab",
                "hash": _sha256_bytes(b"r1"),
                "rightsTraining": "allowed",
                "labelKind": "yield",
                "semantics": {},
                "excluded": False,
                "exclusionReason": None,
            },
        ]
    }
    spec = {
        "base": {"model": "pico-gpt", "sha256": _sha256_bytes(b"base")},
        "tokenizer": {"kind": "byte-bpe", "sha256": _sha256_bytes(b"tok")},
        "adapter": {"method": "lora", "rank": 4},
    }

    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO artifacts (id, workspace_id, storage_key, "
            "media_type, byte_size, checksum_sha256, original_name, "
            "source_kind, classification, review_state, upload_state, "
            "created_by, committed_at) VALUES (%s,%s,%s,"
            "'application/octet-stream',%s,%s,'adapter.safetensors',"
            "'derived','confidential','accepted','committed',%s,now())",
            (art_adapter, ws, adapter_key, len(adapter_bytes), sum_adapter, ids["agent"]),
        )
        conn.execute(
            "INSERT INTO artifacts (id, workspace_id, storage_key, "
            "media_type, byte_size, checksum_sha256, original_name, "
            "source_kind, classification, review_state, upload_state, "
            "created_by, committed_at) VALUES (%s,%s,%s,"
            "'application/json',%s,%s,'result.json',"
            "'derived','confidential','accepted','committed',%s,now())",
            (art_result, ws, result_key, len(result_bytes), sum_result, ids["agent"]),
        )
        conn.execute(
            "INSERT INTO runs (id, workspace_id, task_id, kind, status, "
            "request, request_digest, requested_by, attempt_count, "
            "max_attempts) VALUES (%s,%s,%s,'optimization.screen',"
            "'succeeded',%s,%s,%s,1,3)",
            (extra["run"], ws, task, j(request), content_hash(request), owner),
        )
        conn.execute(
            "INSERT INTO run_feasibility_reports (id, workspace_id, "
            "run_id, evaluated_by, operation, basis, sizes, envelope, "
            "configurations, uncertainty, reasons, missing, hardware, "
            "verdict) VALUES (%s,%s,%s,%s,'optimization.screen',"
            "'bounded_estimate',%s,%s,%s,%s,%s,%s,%s,'infeasible')",
            (
                extra["feasibility"],
                ws,
                extra["run"],
                reviewer,
                j({"batch": 128}),
                j({"memory_bytes": 5 << 30}),
                j([{"group": "cpu-pool", "verdict": "fails"}]),
                j({"memory_bytes": "±20%"}),
                j(["memory below floor"]),
                j(["gpu"]),
                j({"cpu_cores": 8, "memory_bytes": 32 << 30}),
            ),
        )
        conn.execute(
            "INSERT INTO export_proposals (id, workspace_id, run_id, "
            "feasibility_report_id, proposed_by, status, bound_inputs, "
            "bound_digest, required_capability) "
            "VALUES (%s,%s,%s,%s,%s,'proposed',%s,%s,'approve_export')",
            (
                extra["proposal"],
                ws,
                extra["run"],
                extra["feasibility"],
                owner,
                j(bound),
                content_hash(bound),
            ),
        )
        conn.execute(
            "INSERT INTO dataset_snapshots (id, workspace_id, purpose, "
            "name, task_id, manifest, digest, state, created_by, "
            "frozen_by, frozen_at) VALUES (%s,%s,'assistant_sft',"
            "'legacy-sft-set',%s,%s,%s,'frozen',%s,%s,now())",
            (extra["snapshot"], ws, task, j(manifest), content_hash(manifest), owner, reviewer),
        )
        conn.execute(
            "INSERT INTO training_runs (id, workspace_id, task_id, name, "
            "state, snapshot_id, snapshot_digest, spec, spec_digest, "
            "dataset_artifact_id, dataset_digest, dataset_manifest, "
            "telemetry, checkpoints, provenance, capability, "
            "adapter_artifact_id, result_artifact_id, run_id, "
            "approval_id, bound_digest, created_by) "
            "VALUES (%s,%s,%s,'legacy-sft-run','completed',%s,%s,%s,%s,"
            "%s,%s,%s,'{}','[]','{}','{}',%s,%s,%s,%s,%s,%s)",
            (
                extra["training"],
                ws,
                task,
                extra["snapshot"],
                content_hash(manifest),
                j(spec),
                content_hash(spec),
                ids["art_doc"],
                sum_doc,
                j(manifest),
                art_adapter,
                art_result,
                extra["run"],
                ids["appr_contract"],
                content_hash(bound),
                ids["agent"],
            ),
        )
        conn.execute(
            "INSERT INTO model_releases (id, workspace_id, task_id, name, "
            "state, snapshot_id, training_run_id, adapter_artifact_id, "
            "base_model_id, architecture, init_seed, base_sha256, "
            "license_id, tokenizer_kind, tokenizer_sha256, adapter_sha256,"
            " adapter_method, adapter_config, adapter_base_sha256, "
            "adapter_tokenizer_sha256, adapter_architecture, "
            "serving_format, conversions, validation, capability, "
            "approval_id, provenance, created_by) "
            "VALUES (%s,%s,%s,'legacy-release','promoted',%s,%s,%s,"
            "'pico-gpt','pico_gpt',0,%s,'fixture-license','byte-bpe',%s,"
            "%s,'lora',%s,%s,%s,'pico_gpt','serving-bundle-v1',%s,%s,%s,"
            "%s,%s,%s)",
            (
                extra["release"],
                ws,
                task,
                extra["snapshot"],
                extra["training"],
                art_adapter,
                _sha256_bytes(b"base"),
                _sha256_bytes(b"tok"),
                sum_adapter,
                j({"rank": 4}),
                _sha256_bytes(b"base"),
                _sha256_bytes(b"tok"),
                j([]),
                j({"status": "compatible", "mode": "stdlib", "load_verified": False}),
                j({"dataStatus": "fixture_only", "scientificStatus": "not_validated"}),
                ids["appr_contract"],
                j({"lineage": "fixture"}),
                ids["agent"],
            ),
        )
        conn.execute(
            "INSERT INTO serving_pointers (id, workspace_id, release_id, "
            "revision, reason, updated_by) VALUES (%s,%s,%s,1,'promote',%s)",
            (extra["pointer"], ws, extra["release"], ids["appr_contract"]),
        )
        conn.execute(
            "INSERT INTO session_model_pins (id, workspace_id, session_id, "
            "release_id) VALUES (%s,%s,%s,%s)",
            (extra["pin"], ws, ids["rsess"], extra["release"]),
        )


def snapshot(
    dsn: str,
    tables: list[str],
    columns: dict[str, list[str]] | None = None,
) -> dict[str, dict[str, str]]:
    """{table: {pk_text: canonical-row-digest}} over seeded tables.

    ``columns`` optionally pins the projected column set per table —
    pass the pre-change column lists so post-change rows digest over
    exactly the same fields (a migration adding a column must not
    make every old row appear changed).
    """
    snap: dict[str, dict[str, str]] = {}
    with psycopg.connect(dsn, autocommit=True) as conn:
        for table in tables:
            exists = conn.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=%s)",
                (table,),
            ).fetchone()[0]
            if not exists:
                continue
            if columns is None:
                cols = [
                    d.name
                    for d in conn.execute(
                        f"SELECT * FROM {table} LIMIT 0"  # noqa: S608 — fixture tables
                    ).description
                    or []
                ]
            else:
                cols = columns[table]
            col_sql = ", ".join(f'"{c}"' for c in cols)
            rows = conn.execute(
                f"SELECT {col_sql} FROM {table} ORDER BY id"  # noqa: S608
            ).fetchall()
            snap[table] = {}
            for row in rows:
                record = dict(zip(cols, row, strict=True))
                pk = str(record.get("id"))
                snap[table][pk] = hashlib.sha256(canonical_json(record).encode()).hexdigest()
            snap[table]["::cols"] = canonical_json(sorted(cols))
    return snap


def pre_columns(snap: dict[str, dict[str, str]]) -> dict[str, list[str]]:
    """Column lists recorded in a snapshot (for projected re-snapshots)."""
    return {table: json.loads(rows["::cols"]) for table, rows in snap.items() if "::cols" in rows}


def compare_snapshots(pre: dict[str, dict[str, str]], post: dict[str, dict[str, str]]) -> list[str]:
    """Every pre-change row must recompute the same digest on the
    columns it had. Returns a list of mismatch descriptions."""
    mismatches: list[str] = []
    for table, rows in pre.items():
        post_rows = post.get(table, {})
        for pk, digest in rows.items():
            if pk == "::cols":
                continue
            if pk not in post_rows:
                mismatches.append(f"{table}: row {pk} missing after change")
                continue
            if post_rows[pk] != digest:
                mismatches.append(f"{table}: row {pk} content changed")
    return mismatches
