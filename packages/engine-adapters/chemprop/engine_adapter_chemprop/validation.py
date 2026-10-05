"""Independent checks. No Chemprop output is trusted (§13.1, §15.3).

Contract-level sanity only — chemistry validity is the engine's
(RDKit-backed) job. These checks bound inputs, verify artifact lineage,
and confirm every requested row id got exactly one finite prediction.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def check_smiles(smiles: str) -> str:
    """Reject structurally malformed input; chemistry parsing belongs
    to the engine inside the container."""
    if smiles != smiles.strip():
        raise ValueError("smiles has surrounding whitespace")
    if any(ord(c) < 32 or ord(c) == 127 for c in smiles):
        raise ValueError("smiles contains control characters")
    return smiles


def check_rows(rows: Any) -> None:
    for row in rows:
        check_smiles(row.smiles)


def model_file_digest(spec_digest: str, files: dict[str, bytes]) -> str:
    """Content-addressed lineage: train spec digest + every artifact
    file hash. A prediction may only claim this digest when it presents
    the identical artifacts."""
    parts = [spec_digest]
    for name in sorted(files):
        parts.append(f"{name}:{hashlib.sha256(files[name]).hexdigest()}")
    return hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()


def validate_predictions(
    requested_ids: list[str],
    raw: list[dict[str, Any]],
    ensemble_size: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Untrusted engine output: every requested row gets at most one
    prediction; members count must match the declared ensemble; every
    value finite. Nonconforming rows are rejected, never repaired."""
    accepted: list[dict[str, Any]] = []
    rejected = {"invalid": 0, "duplicate": 0}
    seen: set[Any] = set()
    requested = set(requested_ids)
    for item in raw:
        rid = item.get("row_id")
        if rid in seen:
            rejected["duplicate"] += 1
            continue
        seen.add(rid)
        members = item.get("members")
        value = item.get("value")
        ok = (
            isinstance(rid, str)
            and rid in requested
            and isinstance(value, int | float)
            and not isinstance(value, bool)
            and math.isfinite(value)
            and isinstance(members, list)
            and len(members) == ensemble_size
            and all(
                isinstance(m, int | float) and not isinstance(m, bool) and math.isfinite(m)
                for m in members
            )
        )
        if ok:
            accepted.append({"row_id": rid, "value": float(item["value"]), "members": members})
        else:
            rejected["invalid"] += 1
    return accepted, rejected
