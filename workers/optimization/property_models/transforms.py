"""Partition-scoped feature transforms (CS-0604, §15.3, §18.2).

Every transform implements the ``SplitTransform`` protocol from
``domain/learning/splits.py``: ``fit`` is only ever invoked on the
allowed partitions' rows (enforced by ``fit_transform``), while
``transform`` may run on any row. Imputation values, scaling
statistics and categorical vocabularies therefore come exclusively
from training data — held-out measurements can never leak into
feature engineering.

Missing values are never silently dropped: each transform reports
exactly what it imputed, what vocabulary it saw, and which features
were unusable, so the predictor manifest can publish an honest
missing-value policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

NUMERIC = "numeric"
CATEGORICAL = "categorical"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@dataclass
class FeatureSpec:
    """Declared input schema: which features exist and their kind."""

    name: str
    kind: str  # NUMERIC | CATEGORICAL
    required: bool = True


@dataclass
class RowFlags:
    """Per-row transform findings — the missing-value policy in
    action, per example."""

    imputed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    unknown_category: list[str] = field(default_factory=list)
    non_numeric: list[str] = field(default_factory=list)


class FeatureVectorizer:
    """Impute + scale numerics, one-hot encode categoricals.

    ``fit`` records medians/means/stds and category vocabularies.
    ``transform`` emits a fixed-width float vector plus ``RowFlags``.
    ``transform_vector`` is the vector-only variant used at predict
    time."""

    def __init__(self, features: list[FeatureSpec]) -> None:
        self.features = list(features)
        self._means: dict[str, float] = {}
        self._stds: dict[str, float] = {}
        self._vocab: dict[str, list[str]] = {}
        self._ranges: dict[str, tuple[float, float]] = {}
        self._unusable: list[str] = []
        self._fitted = False

    # ------------------------------------------------------------- fit
    def fit(self, rows: list[dict[str, Any]]) -> None:
        for f in self.features:
            if f.kind == NUMERIC:
                values = sorted(
                    float(r[f.name])
                    for r in rows
                    if _is_number(r.get(f.name)) and float(r[f.name]) == float(r[f.name])
                )
                if not values:
                    # Feature never observed in the allowed partition —
                    # declared unusable, impute 0 in scaled space and
                    # publish it as a limitation; never drop silently.
                    self._unusable.append(f.name)
                    self._means[f.name] = 0.0
                    self._stds[f.name] = 1.0
                    continue
                mean = sum(values) / len(values)
                var = sum((v - mean) ** 2 for v in values) / len(values)
                std = var**0.5
                self._means[f.name] = mean
                self._stds[f.name] = std if std > 0 else 1.0
                self._ranges[f.name] = (values[0], values[-1])
                if std <= 0:
                    self._unusable.append(f.name)
            elif f.kind == CATEGORICAL:
                vocab = sorted({str(r[f.name]) for r in rows if r.get(f.name) not in (None, "")})
                self._vocab[f.name] = vocab
                if not vocab:
                    self._unusable.append(f.name)
            else:
                raise ValueError(f"unsupported feature kind {f.kind!r}")
        self._fitted = True

    # -------------------------------------------------------- transform
    @property
    def unusable_features(self) -> list[str]:
        return list(self._unusable)

    def numeric_ranges(self) -> dict[str, tuple[float, float]]:
        """Observed train-partition envelope per numeric feature; the
        applicability assessor uses it — nothing else claims a domain."""
        return dict(self._ranges)

    def categorical_vocab(self) -> dict[str, list[str]]:
        return {k: list(v) for k, v in self._vocab.items()}

    def transform(self, row: dict[str, Any]) -> dict[str, Any]:
        vector, flags = self.transform_vector(row)
        return {**row, "_vector": vector, "_flags": flags}

    def transform_vector(self, row: dict[str, Any]) -> tuple[list[float], RowFlags]:
        if not self._fitted:
            raise ValueError("vectorizer not fitted")
        flags = RowFlags()
        out: list[float] = []
        for f in self.features:
            raw = row.get(f.name)
            if f.kind == NUMERIC:
                if raw is None or raw == "":
                    flags.missing.append(f.name)
                    if f.required:
                        flags.imputed.append(f.name)
                    out.append(0.0)  # train mean in scaled space
                elif _is_number(raw) and float(raw) == float(raw):
                    out.append((float(raw) - self._means[f.name]) / self._stds[f.name])
                else:
                    flags.non_numeric.append(f.name)
                    flags.imputed.append(f.name)
                    out.append(0.0)
            else:
                if raw is None or raw == "":
                    flags.missing.append(f.name)
                    out.extend([0.0] * len(self._vocab[f.name]))
                elif str(raw) in self._vocab[f.name]:
                    out.extend([1.0 if c == str(raw) else 0.0 for c in self._vocab[f.name]])
                else:
                    flags.unknown_category.append(f.name)
                    out.extend([0.0] * len(self._vocab[f.name]))
        return out, flags
