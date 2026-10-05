"""Data-readiness gating (CS-0604, §15.3, §17.2, AT-0604-3).

A property predictor may only be trained when the coverage report
shows the request is meaningful — and "meaningful" is decided by
structure, not invented sample counts:

- at least one labeled, eligible example (``no_labeled_examples``);
- at least the caller-declared minimum, ``min_labeled_examples``
  (``below_declared_minimum`` — the caller owns the number);
- at least two distinct lineage groups, otherwise no held-out
  partition can exist (``insufficient_groups``);
- a non-empty held-out ``final`` partition after group-aware
  assignment (``no_held_out_partition``).

Any blocker yields capability ``not_ready`` plus the full
coverage/exclusion report — never a trained predictor on synthetic
confidence.
"""

from __future__ import annotations

import math
from typing import Any

from studio.domain.learning.splits import (
    SplitPolicy,
    SplitRecord,
    assign_partitions,
    build_groups,
)

NOT_READY = "not_ready"
READY = "ready"
FIXTURE_READY = "fixture_ready"


def assess_readiness(
    records: list[SplitRecord],
    *,
    min_labeled_examples: int = 1,
    exclusion_reasons: dict[str, int] | None = None,
    fixture_only: bool = False,
    seed: int = 0,
) -> dict[str, Any]:
    """Return the capability report; ``records`` are the snapshot's
    included rows with their real group keys and labels."""
    if min_labeled_examples < 1:
        raise ValueError("min_labeled_examples must be at least 1")
    labeled = [r for r in records if r.eligible and r.label is not None and math.isfinite(r.label)]
    blockers: list[str] = []
    if not labeled:
        blockers.append("no_labeled_examples")
    elif len(labeled) < min_labeled_examples:
        blockers.append("below_declared_minimum")
    groups = build_groups([r for r in records if r.eligible])
    distinct_groups = len(set(groups.values()))
    partition_sizes: dict[str, int] = {}
    if distinct_groups < 2:
        blockers.append("insufficient_groups")
    else:
        assignment = assign_partitions(records, SplitPolicy(seed=seed))
        for p in ("train", "development", "calibration", "final"):
            partition_sizes[p] = sum(1 for v in assignment.values() if v == p)
        if partition_sizes["final"] == 0:
            blockers.append("no_held_out_partition")
    status = NOT_READY if blockers else (FIXTURE_READY if fixture_only else READY)
    return {
        "capability": status,
        "scientificStatus": "fixture_only" if fixture_only else "not_validated",
        "coverage": {
            "eligible": sum(1 for r in records if r.eligible),
            "ineligible": sum(1 for r in records if not r.eligible),
            "labeled": len(labeled),
            "unlabeled": sum(
                1 for r in records if r.eligible and (r.label is None or not math.isfinite(r.label))
            ),
            "distinctGroups": distinct_groups,
            "partitionSizes": partition_sizes,
            "minLabeledDeclared": min_labeled_examples,
        },
        "exclusions": dict(exclusion_reasons or {}),
        "blockers": blockers,
    }
