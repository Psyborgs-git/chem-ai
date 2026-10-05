"""CS-0101 acceptance tests — persistence & revision foundation.

AT-0101-1  accepted revision in-place edit fails; supersede required
AT-0101-2  two writers, same expected version → one REVISION_CONFLICT
AT-0101-3  cross-workspace foreign reference rejected by scope FK
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from studio.errors import ErrorCode
from studio.persistence.models import (
    Principal,
    Project,
    ResearchTask,
    SuccessContractRevision,
    Workspace,
)
from studio.persistence.revisions import (
    compare_and_swap,
    content_hash,
    next_revision,
)

pytestmark = pytest.mark.integration


def _scope(session: Session, slug: str = "ws") -> tuple[Workspace, Principal, Project]:
    ws = Workspace(slug=slug, display_name=slug)
    session.add(ws)
    session.flush()  # materialize ws.id for dependents
    p = Principal(
        workspace_id=ws.id,
        kind="user",
        login=f"u-{slug}",
        display_name="U",
    )
    proj = Project(workspace_id=ws.id, slug=f"p-{slug}", name="P")
    session.add_all([p, proj])
    session.flush()
    return ws, p, proj


def _task(session: Session, ws: Workspace, proj: Project) -> ResearchTask:
    task = ResearchTask(
        workspace_id=ws.id,
        project_id=proj.id,
        mode="improve",
        title="t",
        workflow_state="draft",
    )
    session.add(task)
    session.flush()
    return task


def _contract(
    session: Session,
    ws: Workspace,
    task: ResearchTask,
    payload: dict,
    status: str = "draft",
) -> SuccessContractRevision:
    rev = SuccessContractRevision(
        workspace_id=ws.id,
        task_id=task.id,
        revision=next_revision(session, SuccessContractRevision, "task_id", task.id),
        status=status,
        payload=payload,
        content_hash=content_hash(payload),
    )
    session.add(rev)
    session.flush()
    return rev


class TestMigrations:
    def test_upgrade_empty_database(self, db_url: str) -> None:
        """conftest already ran upgrade head on an empty DB — reaching
        here proves migrations apply cleanly."""
        assert db_url.startswith("postgresql")

    def test_populated_roundtrip(self, session: Session) -> None:
        ws, _p, proj = _scope(session)
        task = _task(session, ws, proj)
        rev = _contract(session, ws, task, {"objective": "x"})
        session.commit()
        assert rev.revision == 1 and rev.content_hash


class TestImmutableAcceptedRevision:
    """AT-0101-1."""

    def test_payload_edit_on_frozen_revision_fails(self, session: Session) -> None:
        ws, _p, proj = _scope(session)
        task = _task(session, ws, proj)
        rev = _contract(
            session,
            ws,
            task,
            {"objective": "v1"},
            status="frozen",
        )
        session.commit()

        with pytest.raises(DBAPIError, match="immutable_revision"):
            session.execute(
                update(SuccessContractRevision)
                .where(SuccessContractRevision.id == rev.id)
                .values(payload={"objective": "tampered"})
            )
        session.rollback()

        # delete of an accepted revision also fails
        with pytest.raises(DBAPIError, match="immutable_revision"):
            session.execute(
                delete(SuccessContractRevision).where(SuccessContractRevision.id == rev.id)
            )
        session.rollback()

    def test_supersede_is_the_only_allowed_transition(self, session: Session) -> None:
        ws, _p, proj = _scope(session)
        task = _task(session, ws, proj)
        rev = _contract(session, ws, task, {"objective": "v1"}, status="frozen")
        session.commit()

        session.execute(
            update(SuccessContractRevision)
            .where(SuccessContractRevision.id == rev.id)
            .values(status="superseded")
        )
        session.commit()
        session.refresh(rev)
        assert rev.status == "superseded"
        assert rev.payload == {"objective": "v1"}  # untouched

        # and the superseding revision is a NEW row/revision
        rev2 = _contract(session, ws, task, {"objective": "v2"}, status="frozen")
        session.commit()
        assert rev2.revision == 2 and rev2.id != rev.id


class TestOptimisticLocking:
    """AT-0101-2."""

    def test_second_writer_gets_revision_conflict(self, session: Session) -> None:
        _ws, _p, proj = _scope(session)
        session.commit()
        assert proj.version == 1

        compare_and_swap(session, Project, proj.id, 1, {"name": "writer-1"})
        session.commit()

        from studio.errors import DomainError

        with pytest.raises(DomainError) as exc:
            compare_and_swap(session, Project, proj.id, 1, {"name": "writer-2"})
        assert exc.value.code == ErrorCode.REVISION_CONFLICT

        session.refresh(proj)
        assert proj.name == "writer-1" and proj.version == 2


class TestScopeIntegrity:
    """AT-0101-3."""

    def test_cross_workspace_reference_rejected(self, session: Session) -> None:
        ws_a, _pa, proj_a = _scope(session, "a")
        ws_b, _pb, _proj_b = _scope(session, "b")
        task_a = _task(session, ws_a, proj_a)
        session.commit()

        # task belongs to ws_a; a revision claiming ws_b scope must fail
        bad = SuccessContractRevision(
            workspace_id=ws_b.id,
            task_id=task_a.id,
            revision=1,
            status="draft",
            payload={},
            content_hash="0" * 64,
        )
        session.add(bad)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

    def test_task_in_wrong_workspace_project_rejected(self, session: Session) -> None:
        _ws_a, _pa, proj_a = _scope(session, "a2")
        ws_b, _pb, _proj_b2 = _scope(session, "b2")
        session.commit()

        bad_task = ResearchTask(
            workspace_id=ws_b.id,
            project_id=proj_a.id,
            mode="discover",
            title="x",
            workflow_state="draft",
        )
        session.add(bad_task)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


class TestNumericDecimals:
    """NUMERIC storage sanity (§5.3) — decimal payloads round-trip."""

    def test_decimal_strings_stay_exact_in_jsonb(self, session: Session) -> None:
        ws, _p, proj = _scope(session, "d")
        task = _task(session, ws, proj)
        payload = {"declared_total": "1.000000", "fraction": "0.250000"}
        rev = _contract(session, ws, task, payload, status="frozen")
        session.commit()
        session.refresh(rev)
        assert rev.payload["declared_total"] == "1.000000"
