"""CS-0504 — task report composer + experiment outcomes in session
manifests (§11, §25).

The report is a review aid: hypotheses, measurements, contradictions,
unknowns, review scope — with explicit mode limitations and the
fixture-only label. A failed/stopped execution must surface in the
next session's manifest so the failure cause informs the task
(AT-0504-3 backend leg).
"""

from __future__ import annotations

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext, load_context
from studio.domain.lab.plans import LabPlanService
from studio.domain.tasks.memory import TaskMemoryService
from studio.domain.tasks.report import TaskReportService
from studio.persistence.models import (
    CandidateRevision,
    LabBatch,
    LabExecution,
    LabSample,
    Measurement,
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    SuccessContractRevision,
    TaskQuestion,
    Workspace,
)

pytestmark = pytest.mark.integration


def _principal(session: Session, ws: Workspace, kind: str, role: str, login: str) -> Principal:
    p = Principal(workspace_id=ws.id, kind=kind, login=login, display_name=login)
    session.add(p)
    session.flush()
    for cap in sorted(capabilities_for_role(role)):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=p.id, capability=cap))
    session.flush()
    return p


def _ctx(session: Session, ws: Workspace, p: Principal) -> ServiceContext:
    return load_context(session, ws.id, p.id)


@pytest.fixture()
def ctx(session: Session) -> ServiceContext:
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    return _ctx(session, ws, _principal(session, ws, "user", "researcher", "r"))


def _task(session: Session, ctx: ServiceContext, mode: str = "discover") -> ResearchTask:
    proj = Project(workspace_id=ctx.workspace_id, slug="p", name="P")
    session.add(proj)
    session.flush()
    task = ResearchTask(
        workspace_id=ctx.workspace_id,
        project_id=proj.id,
        mode=mode,
        title="t",
        workflow_state="active",
        target_kind="formulation",
        objective="o",
    )
    session.add(task)
    session.flush()
    contract = SuccessContractRevision(
        workspace_id=ctx.workspace_id,
        task_id=task.id,
        revision=1,
        status="frozen",
        payload={
            "metrics": [
                {
                    "id": "m.idx",
                    "label": "index",
                    "required": True,
                    "operator": "gte",
                    "target_values": ["5"],
                    "unit": "dimensionless",
                    "required_evidence": ["lab_measurement"],
                }
            ],
            "hard_constraints": [],
        },
        content_hash="x",
    )
    session.add(contract)
    session.flush()
    task.current_contract_revision_id = contract.id
    session.flush()
    return task


def _execution(
    session: Session,
    ctx: ServiceContext,
    task: ResearchTask,
    *,
    status: str = "in_progress",
    observations: str | None = None,
) -> LabExecution:
    ex = LabExecution(
        workspace_id=ctx.workspace_id,
        task_id=task.id,
        status=status,
        observations=observations,
    )
    session.add(ex)
    session.flush()
    return ex


def _sample(session: Session, ctx: ServiceContext, ex: LabExecution) -> LabSample:
    batch = LabBatch(workspace_id=ctx.workspace_id, execution_id=ex.id, label="A")
    session.add(batch)
    session.flush()
    s = LabSample(workspace_id=ctx.workspace_id, batch_id=batch.id, label="a1", kind="aliquot")
    session.add(s)
    session.flush()
    return s


class TestTaskReport:
    def test_report_composition(self, session: Session, ctx: ServiceContext) -> None:
        task = _task(session, ctx, mode="match_reference")
        task.mode_inputs = {"matchScope": "functional", "referenceProductId": "rp-1"}
        session.flush()
        cand = CandidateRevision(
            workspace_id=ctx.workspace_id,
            task_id=task.id,
            revision=1,
            status="accepted_for_research",
            entity_kind="formulation",
            payload={"hypothesis": "solvent swap"},
            content_hash="h1",
        )
        session.add(cand)
        session.flush()
        plan = LabPlanService(session, ctx).create(
            task.id, title="m", payload={"candidateRevisionId": str(cand.id)}
        )
        ex = _execution(session, ctx, task)
        ex.plan_id = plan.id
        sample = _sample(session, ctx, ex)
        session.add(
            Measurement(
                workspace_id=ctx.workspace_id,
                sample_id=sample.id,
                method="fixture-index",
                metric="m.idx",
                repeat_type="independent_batch",
                value_type="numeric",
                value={"kind": "numeric", "value": "7", "unit": "dimensionless"},
                status="accepted",
            )
        )
        session.add(
            Measurement(
                workspace_id=ctx.workspace_id,
                sample_id=sample.id,
                method="other",
                repeat_type="same_sample",
                value_type="numeric",
                value={"kind": "numeric", "value": "1", "unit": "dimensionless"},
                status="proposed",
            )
        )
        session.add(
            TaskQuestion(
                workspace_id=ctx.workspace_id,
                task_id=task.id,
                question="which lot?",
                status="open",
                blocking=True,
            )
        )
        session.flush()

        r = TaskReportService(session, ctx).report(task.id)

        assert r["task"]["mode"] == "match_reference"
        assert r["contract"]["status"] == "frozen"
        assert r["evaluation"]["metrics"][0]["verdict"] == "met"
        assert r["hypotheses"][0]["hypothesis"] == "solvent swap"
        assert r["measurements"]["acceptedCount"] == 1
        assert r["measurements"]["attributedCount"] == 1
        assert r["measurements"]["byStatus"] == {"accepted": 1, "proposed": 1}
        # blocking question + nothing else
        assert any("which lot?" in u for u in r["unknowns"])
        # match mode states its honest limit — no identity claims
        assert any("composition or identity" in lim for lim in r["limitations"])
        assert any("fixture-only" in lim for lim in r["limitations"])
        assert r["reviewScope"]["pendingReviewMeasurements"] == 1

    def test_failed_execution_surfaces_in_manifest(
        self, session: Session, ctx: ServiceContext
    ) -> None:
        """AT-0504-3 leg: a stopped execution with observations lands in
        the next session's manifest — failure cause informs the task."""
        task = _task(session, ctx)
        _execution(
            session,
            ctx,
            task,
            status="stopped",
            observations="phase separation at 40C",
        )
        session.flush()

        manifest_items, _ = TaskMemoryService(session, ctx).collect_items(task)
        kinds = {i.kind for i in manifest_items}
        assert "experiment_outcome" in kinds
        outcome = next(i for i in manifest_items if i.kind == "experiment_outcome")
        assert "phase separation" in outcome.text
        assert "stopped" in outcome.text
