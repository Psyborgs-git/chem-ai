"""Property predictor composition (CS-0604, §15.3).

A predictor = declared scope + partition-fitted transforms + a simple
regression + split-conformal calibration + an applicability assessor.
Everything it publishes comes from what actually ran:

- **target/method scope** — the declared endpoint it predicts;
- **training coverage** — how many allowed-partition examples it fit
  and how many it excluded (with reasons, never fabricated counts);
- **missing-value policy** — per-kind treatment applied per row;
- **calibration report** — conformal interval basis and assumptions;
- **applicability assessment** — per-row in/sparse/out-of-domain;
- **limitations** — honest statements a reviewer must see.

Predictions on ``out_of_domain`` rows are still emitted (exploratory
review is allowed, §15.3) but carry the denial and never a
calibrated-confidence claim.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from studio.domain.learning.splits import SplitRecord, fit_transform

from .applicability import ApplicabilityAssessor, ApplicabilityVerdict
from .calibration import SplitConformalCalibrator
from .linear import RidgeRegressor
from .transforms import FeatureSpec, FeatureVectorizer

FIT_PARTITIONS = ("train",)
CALIBRATION_PARTITION = "calibration"


@dataclass
class RowPrediction:
    row_id: str
    value: float
    interval: tuple[float, float] | None
    applicability: ApplicabilityVerdict
    imputed: list[str] = field(default_factory=list)

    def public(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "rowId": self.row_id,
            "value": self.value,
            "applicability": {
                "status": self.applicability.status,
                "reasons": self.applicability.reasons,
            },
        }
        if self.interval is not None:
            out["interval"] = {"lower": self.interval[0], "upper": self.interval[1]}
        if self.imputed:
            out["imputed"] = self.imputed
        return out


class PropertyPredictor:
    """Ridge regression on declared numeric/categorical features."""

    kind = "ridge-regression/structured-features"
    representation = "tabular-numeric-categorical"

    def __init__(
        self,
        *,
        scope: dict[str, str],
        features: list[FeatureSpec],
        ridge_lambda: float = 0.01,
        coverage: float = 0.9,
    ) -> None:
        self.scope = dict(scope)
        self.vectorizer = FeatureVectorizer(features)
        self.assessor = ApplicabilityAssessor()
        self.calibrator = SplitConformalCalibrator(coverage)
        self.model = RidgeRegressor(ridge_lambda)
        self._features = list(features)
        self._train_n = 0
        self._excluded: dict[str, int] = {}
        self._feature_names = [f.name for f in features]
        self._fitted = False

    # ------------------------------------------------------------------
    def _rows(
        self,
        records: list[SplitRecord],
        features: dict[str, dict[str, Any]],
        assignment: dict[str, str],
        partition: str,
    ) -> list[tuple[SplitRecord, dict[str, Any]]]:
        return [
            (r, features[r.record_id])
            for r in records
            if r.eligible and assignment.get(r.record_id) == partition and r.record_id in features
        ]

    def fit(
        self,
        records: list[SplitRecord],
        features: dict[str, dict[str, Any]],
        assignment: dict[str, str],
    ) -> dict[str, int]:
        """Fit transforms + model on the allowed partitions ONLY.

        ``fit_transform`` guarantees the vectorizer's ``fit`` never
        sees development/calibration/final rows — that is the leakage
        boundary, not a convention."""
        transformed = fit_transform(
            records, features, assignment, self.vectorizer, allowed=FIT_PARTITIONS
        )
        train_rows = self._rows(records, features, assignment, "train")
        vectors: list[list[float]] = []
        labels: list[float] = []
        raw_rows: list[dict[str, Any]] = []
        self._excluded = {
            "missing_label": 0,
            "ineligible": sum(1 for r in records if not r.eligible),
        }
        for rec, raw in train_rows:
            if rec.label is None or not math.isfinite(rec.label):
                self._excluded["missing_label"] += 1
                continue
            vec = transformed[rec.record_id]["_vector"]
            vectors.append(vec)
            labels.append(float(rec.label))
            raw_rows.append(raw)
        if not vectors:
            raise ValueError(
                "no labeled training examples in the allowed partition; "
                "capability is not_ready, not a trained predictor"
            )
        self.model.fit(vectors, labels)
        self.assessor.fit(self._features, raw_rows, vectors)
        self._train_n = len(vectors)
        self._fitted = True
        return {"fitted": self._train_n, **self._excluded}

    def calibrate(
        self,
        records: list[SplitRecord],
        features: dict[str, dict[str, Any]],
        assignment: dict[str, str],
    ) -> int:
        if not self._fitted:
            raise ValueError("predictor not fitted")
        residuals = []
        for rec, raw in self._rows(records, features, assignment, CALIBRATION_PARTITION):
            if rec.label is None or not math.isfinite(rec.label):
                continue
            vec, _ = self.vectorizer.transform_vector(raw)
            residuals.append(float(rec.label) - self.model.predict(vec))
        self.calibrator.fit(residuals)
        return self.calibrator.calibration_n

    def predict(self, row_id: str, raw: dict[str, Any]) -> RowPrediction:
        if not self._fitted:
            raise ValueError("predictor not fitted")
        vec, flags = self.vectorizer.transform_vector(raw)
        value = self.model.predict(vec)
        verdict = self.assessor.assess(raw, vec, flags)
        interval = self.calibrator.interval(value)
        if verdict.status == "out_of_domain":
            # §15.3: an exploratory value may be shown, but it is NOT a
            # calibrated prediction — no interval is published for it.
            interval = None
        return RowPrediction(
            row_id=row_id,
            value=value,
            interval=interval,
            applicability=verdict,
            imputed=flags.imputed,
        )

    def manifest(self) -> dict[str, Any]:
        """The published predictor card (§15.3) — everything stated
        here was computed; nothing is asserted beyond it."""
        if not self._fitted:
            raise ValueError("predictor not fitted")
        limitations = [
            "predictions are point estimates from a ridge regression on "
            "declared features; they are not evidence of causation or "
            "of endpoint suitability",
            "out_of_domain and sparse inputs carry an explicit warning; "
            "their values are exploratory, not validated candidate ranking",
        ]
        if self.vectorizer.unusable_features:
            limitations.append(
                "features with no usable training signal: "
                + ", ".join(self.vectorizer.unusable_features)
            )
        if not self.calibrator.calibrated:
            limitations.append(
                "uncalibrated: no calibration-partition residuals — no interval is published"
            )
        return {
            "kind": self.kind,
            "representation": self.representation,
            "scope": dict(self.scope),
            "trainingCoverage": {
                "trainN": self._train_n,
                "calibrationN": self.calibrator.calibration_n,
                "excluded": dict(self._excluded),
                "fitPartitions": list(FIT_PARTITIONS),
            },
            "missingValuePolicy": {
                "numeric": "train-partition mean (0 scaled); imputed features listed per row",
                "categorical": "all-zero indicator; unknown categories flag out_of_domain",
                "neverObserved": self.vectorizer.unusable_features,
            },
            "calibration": self.calibrator.report(),
            "applicability": {
                "method": "train-envelope + train-density",
                "envelopeBasis": "allowed training partition only",
                "nnThreshold": self.assessor.nn_threshold,
                "trainRows": self.assessor.train_rows,
                "denialStates": ["out_of_domain"],
                "warningStates": ["sparse"],
            },
            "methodParameters": {
                "ridgeLambda": self.model.ridge_lambda,
                "coverageDeclared": self.calibrator.coverage,
            },
            "limitations": limitations,
            "scientificStatus": "not_validated",
        }
