"""Typed app operations available to the agent, through owning services."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, cast

import jsonschema
from sqlalchemy.orm import Session

from studio.application.agent_tools.registry import ToolDispatcher, default_registry
from studio.auth.context import ServiceContext
from studio.config.settings import Settings
from studio.domain.agent_workspace import app_tools
from studio.domain.agent_workspace.service import ident
from studio.errors import DomainError, ErrorCode


def _tool(
    name: str, description: str, properties: dict[str, Any], required: list[str] | None = None
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
    }


STRING = {"type": "string"}
OBJECT = {"type": "object"}
ARRAY = {"type": "array", "items": OBJECT}
NOTE_CONTENT = {
    "type": "object",
    "description": "Note body, usually {markdown: '...'}; formulae may use latex/smiles/variables.",
    "properties": {
        "markdown": STRING,
        "latex": STRING,
        "smiles": STRING,
        "variables": {"type": "object", "additionalProperties": {"type": ["string", "number"]}},
        "steps": {"type": "array", "items": STRING},
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": STRING,
                    "amount": {"type": ["string", "number"]},
                    "unit": STRING,
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}
NOTE_CITATIONS = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "sourceId": STRING,
            "artifactId": STRING,
            "url": STRING,
            "title": STRING,
            "locator": OBJECT,
            "archiveStatus": STRING,
        },
        "additionalProperties": False,
    },
}
MEMORY_REFERENCES = {
    "type": "array",
    "minItems": 1,
    "maxItems": 100,
    "items": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["page", "source"]},
            "id": {"type": "string", "description": "The saved page or retained source ID."},
            "revision": {"type": "integer", "minimum": 1},
        },
        "required": ["kind", "id"],
        "additionalProperties": False,
    },
}


def catalog() -> list[dict[str, Any]]:
    return [
        *default_registry().catalog(),
        *app_tools.catalog(),
        _tool(
            "list_private_library",
            "List your private folders, notebooks, research sources and memory.",
            {},
        ),
        _tool(
            "search_private_library",
            "Search your private notes and research memory, returning source references.",
            {"query": STRING, "limit": {"type": "integer", "minimum": 1, "maximum": 20}},
            ["query"],
        ),
        _tool(
            "create_folder",
            "Create an owner-private notebook folder.",
            {"name": STRING, "parentId": STRING},
            ["name"],
        ),
        _tool(
            "create_notebook",
            "Create an owner-private research notebook.",
            {"title": STRING, "folderId": STRING},
            ["title"],
        ),
        _tool(
            "read_note", "Read an owner-private note, recipe or formula.", {"id": STRING}, ["id"]
        ),
        _tool(
            "create_note",
            (
                "Persist an owner-private note, recipe or formula with source citations. "
                "Mark generated content as a draft."
            ),
            {
                "notebookId": STRING,
                "title": STRING,
                "kind": {"type": "string", "enum": ["note", "recipe", "formula"]},
                "content": NOTE_CONTENT,
                "citations": NOTE_CITATIONS,
            },
            ["notebookId", "title", "content"],
        ),
        _tool(
            "update_note",
            "Update your private note with optimistic revision checking.",
            {
                "id": STRING,
                "expectedRevision": {"type": "integer", "minimum": 1},
                "title": STRING,
                "content": NOTE_CONTENT,
                "citations": NOTE_CITATIONS,
            },
            ["id", "expectedRevision"],
        ),
        _tool(
            "save_research_memory",
            (
                "Save source-backed research memory for continuing this work later; preserve"
                " uncertainty and open questions."
            ),
            {"title": STRING, "body": STRING, "sourceRefs": MEMORY_REFERENCES},
            ["title", "body", "sourceRefs"],
        ),
        _tool(
            "search_resources",
            (
                "Search scholarly papers, chemical resources or the web. Available "
                "connectors: openalex, crossref, pubchem, web. Web needs configured SearXNG."
            ),
            {
                "connector": {"type": "string", "enum": ["openalex", "crossref", "pubchem", "web"]},
                "query": STRING,
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            ["connector", "query"],
        ),
        _tool(
            "fetch_resource",
            (
                "Fetch a public research resource into your private library, preserving "
                "original content, citations and a readable copy. No private network "
                "destinations. Set forceRefresh to check a previously saved URL for changes."
            ),
            {
                "url": STRING,
                "title": STRING,
                "citation": OBJECT,
                "forceRefresh": {"type": "boolean"},
            },
            ["url"],
        ),
        _tool(
            "read_resource",
            "Read a previously fetched private research source.",
            {
                "id": STRING,
                "offset": {"type": "integer", "minimum": 0},
                "maxChars": {"type": "integer", "minimum": 100, "maximum": 20000},
            },
            ["id"],
        ),
        _tool(
            "learning_catalog",
            (
                "Inspect available local model, dataset, training and evaluation "
                "capabilities; unavailable engines are explicit."
            ),
            {},
        ),
        _tool("list_datasets", "List your custom molecular and assistant training datasets.", {}),
        _tool(
            "read_dataset",
            "Inspect a private custom dataset and validation report.",
            {
                "id": STRING,
                "offset": {"type": "integer", "minimum": 0},
                "maxRows": {"type": "integer", "minimum": 1, "maximum": 50},
                "rejectionOffset": {"type": "integer", "minimum": 0},
                "maxRejections": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            ["id"],
        ),
        _tool(
            "create_dataset",
            (
                "Import agent-written CSV/JSONL/SMI/SDF data; default origin is synthetic. "
                "Experimental and user_authored labels are refused. Literature requires "
                "source.sourceRefs [{sourceId,locator:{quote}}] matching fetched source text. "
                "Computed data requires source.resultRefs [{runId or jobId,resultPath:[keys]}] "
                "resolving to completed owned engine results. "
                "Checks do not establish scientific truth."
            ),
            {"payload": OBJECT},
            ["payload"],
        ),
        _tool(
            "freeze_dataset",
            "Freeze a validated immutable dataset version for local training.",
            {"id": STRING},
            ["id"],
        ),
        _tool(
            "dataset_from_notebook",
            "Create a sourced dataset from selected private notebook pages, respecting "
            "each notebook's AI and training opt-outs.",
            {"pageIds": {"type": "array", "items": STRING, "minItems": 1}, "name": STRING},
            ["pageIds", "name"],
        ),
        _tool("list_local_models", "List local training model assets and registered outputs.", {}),
        _tool(
            "register_local_model",
            (
                "Register a local model asset, or download a curated pinned Hugging Face "
                "model by catalogId. Downloads return a durable job reference. To verify and "
                "repair missing files in an existing catalog asset, include its repairModelId "
                "with the same catalogId; cached valid weights are reused."
            ),
            {"payload": OBJECT},
            ["payload"],
        ),
        _tool(
            "import_retained_dataset",
            "Import original retained public computed data with "
            "verified source rights and property/method provenance. Values come from the "
            "saved source, never agent-written replacements.",
            {"payload": OBJECT},
            ["payload"],
        ),
        _tool(
            "prepare_polymer_research_dataset",
            "Compile approximately 400 auditable assistant "
            "teaching examples from this workflow's imported property datasets and actually "
            "executed tools. Origin stays synthetic; source measurements are not invented.",
            {"payload": OBJECT},
            ["payload"],
        ),
        _tool(
            "merge_datasets",
            "Merge two to ten owned synthetic assistant dataset shards, "
            "preserving source lineage, tool conversations and evaluation groups. Current "
            "parent rights are rechecked; no measured labels are generated.",
            {"payload": OBJECT},
            ["payload"],
        ),
        _tool(
            "training_preflight",
            "Check task, model, dataset, runtime, held-out partitions, "
            "storage and budget before queueing a real job.",
            {"payload": OBJECT},
            ["payload"],
        ),
        _tool("simulation_capabilities", "Inspect the actual atomistic simulation runtime.", {}),
        _tool(
            "start_simulation_job",
            "Queue a bounded owner-private RadonPy/LAMMPS polymer "
            "MD pilot. Returns a durable job ID; no fabric properties are inferred from "
            "mere structure validity.",
            {"payload": OBJECT},
            ["payload"],
        ),
        _tool(
            "simulation_job_status",
            "Read numerical stability, equilibration status and artifacts from a real simulation.",
            {"id": STRING},
            ["id"],
        ),
        _tool(
            "await_simulation_job",
            "Wait durably for an atomistic simulation job, releasing "
            "the agent worker while computation continues.",
            {"id": STRING},
            ["id"],
        ),
        _tool(
            "cancel_simulation_job",
            "Stop an owned simulation while preserving checkpoints.",
            {"id": STRING},
            ["id"],
        ),
        _tool(
            "resume_simulation_job",
            "Resume a stopped owned simulation from its retained "
            "checkpoint within the remaining workflow budget.",
            {"id": STRING},
            ["id"],
        ),
        _tool(
            "resume_training_job",
            "Resume a stopped owned download/training/evaluation job "
            "from its saved state, enforcing current rights and remaining workflow budget.",
            {"id": STRING},
            ["id"],
        ),
        _tool("list_training_jobs", "List persistent local training and evaluation jobs.", {}),
        _tool(
            "start_training_job",
            (
                "Queue real local SFT/DPO/GRPO, SMILES property training, molecular "
                "fine-tuning/RL, or evaluation. Returns a durable job ID, never a fabricated"
                " result."
            ),
            {"payload": OBJECT},
            ["payload"],
        ),
        _tool(
            "training_job_status",
            (
                "Read actual progress, validation metrics and errors from a local training "
                "or evaluation job."
            ),
            {"id": STRING},
            ["id"],
        ),
        _tool(
            "await_training_job",
            "Wait durably for a training/evaluation job to finish, then continue research. "
            "The worker releases its slot between polls and survives application restart.",
            {"id": STRING},
            ["id"],
        ),
        _tool(
            "calculate_smiles",
            "Calculate real RDKit descriptors for SMILES through the existing durable engine "
            "lane. Results are computed data, never experimental measurements.",
            {"smiles": STRING},
            ["smiles"],
        ),
        _tool(
            "cancel_training_job",
            "Request cancellation of your local training job, keeping its checkpoint.",
            {"id": STRING},
            ["id"],
        ),
        _tool(
            "preview_local_model",
            "Run a supported real prediction or generation preview on a registered local model.",
            {"id": STRING, "payload": OBJECT},
            ["id", "payload"],
        ),
        _tool(
            "consult_role",
            (
                "Ask another configured model role for a focused review. It receives only "
                "the question you supply; it cannot change settings or approve data."
            ),
            {
                "role": {
                    "type": "string",
                    "enum": ["planner", "researcher", "extractor", "reviewer"],
                },
                "question": STRING,
            },
            ["role", "question"],
        ),
    ]


def validate(name: str, arguments: Any) -> dict[str, Any]:
    tool = next((tool for tool in catalog() if tool["name"] == name), None)
    if tool is None:
        raise DomainError(ErrorCode.VALIDATION, "unknown agent tool")
    try:
        jsonschema.validate(arguments, tool["input_schema"])
    except jsonschema.ValidationError as exc:
        raise DomainError(
            ErrorCode.VALIDATION, "invalid tool arguments: " + exc.message[:250]
        ) from exc
    return cast(dict[str, Any], arguments)


def execute(
    db: Session,
    ctx: ServiceContext,
    settings: Settings,
    name: str,
    args: dict[str, Any],
    *,
    task_id: Any = None,
    provider_bound: bool = False,
) -> Any:
    args = validate(name, args)
    if any(tool["name"] == name for tool in app_tools.catalog()):
        return app_tools.execute(db, ctx, settings, name, args)
    if name in default_registry().names():
        result = ToolDispatcher(db, ctx, task_id=task_id, provider_bound=provider_bound).call(
            name, args
        )
        if name == "search_evidence" and result.get("ok"):
            from studio.domain.library.artifacts import archive_cited_artifacts

            hits = result.get("data", {}).get("results", [])
            result["researchCopies"] = archive_cited_artifacts(
                db,
                ctx,
                settings,
                [str(hit["artifact_id"]) for hit in hits if hit.get("artifact_id")],
            )
        return result
    if name.startswith("list_private") or name in {
        "search_private_library",
        "create_folder",
        "create_notebook",
        "read_note",
        "create_note",
        "update_note",
        "save_research_memory",
        "fetch_resource",
        "read_resource",
    }:
        from studio.domain.library.service import LibraryService

        service = LibraryService(db, ctx, vault_root=settings.vault_root)
        if name == "list_private_library":
            result = service.list_all(for_agent=True)
            if provider_bound:
                for key, kind in (("pages", "page"), ("sources", "source"), ("memory", "memory")):
                    result[key] = filter_private_context(
                        db, ctx, settings, [{**row, "kind": kind} for row in result.get(key, [])]
                    )
            return result
        if name == "search_private_library":
            hits = service.search(args["query"], limit=args.get("limit", 12), for_agent=True)
            return filter_private_context(db, ctx, settings, hits) if provider_bound else hits
        if name == "create_folder":
            return service.create_folder(
                args["name"], parent_id=ident(args["parentId"]) if args.get("parentId") else None
            )
        if name == "create_notebook":
            return service.create_notebook(
                args["title"], folder_id=ident(args["folderId"]) if args.get("folderId") else None
            )
        if name == "read_note":
            result = service.get_page(ident(args["id"]), for_agent=True)
            if provider_bound:
                require_provider_context(db, ctx, settings, "page", result["id"])
            return result
        if name == "create_note":
            from studio.domain.library.models import Notebook

            if not service._get(Notebook, ident(args["notebookId"])).ai_enabled:
                raise DomainError(ErrorCode.FORBIDDEN, "AI access is disabled for this notebook")
            return service.create_page(
                ident(args["notebookId"]),
                args["title"],
                kind=args.get("kind", "note"),
                content=args["content"],
                citations=args.get("citations"),
            )
        if name == "update_note":
            service.get_page(ident(args["id"]), for_agent=True)
            return service.update_page(
                ident(args["id"]),
                args["expectedRevision"],
                **{key: args[key] for key in ("title", "content", "citations") if key in args},
            )
        if name == "save_research_memory":
            return service.save_memory(args["title"], args["body"], source_refs=args["sourceRefs"])
        if name == "fetch_resource":
            return service.fetch_source(
                args["url"],
                title=args.get("title"),
                citation=args.get("citation"),
                force_refresh=args.get("forceRefresh", False),
            )
        if name == "read_resource":
            result = service.get_source(ident(args["id"]))
            if provider_bound:
                require_provider_context(db, ctx, settings, "source", result["id"])
            text = result.get("extractedText", "")
            offset, limit = args.get("offset", 0), args.get("maxChars", 12000)
            result["extractedText"] = text[offset : offset + limit]
            result["textLength"], result["offset"] = len(text), offset
            result["nextOffset"] = offset + limit if len(text) > offset + limit else None
            return result
    if name == "search_resources":
        from studio.domain.library.research import search_resources

        return search_resources(args["connector"], args["query"], limit=args.get("limit", 10))
    from studio.domain.learning.workspace import LearningWorkspaceService

    learning = LearningWorkspaceService(db, ctx, settings)
    if name == "prepare_polymer_research_dataset":
        from studio.domain.agent_workspace.textile_examples import prepare_examples

        return prepare_examples(db, ctx, settings, args["payload"])
    if name in {
        "simulation_capabilities",
        "start_simulation_job",
        "simulation_job_status",
        "cancel_simulation_job",
        "resume_simulation_job",
    }:
        from studio.domain.simulations.service import SimulationService

        simulations = SimulationService(db, ctx, settings)
        if name == "simulation_capabilities":
            return simulations.capabilities()
        if name == "start_simulation_job":
            return simulations.create_job(args["payload"])
        if name == "cancel_simulation_job":
            return simulations.cancel_job(args["id"])
        if name == "resume_simulation_job":
            return simulations.resume_job(args["id"])
        return simulations.get_job(args["id"])
    if name == "create_dataset":
        from studio.domain.agent_workspace.datasets import guard_agent_dataset

        args = {**args, "payload": guard_agent_dataset(db, ctx, settings, args["payload"])}
    if name == "dataset_from_notebook":
        return learning.import_notebook({**args, "forAgent": True})
    if provider_bound and name == "read_dataset":
        learning.authorize_dataset_egress(args["id"])
    if name == "read_dataset":
        result = learning.get_dataset(args["id"])
        rows = result.get("rows", [])
        offset, limit = args.get("offset", 0), args.get("maxRows", 20)
        result["rows"] = rows[offset : offset + limit]
        report = dict(result.get("report") or {})
        rejected = report.get("rejections", [])
        rejection_offset, rejection_limit = (
            args.get("rejectionOffset", 0),
            args.get("maxRejections", 10),
        )
        report["rejections"] = rejected[rejection_offset : rejection_offset + rejection_limit]
        result["report"] = report
        result["nextRejectionOffset"] = (
            rejection_offset + rejection_limit
            if len(rejected) > rejection_offset + rejection_limit
            else None
        )
        result["offset"] = offset
        result["nextOffset"] = offset + limit if len(rows) > offset + limit else None
        return result
    if provider_bound and name == "list_datasets":
        visible = []
        for dataset in learning.list_datasets():
            try:
                learning.authorize_dataset_egress(dataset["id"])
            except DomainError:
                continue
            visible.append(dataset)
        return visible
    methods: dict[str, tuple[Callable[..., Any], list[Any]]] = {
        "learning_catalog": (learning.catalog, []),
        "import_retained_dataset": (learning.import_retained_dataset, [args.get("payload")]),
        "training_preflight": (learning.preflight, [args.get("payload")]),
        "merge_datasets": (learning.merge_datasets, [args.get("payload")]),
        "list_datasets": (learning.list_datasets, []),
        "read_dataset": (learning.get_dataset, [args.get("id")]),
        "create_dataset": (learning.import_dataset, [args.get("payload")]),
        "freeze_dataset": (learning.freeze_dataset, [args.get("id")]),
        "list_local_models": (learning.list_models, []),
        "register_local_model": (learning.register_model, [args.get("payload")]),
        "list_training_jobs": (learning.list_jobs, []),
        "start_training_job": (learning.create_job, [args.get("payload")]),
        "training_job_status": (learning.get_job, [args.get("id")]),
        "cancel_training_job": (learning.cancel_job, [args.get("id")]),
        "resume_training_job": (learning.resume_job, [args.get("id")]),
        "preview_local_model": (learning.preview_model, [args.get("id"), args.get("payload")]),
    }
    if name not in methods:
        raise DomainError(ErrorCode.VALIDATION, "tool requires runtime handling")
    method, parameters = methods[name]
    return method(*parameters)


def require_provider_context(
    db: Session,
    ctx: ServiceContext,
    settings: Settings,
    kind: str,
    row_id: str,
    seen: set[str] | None = None,
) -> None:
    """A private copy cannot bypass current originating export rights."""
    from studio.domain.library.artifacts import authorize_retained_artifact
    from studio.domain.library.service import LibraryService

    library = LibraryService(db, ctx, vault_root=settings.vault_root)
    visited = seen if seen is not None else set()
    marker = kind + ":" + row_id
    if marker in visited:
        return
    if len(visited) >= 100:
        raise DomainError(ErrorCode.FORBIDDEN, "research context lineage is too large to verify")
    visited.add(marker)
    if kind == "source":
        source = library.get_source(ident(row_id))
        authorize_retained_artifact(db, ctx, source.get("citation") or {}, provider_bound=True)
    elif kind == "page":
        page = library.get_page(ident(row_id), for_agent=True)
        for citation in page.get("citations", []):
            authorize_retained_artifact(db, ctx, citation, provider_bound=True)
            if citation.get("sourceId"):
                require_provider_context(db, ctx, settings, "source", citation["sourceId"], visited)
    elif kind == "memory":
        memory = next((row for row in library.active_memory() if row["id"] == row_id), None)
        if memory is None:
            raise DomainError(ErrorCode.NOT_FOUND, "current research memory is unavailable")
        for ref in memory.get("sourceRefs", []):
            require_provider_context(db, ctx, settings, ref["kind"], ref["id"], visited)
    elif kind == "artifact":
        authorize_retained_artifact(db, ctx, {"artifactId": row_id}, provider_bound=True)
    elif kind == "dataset":
        from studio.domain.learning.workspace import LearningWorkspaceService

        LearningWorkspaceService(db, ctx, settings).authorize_dataset_egress(row_id)


def source_references(name: str, arguments: dict[str, Any], result: Any) -> list[dict[str, str]]:
    """Track source identities so a local agent cannot launder restricted text into a helper."""
    refs: list[dict[str, str]] = []
    if name in {"read_note", "update_note"}:
        refs.append({"kind": "page", "id": arguments["id"]})
    elif name in {"read_resource", "read_dataset"}:
        refs.append(
            {"kind": "source" if name == "read_resource" else "dataset", "id": arguments["id"]}
        )
    elif (
        name in {"create_note", "fetch_resource", "create_dataset", "dataset_from_notebook"}
        and isinstance(result, dict)
        and result.get("id")
    ):
        refs.append(
            {
                "kind": {"create_note": "page", "fetch_resource": "source"}.get(name, "dataset"),
                "id": str(result["id"]),
            }
        )
    elif name == "search_private_library" and isinstance(result, list):
        refs.extend(
            {"kind": str(row.get("kind", "memory")), "id": str(row["id"])}
            for row in result
            if isinstance(row, dict) and row.get("id")
        )
    elif name == "list_private_library" and isinstance(result, dict):
        for key, kind in (("pages", "page"), ("sources", "source"), ("memory", "memory")):
            refs.extend(
                {"kind": kind, "id": str(row["id"])} for row in result.get(key, []) if row.get("id")
            )
    elif name == "list_datasets" and isinstance(result, list):
        refs.extend({"kind": "dataset", "id": str(row["id"])} for row in result if row.get("id"))
    elif name == "search_evidence" and isinstance(result, dict):
        refs.extend(
            {"kind": "artifact", "id": str(row["artifact_id"])}
            for row in result.get("data", {}).get("results", [])
            if row.get("artifact_id")
        )
    return refs


def filter_private_context(
    db: Session, ctx: ServiceContext, settings: Settings, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        try:
            require_provider_context(db, ctx, settings, row.get("kind", "memory"), row["id"])
        except DomainError:
            continue
        result.append(row)
    return result


def result_summary(name: str, value: Any) -> Any:
    """Keep mutation receipts useful; large content has explicit read tools."""
    if not isinstance(value, dict):
        return value
    value = dict(value)
    if name == "fetch_resource":
        value["textLength"] = len(value.pop("extractedText", ""))
        value["readTool"] = "read_resource"
    if name in {
        "create_dataset",
        "import_retained_dataset",
        "prepare_polymer_research_dataset",
        "merge_datasets",
        "freeze_dataset",
    }:
        value.pop("rows", None)
        value.pop("splits", None)
        value["readTool"] = "read_dataset"
        if isinstance(value.get("report"), dict):
            report = dict(value["report"])
            rejections = report.get("rejections", [])
            if isinstance(rejections, list) and len(rejections) > 10:
                report["rejections"] = rejections[:10]
                report["rejectionsTruncated"] = True
                report["nextRejectionOffset"] = 10
            value["report"] = report
    if name in {
        "training_job_status",
        "await_training_job",
        "resume_training_job",
        "simulation_job_status",
        "await_simulation_job",
        "resume_simulation_job",
    } and isinstance(value.get("events"), list):
        value["eventCount"] = len(value["events"])
        value["events"] = value["events"][-20:]
    if name in {
        "training_job_status",
        "await_training_job",
        "simulation_job_status",
        "await_simulation_job",
    }:
        for key in (None, "result"):
            container = dict(value.get(key) or {}) if key else value
            artifacts = container.get("artifacts")
            if isinstance(artifacts, list) and len(artifacts) > 20:
                container["artifactCount"] = len(artifacts)
                container["artifacts"] = artifacts[:20]
                container["artifactsTruncated"] = True
            if key:
                value[key] = container
    return value


def bounded_result(value: Any) -> str:
    encoded = json.dumps(
        {"ok": True, "data": value, "untrusted": True}, default=str, allow_nan=False
    )
    if len(encoded.encode()) > 64000:
        if isinstance(value, dict) and isinstance(value.get("id"), str):
            # Even unusually large metadata must not hide a successful mutation's
            # resource ID and cause the model to repeat it.
            receipt = {
                key: value[key]
                for key in ("id", "name", "title", "state", "kind", "readTool")
                if key in value and isinstance(value[key], str) and len(value[key]) < 1000
            }
            return json.dumps(
                {
                    "ok": True,
                    "untrusted": True,
                    "data": {
                        **receipt,
                        "receiptTruncated": True,
                        "note": (
                            "Content exceeds the reply limit; "
                            "use the read tool with a smaller selection."
                        ),
                    },
                }
            )
        # Preserve valid JSON, not a silently truncated JSON fragment.
        return json.dumps(
            {
                "ok": False,
                "error": (
                    "Result is too large; request a smaller selection "
                    "or inspect the resource by ID."
                ),
            }
        )
    return encoded
