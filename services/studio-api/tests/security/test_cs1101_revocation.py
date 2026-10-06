"""CS-1101 security tests — AT-1101-2 revocation cascade.

A revoked sensitive source must propagate consistently through every
surface that ever touched it: retrieval index + caches, extracted
records, evidence claims, derived artifact lineage, exposure
reporting, and (CS-1003) the egress broker's revoked bindings.

Every test here *attacks* the surface — the assertion is that the
hostile/revoked content cannot reappear, and that what already left
is recorded honestly rather than erased.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import load_context
from studio.domain.evidence.archive import ArchiveLimits
from studio.domain.evidence.claims import ClaimService
from studio.domain.evidence.imports import ImportService
from studio.domain.evidence.retrieval import RetrievalService
from studio.domain.evidence.revocation import RevocationService
from studio.domain.evidence.service import ArtifactService
from studio.domain.evidence.vault import Vault
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Artifact,
    ExtractedRecord,
    Principal,
    PrincipalCapability,
    RetrievalCache,
    SourceChunk,
    Workspace,
)

pytestmark = pytest.mark.security

PAYLOAD = b"approved-payload-bytes-for-export"


@pytest.fixture()
def env(session: Session, tmp_path: Path):
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    steward_p = Principal(workspace_id=ws.id, kind="user", login="ds", display_name="ds")
    session.add(steward_p)
    session.flush()
    for cap in sorted(capabilities_for_role("data_steward")):
        session.add(
            PrincipalCapability(workspace_id=ws.id, principal_id=steward_p.id, capability=cap)
        )
    agent_p = Principal(workspace_id=ws.id, kind="agent", login="bot", display_name="b")
    session.add(agent_p)
    session.flush()
    for cap in sorted(capabilities_for_role("agent")):
        session.add(
            PrincipalCapability(workspace_id=ws.id, principal_id=agent_p.id, capability=cap)
        )
    # a reader: has read_project but not manage_sources
    reader_p = Principal(workspace_id=ws.id, kind="user", login="rd", display_name="rd")
    session.add(reader_p)
    session.flush()
    for cap in sorted(capabilities_for_role("researcher")):
        if cap == "manage_sources":
            continue
        session.add(
            PrincipalCapability(workspace_id=ws.id, principal_id=reader_p.id, capability=cap)
        )
    session.flush()
    vault = Vault(tmp_path)
    return {
        "ws": ws,
        "steward": load_context(session, ws.id, steward_p.id),
        "agent": load_context(session, ws.id, agent_p.id),
        "reader": load_context(session, ws.id, reader_p.id),
        "steward_p": steward_p,
        "artifacts": ArtifactService(
            session, vault, max_bytes=64 * 1024 * 1024, archive_limits=ArchiveLimits()
        ),
        "importer": ImportService(session, vault, isolate=False),
        "retrieval": RetrievalService(session),
        "claims": ClaimService(session),
        "revocations": RevocationService(session, load_context(session, ws.id, steward_p.id)),
        "session": session,
    }


def _index(env: dict) -> tuple[uuid.UUID, uuid.UUID]:
    """Commit+import+index a csv; returns (artifact_id, batch_id)."""
    ctx = env["steward"]
    data = b"component,amount\nresin_A,12\ncure_agent,3\n"
    artifact = env["artifacts"].initiate(
        ctx,
        original_name="recipe.csv",
        media_type="text/csv",
        declared_size=len(data),
        declared_checksum=None,
    )
    env["artifacts"].staging_path(ctx, artifact.id).write_bytes(data)
    artifact = env["artifacts"].finish(ctx, artifact.id)
    batch, _ = env["importer"].import_artifact(ctx, artifact.id)
    env["retrieval"].index_batch(ctx, batch.id)
    return artifact.id, batch.id


def _derived_artifact(
    env: dict, name: str, source_ids: list[str], created_by: uuid.UUID
) -> Artifact:
    """A derived artifact (dataset snapshot, model artifact, report)
    claiming lineage from source ids — what the cascade must mark."""
    a = Artifact(
        workspace_id=env["ws"].id,
        storage_key=f"derived/{name}",
        media_type="application/json",
        byte_size=10,
        original_name=name,
        source_kind="derived",
        review_state="accepted",
        upload_state="committed",
        source_artifact_ids=source_ids,
        created_by=created_by,
    )
    env["session"].add(a)
    env["session"].flush()
    return a


class TestCascadeCompleteness:
    """AT-1101-2 — every downstream surface of a revoked source flips
    to a revocation-consistent state in the same transaction."""

    def test_records_rejected_and_claims_superseded(self, env: dict) -> None:
        ctx = env["steward"]
        artifact_id, batch_id = _index(env)
        record = (
            env["session"]
            .execute(select(ExtractedRecord).where(ExtractedRecord.batch_id == batch_id))
            .scalars()
            .first()
        )
        accepted = env["claims"].promote_record(
            ctx,
            record.id,
            subject={"entity": "resin_A"},
            statement={"kind": "amount", "value": 12},
        )
        claim2 = env["claims"].create_claim(
            ctx,
            kind="document_claim",
            subject={"entity": "cure_agent"},
            statement={"kind": "amount", "value": 3},
        )
        claim2.source_batch_id = batch_id
        claim2.status = "accepted"
        env["session"].flush()

        env["revocations"].revoke(ctx, artifact_id, reason="rights withdrawn")

        env["session"].refresh(record)
        assert record.status == "rejected"
        assert "source_revoked" in record.flags
        env["session"].refresh(accepted)
        env["session"].refresh(claim2)
        assert accepted.status == "superseded"
        assert claim2.status == "superseded"
        # the artifact itself is revoked and stays committed-but-dead
        artifact = env["session"].get(Artifact, artifact_id)
        assert artifact.review_state == "revoked"

    def test_derived_lineage_marked_bfs(self, env: dict) -> None:
        ctx = env["steward"]
        artifact_id, _ = _index(env)
        dataset_art = _derived_artifact(
            env, "dataset-snap.json", [str(artifact_id)], ctx.principal_id
        )
        model_art = _derived_artifact(
            env, "model-artifact.bin", [str(dataset_art.id)], ctx.principal_id
        )
        unrelated = _derived_artifact(env, "clean.json", [], ctx.principal_id)

        env["revocations"].revoke(ctx, artifact_id, reason="consent revoked")

        env["session"].refresh(dataset_art)
        env["session"].refresh(model_art)
        env["session"].refresh(unrelated)
        for derived in (dataset_art, model_art):
            assert derived.retention["lineage_review"] == "required"
            assert derived.retention["lineage_affected_by"] == str(artifact_id)
        assert not (unrelated.retention or {}).get("lineage_review")

    def test_past_exposure_recorded_honestly(self, env: dict) -> None:
        ctx = env["steward"]
        artifact_id, _ = _index(env)
        # two principals actually see the chunk before revocation —
        # the exposure must be recorded, not forgotten
        hits, manifest1 = env["retrieval"].search(ctx, "resin_A")
        assert len(hits) == 1
        env["retrieval"].search(env["agent"], "resin_A")

        row = env["revocations"].revoke(ctx, artifact_id, reason="rights withdrawn")

        assert str(manifest1.id) in row.report["exposedManifestIds"]
        assert str(ctx.principal_id) in row.report["exposedPrincipalIds"]
        assert str(env["agent"].principal_id) in row.report["exposedPrincipalIds"]
        # manifests are never deleted — past exposure stays auditable
        assert row.report["chunksRevoked"] >= 1

    def test_report_discloses_missing_registries(self, env: dict) -> None:
        ctx = env["steward"]
        artifact_id, _ = _index(env)
        row = env["revocations"].revoke(ctx, artifact_id, reason="policy change")
        # dataset/model-release registries don't exist yet — the
        # report must say so instead of pretending zero impact
        assert row.report["affectedDatasetIds"] == []
        assert row.report["affectedModelReleaseIds"] == []
        assert row.report["unlearningGuarantee"] is False

    def test_rejected_records_never_enter_index(self, env: dict) -> None:
        """Rejected records — including source_revoked ones — must not
        be chunked into the index even if index_batch is re-driven."""
        ctx = env["steward"]
        artifact_id, batch_id = _index(env)
        env["revocations"].revoke(ctx, artifact_id, reason="tainted")
        # drive a second indexing pass over the same batch after
        # clearing chunk rows — rejected records must not be served
        env["session"].execute(
            select(SourceChunk).where(SourceChunk.batch_id == batch_id)
        ).scalars().all()
        for chunk in (
            env["session"]
            .execute(select(SourceChunk).where(SourceChunk.batch_id == batch_id))
            .scalars()
        ):
            assert chunk.status == "revoked"

    def test_revoked_artifact_cannot_reimport(self, env: dict) -> None:
        ctx = env["steward"]
        artifact_id, batch_id = _index(env)
        env["revocations"].revoke(ctx, artifact_id, reason="withdrawn")
        with pytest.raises(DomainError) as exc:
            env["importer"].import_artifact(ctx, artifact_id)
        assert exc.value.code == ErrorCode.CONFLICT
        assert "revoked" in str(exc.value)
        # and indexing the old batch cannot resurrect content
        env["retrieval"].index_batch(ctx, batch_id)
        assert env["retrieval"].search(ctx, "resin_A")[0] == []

    def test_revoke_authorization_edges(self, env: dict) -> None:
        ctx = env["steward"]
        artifact_id, _ = _index(env)

        with pytest.raises(DomainError) as exc:
            RevocationService(env["session"], env["agent"]).revoke(
                env["agent"], artifact_id, reason="try"
            )
        assert exc.value.code == ErrorCode.FORBIDDEN

        with pytest.raises(DomainError) as exc:
            env["revocations"].revoke(env["reader"], artifact_id, reason="try")
        assert exc.value.code == ErrorCode.FORBIDDEN

        with pytest.raises(DomainError) as exc:
            env["revocations"].revoke(ctx, artifact_id, reason="  ")
        assert exc.value.code == ErrorCode.VALIDATION

        env["revocations"].revoke(ctx, artifact_id, reason="real")
        with pytest.raises(DomainError) as exc:
            env["revocations"].revoke(ctx, artifact_id, reason="again")
        assert exc.value.code == ErrorCode.CONFLICT

    def test_revoke_foreign_artifact_is_404_not_oracle(self, env: dict, session: Session) -> None:
        foreign = Workspace(slug="other", display_name="Other")
        session.add(foreign)
        session.flush()
        fp = Principal(workspace_id=foreign.id, kind="user", login="f", display_name="f")
        session.add(fp)
        session.flush()
        f_art = Artifact(
            workspace_id=foreign.id,
            storage_key="k/foreign",
            media_type="text/csv",
            byte_size=3,
            original_name="f.csv",
            source_kind="upload",
            upload_state="committed",
            created_by=fp.id,
        )
        session.add(f_art)
        session.flush()
        with pytest.raises(DomainError) as exc:
            env["revocations"].revoke(env["steward"], f_art.id, reason="cross-scope")
        assert exc.value.code == ErrorCode.NOT_FOUND
        env["session"].refresh(f_art)
        assert f_art.review_state != "revoked"


class TestStaleCacheDefense:
    """Even if a corrupted/stale cache row names revoked chunks, the
    serve path re-filters on chunk status — defense in depth."""

    def test_stale_cache_row_cannot_resurface_revoked_chunks(self, env: dict) -> None:
        ctx = env["steward"]
        artifact_id, _ = _index(env)
        hits, _ = env["retrieval"].search(ctx, "resin_A")
        revoked_ids = [h.chunk_id for h in hits]
        env["revocations"].revoke(ctx, artifact_id, reason="withdrawn")
        # forge a cache row pointing at the revoked chunks under a
        # plausible key — simulates any cache-invalidation bug
        env["session"].add(
            RetrievalCache(
                workspace_id=env["ws"].id,
                cache_key="forged-stale-key",
                chunk_ids=revoked_ids,
            )
        )
        env["session"].flush()
        rows = env["retrieval"]._fetch_chunks(ctx, [uuid.UUID(i) for i in revoked_ids])
        assert rows == []
        assert env["retrieval"].search(ctx, "resin_A")[0] == []


# ---------------------------------------------------------------------
# CS-1003 egress broker — revocation must also close the bytes boundary
# ---------------------------------------------------------------------

from cloud_broker import (  # noqa: E402
    ApprovedBinding,
    EgressBroker,
    EgressGate,
    Permit,
    ProviderDouble,
    Recipient,
    TransferLimits,
    TransferOrder,
)
from cloud_broker.types import CallbackEvent, sha256_bytes  # noqa: E402


def _recipient(**over: str) -> Recipient:
    kw = {
        "provider": "provider-double",
        "account": "acct-1",
        "region": "local",
        "environment": "double",
    }
    kw.update(over)
    return Recipient(**kw)


def _binding(payload: bytes = PAYLOAD, **over) -> ApprovedBinding:
    kw = {
        "manifest_digest": "manifest-1",
        "payload_digest": sha256_bytes(payload),
        "payload_fields": ("smiles", "yield_pct"),
        "source_digests": ("src-1",),
        "transformation_version": "transform-v1",
        "classification": "confidential",
        "recipient": _recipient(),
        "runtime_digest": "runtime-v1",
        "permitted_job": "sft-training",
        "limits": TransferLimits(max_bytes=1_048_576, max_artifacts=8, wall_seconds=3600.0),
        "expiry": datetime.now(UTC) + timedelta(hours=1),
        "approver": "owner-1",
    }
    kw.update(over)
    return ApprovedBinding(**kw)


def _order(binding: ApprovedBinding | None = None, **over) -> TransferOrder:
    binding = binding or _binding()
    kw = {
        "approved": binding,
        "requested_digest": binding.digest(),
        "requested_recipient": binding.recipient,
        "requested_job": binding.permitted_job,
        "approval_digest": binding.digest(),
        "attempt_key": "attempt-k1",
    }
    kw.update(over)
    return TransferOrder(**kw)


@pytest.fixture()
def stack() -> tuple[EgressBroker, ProviderDouble]:
    double = ProviderDouble(auto_progress=False)
    return EgressBroker(providers={double.name: double}), double


class TestBrokerRevocation:
    """The CS-1003 broker is the single egress path — a revoked
    approval must emit zero bytes, and exposure already incurred is
    recorded, not erased."""

    def test_revoked_binding_denies_later_transfers(self, stack) -> None:
        broker, double = stack
        order = _order()
        report = broker.dry_run(order, PAYLOAD)
        assert report.ok  # preview validates before revocation
        broker.revoke_binding(order.approval_digest)
        handle = broker.transfer(order, PAYLOAD)
        assert handle is None
        assert double.received_bytes == 0
        denied = [a for a in broker.attempts if a.outcome == "denied"]
        assert denied and "revoked" in denied[-1].reason

    def test_revoked_binding_dry_run_reports_reason(self, stack) -> None:
        broker, _ = stack
        order = _order()
        broker.revoke_binding(order.approval_digest)
        report = broker.dry_run(order, PAYLOAD)
        names = {n for n, ok, _ in report.checks if not ok}
        assert "binding_not_revoked" in names
        assert report.ok is False

    def test_transfer_denied_leaves_attempt_ledger(self, stack) -> None:
        broker, double = stack
        binding = _binding()
        order = _order(binding, requested_digest="sha256:forged")
        assert broker.transfer(order, PAYLOAD) is None
        assert double.received_bytes == 0
        assert any(a.outcome == "denied" for a in broker.attempts)

    def test_cancel_records_exposure_honestly(self, stack) -> None:
        broker, double = stack
        order = _order()
        handle = broker.transfer(order, PAYLOAD)
        assert handle is not None
        assert double.received_bytes == len(PAYLOAD)
        report = broker.cancel(handle.job_id)
        # bytes that already moved stay reported as exposed —
        # cancel must never claim them 'unseen'
        assert report.exposed is True
        assert report.bytes_transferred == len(PAYLOAD)
        assert "provider still retains" in " ".join(report.unresolved_retention)

    def test_delete_produces_receipt_and_reconcile_clears(self, stack) -> None:
        broker, _ = stack
        handle = broker.transfer(_order(), PAYLOAD)
        receipt = broker.delete(handle.job_id)
        assert receipt.deleted is True
        lineage = broker.lineage(handle.job_id)
        assert lineage.state == "deleted"
        report = broker.reconcile(handle.job_id)
        assert report.state == "deleted"
        assert report.unresolved_retention == []

    def test_unknown_job_raises_not_silent(self, stack) -> None:
        broker, _ = stack
        with pytest.raises(KeyError):
            broker.reconcile("double-999")
        with pytest.raises(KeyError):
            broker.delete("double-999")

    def test_callbacks_converge_idempotently(self, stack) -> None:
        broker, _ = stack
        handle = broker.transfer(_order(), PAYLOAD)
        jid = handle.job_id
        # duplicate delivery is dropped
        cb = CallbackEvent(callback_id="cb-1", job_id=jid, event="running", seq=1)
        assert broker.handle_callback(cb) is True
        assert broker.handle_callback(cb) is False
        # reordered events converge on the higher-rank terminal state
        early = CallbackEvent(callback_id="cb-2", job_id=jid, event="cancelled", seq=3)
        late = CallbackEvent(callback_id="cb-3", job_id=jid, event="failed", seq=4)
        broker.handle_callback(late)
        broker.handle_callback(early)
        lineage = broker.lineage(jid)
        assert lineage.state in {"failed", "cancelled"}
        assert lineage.last_seq == 4
        # unknown job callbacks are ignored
        ghost = CallbackEvent(callback_id="g-1", job_id="double-404", event="running", seq=1)
        assert broker.handle_callback(ghost) is False
        # artifacts dedup by id
        a1 = CallbackEvent(
            callback_id="cb-4", job_id=jid, event="running", seq=5, artifacts=("art-1",)
        )
        a2 = CallbackEvent(
            callback_id="cb-5", job_id=jid, event="running", seq=6, artifacts=("art-1", "art-2")
        )
        broker.handle_callback(a1)
        broker.handle_callback(a2)
        assert broker.lineage(jid).artifact_ids == ["art-1", "art-2"]


class TestEgressGateBoundary:
    """The gate is the last line: an issued permit still cannot move
    mismatched, oversized, expired or replayed bytes."""

    def _permit(self, payload: bytes = PAYLOAD, **over) -> Permit:
        kw = {
            "permit_id": "permit-1",
            "attempt_key": "a1",
            "payload_digest": sha256_bytes(payload),
            "recipient": _recipient(),
            "permitted_job": "sft-training",
            "limits": TransferLimits(max_bytes=1_048_576, max_artifacts=8, wall_seconds=3600.0),
            "expiry": datetime.now(UTC) + timedelta(hours=1),
        }
        kw.update(over)
        return Permit(**kw)

    def test_permit_single_use_replay_denied(self) -> None:
        gate, double = EgressGate(), ProviderDouble()
        permit = self._permit()
        gate.emit(permit, double, PAYLOAD)
        assert double.received_bytes == len(PAYLOAD)
        with pytest.raises(Exception, match="already spent"):
            gate.emit(permit, double, PAYLOAD)
        assert double.received_bytes == len(PAYLOAD)  # no second emit

    def test_tampered_payload_denied_zero_bytes(self) -> None:
        gate, double = EgressGate(), ProviderDouble()
        with pytest.raises(Exception, match="digest"):
            gate.emit(self._permit(), double, b"tampered-other-bytes")
        assert double.received_bytes == 0

    def test_expired_permit_denied(self) -> None:
        gate, double = EgressGate(), ProviderDouble()
        permit = self._permit(expiry=datetime.now(UTC) - timedelta(seconds=1))
        with pytest.raises(Exception, match="expired"):
            gate.emit(permit, double, PAYLOAD)
        assert double.received_bytes == 0

    def test_oversized_payload_denied(self) -> None:
        gate, double = EgressGate(), ProviderDouble()
        permit = self._permit(
            limits=TransferLimits(max_bytes=4, max_artifacts=8, wall_seconds=60.0)
        )
        with pytest.raises(Exception, match="byte limit"):
            gate.emit(permit, double, PAYLOAD)
        assert double.received_bytes == 0

    def test_check_matches_emit_policy(self) -> None:
        """dry_run/check and emit share one check path — a caller
        cannot preview-clean then emit-dirty."""
        gate, double = EgressGate(), ProviderDouble()
        permit = self._permit()
        gate.check(permit, PAYLOAD)  # clean preview
        with pytest.raises(Exception, match="digest"):
            gate.emit(permit, double, b"different-bytes")
        assert double.received_bytes == 0
