"""CS-0503 — per-metric evaluator and task closeout (§7.1, §12.3).

AT-0503-3  all fixture criteria pass + reviewer approves → the closure
           packet binds candidate/contract/evidence revisions and the
           fixture-only status; a later amendment marks reassessment
           without rewriting the signed packet.
"""

from __future__ import annotations

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext, load_context
from studio.domain.lab.measurements import LabMeasurementService
from studio.domain.tasks.evaluation import TaskEvaluationService
from studio.domain.tasks.service import TaskService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    LabBatch,
    LabExecution,
    LabSample,
    Measurement,
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    SuccessContractRevision,
    TaskDecision,
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
def ctxs(session: Session) -> tuple[ServiceContext, ServiceContext]:
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    res = _principal(session, ws, "user", "researcher", "res")
    sr = _principal(session, ws, "user", "scientific_reviewer", "sr")
    return _ctx(session, ws, res), _ctx(session, ws, sr)


def _task(session: Session, res: ServiceContext) -> ResearchTask:
    proj = Project(workspace_id=res.workspace_id, slug="p", name="P")
    session.add(proj)
    session.flush()
    task = ResearchTask(
        workspace_id=res.workspace_id,
        project_id=proj.id,
        mode="improve",
        title="t",
        workflow_state="awaiting_review",
        target_kind="formulation",
        objective="o",
    )
    session.add(task)
    session.flush()
    contract = SuccessContractRevision(
        workspace_id=res.workspace_id,
        task_id=task.id,
        revision=1,
        status="frozen",
        payload={
            "metrics": [
                {
                    "id": "metric.synthetic-performance",
                    "label": "Synthetic test-only index",
                    "required": True,
                    "operator": "gte",
                    "target_values": ["5"],
                    "unit": "dimensionless",
                    "required_evidence": ["lab_measurement"],
                    "aggregation": "fixture-single-value",
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


def _accepted_measurement(
    session: Session, res: ServiceContext, task: ResearchTask, value: str
) -> Measurement:
    ex = LabExecution(
        workspace_id=res.workspace_id,
        task_id=task.id,
        status="in_progress",
        historical=True,
    )
    session.add(ex)
    session.flush()
    batch = LabBatch(workspace_id=res.workspace_id, execution_id=ex.id, label="A")
    session.add(batch)
    session.flush()
    sample = LabSample(workspace_id=res.workspace_id, batch_id=batch.id, label="a1", kind="aliquot")
    session.add(sample)
    session.flush()
    m = Measurement(
        workspace_id=res.workspace_id,
        sample_id=sample.id,
        method="fixture-index",
        metric="metric.synthetic-performance",
        repeat_type="independent_batch",
        value_type="numeric",
        value={"kind": "numeric", "value": value, "unit": "dimensionless"},
        status="accepted",
    )
    session.add(m)
    session.flush()
    return m


class TestCloseout:
    def test_full_cycle_packet_and_reassessment(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """AT-0503-3: fixture criteria pass → packet binds revisions +
        fixture-only; amendment marks reassessment; packet unchanged."""
        res, sr = ctxs
        task = _task(session, res)
        m = _accepted_measurement(session, res, task, "6")

        ev = TaskEvaluationService(session, sr)
        report = ev.evaluate(task.id)
        assert report["metrics"][0]["verdict"] == "met"
        assert report["suggestedDecision"] == "supported_success"
        assert report["supportedSuccessEligible"] is True

        packet = ev.closeout_packet(task.id)
        assert packet["contractRevisionId"] == str(task.current_contract_revision_id)
        assert packet["evidenceIds"] == [str(m.id)]
        assert packet["fixtureOnly"] is True
        assert packet["scientificValidation"] == "not_validated"

        closed = TaskService(session, sr).close(
            task_id=task.id,
            closure_decision="supported_success",
            packet=packet,
        )
        assert closed.workflow_state == "closed"
        assert closed.closure_decision == "supported_success"

        decision = session.execute(
            select(TaskDecision).where(
                TaskDecision.task_id == task.id, TaskDecision.kind == "closure"
            )
        ).scalar_one()
        stored = decision.payload["packet"]
        assert stored["contractRevisionId"] == packet["contractRevisionId"]
        assert stored["evidenceIds"] == [str(m.id)]

        # an accepted measurement may only be corrected via amendment —
        # and that marks the bound packet for reassessment (§12.3)
        assert ev.reassessment_status(task.id)["needsReassessment"] is False
        LabMeasurementService(session, sr).amend(
            m.id,
            reason="transcription error",
            value={"kind": "numeric", "value": "4", "unit": "dimensionless"},
        )
        status = ev.reassessment_status(task.id)
        assert status["needsReassessment"] is True
        assert status["staleEvidenceIds"][0]["status"] == "superseded"
        # the signed packet itself is untouched
        session.refresh(decision)
        assert decision.payload["packet"]["evidenceIds"] == [str(m.id)]

    def test_unmeasured_metric_blocks_supported_success(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """Evaluator suggestion is inconclusive and the close gate
        refuses supported_success with the unmet metric listed."""
        res, sr = ctxs
        task = _task(session, res)
        report = TaskEvaluationService(session, sr).evaluate(task.id)
        assert report["suggestedDecision"] == "inconclusive"
        with pytest.raises(DomainError) as exc:
            TaskService(session, sr).close(
                task_id=task.id, closure_decision="supported_success", packet={}
            )
        assert exc.value.code == ErrorCode.EVIDENCE_INSUFFICIENT
        unmet = exc.value.safe_details["unmet"]
        assert unmet[0]["metric"] == "metric.synthetic-performance"
        assert unmet[0]["verdict"] == "inconclusive"
