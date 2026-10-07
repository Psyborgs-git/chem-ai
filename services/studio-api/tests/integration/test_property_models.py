"""CS-0604 AT-0604-3 — insufficient real data → ``not_ready``.

The capability report carries coverage and exclusion counts with
reasons, read from the frozen snapshot manifest and live lineage —
it never returns a trained predictor."""

from __future__ import annotations

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext, load_context
from studio.domain.learning.datasets import DatasetService
from studio.domain.learning.property_models import PropertyModelService
from studio.errors import DomainError
from studio.persistence.models import (
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

# PAR-05: the method name itself is a provenance marker — a
# "fixture-*" method derives synthetic_fixture and is excluded from
# readiness as fixture evidence; these records model real measured
# outcomes (historical_report via the historical execution flag).
TARGET = {"name": "metric.x", "method": "assay-method", "unit": "dimensionless"}


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
    metric: str = "metric.x",
    method: str = "assay-method",
    unit: str = "dimensionless",
    value: str = "5",
    execution: LabExecution | None = None,
    batch: LabBatch | None = None,
) -> Measurement:
    if execution is None:
        execution = LabExecution(
            workspace_id=ctx.workspace_id,
            task_id=task.id,
            status="in_progress",
            historical=True,
        )
        session.add(execution)
        session.flush()
    if batch is None:
        batch = LabBatch(workspace_id=ctx.workspace_id, execution_id=execution.id, label="A")
        session.add(batch)
        session.flush()
    sample = LabSample(workspace_id=ctx.workspace_id, batch_id=batch.id, label="a1", kind="aliquot")
    session.add(sample)
    session.flush()
    m = Measurement(
        workspace_id=ctx.workspace_id,
        sample_id=sample.id,
        method=method,
        metric=metric,
        repeat_type="independent_batch",
        value_type="numeric",
        value={"kind": "numeric", "value": value, "unit": unit},
        status="accepted",
    )
    session.add(m)
    session.flush()
    return m


class TestInsufficientData:
    """AT-0604-3: readiness reports not_ready, never a predictor."""

    def test_single_group_not_ready(self, session: Session, ctx: ServiceContext) -> None:
        task = _task(session, ctx)
        # Two measurements sharing one batch/execution = ONE lineage
        # group: a held-out partition cannot exist.
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
        _measurement(session, ctx, task, value="5", batch=batch)
        _measurement(session, ctx, task, value="6", batch=batch)
        svc = DatasetService(session, ctx)
        snap = svc.build("property_prediction", "ds", task_id=task.id)
        svc.freeze(snap.id)

        report = PropertyModelService(session, ctx).readiness(snap.id, target=TARGET)
        assert report["capability"] == "not_ready"
        assert "insufficient_groups" in report["blockers"]
        # Real coverage numbers — two eligible labeled examples,
        # one distinct lineage group. Not fabricated, not a model.
        assert report["coverage"]["eligible"] == 2
        assert report["coverage"]["labeled"] == 2
        assert report["coverage"]["distinctGroups"] == 1
        assert "model" not in report and "predictor" not in report
        assert report["snapshotId"] == str(snap.id)
        assert report["snapshotImmutable"] is True

    def test_target_mismatch_counted_as_exclusion(
        self, session: Session, ctx: ServiceContext
    ) -> None:
        task = _task(session, ctx)
        _measurement(session, ctx, task, metric="metric.other")
        svc = DatasetService(session, ctx)
        snap = svc.build("property_prediction", "ds", task_id=task.id)
        svc.freeze(snap.id)

        report = PropertyModelService(session, ctx).readiness(snap.id, target=TARGET)
        assert report["capability"] == "not_ready"
        assert "no_labeled_examples" in report["blockers"]
        # The out-of-scope record is an exclusion with a reason —
        # coverage never invents it as usable.
        assert report["exclusions"]["target_mismatch"] == 1
        assert report["coverage"]["labeled"] == 0

    def test_not_frozen_snapshot_reports_blocker(
        self, session: Session, ctx: ServiceContext
    ) -> None:
        task = _task(session, ctx)
        _measurement(session, ctx, task)
        svc = DatasetService(session, ctx)
        snap = svc.build("property_prediction", "ds", task_id=task.id)

        report = PropertyModelService(session, ctx).readiness(snap.id, target=TARGET)
        assert report["capability"] == "not_ready"
        assert report["blockers"] == ["snapshot_not_frozen"]

    def test_drifted_snapshot_reports_blocker(self, session: Session, ctx: ServiceContext) -> None:
        task = _task(session, ctx)
        m = _measurement(session, ctx, task)
        svc = DatasetService(session, ctx)
        snap = svc.build("property_prediction", "ds", task_id=task.id)
        svc.freeze(snap.id)
        session.refresh(m)
        m.status = "superseded"
        session.flush()

        report = PropertyModelService(session, ctx).readiness(snap.id, target=TARGET)
        assert report["capability"] == "not_ready"
        assert report["blockers"] == ["source_drift"]
        assert report["drift"]["changed"] == [str(m.id)]

    def test_readiness_requires_manage_models(self, session: Session, ctx: ServiceContext) -> None:
        ws = session.get(Workspace, ctx.workspace_id)
        viewer = _principal(session, ws, "viewer", "v")
        vctx = load_context(session, ws.id, viewer.id)
        with pytest.raises(DomainError):
            PropertyModelService(session, vctx).readiness(ws.id, target=TARGET)
