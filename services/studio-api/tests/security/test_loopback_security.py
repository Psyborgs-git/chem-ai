"""CS-0102 acceptance tests — capabilities & loopback security.

AT-0102-1  viewer/agent principal invoking approval → server denies
AT-0102-2  foreign-origin state-changing request → rejected, no change
AT-0102-3  cross-workspace principal → no content/existence leak
"""

from __future__ import annotations

import pytest
from chem_studio_policy.capabilities import (
    CAP_APPROVE_EXPERIMENT,
    CAP_APPROVE_EXPORT,
    CAP_APPROVE_MODEL,
    CAP_READ_PROJECT,
    Grant,
    capabilities_for_role,
    effective_grants,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from studio.api.app import create_app
from studio.auth.context import load_context
from studio.auth.setup import create_owner
from studio.config.settings import Settings
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Principal,
    PrincipalCapability,
    Project,
    Workspace,
)

pytestmark = pytest.mark.security


def _ws(session: Session, slug: str) -> Workspace:
    ws = Workspace(slug=slug, display_name=slug)
    session.add(ws)
    session.flush()
    return ws


def _principal_with_role(
    session: Session, ws: Workspace, kind: str, role: str, login: str
) -> Principal:
    p = Principal(workspace_id=ws.id, kind=kind, login=login, display_name=login)
    session.add(p)
    session.flush()
    for cap in sorted(capabilities_for_role(role)):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=p.id, capability=cap))
    session.flush()
    return p


class TestCapabilityDenial:
    """AT-0102-1: approval capabilities denied for viewer/agent."""

    def test_viewer_cannot_approve(self, session: Session) -> None:
        ws = _ws(session, "v1")
        viewer = _principal_with_role(session, ws, "user", "viewer", "v")
        ctx = load_context(session, ws.id, viewer.id)
        for cap in (CAP_APPROVE_EXPERIMENT, CAP_APPROVE_EXPORT, CAP_APPROVE_MODEL):
            with pytest.raises(DomainError) as exc:
                ctx.require(cap)
            assert exc.value.code == ErrorCode.FORBIDDEN

    def test_agent_never_holds_approval_even_if_granted(self, session: Session) -> None:
        ws = _ws(session, "a1")
        agent = _principal_with_role(session, ws, "agent", "agent", "bot")
        # Directly grant an approval capability to prove the ceiling.
        session.add(
            PrincipalCapability(
                workspace_id=ws.id,
                principal_id=agent.id,
                capability=CAP_APPROVE_EXPERIMENT,
            )
        )
        session.flush()
        ctx = load_context(session, ws.id, agent.id)
        assert CAP_APPROVE_EXPERIMENT not in {g.capability for g in ctx.grants}
        with pytest.raises(DomainError) as exc:
            ctx.require(CAP_APPROVE_EXPERIMENT)
        assert exc.value.code == ErrorCode.FORBIDDEN

    def test_agent_ceiling_is_pure(self) -> None:
        grants = frozenset({Grant(CAP_READ_PROJECT), Grant(CAP_APPROVE_MODEL)})
        assert {g.capability for g in effective_grants("agent", grants)} == {CAP_READ_PROJECT}


class TestLoopbackTransport:
    """AT-0102-2: foreign origin on a state-changing request."""

    def _client(self, db_url: str) -> TestClient:
        app = create_app(Settings(database_url=db_url))
        return TestClient(app)

    def test_foreign_origin_rejected_without_state_change(
        self, db_url: str, session: Session
    ) -> None:
        client = self._client(db_url)
        resp = client.post(
            "/api/auth/setup",
            json={
                "login": "owner",
                "display_name": "Owner",
                "password": "correct horse battery staple",
            },
            headers={
                "origin": "https://attacker.example",
                "host": "127.0.0.1:8787",
            },
        )
        assert resp.status_code == 403
        # No state change: no principal was created.
        count = session.execute(select(func.count(Principal.id))).scalar_one()
        assert count == 0

    def test_foreign_host_header_rejected(self, db_url: str) -> None:
        client = self._client(db_url)
        resp = client.post(
            "/api/auth/setup",
            json={
                "login": "owner",
                "display_name": "Owner",
                "password": "correct horse battery staple",
            },
            headers={"host": "studio.evil.example"},
        )
        assert resp.status_code == 403

    def test_same_origin_setup_and_login_flow(self, db_url: str) -> None:
        client = self._client(db_url)
        headers = {
            "origin": "http://127.0.0.1:8787",
            "host": "127.0.0.1:8787",
        }
        resp = client.post(
            "/api/auth/setup",
            json={
                "login": "owner",
                "display_name": "Owner",
                "password": "correct horse battery staple",
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert "studio_session" in resp.cookies
        # Second setup is refused.
        again = client.post(
            "/api/auth/setup",
            json={
                "login": "other",
                "display_name": "O",
                "password": "correct horse battery staple",
            },
            headers=headers,
        )
        assert again.status_code == 409


class TestCrossScopeDenial:
    """AT-0102-3: no protected content/existence leak across scopes."""

    def test_foreign_principal_cannot_load_context(self, session: Session) -> None:
        ws_a = _ws(session, "sa")
        ws_b = _ws(session, "sb")
        p_a = _principal_with_role(session, ws_a, "user", "researcher", "pa")
        session.commit()
        with pytest.raises(DomainError) as exc:
            load_context(session, ws_b.id, p_a.id)
        assert exc.value.code == ErrorCode.UNAUTHENTICATED

    def test_workspace_scoped_queries_isolate_projects(self, session: Session) -> None:
        ws_a = _ws(session, "iso-a")
        ws_b = _ws(session, "iso-b")
        session.add(Project(workspace_id=ws_a.id, slug="pa", name="A"))
        session.flush()
        visible_in_b = (
            session.execute(select(Project).where(Project.workspace_id == ws_b.id)).scalars().all()
        )
        assert visible_in_b == []

    def test_owner_setup_one_time(self, session: Session) -> None:
        ws = _ws(session, "own")
        create_owner(session, ws, "owner", "Owner", "long-enough-password")
        session.commit()
        with pytest.raises(DomainError) as exc:
            create_owner(session, ws, "second", "Second", "another-password1")
        assert exc.value.code == ErrorCode.CONFLICT
