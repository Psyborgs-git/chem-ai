"""Tool catalog + dispatcher (§10.2).

Tools are domain operations with JSON Schema inputs. The dispatcher
enforces a finite per-turn call budget and routes each call through
``ServiceContext`` — the same capability checks the UI path gets. A
document's embedded instructions can never widen the catalog: there
is no ``export_*``, ``approve_*``, ``promote_*``, or ``close_*`` tool
to invoke, and the dispatcher rejects unregistered names outright.
"""

from __future__ import annotations

import json
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import jsonschema
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext
from studio.domain.candidates.service import CandidateService
from studio.domain.candidates.verification import VerificationService
from studio.domain.evidence.claims import ClaimService
from studio.domain.evidence.retrieval import RetrievalService
from studio.domain.runs.queue import RunService
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import Artifact, ResearchTask, RetrievalManifest, SourceChunk

MAX_RESULT_BYTES = 32_000


class _ToolResultTooLarge(Exception):
    pass


MAX_SUMMARY_CANDIDATES = 10
MAX_SUMMARY_HYPOTHESIS_CHARS = 100


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Any  # callable(db, ctx, args) -> dict
    untrusted_output: bool = True

    def descriptor(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    def __init__(self, tools: list[AgentTool]) -> None:
        self._tools = {t.name: t for t in tools}

    def get(self, name: str) -> AgentTool | None:
        return self._tools.get(name)

    def catalog(self) -> list[dict[str, Any]]:
        return [t.descriptor() for t in self._tools.values()]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def for_task(self, task_id: uuid.UUID | None) -> ToolRegistry:
        """Advertise the session's required calculation attribution without
        changing the unbound catalog used by legacy direct dispatchers."""
        if task_id is None:
            return self
        tools = []
        for tool in self._tools.values():
            if tool.name == "request_calculation":
                schema = deepcopy(tool.input_schema)
                schema["required"] = list(dict.fromkeys([*schema.get("required", []), "task_id"]))
                tool = AgentTool(
                    tool.name, tool.description, schema, tool.handler, tool.untrusted_output
                )
            tools.append(tool)
        return ToolRegistry(tools)


@dataclass
class ToolUsage:
    calls: int = 0
    total_result_bytes: int = 0
    wall_started: float = field(default_factory=time.monotonic)
    names: list[str] = field(default_factory=list)


class ToolDispatcher:
    """Budget-bounded, capability-checked invocation."""

    def __init__(
        self,
        db: Session,
        ctx: ServiceContext,
        *,
        max_calls: int = 8,
        max_wall_seconds: int = 300,
        registry: ToolRegistry | None = None,
        task_id: uuid.UUID | None = None,
        provider_bound: bool = False,
    ) -> None:
        self.db = db
        self.ctx = ctx
        self.max_calls = max_calls
        self.max_wall_seconds = max_wall_seconds
        self.registry = (registry if registry is not None else default_registry()).for_task(task_id)
        self.task_id = task_id
        self.provider_bound = provider_bound
        self.usage = ToolUsage()

    def call(self, name: str, arguments: Any) -> dict[str, Any]:
        if self.usage.calls >= self.max_calls:
            return self._err("BUDGET_EXHAUSTED", "tool-call budget exhausted")
        if time.monotonic() - self.usage.wall_started > self.max_wall_seconds:
            return self._err("BUDGET_EXHAUSTED", "turn wall-time budget exhausted")
        tool = self.registry.get(name)
        if tool is None:
            # an unregistered name (incl. any export/approve/promote
            # verb) is refused outright — the catalog is closed
            return self._err("UNKNOWN_TOOL", f"no registered tool '{name}'")
        if not isinstance(arguments, dict):
            return self._err("INVALID_INPUT", "arguments must be a JSON object")
        try:
            jsonschema.validate(
                arguments, tool.input_schema, format_checker=jsonschema.FormatChecker()
            )
        except jsonschema.ValidationError as exc:
            return self._err("INVALID_INPUT", f"arguments: {exc.message}")
        self.usage.calls += 1
        self.usage.names.append(name)
        try:
            if self.task_id is not None:
                if name == "request_calculation" and not arguments.get("task_id"):
                    return self._err(
                        "INVALID_INPUT", "task_id is required for this research session"
                    )
                if (
                    "task_id" in arguments
                    and _uuid_arg(arguments["task_id"], "task_id") != self.task_id
                ):
                    raise not_found("task")
                candidate_field = {
                    "read_candidate_revision": "candidate_revision_id",
                    "propose_candidate_patch": "candidate_id",
                }.get(name)
                if candidate_field:
                    candidate = CandidateService(self.db, self.ctx).get(
                        _uuid_arg(arguments[candidate_field], candidate_field)
                    )
                    if candidate.task_id != self.task_id:
                        raise not_found("candidate revision")
            # Each invocation is atomic within the turn. A refusal, malformed
            # result, or unexpected implementation failure cannot retain a
            # partially written candidate/run and then report failure.
            with self.db.begin_nested():
                result = tool.handler(self.db, self.ctx, arguments)
                if not isinstance(result, dict):
                    raise TypeError("tool returned an invalid result")
                if self.provider_bound and name == "search_evidence":
                    result = _provider_safe_search_result(self.db, self.ctx, result)
                encoded = json.dumps(result, default=str, allow_nan=False)
                if len(encoded.encode("utf-8")) > MAX_RESULT_BYTES:
                    raise _ToolResultTooLarge
        except DomainError as exc:
            return self._err(exc.code.value, exc.message)
        except _ToolResultTooLarge:
            return self._err("RESULT_TOO_LARGE", f"result exceeds {MAX_RESULT_BYTES} bytes")
        except Exception:
            # Domain implementations are trusted code but can still fail.
            # Never expose a DB/provider exception containing private values.
            return self._err(
                "TOOL_EXECUTION_FAILED", "tool execution failed; no partial changes were applied"
            )
        self.usage.total_result_bytes += len(encoded.encode("utf-8"))
        return {"ok": True, "untrusted": tool.untrusted_output, "data": result}

    @staticmethod
    def _err(code: str, message: str) -> dict[str, Any]:
        return {"ok": False, "error": {"code": code, "message": message}}


# ----------------------------------------------------------- handlers


def _provider_safe_search_result(
    db: Session, ctx: ServiceContext, result: dict[str, Any]
) -> dict[str, Any]:
    """Retrieval permission does not grant permission to send data to a provider.

    Recheck both current records after retrieval, including cache hits. A
    stale chunk cannot override an artifact's revoked export permission.
    Only a count/reason for omissions leaves this boundary, never withheld
    source IDs, locators, or snippets.
    """
    hits = result.get("results") or []
    ids = []
    for hit in hits:
        try:
            ids.append(uuid.UUID(str(hit["chunk_id"])))
        except (KeyError, TypeError, ValueError):
            continue
    permitted = {
        str(chunk_id)
        for chunk_id in db.scalars(
            select(SourceChunk.id)
            .join(
                Artifact,
                (Artifact.id == SourceChunk.artifact_id)
                & (Artifact.workspace_id == SourceChunk.workspace_id),
            )
            .where(
                SourceChunk.workspace_id == ctx.workspace_id,
                SourceChunk.id.in_(ids),
                SourceChunk.status == "active",
                SourceChunk.rights["export"].astext == "allowed",
                Artifact.rights["export"].astext == "allowed",
                Artifact.upload_state == "committed",
                Artifact.review_state.not_in(["revoked", "rejected", "superseded"]),
            )
        )
    }
    visible = [hit for hit in hits if isinstance(hit, dict) and hit.get("chunk_id") in permitted]
    withheld = len(hits) - len(visible)
    manifest_id = _uuid_arg(result.get("manifest_id"), "manifest_id")
    manifest = db.scalar(
        select(RetrievalManifest).where(
            RetrievalManifest.id == manifest_id,
            RetrievalManifest.workspace_id == ctx.workspace_id,
            RetrievalManifest.principal_id == ctx.principal_id,
        )
    )
    if manifest is None:
        raise not_found("retrieval manifest")
    manifest.chunk_ids = [hit["chunk_id"] for hit in visible]
    manifest.policy_version = f"{manifest.policy_version};source-export-v1"
    db.flush()
    return {
        "manifest_id": str(manifest.id),
        "results": visible,
        "export_policy": "source-export-v1",
        "withheld_sources": withheld,
        "omissions": ["Sources without current export permission were withheld."]
        if withheld
        else [],
    }


def _uuid_arg(value: Any, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise DomainError(ErrorCode.VALIDATION, f"{field} must be a uuid") from exc


def _search_evidence(db: Session, ctx: ServiceContext, args: dict[str, Any]) -> dict[str, Any]:
    results, manifest = RetrievalService(db).search(
        ctx, str(args["query"]), limit=int(args.get("limit", 8))
    )
    return {
        "manifest_id": str(manifest.id),
        "results": [
            {
                "chunk_id": r.chunk_id,
                "locator": r.locator,
                "text": r.snippet[:1200],
                "artifact_id": r.artifact_id,
            }
            for r in results
        ],
    }


def _read_candidate(db: Session, ctx: ServiceContext, args: dict[str, Any]) -> dict[str, Any]:
    cand = CandidateService(db, ctx).get(
        _uuid_arg(args["candidate_revision_id"], "candidate_revision_id")
    )
    return {
        "id": str(cand.id),
        "task_id": str(cand.task_id),
        "revision": cand.revision,
        "status": cand.status,
        "eligibility": cand.eligibility,
        "hypothesis": cand.hypothesis,
        "payload": cand.payload,
    }


def _validate_formulation(db: Session, ctx: ServiceContext, args: dict[str, Any]) -> dict[str, Any]:
    return VerificationService(db, ctx).evaluate_candidate(
        task_id=_uuid_arg(args["task_id"], "task_id"),
        candidate_revision_id=_uuid_arg(args["candidate_revision_id"], "candidate_revision_id"),
    )


def _propose_patch(db: Session, ctx: ServiceContext, args: dict[str, Any]) -> dict[str, Any]:
    patch = CandidateService(db, ctx).propose_patch(
        candidate_id=_uuid_arg(args["candidate_id"], "candidate_id"),
        patch=args["patch"],
        reason=args.get("reason"),
    )
    return {
        "patch_id": str(patch.id),
        "status": patch.status,
        "note": "proposed — a human review is required before apply",
    }


def _request_calculation(db: Session, ctx: ServiceContext, args: dict[str, Any]) -> dict[str, Any]:
    run = RunService(db, ctx).request(
        kind=str(args["kind"]),
        request=args["request"],
        task_id=_uuid_arg(args["task_id"], "task_id") if args.get("task_id") else None,
    )
    return {"run_id": str(run.id), "status": run.status}


def _task_evidence_summary(
    db: Session, ctx: ServiceContext, args: dict[str, Any]
) -> dict[str, Any]:
    task_uuid = _uuid_arg(args["task_id"], "task_id")
    task = db.scalar(
        select(ResearchTask).where(
            ResearchTask.id == task_uuid,
            ResearchTask.workspace_id == ctx.workspace_id,
        )
    )
    if task is None:
        raise not_found("task")
    ctx.require("read_project", task.project_id)
    task_id = str(task_uuid)
    claims = [c for c in ClaimService(db).claims(ctx) if c.subject.get("task_id") == task_id]
    by_status: dict[str, int] = {}
    for c in claims:
        by_status[c.status] = by_status.get(c.status, 0) + 1
    candidates = CandidateService(db, ctx).list_for_task(task_uuid)
    return {
        "claims": len(claims),
        "claims_by_status": by_status,
        "candidate_revisions": len(candidates),
        "candidates_total": len(candidates),
        "candidates_truncated": len(candidates) > MAX_SUMMARY_CANDIDATES,
        "candidates": [
            {
                "id": str(candidate.id),
                "revision": candidate.revision,
                "status": candidate.status,
                "hypothesis": (candidate.hypothesis or "")[:MAX_SUMMARY_HYPOTHESIS_CHARS],
                "hypothesis_truncated": len(candidate.hypothesis or "")
                > MAX_SUMMARY_HYPOTHESIS_CHARS,
            }
            for candidate in candidates[:MAX_SUMMARY_CANDIDATES]
        ],
    }


_OBJECT = {"type": "object", "additionalProperties": True}


def default_registry() -> ToolRegistry:
    """The closed catalog — every name is a domain operation."""
    return ToolRegistry(
        [
            AgentTool(
                name="search_evidence",
                description="Lexical search over scoped, rights-gated sources.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                handler=_search_evidence,
            ),
            AgentTool(
                name="read_candidate_revision",
                description="Read one scoped candidate revision.",
                input_schema={
                    "type": "object",
                    "properties": {"candidate_revision_id": {"type": "string", "format": "uuid"}},
                    "required": ["candidate_revision_id"],
                    "additionalProperties": False,
                },
                handler=_read_candidate,
            ),
            AgentTool(
                name="validate_formulation",
                description="Run the deterministic verifier on a candidate revision.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "format": "uuid"},
                        "candidate_revision_id": {"type": "string", "format": "uuid"},
                    },
                    "required": ["task_id", "candidate_revision_id"],
                    "additionalProperties": False,
                },
                handler=_validate_formulation,
            ),
            AgentTool(
                name="propose_candidate_patch",
                description="Propose a candidate patch — proposal only; a human applies.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "candidate_id": {"type": "string", "format": "uuid"},
                        "patch": _OBJECT,
                        "reason": {"type": "string"},
                    },
                    "required": ["candidate_id", "patch"],
                    "additionalProperties": False,
                },
                handler=_propose_patch,
            ),
            AgentTool(
                name="request_calculation",
                description="Request a queued run under admission and budgets.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string"},
                        "request": _OBJECT,
                        "task_id": {"type": "string", "format": "uuid"},
                    },
                    "required": ["kind", "request"],
                    "additionalProperties": False,
                },
                handler=_request_calculation,
            ),
            AgentTool(
                name="summarize_task_evidence",
                description="Counts and status of claims and candidates for a task.",
                input_schema={
                    "type": "object",
                    "properties": {"task_id": {"type": "string", "format": "uuid"}},
                    "required": ["task_id"],
                    "additionalProperties": False,
                },
                handler=_task_evidence_summary,
            ),
        ]
    )
