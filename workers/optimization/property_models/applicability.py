"""Applicability-domain assessment (CS-0604, §15.3, AT-0604-2).

An assessor fitted ONLY on the allowed training partition. It answers
one narrow question per row — "is this input inside what the model
has evidence for?" — with three honest states:

- ``in_domain``: inside every observed envelope and at typical
  training density.
- ``sparse``: inside the envelope but far from every training example
  in scaled feature space. The threshold is *data-derived* — the
  largest nearest-neighbour gap the training set itself contains —
  so the model is compared against its own coverage, never an
  invented scientific cutoff.
- ``out_of_domain``: outside an observed envelope (numeric range or
  categorical vocabulary) or carrying unfeaturizable values. This is
  a denial of applicability, not a confident prediction — callers
  must not present the value as validated ranking (§15.3).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .transforms import CATEGORICAL, NUMERIC, FeatureSpec, RowFlags


@dataclass
class ApplicabilityVerdict:
    status: str  # "in_domain" | "sparse" | "out_of_domain"
    reasons: list[str] = field(default_factory=list)


class ApplicabilityAssessor:
    def __init__(self) -> None:
        self._ranges: dict[str, tuple[float, float]] = {}
        self._vocab: dict[str, set[str]] = {}
        self._train_vectors: list[list[float]] = []
        self._nn_threshold: float | None = None
        self._fitted = False

    def fit(
        self,
        features: list[FeatureSpec],
        raw_rows: list[dict[str, Any]],
        vectors: list[list[float]],
    ) -> None:
        for f in features:
            if f.kind == NUMERIC:
                vals = [
                    float(r[f.name])
                    for r in raw_rows
                    if isinstance(r.get(f.name), (int, float))
                    and not isinstance(r.get(f.name), bool)
                    and math.isfinite(float(r[f.name]))
                ]
                if vals:
                    self._ranges[f.name] = (min(vals), max(vals))
            elif f.kind == CATEGORICAL:
                self._vocab[f.name] = {
                    str(r[f.name]) for r in raw_rows if r.get(f.name) not in (None, "")
                }
        self._train_vectors = [list(v) for v in vectors]
        if len(self._train_vectors) >= 2:
            gaps = []
            for i, v in enumerate(self._train_vectors):
                best = min(_distance(v, w) for j, w in enumerate(self._train_vectors) if j != i)
                gaps.append(best)
            self._nn_threshold = max(gaps)
        else:
            # A single training example defines no density region at
            # all: every other point is out of domain by coverage.
            self._nn_threshold = 0.0
        self._fitted = True

    @property
    def nn_threshold(self) -> float | None:
        return self._nn_threshold

    @property
    def train_rows(self) -> int:
        return len(self._train_vectors)

    def assess(
        self, row: dict[str, Any], vector: list[float], flags: RowFlags
    ) -> ApplicabilityVerdict:
        if not self._fitted:
            raise ValueError("assessor not fitted")
        reasons: list[str] = []
        for name in flags.unknown_category:
            reasons.append(f"unknown_category:{name}")
        for name in flags.non_numeric:
            reasons.append(f"non_numeric:{name}")
        for name, (lo, hi) in self._ranges.items():
            raw = row.get(name)
            if (
                isinstance(raw, (int, float))
                and not isinstance(raw, bool)
                and math.isfinite(float(raw))
            ):
                v = float(raw)
                if v < lo:
                    reasons.append(f"below_train_range:{name}")
                elif v > hi:
                    reasons.append(f"above_train_range:{name}")
        if reasons:
            return ApplicabilityVerdict("out_of_domain", sorted(set(reasons)))
        if self._train_vectors:
            dist = min(_distance(vector, w) for w in self._train_vectors)
            if self._nn_threshold is not None and dist > self._nn_threshold:
                return ApplicabilityVerdict(
                    "sparse",
                    [
                        f"sparse_region:distance {dist:.6g} exceeds max train gap "
                        f"{self._nn_threshold:.6g}"
                    ],
                )
        return ApplicabilityVerdict("in_domain", [])


def _distance(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)))
