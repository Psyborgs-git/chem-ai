"""Matched baselines for property evaluation (CS-0602, §18.2).

Baselines are deliberately simple and fitted on the same permitted
partitions as the model under test — a matched comparator, not a
strawman. A sophisticated model only earns its label by beating these
on the same held-out examples.

- ``MeanBaseline`` — predicts the train-partition mean.
- ``MedianBaseline`` — robust variant for skewed fixture data.

Both expose ``fit``/``predict``; ``evaluate_baseline`` returns a
denominator-aware report (n, missing, invalid, MAE, small-sample
uncertainty) rather than a single number.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MeanBaseline:
    """Predict the mean of the partition it was fit on."""

    _mean: float | None = field(default=None, init=False)

    def fit(self, labels: list[float]) -> None:
        if not labels:
            raise ValueError("baseline requires at least one label")
        self._mean = sum(labels) / len(labels)

    def predict(self, n: int) -> list[float]:
        if self._mean is None:
            raise ValueError("baseline not fitted")
        return [self._mean] * n


@dataclass
class MedianBaseline:
    _median: float | None = field(default=None, init=False)

    def fit(self, labels: list[float]) -> None:
        if not labels:
            raise ValueError("baseline requires at least one label")
        s = sorted(labels)
        mid = len(s) // 2
        self._median = s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2

    def predict(self, n: int) -> list[float]:
        if self._median is None:
            raise ValueError("baseline not fitted")
        return [self._median] * n


def evaluate_baseline(
    baseline: MeanBaseline | MedianBaseline,
    labels: list[float | None],
) -> dict[str, float | int | bool | None]:
    """Score a fitted baseline on held-out labels with an honest
    denominator: missing labels are counted, not dropped silently."""
    present = [(i, v) for i, v in enumerate(labels) if v is not None]
    preds = baseline.predict(len(present)) if present else []
    errors = [abs(p - v) for (_, v), p in zip(present, preds, strict=True)]
    n = len(errors)
    return {
        "evaluated": n,
        "missing": len(labels) - n,
        "mae": (sum(errors) / n) if n else None,
        "smallSample": n < 30,
    }
