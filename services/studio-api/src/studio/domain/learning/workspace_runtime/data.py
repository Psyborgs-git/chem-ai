"""Bounded custom dataset parsing and molecule/scaffold leakage prevention."""

from __future__ import annotations

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
            ):
                source_key = mapping.get(key, key)
                if source_key and source_key in original and original[source_key] is not None:
                    value = original[source_key]
                    if len(str(value)) > MAX_CELL:
                        raise ValueError(f"{key} exceeds {MAX_CELL} characters")
                    record[key] = value
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
            if not record.get("smiles") and not record.get("prompt"):
                raise ValueError("A row needs a valid SMILES structure or a prompt")
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
        for key in grouping:
            if key in keys:
                parents[find(index)] = find(keys[key])
            else:
                keys[key] = index
    groups = sorted(
        {find(i) for i in range(len(rows))}, key=lambda i: digest([seed, rows[i]["id"]])
    )
    assigned = {group: "train" for group in groups}
    if len(groups) >= 3:
        heldout = max(1, int(len(groups) * 0.1))
        for group in groups[:heldout]:
            assigned[group] = "final"
        for group in groups[heldout : heldout * 2]:
            assigned[group] = "development"
    return {str(row["id"]): assigned[find(i)] for i, row in enumerate(rows)}
