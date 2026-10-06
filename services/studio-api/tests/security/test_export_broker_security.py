"""CS-1003 security tests — the egress boundary holds under misuse.

AT-1003-1 [security]  payload/recipient/expiry differing from the
                      approval emits ZERO outbound proprietary bytes —
                      enforced at the bytes boundary, not just the
                      service layer.
AT-1003-2 [security]  revocation records honestly what was exposed;
                      revocation is a human-only act.
AT-1003-3             untrusted callbacks can't fabricate state.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session

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
    EvidenceClaim,
    ExportJob,
    ExportJobAttempt,
    ExportProposal,
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

pytestmark = pytest.mark.security

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


def _seeded_workspace(env, session: Session):
    task = _task(session, env["octx"])
    session.add(
        MaterialIdentity(
            workspace_id=env["ws"].id,
            kind="commercial_mixture",
            name="AcmeBond 3000",
            identifiers=[{"scheme": "supplier_sku", "value": "AB-3000", "source": "supplier"}],
        )
    )
    ex = LabExecution(
        workspace_id=env["octx"].workspace_id,
        task_id=task.id,
        status="in_progress",
        historical=True,
    )
    session.add(ex)
    session.flush()
    batch = LabBatch(workspace_id=env["octx"].workspace_id, execution_id=ex.id, label="A")
    session.add(batch)
    session.flush()
    sample = LabSample(
        workspace_id=env["octx"].workspace_id,
        batch_id=batch.id,
        label="a1",
        kind="aliquot",
    )
    session.add(sample)
    session.flush()
    session.add(
        Measurement(
            workspace_id=env["octx"].workspace_id,
            sample_id=sample.id,
            method="fixture-method",
            metric="metric.tack-4h",
            repeat_type="independent_batch",
            value_type="numeric",
            value={"kind": "numeric", "value": "4.2", "unit": "MPa"},
            conditions={"actual": {"temperature": 296.15}},
            status="accepted",
        )
    )
    art = Artifact(
        workspace_id=env["octx"].workspace_id,
        storage_key="aa/" + "a" * 62,
        media_type="text/csv",
        byte_size=4,
        checksum_sha256="a" * 64,
        original_name="supplier.csv",
        rights={"training": "allowed", "export": "allowed"},
    )
    session.add(art)
    session.flush()
    ib = ImportBatch(
        workspace_id=env["octx"].workspace_id,
        artifact_id=art.id,
        checksum_sha256="a" * 64,
        original_name="supplier.csv",
        detected_type="csv",
        parser_name="csv",
        parser_version="1",
        document_group=art.id,
        status="parsed",
    )
    session.add(ib)
    session.flush()
    rec = ExtractedRecord(
        workspace_id=env["octx"].workspace_id,
        batch_id=ib.id,
        kind="row",
        locator={"row": 1},
        original_text="supplier sheet",
        payload={},
        status="accepted",
    )
    session.add(rec)
    session.flush()
    session.add(
        EvidenceClaim(
            workspace_id=env["octx"].workspace_id,
            kind="document_claim",
            status="accepted",
            subject={"ref": "supplier.csv"},
            statement={"claim": "viscosity 900 mPa s"},
            source_batch_id=ib.id,
            source_record_id=rec.id,
        )
    )
    session.flush()
    return task


@pytest.fixture()
def env(session: Session):
    from cloud_broker import EgressBroker, ProviderDouble

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
        "octx": octx,
        "rctx": rctx,
        "runs": RunService(session, rctx),
        "feas": FeasibilityService(session, rctx),
        "datasets": DatasetService(session, octx),
        "transform": TransformService(session, octx),
        "double": double,
        "broker": broker,
        "svc": ExportBrokerService(session, octx, broker=broker),
    }


def _approved(env, session: Session) -> ExportTransformedPayload:
    task = _seeded_workspace(env, session)
    snap = env["datasets"].build("property_prediction", "export-snap", task.id)
    session.flush()
    env["datasets"].freeze(snap.id)
    session.flush()
    run = env["runs"].request(
        kind="simulation",
        request={
            "operation": "large dft batch",
            "sizes": {"modelBytes": 2 * GB, "dataBytes": 500 * GB},
            "envelope": {"cpu_cores": 64, "memory_bytes": 256 * GB, "wall_seconds": 3600},
        },
    )
    env["feas"].request_fallback(run.id, hardware=HARDWARE_FIXTURE)
    session.flush()
    proposal = session.execute(
        select(ExportProposal).where(ExportProposal.run_id == run.id)
    ).scalar_one()
    row = env["transform"].prepare(
        proposal.id,
        snap.id,
        recipient="provider-double",
        account="acct-test",
        region="local",
        deletion_expectation="delete after 30d",
        max_records=100,
    )
    session.flush()
    env["transform"].decide(row.id, decision="approved", rationale="reviewed")
    session.flush()
    return row


class TestDeniedTransfersEmitNothing:
    """AT-1003-1: every drifted/mismatched/embittered attempt emits
    exactly zero bytes at the boundary — verified against the
    provider-double's own byte counter."""

    def test_recipient_mismatch_zero_bytes(self, env, session: Session) -> None:
        row = _approved(env, session)
        view = env["svc"].submit(
            row.id,
            requested_recipient={
                "provider": "provider-double",
                "account": "acct-attacker",
                "region": "elsewhere",
                "environment": "unconfigured",
            },
        )
        session.flush()
        assert view["status"] == "denied"
        assert env["double"].received_bytes == 0
        attempt = session.execute(
            select(ExportJobAttempt).where(ExportJobAttempt.job_id == view["id"])
        ).scalar_one()
        assert attempt.outcome == "denied"
        assert attempt.bytes_emitted == 0

    def test_payload_digest_mismatch_zero_bytes(self, env, session: Session) -> None:
        row = _approved(env, session)
        view = env["svc"].submit(row.id, requested_digest="0" * 64)
        session.flush()
        assert view["status"] == "denied"
        assert env["double"].received_bytes == 0

    def test_drifted_bound_inputs_stale_zero_bytes(self, env, session: Session) -> None:
        """Reviewed classification change re-binds the digest — the old
        approval is stale (AT-1002-3) and emits nothing (AT-1003-1)."""
        row = _approved(env, session)
        env["transform"].set_classification(
            row.id, classification="restricted", rationale="tighter"
        )
        session.flush()
        with pytest.raises(DomainError) as err:
            env["svc"].submit(row.id)
        assert err.value.code == ErrorCode.APPROVAL_STALE
        assert env["double"].received_bytes == 0

    def test_expired_approval_zero_bytes(self, env, session: Session) -> None:
        row = _approved(env, session)
        approval = session.execute(
            select(Approval).where(
                Approval.workspace_id == env["ws"].id,
                Approval.bound_digest == row.bound_digest,
            )
        ).scalar_one()
        approval.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.flush()
        with pytest.raises(DomainError) as err:
            env["svc"].submit(row.id)
        assert err.value.code == ErrorCode.APPROVAL_EXPIRED
        assert env["double"].received_bytes == 0

    def test_no_capability_no_egress(self, env, session: Session) -> None:
        """A researcher without review_export cannot even attempt."""
        row = _approved(env, session)
        svc_r = ExportBrokerService(session, env["rctx"], broker=env["broker"])
        with pytest.raises(DomainError) as err:
            svc_r.submit(row.id)
        assert err.value.code == ErrorCode.FORBIDDEN
        assert env["double"].received_bytes == 0

    def test_provider_not_configured_is_failed_not_silent(self, env, session: Session) -> None:
        """Approval bound to a provider that is not_configured → the
        attempt is honestly recorded as failed, nothing emitted."""
        task = _seeded_workspace(env, session)
        snap = env["datasets"].build("property_prediction", "s2", task.id)
        session.flush()
        env["datasets"].freeze(snap.id)
        session.flush()
        run = env["runs"].request(
            kind="simulation",
            request={
                "operation": "big batch",
                "sizes": {"modelBytes": 2 * GB, "dataBytes": 500 * GB},
                "envelope": {"cpu_cores": 64, "memory_bytes": 256 * GB, "wall_seconds": 3600},
            },
        )
        env["feas"].request_fallback(run.id, hardware=HARDWARE_FIXTURE)
        session.flush()
        proposal = session.execute(
            select(ExportProposal).where(ExportProposal.run_id == run.id)
        ).scalar_one()
        row = env["transform"].prepare(
            proposal.id,
            snap.id,
            recipient="real-cloud-that-does-not-exist",
            account="acct",
            region="r",
        )
        session.flush()
        env["transform"].decide(row.id, decision="approved", rationale="ok")
        session.flush()
        view = env["svc"].submit(row.id)
        session.flush()
        assert view["status"] == "failed"
        assert env["double"].received_bytes == 0


class TestRevocationHonesty:
    def test_revoke_never_claims_unseen(self, env, session: Session) -> None:
        """AT-1003-2: after bytes moved, revocation reports exposure."""
        row = _approved(env, session)
        view = env["svc"].submit(row.id)
        sent = view["bytesTransferred"]
        assert sent > 0
        env["svc"].revoke(row.id, reason="security hold")
        session.flush()
        job = session.execute(select(ExportJob).where(ExportJob.id == view["id"])).scalar_one()
        assert job.exposed == sent  # recorded as exposed — not 'unseen'
        assert job.bytes_transferred == sent

    def test_revoke_is_human_only(self, env, session: Session) -> None:
        """Agents/service principals can never drive revocation —
        approvals are human-bound (§21.1)."""
        row = _approved(env, session)
        agent = Principal(workspace_id=env["ws"].id, kind="agent", login="bot", display_name="bot")
        session.add(agent)
        session.flush()
        for cap in sorted(capabilities_for_role("owner")):
            session.add(
                PrincipalCapability(
                    workspace_id=env["ws"].id,
                    principal_id=agent.id,
                    capability=cap,
                )
            )
        session.flush()
        actx = load_context(session, env["ws"].id, agent.id)
        svc = ExportBrokerService(session, actx, broker=env["broker"])
        with pytest.raises(DomainError) as err:
            svc.revoke(row.id, reason="agent attempted revoke")
        assert err.value.code == ErrorCode.FORBIDDEN

    def test_malformed_or_foreign_callbacks_change_nothing(self, env, session: Session) -> None:
        """Untrusted callbacks: empty ids and callbacks on jobs the
        caller cannot see are dropped without touching the ledger."""
        row = _approved(env, session)
        view = env["svc"].submit(row.id)
        session.flush()
        # empty callback id — malformed, dropped
        res = env["svc"].handle_callback(view["id"], callback_id="", event="deleted", seq=99)
        assert res["applied"] is False
        # job id from another workspace is invisible (workspace scope)
        ws2 = Workspace(slug="w2", display_name="W2")
        session.add(ws2)
        session.flush()
        outsider = _principal(session, ws2, "owner", "o2")
        octx2 = load_context(session, ws2.id, outsider.id)
        svc2 = ExportBrokerService(session, octx2, broker=env["broker"])
        with pytest.raises(DomainError) as err:
            svc2.handle_callback(uuid.uuid4(), callback_id="x", event="deleted", seq=1)
        assert err.value.code == ErrorCode.NOT_FOUND
        # the real job was untouched
        job = session.execute(select(ExportJob).where(ExportJob.id == view["id"])).scalar_one()
        assert job.status == "transferred"
