"""Auditable assistant examples compiled from retained polymer records and tool traces."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select

from studio.domain.agent_workspace.models import AgentMessage
from studio.domain.agent_workspace.workflows import WorkflowService
from studio.domain.learning.workspace import LearningWorkspaceService
from studio.domain.learning.workspace_runtime.models import LearningDataset
from studio.errors import DomainError, ErrorCode


def prepare_examples(db: Any, ctx: Any, settings: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """This creates synthetic teaching tasks, not new property measurements."""
    workflows = WorkflowService(db, ctx)
    workflow = workflows.get(payload.get("workflowId"), lock=True)
    learning = LearningWorkspaceService(db, ctx, settings)
    identifiers = payload.get("datasetIds", [])
    if not isinstance(identifiers, list) or not 1 <= len(identifiers) <= 3:
        raise DomainError(ErrorCode.VALIDATION, "Choose one to three workflow property datasets")
    examples, refs = [], []
    for identifier in identifiers:
        workflows.require_resource(workflow, "dataset", identifier)
        dataset = learning._owned(LearningDataset, str(identifier))
        learning.authorize_dataset_training(str(identifier))
        if dataset.source.get("kind") != "external_computed":
            raise DomainError(ErrorCode.VALIDATION, "Use original-source computed property data")
        sources = dataset.source.get("sourceRefs", [])
        if not sources:
            raise DomainError(
                ErrorCode.VALIDATION, "Computed data needs retained source references"
            )
        for ref in sources:
            workflows.require_resource(workflow, "source", ref.get("sourceId") or ref.get("id"))
        refs.extend(sources)
        source_id = str(sources[0]["sourceId"])
        ordered = sorted(
            dataset.rows,
            key=lambda row: hashlib.sha256(
                str(row.get("polymerId", row["id"])).encode()
            ).hexdigest(),
        )
        for row in ordered[:180]:
            if "target" not in row:
                continue
            polymer_id = str(row.get("polymerId", row["id"]))
            prop = str(
                row.get(
                    "property",
                    dataset.source.get("externalComputation", {}).get("property", "property"),
                )
            )
            unit = str(row.get("unit", "1"))
            excerpt = {
                "polymerId": polymer_id,
                "repeatSmiles": row.get("originalSmiles", row.get("psmiles", row.get("smiles"))),
                "property": prop,
                "value": row["target"],
                "unit": unit,
                "sourceId": source_id,
                "origin": "computed",
                "conditions": row.get("conditions", {}),
                "method": row.get("method", "RadonPy"),
                "materialScope": "amorphous polymer simulation",
            }
            answer = {
                "property": prop,
                "measurement": {"value": row["target"], "unit": unit},
                "origin": "computed",
                "citations": [source_id],
                "supportsSilkEquivalence": False,
            }
            examples.append(
                {
                    "prompt": "Extract the property from this cited simulation record. "
                    "Return only JSON with "
                    "property, measurement {value,unit}, origin, citations [sourceId], and "
                    "supportsSilkEquivalence. A bulk simulation does not measure "
                    "fabric hand, drape or lustre. "
                    "Do not invent missing measurements. Record: "
                    + json.dumps(excerpt, sort_keys=True),
                    "response": json.dumps(answer, sort_keys=True),
                    "documentId": "polymer-record:" + polymer_id,
                    "sourceRefs": sources,
                    "evaluation": {
                        "jsonRequired": True,
                        "requiredFields": list(answer),
                        "allowedCitations": [source_id],
                        "requiredCitations": [source_id],
                        "numericTargets": [
                            {"field": "measurement", "value": row["target"], "unit": unit}
                        ],
                        "forbiddenClaims": [
                            "experimentally validated silk",
                            "proven silk replacement",
                        ],
                    },
                }
            )
    # Reuse executed calls, not invented tool results. Every trace remains tied
    # to this workflow and its original event ID; failed calls are excluded.
    from studio.domain.agent_workspace import tools

    events = list(
        db.scalars(
            select(AgentMessage)
            .where(
                AgentMessage.thread_id == workflow.thread_id,
                AgentMessage.owner_id == ctx.principal_id,
                AgentMessage.workspace_id == ctx.workspace_id,
            )
            .order_by(AgentMessage.created_at)
        )
    )
    calls = {
        (event.run_id, event.refs.get("toolCallId")): event
        for event in events
        if event.kind == "tool_call"
    }
    for event in events:
        if event.kind != "tool_result" or len(examples) >= 400:
            continue
        original = calls.get((event.run_id, event.refs.get("toolCallId")))
        if original is None:
            continue
        try:
            outcome = json.loads(event.content)
            if not isinstance(outcome, dict) or outcome.get("ok") is not True:
                continue
            call = json.loads(original.content)
            name, args = call["name"], call["arguments"]
            if name not in {
                "learning_catalog",
                "read_resource",
                "read_dataset",
                "training_preflight",
            }:
                continue
            workflows.authorize_tool(workflow, name, args)
            definition = next(item for item in tools.catalog() if item["name"] == name)
        except (ValueError, KeyError, StopIteration, DomainError):
            continue
        for wording in ("Use", "Call", "Invoke", "Inspect with"):
            if len(examples) >= 400:
                break
            prompt = (
                f"{wording} {name} with these exact arguments: {json.dumps(args, sort_keys=True)}"
            )
            messages = [
                {"role": "user", "content": prompt},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {"name": name, "arguments": args},
                        }
                    ],
                },
            ]
            base = {
                "documentId": "tool-trace:" + str(event.id),
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": definition["description"],
                            "parameters": definition["input_schema"],
                        },
                    }
                ],
                "metadata": {"toolEventId": str(event.id), "workflowId": str(workflow.id)},
            }
            # The held-out target is the native tool call itself, so tool
            # correctness is measured rather than a fixed closing sentence.
            examples.append(
                {
                    **base,
                    "messages": messages,
                    "evaluation": {
                        "expectedToolCalls": [{"name": name, "arguments": args}],
                    },
                }
            )
            # Full results add a second, final-answer target. Keep these short
            # enough to retain that target within the 1024-token pilot context.
            if len(event.content) <= 600 and len(examples) < 400:
                examples.append(
                    {
                        **base,
                        "messages": [
                            *messages,
                            {"role": "tool", "tool_call_id": call["id"], "content": event.content},
                            {
                                "role": "assistant",
                                "content": f"{name} returned the recorded application result.",
                            },
                        ],
                    }
                )
    if len(examples) < 100:
        raise DomainError(
            ErrorCode.VALIDATION, "At least 100 auditable source examples are required"
        )
    result = learning.import_dataset(
        {
            "name": payload.get("name", "Polymer research assistant tasks"),
            "format": "jsonl",
            "content": "\n".join(json.dumps(item) for item in examples),
            "dataKind": "synthetic",
            "rights": "allowed",
            "source": {
                "kind": "source_grounded_synthetic",
                "sourceRefs": refs,
                "datasetIds": identifiers,
                "workflowId": str(workflow.id),
                "generation": "record extraction tasks and actually executed app traces",
                "scientificStatus": "not_validated",
            },
        }
    )
    workflows.add_resource(workflow, "dataset", result["id"])
    return result
