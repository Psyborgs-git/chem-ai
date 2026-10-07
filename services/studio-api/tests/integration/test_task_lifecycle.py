"""CS-0201 acceptance tests — project/task/contract lifecycle.

AT-0201-1  drafts in all three modes persist mode + unknown inputs
AT-0201-2  closed task + new contract → original closure keeps its
           original contract revision
AT-0201-3  agent-proposed success → closure blocked: human review and
           evidence gates required
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.testclient import TestClient
from strawberry import relay

from studio.api.app import create_app
from studio.auth.context import ServiceContext, load_context
from studio.config.settings import Settings
from studio.domain.tasks.service import TaskService, unresolved_inputs
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

HEADERS = {"origin": "http://127.0.0.1:8787", "host": "127.0.0.1:8787"}


def _client(db_url: str) -> TestClient:
    return TestClient(create_app(Settings(database_url=db_url)))


def _setup_owner(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/setup",
        json={
            "login": "owner",
            "display_name": "Owner",
            "password": "correct horse battery staple",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text


def _gql(client: TestClient, query: str, variables: dict[str, Any] | None = None) -> Any:
    resp = client.post(
        "/graphql",
        json={"query": query, "variables": variables or {}},
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _gid(type_name: str, row_id: uuid.UUID) -> str:
    return str(relay.GlobalID(type_name=type_name, node_id=str(row_id)))


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


def _project(session: Session, ws: Workspace) -> Project:
    p = Project(workspace_id=ws.id, slug="p", name="P")
    session.add(p)
    session.flush()
    return p


class TestModeDraftPersistence:
    """AT-0201-1: drafts keep their mode and honest unknowns."""

    def test_all_three_modes_persist_with_unknowns(self, db_url: str, session: Session) -> None:
        client = _client(db_url)
        _setup_owner(client)
        ws = session.query(Workspace).one()
        project = _project(session, ws)
        session.commit()
        create = (
            "mutation($input: TaskCreateInput!) { taskCreate(input: $input) "
            "{ task { id mode targetKind unresolvedInputs } errors { code } } }"
        )
        cases = [
            {"mode": "improve", "modeInputs": {"variationScope": {"wheels": "free"}}},
            {"mode": "match_reference", "modeInputs": {"matchScope": "functional"}},
            {"mode": "discover"},
        ]
        for extra in cases:
            out = _gql(
                client,
                create,
                {
                    "input": {
                        "projectId": _gid("Project", project.id),
                        "title": extra["mode"],
                        **extra,
                    }
                },
            )["data"]["taskCreate"]
            assert out["errors"] == [], out
            task = out["task"]
            assert task["mode"] == extra["mode"]
            # nothing fabricated: discover keeps unknown target kind
            if extra["mode"] == "discover":
                assert task["targetKind"] == "unknown"
                assert "targetKind" in task["unresolvedInputs"]
            if extra["mode"] == "improve":
                # baseline not supplied → unresolved, not invented
                assert "baselineRevisionId" in task["unresolvedInputs"]
                assert "variationScope" not in task["unresolvedInputs"]
            if extra["mode"] == "match_reference":
                assert "referenceProductId" in task["unresolvedInputs"]
                assert "matchScope" not in task["unresolvedInputs"]

    def test_mode_inputs_roundtrip_unmodified(self, session: Session) -> None:
        ws = Workspace(slug="w", display_name="W")
        session.add(ws)
        session.flush()
        p = _principal(session, ws, "user", "researcher", "r")
        project = _project(session, ws)
        ctx = _ctx(session, ws, p)
        svc = TaskService(session, ctx)
        inputs = {"matchScope": "functional", "supplierDocIds": ["d1"]}
        task = svc.create(
            project_id=project.id,
            title="match",
            mode="match_reference",
            mode_inputs=inputs,
        )
        session.commit()
        reloaded = session.get(ResearchTask, task.id)
        assert reloaded is not None
        assert reloaded.mode_inputs == inputs
        assert unresolved_inputs(reloaded) == ["referenceProductId"]


class TestLifecycleTransitions:
    def test_state_machine_rules(self, session: Session) -> None:
        ws = Workspace(slug="w", display_name="W")
        session.add(ws)
        session.flush()
        p = _principal(session, ws, "user", "researcher", "r")
        project = _project(session, ws)
        ctx = _ctx(session, ws, p)
        svc = TaskService(session, ctx)
        task = svc.create(project_id=project.id, title="t", mode="discover")
        session.commit()

        # draft -> closed is not a legal transition
        with pytest.raises(DomainError) as exc:
            svc.transition(task_id=task.id, to_state="closed")
        assert exc.value.code == ErrorCode.VALIDATION
        # draft -> awaiting_review also not legal
        with pytest.raises(DomainError) as exc:
            svc.transition(task_id=task.id, to_state="awaiting_review")
        assert exc.value.code == ErrorCode.VALIDATION

        svc.transition(task_id=task.id, to_state="active")
        svc.transition(task_id=task.id, to_state="paused")
        svc.transition(task_id=task.id, to_state="active")
        svc.transition(task_id=task.id, to_state="awaiting_review")
        # return to active requires a review reason
        with pytest.raises(DomainError):
            svc.transition(task_id=task.id, to_state="active")
        svc.transition(task_id=task.id, to_state="active", reason="needs more data")
        session.commit()
        task = session.get(ResearchTask, task.id)
        assert task is not None and task.workflow_state == "active"
        kinds = [d.kind for d in session.execute(select(TaskDecision)).scalars().all()]
        assert "review_return" in kinds

    def test_optimistic_expected_version(self, session: Session) -> None:
        ws = Workspace(slug="w", display_name="W")
        session.add(ws)
        session.flush()
        p = _principal(session, ws, "user", "researcher", "r")
        project = _project(session, ws)
        ctx = _ctx(session, ws, p)
        svc = TaskService(session, ctx)
        task = svc.create(project_id=project.id, title="t", mode="discover")
        session.commit()
        with pytest.raises(DomainError) as exc:
            svc.transition(task_id=task.id, to_state="active", expected_version=99)
        assert exc.value.code == ErrorCode.REVISION_CONFLICT
        svc.transition(task_id=task.id, to_state="active", expected_version=1)
        session.commit()
        assert session.get(ResearchTask, task.id).version == 2  # type: ignore[union-attr]

    def test_cancel_from_active(self, session: Session) -> None:
        ws = Workspace(slug="w", display_name="W")
        session.add(ws)
        session.flush()
        p = _principal(session, ws, "user", "researcher", "r")
        project = _project(session, ws)
        ctx = _ctx(session, ws, p)
        svc = TaskService(session, ctx)
        task = svc.create(project_id=project.id, title="t", mode="discover")
        svc.transition(task_id=task.id, to_state="active")
        svc.transition(task_id=task.id, to_state="cancelled")
        session.commit()
        assert session.get(ResearchTask, task.id).workflow_state == "cancelled"  # type: ignore[union-attr]


class TestClosureAndContracts:
    """AT-0201-2/3: closure decisions, contracts, reopen isolation."""

    def _make(self, session: Session) -> tuple[ServiceContext, ServiceContext, Project]:
        ws = Workspace(slug="w", display_name="W")
        session.add(ws)
        session.flush()
        researcher = _principal(session, ws, "user", "researcher", "r")
        reviewer = _principal(session, ws, "user", "scientific_reviewer", "sr")
        project = _project(session, ws)
        return _ctx(session, ws, researcher), _ctx(session, ws, reviewer), project

    def test_close_requires_awaiting_review(self, session: Session) -> None:
        ctx_r, ctx_rev, project = self._make(session)
        svc = TaskService(session, ctx_rev)
        task = TaskService(session, ctx_r).create(project_id=project.id, title="t", mode="discover")
        session.commit()
        with pytest.raises(DomainError) as exc:
            svc.close(task_id=task.id, closure_decision="stopped")
        assert exc.value.code == ErrorCode.VALIDATION

    def test_full_close_reopen_new_contract_keeps_link(self, session: Session) -> None:
        ctx_r, ctx_rev, project = self._make(session)
        svc_r = TaskService(session, ctx_r)
        svc_rev = TaskService(session, ctx_rev)
        task = svc_r.create(project_id=project.id, title="t", mode="discover")
        session.commit()
        task_id = task.id

        # contract A frozen — canonical success contract (PAR-01)
        rev_a = svc_r.draft_contract(
            task_id=task_id,
            payload={
                "metrics": [
                    {
                        "id": "m.gloss",
                        "label": "gloss",
                        "required": True,
                        "value_kind": "numeric",
                        "operator": "gte",
                        "target_values": ["80"],
                        "unit": "dimensionless",
                        "required_evidence": ["lab_measurement"],
                        "aggregation": "fixture-single-value",
                    }
                ],
                "hard_constraints": [],
            },
        )
        svc_r.freeze_contract(revision_id=rev_a.id)
        session.commit()
        contract_a = rev_a.id

        # active -> awaiting_review -> closed — the unmeasured
        # experiment's honest closure label is
        # inconclusive (PAR-04 §6: supported_failure beyond the
        # evaluator's suggestion needs rationale + bound evidence)
        svc_r.transition(task_id=task_id, to_state="active")
        svc_r.transition(task_id=task_id, to_state="awaiting_review")
        svc_rev.close(task_id=task_id, closure_decision="inconclusive")
        session.commit()
        row = session.get(ResearchTask, task_id)
        assert row is not None
        assert row.workflow_state == "closed"
        assert row.closure_decision == "inconclusive"
        closure = session.execute(
            select(TaskDecision).where(
                TaskDecision.task_id == task_id, TaskDecision.kind == "closure"
            )
        ).scalar_one()
        assert closure.payload["contractRevisionId"] == str(contract_a)
        assert closure.payload["closureDecision"] == "inconclusive"

        # reopen → new cycle, old packet retained
        svc_r.reopen(task_id=task_id, reason="new evidence arrived")
        session.commit()
        row = session.get(ResearchTask, task_id)
        assert row is not None
        assert row.workflow_state == "active"
        assert row.closure_decision is None
        assert row.evaluation_cycle == 2

        # contract B frozen — original closure still points at A
        rev_b = svc_r.draft_contract(
            task_id=task_id,
            payload={
                "metrics": [
                    {
                        "id": "m.gloss",
                        "label": "gloss",
                        "required": True,
                        "value_kind": "numeric",
                        "operator": "gte",
                        "target_values": ["90"],
                        "unit": "dimensionless",
                        "required_evidence": ["lab_measurement"],
                        "aggregation": "fixture-single-value",
                    }
                ],
                "hard_constraints": [],
            },
        )
        svc_r.freeze_contract(revision_id=rev_b.id)
        session.commit()
        row = session.get(ResearchTask, task_id)
        assert row is not None and row.current_contract_revision_id == rev_b.id
        old_contract = session.get(SuccessContractRevision, contract_a)
        assert old_contract is not None and old_contract.status == "superseded"
        closure_again = session.execute(
            select(TaskDecision).where(
                TaskDecision.task_id == task_id, TaskDecision.kind == "closure"
            )
        ).scalar_one()
        assert closure_again.payload["contractRevisionId"] == str(contract_a)
        reopen_decision = session.execute(
            select(TaskDecision).where(
                TaskDecision.task_id == task_id, TaskDecision.kind == "reopen"
            )
        ).scalar_one()
        assert reopen_decision.payload["priorClosure"]["contractRevisionId"] == str(contract_a)

    def test_agent_cannot_close(self, session: Session) -> None:
        """AT-0201-3: an agent-proposed success still requires human
        review — an agent principal is denied at the service layer."""
        ws = Workspace(slug="w", display_name="W")
        session.add(ws)
        session.flush()
        researcher = _principal(session, ws, "user", "researcher", "r")
        agent = _principal(session, ws, "agent", "agent", "bot")
        project = _project(session, ws)
        ctx_r = _ctx(session, ws, researcher)
        svc = TaskService(session, ctx_r)
        task = svc.create(project_id=project.id, title="t", mode="discover")
        svc.transition(task_id=task.id, to_state="active")
        svc.transition(task_id=task.id, to_state="awaiting_review")
        session.commit()

        ctx_agent = _ctx(session, ws, agent)
        svc_agent = TaskService(session, ctx_agent)
        with pytest.raises(DomainError) as exc:
            svc_agent.close(task_id=task.id, closure_decision="supported_success")
        assert exc.value.code == ErrorCode.FORBIDDEN

        # a human without review_science is also denied
        with pytest.raises(DomainError) as exc:
            svc.close(task_id=task.id, closure_decision="supported_success")
        assert exc.value.code == ErrorCode.FORBIDDEN

    def test_supported_success_needs_frozen_contract_evidence(self, session: Session) -> None:
        """Evidence gate: frozen contract + reviewed measurements for
        required metrics. An agent can't reach it; a reviewer can but
        is blocked without evidence (AT-0201-3)."""
        ctx_r, ctx_rev, project = self._make(session)
        svc_r = TaskService(session, ctx_r)
        svc_rev = TaskService(session, ctx_rev)
        task = svc_r.create(project_id=project.id, title="t", mode="discover")
        svc_r.transition(task_id=task.id, to_state="active")
        svc_r.transition(task_id=task.id, to_state="awaiting_review")
        session.commit()
        # no contract at all → EVIDENCE_INSUFFICIENT
        with pytest.raises(DomainError) as exc:
            svc_rev.close(task_id=task.id, closure_decision="supported_success")
        assert exc.value.code == ErrorCode.EVIDENCE_INSUFFICIENT

        # frozen contract requiring metrics → still insufficient
        rev = svc_r.draft_contract(
            task_id=task.id,
            payload={
                "metrics": [
                    {
                        "id": "metric.synthetic",
                        "label": "Synthetic index",
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
        )
        svc_r.freeze_contract(revision_id=rev.id)
        session.commit()
        with pytest.raises(DomainError) as exc:
            svc_rev.close(task_id=task.id, closure_decision="supported_success")
        assert exc.value.code == ErrorCode.EVIDENCE_INSUFFICIENT
        unmet = exc.value.safe_details.get("unmet")
        assert unmet and unmet[0]["metric"] == "metric.synthetic"

        # accepted measurement attributed to the metric → gate passes
        ex = LabExecution(workspace_id=task.workspace_id, task_id=task.id, status="in_progress")
        session.add(ex)
        session.flush()
        batch = LabBatch(workspace_id=task.workspace_id, execution_id=ex.id, label="A")
        session.add(batch)
        session.flush()
        sample = LabSample(
            workspace_id=task.workspace_id, batch_id=batch.id, label="a1", kind="aliquot"
        )
        session.add(sample)
        session.flush()
        session.add(
            Measurement(
                workspace_id=task.workspace_id,
                sample_id=sample.id,
                method="fixture-index",
                metric="metric.synthetic",
                repeat_type="independent_batch",
                value_type="numeric",
                value={"kind": "numeric", "value": "6", "unit": "dimensionless"},
                status="accepted",
            )
        )
        session.commit()
        svc_rev.close(task_id=task.id, closure_decision="supported_success")
        session.commit()
        row = session.get(ResearchTask, task.id)
        assert row is not None and row.closure_decision == "supported_success"

    def test_non_success_closures_allowed_for_reviewer(self, session: Session) -> None:
        ctx_r, ctx_rev, project = self._make(session)
        task = TaskService(session, ctx_r).create(project_id=project.id, title="t", mode="discover")
        svc_r = TaskService(session, ctx_r)
        svc_r.transition(task_id=task.id, to_state="active")
        svc_r.transition(task_id=task.id, to_state="awaiting_review")
        TaskService(session, ctx_rev).close(task_id=task.id, closure_decision="inconclusive")
        session.commit()
        assert (
            session.get(ResearchTask, task.id).closure_decision == "inconclusive"  # type: ignore[union-attr]
        )


class TestLifecycleThroughGraphQL:
    """End-to-end through the mutations (AT-0201-1/2 transport)."""

    def test_transition_close_reopen_via_graphql(self, db_url: str, session: Session) -> None:
        client = _client(db_url)
        _setup_owner(client)
        ws = session.query(Workspace).one()
        project = _project(session, ws)
        session.commit()

        created = _gql(
            client,
            "mutation($input: TaskCreateInput!) { taskCreate(input: $input) "
            "{ task { id workflowState } errors { code } } }",
            {"input": {"projectId": _gid("Project", project.id), "title": "g", "mode": "discover"}},
        )["data"]["taskCreate"]
        task_gid = created["task"]["id"]

        trans = (
            "mutation($input: TaskTransitionInput!) { taskTransition(input: $input) "
            "{ task { workflowState evaluationCycle } errors { code message } } }"
        )
        for state in ("active", "awaiting_review"):
            out = _gql(
                client,
                trans,
                {"input": {"taskId": task_gid, "toState": state}},
            )["data"]["taskTransition"]
            assert out["errors"] == [], out

        # contract draft + freeze
        draft = _gql(
            client,
            "mutation($input: ContractDraftCreateInput!) { contractDraftCreate(input: $input) "
            "{ contractRevision { id revision status } errors { code } } }",
            {
                "input": {
                    "taskId": task_gid,
                    "payload": {
                        "metrics": [
                            {
                                "id": "m.t",
                                "label": "t",
                                "required": True,
                                "value_kind": "numeric",
                                "operator": "gte",
                                "target_values": ["1"],
                                "unit": "dimensionless",
                                "required_evidence": ["lab_measurement"],
                                "aggregation": "fixture-single-value",
                            }
                        ],
                        "hard_constraints": [],
                    },
                }
            },
        )["data"]["contractDraftCreate"]
        assert draft["errors"] == []
        rev_gid = draft["contractRevision"]["id"]
        frozen = _gql(
            client,
            "mutation($input: ContractFreezeInput!) { contractFreeze(input: $input) "
            "{ contractRevision { id status } errors { code } } }",
            {"input": {"revisionId": rev_gid}},
        )["data"]["contractFreeze"]
        assert frozen["errors"] == []
        assert frozen["contractRevision"]["status"] == "frozen"

        closed = _gql(
            client,
            "mutation($input: TaskCloseInput!) { taskClose(input: $input) "
            "{ task { workflowState closureDecision } errors { code } } }",
            {"input": {"taskId": task_gid, "closureDecision": "stopped"}},
        )["data"]["taskClose"]
        assert closed["errors"] == []
        assert closed["task"]["workflowState"] == "closed"

        reopened = _gql(
            client,
            "mutation($input: TaskReopenInput!) { taskReopen(input: $input) "
            "{ task { workflowState evaluationCycle } errors { code } } }",
            {"input": {"taskId": task_gid, "reason": "new data"}},
        )["data"]["taskReopen"]
        assert reopened["errors"] == []
        assert reopened["task"]["workflowState"] == "active"
        assert reopened["task"]["evaluationCycle"] == 2

        # decisions connection carries the closure w/ its contract
        decs = _gql(
            client,
            "query($id: ID!) { taskDecisions(taskId: $id) { edges { node { kind payload } } } }",
            {"id": task_gid},
        )["data"]["taskDecisions"]["edges"]
        kinds = {e["node"]["kind"] for e in decs}
        assert {"closure", "reopen"} <= kinds
