"""CS-0204 acceptance tests — formulation/process/candidate revisions.

AT-0204-1  mass fractions totaling 1.2 -> acceptance blocked with
           COMPOSITION_TOTAL_INVALID; stored values are not normalized
AT-0204-2  rejecting a candidate patch leaves current candidate
           content unchanged and retains the rejection reason
AT-0204-3  equivalent ingredient lists with different process order
           keep their process differences through deduplication
"""

from __future__ import annotations

import uuid

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext, load_context
from studio.domain.candidates.service import CandidateService
from studio.domain.materials.formulations import (
    FormulationService,
    ingredient_key,
    process_signature,
)
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    CandidatePatch,
    CandidateRevision,
    FormulationRevision,
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


def _task(session: Session, workspace_id: uuid.UUID) -> ResearchTask:
    proj = Project(workspace_id=workspace_id, slug="p", name="P")
    session.add(proj)
    session.flush()
    task = ResearchTask(
        workspace_id=workspace_id,
        project_id=proj.id,
        mode="improve",
        title="improve base coating",
        workflow_state="active",
    )
    session.add(task)
    session.flush()
    return task


def _fraction(v: str) -> dict[str, object]:
    return {
        "value": v,
        "unit": "mass_fraction",
        "basis": "as_supplied",
        "original_text": v,
    }


def _payload(fractions: list[str], *, completeness: str = "complete") -> dict:
    return {
        "completeness": completeness,
        "amountBasis": "as_supplied",
        "declaredTotal": "1",
        "tolerance": "0.001",
        "ingredients": [
            {"name": f"ing-{i}", "amount": _fraction(f)} for i, f in enumerate(fractions)
        ],
    }


class TestCompositionTotal:
    """AT-0204-1: 1.2 total -> COMPOSITION_TOTAL_INVALID, no normalization."""

    def test_reject_normalized_never(
        self, session: Session, ctxs: tuple[ServiceContext, ...]
    ) -> None:
        res, _, _ = ctxs
        svc = FormulationService(session, res)
        fam = svc.create_family(name="coating")
        rev = svc.draft_revision(family_id=fam.id, payload=_payload(["0.6", "0.6"]))
        with pytest.raises(DomainError) as err:
            svc.accept_revision(revision_id=rev.id)
        assert err.value.code == ErrorCode.COMPOSITION_TOTAL_INVALID
        stored = session.execute(
            select(FormulationRevision).where(FormulationRevision.id == rev.id)
        ).scalar_one()
        assert stored.status == "draft"
        amounts = [line["amount"]["value"] for line in stored.payload["ingredients"]]
        assert amounts == ["0.6", "0.6"]  # never normalized to 0.5/0.5

    def test_valid_total_accepts(self, session: Session, ctxs: tuple[ServiceContext, ...]) -> None:
        res, _, _ = ctxs
        svc = FormulationService(session, res)
        fam = svc.create_family(name="coating")
        rev = svc.draft_revision(family_id=fam.id, payload=_payload(["0.6", "0.4"]))
        accepted = svc.accept_revision(revision_id=rev.id)
        assert accepted.status == "accepted"

    def test_incomplete_draft_keeps_findings_without_blocking(
        self, session: Session, ctxs: tuple[ServiceContext, ...]
    ) -> None:
        """An incomplete draft may sit outside its stated total — the
        deviation is recorded as a finding, not rejected or fixed."""
        res, _, _ = ctxs
        svc = FormulationService(session, res)
        fam = svc.create_family(name="coating")
        rev = svc.draft_revision(
            family_id=fam.id,
            payload=_payload(["0.6", "0.6"], completeness="draft"),
        )
        kinds = [f["kind"] for f in rev.payload["validationFindings"]]
        assert "total_outside_tolerance" in kinds
        assert rev.status == "draft"
        # incomplete revisions can't be accepted outright
        with pytest.raises(DomainError) as err:
            svc.accept_revision(revision_id=rev.id)
        assert err.value.code == ErrorCode.VALIDATION

    def test_duplicate_lines_flagged_not_summed(
        self, session: Session, ctxs: tuple[ServiceContext, ...]
    ) -> None:
        res, _, _ = ctxs
        svc = FormulationService(session, res)
        fam = svc.create_family(name="coating")
        payload = _payload(["0.5", "0.5"], completeness="draft")
        payload["ingredients"][1]["name"] = "ing-0"  # duplicate identity
        rev = svc.draft_revision(family_id=fam.id, payload=payload)
        kinds = [f["kind"] for f in rev.payload["validationFindings"]]
        assert "duplicate_ingredient_line" in kinds
        names = [line["name"] for line in rev.payload["ingredients"]]
        assert names.count("ing-0") == 2  # lines preserved, not summed


class TestCandidatePatches:
    """AT-0204-2: rejected patch -> content unchanged, reason kept."""

    def test_rejected_patch_retains_reason(
        self, session: Session, ctxs: tuple[ServiceContext, ...]
    ) -> None:
        res, reviewer, _ = ctxs
        task = _task(session, res.workspace_id)
        cands = CandidateService(session, res)
        cand = cands.create_candidate(
            task_id=task.id,
            entity_kind="formulation",
            hypothesis="lower solvent keeps film",
            proposed_differences=[{"field": "solvent", "op": "reduce"}],
        )
        before_payload = dict(cand.payload)
        before_hash = cand.content_hash
        patch = cands.propose_patch(
            candidate_id=cand.id,
            patch={"hypothesis": "different hypothesis"},
        )
        review = CandidateService(session, reviewer)
        decided = review.review_patch(
            patch_id=patch.id,
            accept=False,
            rejection_reason="contradicts the closure criteria",
        )
        session.flush()
        assert decided.status == "rejected"
        assert decided.rejection_reason == "contradicts the closure criteria"
        reloaded = session.execute(
            select(CandidateRevision).where(CandidateRevision.id == cand.id)
        ).scalar_one()
        assert reloaded.payload == before_payload
        assert reloaded.content_hash == before_hash
        assert reloaded.revision == cand.revision  # no new revision
        stored_patch = session.execute(
            select(CandidatePatch).where(CandidatePatch.id == patch.id)
        ).scalar_one()
        assert stored_patch.rejection_reason == "contradicts the closure criteria"

    def test_accepted_patch_creates_new_revision(
        self, session: Session, ctxs: tuple[ServiceContext, ...]
    ) -> None:
        res, reviewer, _ = ctxs
        task = _task(session, res.workspace_id)
        cands = CandidateService(session, res)
        cand = cands.create_candidate(
            task_id=task.id,
            entity_kind="formulation",
            proposed_differences=[{"field": "solvent", "op": "reduce"}],
        )
        patch = cands.propose_patch(
            candidate_id=cand.id,
            patch={"proposedDifferences": [{"field": "solvent", "op": "replace"}]},
        )
        decided = CandidateService(session, reviewer).review_patch(patch_id=patch.id, accept=True)
        session.flush()
        assert decided.status == "accepted"
        original = session.execute(
            select(CandidateRevision).where(CandidateRevision.id == cand.id)
        ).scalar_one()
        assert original.payload["proposedDifferences"] == [
            {"field": "solvent", "op": "reduce"}
        ]  # untouched
        child = session.execute(
            select(CandidateRevision).where(CandidateRevision.parent_revision_id == cand.id)
        ).scalar_one()
        assert child.payload["proposedDifferences"] == [{"field": "solvent", "op": "replace"}]
        assert child.revision == cand.revision + 1

    def test_agent_can_propose_but_cannot_review(
        self, session: Session, ctxs: tuple[ServiceContext, ...]
    ) -> None:
        _, _, agent = ctxs
        task = _task(session, agent.workspace_id)
        svc = CandidateService(session, agent)
        cand = svc.create_candidate(task_id=task.id, entity_kind="molecule")
        svc.submit_candidate(candidate_id=cand.id)
        with pytest.raises(DomainError) as err:
            svc.review_candidate(candidate_id=cand.id, accept=True)
        assert err.value.code == ErrorCode.FORBIDDEN

    def test_reviewed_candidate_immutable_but_eligibility_moves(
        self, session: Session, ctxs: tuple[ServiceContext, ...]
    ) -> None:
        res, reviewer, _ = ctxs
        task = _task(session, res.workspace_id)
        cands = CandidateService(session, res)
        cand = cands.create_candidate(task_id=task.id, entity_kind="formulation")
        cands.submit_candidate(candidate_id=cand.id)
        review = CandidateService(session, reviewer)
        decided = review.review_candidate(candidate_id=cand.id, accept=True)
        assert decided.status == "accepted_for_research"
        # eligibility is an assessment axis, not content — it may move
        moved = review.set_eligibility(candidate_id=cand.id, eligibility="eligible_for_computation")
        assert moved.eligibility == "eligible_for_computation"
        # but content stays frozen — the DB guard must reject edits
        decided.payload = {"tampered": True}
        with pytest.raises(DBAPIError, match="immutable_revision"):
            session.flush()
        session.rollback()


class TestProcessOrderDedup:
    """AT-0204-3: equal ingredient sets + different process order stay
    distinguishable through deduplication."""

    def test_process_order_survives_dedup(
        self, session: Session, ctxs: tuple[ServiceContext, ...]
    ) -> None:
        res, _, _ = ctxs
        svc = FormulationService(session, res)
        fam_a = svc.create_family(name="coating-a")
        fam_b = svc.create_family(name="coating-b")
        same_ingredients = _payload(["0.6", "0.4"])
        svc.draft_revision(family_id=fam_a.id, payload=same_ingredients)
        svc.draft_revision(family_id=fam_b.id, payload=dict(same_ingredients))
        proc_a = svc.draft_process_revision(
            family_id=fam_a.id,
            payload={
                "steps": [
                    {"order": 1, "action": "disperse"},
                    {"order": 2, "action": "bake"},
                ],
                "source": "lab notebook 12",
                "approvalStatus": "draft",
            },
        )
        proc_b = svc.draft_process_revision(
            family_id=fam_b.id,
            payload={
                "steps": [
                    {"order": 1, "action": "bake"},
                    {"order": 2, "action": "disperse"},
                ],
                "source": "lab notebook 13",
                "approvalStatus": "draft",
            },
        )
        svc.accept_process_revision(revision_id=proc_a.id)
        svc.accept_process_revision(revision_id=proc_b.id)
        groups = svc.find_duplicate_formulations()
        shared = [g for g in groups if len(g["revisions"]) == 2]
        assert len(shared) == 1
        group = shared[0]
        assert group["ingredientKey"] == ingredient_key(same_ingredients)
        # both revisions are reported — nothing merged
        assert {m["familyId"] for m in group["revisions"]} == {
            str(fam_a.id),
            str(fam_b.id),
        }
        sigs = group["processSignatures"]
        assert len(sigs) == 2  # different order -> different signatures
        assert process_signature(proc_a.payload) in sigs
        assert process_signature(proc_b.payload) in sigs
