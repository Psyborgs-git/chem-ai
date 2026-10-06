"""CS-1002 integration tests — minimal transformed payload + review.

AT-1002-3  transformation version changes → digest mismatch
           invalidates a reused approval (the approvals ledger binds
           the exact payload+transformation digest).

Plus the end-to-end surface: prepare → exact payload + redaction +
residual-risk + manifest; dedupe by bound digest; export-rights and
drift gates; review/approve capability checks; reviewed classification
changes re-binding the digest.
"""

from __future__ import annotations

import uuid

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import load_context
from studio.domain.learning.datasets import DatasetService
from studio.domain.learning.exports.transform import TransformService
from studio.domain.runs.admission import AdmissionService
from studio.domain.runs.feasibility import FeasibilityService
from studio.domain.runs.queue import RunService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Artifact,
    DatasetSnapshot,
    EvidenceClaim,
    ExportProposal,
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


def _measurement(
    session: Session,
    ctx,
    task: ResearchTask,
    *,
    metric: str = "metric.tack-4h",
    value: dict | None = None,
    conditions: dict | None = None,
) -> Measurement:
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
        metric=metric,
        repeat_type="independent_batch",
        value_type="numeric",
        value=value or {"kind": "numeric", "value": "5", "unit": "dimensionless"},
        conditions=conditions or {"actual": {"temperature": 296.15}},
        status="accepted",
    )
    session.add(m)
    session.flush()
    return m


def _supplier_claim(
    session: Session,
    ctx,
    *,
    rights: dict,
    statement: dict | None = None,
) -> EvidenceClaim:
    art = Artifact(
        workspace_id=ctx.workspace_id,
        storage_key="aa/" + "a" * 62,
        media_type="text/csv",
        byte_size=4,
        checksum_sha256="a" * 64,
        original_name="supplier.csv",
        rights=rights,
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
        statement=statement or {"claim": "viscosity 900 mPa·s"},
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
        capacity={"cpu_cores": 8, "memory_bytes": 16 * GB, "gpu_devices": 0, "concurrency": 1},
        reserve={"memory_bytes": 2 * GB},
    )
    session.flush()
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
        "svc": TransformService(session, octx),
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
    """A workspace with a material name, one measurement with process
    conditions + a compositional value, and one supplier claim carrying
    a hidden metadata field."""
    session.add(
        MaterialIdentity(
            workspace_id=env["ws"].id,
            kind="commercial_mixture",
            name="AcmeBond 3000",
            identifiers=[{"scheme": "supplier_sku", "value": "AB-3000", "source": "supplier"}],
            aliases=["AB3"],
        )
    )
    _measurement(
        session,
        env["octx"],
        task,
        value={
            "kind": "numeric",
            "value": "4.2",
            "unit": "MPa",
            "parts": {"resin": 55.0, "hardener": 45.0},
        },
        conditions={"actual": {"temperature": 296.15, "rpm": 300}},
    )
    _supplier_claim(
        session,
        env["octx"],
        rights={"training": "allowed", "export": "allowed"},
        statement={
            "claim": "AcmeBond 3000 reached viscosity 900 mPa·s",
            "recorded_by": "jdoe",
        },
    )


class TestPrepare:
    def test_minimal_payload_and_manifest(self, env, session: Session) -> None:
        task = _task(session, env["octx"])
        _seed(env, session, task)
        snap = _frozen_snapshot(env, session, task)
        proposal = _proposal(env, session)

        row = env["svc"].prepare(
            proposal.id,
            snap.id,
            recipient="acme-collab",
            region="eu",
            retention_expectation="review only",
            deletion_expectation="delete after 30d",
            max_records=100,
        )
        session.flush()

        # Exact payload: allowlisted fields only, aliases not names.
        doc = row.payload
        assert doc["version"] == "export-payload/v1"
        assert doc["transformationVersion"] == "export-transform/v1"
        assert len(doc["records"]) == 2
        by_kind = {r["kind"]: r for r in doc["records"]}
        meas = by_kind["measurement"]["fields"]
        assert set(meas) == {"metric", "method", "valueType", "value", "conditions"}
        assert meas["metric"] == "m-0001"  # metric name aliased
        claim = by_kind["claim"]["fields"]
        assert set(claim) == {"sourceClass", "labelKind", "subject", "statement", "conditions"}
        # The hidden metadata key is gone from the payload (AT-1002-2).
        assert "recorded_by" not in canonical_doc(doc)
        assert "jdoe" not in canonical_doc(doc)
        # The material name is aliased inside free text; the original
        # never leaves the vault.
        assert "AcmeBond" not in canonical_doc(doc)
        assert "mat-" in canonical_doc(doc)
        # ...but the LOCAL map can decode it.
        originals = {v["original"] for v in row.local_alias_map.values()}
        assert "AcmeBond 3000" in originals

        # §20.2 manifest fields.
        m = row.manifest
        assert m["version"] == "export-manifest/v1"
        assert m["payload"]["digest"] == row.payload_digest
        assert m["snapshot"]["digest"] == snap.digest
        assert m["recipient"] == {"provider": "acme-collab", "account": None, "region": "eu"}
        assert m["permittedJob"]["operation"] == "large dft batch"
        assert m["limits"] == {"maxRecords": 100, "maxBytes": 4194304}
        assert m["retention"]["expectation"] == "review only"
        assert m["egress"] == "deny"
        assert m["approver"] is None
        assert row.bound_digest and len(row.bound_digest) == 64

        # Classification preserved from source artifact (default
        # classification column → 'internal' unless set) — never
        # downgraded silently.
        assert row.classification == row.source_classification

        # Idempotent: identical inputs reuse the row.
        again = env["svc"].prepare(
            proposal.id,
            snap.id,
            recipient="acme-collab",
            region="eu",
            retention_expectation="review only",
            deletion_expectation="delete after 30d",
            max_records=100,
        )
        assert again.id == row.id

        view = env["svc"].review_view(proposal.id)
        assert view["payload"]["id"] == str(row.id)
        assert view["payload"]["document"] == doc
        assert view["residual"]["anonymous"] is False
        assert view["approval"]["state"] == "none"
        assert view["alias"]["localOnly"] is True
        assert view["capabilities"]["canApprove"] is True
        assert view["egress"] == "deny"

    def test_export_rights_unresolved_excludes_claim(self, env, session: Session) -> None:
        task = _task(session, env["octx"])
        # Supplier sheet grants training but says nothing about export.
        _supplier_claim(session, env["octx"], rights={"training": "allowed"})
        _measurement(session, env["octx"], task)
        snap = _frozen_snapshot(env, session, task)
        proposal = _proposal(env, session)

        row = env["svc"].prepare(proposal.id, snap.id)
        assert [r["kind"] for r in row.payload["records"]] == ["measurement"]
        excluded = row.redaction_report["excludedEntries"]
        assert excluded == [
            {
                "recordId": str(_claim_id(session)),
                "recordKind": "claim",
                "reason": "export_rights_unresolved",
            }
        ]

    def test_drift_refuses_prepare(self, env, session: Session) -> None:
        task = _task(session, env["octx"])
        m = _measurement(session, env["octx"], task)
        snap = _frozen_snapshot(env, session, task)
        proposal = _proposal(env, session)
        m.value = {"kind": "numeric", "value": "9", "unit": "dimensionless"}
        session.flush()
        with pytest.raises(DomainError) as exc:
            env["svc"].prepare(proposal.id, snap.id)
        assert exc.value.code == ErrorCode.CONFLICT
        assert "drift" in exc.value.message

    def test_unfrozen_snapshot_refused(self, env, session: Session) -> None:
        task = _task(session, env["octx"])
        _measurement(session, env["octx"], task)
        snap = env["datasets"].build("property_prediction", "draft-snap", task.id)
        session.flush()
        proposal = _proposal(env, session)
        with pytest.raises(DomainError) as exc:
            env["svc"].prepare(proposal.id, snap.id)
        assert exc.value.code == ErrorCode.CONFLICT

    def test_record_limit_enforced(self, env, session: Session) -> None:
        task = _task(session, env["octx"])
        _measurement(session, env["octx"], task)
        _supplier_claim(session, env["octx"], rights={"training": "allowed", "export": "allowed"})
        snap = _frozen_snapshot(env, session, task)
        proposal = _proposal(env, session)
        with pytest.raises(DomainError) as exc:
            env["svc"].prepare(proposal.id, snap.id, max_records=1)
        assert exc.value.code == ErrorCode.VALIDATION

    def test_prepare_requires_review_export(self, env, session: Session) -> None:
        """A researcher can trigger feasibility but cannot prepare or
        review an export payload."""
        task = _task(session, env["octx"])
        _measurement(session, env["octx"], task)
        snap = _frozen_snapshot(env, session, task)
        proposal = _proposal(env, session)
        rsvc = TransformService(session, env["rctx"])
        with pytest.raises(DomainError) as exc:
            rsvc.prepare(proposal.id, snap.id)
        assert exc.value.code == ErrorCode.FORBIDDEN
        with pytest.raises(DomainError):
            rsvc.review_view(proposal.id)


class TestApprovalBinding:
    def test_at_1002_3_version_bump_invalidates_approval(self, env, session: Session) -> None:
        """Approve the exact payload+transformation digest, rebuild
        under a new transformation version → the reused approval fails
        APPROVAL_STALE; the v1 approval still validates against v1."""
        task = _task(session, env["octx"])
        _seed(env, session, task)
        snap = _frozen_snapshot(env, session, task)
        proposal = _proposal(env, session)

        v1 = env["svc"].prepare(proposal.id, snap.id)
        approval = env["svc"].decide(v1.id, decision="approved", rationale="looks fine")
        session.flush()
        assert approval.bound_digest == v1.bound_digest
        assert env["svc"].validate_approval(v1.id).id == approval.id
        assert env["svc"].review_view(proposal.id)["approval"]["state"] == "approved"

        v2 = env["svc"].prepare(proposal.id, snap.id, transformation_version="export-transform/v2")
        assert v2.id != v1.id
        assert v2.bound_digest != v1.bound_digest
        assert v2.payload_digest != v1.payload_digest

        with pytest.raises(DomainError) as exc:
            env["svc"].validate_approval(v2.id)
        assert exc.value.code == ErrorCode.APPROVAL_STALE
        assert env["svc"].review_view(proposal.id)["approval"]["state"] == "stale"
        # The v1 approval still binds the v1 row.
        assert env["svc"].validate_approval(v1.id).id == approval.id

    def test_rejected_and_revoked_states(self, env, session: Session) -> None:
        task = _task(session, env["octx"])
        _measurement(session, env["octx"], task)
        snap = _frozen_snapshot(env, session, task)
        proposal = _proposal(env, session)
        row = env["svc"].prepare(proposal.id, snap.id)
        env["svc"].decide(row.id, decision="rejected", rationale="too much detail")
        session.flush()
        view = env["svc"].review_view(proposal.id)
        assert view["approval"]["state"] == "rejected"
        assert (
            session.execute(
                select(ExportProposal.status).where(ExportProposal.id == proposal.id)
            ).scalar_one()
            == "rejected"
        )
        with pytest.raises(DomainError) as exc:
            env["svc"].validate_approval(row.id)
        assert exc.value.code == ErrorCode.FORBIDDEN

    def test_classification_review_rebinds_digest(self, env, session: Session) -> None:
        task = _task(session, env["octx"])
        _measurement(session, env["octx"], task)
        snap = _frozen_snapshot(env, session, task)
        proposal = _proposal(env, session)
        row = env["svc"].prepare(proposal.id, snap.id)
        env["svc"].decide(row.id, decision="approved")
        approved_digest = row.bound_digest

        changed = env["svc"].set_classification(
            row.id, classification="restricted", rationale="supplier data inside"
        )
        session.flush()
        assert changed.classification == "restricted"
        assert changed.source_classification == row.source_classification
        assert changed.classification_review["from"] == row.source_classification
        assert changed.bound_digest != approved_digest
        # Prior approval no longer binds — the digest changed.
        with pytest.raises(DomainError) as exc:
            env["svc"].validate_approval(row.id)
        assert exc.value.code == ErrorCode.APPROVAL_STALE

    def test_classification_review_needs_rationale(self, env, session: Session) -> None:
        task = _task(session, env["octx"])
        _measurement(session, env["octx"], task)
        snap = _frozen_snapshot(env, session, task)
        proposal = _proposal(env, session)
        row = env["svc"].prepare(proposal.id, snap.id)
        with pytest.raises(DomainError) as exc:
            env["svc"].set_classification(row.id, classification="restricted", rationale=" ")
        assert exc.value.code == ErrorCode.VALIDATION

    def test_fallback_view_reflects_payload_approval(self, env, session: Session) -> None:
        """The fallback card's ``approved`` flag follows the payload
        approval — a stale bound digest must not report approved."""
        task = _task(session, env["octx"])
        _measurement(session, env["octx"], task)
        snap = _frozen_snapshot(env, session, task)
        proposal = _proposal(env, session)
        feas = env["feas"]

        def flag() -> bool:
            return feas.fallback_view(proposal.run_id)["proposal"]["approved"]

        assert flag() is False
        row = env["svc"].prepare(proposal.id, snap.id)
        assert flag() is False
        env["svc"].decide(row.id, decision="approved")
        session.flush()
        assert flag() is True
        # Re-binding the digest (new transformation version) invalidates
        # the approval — the flag goes back to False, matching the
        # review page's 'stale' state.
        env["svc"].prepare(proposal.id, snap.id, transformation_version="export-transform/v2")
        assert flag() is False


def _claim_id(session: Session) -> uuid.UUID:
    return session.execute(select(EvidenceClaim.id)).scalars().first()


def canonical_doc(doc: dict) -> str:
    import json

    return json.dumps(doc, sort_keys=True)
