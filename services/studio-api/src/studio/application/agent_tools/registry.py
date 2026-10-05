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
from dataclasses import dataclass, field
from typing import Any

import jsonschema
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext
from studio.domain.candidates.service import CandidateService
from studio.domain.candidates.verification import VerificationService
from studio.domain.evidence.claims import ClaimService
from studio.domain.evidence.retrieval import RetrievalService
from studio.domain.runs.queue import RunService
from studio.errors import DomainError, ErrorCode

MAX_RESULT_BYTES = 32_000


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
    ) -> None:
        self.db = db
        self.ctx = ctx
        self.max_calls = max_calls
        self.max_wall_seconds = max_wall_seconds
        self.usage = ToolUsage()

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.usage.calls >= self.max_calls:
            return self._err("BUDGET_EXHAUSTED", "tool-call budget exhausted")
        if time.monotonic() - self.usage.wall_started > self.max_wall_seconds:
            return self._err("BUDGET_EXHAUSTED", "turn wall-time budget exhausted")
        tool = default_registry().get(name)
        if tool is None:
            # an unregistered name (incl. any export/approve/promote
            # verb) is refused outright — the catalog is closed
            return self._err("UNKNOWN_TOOL", f"no registered tool '{name}'")
        try:
            jsonschema.validate(arguments, tool.input_schema)
        except jsonschema.ValidationError as exc:
            return self._err("INVALID_INPUT", f"arguments: {exc.message}")
        self.usage.calls += 1
        self.usage.names.append(name)
        try:
            result = tool.handler(self.db, self.ctx, arguments)
        except DomainError as exc:
            return self._err(exc.code.value, exc.message)
        encoded = json.dumps(result, default=str)
        if len(encoded) > MAX_RESULT_BYTES:
            return self._err("RESULT_TOO_LARGE", f"result exceeds {MAX_RESULT_BYTES} bytes")
        self.usage.total_result_bytes += len(encoded)
        return {"ok": True, "untrusted": tool.untrusted_output, "data": result}

    @staticmethod
    def _err(code: str, message: str) -> dict[str, Any]:
        return {"ok": False, "error": {"code": code, "message": message}}


# ----------------------------------------------------------- handlers


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
