"""CS-0503 — gate semantics and capability boundaries (§12.2).

AT-0503-2  high metric performance cannot compensate a failed hard
           safety/identity gate — and a human-only closure rejects
           agents even when the capability somehow lands.
"""

from __future__ import annotations

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext, load_context
from studio.domain.lab.measurements import LabMeasurementService
from studio.domain.tasks.evaluation import TaskEvaluationService
from studio.domain.tasks.service import TaskService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    CandidateRevision,
    FormulationFamily,
    FormulationRevision,
    LabBatch,
    LabExecution,
    LabSample,
    Measurement,
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    SuccessContractRevision,
    Workspace,
)

pytestmark = pytest.mark.security


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


EXCLUDED_MATERIAL = "11111111-1111-1111-1111-111111111111"


def _frozen_task(session: Session, res: ServiceContext) -> ResearchTask:
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
                    "id": "metric.perf",
                    "required": True,
                    "operator": "gte",
                    "target_values": ["100"],
                    "unit": "mPa·s",
                    "required_evidence": ["lab_measurement"],
                }
            ],
            "hard_constraints": [
                {
                    "id": "gate.no-banned-solvent",
                    "text": "banned solvent must be absent",
                    "check": {
                        "kind": "ingredient_absent",
                        "materialIdentityId": EXCLUDED_MATERIAL,
                    },
                }
            ],
        },
        content_hash="x",
    )
    session.add(contract)
    session.flush()
    task.current_contract_revision_id = contract.id
    session.flush()
    return task


def _accepted_measurement(
    session: Session, res: ServiceContext, task: ResearchTask, value: str = "150"
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
        method="ASTM D2196",
        metric="metric.perf",
        repeat_type="independent_batch",
        value_type="numeric",
        value={"kind": "numeric", "value": value, "unit": "mPa·s"},
        status="accepted",
    )
    session.add(m)
    session.flush()
    return m


def _candidate_with_banned(
    session: Session, res: ServiceContext, task: ResearchTask
) -> CandidateRevision:
    fam = FormulationFamily(workspace_id=res.workspace_id, name="f")
    session.add(fam)
    session.flush()
    frev = FormulationRevision(
        workspace_id=res.workspace_id,
        family_id=fam.id,
        revision=1,
        status="draft",
        payload={
            "ingredients": [
                {"materialId": EXCLUDED_MATERIAL, "amount": {"value": "5", "unit": "%"}}
            ]
        },
        content_hash="y",
    )
    session.add(frev)
    session.flush()
    cand = CandidateRevision(
        workspace_id=res.workspace_id,
        task_id=task.id,
        revision=1,
        status="accepted_for_research",
        entity_kind="formulation",
        entity_revision_id=frev.id,
        hypothesis="contains banned solvent",
        payload={},
        content_hash="z",
    )
    session.add(cand)
    session.flush()
    return cand


class TestHardGateNoCompensation:
    def test_failed_gate_not_compensated_by_performance(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """AT-0503-2: metric far above target + banned ingredient →
        the gate still fails; success is not suggested or allowed."""
        res, sr = ctxs
        task = _frozen_task(session, res)
        m = _accepted_measurement(session, res, task, value="999")  # way above 100
        cand = _candidate_with_banned(session, res, task)
        # PAR-02: lineage-less evidence only substantiates a candidate
        # through a reviewed applicability mapping — never by pooling
        LabMeasurementService(session, sr).record_applicability(
            m.id,
            candidate_revision_id=cand.id,
            applicable=True,
            rationale="fixture binds the reading to this candidate",
        )

        report = TaskEvaluationService(session, sr).evaluate(task.id)
        gate = report["gates"][0]
        assert gate["verdict"] == "fail"
        assert report["metrics"][0]["verdict"] == "met"
        # a failed hard gate is a definitive negative — never absorbed
        assert report["supportedSuccessEligible"] is False
        assert report["suggestedDecision"] == "supported_failure"

        # and the close path rejects supported_success outright
        with pytest.raises(DomainError) as exc:
            TaskService(session, sr).close(
                task_id=task.id,
                closure_decision="supported_success",
                packet=TaskEvaluationService(session, sr).closeout_packet(task.id),
            )
        assert exc.value.code == ErrorCode.EVIDENCE_INSUFFICIENT
        assert exc.value.safe_details["unprovenGates"][0]["verdict"] == "fail"

    def test_agent_cannot_close_even_when_eligible(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """Closure is human-only even where the evidence qualifies."""
        res, sr = ctxs
        agent = _principal(session, session.get(Workspace, res.workspace_id), "agent", "agent", "a")
        a_ctx = _ctx(session, session.get(Workspace, res.workspace_id), agent)
        task = _frozen_task(session, res)
        _accepted_measurement(session, res, task)
        # no banned ingredient → gate passes, metrics met
        report = TaskEvaluationService(session, sr).evaluate(task.id)
        assert report["suggestedDecision"] == "supported_success"

        with pytest.raises(DomainError) as exc:
            TaskService(session, a_ctx).close(
                task_id=task.id, closure_decision="supported_success", packet={}
            )
        assert exc.value.code == ErrorCode.FORBIDDEN
