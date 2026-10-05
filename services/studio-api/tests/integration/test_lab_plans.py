"""CS-0501 — immutable experiment plans and review.

AT-0501-2  missing material identity or required method → review
           lists blockers rather than inventing input
AT-0501-3  approved plan → packet carries exact immutable revisions
           and the manual-execution label (service half; e2e covers UI)
"""

from __future__ import annotations

import uuid

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext, load_context
from studio.domain.lab.plans import MANUAL_EXECUTION_LABEL, LabPlanService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    CandidateRevision,
    FormulationFamily,
    FormulationRevision,
    MaterialIdentity,
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
def ctxs(session: Session) -> tuple[ServiceContext, ServiceContext]:
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    researcher = _principal(session, ws, "user", "researcher", "res")
    reviewer = _principal(session, ws, "user", "scientific_reviewer", "sr")
    return _ctx(session, ws, researcher), _ctx(session, ws, reviewer)


def _task(session: Session, workspace_id: uuid.UUID, **kwargs) -> ResearchTask:
    proj = Project(workspace_id=workspace_id, slug="p", name="P")
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
        **kwargs,
    )
    session.add(task)
    session.flush()
    return task


def _candidate(
    session: Session,
    ws_id: uuid.UUID,
    task_id: uuid.UUID,
    *,
    with_material: bool,
) -> CandidateRevision:
    """Formulation candidate: 1 known material + 1 ingredient whose
    material link is absent."""
    fam = FormulationFamily(workspace_id=ws_id, name="f")
    session.add(fam)
    session.flush()
    mat = MaterialIdentity(workspace_id=ws_id, kind="defined_molecule", name="water")
    session.add(mat)
    session.flush()
    lines = [
        {
            "name": "water",
            "materialId": str(mat.id),
            "amount": {"value": "0.6", "unit": "mass_fraction"},
        },
        {
            "name": "mystery-resin",
            "amount": {"value": "0.4", "unit": "mass_fraction"},
        },
    ]
    rev = FormulationRevision(
        workspace_id=ws_id,
        family_id=fam.id,
        revision=1,
        status="accepted",
        payload={"completeness": "complete", "ingredients": lines},
        content_hash="x" * 64,
    )
    session.add(rev)
    session.flush()
    cand = CandidateRevision(
        workspace_id=ws_id,
        task_id=task_id,
        revision=1,
        status="accepted_for_research",
        eligibility="not_assessed",
        entity_kind="formulation",
        entity_revision_id=rev.id,
        payload={},
        content_hash="x" * 64,
    )
    session.add(cand)
    session.flush()
    return cand


def _plan_payload(cand_id: uuid.UUID, *, method: str | None = "ASTM D2196") -> dict:
    p: dict = {
        "candidateRevisionId": str(cand_id),
        "method": method,
        "samplePlan": [{"batch": "A", "aliquots": 2}],
        "acceptanceCriteria": "viscosity within contract band",
        "hazardNotes": "no special hazards identified",
        "resourceNeeds": "mixer, viscometer",
    }
    if method is None:
        del p["method"]
    return p


class TestPlanLifecycle:
    def test_happy_path_packet_binds_exact_revisions(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """AT-0501-3 service half: approved plan → packet carries the
        exact revision ids and the manual-execution label."""
        res, sr = ctxs
        task = _task(session, res.workspace_id)
        # mystery-resin would block approval — give it a material link
        cand = _candidate(session, res.workspace_id, task.id, with_material=True)
        # link the unknown ingredient to a registered identity so the
        # review has no blockers
        mat2 = MaterialIdentity(
            workspace_id=res.workspace_id, kind="commercial_mixture", name="mystery-resin"
        )
        session.add(mat2)
        session.flush()
        rev = session.get(FormulationRevision, cand.entity_revision_id)
        rev.payload["ingredients"][1]["materialId"] = str(mat2.id)
        session.flush()

        svc = LabPlanService(session, res)
        plan = svc.create(task.id, title="viscosity check", payload=_plan_payload(cand.id))
        assert plan.status == "draft"
        assert plan.blockers == []

        svc.submit(plan.id)
        assert plan.status == "submitted"

        LabPlanService(session, sr).review(plan.id, decision="approved", rationale="ok")
        assert plan.status == "approved"
        assert plan.approval_id is not None

        packet = svc.export_packet(plan.id)
        assert packet["executionMode"] == "manual"
        assert packet["label"] == MANUAL_EXECUTION_LABEL
        assert packet["revisions"]["candidateRevisionId"] == str(cand.id)
        assert packet["contentDigest"] == plan.content_digest

    def test_blockers_listed_not_invented(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """AT-0501-2: missing material identity + missing method land
        in the blocker list; approval refuses while they remain."""
        res, sr = ctxs
        task = _task(session, res.workspace_id)
        cand = _candidate(session, res.workspace_id, task.id, with_material=False)
        svc = LabPlanService(session, res)
        plan = svc.create(
            task.id,
            title="incomplete plan",
            payload=_plan_payload(cand.id, method=None),
        )
        kinds = {b["kind"] for b in plan.blockers}
        assert "missing_method" in kinds
        assert "material_identity_missing" in kinds

        svc.submit(plan.id)
        with pytest.raises(DomainError) as err:
            LabPlanService(session, sr).review(plan.id, decision="approved")
        assert err.value.code == ErrorCode.CONFLICT
        assert "blockers" in (err.value.safe_details or {})
        session.refresh(plan)
        assert plan.status == "submitted"

        # a rejection with a rationale is allowed despite blockers
        LabPlanService(session, sr).review(
            plan.id, decision="rejected", rationale="resolve inputs first"
        )
        assert plan.status == "rejected"

    def test_submit_requires_draft(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, _ = ctxs
        task = _task(session, res.workspace_id)
        svc = LabPlanService(session, res)
        plan = svc.create(task.id, title="p", payload={"method": "m"})
        svc.submit(plan.id)
        with pytest.raises(DomainError):
            svc.submit(plan.id)
