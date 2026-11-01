"""Bounded, public-source research campaigns and their private output lineage."""

from __future__ import annotations

import copy
import hashlib
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ForeignKeyConstraint, String, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from studio.auth.context import ServiceContext
from studio.errors import DomainError, ErrorCode
from studio.persistence.base import Base, Timestamped, UUIDPrimaryKey, WorkspaceScoped


class ResearchWorkflow(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped):
    __tablename__ = "private_research_workflows"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "owner_id"], ["principals.workspace_id", "principals.id"]
        ),
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200))
    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    notebook_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    provider_revision: Mapped[int] = mapped_column(nullable=False)
    specification: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    ledger: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


PUBLIC_TOOLS = {
    "merge_datasets",
    "prepare_polymer_research_dataset",
    "search_resources",
    "fetch_resource",
    "read_resource",
    "create_note",
    "read_note",
    "update_note",
    "save_research_memory",
    "learning_catalog",
    "register_local_model",
    "create_dataset",
    "import_retained_dataset",
    "freeze_dataset",
    "read_dataset",
    "start_training_job",
    "training_preflight",
    "training_job_status",
    "await_training_job",
    "cancel_training_job",
    "resume_training_job",
    "preview_local_model",
    "simulation_capabilities",
    "start_simulation_job",
    "simulation_job_status",
    "await_simulation_job",
    "cancel_simulation_job",
    "resume_simulation_job",
}


class WorkflowService:
    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db, self.ctx = db, ctx

    def get(self, identifier: Any, *, lock: bool = False) -> ResearchWorkflow:
        try:
            identifier = uuid.UUID(str(identifier))
        except (ValueError, TypeError) as exc:
            raise DomainError(ErrorCode.VALIDATION, "Invalid workflow identifier") from exc
        statement = select(ResearchWorkflow).where(
            ResearchWorkflow.id == identifier,
            ResearchWorkflow.workspace_id == self.ctx.workspace_id,
            ResearchWorkflow.owner_id == self.ctx.principal_id,
        )
        row = self.db.scalar(statement.with_for_update() if lock else statement)
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, "Private research workflow not found")
        return row

    def create(self, payload: dict[str, Any], settings: Any) -> dict[str, Any]:
        from studio.domain.agent_workspace.service import AgentWorkspaceService, ident
        from studio.domain.inference.providers import ProviderService
        from studio.domain.library.service import LibraryService

        name = str(payload.get("name", "Research workflow")).strip()
        if not name or len(name) > 200:
            raise DomainError(ErrorCode.VALIDATION, "Workflow name must contain 1-200 characters")
        provider = ProviderService(self.db, self.ctx).get(ident(payload.get("providerId")))
        if not provider.enabled:
            raise DomainError(ErrorCode.VALIDATION, "Select an enabled provider")
        limits = {}
        for key, default, maximum in (
            ("trainingSeconds", 14400, 86400),
            ("simulationSeconds", 14400, 86400),
            ("paidCostUsd", 20, 10000),
        ):
            value = payload.get(key, default)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 < value <= maximum
            ):
                raise DomainError(ErrorCode.VALIDATION, f"Invalid {key}")
            limits[key] = float(value)
        library = LibraryService(self.db, self.ctx, vault_root=settings.vault_root)
        notebook = library.create_notebook(name)
        thread = AgentWorkspaceService(self.db, self.ctx).create_thread(
            {
                "title": name,
                "notebookId": notebook["id"],
            }
        )
        row = ResearchWorkflow(
            workspace_id=self.ctx.workspace_id,
            owner_id=self.ctx.principal_id,
            name=name,
            thread_id=uuid.UUID(thread["id"]),
            notebook_id=uuid.UUID(notebook["id"]),
            provider_id=provider.id,
            provider_revision=provider.version,
            specification={
                "publicSourcesOnly": True,
                "limits": limits,
                "goal": str(payload.get("goal", ""))[:16000],
            },
            ledger={"resources": {}, "allocations": [], "stages": []},
        )
        self.db.add(row)
        self.db.flush()
        return self.describe(row)

    def describe(self, row: ResearchWorkflow) -> dict[str, Any]:
        from studio.domain.agent_workspace.models import AgentRun

        costs = [
            float((run.checkpoint or {}).get("costUsd", 0))
            for run in self.db.scalars(
                select(AgentRun).where(
                    AgentRun.thread_id == row.thread_id,
                    AgentRun.owner_id == row.owner_id,
                    AgentRun.workspace_id == row.workspace_id,
                )
            )
            if (run.checkpoint or {}).get("workflowId") == str(row.id)
        ]
        return {
            "id": str(row.id),
            "name": row.name,
            "threadId": str(row.thread_id),
            "notebookId": str(row.notebook_id),
            "providerId": str(row.provider_id),
            "specification": row.specification,
            "ledger": row.ledger,
            "paidCostUsd": sum(costs),
        }

    def add_resource(self, row: ResearchWorkflow, kind: str, identifier: Any) -> None:
        if not identifier:
            return
        ledger = copy.deepcopy(row.ledger)
        values = ledger.setdefault("resources", {}).setdefault(kind, [])
        if str(identifier) not in values:
            values.append(str(identifier))
        row.ledger = ledger
        self.db.flush()

    def require_resource(self, row: ResearchWorkflow, kind: str, identifier: Any) -> None:
        if str(identifier) not in row.ledger.get("resources", {}).get(kind, []):
            raise DomainError(
                ErrorCode.FORBIDDEN, "Resource is outside this public-source workflow"
            )

    def fetch_resource(
        self, row: ResearchWorkflow, args: dict[str, Any], settings: Any
    ) -> dict[str, Any]:
        """Retain fresh public bytes without reusing an unrelated private copy.

        Both URL and byte deduplication use this workflow namespace. Original
        requested/source URLs remain public URLs in the retained metadata.
        """
        from studio.domain.library.research import fetch_public, public_url
        from studio.domain.library.service import LibraryService

        url = public_url(args["url"])
        citation = copy.deepcopy(args.get("citation") or {})
        if any(key in citation for key in ("artifactId", "sourceChunkId", "pageId", "notebookId")):
            raise DomainError(
                ErrorCode.FORBIDDEN, "Public retrieval cannot attach private artifacts"
            )
        namespace = hashlib.sha256(f"workflow:{row.id}:{url}".encode()).hexdigest()
        downloaded = fetch_public(url)
        result = LibraryService(self.db, self.ctx, vault_root=settings.vault_root).archive_download(
            downloaded,
            title=args.get("title"),
            citation={**citation, "workflowId": str(row.id)},
            url_hash=namespace,
            requested_url=url,
        )
        self.add_resource(row, "source", result["id"])
        return result

    def authorize_tool(
        self, row: ResearchWorkflow, name: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        if name not in PUBLIC_TOOLS:
            raise DomainError(
                ErrorCode.FORBIDDEN, "This tool is outside the public-source workflow"
            )
        args = copy.deepcopy(args)
        if name == "save_research_memory":
            references = args.get("sourceRefs")
            if not isinstance(references, list) or not 1 <= len(references) <= 100:
                raise DomainError(
                    ErrorCode.VALIDATION, "Memory requires 1-100 workflow source references"
                )
            for reference in references:
                if (
                    not isinstance(reference, dict)
                    or reference.get("kind") not in {"page", "source"}
                    or set(reference) - {"kind", "id", "revision"}
                ):
                    raise DomainError(
                        ErrorCode.FORBIDDEN,
                        "Memory may reference workflow pages and public sources only",
                    )
                self.require_resource(row, reference["kind"], reference.get("id"))
        if name in {"create_note", "update_note", "read_note"}:
            if name == "create_note" and args.get("notebookId") != str(row.notebook_id):
                raise DomainError(ErrorCode.FORBIDDEN, "Use the workflow notebook")
            if name != "create_note":
                self.require_resource(row, "page", args.get("id"))
            for citation in args.get("citations", []):
                if citation.get("sourceId"):
                    self.require_resource(row, "source", citation["sourceId"])
                if any(key in citation for key in ("artifactId", "sourceChunkId", "pageId")):
                    raise DomainError(ErrorCode.FORBIDDEN, "Use workflow public-source citations")
        kinds = {
            "read_resource": "source",
            "read_dataset": "dataset",
            "freeze_dataset": "dataset",
            "training_job_status": "job",
            "await_training_job": "job",
            "cancel_training_job": "job",
            "resume_training_job": "job",
            "preview_local_model": "model",
            "simulation_job_status": "simulation",
            "await_simulation_job": "simulation",
            "cancel_simulation_job": "simulation",
            "resume_simulation_job": "simulation",
        }
        if name in kinds:
            self.require_resource(row, kinds[name], args.get("id"))
        payload = args.get("payload", {})
        if name == "merge_datasets":
            for identifier in payload.get("datasetIds", []):
                self.require_resource(row, "dataset", identifier)
        if name == "prepare_polymer_research_dataset":
            payload["workflowId"] = str(row.id)
        if name == "import_retained_dataset":
            self.require_resource(row, "source", payload.get("sourceId"))
        if name in {"start_training_job", "training_preflight"}:
            self.require_resource(row, "dataset", payload.get("datasetId"))
            if payload.get("modelId"):
                self.require_resource(row, "model", payload["modelId"])
            payload["workflowId"] = str(row.id)
        if name == "register_local_model":
            from studio.domain.learning.workspace import CATALOG

            catalog = next(
                (item for item in CATALOG if item["id"] == payload.get("catalogId")), None
            )
            if catalog is None or not re.fullmatch(r"[0-9a-f]{40}", catalog.get("revision", "")):
                raise DomainError(
                    ErrorCode.FORBIDDEN,
                    "Public workflows can download pinned curated model assets only",
                )
            if set(payload) - {"catalogId", "name", "repairModelId", "workflowId"}:
                raise DomainError(
                    ErrorCode.FORBIDDEN,
                    "Public model registration cannot override curated model settings",
                )
            if payload.get("workflowId") and payload["workflowId"] != str(row.id):
                raise DomainError(ErrorCode.FORBIDDEN, "Model belongs to a different workflow")
            if payload.get("repairModelId"):
                self.require_resource(row, "model", payload["repairModelId"])
            payload["workflowId"] = str(row.id)
        if name == "create_dataset":
            source = payload.get("source", {})
            for ref in source.get("sourceRefs", []):
                self.require_resource(row, "source", ref.get("sourceId") or ref.get("id"))
            for identifier in source.get("sourceIds", []):
                self.require_resource(row, "source", identifier)
            for ref in source.get("resultRefs", []):
                if ref.get("runId"):
                    raise DomainError(
                        ErrorCode.FORBIDDEN, "Shared engine runs are outside this workflow"
                    )
                self.require_resource(row, "job", ref.get("jobId"))
            for identifier in source.get("jobIds", []):
                self.require_resource(row, "job", identifier)
            if (
                source.get("runIds")
                or source.get("pages")
                or source.get("kind") == "private_notebook"
            ):
                raise DomainError(ErrorCode.FORBIDDEN, "Use workflow source data only")
        if name == "start_simulation_job":
            payload["campaignId"] = str(row.id)
        if "payload" in args:
            args["payload"] = payload
        return args

    def record_tool(self, row: ResearchWorkflow, name: str, result: Any) -> None:
        if not isinstance(result, dict):
            return
        kinds = {
            "merge_datasets": "dataset",
            "prepare_polymer_research_dataset": "dataset",
            "fetch_resource": "source",
            "create_note": "page",
            "save_research_memory": "memory",
            "create_dataset": "dataset",
            "import_retained_dataset": "dataset",
            "register_local_model": "model",
            "start_training_job": "job",
            "start_simulation_job": "simulation",
        }
        if name in kinds:
            self.add_resource(row, kinds[name], result.get("id"))
        if name == "register_local_model":
            self.add_resource(row, "job", result.get("downloadJobId"))
        # Candidate/download model references are linked by the owning learning job.
        if name in {"training_job_status", "await_training_job"}:
            details = result.get("result") or {}
            for key in ("modelId", "candidateModelId", "registeredModelId"):
                self.add_resource(row, "model", details.get(key))
            model = details.get("model")
            if isinstance(model, dict):
                self.add_resource(row, "model", model.get("id"))
        ledger = copy.deepcopy(row.ledger)
        ledger.setdefault("stages", []).append(
            {
                "tool": name,
                "id": result.get("id"),
                "state": result.get("state"),
                "at": datetime.now(UTC).isoformat(),
            }
        )
        ledger["stages"] = ledger["stages"][-500:]
        row.ledger = ledger


def workflow_for_run(
    db: Session, ctx: ServiceContext, run: Any, *, lock: bool = False
) -> ResearchWorkflow | None:
    identifier = (run.checkpoint or {}).get("workflowId")
    return WorkflowService(db, ctx).get(identifier, lock=lock) if identifier else None


def admit_job(
    db: Session, ctx: ServiceContext, payload: dict[str, Any], category: str
) -> tuple[ResearchWorkflow | None, int]:
    """Lock campaign through job admission; reserve complete caps, including retries."""
    identifier = payload.get("workflowId") or payload.get("campaignId")
    if not identifier:
        return None, 0
    service = WorkflowService(db, ctx)
    row = service.get(identifier, lock=True)
    from studio.domain.learning.workspace_runtime.models import LearningJob
    from studio.domain.simulations.models import SimulationJob

    for cls, states in (
        (LearningJob, ("queued", "running")),
        (SimulationJob, ("queued", "running")),
    ):
        if db.scalar(
            select(cls.id)
            .where(
                cls.workspace_id == ctx.workspace_id,
                cls.owner_id == ctx.principal_id,
                cls.state.in_(states),
            )
            .limit(1)
        ):
            raise DomainError(
                ErrorCode.CONFLICT, "Wait for the current compute job before queueing another"
            )
    limit = row.specification["limits"][category + "Seconds"]
    used = 0.0
    ledger = copy.deepcopy(row.ledger)
    for entry in ledger.get("allocations", []):
        if entry["category"] != category:
            continue
        cls = LearningJob if category == "training" else SimulationJob
        job: Any = db.get(cls, uuid.UUID(entry["jobId"]))
        if "spentSeconds" not in entry and job and job.state not in {"queued", "running"}:
            cumulative = float((job.result or {}).get("elapsedSeconds", entry["seconds"]))
            entry["spentSeconds"] = min(
                entry["seconds"], max(0, cumulative - entry.get("startElapsedSeconds", 0))
            )
        used += entry.get("spentSeconds", entry["seconds"])
    row.ledger = ledger
    remaining = max(0, int(limit - used))
    requested = int(
        payload.get("maxWallSeconds", 1800)
        if category == "simulation"
        else payload.get("config", {}).get("maxSeconds", 3600)
    )
    if remaining < 10:
        raise DomainError(ErrorCode.CONFLICT, f"Workflow {category} budget is exhausted")
    return row, min(requested, remaining)


def record_job(
    db: Session, row: ResearchWorkflow | None, job_id: Any, category: str, seconds: int
) -> None:
    if row is None:
        return
    ledger = copy.deepcopy(row.ledger)
    from studio.domain.learning.workspace_runtime.models import LearningJob
    from studio.domain.simulations.models import SimulationJob

    job: Any = db.get(
        LearningJob if category == "training" else SimulationJob, uuid.UUID(str(job_id))
    )
    start_elapsed = float((job.result or {}).get("elapsedSeconds", 0)) if job else 0
    ledger.setdefault("allocations", []).append(
        {
            "category": category,
            "jobId": str(job_id),
            "seconds": seconds,
            "startElapsedSeconds": start_elapsed,
        }
    )
    row.ledger = ledger
    db.flush()
