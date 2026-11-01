"""Durable browser calculations: real engine outputs and truthful lifecycle."""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from starlette.testclient import TestClient
from strawberry import relay
from workers.common.resources import HardwareReport

from engine_adapter_rdkit import EngineError, RDKitAdapter, StructuralResult
from studio.api.app import create_app
from studio.auth.context import load_context
from studio.config.settings import Settings
from studio.domain.runs.admission import AdmissionService
from studio.domain.runs.queue import RunService
from studio.domain.runs.structures import StructureRunService, input_summary
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Artifact,
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    ResourceGroup,
    ResourceReservation,
    Run,
    RunAttempt,
    Workspace,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def env(db_url: str, session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ws = Workspace(slug="structure-test", display_name="Structure test")
    session.add(ws)
    session.flush()
    principal = Principal(
        workspace_id=ws.id, kind="user", login="researcher", display_name="Researcher"
    )
    session.add(principal)
    session.flush()
    for capability in capabilities_for_role("researcher"):
        session.add(
            PrincipalCapability(
                workspace_id=ws.id, principal_id=principal.id, capability=capability
            )
        )
    project = Project(workspace_id=ws.id, slug="structures", name="Structures")
    session.add(project)
    session.flush()
    task = ResearchTask(
        workspace_id=ws.id, project_id=project.id, title="Molecule checks", mode="discover"
    )
    session.add(task)
    session.commit()
    engine = create_engine(db_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(database_url=db_url, vault_root=tmp_path / "vault")
    service = StructureRunService(factory, settings)
    monkeypatch.setattr(
        "studio.domain.runs.structures.detect",
        lambda: HardwareReport(
            os="test",
            arch="test",
            python_version="3.12",
            observed_at="now",
            cpu_count_logical=4,
            ram_total_bytes=8 * 1024**3,
            disk_free_bytes=8 * 1024**3,
        ),
    )
    yield {
        "service": service,
        "factory": factory,
        "ws": ws.id,
        "principal": principal.id,
        "task": task.id,
        "project": project.id,
        "settings": settings,
    }
    engine.dispose()


def launch(env: dict[str, Any], smiles: str = "CCO", key: str = "structure-test") -> uuid.UUID:
    return env["service"].describe(env["ws"], env["principal"], None, env["task"], smiles, key)


def test_persisted_input_results_and_idempotent_replay(env, monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    def describe(_self, *, smiles, cancel):
        calls.append(smiles)
        return StructuralResult(
            ok=True,
            canonical_smiles=smiles,
            formula="C2H6O",
            descriptors={"mw": 46.069},
            engine_version="test-engine",
            execution={"profile": "test"},
        )

    monkeypatch.setattr(RDKitAdapter, "describe", describe)
    run_id = launch(env)
    assert launch(env) == run_id
    assert calls == ["CCO"]
    with pytest.raises(DomainError) as exc:
        launch(env, smiles="O")
    assert exc.value.code == ErrorCode.IDEMPOTENCY_MISMATCH
    with env["factory"]() as db:
        run = db.get(Run, run_id)
        assert run.status == "succeeded"
        assert "smiles" not in run.request
        assert run.result_summary["descriptors"]["mw"] == 46.069
        assert run.result_summary["evidence_type"] == "descriptor"
        assert run.result_summary["scientific_status"] == "not_validated"
        assert db.scalar(select(func.count()).select_from(Artifact)) == 1
        assert db.scalar(select(func.count()).select_from(RunAttempt)) == 1
        assert db.scalar(select(ResourceReservation.status)) == "released"
        ctx = load_context(db, env["ws"], env["principal"])
        assert input_summary(db, env["service"].vault, ctx, run)["smiles"] == "CCO"


@pytest.mark.parametrize(
    "code,status",
    [("PARSE_FAILED", "failed"), ("ENGINE_UNAVAILABLE", "failed"), ("TIMED_OUT", "timed_out")],
)
def test_engine_errors_are_persisted_without_descriptors(
    env, monkeypatch: pytest.MonkeyPatch, code: str, status: str
):
    monkeypatch.setattr(
        RDKitAdapter,
        "describe",
        lambda *_args, **_kwargs: EngineError(code, "explicit engine failure", "parse"),
    )
    run_id = launch(env)
    with env["factory"]() as db:
        run = db.get(Run, run_id)
        assert run.status == status
        assert "descriptors" not in run.result_summary
        assert db.scalar(select(ResourceReservation.status)) == "released"


@pytest.mark.parametrize("smiles", ["", "\x00CCO", "C" * 8193, "\ud800CCO"])
def test_invalid_inputs_create_no_run(env, smiles: str):
    with pytest.raises(DomainError) as exc:
        launch(env, smiles=smiles)
    assert exc.value.code == ErrorCode.VALIDATION
    with env["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(Run)) == 0


def test_scope_and_compute_grant_checked_before_side_effects(env):
    with env["factory"]() as db:
        principal = db.get(Principal, env["principal"])
        for grant in db.scalars(
            select(PrincipalCapability).where(PrincipalCapability.principal_id == principal.id)
        ):
            db.delete(grant)
        db.commit()
    with pytest.raises(DomainError) as exc:
        launch(env)
    assert exc.value.code == ErrorCode.FORBIDDEN
    with env["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(Artifact)) == 0


def test_insufficient_capacity_records_blocked_run_without_execution(
    env, monkeypatch: pytest.MonkeyPatch
):
    with env["factory"]() as db:
        db.add(
            ResourceGroup(
                workspace_id=env["ws"],
                name="structure",
                capacity={"cpu_cores": 0, "memory_bytes": 0, "concurrency": 1},
                reserve={},
            )
        )
        db.commit()
    monkeypatch.setattr(
        RDKitAdapter, "describe", lambda *_args, **_kwargs: pytest.fail("blocked run executed")
    )
    run_id = launch(env)
    with env["factory"]() as db:
        run = db.get(Run, run_id)
        assert run.status == "blocked"
        assert run.error["message"] == "insufficient_local_resources"
        assert run.attempt_count == 0
        assert db.scalar(select(func.count()).select_from(ResourceReservation)) == 0


def test_foreign_task_refused_before_creating_artifact(env):
    with env["factory"]() as db:
        foreign_ws = Workspace(slug="foreign", display_name="Foreign")
        db.add(foreign_ws)
        db.flush()
        project = Project(workspace_id=foreign_ws.id, slug="foreign", name="Foreign")
        db.add(project)
        db.flush()
        task = ResearchTask(
            workspace_id=foreign_ws.id, project_id=project.id, title="Foreign", mode="discover"
        )
        db.add(task)
        db.commit()
        foreign_task_id = task.id
    with pytest.raises(DomainError) as exc:
        env["service"].describe(
            env["ws"], env["principal"], None, foreign_task_id, "CCO", "foreign"
        )
    assert exc.value.code == ErrorCode.NOT_FOUND
    with env["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(Artifact)) == 0


def test_changed_input_blob_fails_provenance_verification(env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        RDKitAdapter,
        "describe",
        lambda *_args, **_kwargs: EngineError("PARSE_FAILED", "invalid", "parse"),
    )
    run_id = launch(env)
    with env["factory"]() as db:
        run = db.get(Run, run_id)
        artifact = db.get(Artifact, uuid.UUID(run.request["inputArtifactId"]))
        env["service"].vault.blob_path(env["ws"], artifact.storage_key).write_bytes(
            b'{"smiles":"O"}'
        )
        ctx = load_context(db, env["ws"], env["principal"])
        with pytest.raises(DomainError) as exc:
            input_summary(db, env["service"].vault, ctx, run)
        assert exc.value.code == ErrorCode.PROVENANCE_UNKNOWN


@pytest.mark.parametrize("state", ["closed", "cancelled"])
def test_terminal_task_denies_new_calculation_but_allows_existing_replay(
    env, monkeypatch: pytest.MonkeyPatch, state: str
):
    monkeypatch.setattr(
        RDKitAdapter,
        "describe",
        lambda *_args, **_kwargs: EngineError("PARSE_FAILED", "invalid", "parse"),
    )
    run_id = launch(env)
    with env["factory"]() as db:
        db.get(ResearchTask, env["task"]).workflow_state = state
        db.commit()
    assert launch(env) == run_id
    with pytest.raises(DomainError) as exc:
        launch(env, key="new-calculation")
    assert exc.value.code == ErrorCode.CONFLICT
    with env["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(Artifact)) == 1
        assert db.scalar(select(func.count()).select_from(Run)) == 1


@pytest.mark.parametrize("cancel_requested", [False, True])
def test_abandoned_attempt_becomes_interrupted_without_retry(
    env, monkeypatch: pytest.MonkeyPatch, cancel_requested: bool
):
    with env["factory"]() as db:
        ctx = load_context(db, env["ws"], env["principal"])
        admission = AdmissionService(db, ctx)
        admission.ensure_group(
            "structure",
            capacity={
                "cpu_cores": 4,
                "memory_bytes": 8 * 1024**3,
                "storage_bytes": 8 * 1024**3,
                "concurrency": 1,
            },
        )
        runs = RunService(db, ctx)
        abandoned = runs.request(
            kind="rdkit_descriptors",
            task_id=env["task"],
            request={"test": "abandoned"},
            max_attempts=1,
        )
        assert admission.admit(
            abandoned.id, {"memory_bytes": 512 * 1024**2}, group_name="structure"
        ).admitted
        attempt = db.scalar(select(RunAttempt).where(RunAttempt.run_id == abandoned.id))
        runs.start_attempt(run_id=abandoned.id, attempt_id=attempt.id)
        attempt.started_at = datetime.now(UTC) - timedelta(seconds=120)
        if cancel_requested:
            runs.request_cancel(abandoned.id)
        db.commit()
        abandoned_id = abandoned.id
    monkeypatch.setattr(
        RDKitAdapter,
        "describe",
        lambda *_args, **_kwargs: EngineError("PARSE_FAILED", "invalid", "parse"),
    )
    launch(env)
    with env["factory"]() as db:
        abandoned = db.get(Run, abandoned_id)
        assert abandoned.status == "interrupted"
        assert abandoned.error["code"] == "worker_lost"
        assert abandoned.finished_at is not None
        assert abandoned.attempt_count == 1
        assert (
            db.scalar(select(RunAttempt.status).where(RunAttempt.run_id == abandoned_id))
            == "interrupted"
        )
        assert (
            db.scalar(
                select(ResourceReservation.status).where(ResourceReservation.run_id == abandoned_id)
            )
            == "released"
        )


def test_cancel_reaches_worker_before_terminal_confirmation(env, monkeypatch: pytest.MonkeyPatch):
    started = threading.Event()
    output: list[uuid.UUID] = []
    calls: list[str] = []

    def describe(_self, *, smiles, cancel):
        calls.append(smiles)
        started.set()
        assert cancel.wait(5), "persistent cancel request never reached worker"
        return EngineError("CANCELLED", "cancelled", "execution")

    monkeypatch.setattr(RDKitAdapter, "describe", describe)
    worker = threading.Thread(target=lambda: output.append(launch(env)))
    worker.start()
    assert started.wait(5)
    replay_id = launch(env)
    assert calls == ["CCO"]
    with env["factory"]() as db:
        ctx = load_context(db, env["ws"], env["principal"])
        run = db.scalar(select(Run))
        RunService(db, ctx).request_cancel(run.id)
        db.commit()
        assert run.status == "cancel_requested"
    worker.join(timeout=8)
    assert not worker.is_alive()
    with env["factory"]() as db:
        assert output[0] == replay_id
        assert db.get(Run, output[0]).status == "cancelled"
        assert db.scalar(select(ResourceReservation.status)) == "released"


def test_graphql_calculation_and_node_reload(env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        RDKitAdapter,
        "describe",
        lambda *_args, **_kwargs: StructuralResult(
            ok=True,
            canonical_smiles="CCO",
            formula="C2H6O",
            descriptors={"mw": 46.069},
            engine_version="test",
        ),
    )
    from studio.auth.sessions import issue_session

    with env["factory"]() as db:
        issued = issue_session(
            db,
            workspace_id=env["ws"],
            principal=db.get(Principal, env["principal"]),
            ttl_seconds=3600,
        )
        db.commit()
    headers = {"origin": "http://127.0.0.1:8787", "host": "127.0.0.1:8787"}
    with TestClient(create_app(env["settings"])) as client:
        client.cookies.set("studio_session", issued.token)
        response = client.post(
            "/graphql",
            headers=headers,
            json={
                "query": """mutation($i:DescribeStructureInput!){runs{
                    describeStructure(input:$i){
                      run{id taskId status inputSummary resultSummary}
                      errors{code message}
                    }}}""",
                "variables": {
                    "i": {
                        "taskId": str(relay.GlobalID("Task", str(env["task"]))),
                        "smiles": "CCO",
                        "idempotencyKey": "graphql-test",
                    }
                },
            },
        ).json()
        assert "errors" not in response, response
        result = response["data"]["runs"]["describeStructure"]
        assert result["errors"] == [], result
        run = result["run"]
        assert run["status"] == "succeeded"
        assert run["inputSummary"]["smiles"] == "CCO"
        reloaded = client.post(
            "/graphql",
            headers=headers,
            json={
                "query": "query($id:ID!){node(id:$id){...on Run{id status taskId resultSummary}}}",
                "variables": {"id": run["id"]},
            },
        ).json()
        assert reloaded["data"]["node"]["resultSummary"]["descriptors"]["mw"] == 46.069


@pytest.mark.engine
def test_real_ethanol_and_invalid_valence(env):
    if not RDKitAdapter().capability().available:
        pytest.skip("real RDKit unavailable")
    run_id = launch(env)
    bad_id = launch(env, smiles="C(C)(C)(C)(C)(C)", key="bad-valence")
    with env["factory"]() as db:
        run = db.get(Run, run_id)
        assert run.status == "succeeded"
        assert run.result_summary["structure"]["formula"] == "C2H6O"
        assert 45 < run.result_summary["descriptors"]["mw"] < 47
        assert run.result_summary["engine"]["version"]
        assert "<svg" in run.result_summary["structure"]["depiction_svg"]
        bad = db.get(Run, bad_id)
        assert bad.status == "failed"
        assert bad.error["code"] in {"PARSE_FAILED", "SANITIZE_FAILED"}
        assert "descriptors" not in bad.result_summary


def quick_launch(env, smiles="CCO", key="quick-test", project_id=None):
    return env["service"].quick_describe(env["ws"], env["principal"], None, smiles, key, project_id)


def _quick_result(_self, *, smiles, cancel):
    return StructuralResult(
        ok=True,
        canonical_smiles=smiles,
        formula="C2H6O",
        descriptors={"mw": 46.069},
        engine_version="test",
    )


def test_quick_first_submit_organizes_empty_workspace_and_replays(env, monkeypatch):
    with env["factory"]() as db:
        db.delete(db.get(ResearchTask, env["task"]))
        db.flush()
        db.delete(db.get(Project, env["project"]))
        db.commit()
    calls = []

    def describe(*args, **kwargs):
        calls.append(kwargs["smiles"])
        return _quick_result(*args, **kwargs)

    monkeypatch.setattr(RDKitAdapter, "describe", describe)
    run_id = quick_launch(env)
    assert quick_launch(env) == run_id
    assert calls == ["CCO"]
    with pytest.raises(DomainError) as exc:
        quick_launch(env, smiles="O")
    assert exc.value.code == ErrorCode.IDEMPOTENCY_MISMATCH
    with env["factory"]() as db:
        project = db.scalars(select(Project)).one()
        assert project.slug == "quick-calculations"
        assert project.name == "Quick calculations"
        task = db.scalars(select(ResearchTask)).one()
        assert task.project_id == project.id
        assert task.target_kind == "molecule"
        assert task.mode == "discover"
        assert "CCO" in task.title
        assert "no laboratory validation" in task.objective
        run = db.get(Run, run_id)
        assert run.task_id == task.id
        assert run.status == "succeeded"
        assert db.scalar(select(func.count()).select_from(Run)) == 1
        assert db.scalar(select(func.count()).select_from(Artifact)) == 1


def test_quick_selected_project_reuses_existing_scope(env, monkeypatch):
    monkeypatch.setattr(RDKitAdapter, "describe", _quick_result)
    run_id = quick_launch(env, project_id=env["project"])
    with env["factory"]() as db:
        run = db.get(Run, run_id)
        task = db.get(ResearchTask, run.task_id)
        assert task.project_id == env["project"]
        assert db.scalar(select(func.count()).select_from(Project)) == 1
        assert db.scalar(select(func.count()).select_from(ResearchTask)) == 2


def test_quick_concurrent_same_key_reuses_task_run_and_execution(env, monkeypatch):
    started, finish = threading.Event(), threading.Event()
    output = []
    calls = []

    def describe(*args, **kwargs):
        calls.append(kwargs["smiles"])
        started.set()
        assert finish.wait(8)
        return _quick_result(*args, **kwargs)

    monkeypatch.setattr(RDKitAdapter, "describe", describe)
    worker = threading.Thread(target=lambda: output.append(quick_launch(env)))
    worker.start()
    try:
        assert started.wait(8)
        replay_id = quick_launch(env)
        assert calls == ["CCO"]
    finally:
        finish.set()
        worker.join(timeout=10)
    assert not worker.is_alive()
    assert output == [replay_id]
    with env["factory"]() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Project)
                .where(Project.slug == "quick-calculations")
            )
            == 1
        )
        assert db.scalar(select(func.count()).select_from(ResearchTask)) == 2
        assert db.scalar(select(func.count()).select_from(Run)) == 1
        assert db.scalar(select(func.count()).select_from(RunAttempt)) == 1


def test_quick_concurrent_different_keys_share_one_default_project(env, monkeypatch):
    monkeypatch.setattr(RDKitAdapter, "describe", _quick_result)
    barrier = threading.Barrier(2)
    output = []
    errors = []

    def submit(key):
        try:
            barrier.wait(timeout=5)
            output.append(quick_launch(env, key=key))
        except Exception as exc:
            errors.append(exc)

    workers = [threading.Thread(target=submit, args=(f"concurrent-{i}",)) for i in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=12)
    assert not errors
    assert len(set(output)) == 2
    with env["factory"]() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Project)
                .where(Project.slug == "quick-calculations")
            )
            == 1
        )
        assert db.scalar(select(func.count()).select_from(ResearchTask)) == 3


@pytest.mark.parametrize("capability", ["edit_task", "request_compute", "read_project"])
def test_quick_required_permissions_precede_organization(env, capability):
    with env["factory"]() as db:
        grant = db.scalar(
            select(PrincipalCapability).where(
                PrincipalCapability.principal_id == env["principal"],
                PrincipalCapability.capability == capability,
            )
        )
        db.delete(grant)
        db.commit()
    with pytest.raises(DomainError) as exc:
        quick_launch(env)
    assert exc.value.code == ErrorCode.FORBIDDEN
    with env["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(Project)) == 1
        assert db.scalar(select(func.count()).select_from(ResearchTask)) == 1
        assert db.scalar(select(func.count()).select_from(Run)) == 0


def test_quick_foreign_project_is_not_accessible(env):
    with env["factory"]() as db:
        foreign = Workspace(slug="quick-foreign", display_name="Foreign")
        db.add(foreign)
        db.flush()
        project = Project(workspace_id=foreign.id, slug="foreign", name="Foreign")
        db.add(project)
        db.commit()
        foreign_id = project.id
    with pytest.raises(DomainError) as exc:
        quick_launch(env, project_id=foreign_id)
    assert exc.value.code == ErrorCode.NOT_FOUND
    with env["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(ResearchTask)) == 1
        assert db.scalar(select(func.count()).select_from(Run)) == 0


def test_quick_invalid_input_does_not_organize(env):
    with pytest.raises(DomainError) as exc:
        quick_launch(env, smiles="")
    assert exc.value.code == ErrorCode.VALIDATION
    with env["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(Project)) == 1
        assert db.scalar(select(func.count()).select_from(ResearchTask)) == 1


def test_quick_graphql_returns_real_run_contract(env, monkeypatch):
    from studio.auth.sessions import issue_session

    monkeypatch.setattr(RDKitAdapter, "describe", _quick_result)
    with env["factory"]() as db:
        issued = issue_session(
            db,
            workspace_id=env["ws"],
            principal=db.get(Principal, env["principal"]),
            ttl_seconds=3600,
        )
        db.commit()
    with TestClient(create_app(env["settings"])) as client:
        client.cookies.set("studio_session", issued.token)
        response = client.post(
            "/graphql",
            headers={"origin": "http://127.0.0.1:8787", "host": "127.0.0.1:8787"},
            json={
                "query": """mutation($input: QuickDescribeStructureInput!){runs{
            quickDescribeStructure(input:$input){
                run{id taskId status inputSummary} errors{code message}
            }
        }}""",
                "variables": {"input": {"smiles": "CCO", "idempotencyKey": "quick-graphql"}},
            },
        ).json()
        assert "errors" not in response, response
        result = response["data"]["runs"]["quickDescribeStructure"]
        assert result["errors"] == [], result
        assert result["run"]["status"] == "succeeded"
        assert result["run"]["taskId"]
        assert result["run"]["inputSummary"]["smiles"] == "CCO"
