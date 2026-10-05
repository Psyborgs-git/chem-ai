"""CS-0104 acceptance tests — GraphQL Node/Relay foundation.

AT-0104-1  canonical GlobalID roundtrip: node(id) + mutation return
AT-0104-2  bounded keyset pagination; scoped/signed cursors; no
           backward pagination; foreign-scope cursor rejected
AT-0104-3  Relay boundary: one transport, one environment, no second
           server-state cache (frontend test + static check; the
           request-scoped DB close is proven here)

Scoping: every node/connection resolution is workspace-bound — foreign
IDs resolve to null with no existence leak.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session
from starlette.testclient import TestClient
from strawberry import relay

from studio.api.app import create_app
from studio.auth.sessions import issue_session
from studio.config.settings import Settings
from studio.persistence.models import (
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


def _project(session: Session, ws: Workspace, slug: str, name: str = "P") -> Project:
    p = Project(workspace_id=ws.id, slug=slug, name=name)
    session.add(p)
    session.flush()
    return p


def _principal(session: Session, ws: Workspace, kind: str, role: str, login: str) -> Principal:
    p = Principal(workspace_id=ws.id, kind=kind, login=login, display_name=login)
    session.add(p)
    session.flush()
    for cap in sorted(capabilities_for_role(role)):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=p.id, capability=cap))
    session.flush()
    return p


class TestNodeRoundtrip:
    """AT-0104-1: canonical IDs decode to the same scoped record."""

    def test_node_roundtrip_task(self, db_url: str, session: Session) -> None:
        client = _client(db_url)
        _setup_owner(client)
        ws = session.query(Workspace).one()
        project = _project(session, ws, "p1")
        task = ResearchTask(
            workspace_id=ws.id,
            project_id=project.id,
            mode="improve",
            title="T1",
        )
        session.add(task)
        session.commit()

        gid = _gid("Task", task.id)
        out = _gql(
            client,
            "query($id: ID!) { node(id: $id) { id ... on Task { title mode } } }",
            {"id": gid},
        )
        assert "errors" not in out, out
        assert out["data"]["node"]["id"] == gid
        assert out["data"]["node"]["title"] == "T1"

    def test_nodes_mixed_and_foreign_null(self, db_url: str, session: Session) -> None:
        client = _client(db_url)
        _setup_owner(client)
        ws = session.query(Workspace).one()
        ws_b = Workspace(slug="ws-b", display_name="B")
        session.add(ws_b)
        session.flush()
        mine = _project(session, ws, "mine")
        foreign = _project(session, ws_b, "foreign")
        session.commit()

        out = _gql(
            client,
            "query($ids: [ID!]!) { nodes(ids: $ids) { id ... on Project { slug } } }",
            {"ids": [_gid("Project", mine.id), _gid("Project", foreign.id)]},
        )
        assert "errors" not in out, out
        nodes = out["data"]["nodes"]
        assert nodes[0]["slug"] == "mine"
        # foreign workspace ID → null, no existence leak
        assert nodes[1] is None

    def test_node_foreign_workspace_null(self, db_url: str, session: Session) -> None:
        client = _client(db_url)
        _setup_owner(client)
        ws_b = Workspace(slug="ws-b", display_name="B")
        session.add(ws_b)
        session.flush()
        foreign = _project(session, ws_b, "foreign")
        session.commit()

        out = _gql(
            client,
            "query($id: ID!) { node(id: $id) { id ... on Project { slug } } }",
            {"id": _gid("Project", foreign.id)},
        )
        assert "errors" not in out, out
        assert out["data"]["node"] is None

    def test_unauthenticated_node_query_errors(self, db_url: str) -> None:
        client = _client(db_url)
        out = _gql(
            client,
            'query { node(id: "UHJvamVjdDox") { id } }',
        )
        assert "errors" in out

    def test_engine_and_hardware_capability_reports(self, db_url: str) -> None:
        client = _client(db_url)
        _setup_owner(client)
        out = _gql(
            client,
            "{ engineCapabilities { core { status } training { status } } "
            "hardwareCapabilities { os arch gpu } }",
        )
        assert "errors" not in out, out
        caps = out["data"]["engineCapabilities"]
        assert caps["core"]["status"] in {"available", "ready"}
        assert "status" in caps["training"]


class TestKeysetPagination:
    """AT-0104-2: bounded forward pagination with bound cursors."""

    def _seed(self, client: TestClient, session: Session, n: int) -> list[Project]:
        _setup_owner(client)
        ws = session.query(Workspace).one()
        projects = [_project(session, ws, f"p{i}") for i in range(n)]
        session.commit()
        return projects

    def test_forward_pagination_no_duplicates(self, db_url: str, session: Session) -> None:
        client = _client(db_url)
        self._seed(client, session, 3)
        q = (
            "query($first: Int, $after: String) { projects(first: $first, after: $after) "
            "{ edges { cursor node { slug } } pageInfo { hasNextPage endCursor } } }"
        )
        first = _gql(client, q, {"first": 2})
        assert "errors" not in first, first
        page = first["data"]["projects"]
        assert len(page["edges"]) == 2
        assert page["pageInfo"]["hasNextPage"] is True

        second = _gql(client, q, {"first": 2, "after": page["pageInfo"]["endCursor"]})
        assert "errors" not in second, second
        seen = {e["node"]["slug"] for e in page["edges"]}
        for e in second["data"]["projects"]["edges"]:
            assert e["node"]["slug"] not in seen
        assert second["data"]["projects"]["pageInfo"]["hasNextPage"] is False

    def test_backward_pagination_rejected(self, db_url: str, session: Session) -> None:
        client = _client(db_url)
        self._seed(client, session, 1)
        out = _gql(client, "{ projects(last: 1) { edges { cursor } } }")
        assert "errors" in out
        assert "backward" in out["errors"][0]["message"].lower()

    def test_page_size_bounded(self, db_url: str, session: Session) -> None:
        client = _client(db_url)
        self._seed(client, session, 1)
        out = _gql(client, "{ projects(first: 500) { edges { cursor } } }")
        assert "errors" in out

    def test_foreign_scope_cursor_rejected(self, db_url: str, session: Session) -> None:
        """A cursor minted for workspace A's projects is rejected when
        replayed under workspace B's session (§8.1 scope binding)."""
        client = _client(db_url)
        self._seed(client, session, 2)
        page = _gql(client, "{ projects(first: 1) { edges { cursor } } }")
        cursor = page["data"]["projects"]["edges"][0]["cursor"]

        ws_b = Workspace(slug="ws-b", display_name="B")
        session.add(ws_b)
        session.flush()
        _project(session, ws_b, "b1")
        other = _principal(session, ws_b, "user", "researcher", "rb")
        issued = issue_session(session, ws_b.id, other, 43200)
        session.commit()

        client_b = _client(db_url)
        out = client_b.post(
            "/graphql",
            json={
                "query": "query($after: String) { projects(first: 1, after: $after) "
                "{ edges { cursor } } }",
                "variables": {"after": cursor},
            },
            headers={**HEADERS, "authorization": f"Bearer {issued.token}"},
        )
        body = out.json()
        assert "errors" in body
        assert "cursor" in body["errors"][0]["message"].lower()

    def test_cross_connection_cursor_rejected(self, db_url: str, session: Session) -> None:
        """A `projects` cursor does not replay against `projectTasks`."""
        client = _client(db_url)
        projects = self._seed(client, session, 2)
        ws = session.query(Workspace).one()
        t = ResearchTask(workspace_id=ws.id, project_id=projects[0].id, mode="improve", title="T")
        session.add(t)
        session.commit()
        page = _gql(client, "{ projects(first: 1) { edges { cursor } } }")
        cursor = page["data"]["projects"]["edges"][0]["cursor"]
        out = _gql(
            client,
            "query($pid: ID!, $after: String) { projectTasks(projectId: $pid, "
            "first: 1, after: $after) { edges { cursor } } }",
            {"pid": _gid("Project", projects[0].id), "after": cursor},
        )
        assert "errors" in out
        assert "cursor" in out["errors"][0]["message"].lower()

    def test_project_tasks_scoped_to_workspace(self, db_url: str, session: Session) -> None:
        client = _client(db_url)
        _setup_owner(client)
        ws_b = Workspace(slug="ws-b", display_name="B")
        session.add(ws_b)
        session.flush()
        foreign = _project(session, ws_b, "fproj")
        session.commit()
        out = _gql(
            client,
            "query($pid: ID!) { projectTasks(projectId: $pid) { edges { node { title } } } }",
            {"pid": _gid("Project", foreign.id)},
        )
        assert "errors" not in out, out
        assert out["data"]["projectTasks"]["edges"] == []


class TestTaskCreateMutation:
    """AT-0104-1: mutation returns the canonical ID; domain errors are
    typed payloads, not transport failures (§8.3)."""

    def test_task_create_returns_canonical_id(self, db_url: str, session: Session) -> None:
        client = _client(db_url)
        _setup_owner(client)
        ws = session.query(Workspace).one()
        project = _project(session, ws, "p1")
        session.commit()

        out = _gql(
            client,
            "mutation($input: TaskCreateInput!) { taskCreate(input: $input) "
            "{ task { id title mode workflowState } errors { code } } }",
            {
                "input": {
                    "projectId": _gid("Project", project.id),
                    "title": "Improve gloss",
                    "mode": "improve",
                }
            },
        )
        assert "errors" not in out, out
        result = out["data"]["taskCreate"]
        assert result["errors"] == []
        task_id = result["task"]["id"]
        decoded = relay.GlobalID.from_id(task_id)
        assert decoded.type_name == "Task"
        row = session.get(ResearchTask, uuid.UUID(decoded.node_id))
        assert row is not None and row.title == "Improve gloss"

    def test_task_create_denied_without_capability(self, db_url: str, session: Session) -> None:
        client = _client(db_url)
        _setup_owner(client)
        ws = session.query(Workspace).one()
        project = _project(session, ws, "p1")
        viewer = _principal(session, ws, "user", "viewer", "v")
        issued = issue_session(session, ws.id, viewer, 43200)
        session.commit()

        # extract_token prefers the cookie — clear the owner session so
        # the viewer bearer token is used.
        client.cookies.clear()
        resp = client.post(
            "/graphql",
            json={
                "query": "mutation($input: TaskCreateInput!) { taskCreate(input: $input) "
                "{ task { id } errors { code } } }",
                "variables": {
                    "input": {
                        "projectId": _gid("Project", project.id),
                        "title": "x",
                        "mode": "improve",
                    }
                },
            },
            headers={**HEADERS, "authorization": f"Bearer {issued.token}"},
        )
        body = resp.json()
        result = body["data"]["taskCreate"]
        assert result["task"] is None
        assert result["errors"][0]["code"] == "FORBIDDEN"

    def test_task_create_validation_errors(self, db_url: str, session: Session) -> None:
        client = _client(db_url)
        _setup_owner(client)
        ws = session.query(Workspace).one()
        project = _project(session, ws, "p1")
        session.commit()
        out = _gql(
            client,
            "mutation($input: TaskCreateInput!) { taskCreate(input: $input) "
            "{ task { id } errors { code fieldPath } } }",
            {
                "input": {
                    "projectId": _gid("Project", project.id),
                    "title": "x",
                    "mode": "teleport",
                }
            },
        )
        result = out["data"]["taskCreate"]
        assert result["task"] is None
        assert result["errors"][0]["code"] == "VALIDATION"
        assert result["errors"][0]["fieldPath"] == "input.mode"


class TestRequestDbLifecycle:
    """The request-scoped GraphQL session is always closed (§8.2)."""

    def test_request_session_closed(self, db_url: str) -> None:
        app = create_app(Settings(database_url=db_url))
        client = TestClient(app)
        _setup_owner(client)
        closed: list[bool] = []
        sessions: list[Session] = []
        orig = app.state.session_factory

        def spy() -> Session:
            s: Session = orig()
            real_close = s.close
            index = len(closed)
            closed.append(False)
            sessions.append(s)

            def close() -> None:  # type: ignore[no-untyped-def]
                closed[index] = True
                real_close()

            s.close = close  # type: ignore[method-assign]
            return s

        app.state.session_factory = spy  # type: ignore[assignment]
        out = _gql(client, "{ viewer { id displayName } }")
        assert "errors" not in out, out
        assert sessions, "GraphQL request should open a session"
        assert all(closed)
