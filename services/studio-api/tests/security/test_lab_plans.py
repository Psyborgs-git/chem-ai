"""CS-0501 security tier — stale approvals and capability gates.

AT-0501-1  an approved plan is edited → packet request → stale
           approval blocks the changed plan
Plus: agents can never review or decide; non-owners cannot export.
"""

from __future__ import annotations

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext, load_context
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


def _approved_plan(session: Session, res: ServiceContext, sr: ServiceContext):
    proj = Project(workspace_id=res.workspace_id, slug="p", name="P")
    session.add(proj)
    session.flush()
    task = ResearchTask(
        workspace_id=res.workspace_id,
        project_id=proj.id,
        mode="discover",
        title="t",
        workflow_state="active",
        target_kind="formulation",
        objective="o",
    )
    session.add(task)
    session.flush()
    svc = LabPlanService(session, res)
    plan = svc.create(
        task.id, title="release plan", payload={"method": "ASTM D2196", "concentration": "5%"}
    )
    svc.submit(plan.id)
    LabPlanService(session, sr).review(plan.id, decision="approved", rationale="ship it")
    return task, plan


class TestStaleApproval:
    def test_edited_approved_plan_blocked_at_export(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
    ) -> None:
        """AT-0501-1: approval binds the digest; a post-approval edit
        makes export fail APPROVAL_STALE — never silently ships."""
        res, sr, _ = ctxs
        _, plan = _approved_plan(session, res, sr)
        svc = LabPlanService(session, res)
        svc.export_packet(plan.id)  # valid while untouched

        svc.update(plan.id, payload={"method": "ASTM D2196", "concentration": "10%"})
        with pytest.raises(DomainError) as err:
            svc.export_packet(plan.id)
        assert err.value.code == ErrorCode.APPROVAL_STALE

    def test_revoked_or_expired_blocks(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
    ) -> None:
        res, sr, _ = ctxs
        _, plan = _approved_plan(session, res, sr)
        from studio.application.approvals import revoke

        revoke(session, sr, approval_id=plan.approval_id)
        with pytest.raises(DomainError) as err:
            LabPlanService(session, res).export_packet(plan.id)
        assert err.value.code == ErrorCode.FORBIDDEN


class TestCapabilityGates:
    def test_agent_cannot_review(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
    ) -> None:
        res, _, agent = ctxs
        proj = Project(workspace_id=res.workspace_id, slug="p2", name="P2")
        session.add(proj)
        session.flush()
        task = ResearchTask(
            workspace_id=res.workspace_id,
            project_id=proj.id,
            mode="discover",
            title="t2",
            workflow_state="active",
            target_kind="formulation",
            objective="o",
        )
        session.add(task)
        session.flush()
        svc = LabPlanService(session, res)
        plan = svc.create(task.id, title="p", payload={"method": "m"})
        svc.submit(plan.id)
        with pytest.raises(DomainError) as err:
            LabPlanService(session, agent).review(plan.id, decision="approved")
        assert err.value.code == ErrorCode.FORBIDDEN
