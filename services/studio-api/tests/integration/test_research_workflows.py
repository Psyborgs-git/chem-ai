"""Public workflows cannot pull unrelated private data or expand compute limits."""

from __future__ import annotations

import uuid

import pytest
from chem_studio_policy.capabilities import capabilities_for_role

from studio.auth.context import load_context
from studio.config.settings import Settings
from studio.domain.agent_workspace.runtime import _prompt
from studio.domain.agent_workspace.service import AgentWorkspaceService
from studio.domain.agent_workspace.workflows import WorkflowService, admit_job, record_job
from studio.domain.learning.workspace_runtime.models import LearningJob
from studio.domain.library.service import LibraryService
from studio.errors import DomainError
from studio.persistence.models import InferenceProvider, Principal, PrincipalCapability, Workspace

pytestmark = pytest.mark.integration


@pytest.fixture()
def setup(session, tmp_path):
    workspace = Workspace(slug="public-research", display_name="Research")
    session.add(workspace)
    session.flush()
    owner = Principal(workspace_id=workspace.id, kind="user", login="owner", display_name="Owner")
    session.add(owner)
    session.flush()
    for capability in capabilities_for_role("owner"):
        session.add(
            PrincipalCapability(
                workspace_id=workspace.id, principal_id=owner.id, capability=capability
            )
        )
    session.flush()
    ctx = load_context(session, workspace.id, owner.id)
    provider = InferenceProvider(
        workspace_id=workspace.id,
        version=1,
        name="Research",
        kind="openai",
        base_url="https://api.openai.com/v1",
        model="test",
        api_style="responses",
        enabled=True,
        supports_tools=True,
        last_test_status="untested",
    )
    session.add(provider)
    session.flush()
    settings = Settings(vault_root=tmp_path)
    service = WorkflowService(session, ctx)
    workflow = service.get(
        service.create(
            {
                "name": "Public material research",
                "providerId": str(provider.id),
                "trainingSeconds": 100,
                "simulationSeconds": 100,
            },
            settings,
        )["id"]
    )
    return ctx, provider, service, workflow, settings


def test_public_workflow_does_not_retrieve_unrelated_notes(session, setup):
    ctx, _provider, service, workflow, settings = setup
    library = LibraryService(session, ctx, vault_root=settings.vault_root)
    notebook = library.create_notebook("Secret research")
    page = library.create_page(
        uuid.UUID(notebook["id"]),
        "Polyester secrets",
        content={"markdown": "PRIVATE-SENTINEL-DO-NOT-SEND"},
    )
    agents = AgentWorkspaceService(session, ctx)
    run_json = agents.create_run(
        workflow.thread_id, {"message": "Research polyester", "workflowId": str(workflow.id)}
    )
    from studio.domain.agent_workspace.models import AgentRun

    run = session.get(AgentRun, uuid.UUID(run_json["id"]))
    prompt = _prompt(session, run, ctx, settings, [])
    assert "PRIVATE-SENTINEL-DO-NOT-SEND" not in str(prompt)
    assert agents.policy()["remoteDisclosures"] == {}
    for name, args in (
        ("read_note", {"id": page["id"]}),
        ("list_private_library", {}),
        ("consult_role", {"role": "reviewer", "question": "Read my notes"}),
    ):
        with pytest.raises(DomainError):
            service.authorize_tool(workflow, name, args)


def test_public_workflow_only_authorizes_its_own_created_resources(session, setup):
    _ctx, _provider, service, workflow, _settings = setup
    source = str(uuid.uuid4())
    with pytest.raises(DomainError):
        service.authorize_tool(workflow, "read_resource", {"id": source})
    service.add_resource(workflow, "source", source)
    assert service.authorize_tool(workflow, "read_resource", {"id": source}) == {"id": source}
    with pytest.raises(DomainError):
        service.authorize_tool(
            workflow, "create_note", {"notebookId": str(uuid.uuid4()), "title": "X", "content": {}}
        )
    with pytest.raises(DomainError):
        service.authorize_tool(
            workflow, "register_local_model", {"payload": {"location": "/private/model"}}
        )


@pytest.mark.parametrize(
    "override",
    [
        {"catalogId": "not-in-catalog", "location": "/private/model"},
        {"location": "/private/model"},
        {"backend": "reinvent"},
        {"repo": "unreviewed/model"},
        {"revision": "main"},
        {"license": "owned"},
        {"workflowId": str(uuid.uuid4())},
    ],
)
def test_public_workflow_catalog_rejects_local_and_unpinned_overrides(session, setup, override):
    _ctx, _provider, service, workflow, _settings = setup
    with pytest.raises(DomainError):
        service.authorize_tool(
            workflow,
            "register_local_model",
            {"payload": {"catalogId": "qwen3-4b-instruct-mlx", **override}},
        )
    assert workflow.ledger["resources"] == {}


def test_public_workflow_catalog_requires_pin_and_keeps_valid_download_and_repair_scoped(
    session, setup, monkeypatch
):
    from studio.domain.agent_workspace import tools
    from studio.domain.learning.workspace import CATALOG

    ctx, _provider, service, workflow, settings = setup
    monkeypatch.setattr(
        "studio.domain.learning.workspace.runtime_capability", lambda _name: {"available": False}
    )
    payload = {"catalogId": "qwen3-4b-instruct-mlx", "name": "Workflow research base"}
    approved = service.authorize_tool(workflow, "register_local_model", {"payload": payload})
    registered = tools.execute(session, ctx, settings, "register_local_model", approved)
    service.record_tool(workflow, "register_local_model", registered)
    assert registered["details"]["repo"] == "mlx-community/Qwen3-4B-Instruct-2507-4bit"
    assert registered["details"]["revision"] == "50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b"
    assert registered["id"] in workflow.ledger["resources"]["model"]
    assert registered["downloadJobId"] in workflow.ledger["resources"]["job"]
    repaired = service.authorize_tool(
        workflow,
        "register_local_model",
        {"payload": {**payload, "repairModelId": registered["id"]}},
    )
    assert repaired["payload"]["workflowId"] == str(workflow.id)
    with pytest.raises(DomainError, match="outside"):
        service.authorize_tool(
            workflow,
            "register_local_model",
            {"payload": {**payload, "repairModelId": str(uuid.uuid4())}},
        )
    monkeypatch.setitem(CATALOG[0], "revision", "main")
    with pytest.raises(DomainError, match="pinned curated"):
        service.authorize_tool(
            workflow, "register_local_model", {"payload": {"catalogId": CATALOG[0]["id"]}}
        )


def test_public_workflow_saves_memory_only_from_its_resources_without_auto_retrieval(
    session, setup, tmp_path
):
    from studio.domain.agent_workspace import tools
    from studio.domain.agent_workspace.models import AgentRun
    from studio.domain.library.models import Notebook
    from studio.domain.library.research import Download

    ctx, _provider, service, workflow, settings = setup
    library = LibraryService(
        session, ctx, vault_root=settings.vault_root, downloads_root=tmp_path / "review"
    )
    source = library.archive_download(
        Download(
            "https://example.org/workflow.txt",
            "text/plain",
            b"Public research source with retained evidence.",
        ),
        title="Public source",
    )
    page = library.create_page(
        workflow.notebook_id,
        "Public findings",
        content={"markdown": "A conditional research finding"},
        citations=[{"sourceId": source["id"]}],
    )
    service.record_tool(workflow, "fetch_resource", source)
    service.record_tool(workflow, "create_note", page)
    args = {
        "title": "Next research question",
        "body": "PUBLIC-SAVED-MEMORY-SENTINEL",
        "sourceRefs": [
            {"kind": "page", "id": page["id"], "revision": page["revision"]},
            {"kind": "source", "id": source["id"], "revision": source["revision"]},
        ],
    }
    approved = service.authorize_tool(workflow, "save_research_memory", args)
    memory = tools.execute(
        session, ctx, settings, "save_research_memory", approved, provider_bound=True
    )
    service.record_tool(workflow, "save_research_memory", memory)
    assert workflow.ledger["resources"]["memory"] == [memory["id"]]
    assert {ref["id"] for ref in memory["sourceRefs"]} == {page["id"], source["id"]}
    assert AgentWorkspaceService(session, ctx).policy()["remoteDisclosures"] == {}
    result = AgentWorkspaceService(session, ctx).create_run(
        workflow.thread_id, {"workflowId": str(workflow.id), "message": "Continue public research"}
    )
    run = session.get(AgentRun, uuid.UUID(result["id"]))
    assert "PUBLIC-SAVED-MEMORY-SENTINEL" not in str(_prompt(session, run, ctx, settings, []))
    for name in ("search_private_library", "list_private_library"):
        with pytest.raises(DomainError):
            service.authorize_tool(workflow, name, {"query": "research"})
    notebook = session.get(Notebook, workflow.notebook_id)
    notebook.ai_enabled = False
    session.flush()
    with pytest.raises(DomainError, match="AI access is disabled"):
        tools.execute(session, ctx, settings, "save_research_memory", approved, provider_bound=True)


def test_public_workflow_memory_rejects_unrelated_pages_sources_and_artifact_aliases(
    session, setup, tmp_path
):
    from studio.domain.library.research import Download

    ctx, _provider, service, workflow, settings = setup
    library = LibraryService(
        session, ctx, vault_root=settings.vault_root, downloads_root=tmp_path / "review"
    )
    notebook = library.create_notebook("Unrelated private notebook")
    page = library.create_page(
        notebook["id"], "Private source", content={"markdown": "Do not disclose"}
    )
    source = library.archive_download(
        Download(
            "https://example.org/unrelated.txt",
            "text/plain",
            b"Unrelated source known to the same owner",
        ),
        title="Unrelated source",
    )
    known_source = str(uuid.uuid4())
    service.add_resource(workflow, "source", known_source)
    for reference in (
        {"kind": "page", "id": page["id"]},
        {"kind": "source", "id": source["id"]},
        {"kind": "artifact", "id": str(uuid.uuid4())},
        {"kind": "source", "id": known_source, "artifactId": str(uuid.uuid4())},
        {"kind": "source", "id": known_source, "sourceChunkId": str(uuid.uuid4())},
    ):
        with pytest.raises(DomainError):
            service.authorize_tool(
                workflow,
                "save_research_memory",
                {"title": "Do not leak", "body": "A finding", "sourceRefs": [reference]},
            )
    with pytest.raises(DomainError, match="1-100"):
        service.authorize_tool(
            workflow,
            "save_research_memory",
            {"title": "Unbacked", "body": "No evidence", "sourceRefs": []},
        )


def test_workflow_budgets_reconcile_completed_jobs_and_bound_retries(session, setup):
    ctx, _provider, _service, workflow, _settings = setup
    payload = {"workflowId": str(workflow.id), "config": {"maxSeconds": 80}}
    row, seconds = admit_job(session, ctx, payload, "training")
    assert seconds == 80
    job = LearningJob(
        workspace_id=ctx.workspace_id,
        owner_id=ctx.principal_id,
        name="First",
        kind="sft",
        state="queued",
        config={},
        result={},
        events=[],
    )
    session.add(job)
    session.flush()
    record_job(session, row, job.id, "training", seconds)
    job.state, job.result = "completed", {"elapsedSeconds": 25}
    session.flush()
    assert admit_job(session, ctx, payload, "training")[1] == 75
    job.state = "running"
    session.flush()
    with pytest.raises(DomainError, match="current compute job"):
        admit_job(session, ctx, payload, "training")


def test_workflow_rejects_other_provider_and_other_thread(session, setup):
    ctx, _provider, _service, workflow, _settings = setup
    agents = AgentWorkspaceService(session, ctx)
    unrelated = agents.create_thread({"title": "Unrelated"})
    with pytest.raises(DomainError):
        agents.create_run(
            uuid.UUID(unrelated["id"]), {"workflowId": str(workflow.id), "message": "Hello"}
        )


def test_workflow_fetch_namespace_never_reuses_unrelated_private_metadata(
    session, setup, monkeypatch, tmp_path
):
    from studio.domain.library.research import Download

    ctx, _provider, service, workflow, settings = setup
    monkeypatch.setenv("STUDIO_RESEARCH_DOWNLOADS_ROOT", str(tmp_path / "downloads"))
    fetched = Download(
        "https://example.org/public.txt", "text/plain", b"Original public paper content"
    )
    private = LibraryService(session, ctx, vault_root=settings.vault_root).archive_download(
        fetched,
        title="PRIVATE-TITLE-SENTINEL",
        citation={"privateComment": "PRIVATE-METADATA-SENTINEL"},
    )
    monkeypatch.setattr("studio.domain.library.research.fetch_public", lambda _url: fetched)
    result = service.fetch_resource(
        workflow, {"url": fetched.url, "title": "Public paper"}, settings
    )
    assert result["id"] != private["id"]
    assert "PRIVATE-" not in str(result)
    assert result["sourceUrl"] == fetched.url
    service.require_resource(workflow, "source", result["id"])
    again = service.fetch_resource(workflow, {"url": fetched.url}, settings)
    assert again["id"] == result["id"]


@pytest.mark.parametrize(
    "source",
    [
        {"sourceIds": [str(uuid.uuid4())]},
        {"sourceRefs": [{"id": str(uuid.uuid4())}]},
        {"jobIds": [str(uuid.uuid4())]},
        {"runIds": [str(uuid.uuid4())]},
        {"resultRefs": [{"runId": str(uuid.uuid4())}]},
        {"kind": "private_notebook", "pages": [{"pageId": str(uuid.uuid4())}]},
    ],
)
def test_workflow_blocks_all_alternate_private_dataset_reference_shapes(session, setup, source):
    _ctx, _provider, service, workflow, _settings = setup
    with pytest.raises(DomainError):
        service.authorize_tool(workflow, "create_dataset", {"payload": {"source": source}})


def test_public_workflow_resume_preserves_pinned_provider_without_global_disclosure(session, setup):
    from studio.domain.agent_workspace.models import AgentRun
    from studio.domain.learning.workspace_runtime.models import LearningModel

    ctx, provider, service, workflow, _settings = setup
    model = LearningModel(
        workspace_id=ctx.workspace_id,
        owner_id=ctx.principal_id,
        name="Unrelated private trained model",
        backend="mlx",
        location="/private/model",
        details={},
    )
    session.add(model)
    session.flush()
    agents = AgentWorkspaceService(session, ctx)
    with pytest.raises(DomainError, match="outside"):
        agents.create_run(
            workflow.thread_id, {"message": "Research", "localModelId": str(model.id)}
        )
    result = agents.create_run(workflow.thread_id, {"message": "Research"})
    run = session.get(AgentRun, uuid.UUID(result["id"]))
    run.status = "failed"
    session.flush()
    assert agents.policy()["remoteDisclosures"] == {}
    assert agents.resume(run.id)["status"] == "queued"
    run.status = "failed"
    provider.version += 1
    session.flush()
    with pytest.raises(DomainError, match="provider changed"):
        agents.resume(run.id)
    with pytest.raises(DomainError):
        service.authorize_tool(
            workflow,
            "create_note",
            {
                "notebookId": str(workflow.notebook_id),
                "title": "X",
                "content": {},
                "citations": [{"sourceId": str(uuid.uuid4())}],
            },
        )


def test_workflow_resume_allocations_charge_only_each_attempt_delta(session, setup):
    ctx, _provider, _service, workflow, _settings = setup
    payload = {"workflowId": str(workflow.id), "config": {"maxSeconds": 80}}
    row, seconds = admit_job(session, ctx, payload, "training")
    job = LearningJob(
        workspace_id=ctx.workspace_id,
        owner_id=ctx.principal_id,
        name="Resume",
        kind="sft",
        state="queued",
        config={},
        result={},
        events=[],
    )
    session.add(job)
    session.flush()
    record_job(session, row, job.id, "training", seconds)
    job.state, job.result = "cancelled", {"elapsedSeconds": 25}
    session.flush()
    row, seconds = admit_job(session, ctx, payload, "training")
    assert seconds == 75
    record_job(session, row, job.id, "training", seconds)
    job.result = {"elapsedSeconds": 40}
    session.flush()
    assert admit_job(session, ctx, payload, "training")[1] == 60


@pytest.mark.parametrize(
    ("prices", "limit", "expected_state", "expected_calls", "oversized_context"),
    [
        ((2, 10), 0.000001, "budget_exhausted", 0, False),
        ((None, None), 20, "failed", 0, False),
        ((0, 0), 0.000001, "completed", 1, False),
        ((2, 10), 20, "completed", 1, False),
        ((0, 0), 20, "budget_exhausted", 0, True),
    ],
)
def test_loopback_workflow_enforces_declared_http_cost_before_inference(
    session, setup, monkeypatch, prices, limit, expected_state, expected_calls, oversized_context
):
    from sqlalchemy import select, text
    from sqlalchemy.orm import sessionmaker

    from studio.domain.agent_workspace import runtime as worker_module
    from studio.domain.agent_workspace.models import AgentRun, ProviderModel

    ctx, provider, _service, workflow, settings = setup
    provider.base_url, provider.version = "http://127.0.0.1:9999/v1", provider.version + 1
    workflow.provider_revision = provider.version
    workflow.specification = {
        **workflow.specification,
        "limits": {**workflow.specification["limits"], "paidCostUsd": limit},
    }
    agents = AgentWorkspaceService(session, ctx)
    created = agents.create_run(workflow.thread_id, {"message": "Research public fibres"})
    model = session.scalar(
        select(ProviderModel).where(
            ProviderModel.workspace_id == ctx.workspace_id,
            ProviderModel.provider_id == provider.id,
        )
    )
    model.input_price, model.output_price = prices
    run_id = uuid.UUID(created["id"])
    prior_cost = 0.00000025 if expected_state == "budget_exhausted" else 0
    if prior_cost:
        run = session.get(AgentRun, run_id)
        run.checkpoint = {**run.checkpoint, "costUsd": prior_cost, "retainedCheckpoint": "keep"}
    session.commit()
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    reserved = []

    def bounded_factory():
        db = factory()
        db.execute(text("SET LOCAL lock_timeout = '2s'"))
        return db

    if oversized_context:
        monkeypatch.setattr(
            worker_module,
            "_prompt",
            lambda *_args: [{"role": "user", "content": "x" * 210_000}],
        )

    class Runtime(worker_module.OpenAICompatibleRuntime):
        def generate(self, *_args, **_kwargs):
            with factory() as db:
                pending = db.get(AgentRun, run_id).checkpoint
                reserved.append(pending.get("pendingCostUsd", 0))
            return {
                "choices": [
                    {"message": {"content": "Retain source evidence before a conclusion."}}
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            }

    monkeypatch.setattr(worker_module, "OpenAICompatibleRuntime", Runtime)
    worker = worker_module.AgentWorker(bounded_factory, settings)
    try:
        worker._run(run_id)
        with factory() as db:
            current = db.get(AgentRun, run_id)
            assert current.status == expected_state
            assert len(reserved) == expected_calls
            if expected_calls and prices == (2, 10):
                assert reserved[0] > 0.0004
                assert current.checkpoint["costUsd"] == pytest.approx(0.0004)
                current_ctx = load_context(db, ctx.workspace_id, ctx.principal_id)
                summary = WorkflowService(db, current_ctx).describe(
                    WorkflowService(db, current_ctx).get(workflow.id)
                )
                assert summary["paidCostUsd"] == pytest.approx(0.0004)
            elif expected_calls:
                assert reserved == [0]
                assert current.checkpoint["costUsd"] == 0
            else:
                assert current.checkpoint["costUsd"] == prior_cost
                assert current.checkpoint["messages"] == []
                if expected_state == "budget_exhausted":
                    assert current.checkpoint["contextEpoch"]
                    assert current.checkpoint["retainedCheckpoint"] == "keep"
            if prices == (None, None):
                assert "explicit input and output token prices" in current.error
            if oversized_context:
                assert "Workflow context is full" in current.error
    finally:
        worker.stop()
