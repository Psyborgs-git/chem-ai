"""Matched baseline/model comparison (CS-0604, §18.2, AT-0604-1).

One runner trains the candidate model and every baseline on the SAME
allowed partition, calibrates on the SAME calibration partition, and
scores all of them on the SAME held-out examples with the SAME
feature budget. That is what "comparison" means here — identical
examples and budget, explicit metrics and denominators, never a
single average and never different data slices per arm.
"""

from __future__ import annotations

import math
from typing import Any

from workers.optimization.baselines import MeanBaseline, MedianBaseline, evaluate_baseline

from studio.domain.learning.splits import SplitRecord, denominator_report

from .predictor import PropertyPredictor
from .transforms import FeatureSpec


def _metric_summary(pairs: list[tuple[float, float]]) -> dict[str, Any]:
    errors = [abs(p - y) for p, y in pairs]
    sq = [e * e for e in errors]
    n = len(errors)
    return {
        "evaluated": n,
        "mae": sum(errors) / n if n else None,
        "rmse": math.sqrt(sum(sq) / n) if n else None,
        "smallSample": n < 30,
    }


def evaluate_property_model(
    *,
    records: list[SplitRecord],
    features: dict[str, dict[str, Any]],
    assignment: dict[str, str],
    feature_spec: list[FeatureSpec],
    scope: dict[str, str],
    eval_partition: str = "final",
    coverage: float = 0.9,
    ridge_lambda: float = 0.01,
    scientific_status: str = "fixture_only",
) -> dict[str, Any]:
    """Fit the ridge model + mean/median baselines on the same train
    partition and score them on the same held-out examples.

    Returns the full report: per-arm metrics on identical example
    sets, conformal calibration outcome, applicability findings, and
    the honest denominator (missing/invalid counted, not dropped)."""
    predictor = PropertyPredictor(
        scope=scope, features=feature_spec, ridge_lambda=ridge_lambda, coverage=coverage
    )
    coverage_counts = predictor.fit(records, features, assignment)
    predictor.calibrate(records, features, assignment)

    train_labels = [
        float(r.label)
        for r in records
        if r.eligible and assignment.get(r.record_id) == "train" and r.label is not None
    ]
    eval_rows = [r for r in records if r.eligible and assignment.get(r.record_id) == eval_partition]
    eval_labels = [r.label for r in eval_rows]
    eval_ids = [r.record_id for r in eval_rows]

    baselines: dict[str, Any] = {}
    for name, baseline in (("mean", MeanBaseline()), ("median", MedianBaseline())):
        baseline.fit(train_labels)
        baselines[name] = evaluate_baseline(baseline, eval_labels)

    labeled = [
        (r, float(r.label)) for r in eval_rows if r.label is not None and r.record_id in features
    ]
    predictions = [predictor.predict(r.record_id, features[r.record_id]) for r, _ in labeled]
    model_pairs = [(p.value, y) for p, (_, y) in zip(predictions, labeled, strict=True)]
    applicability_counts = {"in_domain": 0, "sparse": 0, "out_of_domain": 0}
    in_domain_pairs: list[tuple[float, float]] = []
    covered = 0
    for p, (_, y) in zip(predictions, labeled, strict=True):
        applicability_counts[p.applicability.status] += 1
        if p.applicability.status == "in_domain":
            in_domain_pairs.append((p.value, y))
            if p.interval is not None and p.interval[0] <= y <= p.interval[1]:
                covered += 1
    in_domain_n = len(in_domain_pairs)
    calibration_report = predictor.calibrator.report() | {
        "empiricalCoverage": (covered / in_domain_n) if in_domain_n else None,
        "empiricalN": in_domain_n,
    }
    report = {
        "evalPartition": eval_partition,
        "evaluatedExampleIds": sorted(eval_ids),
        "models": {
            "ridge": _metric_summary(model_pairs),
            "ridge_in_domain": _metric_summary(in_domain_pairs),
            **baselines,
        },
        "budget": {
            "sameExamples": True,
            "samePartitions": True,
            "features": [f.name for f in feature_spec],
            "ridgeLambda": ridge_lambda,
            "coverageDeclared": coverage,
        },
        "trainingCoverage": coverage_counts,
        "calibration": calibration_report,
        "applicability": applicability_counts,
        "denominators": denominator_report(
            expected=len(eval_rows),
            # Held-out rows with no label or no features are simply
            # missing — they never produced a result, so they count
            # under ``missing``, not ``invalid``.
            results=[
                {"value": p.value, "valid": p.applicability.status != "out_of_domain"}
                for p in predictions
            ],
            partition_sizes={
                p: sum(1 for v in assignment.values() if v == p)
                for p in ("train", "development", "calibration", "final")
            },
        ),
        "manifest": predictor.manifest(),
        "scientificStatus": scientific_status,
    }
    return report
