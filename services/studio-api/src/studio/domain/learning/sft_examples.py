"""SFT example construction (CS-0801, §17.2-17.3).

Turns the *included* records of a frozen ``assistant_sft`` snapshot into
the dataset the pinned trainer consumes:

- research sessions become task/tool/citation turns — context,
  observable messages/tool calls/results, and the *reviewed* response
  (an assistant message authored by a human principal);
- hidden reasoning traces never enter the bytes: ``kind="rationale"``
  messages are dropped and recorded as exclusions;
- quality gates run BEFORE serialization — duplicates, contradictions,
  missing units on claim-backed quantities, and held-out label leakage
  are detected and excluded with reasons recorded;
- split groups come from CS-0602's union-find so correlated examples
  (same session, same normalized context) can never straddle a
  partition boundary; the ``final`` partition stays untouched.

The output is a JSONL byte payload (one ``SftTrainingExample`` per
line) plus a manifest of counts/exclusions — the payload digest is the
``dataset_digest`` the eligibility gate binds to the approval.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine_adapter_sft.contracts import (
    SftTrainingExample,
    sha256_text,
)
from studio.auth.context import ServiceContext
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    DatasetSnapshot,
    EvidenceClaim,
    ResearchSession,
    SessionMessage,
)

SFT_SPLIT_SEED = 0
SFT_SPLIT_FRACTIONS = {"train": 0.6, "development": 0.15, "calibration": 0.15, "final": 0.10}

# Units the claim-backed quantity check recognizes; a response quoting
# a claim's numeric value without its unit is excluded (§17.3).
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


class SftExclusion(dict[str, Any]):
    """One recorded exclusion — never silently dropped (§17.3)."""

    def __init__(self, example_id: str, reason: str, detail: str | None = None) -> None:
        super().__init__(exampleId=example_id, reason=reason, detail=detail)


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()


def _message_is_hidden_trace(m: SessionMessage) -> bool:
    return m.kind == "rationale" or (m.role == "system" and m.kind != "message")


def _extract_turns(
    session: ResearchSession, messages: list[SessionMessage]
) -> tuple[list[dict[str, Any]], list[SftExclusion]]:
    """Group session messages into supervised turns.

    A turn = the observable prefix (user/system/tool messages + tool
    calls/results) up to a *reviewed* assistant response — in this
    system assistant content is human-posted through the API, so
    ``created_by`` on the response message IS the review provenance.
    ``rationale``/hidden-trace messages never enter a turn; they are
    counted once each as exclusions.
    """
    turns: list[dict[str, Any]] = []
    exclusions: list[SftExclusion] = []
    pending: list[SessionMessage] = []
    pending_tools: list[SessionMessage] = []
    pending_results: list[SessionMessage] = []
    for m in messages:
        if _message_is_hidden_trace(m):
            exclusions.append(SftExclusion(str(m.id), "hidden_reasoning_trace", f"kind:{m.kind}"))
            continue
        if m.kind == "tool_call":
            pending_tools.append(m)
            continue
        if m.kind == "tool_result":
            pending_results.append(m)
            continue
        if m.role == "assistant" and m.kind == "message":
            if m.created_by is None:
                exclusions.append(
                    SftExclusion(str(m.id), "unreviewed_response", "no author principal")
                )
                pending, pending_tools, pending_results = [], [], []
                continue
            turns.append(
                {
                    "context_messages": pending,
                    "tool_calls": pending_tools,
                    "tool_results": pending_results,
                    "response": m,
                }
            )
            pending, pending_tools, pending_results = [], [], []
            continue
        pending.append(m)
    return turns, exclusions


def _turn_to_example(session: ResearchSession, turn: dict[str, Any]) -> dict[str, Any]:
    response = turn["response"]
    payload = {
        "context": {
            "task_id": str(session.task_id),
            "session_id": str(session.id),
            "manifest_id": str(session.start_manifest_id) if session.start_manifest_id else None,
        },
        "messages": [
            {
                "role": m.role,
                "kind": "message",
                "content": m.content,
                "refs": list((m.refs or {}).get("claims") or []),
            }
            for m in turn["context_messages"]
        ],
        "tool_calls": [
            {
                "name": (m.refs or {}).get("tool", "unknown"),
                "arguments": (m.refs or {}).get("arguments", {}),
                "call_id": str(m.id),
            }
            for m in turn["tool_calls"]
        ],
        "tool_results": [
            {"name": (m.refs or {}).get("tool", "unknown"), "call_id": None, "content": m.content}
            for m in turn["tool_results"]
        ],
        "response": {
            "content": response.content,
            "refs": list((response.refs or {}).get("claims") or []),
        },
        "provenance": {
            "message_id": str(response.id),
            "author_principal_id": str(response.created_by) if response.created_by else None,
            "reviewed_at": response.created_at.isoformat() if response.created_at else None,
            "kind": "reviewed_response",
        },
        "rights": {"training": "owned", "source_classes": ["research_session"]},
        "group_keys": [f"session:{session.id}"],
    }
    payload["example_digest"] = SftTrainingExample.digest_payload(payload)
    return payload


def _detect_duplicates_and_contradictions(
    examples: list[dict[str, Any]], exclusions: list[SftExclusion]
) -> list[dict[str, Any]]:
    """Identical supervision payload twice → keep first, exclude rest;
    same context with a different response → exclude BOTH (§17.3)."""
    by_context: dict[str, list[dict[str, Any]]] = {}
    for ex in examples:
        context_key = sha256_text(
            json.dumps(
                {
                    "messages": ex["messages"],
                    "tool_calls": ex["tool_calls"],
                    "tool_results": ex["tool_results"],
                },
                sort_keys=True,
            )
        )
        by_context.setdefault(context_key, []).append(ex)

    kept: list[dict[str, Any]] = []
    for group in by_context.values():
        responses = {ex["example_digest"] for ex in group}
        if len(responses) > 1:
            for ex in group:
                exclusions.append(
                    SftExclusion(ex["_id"], "contradiction", "same context, different response")
                )
            continue
        kept.append(group[0])
        for dup in group[1:]:
            exclusions.append(SftExclusion(dup["_id"], "duplicate"))
    return kept


def _detect_missing_units(
    examples: list[dict[str, Any]],
    claims: dict[uuid.UUID, EvidenceClaim],
    exclusions: list[SftExclusion],
) -> list[dict[str, Any]]:
    """A response that quotes a claim's quantity must carry its unit.

    The check is deliberately conservative and documented: for every
    claim the response cites via ``refs``, if the claim statement
    encodes ``<number> <unit>`` and the response contains that number
    but not the unit string, the example is excluded.
    """
    kept: list[dict[str, Any]] = []
    for ex in examples:
        claim_ids = [r for r in ex["response"]["refs"] if _looks_uuid(r)]
        claim_ids += [r for m in ex["messages"] for r in m["refs"] if _looks_uuid(r)]
        missing: list[str] = []
        for cid in set(claim_ids):
            claim = claims.get(uuid.UUID(cid))
            if claim is None:
                continue
            statement = (
                claim.statement
                if isinstance(claim.statement, str)
                else json.dumps(claim.statement, sort_keys=True)
            )
            match = re.search(r"(\d+(?:\.\d+)?)\s*([a-zA-Z%µ°/·\-\^0-9]+)", statement)
            if not match:
                continue
            value, unit = match.group(1), match.group(2)
            body = ex["response"]["content"]
            if value in body and unit not in body:
                missing.append(f"{value} {unit} (claim {cid})")
        if missing:
            exclusions.append(SftExclusion(ex["_id"], "missing_units", "; ".join(missing)))
            continue
        kept.append(ex)
    return kept


def _looks_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return False
    return True


def _detect_leaked_labels(
    examples: list[dict[str, Any]],
    held_out_labels: list[str],
    exclusions: list[SftExclusion],
) -> list[dict[str, Any]]:
    """A train/dev/calibration example must not embed a held-out
    (``final``) label — outcome labels can never leak (§17.3)."""
    if not held_out_labels:
        return examples
    kept: list[dict[str, Any]] = []
    for ex in examples:
        body = ex["response"]["content"]
        leaked = [label for label in held_out_labels if label and label in body]
        if leaked and ex["_partition"] != "final":
            exclusions.append(SftExclusion(ex["_id"], "leaked_outcome_label", leaked[0][:64]))
            continue
        kept.append(ex)
    return kept


def _assign_partitions(examples: list[dict[str, Any]]) -> None:
    """Group-aware split via CS-0602 — examples sharing a group key
    can never straddle a boundary (§17.2)."""
    from studio.domain.learning.splits import (
        SplitPolicy,
        SplitRecord,
        assign_partitions,
    )

    policy = SplitPolicy(seed=SFT_SPLIT_SEED, fractions=SFT_SPLIT_FRACTIONS)
    records = [
        SplitRecord(
            record_id=ex["_id"],
            group_keys=frozenset([*ex["group_keys"], f"dedup:{ex['example_digest']}"]),
            label=ex["response"]["content"],
            eligible=True,
        )
        for ex in examples
    ]
    assignment = assign_partitions(records, policy)
    for ex in examples:
        ex["_partition"] = assignment[ex["_id"]]


def build_dataset(
    db: Session, ctx: ServiceContext, snapshot: DatasetSnapshot
) -> tuple[bytes, dict[str, Any]]:
    """Serialize the frozen snapshot's session entries into the JSONL
    payload + manifest. Read-only over sources; the caller persists."""
    if snapshot.purpose not in ("assistant_sft", "preference_pairs"):
        raise DomainError(ErrorCode.VALIDATION, f"purpose {snapshot.purpose} is not an SFT dataset")
    session_entries = [
        e
        for e in snapshot.manifest.get("entries", [])
        if e.get("recordKind") == "session" and not e.get("excluded")
    ]
    exclusions: list[SftExclusion] = []
    examples: list[dict[str, Any]] = []
    for entry in session_entries:
        sid = uuid.UUID(str(entry["recordId"]))
        session = db.get(ResearchSession, sid)
        if session is None:
            exclusions.append(SftExclusion(str(sid), "missing_source", "session deleted"))
            continue
        messages = (
            db.execute(
                select(SessionMessage)
                .where(SessionMessage.session_id == sid)
                .order_by(SessionMessage.created_at, SessionMessage.id)
            )
            .scalars()
            .all()
        )
        turns, excl = _extract_turns(session, list(messages))
        exclusions.extend(excl)
        for turn in turns:
            ex = _turn_to_example(session, turn)
            ex["_id"] = hashlib.sha256(f"{session.id}:{turn['response'].id}".encode()).hexdigest()[
                :24
            ]
            examples.append(ex)

    examples = _detect_duplicates_and_contradictions(examples, exclusions)

    claims = {
        c.id: c
        for c in db.execute(
            select(EvidenceClaim).where(EvidenceClaim.workspace_id == ctx.workspace_id)
        )
        .scalars()
        .all()
    }
    examples = _detect_missing_units(examples, claims, exclusions)
    _assign_partitions(examples)

    # Held-out labels = final-partition response texts; scan the rest.
    held_out = [e["response"]["content"] for e in examples if e["_partition"] == "final"]
    examples = _detect_leaked_labels(examples, held_out, exclusions)

    for ex in examples:
        ex["partition"] = ex.pop("_partition")
        ex["example_id"] = ex.pop("_id")
        SftTrainingExample.model_validate(ex)  # contract check before persist

    payload = "\n".join(json.dumps(e, sort_keys=True, ensure_ascii=True) for e in examples).encode(
        "utf-8"
    )
    digest = hashlib.sha256(payload).hexdigest()

    partitions: dict[str, int] = {}
    for e in examples:
        partitions[e["partition"]] = partitions.get(e["partition"], 0) + 1

    manifest = {
        "schemaName": "sft_dataset_manifest",
        "schemaVersion": 1,
        "purpose": snapshot.purpose,
        "snapshotId": str(snapshot.id),
        "snapshotDigest": snapshot.digest,
        "exampleCount": len(examples),
        "partitions": partitions,
        "splitPolicy": {
            "name": "sft_v1",
            "seed": SFT_SPLIT_SEED,
            "fractions": SFT_SPLIT_FRACTIONS,
            "grouped": True,
        },
        "exclusions": [dict(e) for e in exclusions],
        "excludedCount": len(exclusions),
        "hiddenTracesPolicy": "dropped; recorded as exclusions",
        "datasetDigest": digest,
        "scientificStatus": "not_validated",
        "notes": "fixture/reviewed-response data; not scientific validation",
    }
    return payload, manifest
