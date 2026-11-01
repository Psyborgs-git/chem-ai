"""Agent dataset origin checks; schema validation never creates experimental truth."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext
from studio.config.settings import Settings
from studio.domain.agent_workspace.service import ident
from studio.errors import DomainError, ErrorCode


def _invalid(message: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION, message)


def _literature(
    db: Session, ctx: ServiceContext, settings: Settings, source: dict[str, Any]
) -> dict[str, Any]:
    from studio.domain.library.service import LibraryService

    library = LibraryService(db, ctx, vault_root=settings.vault_root)
    references = copy.deepcopy(source.get("sourceRefs") or [])
    if not isinstance(references, list):
        raise _invalid("literature sourceRefs must be a list")
    source_ids = source.get("sourceIds") or []
    if not isinstance(source_ids, list):
        raise _invalid("literature sourceIds must be a list")
    supplied = {
        str(ref.get("sourceId") or ref.get("id")) for ref in references if isinstance(ref, dict)
    }
    locators = source.get("locators") or {}
    if not isinstance(locators, dict):
        raise _invalid("literature locators must map source IDs to text locators")
    for source_id in source_ids:
        if str(source_id) not in supplied:
            references.append(
                {
                    "sourceId": str(source_id),
                    "locator": locators.get(
                        str(source_id), source.get("locator", {}) if len(source_ids) == 1 else {}
                    ),
                }
            )
    if not references or len(references) > 100:
        raise _invalid(
            "literature data requires 1-100 sourceRefs with sourceId and a resolvable locator"
        )
    verified = []
    for ref in references:
        if not isinstance(ref, dict):
            raise _invalid("each literature source reference must be an object")
        record = library.get_source(ident(ref.get("sourceId") or ref.get("id")))
        text = record.get("extractedText") or ""
        locator = ref.get("locator") or {}
        if not isinstance(locator, dict):
            raise _invalid("literature locator must be an object")
        quote = locator.get("quote")
        if isinstance(quote, str) and quote.strip():
            normalized, quote = " ".join(text.split()), " ".join(quote.split())
            start = normalized.find(quote)
            if len(quote) < 12 or start < 0:
                raise _invalid(
                    "literature locator quote must resolve to at least 12 characters "
                    "in its current source"
                )
            resolved = {
                "quote": quote,
                "start": start,
                "end": start + len(quote),
                "basis": "whitespace_normalized_text",
            }
        else:
            range_start, range_end = locator.get("start"), locator.get("end")
            if (
                not isinstance(range_start, int)
                or not isinstance(range_end, int)
                or isinstance(range_start, bool)
                or isinstance(range_end, bool)
                or not 0 <= range_start < range_end <= len(text)
                or range_end - range_start < 12
            ):
                raise _invalid(
                    "literature locator needs a matching quote or valid start/end text range"
                )
            resolved = {
                "quote": text[range_start:range_end],
                "start": range_start,
                "end": range_end,
                "basis": "extracted_text",
            }
        verified.append(
            {
                "kind": "source",
                "sourceId": record["id"],
                "revision": record["revision"],
                "checksum": record["checksum"],
                "locator": resolved,
            }
        )
    return {
        **source,
        "sourceIds": list(dict.fromkeys(ref["sourceId"] for ref in verified)),
        "sourceRefs": verified,
    }


def _computed(db: Session, ctx: ServiceContext, source: dict[str, Any]) -> dict[str, Any]:
    from studio.domain.learning.workspace_runtime.models import LearningJob
    from studio.persistence.models import Run

    references = copy.deepcopy(source.get("resultRefs") or [])
    if not isinstance(references, list):
        raise _invalid("computed resultRefs must be a list")
    run_ids, job_ids = source.get("runIds") or [], source.get("jobIds") or []
    if not isinstance(run_ids, list) or not isinstance(job_ids, list):
        raise _invalid("computed runIds and jobIds must be lists")
    references.extend({"runId": value} for value in run_ids)
    references.extend({"jobId": value} for value in job_ids)
    if not references or len(references) > 100:
        raise _invalid(
            "computed data requires completed engine resultRefs containing runId or jobId"
        )
    verified = []
    for ref in references:
        if not isinstance(ref, dict) or bool(ref.get("runId")) == bool(ref.get("jobId")):
            raise _invalid("each computed reference must identify one runId or jobId")
        if ref.get("runId"):
            run = db.scalar(
                select(Run).where(
                    Run.id == ident(ref["runId"]),
                    Run.workspace_id == ctx.workspace_id,
                    Run.requested_by == ctx.principal_id,
                )
            )
            if run is None or run.status != "succeeded" or not run.result_summary:
                raise _invalid("computed run must be a successful result owned by the current user")
            engine, result = run.kind, run.result_summary
            reference = {"runId": str(run.id)}
        else:
            job = db.scalar(
                select(LearningJob).where(
                    LearningJob.id == ident(ref["jobId"]),
                    LearningJob.workspace_id == ctx.workspace_id,
                    LearningJob.owner_id == ctx.principal_id,
                )
            )
            if (
                job is None
                or job.state != "completed"
                or not job.result
                or not job.config.get("backend")
            ):
                raise _invalid(
                    "computed job must have a completed engine result owned by the current user"
                )
            engine, result = str(job.config["backend"]), job.result
            reference = {"jobId": str(job.id)}
        path = ref.get("resultPath", [])
        if isinstance(path, str):
            path = path.removeprefix("$.").split(".") if path else []
        if not isinstance(path, list) or len(path) > 20:
            raise _invalid("computed resultPath must be a bounded list of result keys")
        value: Any = result
        try:
            for key in path:
                value = value[key] if isinstance(value, dict) else value[int(key)]
        except (KeyError, IndexError, ValueError, TypeError):
            raise _invalid(
                "computed resultPath does not resolve to a persisted engine result"
            ) from None
        verified.append(
            {
                **reference,
                "engine": engine,
                "resultPath": path,
                "resultDigest": hashlib.sha256(
                    json.dumps(value, sort_keys=True, default=str).encode()
                ).hexdigest(),
            }
        )
    return {**source, "resultRefs": verified}


def guard_agent_dataset(
    db: Session, ctx: ServiceContext, settings: Settings, payload: dict[str, Any]
) -> dict[str, Any]:
    """Generated payloads can never self-certify as measured or user-authored."""
    result = copy.deepcopy(payload)
    kind = result.get("dataKind", "synthetic")
    if kind in {"experimental", "user_authored"}:
        raise _invalid(
            "agent-written rows cannot be experimental or user_authored; "
            "use verified lab import or dataset_from_notebook, "
            "otherwise classify them synthetic"
        )
    if kind not in {"synthetic", "literature", "computed"}:
        raise _invalid("agent datasets must be synthetic, literature or computed")
    source = result.get("source") or {}
    if not isinstance(source, dict):
        raise _invalid("dataset provenance must be a JSON object")
    if kind == "literature":
        source = _literature(db, ctx, settings, source)
    elif kind == "computed":
        source = _computed(db, ctx, source)
    result["dataKind"] = kind
    result["source"] = {
        **source,
        "createdBy": "agent",
        "scientificStatus": "not_validated",
        "validationMeaning": "origin_and_structure_checks_only",
    }
    return result
