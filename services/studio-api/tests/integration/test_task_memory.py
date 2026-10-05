"""CS-0304 integration tests — durable task memory + session snapshots.

AT-0304-1  prior rejection/constraints/evidence present in new session
AT-0304-2  contract change → old summary stale, never overwrites state
"""

from __future__ import annotations

from typing import Any

import pytest
from chem_studio_policy.capabilities import CAP_READ_PROJECT, capabilities_for_role
from sqlalchemy.orm import Session

from studio.auth.context import load_context
from studio.domain.candidates.service import CandidateService
from studio.domain.tasks.memory import TaskMemoryService
from studio.domain.tasks.service import TaskService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    EvidenceClaim,
    Principal,
    PrincipalCapability,
    Project,
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


@pytest.fixture()
def env(session: Session) -> dict[str, Any]:
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    owner = _principal(session, ws, "user", "owner", "owner")
    reviewer = _principal(session, ws, "user", "scientific_reviewer", "rev")
    project = Project(workspace_id=ws.id, slug="p", name="P")
    session.add(project)
    session.flush()
    ctx = load_context(session, ws.id, owner.id)
    task = TaskService(session, ctx).create(
        project_id=project.id, title="t", mode="improve", objective="lower cost"
    )
    contract = TaskService(session, ctx).draft_contract(
        task_id=task.id,
        payload={
            "metrics": [{"name": "viscosity", "target": ">= 500"}],
            "constraints": ["keep pH below 9", "no solvent swaps"],
            "warnings": ["solvent lot identity unverified"],
        },
    )
    TaskService(session, ctx).freeze_contract(revision_id=contract.id)
    return {
        "ws": ws,
        "project": project,
        "task": task,
        "contract": contract,
        "owner": ctx,
        "reviewer": load_context(session, ws.id, reviewer.id),
        "session": session,
    }


def _claim(session: Session, env: dict[str, Any]) -> EvidenceClaim:
    c = EvidenceClaim(
        workspace_id=env["ws"].id,
        kind="document_claim",
        status="accepted",
        subject={"entity": "baseline"},
        statement={"text": "baseline viscosity 480 mPa·s"},
        locator={"row": 2, "col": 1},
        created_by=env["owner"].principal_id,
    )
    session.add(c)
    session.flush()
    return c


class TestSessionResumption:
    """AT-0304-1: a new session starts from a manifest that still
    carries the prior session's rejection, constraints, and evidence —
    nothing needs re-explaining."""

    def test_prior_rejection_and_evidence_in_new_manifest(self, env: dict[str, Any]) -> None:
        ctx = env["owner"]
        task = env["task"]
        mem = TaskMemoryService(env["session"], ctx)
        cand_svc = CandidateService(env["session"], ctx)
        claim = _claim(env["session"], env)

        # session A: reject a candidate patch with a reason tied to evidence
        s_a = mem.start_session(task.id)
        cand = cand_svc.create_candidate(
            task_id=task.id,
            entity_kind="formulation",
            proposed_differences=[{"op": "set", "path": "/solvent", "value": "IPA"}],
            evidence_ids=[str(claim.id)],
        )
        patch = cand_svc.propose_patch(
            candidate_id=cand.id,
            patch={"ops": [{"op": "set", "path": "/solvent", "value": "ethanol"}]},
        )
        cand_svc.review_patch(
            patch_id=patch.id,
            accept=False,
            rejection_reason=f"solvent swaps barred; see claim {claim.id}",
        )
        mem.post_message(s_a.id, role="user", content="rejected the solvent swap proposal")
        mem.end_session(s_a.id)

        # session B: manifest carries the rejection + evidence + constraints
        s_b = mem.start_session(task.id)
        manifest = mem.manifest(s_b.start_manifest_id)
        kinds = {i["kind"] for i in manifest.items}
        assert "rejected_approach" in kinds
        rejected = [i for i in manifest.items if i["kind"] == "rejected_approach"]
        assert any("solvent swaps barred" in i["text"] for i in rejected)
        assert any(str(claim.id) in i["text"] for i in rejected)
        assert "evidence" in kinds
        assert any(str(claim.id) == i["refId"] for i in manifest.items if i["kind"] == "evidence")
        # hard constraints are pinned, not budget-dependent
        pinned = [i for i in manifest.items if i["pinned"]]
        assert any("keep pH below 9" in i["text"] for i in pinned)
        assert any("identity unverified" in i["text"] for i in pinned)
        # the new session stays anchored to the contract it opened under
        assert s_b.start_contract_revision_id == task.current_contract_revision_id
        # session A is untouched — linked to its own start context
        assert s_a.status == "ended"
        assert s_a.end_snapshot["contractRevisionId"] == str(task.current_contract_revision_id)

    def test_end_session_snapshot_and_message_layer(self, env: dict[str, Any]) -> None:
        ctx = env["owner"]
        mem = TaskMemoryService(env["session"], ctx)
        s = mem.start_session(env["task"].id)
        q = mem.raise_question(env["task"].id, question="which baseline lot?", blocking=True)
        mem.post_message(s.id, role="assistant", kind="rationale", content="need lot")
        msgs = mem.messages(s.id)
        assert msgs[0].kind == "rationale"
        ended = mem.end_session(s.id)
        assert ended.end_snapshot["openQuestions"] == 1
        # a resolved question leaves the open set
        mem.resolve_question(q.id, resolution="lot 2314")
        assert mem.questions(env["task"].id)[0].status == "resolved"


class TestSummaryStaleness:
    """AT-0304-2: a summary written against contract rev N is stale once
    the contract moves — it is marked, and it cannot overwrite
    structured state (there is no apply path)."""

    def test_summary_marked_stale_after_contract_change(self, env: dict[str, Any]) -> None:
        ctx = env["owner"]
        task = env["task"]
        mem = TaskMemoryService(env["session"], ctx)
        claim = _claim(env["session"], env)

        summary = mem.create_summary(
            task.id,
            body="baseline documented at 480 mPa·s; solvent identity open",
            source_ids=[str(claim.id)],
            generator="deterministic",
        )
        rows = mem.summaries(task.id)
        assert rows[0][1] is False  # fresh

        # a new contract revision supersedes the pinned one
        svc = TaskService(env["session"], ctx)
        rev2 = svc.draft_contract(
            task_id=task.id,
            payload={"metrics": [{"name": "viscosity", "target": ">= 600"}]},
        )
        svc.freeze_contract(revision_id=rev2.id)

        rows = mem.summaries(task.id)
        assert rows[0][0].id == summary.id
        assert rows[0][1] is True  # stale: pinned rev != current rev
        assert rows[0][0].contract_revision_id == env["contract"].id
        # structured state untouched — task points at rev2, summary at rev1
        assert task.current_contract_revision_id == rev2.id
        # no apply/update path exists on the service
        assert not hasattr(mem, "apply_summary")
        assert not hasattr(mem, "update_from_summary")

    def test_summary_stale_when_source_claim_superseded(self, env: dict[str, Any]) -> None:
        ctx = env["owner"]
        mem = TaskMemoryService(env["session"], ctx)
        claim = _claim(env["session"], env)
        mem.create_summary(env["task"].id, body="s", source_ids=[str(claim.id)], generator="g")
        claim.status = "superseded"
        env["session"].flush()
        assert mem.summaries(env["task"].id)[0][1] is True


class TestMemoryAuthorization:
    """Session/summary writes require edit_task on the task's project;
    a read-only principal can read but not write."""

    def test_read_only_principal_cannot_start_session(self, env: dict[str, Any]) -> None:
        viewer = Principal(workspace_id=env["ws"].id, kind="user", login="v", display_name="v")
        env["session"].add(viewer)
        env["session"].flush()
        env["session"].add(
            PrincipalCapability(
                workspace_id=env["ws"].id,
                principal_id=viewer.id,
                capability=CAP_READ_PROJECT,
                scope_ref=str(env["project"].id),
            )
        )
        env["session"].flush()
        vctx = load_context(env["session"], env["ws"].id, viewer.id)
        mem = TaskMemoryService(env["session"], vctx)

        with pytest.raises(DomainError) as exc:
            mem.start_session(env["task"].id)
        assert exc.value.code == ErrorCode.FORBIDDEN

        # but reading is allowed within scope
        assert mem.questions(env["task"].id) == []

    def test_session_is_workspace_scoped(self, env: dict[str, Any], session: Session) -> None:
        other_ws = Workspace(slug="w2", display_name="W2")
        session.add(other_ws)
        session.flush()
        outsider = _principal(session, other_ws, "user", "owner", "o2")
        octx = load_context(session, other_ws.id, outsider.id)
        mem = TaskMemoryService(session, octx)
        with pytest.raises(DomainError) as exc:
            mem.start_session(env["task"].id)  # task is in ws, not w2
        assert exc.value.code == ErrorCode.NOT_FOUND
