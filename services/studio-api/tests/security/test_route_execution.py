"""CS-0903 security tier — a stock-resolved retrosynthesis route is a
hypothesis, never an execution instruction.

AT-0903-3  a route reaching purchasable precursors still requires an
           independent plan approval; no principal — and least of all
           an agent — can turn the proposed route into lab execution.
"""

from __future__ import annotations

import pytest
from chem_studio_policy.capabilities import (
    APPROVAL_CAPABILITIES,
    CAP_APPROVE_EXPERIMENT,
    Grant,
    capabilities_for_role,
    effective_grants,
)
from sqlalchemy.orm import Session

from engine_adapter_aizynthfinder.contracts import (
    DOES_NOT_ESTABLISH,
    ProposedRoute,
    RouteOutcome,
)
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


def _stock_resolved_outcome() -> RouteOutcome:
    """A route where every precursor resolves to the purchasable stock
    — the strongest possible AT-0903-3 trigger."""
    return RouteOutcome(
        status="succeeded",
        usable=True,
        classification="reference_integration",
        routes=[
            ProposedRoute(
                rank=1,
                is_solved=True,
                all_precursors_in_stock=True,
                num_reactions=2,
                precursor_smiles=["CCO", "O=CC"],
                precursors_in_stock=["CCO", "O=CC"],
                score=0.9,
            )
        ],
        num_solved=1,
        provenance={"stock": {"name": "zinc_stock", "license": "mit"}},
        search_stats={"number_of_solved_routes": 1},
        engine_version="4.4.1",
        isolation={"backend": "container", "enforced": True},
    )


def _plan_for(
    session: Session, ctx: ServiceContext, outcome: RouteOutcome
) -> tuple[object, object]:
    proj = Project(workspace_id=ctx.workspace_id, slug="rxn", name="Rxn")
    session.add(proj)
    session.flush()
    task = ResearchTask(
        workspace_id=ctx.workspace_id,
        project_id=proj.id,
        mode="discover",
        title="route hypothesis",
        workflow_state="active",
        target_kind="compound",
        objective="retro",
    )
    session.add(task)
    session.flush()
    svc = LabPlanService(session, ctx)
    plan = svc.create(
        task.id,
        title="route hypothesis",
        payload={
            "method": "manual synthesis of the proposed route under lab protocol",
            "route": outcome.routes[0].model_dump(mode="json"),
            "route_label": outcome.label,
        },
    )
    svc.submit(plan.id)
    return task, plan


def test_stock_resolved_route_carries_no_execution_authority() -> None:
    outcome = _stock_resolved_outcome()
    assert outcome.routes[0].all_precursors_in_stock is True
    assert outcome.label == "proposed"
    assert outcome.execution_gate == "independent_plan_approval_required"
    assert outcome.routes[0].label == "proposed"
    for claim in ("yield", "selectivity", "safety", "scale_up_feasibility"):
        assert claim in outcome.does_not_establish
    assert "cost" in DOES_NOT_ESTABLISH


def test_at0903_3_agent_principal_never_approves_route(
    session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
) -> None:
    """Even with a fully stock-resolved route in hand, an agent
    principal cannot approve the plan that would execute it."""
    res, _, agent = ctxs
    outcome = _stock_resolved_outcome()
    task, plan = _plan_for(session, res, outcome)

    # Inert at the policy layer even if granted on paper.
    assert agent.has(CAP_APPROVE_EXPERIMENT) is False
    assert (
        effective_grants("agent", frozenset(Grant(c, None) for c in APPROVAL_CAPABILITIES))
        == frozenset()
    )

    svc = LabPlanService(session, agent)
    with pytest.raises(DomainError) as err:
        svc.review(plan.id, decision="approved", rationale="ship the route")
    assert err.value.code == ErrorCode.FORBIDDEN

    reloaded = LabPlanService(session, res).get(plan.id)
    assert reloaded.status == "submitted"
    assert task.id


def test_at0903_3_researcher_needs_independent_reviewer(
    session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
) -> None:
    """A researcher principal also lacks approve_experiment — the route
    only becomes a lab plan after an independent reviewer's approval."""
    res, sr, _ = ctxs
    outcome = _stock_resolved_outcome()
    _, plan = _plan_for(session, res, outcome)

    with pytest.raises(DomainError) as err:
        LabPlanService(session, res).review(plan.id, decision="approved")
    assert err.value.code == ErrorCode.FORBIDDEN

    LabPlanService(session, sr).review(
        plan.id, decision="approved", rationale="independent review ok"
    )
    reloaded = LabPlanService(session, res).get(plan.id)
    assert reloaded.status == "approved"
