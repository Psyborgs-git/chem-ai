"""Leakage-safe splits and evaluation contexts (CS-0602, §17.2, §18).

Pure functions — no I/O, no DB. Three guarantees:

1. **Grouping (AT-0602-1).** Records sharing any group key (formula
   family, preparation batch, near-duplicate hash, derived-document
   lineage, repeated-measurement sample) belong to ONE connected
   component; partitions are assigned per component, so related
   examples can never cross a split boundary just because they have
   different row ids.

2. **Isolation (AT-0602-2).** ``prepare_evaluation`` runs a
   contamination check: a held-out record appearing in a predictor's
   training lineage, or a held-out label/id surfacing in a context
   summary, blocks the evaluation with ``EVAL_CONTAMINATION``.

3. **Partition-only fitting (AT-0602-3).** ``fit_transform`` calls
   ``fit`` only on records in the allowed partitions; transforms may
   then *transform* any partition but never see test labels or test
   features while fitting.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from studio.errors import DomainError, ErrorCode

PARTITIONS = ("train", "development", "calibration", "final")
"""§17.2 step 5: separate partitions; ``final`` is the untouched
evaluation set, isolated by construction."""


@dataclass(frozen=True)
class SplitRecord:
    """One dataset row entering a split. ``group_keys`` link related
    records: ``formula:<family>``, ``batch:<prep batch>``,
    ``dedup:<near-duplicate hash>``, ``doc:<derived document group>``,
    ``sample:<measured sample>``."""

    record_id: str
    group_keys: frozenset[str] = frozenset()
    label: float | None = None
    eligible: bool = True


# ------------------------------------------------------------------
# grouping (connected components over shared keys)


def build_groups(records: list[SplitRecord]) -> dict[str, str]:
    """Union-find over shared group keys. Returns record_id → group_id.

    Every group key names one identity; records sharing a key end in
    the same component, and components merge transitively."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    key_owner: dict[str, str] = {}
    for rec in records:
        find(rec.record_id)
        for key in rec.group_keys:
            if key in key_owner:
                union(rec.record_id, key_owner[key])
            else:
                key_owner[key] = rec.record_id
    return {rec.record_id: find(rec.record_id) for rec in records}


# ------------------------------------------------------------------
# partition assignment


@dataclass(frozen=True)
class SplitPolicy:
    """Declared partition policy (§17.2 step 5). Fractions apply to
    whole groups, weighted by member count; assignment order is a
    seeded hash of the group id — deterministic, not row-order
    dependent."""

    seed: int = 0
    fractions: dict[str, float] = field(
        default_factory=lambda: {
            "train": 0.6,
            "development": 0.15,
            "calibration": 0.15,
            "final": 0.10,
        }
    )

    def validate(self) -> None:
        unknown = set(self.fractions) - set(PARTITIONS)
        if unknown:
            raise DomainError(ErrorCode.VALIDATION, f"unknown partitions: {sorted(unknown)}")
        total = sum(self.fractions.values())
        if total <= 0 or total > 1.0 + 1e-9:
            raise DomainError(ErrorCode.VALIDATION, f"invalid partition fractions (sum {total})")
        if self.fractions.get("final", 0) <= 0:
            raise DomainError(
                ErrorCode.VALIDATION,
                "a held-out final partition is mandatory (§17.2)",
            )


def _group_rank(group_id: str, seed: int) -> float:
    digest = hashlib.sha256(f"{seed}:{group_id}".encode()).hexdigest()
    return int(digest[:12], 16) / float(0xFFFFFFFFFFFF)


def assign_partitions(records: list[SplitRecord], policy: SplitPolicy) -> dict[str, str]:
    """Assign each record to one partition. Related records (same
    connected component) always land together (AT-0602-1)."""
    policy.validate()
    groups = build_groups([r for r in records if r.eligible])
    # component → member count (weight)
    sizes: dict[str, int] = {}
    for gid in groups.values():
        sizes[gid] = sizes.get(gid, 0) + 1

    order = sorted(sizes, key=lambda g: _group_rank(g, policy.seed))
    targets = {p: f * len(groups) for p, f in policy.fractions.items()}
    fill = dict.fromkeys(PARTITIONS, 0)
    assignment: dict[str, str] = {}

    # Greedy: each component goes to the most under-filled partition.
    for gid in order:
        best = min(
            PARTITIONS,
            key=lambda p: (fill[p] + sizes[gid]) / targets[p] if targets[p] else float("inf"),
        )
        for rid, g in groups.items():
            if g == gid:
                assignment[rid] = best
        fill[best] += sizes[gid]
    return assignment


# ------------------------------------------------------------------
# contamination check (AT-0602-2)


@dataclass(frozen=True)
class ContaminationReport:
    contaminated: bool
    findings: list[str]


def contamination_check(
    *,
    held_out_ids: set[str],
    held_out_labels: set[str],
    predictor_lineage_ids: set[str],
    context_texts: list[str],
) -> ContaminationReport:
    """A held-out record may not appear in predictor lineage, and a
    held-out label/id may not surface in any evaluation-context text."""
    findings: list[str] = []
    leaked_lineage = sorted(held_out_ids & predictor_lineage_ids)
    if leaked_lineage:
        findings.append(f"held-out records in predictor lineage: {leaked_lineage}")
    for i, text in enumerate(context_texts):
        for rid in sorted(held_out_ids):
            if rid and rid in text:
                findings.append(f"held-out id {rid} present in context text {i}")
        for label in sorted(held_out_labels):
            if label and label in text:
                findings.append(f"held-out label {label!r} in context text {i}")
    return ContaminationReport(bool(findings), findings)


def prepare_evaluation(
    *,
    records: list[SplitRecord],
    assignment: dict[str, str],
    predictor_lineage_ids: set[str],
    context_texts: list[str],
) -> dict[str, Any]:
    """Build the evaluation context manifest; raises
    ``EVAL_CONTAMINATION`` when the held-out partition leaks."""
    final_ids = {r for r, p in assignment.items() if p == "final"}
    final_labels = {
        f"{r.record_id}:{r.label}"
        for r in records
        if r.record_id in final_ids and r.label is not None
    }
    final_label_values = {
        str(r.label) for r in records if r.record_id in final_ids and r.label is not None
    }
    report = contamination_check(
        held_out_ids=final_ids,
        held_out_labels=final_label_values,
        predictor_lineage_ids=predictor_lineage_ids,
        context_texts=context_texts,
    )
    if report.contaminated:
        raise DomainError(
            ErrorCode.EVAL_CONTAMINATION,
            "held-out evaluation records leak into context or lineage",
            safe_details={"findings": report.findings},
        )
    return {
        "contextKind": "evaluation",
        "partitions": {p: 0 for p in PARTITIONS}
        | {p: sum(1 for v in assignment.values() if v == p) for p in PARTITIONS},
        "heldOutCount": len(final_ids),
        "heldOutIdsHash": hashlib.sha256(_canon_str(sorted(final_ids | final_labels))).hexdigest(),
        "predictorLineageHash": hashlib.sha256(
            _canon_str(sorted(predictor_lineage_ids))
        ).hexdigest(),
        "contamination": {"checked": True, "findings": []},
        "scientificStatus": "not_validated",
    }


def _canon_str(items: list[str]) -> bytes:
    return json.dumps(items, separators=(",", ":")).encode()


# ------------------------------------------------------------------
# partition-scoped transform fitting (AT-0602-3)


class SplitTransform(Protocol):
    """A preprocessing step. ``fit`` must only ever receive the
    allowed partitions' data — enforced by ``fit_transform``."""

    def fit(self, rows: list[dict[str, Any]]) -> None: ...

    def transform(self, row: dict[str, Any]) -> dict[str, Any]: ...


def fit_transform(
    records: list[SplitRecord],
    features: dict[str, dict[str, Any]],
    assignment: dict[str, str],
    transform: SplitTransform,
    allowed: tuple[str, ...] = ("train",),
) -> dict[str, dict[str, Any]]:
    """Fit ``transform`` on allowed partitions only, then transform all
    records. Returns record_id → transformed features.

    Test/final features never reach ``fit`` — fitting on them is the
    leakage this function exists to prevent (§18.2)."""
    unknown = set(allowed) - set(PARTITIONS)
    if unknown:
        raise DomainError(ErrorCode.VALIDATION, f"unknown fit partitions: {sorted(unknown)}")
    fit_rows = [
        features[r.record_id]
        for r in records
        if r.eligible and assignment.get(r.record_id) in allowed and r.record_id in features
    ]
    transform.fit(fit_rows)
    return {
        r.record_id: transform.transform(features[r.record_id])
        for r in records
        if r.eligible and r.record_id in features
    }


# ------------------------------------------------------------------
# denominator / uncertainty report (§18.2)


def denominator_report(
    *,
    expected: int,
    results: list[dict[str, Any]],
    partition_sizes: dict[str, int],
) -> dict[str, Any]:
    """Report denominators, missing/invalid results and small-sample
    uncertainty — never just an average (§18.2)."""
    valid = [r for r in results if r.get("valid", True) and r.get("value") is not None]
    n = len(valid)
    values = [float(r["value"]) for r in valid]
    mean = sum(values) / n if n else None
    return {
        "expected": expected,
        "reported": len(results),
        "valid": n,
        "missing": expected - len(results),
        "invalid": len(results) - n,
        "mean": mean,
        "uncertainty": {
            "smallSample": n < 30,
            "note": "n < 30: treat as low-confidence; no accuracy claim",
        }
        if n < 30
        else {"smallSample": False},
        "partitionSizes": partition_sizes,
    }
