"""CS-0404 acceptance test — deterministic verifier + RDKit, integrated.

AT-0404-3  a *passed* structural check still cannot satisfy a contract
           whose required metric demands lab_measurement evidence:
           the verifier reports the missing endpoint, and the task's
           supported_success gate continues to block.

Where a real rdkit exists (container image or native install) the
structural checks run live; where it doesn't, the packet reports the
engine as unavailable instead of fabricating a pass — either way the
closure outcome under test is identical and honest.
"""

from __future__ import annotations

import uuid

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine_adapter_rdkit import RDKitAdapter
from studio.auth.context import ServiceContext, load_context
from studio.domain.candidates.service import CandidateService
from studio.domain.candidates.verification import VerificationService
from studio.domain.materials.formulations import FormulationService
from studio.domain.tasks.service import TaskService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
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
def ctx(session: Session) -> ServiceContext:
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    return _ctx(session, ws, _principal(session, ws, "user", "researcher", "res"))


@pytest.fixture()
def reviewer_ctx(session: Session, ctx: ServiceContext) -> ServiceContext:
    ws = session.execute(select(Workspace).where(Workspace.id == ctx.workspace_id)).scalar_one()
    return _ctx(session, ws, _principal(session, ws, "user", "scientific_reviewer", "rev"))


def _fraction(v: str) -> dict[str, object]:
    return {
        "value": v,
        "unit": "mass_fraction",
        "basis": "as_supplied",
        "original_text": v,
    }


def _setup(session: Session, ctx: ServiceContext) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Task + frozen contract (one lab-measurement metric) + accepted
    formulation with a known-valid structure + candidate revision."""
    proj = Project(workspace_id=ctx.workspace_id, slug="p", name="P")
    session.add(proj)
    session.flush()
    task = ResearchTask(
        workspace_id=ctx.workspace_id,
        project_id=proj.id,
        mode="improve",
        title="improve coating",
        workflow_state="active",
    )
    session.add(task)
    session.flush()

    tasks = TaskService(session, ctx)
    contract = tasks.draft_contract(
        task_id=task.id,
        payload={
            "objective": "improve tack strength",
            "metrics": [
                {
                    "id": "m.tack",
                    "label": "tack strength",
                    "required": True,
                    "value_kind": "numeric",
                    "operator": "gte",
                    "target_values": ["10"],
                    "unit": "N",
                    "method_revision_id": None,
                    "conditions": {"substrate_revision_id": None, "description": "std"},
                    "required_evidence": ["lab_measurement"],
                    "aggregation": "mean",
                    "replication_rule": "n>=3",
                }
            ],
            "requiredMetrics": ["m.tack"],
            "hard_constraints": [],
        },
    )
    tasks.freeze_contract(revision_id=contract.id)

    # An identity whose structure is reviewed/resolved (ethanol).
    ident = MaterialIdentity(
        workspace_id=ctx.workspace_id,
        kind="defined_molecule",
        name="ethanol",
        structure="CCO",
        structure_format="smiles",
        structure_status="reviewed",
    )
    session.add(ident)
    session.flush()

    forms = FormulationService(session, ctx)
    fam = forms.create_family(name="coating")
    rev = forms.draft_revision(
        family_id=fam.id,
        payload={
            "completeness": "complete",
            "amountBasis": "as_supplied",
            "declaredTotal": "1",
            "tolerance": "0.001",
            "ingredients": [
                {
                    "materialId": str(ident.id),
                    "name": "ethanol",
                    "amount": _fraction("1.0"),
                }
            ],
        },
    )
    accepted = forms.accept_revision(revision_id=rev.id)
    cand = CandidateService(session, ctx).create_candidate(
        task_id=task.id,
        entity_kind="formulation",
        entity_revision_id=accepted.id,
        hypothesis="baseline candidate",
    )
    session.flush()
    return task.id, contract.id, cand.id


def test_structural_pass_still_blocks_supported_success(
    session: Session, ctx: ServiceContext, reviewer_ctx: ServiceContext
) -> None:
    """AT-0404-3: structural evidence != laboratory endpoints."""
    task_id, _, cand_id = _setup(session, ctx)
    verifier = VerificationService(session, ctx, adapter=RDKitAdapter())
    packet = verifier.evaluate_candidate(task_id=task_id, candidate_revision_id=cand_id)

    # Findings carry real check output — a structure pass is recorded
    # as descriptor evidence, never lab proof.
    kinds = {f["kind"] for f in packet["findings"]}
    engine_up = packet["engine"]["available"]
    if engine_up:
        assert "structure_valid" in kinds
        structural = packet["structural"]
        assert structural and structural[0]["ok"] is True
        assert structural[0]["engine_version"]
        assert structural[0]["evidence_type"] == "descriptor"
    else:
        # Honest degradation: engine unavailability is reported, a
        # pass is never simulated.
        assert "structure_invalid" in kinds
    assert "composition_total" in kinds  # deterministic basis check ran

    # Closure: the contract's lab_measurement requirement is missing.
    closure = packet["closure"]
    assert closure["assessable"] is True
    assert closure["supportedSuccessEligible"] is False
    assert "lab_measurement" in closure["missingEvidence"]
    metric = closure["metrics"][0]
    assert metric["status"] == "missing"
    assert metric["missing"] == ["lab_measurement"]
    assert packet["evidenceTypes"] == ["descriptor"]

    # The authoritative gate agrees — supported_success stays blocked
    # even for a human reviewer closing an awaiting_review task.
    tasks = TaskService(session, ctx)
    tasks.transition(task_id=task_id, to_state="awaiting_review")
    with pytest.raises(DomainError) as err:
        TaskService(session, reviewer_ctx).close(
            task_id=task_id,
            closure_decision="supported_success",
        )
    assert err.value.code == ErrorCode.EVIDENCE_INSUFFICIENT


def test_invalid_structure_blocks_without_fabrication(
    session: Session, ctx: ServiceContext
) -> None:
    """A formulation whose identity carries an invalid-valence
    structure yields a blocking finding — no descriptors invented."""
    ws = ctx.workspace_id
    proj = Project(workspace_id=ws, slug="p2", name="P2")
    session.add(proj)
    session.flush()
    task = ResearchTask(
        workspace_id=ws,
        project_id=proj.id,
        mode="improve",
        title="t",
        workflow_state="active",
    )
    session.add(task)
    session.flush()
    bad = MaterialIdentity(
        workspace_id=ws,
        kind="defined_molecule",
        name="bad-mol",
        structure="C(C)(C)(C)(C)(C)",
        structure_format="smiles",
        structure_status="reviewed",
    )
    session.add(bad)
    session.flush()
    forms = FormulationService(session, ctx)
    fam = forms.create_family(name="f")
    rev = forms.draft_revision(
        family_id=fam.id,
        payload={
            "completeness": "complete",
            "declaredTotal": "1",
            "ingredients": [{"materialId": str(bad.id), "amount": _fraction("1.0")}],
        },
    )
    cand = CandidateService(session, ctx).create_candidate(
        task_id=task.id, entity_kind="formulation", entity_revision_id=rev.id
    )
    session.flush()
    verifier = VerificationService(session, ctx, adapter=RDKitAdapter())
    if not verifier.adapter.capability().available:
        pytest.skip("rdkit engine unavailable on this host")
    packet = verifier.evaluate_candidate(task_id=task.id, candidate_revision_id=cand.id)
    invalid = [f for f in packet["findings"] if f["kind"] == "structure_invalid"]
    assert invalid and invalid[0]["severity"] == "blocking"
    for entry in packet["structural"]:
        assert entry["ok"] is False
        assert "descriptors" not in entry  # nothing fabricated
