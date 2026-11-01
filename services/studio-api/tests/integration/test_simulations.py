from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from studio.auth.context import ServiceContext
from studio.config.settings import Settings
from studio.domain.simulations.dispatcher import SimulationDispatcher
from studio.domain.simulations.models import SimulationJob
from studio.domain.simulations.service import PET_REPEAT, SimulationService, job_directory
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import Principal, Workspace

pytestmark = pytest.mark.integration


def _services(session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "studio.domain.simulations.service.runtime_capability", lambda: {"available": True}
    )
    workspace = Workspace(slug=f"md-{uuid.uuid4().hex[:8]}", display_name="MD private")
    session.add(workspace)
    session.flush()
    settings = Settings(vault_root=tmp_path)
    services = []
    for name in ("one", "two"):
        owner = Principal(workspace_id=workspace.id, login=name, display_name=name, kind="user")
        session.add(owner)
        session.flush()
        ctx = ServiceContext(session, workspace.id, owner.id, "user", frozenset())
        services.append(SimulationService(session, ctx, settings))
    return services


def test_md_jobs_artifacts_cancellation_and_resume_remain_owner_private(
    session, tmp_path, monkeypatch
):
    one, two = _services(session, tmp_path, monkeypatch)
    result = one.create_job({"repeatSmiles": PET_REPEAT})
    assert result["state"] == "queued" and result["trainingEligible"] is False
    assert two.list_jobs() == []
    for method in (two.get_job, two.cancel_job, two.resume_job):
        with pytest.raises(DomainError) as denied:
            method(result["id"])
        assert denied.value.code == ErrorCode.NOT_FOUND
    job = session.get(SimulationJob, uuid.UUID(result["id"]))
    directory = job_directory(one.settings, job)
    directory.mkdir(parents=True)
    (directory / "raw.log").write_text("Real engine artifact placeholder for ACL test")
    assert one.artifact_path(result["id"], "raw.log").read_text().startswith("Real")
    with pytest.raises(DomainError):
        one.artifact_path(result["id"], "../../outside")
    outside = tmp_path / "outside-secret"
    outside.write_text("outside")
    (directory / "link").symlink_to(outside)
    with pytest.raises(DomainError):
        one.artifact_path(result["id"], "link")
    assert one.cancel_job(result["id"])["state"] == "cancelled"
    assert one.resume_job(result["id"])["state"] == "queued"
    job.state, job.elapsed_seconds = "timed_out", 1800.0
    with pytest.raises(DomainError, match="budget"):
        one.resume_job(result["id"])


def test_dispatch_claim_refuses_parallel_heavy_md_jobs(session, db_url, tmp_path, monkeypatch):
    one, _ = _services(session, tmp_path, monkeypatch)
    first = one.create_job({"repeatSmiles": PET_REPEAT})
    one.create_job({"repeatSmiles": PET_REPEAT})
    session.commit()
    engine = create_engine(db_url)
    factory = sessionmaker(engine, expire_on_commit=False)
    dispatcher = SimulationDispatcher(factory, one.settings)
    assert str(dispatcher._claim()) == first["id"]
    assert dispatcher._claim() is None
    engine.dispose()


def test_real_native_dispatch_cancel_and_resume_from_stage_checkpoint(
    session, db_url, tmp_path, monkeypatch
):
    import os
    import threading
    import time

    if os.environ.get("STUDIO_SIMULATION_REAL_TEST") != "1":
        pytest.skip("Set STUDIO_SIMULATION_REAL_TEST=1 with the isolated native simulation runtime")
    one, _ = _services(session, tmp_path, monkeypatch)
    result = one.create_job(
        {
            "repeatSmiles": PET_REPEAT,
            "repeats": 2,
            "chains": 2,
            "protocolScale": 0.001,
            "samplingSteps": 10000,
            "maxWallSeconds": 120,
        }
    )
    session.commit()
    engine = create_engine(db_url)
    factory = sessionmaker(engine, expire_on_commit=False)
    dispatcher = SimulationDispatcher(factory, one.settings)
    identifier = dispatcher._claim()
    assert identifier is not None
    job = session.get(SimulationJob, identifier)
    directory = job_directory(one.settings, job)
    thread = threading.Thread(target=dispatcher._execute, args=(identifier,))
    thread.start()
    deadline = time.monotonic() + 30
    checkpoint = directory / "seed-1729/stage-2.json"
    while not checkpoint.exists() and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert checkpoint.exists(), "Real MD did not complete the compression stage"
    one.cancel_job(result["id"])
    session.commit()
    thread.join(timeout=15)
    assert not thread.is_alive()
    session.expire_all()
    stopped = one.get_job(result["id"])
    assert stopped["state"] == "cancelled" and stopped["elapsedSeconds"] > 0
    assert list(directory.rglob("*.rst")) and list(directory.rglob("*.xtc"))
    one.resume_job(result["id"])
    session.commit()
    assert dispatcher._claim() == identifier
    dispatcher._execute(identifier)
    session.expire_all()
    finished = one.get_job(result["id"])
    assert finished["state"] == "completed", finished
    assert finished["result"]["numericallyStable"] is True
    assert finished["trainingEligible"] is False
    assert len(finished["result"]["seeds"]) == 2
    assert any(e["phase"] == "resuming_seed" for e in finished["events"])
    assert all(seed["atoms"] <= 2000 for seed in finished["result"]["seeds"])
    engine.dispose()


def test_failed_simulation_resume_requires_checkpoint_and_preserves_total_cap(
    session, tmp_path, monkeypatch
):
    import json

    from rdkit import Chem

    one, _ = _services(session, tmp_path, monkeypatch)
    result = one.create_job({"repeatSmiles": PET_REPEAT})
    job = session.get(SimulationJob, uuid.UUID(result["id"]))
    job.state, job.elapsed_seconds = "failed", 800.0
    job.result = {"elapsedSeconds": 800.0, "error": "Native process finalization exit 15"}
    with pytest.raises(DomainError, match="no completed stage checkpoint"):
        one.resume_job(result["id"])
    directory = job_directory(one.settings, job) / "seed-1729"
    directory.mkdir(parents=True)
    (directory / "stage-checkpoint.json").write_text(json.dumps({"stage": 2, "seed": 1729}))
    (directory / "stage-2.json").write_text(Chem.MolsToJSON([Chem.MolFromSmiles("CC")]))
    resumed = one.resume_job(result["id"])
    assert resumed["state"] == "queued"
    assert job.config["maxWallSeconds"] == 1800
    assert job.elapsed_seconds == 800.0
    job.state, job.elapsed_seconds = "failed", 1800.0
    with pytest.raises(DomainError, match="budget"):
        one.resume_job(result["id"])
