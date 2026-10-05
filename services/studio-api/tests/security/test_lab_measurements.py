"""CS-0502 security tier — capability gates and agent denial.

Agents can never review or amend measurements; recording requires
edit_task on the owning project; review requires review_measurement.
"""

from __future__ import annotations

import uuid

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext, load_context
from studio.domain.lab.measurements import LabMeasurementService
from studio.domain.lab.plans import LabPlanService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
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
def ctxs(session: Session) -> tuple[ServiceContext, ServiceContext, ServiceContext]:
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    researcher = _principal(session, ws, "user", "researcher", "res")
    reviewer = _principal(session, ws, "user", "scientific_reviewer", "sr")
    agent = _principal(session, ws, "agent", "agent", "bot")
    return (
        _ctx(session, ws, researcher),
        _ctx(session, ws, reviewer),
        _ctx(session, ws, agent),
    )


def _approved_plan(session: Session, res: ServiceContext, sr: ServiceContext, task: ResearchTask):
    svc = LabPlanService(session, res)
    plan = svc.create(task.id, title="p", payload={"method": "m"})
    svc.submit(plan.id)
    LabPlanService(session, sr).review(plan.id, decision="approved")
    return plan


def _task(session: Session, workspace_id: uuid.UUID, slug: str = "p") -> ResearchTask:
    proj = Project(workspace_id=workspace_id, slug=slug, name="P")
    session.add(proj)
    session.flush()
    task = ResearchTask(
        workspace_id=workspace_id,
        project_id=proj.id,
        mode="discover",
        title="t",
        workflow_state="active",
        target_kind="formulation",
        objective="o",
    )
    session.add(task)
    session.flush()
    return task


class TestCapabilityGates:
    def test_agent_cannot_review_or_amend(
        self,
        session: Session,
        ctxs: tuple[ServiceContext, ServiceContext, ServiceContext],
    ) -> None:
        res, sr, agent = ctxs
        task = _task(session, res.workspace_id)
        plan = _approved_plan(session, res, sr, task)
        svc = LabMeasurementService(session, res)
        ex = svc.open_execution(plan.id)
        batch = svc.add_batch(ex.id, label="b")
        sample = svc.add_sample(batch.id, label="s")
        m = svc.record_measurement(
            sample.id,
            method="m",
            repeat_type="same_sample",
            value={"kind": "numeric", "value": "1", "unit": "g"},
        )
        bot = LabMeasurementService(session, agent)
        with pytest.raises(DomainError) as err:
            bot.review(m.id, decision="accepted")
        assert err.value.code == ErrorCode.FORBIDDEN
        with pytest.raises(DomainError) as err:
            bot.amend(m.id, reason="x", value={"kind": "numeric", "value": "2", "unit": "g"})
        assert err.value.code == ErrorCode.FORBIDDEN

    def test_viewer_cannot_record_or_review(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
    ) -> None:
        res, sr, _ = ctxs
        viewer = _principal(
            session,
            session.get(Workspace, res.workspace_id),
            "user",
            "viewer",
            "v",
        )
        v_ctx = _ctx(session, session.get(Workspace, res.workspace_id), viewer)
        task = _task(session, res.workspace_id, slug="p2")
        plan = _approved_plan(session, res, sr, task)
        svc = LabMeasurementService(session, res)
        ex = svc.open_execution(plan.id)
        batch = svc.add_batch(ex.id, label="b")
        sample = svc.add_sample(batch.id, label="s")
        v_svc = LabMeasurementService(session, v_ctx)
        with pytest.raises(DomainError) as err:
            v_svc.record_measurement(
                sample.id,
                method="m",
                repeat_type="same_sample",
                value={"kind": "numeric", "value": "1", "unit": "g"},
            )
        assert err.value.code == ErrorCode.FORBIDDEN

    def test_open_execution_denied_without_edit_task(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
    ) -> None:
        res, sr, _ = ctxs
        # scientific_reviewer lacks edit_task — cannot open executions
        task = _task(session, res.workspace_id, slug="p3")
        plan = _approved_plan(session, res, sr, task)
        with pytest.raises(DomainError) as err:
            LabMeasurementService(session, sr).open_execution(plan.id)
        assert err.value.code == ErrorCode.FORBIDDEN
