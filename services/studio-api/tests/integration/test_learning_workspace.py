from __future__ import annotations

import io
import json
import uuid
import zipfile

import pytest

from studio.auth.context import ServiceContext
from studio.config.settings import Settings
from studio.domain.learning.workspace import LearningWorkspaceService
from studio.domain.learning.workspace_runtime.models import (
    LearningDataset,
    LearningJob,
    LearningModel,
)
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


def test_shared_preflight_blocks_unheldout_or_incompatible_training_before_queue(session, tmp_path):
    first, _second = _env(session, tmp_path)
    single = _dataset(first, content="smiles,target\nCC,1\n")
    first.freeze_dataset(single["id"])
    payload = {
        "kind": "chemprop",
        "datasetId": single["id"],
        "config": {"executionTarget": "remote"},
    }
    check = first.preflight(payload)
    assert check["ready"] is False
    assert any(item["id"] == "heldout" and item["status"] == "fail" for item in check["checks"])
    assert first.create_job(payload)["state"] == "blocked"
    invalid = first.preflight({**payload, "kind": "sft"})
    assert invalid["ready"] is False
    assert "model" in invalid["checks"][0]["message"]


def test_property_preflight_records_actual_fixed_engine_schedule(session, tmp_path):
    first, _second = _env(session, tmp_path)
    data = _dataset(first)
    first.freeze_dataset(data["id"])
    result = first.preflight(
        {
            "kind": "chemprop",
            "datasetId": data["id"],
            "config": {"executionTarget": "remote", "learningRate": 0.005},
        }
    )
    assert result["ready"]
    config = result["normalizedConfig"]
    assert "learningRate" not in config
    assert config["learningRateSchedule"] == {
        "engine": "chemprop-2.3.1-default",
        "initial": 0.0001,
        "maximum": 0.001,
        "final": 0.0001,
        "warmupEpochs": 2,
    }


@pytest.mark.parametrize("active_state", ["queued", "running"])
def test_catalog_repair_reuses_owned_pinned_model_path(session, tmp_path, active_state):
    first, second = _env(session, tmp_path)
    registered = first.register_model({"catalogId": "qwen3-4b-instruct-mlx"})
    model = session.get(LearningModel, uuid.UUID(registered["id"]))
    old_job = session.get(LearningJob, uuid.UUID(registered["downloadJobId"]))
    old_job.state = "completed"
    model.details = {**model.details, "state": "ready"}
    session.flush()
    payload = {"catalogId": "qwen3-4b-instruct-mlx", "repairModelId": registered["id"]}
    with pytest.raises(DomainError):
        second.register_model(payload)
    repaired = first.register_model(payload)
    assert repaired["id"] == registered["id"]
    assert repaired["location"] == registered["location"]
    assert repaired["downloadJobId"] != registered["downloadJobId"]
    # Optional download dependencies or disk space can leave the new job blocked.
    # Exercise the active-job guard independently of the host's download readiness.
    new_job = session.get(LearningJob, uuid.UUID(repaired["downloadJobId"]))
    assert new_job is not None
    new_job.state = active_state
    session.flush()
    with pytest.raises(DomainError, match="active job"):
        first.register_model(payload)
    with pytest.raises(DomainError, match="same pinned"):
        first.register_model({**payload, "catalogId": "qwen3-0.6b-mlx"})


@pytest.mark.parametrize("catalog_id", ["not-in-catalog", "", None])
def test_unknown_catalog_never_falls_back_to_existing_local_model(session, tmp_path, catalog_id):
    first, _second = _env(session, tmp_path)
    private_path = tmp_path / "unrelated-private-model"
    private_path.mkdir()
    (private_path / "config.json").write_text('{"model_type":"qwen3"}')
    (private_path / "model.safetensors").write_bytes(b"registration-only test artifact")
    payload = {"location": str(private_path), "backend": "mlx", "license": "owned"}
    with pytest.raises(DomainError, match="Unknown curated model catalog"):
        first.register_model({**payload, "catalogId": catalog_id})
    assert first.list_models() == []
    assert first.list_jobs() == []
    # Explicit owner-requested local imports remain available without a catalog ID.
    local = first.register_model(payload)
    assert local["location"] == str(private_path)
    assert local["details"]["state"] == "ready"


def test_merge_shards_preserves_conversations_and_source_groups(session, tmp_path):
    first, second = _env(session, tmp_path)
    one = {
        "prompt": "First paper-A finding",
        "response": "Generated summary",
        "documentId": "paper-a",
        "evaluation": {"jsonRequired": True},
    }
    chat = {
        "messages": [
            {"role": "user", "content": "Read paper B"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "lookup", "function": {"name": "read_resource", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "lookup", "content": "Public source text"},
            {"role": "assistant", "content": "A computed property."},
        ],
        "tools": [{"type": "function", "function": {"name": "read_resource"}}],
        "documentId": "paper-b",
    }

    def shard(name, rows):
        return first.import_dataset(
            {
                "name": name,
                "format": "jsonl",
                "content": "\n".join(json.dumps(row) for row in rows),
                "dataKind": "synthetic",
                "rights": "owned",
            }
        )

    left = shard("First shard", [one, chat])
    right = shard(
        "Second shard",
        [
            one,
            {
                "prompt": "Second paper-A finding",
                "response": "Second summary",
                "documentId": "paper-a",
            },
            {"prompt": "Paper C", "response": "Third summary", "documentId": "paper-c"},
            {"prompt": "Paper D", "response": "Fourth summary", "documentId": "paper-d"},
        ],
    )
    merged = first.merge_datasets({"datasetIds": [left["id"], right["id"]]})
    assert merged["rowCount"] == 5
    assert merged["report"]["duplicates"] == 1
    assert merged["source"]["parents"][0]["digest"] == left["digest"]
    conversation = next(row for row in merged["rows"] if row.get("messages"))
    assert conversation["messages"] == chat["messages"]
    assert conversation["tools"] == chat["tools"]
    assert merged["rows"][0]["evaluation"] == one["evaluation"]
    frozen = first.freeze_dataset(merged["id"])
    paper_a = [row["id"] for row in frozen["rows"] if row.get("documentId") == "paper-a"]
    assert len({frozen["splits"][identifier] for identifier in paper_a}) == 1
    assert set(frozen["partitions"]) == {"train", "development", "final"}
    with pytest.raises(DomainError):
        second.merge_datasets({"datasetIds": [left["id"], right["id"]]})
    measured = _dataset(first)
    with pytest.raises(DomainError, match="synthetic"):
        first.merge_datasets({"datasetIds": [left["id"], measured["id"]]})


def test_merge_rechecks_live_parent_and_retained_source_rights(session, tmp_path):
    from studio.domain.library.models import LibrarySource
    from studio.domain.library.research import Download
    from studio.domain.library.service import LibraryService

    first, _second = _env(session, tmp_path)
    library = LibraryService(
        session, first.ctx, vault_root=tmp_path, downloads_root=tmp_path / "review"
    )
    source = library.archive_download(
        Download(
            "https://example.org/paper",
            "text/plain",
            b"A public paper with declared training rights.",
        ),
        title="Paper",
        citation={"rights": {"training": "allowed", "extraction": "allowed"}},
    )
    datasets = [
        first.import_dataset(
            {
                "name": f"Shard {number}",
                "format": "jsonl",
                "content": json.dumps(
                    {
                        "prompt": f"Question {number}",
                        "response": "Generated summary",
                        "documentId": f"paper-{number}",
                    }
                ),
                "dataKind": "synthetic",
                "rights": "allowed",
                "source": {"sourceIds": [source["id"]]},
            }
        )
        for number in range(2)
    ]
    merged = first.merge_datasets({"datasetIds": [row["id"] for row in datasets]})
    first.authorize_dataset_training(merged["id"])
    parent = session.get(LearningDataset, uuid.UUID(datasets[0]["id"]))
    parent.rights = "denied"
    session.flush()
    with pytest.raises(DomainError, match="parent dataset rights"):
        first.authorize_dataset_training(merged["id"])
    parent.rights = "allowed"
    retained = session.get(LibrarySource, uuid.UUID(source["id"]))
    retained.citation = {"rights": {"training": "denied", "extraction": "allowed"}}
    session.flush()
    with pytest.raises(DomainError, match="source rights"):
        first.authorize_dataset_training(merged["id"])


def test_workflow_preflight_preserves_five_gib_free_reserve_without_changing_manual_jobs(
    session, tmp_path, monkeypatch
):
    from studio.domain.learning import workspace

    first, _second = _env(session, tmp_path)
    dataset = _dataset(first)
    first.freeze_dataset(dataset["id"])
    monkeypatch.setattr(
        workspace,
        "storage_preflight",
        lambda _settings, required: {
            "available": required <= 4 * 1024**3,
            "requiredFreeBytes": required,
            "freeBytes": 4 * 1024**3,
        },
    )
    payload = {
        "kind": "chemprop",
        "datasetId": dataset["id"],
        "config": {"executionTarget": "remote"},
    }
    assert first.preflight(payload)["ready"]
    workflow_payload = {**payload, "workflowId": str(uuid.uuid4())}
    check = first.preflight(workflow_payload)
    assert not check["ready"]
    assert check["estimated"]["requiredFreeBytes"] > 5 * 1024**3
    assert first.create_job(workflow_payload)["state"] == "blocked"


def test_external_computed_import_reads_retained_bytes_and_preserves_property_context(
    session, tmp_path
):
    from studio.domain.library.research import Download
    from studio.domain.library.service import LibraryService

    first, second = _env(session, tmp_path)
    library = LibraryService(
        session, first.ctx, vault_root=tmp_path, downloads_root=tmp_path / "review"
    )
    source = library.archive_download(
        Download(
            "https://huggingface.co/datasets/fixture/resolve/abc/data.csv",
            "text/csv",
            b"PSMILES,density,UUID,temp,check_eq\n*CC*,1.2,one,300,True\n*CO*,1.1,two,300,True\n*CN*,1.3,three,300,True\n*CCC*,1.4,four,300,False\n",
        ),
        title="Computed polymer data",
        citation={
            "license": "cc-by-4.0",
            "rights": {"training": "allowed", "extraction": "allowed"},
        },
    )
    payload = {
        "sourceId": source["id"],
        "name": "Density",
        "mapping": {"smiles": "PSMILES", "target": "density", "polymerId": "UUID"},
        "metadataColumns": ["UUID", "temp", "check_eq"],
        "filters": {"check_eq": True},
        "property": "density",
        "unit": "g/cm3",
        "method": "RadonPy MD",
        "conditions": {"temperatureK": 300},
        "content": "malicious replacement labels ignored",
    }
    imported = first.import_retained_dataset(payload)
    assert imported["rowCount"] == 3
    assert imported["dataKind"] == "computed"
    assert imported["rows"][0]["target"] == 1.2
    assert imported["rows"][0]["metadata"]["UUID"] == "one"
    assert imported["rows"][0]["conditions"]["temperatureK"] == 300
    assert imported["source"]["sourceRefs"][0]["checksum"] == source["checksum"]
    with pytest.raises(DomainError):
        second.import_retained_dataset(payload)
    first.freeze_dataset(imported["id"])
    good = first.preflight(
        {"kind": "chemprop", "datasetId": imported["id"], "config": {"executionTarget": "remote"}}
    )
    assert good["ready"]
    assert good["normalizedConfig"]["unit"] == "g/cm3"
    bad = first.preflight(
        {
            "kind": "chemprop",
            "datasetId": imported["id"],
            "config": {"executionTarget": "remote", "unit": "kg/m3"},
        }
    )
    assert not bad["ready"]
    path, _, _ = library.source_file(source["id"])
    path.write_text("tampered")
    with pytest.raises(DomainError, match="checksum"):
        first.import_retained_dataset(payload)


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
