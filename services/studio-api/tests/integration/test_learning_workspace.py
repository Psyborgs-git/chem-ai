from __future__ import annotations

import io
import json
import uuid
import zipfile

import pytest

from studio.auth.context import ServiceContext
from studio.config.settings import Settings
from studio.domain.learning.workspace import LearningWorkspaceService
from studio.domain.learning.workspace_runtime.models import LearningJob, LearningModel
from studio.domain.learning.workspace_runtime.remote import (
    complete,
    heartbeat,
    lease,
    model_archive,
)
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import Principal, Workspace

pytestmark = pytest.mark.integration


def _env(db, tmp_path):
    workspace = Workspace(slug="learning-private", display_name="Private Learning")
    db.add(workspace)
    db.flush()
    services = []
    for login in ("owner-one", "owner-two"):
        user = Principal(workspace_id=workspace.id, kind="user", login=login, display_name=login)
        db.add(user)
        db.flush()
        ctx = ServiceContext(db, workspace.id, user.id, "user", frozenset())
        services.append(LearningWorkspaceService(db, ctx, Settings(vault_root=tmp_path)))
    return services


def _dataset(service, **overrides):
    return service.import_dataset(
        {
            "name": "Custom molecules",
            "format": "csv",
            "content": "smiles,target\nCCO,1\nCC,2\nCCN,3\nCO,4\n",
            "dataKind": "experimental",
            "rights": "owned",
            "source": {"file": "our-measurements.csv"},
            **overrides,
        }
    )


def test_datasets_and_jobs_are_owner_private_even_in_the_same_workspace(session, tmp_path):
    first, second = _env(session, tmp_path)
    dataset = _dataset(first)
    assert second.list_datasets() == []
    with pytest.raises(DomainError) as denied:
        second.get_dataset(dataset["id"])
    assert denied.value.code == ErrorCode.NOT_FOUND
    with pytest.raises(DomainError):
        second.freeze_dataset(dataset["id"])
    frozen = first.freeze_dataset(dataset["id"])
    assert frozen["partitions"]["final"] == 1
    job = first.create_job(
        {
            "kind": "chemprop",
            "datasetId": dataset["id"],
            "config": {"executionTarget": "remote", "maxSteps": 1},
        }
    )
    assert job["state"] == "queued"
    assert second.list_jobs() == []
    with pytest.raises(DomainError):
        second.cancel_job(job["id"])
    assert lease(second, {"workerId": "worker-two", "backends": ["chemprop"]})["jobId"] is None
    leased = lease(first, {"workerId": "worker-one", "backends": ["chemprop"]})
    assert leased["jobId"] == job["id"]
    assert len(leased["request"]["rows"]) == 4
    with pytest.raises(DomainError):
        heartbeat(first, job["id"], {"workerId": "another-worker"})
    first.cancel_job(job["id"])
    assert heartbeat(first, job["id"], {"workerId": "worker-one"})["cancelRequested"]


def test_unknown_rights_block_freeze_and_custom_data_never_claims_validation(session, tmp_path):
    first, _second = _env(session, tmp_path)
    dataset = _dataset(first, rights="unknown", dataKind="literature")
    assert dataset["report"]["scientificStatus"] == "not_validated"
    with pytest.raises(DomainError) as denied:
        first.freeze_dataset(dataset["id"])
    assert denied.value.code == ErrorCode.DATA_RIGHTS_UNKNOWN


def test_remote_upload_rejects_paths_before_persisting_artifacts(session, tmp_path):
    first, _second = _env(session, tmp_path)
    dataset = _dataset(first)
    first.freeze_dataset(dataset["id"])
    job = first.create_job(
        {"kind": "chemprop", "datasetId": dataset["id"], "config": {"executionTarget": "remote"}}
    )
    lease(first, {"workerId": "worker-one", "backends": ["chemprop"]})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../not-allowed", "secret")
    with pytest.raises(DomainError, match="Unsafe artifact"):
        complete(
            first, job["id"], {"workerId": "worker-one", "result": {"ok": True}}, buffer.getvalue()
        )
    assert not (tmp_path / "not-allowed").exists()
    row = session.get(LearningJob, uuid.UUID(job["id"]))
    assert row.state == "running"


def test_worker_actual_process_reports_missing_runtime_instead_of_success(tmp_path):
    import subprocess
    import sys

    # Native real process path, using a deliberately invalid job schema; no mock training result.
    request = {"kind": "chemprop", "config": {"backend": "chemprop"}, "rows": [], "splits": {}}
    (tmp_path / "request.json").write_text(json.dumps(request))
    subprocess.run(  # noqa: S603 — fixed real worker process
        [sys.executable, "-m", "studio.domain.learning.workspace_runtime.worker", str(tmp_path)],
        capture_output=True,
        timeout=20,
        check=False,
    )
    result = json.loads((tmp_path / "result.json").read_text())
    assert result["ok"] is False
    assert "error" in result
    assert "artifacts" not in result


def test_notebook_opt_out_blocks_frozen_dataset_training(session, tmp_path):
    from studio.domain.library.models import Notebook
    from studio.domain.library.service import LibraryService

    first, _second = _env(session, tmp_path)
    library = LibraryService(session, first.ctx, vault_root=tmp_path)
    notebook = library.create_notebook("Private chemistry notes")
    page = library.create_page(
        notebook["id"], "Ethanol", content={"markdown": "The SMILES is CCO."}
    )
    dataset = first.import_notebook({"pageIds": [page["id"]]})
    assert dataset["dataKind"] == "user_authored"
    first.freeze_dataset(dataset["id"])
    row = session.get(Notebook, uuid.UUID(notebook["id"]))
    row.training_enabled = False
    session.flush()
    with pytest.raises(DomainError, match="no longer enabled"):
        first.create_job({"kind": "chemprop", "datasetId": dataset["id"]})


def test_model_activation_requires_own_independent_evaluation_and_explicit_human_approval(
    session, tmp_path
):
    first, second = _env(session, tmp_path)
    model = LearningModel(
        workspace_id=first.ctx.workspace_id,
        owner_id=first.ctx.principal_id,
        name="Fixture adapter",
        backend="mlx",
        location=str(tmp_path),
        details={"state": "ready", "license": "owned"},
    )
    session.add(model)
    session.flush()
    evaluation = LearningJob(
        workspace_id=first.ctx.workspace_id,
        owner_id=first.ctx.principal_id,
        name="Fixture matched evaluation",
        kind="evaluate",
        model_id=model.id,
        state="completed",
        config={},
        result={
            "ok": True,
            "partition": "final",
            "matchedExamples": 2,
            "baseExactMatch": 0.5,
            "candidateExactMatch": 0.5,
        },
        events=[],
    )
    session.add(evaluation)
    session.flush()
    with pytest.raises(DomainError, match="approval"):
        first.activate_model(str(model.id), {"evaluationJobId": str(evaluation.id)})
    with pytest.raises(DomainError):
        second.activate_model(
            str(model.id), {"approved": True, "evaluationJobId": str(evaluation.id)}
        )
    evaluation.result = {"ok": True, "partition": "train", "matchedExamples": 2}
    with pytest.raises(DomainError, match="held-out"):
        first.activate_model(
            str(model.id), {"approved": True, "evaluationJobId": str(evaluation.id)}
        )
    evaluation.result = {
        "ok": True,
        "partition": "final",
        "matchedExamples": 2,
        "baseExactMatch": 0.5,
        "candidateExactMatch": 0.5,
    }
    activated = first.activate_model(
        str(model.id), {"approved": True, "evaluationJobId": str(evaluation.id)}
    )
    assert activated["details"]["active"] is True
    assert activated["details"]["review"]["evaluationJobId"] == str(evaluation.id)


def test_local_model_tool_calls_are_parsed_and_limited_to_the_supplied_catalog(
    session, tmp_path, monkeypatch
):
    from studio.domain.learning.workspace_runtime import dispatcher

    first, second = _env(session, tmp_path)
    model = LearningModel(
        workspace_id=first.ctx.workspace_id,
        owner_id=first.ctx.principal_id,
        name="Fixture chat model",
        backend="mlx",
        location=str(tmp_path),
        details={"state": "ready", "license": "owned"},
    )
    session.add(model)
    session.flush()
    monkeypatch.setattr(
        dispatcher,
        "run_preview",
        lambda *args, **kwargs: {
            "text": '<tool_call>{"name":"search_papers",'
            '"arguments":{"query":"ethanol"}}</tool_call>\n'
            '<tool_call>{"name":"delete_everything","arguments":{}}</tool_call>'
        },
    )
    response = first.infer_model(
        str(model.id),
        [{"role": "user", "content": "research ethanol"}],
        [{"type": "function", "function": {"name": "search_papers"}}],
    )
    calls = response["choices"][0]["message"]["tool_calls"]
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "search_papers"
    assert json.loads(calls[0]["function"]["arguments"]) == {"query": "ethanol"}
    with pytest.raises(DomainError):
        second.infer_model(str(model.id), [{"role": "user", "content": "read"}])


def test_low_disk_blocks_jobs_and_catalog_downloads_without_starting_workers(
    session, tmp_path, monkeypatch
):
    import studio.domain.learning.workspace as module

    first, _second = _env(session, tmp_path)
    monkeypatch.setattr(
        module,
        "storage_preflight",
        lambda _settings, required: {
            "available": False,
            "freeBytes": 1024,
            "requiredFreeBytes": required,
        },
    )
    dataset = _dataset(first)
    first.freeze_dataset(dataset["id"])
    job = first.create_job(
        {"kind": "chemprop", "datasetId": dataset["id"], "config": {"executionTarget": "remote"}}
    )
    assert job["state"] == "blocked"
    assert "disk" in job["error"]
    assert job["result"]["storagePreflight"]["freeBytes"] == 1024
    model = first.register_model({"catalogId": "qwen3-0.6b-mlx"})
    assert model["details"]["state"] == "blocked"
    download = first.get_job(model["downloadJobId"])
    assert download["state"] == "blocked"
    assert "disk" in download["error"]


def test_dataset_source_rights_are_rechecked_for_training_and_provider_transfer(session, tmp_path):
    from chem_studio_policy.capabilities import Grant

    from studio.persistence.models import Artifact

    first, _second = _env(session, tmp_path)
    ctx = ServiceContext(
        session,
        first.ctx.workspace_id,
        first.ctx.principal_id,
        "user",
        frozenset({Grant("read_project", None)}),
    )
    first = LearningWorkspaceService(session, ctx, first.settings)
    artifact = Artifact(
        workspace_id=ctx.workspace_id,
        storage_key="fixture",
        media_type="text/csv",
        byte_size=1,
        original_name="paper.csv",
        upload_state="committed",
        review_state="accepted",
        checksum_sha256="a" * 64,
        rights={"retrieval": "allowed", "training": "allowed", "export": "denied"},
    )
    session.add(artifact)
    session.flush()
    dataset = _dataset(first, source={"artifactId": str(artifact.id), "artifactChecksum": "a" * 64})
    assert first.authorize_dataset_training(dataset["id"])
    with pytest.raises(DomainError, match="provider transfer"):
        first.authorize_dataset_egress(dataset["id"])
    artifact.rights = {"retrieval": "allowed", "training": "allowed", "export": "allowed"}
    assert first.authorize_dataset_egress(dataset["id"])
    artifact.rights = {"retrieval": "allowed", "training": "denied", "export": "allowed"}
    with pytest.raises(DomainError, match="permit training"):
        first.authorize_dataset_training(dataset["id"])


def test_remote_worker_completion_registers_private_artifacts_and_rebuilds_paths(session, tmp_path):
    first, second = _env(session, tmp_path)
    dataset = _dataset(first)
    first.freeze_dataset(dataset["id"])
    job = first.create_job(
        {"kind": "chemprop", "datasetId": dataset["id"], "config": {"executionTarget": "remote"}}
    )
    leased = lease(first, {"workerId": "fixture-worker", "backends": ["chemprop"]})
    assert leased["jobId"] == job["id"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"fixture": True}))
        archive.writestr("model_0.pt", "fixture-weights")
    result = complete(
        first,
        job["id"],
        {
            "workerId": "fixture-worker",
            "result": {
                "ok": True,
                "location": "/another-owner/private",
                "baseLocation": "/unsafe",
                "active": True,
                "scope": {"name": "fixture", "unit": "1", "method": "fixture"},
                "modelDigest": "a" * 64,
            },
        },
        buffer.getvalue(),
    )
    assert result["state"] == "completed"
    model_id = result["result"]["registeredModelId"]
    model = first.get_model(model_id)
    assert model["location"].startswith(str(tmp_path))
    assert "active" not in model["details"]
    assert second.list_models() == []
    prediction = first.create_job(
        {
            "kind": "predict",
            "datasetId": dataset["id"],
            "modelId": model_id,
            "config": {"executionTarget": "remote"},
        }
    )
    next_lease = lease(first, {"workerId": "fixture-worker", "backends": ["chemprop"]})
    assert "location" not in next_lease["request"]["model"]
    assert next_lease["jobId"] == prediction["id"]
    archived = model_archive(first, prediction["id"], "fixture-worker")
    with zipfile.ZipFile(io.BytesIO(archived)) as archive:
        assert archive.read("model_0.pt") == b"fixture-weights"
