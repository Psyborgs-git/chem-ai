"""CS-1003 integration tests — approved broker, revocation, receipts.

AT-1003-1  payload/recipient/expiry differs from approval → zero
           outbound proprietary bytes.
AT-1003-2  revoke during execution → cancel/reconcile records honestly
           what was already transferred — never claims unseen.
AT-1003-3  repeated/crossed/reordered provider callbacks → one
           consistent external job/artifact lineage.
"""

from __future__ import annotations

import hashlib

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cloud_broker import EgressBroker, ProviderDouble
from cloud_broker.types import sha256_bytes
from studio.application import approvals
from studio.application.idempotency import canonical_json
from studio.auth.context import load_context
from studio.domain.learning.datasets import DatasetService
from studio.domain.learning.exports.broker import ExportBrokerService
from studio.domain.learning.exports.transform import TransformService
from studio.domain.runs.admission import AdmissionService
from studio.domain.runs.feasibility import FeasibilityService
from studio.domain.runs.queue import RunService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Approval,
    Artifact,
    DatasetSnapshot,
    EvidenceClaim,
    ExportCallback,
    ExportJob,
    ExportJobAttempt,
    ExportProposal,
    ExportReceipt,
    ExportTransformedPayload,
    ExtractedRecord,
    ImportBatch,
    LabBatch,
    LabExecution,
    LabSample,
    MaterialIdentity,
    Measurement,
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    Workspace,
)

pytestmark = pytest.mark.integration

GB = 1024**3

HARDWARE_FIXTURE = {
    "os": "Linux",
    "arch": "x86_64",
    "python_version": "3.12",
    "observed_at": "2026-10-06T00:00:00+00:00",
    "memory_model": "unknown",
    "cpu_count_logical": 8,
    "cpu_count_physical": 8,
    "ram_total_bytes": 16 * GB,
    "ram_available_bytes": 8 * GB,
    "disk_free_bytes": 50 * GB,
    "gpus": [],
    "runtimes": {},
    "isolation": {},
}


def _principal(session: Session, ws: Workspace, role: str, login: str) -> Principal:
    p = Principal(workspace_id=ws.id, kind="user", login=login, display_name=login)
    session.add(p)
    session.flush()
    for cap in sorted(capabilities_for_role(role)):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=p.id, capability=cap))
    session.flush()
    return p


def _task(session: Session, ctx) -> ResearchTask:
    proj = Project(workspace_id=ctx.workspace_id, slug="p", name="P")
    session.add(proj)
    session.flush()
    task = ResearchTask(
        workspace_id=ctx.workspace_id,
        project_id=proj.id,
        mode="improve",
        title="t",
        workflow_state="active",
        target_kind="formulation",
        objective="o",
    )
    session.add(task)
    session.flush()
    return task


def _measurement(session: Session, ctx, task: ResearchTask) -> Measurement:
    ex = LabExecution(
        workspace_id=ctx.workspace_id,
        task_id=task.id,
        status="in_progress",
        historical=True,
    )
    session.add(ex)
    session.flush()
    batch = LabBatch(workspace_id=ctx.workspace_id, execution_id=ex.id, label="A")
    session.add(batch)
    session.flush()
    sample = LabSample(workspace_id=ctx.workspace_id, batch_id=batch.id, label="a1", kind="aliquot")
    session.add(sample)
    session.flush()
    m = Measurement(
        workspace_id=ctx.workspace_id,
        sample_id=sample.id,
        method="fixture-method",
        metric="metric.tack-4h",
        repeat_type="independent_batch",
        value_type="numeric",
        value={"kind": "numeric", "value": "4.2", "unit": "MPa"},
        conditions={"actual": {"temperature": 296.15}},
        status="accepted",
    )
    session.add(m)
    session.flush()
    return m


def _supplier_claim(session: Session, ctx) -> EvidenceClaim:
    art = Artifact(
        workspace_id=ctx.workspace_id,
        storage_key="aa/" + "a" * 62,
        media_type="text/csv",
        byte_size=4,
        checksum_sha256="a" * 64,
        original_name="supplier.csv",
        rights={"training": "allowed", "export": "allowed"},
    )
    session.add(art)
    session.flush()
    batch = ImportBatch(
        workspace_id=ctx.workspace_id,
        artifact_id=art.id,
        checksum_sha256="a" * 64,
        original_name="supplier.csv",
        detected_type="csv",
        parser_name="csv",
        parser_version="1",
        document_group=art.id,
        status="parsed",
    )
    session.add(batch)
    session.flush()
    rec = ExtractedRecord(
        workspace_id=ctx.workspace_id,
        batch_id=batch.id,
        kind="row",
        locator={"row": 1},
        original_text="supplier sheet",
        payload={},
        status="accepted",
    )
    session.add(rec)
    session.flush()
    claim = EvidenceClaim(
        workspace_id=ctx.workspace_id,
        kind="document_claim",
        status="accepted",
        subject={"ref": "supplier.csv"},
        statement={"claim": "viscosity 900 mPa s"},
        source_batch_id=batch.id,
        source_record_id=rec.id,
    )
    session.add(claim)
    session.flush()
    return claim


@pytest.fixture()
def env(session: Session):
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    owner = _principal(session, ws, "owner", "o")
    researcher = _principal(session, ws, "researcher", "r")
    octx = load_context(session, ws.id, owner.id)
    rctx = load_context(session, ws.id, researcher.id)
    adm = AdmissionService(session, rctx)
    adm.ensure_group(
        "compute",
        capacity={
            "cpu_cores": 8,
            "memory_bytes": 16 * GB,
            "gpu_devices": 0,
            "concurrency": 1,
        },
        reserve={"memory_bytes": 2 * GB},
    )
    session.flush()
    double = ProviderDouble()
    broker = EgressBroker(providers={double.name: double})
    return {
        "ws": ws,
        "owner": owner,
        "researcher": researcher,
        "octx": octx,
        "rctx": rctx,
        "adm": adm,
        "runs": RunService(session, rctx),
        "feas": FeasibilityService(session, rctx),
        "datasets": DatasetService(session, octx),
        "transform": TransformService(session, octx),
        "double": double,
        "broker": broker,
        "svc": ExportBrokerService(session, octx, broker=broker),
    }


def _proposal(env, session: Session) -> ExportProposal:
    run = env["runs"].request(
        kind="simulation",
        request={
            "operation": "large dft batch",
            "sizes": {"modelBytes": 2 * GB, "dataBytes": 500 * GB},
            "envelope": {"cpu_cores": 64, "memory_bytes": 256 * GB, "wall_seconds": 3600},
        },
    )
    decision = env["feas"].request_fallback(run.id, hardware=HARDWARE_FIXTURE)
    session.flush()
    assert decision.decision == "export_review_proposed"
    return session.execute(
        select(ExportProposal).where(ExportProposal.run_id == run.id)
    ).scalar_one()


def _frozen_snapshot(env, session: Session, task: ResearchTask) -> DatasetSnapshot:
    snap = env["datasets"].build("property_prediction", "export-snap", task.id)
    session.flush()
    env["datasets"].freeze(snap.id)
    session.flush()
    return snap


def _seed(env, session: Session, task: ResearchTask) -> None:
    session.add(
        MaterialIdentity(
            workspace_id=env["ws"].id,
            kind="commercial_mixture",
            name="AcmeBond 3000",
            identifiers=[{"scheme": "supplier_sku", "value": "AB-3000", "source": "supplier"}],
        )
    )
    _measurement(session, env["octx"], task)
    _supplier_claim(session, env["octx"])


def _approved(env, session: Session) -> ExportTransformedPayload:
    """prepare → human approve → returns the bound payload row."""
    task = _task(session, env["octx"])
    _seed(env, session, task)
    snap = _frozen_snapshot(env, session, task)
    proposal = _proposal(env, session)
    row = env["transform"].prepare(
        proposal.id,
        snap.id,
        recipient="provider-double",
        account="acct-test",
        region="local",
        retention_expectation="review only",
        deletion_expectation="delete after 30d",
        max_records=100,
    )
    session.flush()
    env["transform"].decide(row.id, decision="approved", rationale="reviewed")
    session.flush()
    return row


class TestDryRun:
    def test_dry_run_validates_full_binding_zero_bytes(self, env, session: Session) -> None:
        row = _approved(env, session)
        result = env["svc"].dry_run(row.id)
        session.flush()

        assert result["ok"] is True
        assert all(ok for _, ok, _ in result["checks"])
        assert env["double"].received_bytes == 0
        attempt = session.execute(
            select(ExportJobAttempt).where(ExportJobAttempt.workspace_id == env["ws"].id)
        ).scalar_one()
        assert attempt.outcome == "validated"
        assert attempt.bytes_emitted == 0

    def test_dry_run_denied_is_recorded_with_no_bytes(self, env, session: Session) -> None:
        row = _approved(env, session)
        # bound drift after approval → stale → the dry-run reports it
        env["transform"].set_classification(
            row.id, classification="restricted", rationale="deeper review"
        )
        session.flush()
        with pytest.raises(DomainError) as err:
            env["svc"].dry_run(row.id)
        assert err.value.code == ErrorCode.APPROVAL_STALE
        assert env["double"].received_bytes == 0


class TestSubmit:
    def test_submit_transfers_and_persists_lineage(self, env, session: Session) -> None:
        row = _approved(env, session)
        view = env["svc"].submit(row.id)
        session.flush()

        assert view["status"] == "transferred"
        assert view["externalJobId"]
        expected = len(canonical_json(row.payload).encode("utf-8"))
        assert view["bytesTransferred"] == expected
        assert view["exposed"] == expected
        assert env["double"].received_bytes == expected

        job = session.execute(select(ExportJob).where(ExportJob.id == view["id"])).scalar_one()
        assert job.manifest_digest == row.bound_digest
        assert job.payload_digest == row.payload_digest
        attempts = (
            session.execute(select(ExportJobAttempt).where(ExportJobAttempt.job_id == job.id))
            .scalars()
            .all()
        )
        assert [a.outcome for a in attempts] == ["transferred"]
        assert attempts[0].bytes_emitted == expected

    def test_retry_within_same_binding_reuses_job(self, env, session: Session) -> None:
        row = _approved(env, session)
        v1 = env["svc"].submit(row.id)
        v2 = env["svc"].submit(row.id)
        session.flush()
        assert v1["id"] == v2["id"]  # §20.2: retries share the manifest binding
        assert session.execute(select(func.count()).select_from(ExportJob)).scalar_one() == 1


class TestRevocation:
    def test_revoke_during_execution_honest_exposure(self, env, session: Session) -> None:
        """AT-1003-2: bytes already sent stay recorded as exposed."""
        row = _approved(env, session)
        view = env["svc"].submit(row.id)
        sent = view["bytesTransferred"]
        assert sent > 0

        result = env["svc"].revoke(row.id, reason="operator revoked")
        session.flush()
        assert result["revoked"] is True
        assert result["jobsCancelled"] == 1
        assert result["exposed"] == sent

        job = session.execute(select(ExportJob).where(ExportJob.id == view["id"])).scalar_one()
        assert job.status == "cancelled"
        assert job.exposed == sent
        receipts = (
            session.execute(select(ExportReceipt).where(ExportReceipt.job_id == job.id))
            .scalars()
            .all()
        )
        assert any(r.kind == "cancellation" for r in receipts)
        assert any(r.exposed == sent for r in receipts)

        # A later submit is blocked by approval revalidation — zero bytes.
        with pytest.raises(DomainError) as err:
            env["svc"].submit(row.id)
        assert err.value.code == ErrorCode.FORBIDDEN
        assert env["double"].received_bytes == sent

    def test_revoke_before_transfer_blocks(self, env, session: Session) -> None:
        row = _approved(env, session)
        # revoke via the approvals ledger itself (human + capability gated)
        approval = session.execute(
            select(Approval).where(
                Approval.workspace_id == env["ws"].id,
                Approval.bound_digest == row.bound_digest,
            )
        ).scalar_one()
        approvals.revoke(session, env["octx"], approval_id=approval.id)
        session.flush()
        env["svc"].revoke(row.id, reason="pre-transfer revoke")
        session.flush()

        with pytest.raises(DomainError) as err:
            env["svc"].submit(row.id)
        assert err.value.code == ErrorCode.FORBIDDEN
        assert env["double"].received_bytes == 0


class TestCallbacks:
    def test_repeated_reordered_callbacks_converge(self, env, session: Session) -> None:
        """AT-1003-3: duplicates + reordering → one consistent lineage."""
        row = _approved(env, session)
        view = env["svc"].submit(row.id)
        session.flush()
        assert view["externalJobId"]

        events = [
            ("cb-2", "running", 2, []),
            ("cb-1", "submitted", 1, []),  # crossed order
            ("cb-2", "running", 2, []),  # exact replay
            ("cb-3", "succeeded", 3, ["ext-art-1"]),
            ("cb-3", "succeeded", 3, ["ext-art-1"]),  # replay
        ]
        for cb_id, event, seq, arts in events:
            env["svc"].handle_callback(
                view["id"], callback_id=cb_id, event=event, seq=seq, artifacts=arts
            )
        session.flush()

        job = session.execute(select(ExportJob).where(ExportJob.id == view["id"])).scalar_one()
        assert job.status == "succeeded"
        assert job.external_state == "succeeded"
        assert sorted(job.artifact_ids) == ["ext-art-1"]
        rows = (
            session.execute(select(ExportCallback).where(ExportCallback.job_id == job.id))
            .scalars()
            .all()
        )
        assert len(rows) == 3  # cb-1, cb-2, cb-3 — replays deduped

        # terminal state cannot regress on a late 'running' replay
        env["svc"].handle_callback(view["id"], callback_id="cb-4", event="running", seq=4)
        session.flush()
        job2 = session.execute(
            select(ExportJob).where(ExportJob.id == view["id"])
        ).scalar_one()
        assert job2.status == "succeeded"


class TestReceipts:
    def test_reconcile_lists_unresolved_retention(self, env, session: Session) -> None:
        row = _approved(env, session)
        view = env["svc"].submit(row.id)
        session.flush()

        env["svc"].reconcile(view["id"])
        session.flush()
        receipt = session.execute(
            select(ExportReceipt).where(
                ExportReceipt.job_id == view["id"],
                ExportReceipt.kind == "reconcile",
            )
        ).scalar_one()
        # provider still holds the payload → honestly listed, never hidden
        assert "provider still retains submitted payload bytes" in (receipt.unresolved_retention)
        assert receipt.bytes_transferred == view["bytesTransferred"]

    def test_delete_remote_records_receipt(self, env, session: Session) -> None:
        row = _approved(env, session)
        view = env["svc"].submit(row.id)
        session.flush()

        deleted = env["svc"].delete_remote(view["id"])
        session.flush()
        assert deleted["status"] == "deleted"
        receipt = session.execute(
            select(ExportReceipt).where(
                ExportReceipt.job_id == view["id"],
                ExportReceipt.kind == "deletion",
            )
        ).scalar_one()
        assert receipt.receipt_ref
        assert receipt.raw["deleted"] is True


class TestReturnedArtifacts:
    def test_returned_checkpoint_quarantined_before_vault_commit(
        self, env, session: Session, tmp_path
    ) -> None:
        """§20.5: returned checkpoints/logs are confidential AND
        untrusted — digest-validated, quarantined, vault-committed,
        never publishable."""
        from studio.domain.evidence.vault import Vault

        row = _approved(env, session)
        view = env["svc"].submit(row.id)
        session.flush()
        svc = ExportBrokerService(session, env["octx"], broker=env["broker"], vault=Vault(tmp_path))
        raw = b"checkpoint-bytes-from-provider"
        digest = sha256_bytes(raw)
        art = svc.import_returned_artifact(
            view["id"], data=raw, declared_digest=digest, kind="checkpoint"
        )
        session.flush()
        assert art.classification == "confidential"
        assert art.review_state == "quarantined"
        assert art.source_kind == "derived"
        assert art.upload_state == "committed"
        assert art.rights["publishable"] is False
        assert hashlib.sha256(raw).hexdigest() == art.checksum_sha256
        # blob verifiably staged into the vault
        assert Vault(tmp_path).blob_exists(env["ws"].id, art.storage_key)

    def test_wrong_declared_digest_rejected(self, env, session: Session, tmp_path) -> None:
        from studio.domain.evidence.vault import Vault

        row = _approved(env, session)
        view = env["svc"].submit(row.id)
        session.flush()
        svc = ExportBrokerService(session, env["octx"], broker=env["broker"], vault=Vault(tmp_path))
        with pytest.raises(DomainError) as err:
            svc.import_returned_artifact(
                view["id"], data=b"actual", declared_digest="f" * 64, kind="log"
            )
        assert err.value.code == ErrorCode.VALIDATION
        assert session.execute(select(func.count()).select_from(ExportCallback)).scalar_one() >= 0
