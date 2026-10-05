"""CS-0105 acceptance tests — commands, approvals, outbox.

AT-0105-1  same key + same payload → original result, no duplicates
AT-0105-2  same key + different payload → IDEMPOTENCY_MISMATCH
AT-0105-3  bound input/recipient/budget changed → APPROVAL_STALE blocks
           (also: expiry, revocation, missing approval)

Plus: transactional outbox (dedupe per consumer) and minimal audit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.testclient import TestClient
from strawberry import relay

from studio.api.app import create_app
from studio.application.approvals import grant, require_valid, revoke
from studio.application.idempotency import canonical_json, request_digest, run_idempotent
from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext, load_context
from studio.config.settings import Settings
from studio.errors import DomainError, ErrorCode
from studio.events.outbox import deliver_pending, publish
from studio.persistence.models import (
    Approval,
    AuditEvent,
    IdempotencyRecord,
    OutboxDelivery,
    OutboxEvent,
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
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


class TestIdempotentCommands:
    """AT-0105-1/2 at the command layer and through GraphQL."""

    def test_same_key_same_payload_replays_result(self, session: Session) -> None:
        ws = Workspace(slug="w", display_name="W")
        session.add(ws)
        session.flush()
        p = _principal(session, ws, "user", "researcher", "r")
        ctx = _ctx(session, ws, p)
        calls: list[int] = []

        def fn() -> dict[str, Any]:
            calls.append(1)
            return {"taskId": str(uuid.uuid4())}

        first = run_idempotent(session, ctx, operation="op", key="k1", payload={"a": 1}, fn=fn)
        session.commit()
        second = run_idempotent(session, ctx, operation="op", key="k1", payload={"a": 1}, fn=fn)
        session.commit()
        assert first == second
        assert len(calls) == 1, "fn must not re-run on replay"
        records = session.execute(select(func.count(IdempotencyRecord.id))).scalar_one()
        assert records == 1

    def test_same_key_different_payload_mismatch(self, session: Session) -> None:
        ws = Workspace(slug="w", display_name="W")
        session.add(ws)
        session.flush()
        p = _principal(session, ws, "user", "researcher", "r")
        ctx = _ctx(session, ws, p)
        run_idempotent(
            session,
            ctx,
            operation="op",
            key="k1",
            payload={"a": 1},
            fn=lambda: {"ok": True},
        )
        session.commit()
        with pytest.raises(DomainError) as exc:
            run_idempotent(
                session,
                ctx,
                operation="op",
                key="k1",
                payload={"a": 2},
                fn=lambda: {"ok": True},
            )
        assert exc.value.code == ErrorCode.IDEMPOTENCY_MISMATCH

    def test_task_create_idempotent_end_to_end(self, db_url: str, session: Session) -> None:
        client = _client(db_url)
        _setup_owner(client)
        ws = session.query(Workspace).one()
        project = Project(workspace_id=ws.id, slug="p", name="P")
        session.add(project)
        session.commit()

        mutation = (
            "mutation($input: TaskCreateInput!) { taskCreate(input: $input) "
            "{ task { id title } errors { code } } }"
        )
        variables = {
            "input": {
                "projectId": _gid("Project", project.id),
                "title": "Idem",
                "mode": "improve",
                "idempotencyKey": "k-1",
            }
        }
        first = _gql(client, mutation, variables)["data"]["taskCreate"]
        second = _gql(client, mutation, variables)["data"]["taskCreate"]
        assert first["task"]["id"] == second["task"]["id"]
        count = session.execute(select(func.count(ResearchTask.id))).scalar_one()
        assert count == 1
        # the single task produced exactly one outbox event
        events = session.execute(select(func.count(OutboxEvent.id))).scalar_one()
        assert events == 1

        mismatch = _gql(
            client,
            mutation,
            {
                "input": {
                    "projectId": _gid("Project", project.id),
                    "title": "Changed",
                    "mode": "improve",
                    "idempotencyKey": "k-1",
                }
            },
        )["data"]["taskCreate"]
        assert mismatch["task"] is None
        assert mismatch["errors"][0]["code"] == "IDEMPOTENCY_MISMATCH"

    def test_task_create_writes_outbox_and_audit(self, db_url: str, session: Session) -> None:
        client = _client(db_url)
        _setup_owner(client)
        ws = session.query(Workspace).one()
        project = Project(workspace_id=ws.id, slug="p", name="P")
        session.add(project)
        session.commit()
        out = _gql(
            client,
            "mutation($input: TaskCreateInput!) { taskCreate(input: $input) "
            "{ task { id } errors { code } } }",
            {
                "input": {
                    "projectId": _gid("Project", project.id),
                    "title": "T",
                    "mode": "discover",
                }
            },
        )["data"]["taskCreate"]
        assert out["errors"] == []
        task_id = relay.GlobalID.from_id(out["task"]["id"]).node_id

        ev = session.execute(select(OutboxEvent)).scalar_one()
        assert ev.event_type == "task.created"
        assert str(ev.aggregate_id) == task_id
        au = session.execute(
            select(AuditEvent).where(AuditEvent.action == "task.create")
        ).scalar_one()
        assert str(au.target_id) == task_id
        # audit carries metadata only — no title/objective payload
        assert au.detail is not None and "title" not in au.detail


class TestOutboxDelivery:
    """At-least-once with per-consumer dedupe (§7.4)."""

    def test_dedupe_per_consumer(self, session: Session) -> None:
        ws = Workspace(slug="w", display_name="W")
        session.add(ws)
        session.flush()
        ev = publish(
            session,
            ws.id,
            aggregate_type="task",
            aggregate_id=uuid.uuid4(),
            event_type="task.created",
            payload={"x": 1},
        )
        session.commit()

        seen: list[uuid.UUID] = []
        n = deliver_pending(session, ws.id, consumer="indexer", handler=lambda e: seen.append(e.id))
        session.commit()
        assert n == 1 and seen == [ev.id]
        # redelivery attempt → dedupe row blocks a second handler call
        n2 = deliver_pending(
            session, ws.id, consumer="indexer", handler=lambda e: seen.append(e.id)
        )
        session.commit()
        assert n2 == 0 and seen == [ev.id]
        assert session.execute(select(func.count(OutboxDelivery.event_id))).scalar_one() == 1

    def test_independent_consumers_each_receive(self, session: Session) -> None:
        ws = Workspace(slug="w", display_name="W")
        session.add(ws)
        session.flush()
        publish(
            session,
            ws.id,
            aggregate_type="task",
            aggregate_id=uuid.uuid4(),
            event_type="task.created",
            payload={},
        )
        session.commit()
        a: list[int] = []
        b: list[int] = []
        deliver_pending(session, ws.id, consumer="a", handler=lambda e: a.append(1))
        deliver_pending(session, ws.id, consumer="b", handler=lambda e: b.append(1))
        session.commit()
        assert len(a) == 1 and len(b) == 1

    def test_event_survives_only_with_its_state(self, session: Session) -> None:
        """Rollback of the domain change removes the outbox row too —
        no phantom events (§7.4 transactional guarantee)."""
        ws = Workspace(slug="w", display_name="W")
        session.add(ws)
        session.flush()
        publish(
            session,
            ws.id,
            aggregate_type="task",
            aggregate_id=uuid.uuid4(),
            event_type="x",
            payload={},
        )
        session.rollback()
        assert session.execute(select(func.count(OutboxEvent.id))).scalar_one() == 0


class TestApprovalEnvelopes:
    """AT-0105-3: stale/expired/revoked approvals block execution."""

    def _ctx_with_approver(self, session: Session) -> tuple[Workspace, ServiceContext]:
        ws = Workspace(slug="w", display_name="W")
        session.add(ws)
        session.flush()
        p = _principal(session, ws, "user", "scientific_reviewer", "sr")
        return ws, _ctx(session, ws, p)

    def _inputs(self) -> dict[str, Any]:
        return {
            "revisionId": str(uuid.uuid4()),
            "contractRevisionId": str(uuid.uuid4()),
            "methodVersion": "m1",
            "recipient": "lab-operator-1",
            "budget": {"samples": 3},
        }

    def test_valid_then_stale_blocks(self, session: Session) -> None:
        _, ctx = self._ctx_with_approver(session)
        inputs = self._inputs()
        grant(
            session,
            ctx,
            action="experiment_release",
            bound_inputs=inputs,
            envelope={"samples": 3},
        )
        session.commit()
        # same bound inputs → approval valid
        ap = require_valid(session, ctx, action="experiment_release", bound_inputs=inputs)
        assert ap.decision == "approved"
        # changed revision → stale
        changed = dict(inputs, revisionId=str(uuid.uuid4()))
        with pytest.raises(DomainError) as exc:
            require_valid(session, ctx, action="experiment_release", bound_inputs=changed)
        assert exc.value.code == ErrorCode.APPROVAL_STALE
        # changed recipient → stale
        changed = dict(inputs, recipient="someone-else")
        with pytest.raises(DomainError) as exc:
            require_valid(session, ctx, action="experiment_release", bound_inputs=changed)
        assert exc.value.code == ErrorCode.APPROVAL_STALE
        # changed budget → stale
        changed = dict(inputs, budget={"samples": 99})
        with pytest.raises(DomainError) as exc:
            require_valid(session, ctx, action="experiment_release", bound_inputs=changed)
        assert exc.value.code == ErrorCode.APPROVAL_STALE

    def test_expired_approval_blocks(self, session: Session) -> None:
        _, ctx = self._ctx_with_approver(session)
        inputs = self._inputs()
        grant(
            session,
            ctx,
            action="experiment_release",
            bound_inputs=inputs,
            ttl_seconds=1,
        )
        session.commit()
        later = datetime.now(UTC) + timedelta(seconds=5)
        with pytest.raises(DomainError) as exc:
            require_valid(
                session,
                ctx,
                action="experiment_release",
                bound_inputs=inputs,
                now=later,
            )
        assert exc.value.code == ErrorCode.APPROVAL_EXPIRED

    def test_revoked_approval_blocks(self, session: Session) -> None:
        _, ctx = self._ctx_with_approver(session)
        inputs = self._inputs()
        ap = grant(session, ctx, action="experiment_release", bound_inputs=inputs)
        revoke(session, ctx, approval_id=ap.id)
        session.commit()
        with pytest.raises(DomainError) as exc:
            require_valid(session, ctx, action="experiment_release", bound_inputs=inputs)
        assert exc.value.code == ErrorCode.FORBIDDEN

    def test_missing_approval_blocks(self, session: Session) -> None:
        _, ctx = self._ctx_with_approver(session)
        with pytest.raises(DomainError) as exc:
            require_valid(
                session,
                ctx,
                action="experiment_release",
                bound_inputs=self._inputs(),
            )
        assert exc.value.code == ErrorCode.FORBIDDEN

    def test_agent_cannot_grant_approval(self, session: Session) -> None:
        ws = Workspace(slug="w", display_name="W")
        session.add(ws)
        session.flush()
        agent = _principal(session, ws, "agent", "agent", "bot")
        ctx = _ctx(session, ws, agent)
        with pytest.raises(DomainError) as exc:
            grant(
                session,
                ctx,
                action="experiment_release",
                bound_inputs=self._inputs(),
            )
        assert exc.value.code == ErrorCode.FORBIDDEN

    def test_rejected_decision_never_validates(self, session: Session) -> None:
        _, ctx = self._ctx_with_approver(session)
        inputs = self._inputs()
        grant(
            session,
            ctx,
            action="experiment_release",
            bound_inputs=inputs,
            decision="rejected",
        )
        session.commit()
        with pytest.raises(DomainError) as exc:
            require_valid(session, ctx, action="experiment_release", bound_inputs=inputs)
        assert exc.value.code == ErrorCode.FORBIDDEN


class TestAuditTrail:
    def test_audit_is_minimal_metadata(self, session: Session) -> None:
        ws = Workspace(slug="w", display_name="W")
        session.add(ws)
        session.flush()
        p = _principal(session, ws, "user", "researcher", "r")
        ctx = _ctx(session, ws, p)
        audit_record(
            session,
            ctx,
            action="artifact.download",
            target_type="artifact",
            target_id=uuid.uuid4(),
            detail={"mediaType": "application/pdf", "payload": "should-drop"},
        )
        session.commit()
        row = session.execute(select(AuditEvent)).scalar_one()
        assert row.action == "artifact.download"
        assert row.detail == {"mediaType": "application/pdf"}

    def test_canonical_digest_stability(self) -> None:
        a = {"x": 1, "y": [2, 3], "z": {"n": "v"}}
        b = {"z": {"n": "v"}, "y": [2, 3], "x": 1}
        assert canonical_json(a) == canonical_json(b)
        assert request_digest(a) == request_digest(b)
        assert request_digest(a) != request_digest({"x": 2})


class TestApprovalWorkspaceIsolation:
    def test_approval_not_visible_cross_workspace(self, session: Session) -> None:
        ws_a = Workspace(slug="a", display_name="A")
        ws_b = Workspace(slug="b", display_name="B")
        session.add_all([ws_a, ws_b])
        session.flush()
        approver_a = _principal(session, ws_a, "user", "scientific_reviewer", "a")
        reviewer_b = _principal(session, ws_b, "user", "scientific_reviewer", "b")
        ctx_a = _ctx(session, ws_a, approver_a)
        inputs = {"revisionId": str(uuid.uuid4())}
        grant(session, ctx_a, action="experiment_release", bound_inputs=inputs)
        session.commit()
        ctx_b = _ctx(session, ws_b, reviewer_b)
        with pytest.raises(DomainError) as exc:
            require_valid(session, ctx_b, action="experiment_release", bound_inputs=inputs)
        assert exc.value.code == ErrorCode.FORBIDDEN
        approvals_in_b = session.execute(
            select(func.count(Approval.id)).where(Approval.workspace_id == ws_b.id)
        ).scalar_one()
        assert approvals_in_b == 0
