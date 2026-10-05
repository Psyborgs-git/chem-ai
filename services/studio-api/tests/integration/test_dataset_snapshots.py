"""CS-0601 — dataset snapshots and training eligibility (§17.2).

AT-0601-1  supplier claims and lab values mixed in a property dataset
           → source classes and permitted labels remain distinct
AT-0601-2  rights unknown for training → freeze blocked with
           DATA_RIGHTS_UNKNOWN naming the affected records
AT-0601-3  source revision changes after freeze → run preparation
           detects digest drift; the signed manifest stays immutable
"""

from __future__ import annotations

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext, load_context
from studio.domain.learning.datasets import DatasetService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Artifact,
    EvidenceClaim,
    ExtractedRecord,
    ImportBatch,
    LabBatch,
    LabExecution,
    LabSample,
    Measurement,
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    Workspace,
)

pytestmark = pytest.mark.integration


def _principal(session: Session, ws: Workspace, role: str, login: str) -> Principal:
    p = Principal(workspace_id=ws.id, kind="user", login=login, display_name=login)
    session.add(p)
    session.flush()
    for cap in sorted(capabilities_for_role(role)):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=p.id, capability=cap))
    session.flush()
    return p


@pytest.fixture()
def ctx(session: Session) -> ServiceContext:
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    owner = _principal(session, ws, "owner", "o")
    return load_context(session, ws.id, owner.id)


def _task(session: Session, ctx: ServiceContext) -> ResearchTask:
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
    ctx: ServiceContext,
    task: ResearchTask,
    *,
    value_type: str = "numeric",
    value: dict | None = None,
    status: str = "accepted",
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
        metric="metric.x",
        repeat_type="independent_batch",
        value_type=value_type,
        value=value or {"kind": "numeric", "value": "5", "unit": "dimensionless"},
        status=status,
    )
    session.add(m)
    session.flush()
    return m


def _supplier_claim(
    session: Session, ctx: ServiceContext, *, training_rights: str
) -> EvidenceClaim:
    """A document claim from an imported supplier sheet."""
    art = Artifact(
        workspace_id=ctx.workspace_id,
        storage_key="aa/" + "a" * 62,
        media_type="text/csv",
        byte_size=4,
        checksum_sha256="a" * 64,
        original_name="supplier.csv",
        rights={"training": training_rights},
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
        original_text="supplier says viscosity 900",
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
        statement={"claim": "viscosity 900 mPa·s"},
        source_batch_id=batch.id,
        source_record_id=rec.id,
    )
    session.add(claim)
    session.flush()
    return claim


class TestSourceClasses:
    """AT-0601-1."""

    def test_classes_and_labels_distinct(self, session: Session, ctx: ServiceContext) -> None:
        task = _task(session, ctx)
        _measurement(session, ctx, task)
        _supplier_claim(session, ctx, training_rights="allowed")

        svc = DatasetService(session, ctx)
        snap = svc.build("property_prediction", "ds", task_id=task.id)
        by_kind = {e["recordKind"]: e for e in snap.manifest["entries"]}

        assert by_kind["measurement"]["sourceClass"] == "lab_measurement"
        assert by_kind["measurement"]["labelKind"] == "measured_value"
        assert by_kind["measurement"]["rightsTraining"] == "owned"
        assert by_kind["claim"]["sourceClass"] == "document_claim"
        assert by_kind["claim"]["labelKind"] == "claimed_value"
        assert by_kind["claim"]["rightsTraining"] == "allowed"

    def test_missing_and_censored_semantics_retained(
        self, session: Session, ctx: ServiceContext
    ) -> None:
        task = _task(session, ctx)
        _measurement(
            session,
            ctx,
            task,
            value_type="missing",
            value={"kind": "missing", "reason": "instrument_failure"},
        )
        svc = DatasetService(session, ctx)
        snap = svc.build("property_prediction", "ds", task_id=task.id)
        entry = snap.manifest["entries"][0]
        assert entry["excluded"] is True
        assert entry["exclusionReason"] == "value_type:missing"
        assert entry["semantics"]["missingReason"] == "instrument_failure"


class TestFreezeRights:
    """AT-0601-2."""

    def test_unknown_rights_block_freeze(self, session: Session, ctx: ServiceContext) -> None:
        _task(session, ctx)
        _supplier_claim(session, ctx, training_rights="unknown")
        svc = DatasetService(session, ctx)
        snap = svc.build("property_prediction", "ds")
        with pytest.raises(DomainError) as ei:
            svc.freeze(snap.id)
        assert ei.value.code == ErrorCode.DATA_RIGHTS_UNKNOWN
        assert ei.value.safe_details["recordIds"]

    def test_allowed_rights_freeze(self, session: Session, ctx: ServiceContext) -> None:
        _task(session, ctx)
        _supplier_claim(session, ctx, training_rights="allowed")
        svc = DatasetService(session, ctx)
        snap = svc.build("property_prediction", "ds")
        frozen = svc.freeze(snap.id)
        assert frozen.state == "frozen"
        assert frozen.frozen_by == ctx.principal_id

    def test_build_requires_capability(self, session: Session, ctx: ServiceContext) -> None:
        ws = session.get(Workspace, ctx.workspace_id)
        viewer = _principal(session, ws, "viewer", "v")
        vctx = load_context(session, ws.id, viewer.id)
        with pytest.raises(DomainError):
            DatasetService(session, vctx).build("property_prediction", "ds")


class TestDrift:
    """AT-0601-3."""

    def test_source_change_detected_after_freeze(
        self, session: Session, ctx: ServiceContext
    ) -> None:
        task = _task(session, ctx)
        m = _measurement(session, ctx, task)
        svc = DatasetService(session, ctx)
        snap = svc.build("property_prediction", "ds", task_id=task.id)
        svc.freeze(snap.id)

        ready = svc.prepare_run(snap.id)
        assert ready["ok"] is True

        # Source changes after freeze (via amendment-style status flip).
        session.refresh(m)
        m.status = "superseded"
        session.flush()

        drift = svc.drift_status(snap.id)
        assert drift["drift"] is True
        assert str(m.id) in drift["changed"]

        run = svc.prepare_run(snap.id)
        assert run["ok"] is False
        assert run["reason"] == "source_drift"

        # The signed manifest is immutable — still carries the old hash.
        session.refresh(snap)
        assert snap.state == "frozen"
        entry = snap.manifest["entries"][0]
        assert entry["hash"] != ""
        assert entry["semantics"]["status"] == "accepted"

    def test_prepare_requires_frozen(self, session: Session, ctx: ServiceContext) -> None:
        task = _task(session, ctx)
        _measurement(session, ctx, task)
        svc = DatasetService(session, ctx)
        snap = svc.build("property_prediction", "ds", task_id=task.id)
        with pytest.raises(DomainError):
            svc.prepare_run(snap.id)
