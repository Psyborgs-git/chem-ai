"""Pure-Python ridge regression (CS-0604, §15.3).

The core profile carries no numeric dependencies — this solver is a
deliberate, honest baseline model: normal equations with explicit L2
regularization, solved by Gauss-Jordan with partial pivoting. It is
appropriate for small structured endpoint datasets (tens-to-hundreds
of examples, tens of features) — exactly where a baseline must be
tried *before* a molecular neural model (implementation order 1→2).

``ridge_lambda`` is a declared method parameter, not a tuned
scientific threshold; it is recorded in the predictor manifest.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class RidgeRegressor:
    """Least-squares with L2 penalty λ‖w‖²; intercept unpenalized."""

    ridge_lambda: float = 0.01
    weights: list[float] = field(default_factory=list)
    intercept: float = 0.0
    n_features: int = 0

    def fit(self, vectors: list[list[float]], labels: list[float]) -> None:
        if self.ridge_lambda <= 0 or not math.isfinite(self.ridge_lambda):
            raise ValueError("ridge_lambda must be positive and finite")
        if not vectors or len(vectors) != len(labels):
            raise ValueError("training rows and labels must be non-empty and aligned")
        d = len(vectors[0])
        if d == 0 or any(len(v) != d for v in vectors):
            raise ValueError("ragged or empty feature vectors")
        # Center labels; the intercept is then the train mean — the
        # regression baseline and the MeanBaseline differ only by what
        # the features explain, which is the comparison §18.2 wants.
        y_mean = sum(labels) / len(labels)
        # Normal equations A w = b with A = XᵀX + λI, b = Xᵀ(y-ȳ).
        a = [[0.0] * d for _ in range(d)]
        b = [0.0] * d
        for x, y in zip(vectors, labels, strict=True):
            residual = y - y_mean
            for i in range(d):
                xi = x[i]
                b[i] += xi * residual
                row = a[i]
                for j in range(d):
                    row[j] += xi * x[j]
        for i in range(d):
            a[i][i] += self.ridge_lambda
        self.weights = _solve(a, b)
        self.intercept = y_mean
        self.n_features = d

    def predict(self, vector: list[float]) -> float:
        if not self.weights:
            raise ValueError("regressor not fitted")
        if len(vector) != self.n_features:
            raise ValueError("feature vector width differs from fitted model")
        return self.intercept + sum(w * x for w, x in zip(self.weights, vector, strict=True))


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gauss-Jordan with partial pivoting. λ>0 makes A positive
    definite, so a zero pivot means the input was degenerate — fail
    loudly rather than emit a silent pseudo-solution."""
    n = len(a)
    aug = [[*row[:], b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-15:
            raise ValueError("degenerate design matrix; model not fitted")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        inv = 1.0 / aug[col][col]
        aug[col] = [v * inv for v in aug[col]]
        for r in range(n):
            if r != col and aug[r][col] != 0.0:
                factor = aug[r][col]
                aug[r] = [v - factor * pv for v, pv in zip(aug[r], aug[col], strict=True)]
    return [aug[i][n] for i in range(n)]
