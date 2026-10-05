"""Split-conformal calibration (CS-0604, §18.2).

Calibration is fitted ONLY on the calibration partition — never on
held-out evaluation data and never on the full dataset (§15.3). The
method is standard split conformal with absolute residuals: for a
declared coverage level ``c`` the interval half-width is the
``ceil((n+1)·c)/n`` empirical quantile of held-out residuals.

The report states coverage as *declared* (the finite-sample
guarantee holds under exchangeability of calibration and evaluation
data — an assumption the manifest names), plus what was actually
measured on the evaluation partition. No unconditional certainty is
claimed for out-of-domain chemistry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class SplitConformalCalibrator:
    coverage: float = 0.9
    half_width: float | None = None
    calibration_n: int = 0

    def fit(self, residuals: list[float]) -> None:
        if not 0 < self.coverage < 1 or not math.isfinite(self.coverage):
            raise ValueError("coverage must be a finite fraction in (0, 1)")
        clean = sorted(abs(r) for r in residuals if math.isfinite(r))
        self.calibration_n = len(clean)
        if not clean:
            self.half_width = None
            return
        k = min(len(clean) - 1, max(0, math.ceil((len(clean) + 1) * self.coverage) - 1))
        self.half_width = clean[k]

    @property
    def calibrated(self) -> bool:
        return self.half_width is not None

    def interval(self, value: float) -> tuple[float, float] | None:
        if self.half_width is None:
            return None
        return (value - self.half_width, value + self.half_width)

    def report(self) -> dict[str, object]:
        return {
            "method": "split-conformal-absolute-residual",
            "coverageDeclared": self.coverage,
            "calibrationN": self.calibration_n,
            "halfWidth": self.half_width,
            "fittedOn": "calibration",
            "assumption": (
                "marginal coverage under exchangeability of the calibration and "
                "evaluation partitions; not a guarantee for out-of-domain inputs"
            ),
            "calibrated": self.calibrated,
        }
