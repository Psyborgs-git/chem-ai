"""Bounded custom dataset parsing and molecule/scaffold leakage prevention."""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
from collections import Counter
from typing import Any

MAX_DATASET_BYTES = 20 * 1024 * 1024
MAX_ROWS = 50_000
MAX_CELL = 64_000


def chat_record(value: Any) -> list[dict[str, Any]]:
    """Validate persisted training conversations without executing their tools."""
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list) or not 2 <= len(value) <= 128:
        raise ValueError("messages must contain 2-128 chat turns")
    result = []
    calls: set[str] = set()
    assistant = False
    for item in value:
        if not isinstance(item, dict) or item.get("role") not in {
            "system",
            "user",
            "assistant",
            "tool",
        }:
            raise ValueError("messages contain an unsupported role")
        role, content = item["role"], item.get("content")
        if content is not None and not isinstance(content, str):
            raise ValueError("message content must be text or null")
        turn: dict[str, Any] = {"role": role, "content": content}
        if role == "assistant":
            assistant = True
            tool_calls = item.get("tool_calls")
            if tool_calls:
                if not isinstance(tool_calls, list) or len(tool_calls) > 32:
                    raise ValueError("tool_calls must be a bounded list")
                for call in tool_calls:
                    if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
                        raise ValueError("tool calls require a function")
                    identifier, function = call.get("id"), call["function"]
                    if not isinstance(identifier, str) or not identifier or identifier in calls:
                        raise ValueError("tool call IDs must be unique nonempty strings")
                    if not isinstance(function.get("name"), str) or not function["name"]:
                        raise ValueError("tool calls require a function name")
                    arguments = function.get("arguments", "{}")
                    if isinstance(arguments, str):
                        arguments = json.loads(arguments)
                    if not isinstance(arguments, dict):
                        raise ValueError("tool arguments must be JSON objects")
                    calls.add(identifier)
                turn["tool_calls"] = copy.deepcopy(tool_calls)
        if role == "tool":
            if item.get("tool_call_id") not in calls:
                raise ValueError("tool turn must refer to an earlier assistant call")
            turn["tool_call_id"] = item["tool_call_id"]
        result.append(turn)
    if not assistant or not any(item["role"] == "user" for item in result):
        raise ValueError("messages require both user and assistant turns")
    if result[-1]["role"] != "assistant":
        raise ValueError("training conversations must finish with an assistant target")
    if len(json.dumps(result)) > MAX_CELL:
        raise ValueError("messages exceed the row context limit")
    return result


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def canonical_structure(smiles: str) -> dict[str, str]:
    from rdkit import Chem, rdBase
    from rdkit.Chem.Scaffolds import MurckoScaffold

    if not smiles or len(smiles) > 8192:
        raise ValueError("SMILES must contain 1-8192 characters")
    with rdBase.BlockLogs():
        mol = Chem.MolFromSmiles(smiles)
    if mol is None or mol.GetNumAtoms() == 0:
        raise ValueError("SMILES could not be parsed and sanitized")
    canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
    # Stereo variants must not enter independent partitions.
    identity = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=False)
    scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=False)  # type: ignore[no-untyped-call]
    return {"smiles": canonical, "identity": identity, "scaffold": scaffold or identity}


def _parse(content: str, fmt: str) -> list[dict[str, Any]]:
    if len(content.encode("utf-8")) > MAX_DATASET_BYTES:
        raise ValueError("Dataset exceeds the 20 MiB import limit")
    if fmt == "csv":
        result = list(csv.DictReader(io.StringIO(content)))
    elif fmt == "jsonl":
        result = []
        for number, line in enumerate(content.splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except ValueError as exc:
                raise ValueError(f"Line {number}: invalid JSON") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Line {number}: expected a JSON object")
            result.append(value)
    elif fmt in {"smi", "smiles"}:
        result = []
        for line in content.splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                parts = line.split(maxsplit=1)
                result.append({"smiles": parts[0], "name": parts[1] if len(parts) > 1 else ""})
    elif fmt == "sdf":
        from rdkit import Chem, rdBase

        result = []
        with rdBase.BlockLogs():
            supplier = Chem.ForwardSDMolSupplier(io.BytesIO(content.encode()))
            for index, mol in enumerate(supplier):
                if mol is None:
                    result.append({"_parseError": f"SDF record {index + 1} is invalid"})
                else:
                    result.append({**mol.GetPropsAsDict(), "smiles": Chem.MolToSmiles(mol)})
    else:
        raise ValueError("Supported formats: csv, jsonl, smi, sdf")
    if len(result) > MAX_ROWS:
        raise ValueError(f"Dataset exceeds {MAX_ROWS} rows")
    return result


def validate_import(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    content = payload.get("content")
    if not isinstance(content, str):
        raise ValueError("content must be UTF-8 text")
    mapping = payload.get("mapping") or {}
    if not isinstance(mapping, dict):
        raise ValueError("mapping must map field names to source columns")
    parsed = _parse(content, str(payload.get("format", "csv")).lower())
    rows: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    duplicates = 0
    seen: set[str] = set()
    for index, original in enumerate(parsed, 1):
        try:
            if "_parseError" in original:
                raise ValueError(original["_parseError"])
            record: dict[str, Any] = {"id": f"row-{index}", "sourceRow": index}
            for key in (
                "smiles",
                "target",
                "prompt",
                "response",
                "chosen",
                "rejected",
                "expected",
                "unit",
                "method",
                "documentId",
                "psmiles",
                "polymerId",
                "property",
                "sourceId",
                "metadata",
                "conditions",
                "sourceRefs",
                "evaluation",
                "messages",
                "tools",
            ):
                source_key = mapping.get(key, key)
                if source_key and source_key in original and original[source_key] is not None:
                    value = original[source_key]
                    if len(str(value)) > MAX_CELL:
                        raise ValueError(f"{key} exceeds {MAX_CELL} characters")
                    record[key] = value
            for key in ("metadata", "conditions", "sourceRefs", "evaluation", "tools"):
                if key in record and isinstance(record[key], str):
                    record[key] = json.loads(record[key])
            if "messages" in record:
                record["messages"] = chat_record(record["messages"])
            if "tools" in record and (
                not isinstance(record["tools"], list) or len(record["tools"]) > 128
            ):
                raise ValueError("tools must be a bounded list")
            metadata_columns = payload.get("metadataColumns", [])
            if not isinstance(metadata_columns, list) or len(metadata_columns) > 30:
                raise ValueError("metadataColumns must contain at most 30 columns")
            if metadata_columns:
                record["metadata"] = {
                    **(record.get("metadata") or {}),
                    **{str(key): original[key] for key in metadata_columns if key in original},
                }
            defaults = payload.get("defaults") or {}
            if not isinstance(defaults, dict):
                raise ValueError("defaults must be a metadata object")
            for key in ("unit", "method", "property", "conditions"):
                if key not in record and key in defaults:
                    record[key] = copy.deepcopy(defaults[key])
            if not record.get("smiles") and record.get("psmiles"):
                record["smiles"] = str(record["psmiles"])
            if record.get("smiles"):
                record["originalSmiles"] = str(record["smiles"])
                record.update(canonical_structure(str(record["smiles"])))
            if "target" in record and str(record["target"]).strip():
                value = float(record["target"])
                if not math.isfinite(value):
                    raise ValueError("Target must be a finite number")
                record["target"] = value
            elif "target" in record:
                del record["target"]
            if not record.get("smiles") and not record.get("prompt") and not record.get("messages"):
                raise ValueError("A row needs a valid SMILES structure, prompt or conversation")
            if record.get("chosen") and not record.get("rejected"):
                raise ValueError("Preference data requires both chosen and rejected responses")
            # Equal records retain exactly one identity; conflicting measurements remain visible.
            signature = digest(
                {k: v for k, v in record.items() if k not in {"id", "sourceRow", "originalSmiles"}}
            )
            if signature in seen:
                duplicates += 1
                continue
            seen.add(signature)
            rows.append(record)
        except (ValueError, TypeError, KeyError) as exc:
            rejects.append({"row": index, "reason": str(exc)[:300]})
    counts = Counter("molecular" if "smiles" in row else "assistant" for row in rows)
    return rows, {
        "total": len(parsed),
        "accepted": len(rows),
        "rejected": len(rejects),
        "duplicates": duplicates,
        "rejections": rejects[:1000],
        "rowKinds": dict(counts),
        "validation": "structure_and_schema",
        "scientificStatus": "not_validated",
    }


def split_rows(rows: list[dict[str, Any]], seed: int = 0) -> dict[str, str]:
    """Connected identity/scaffold/document groups stay in one partition."""
    parents = list(range(len(rows)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    keys: dict[str, int] = {}
    for index, row in enumerate(rows):
        grouping = []
        for name in ("identity", "scaffold", "documentId"):
            if row.get(name):
                grouping.append(f"{name}:{row[name]}")
        if row.get("prompt"):
            grouping.append(f"prompt:{digest(str(row['prompt']).strip())}")
        if row.get("messages"):
            user_turns = [
                str(turn.get("content", "")).strip()
                for turn in row["messages"]
                if turn.get("role") == "user"
            ]
            grouping.append(f"conversation:{digest(user_turns)}")
        for key in grouping:
            if key in keys:
                parents[find(index)] = find(keys[key])
            else:
                keys[key] = index
    groups = sorted(
        {find(i) for i in range(len(rows))}, key=lambda i: digest([seed, rows[i]["id"]])
    )
    assigned = {group: "train" for group in groups}
    tool_groups = {
        find(i) for i, row in enumerate(rows) if row.get("evaluation", {}).get("expectedToolCalls")
    }
    # Keep actual tool-call tasks represented in evaluation without splitting
    # any connected source/conversation group or selecting on model outcomes.
    strata = [groups]
    if len(tool_groups) >= 3 and len(groups) - len(tool_groups) >= 3:
        strata = [
            [g for g in groups if g in tool_groups],
            [g for g in groups if g not in tool_groups],
        ]
    for stratum in strata:
        if len(stratum) >= 3:
            heldout = max(1, int(len(stratum) * 0.1))
            for group in stratum[:heldout]:
                assigned[group] = "final"
            for group in stratum[heldout : heldout * 2]:
                assigned[group] = "development"
    return {str(row["id"]): assigned[find(i)] for i, row in enumerate(rows)}
