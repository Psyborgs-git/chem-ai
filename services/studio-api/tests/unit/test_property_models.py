"""CS-0604 unit tests — transforms, ridge, applicability, calibration.

Fixture-only software tests; no scientific performance claim."""

from __future__ import annotations

import pytest
from workers.optimization.property_models import (
    FeatureSpec,
    PropertyPredictor,
    RidgeRegressor,
    SplitConformalCalibrator,
    assess_readiness,
)
from workers.optimization.property_models.applicability import ApplicabilityAssessor
from workers.optimization.property_models.transforms import (
    CATEGORICAL,
    NUMERIC,
    FeatureVectorizer,
)

from studio.domain.learning.splits import SplitRecord


def test_vectorizer_fit_transform_policy() -> None:
    spec = [
        FeatureSpec("a", NUMERIC),
        FeatureSpec("b", CATEGORICAL),
    ]
    vec = FeatureVectorizer(spec)
    vec.fit(
        [
            {"a": 1.0, "b": "x"},
            {"a": 3.0, "b": "y"},
            {"a": None, "b": "x"},
        ]
    )
    out, flags = vec.transform_vector({"a": 5.0, "b": "x"})
    assert len(out) == 1 + 2  # one numeric + 2-category one-hot
    assert flags.missing == [] and flags.unknown_category == []
    out, flags = vec.transform_vector({"a": None, "b": "zzz"})
    assert flags.missing == ["a"] and flags.unknown_category == ["b"]
    assert out == [0.0, 0.0, 0.0]
    # Unseen category produces no invented indicator column.
    assert sum(out) == 0.0


def test_vectorizer_declares_unusable_features() -> None:
    vec = FeatureVectorizer([FeatureSpec("flat", NUMERIC), FeatureSpec("c", CATEGORICAL)])
    vec.fit([{"flat": 2.0, "c": "x"}, {"flat": 2.0, "c": "y"}])
    # Constant feature is declared unusable, not silently kept.
    assert vec.unusable_features == ["flat"]
    assert vec.numeric_ranges()["flat"] == (2.0, 2.0)


def test_ridge_recovers_linear_signal() -> None:
    vectors = [[x, 0.0] for x in range(-5, 6)] + [[0.0, y] for y in range(-5, 6)]
    labels = [2.0 * v[0] + 3.0 * v[1] + 1.0 for v in vectors]
    reg = RidgeRegressor(0.01)
    reg.fit(vectors, labels)
    assert abs(reg.predict([1.0, 0.0]) - 3.0) < 0.2
    assert abs(reg.predict([0.0, 1.0]) - 4.0) < 0.2
    with pytest.raises(ValueError, match="not fitted"):
        RidgeRegressor(0.01).predict([1.0])
    with pytest.raises(ValueError):
        RidgeRegressor(0.0).fit(vectors, labels)


def test_applicability_denies_out_of_domain() -> None:
    spec = [FeatureSpec("x", NUMERIC), FeatureSpec("cat", CATEGORICAL)]
    raw = [{"x": v, "cat": "a"} for v in (1.0, 2.0, 3.0)]
    vectors = [[0.0, 1.0], [0.5, 1.0], [1.0, 1.0]]
    assessor = ApplicabilityAssessor()
    assessor.fit(spec, raw, vectors)
    from workers.optimization.property_models.transforms import RowFlags

    verdict = assessor.assess({"x": 99.0, "cat": "a"}, [0.0, 1.0], RowFlags())
    assert verdict.status == "out_of_domain"
    assert any("above_train_range" in r for r in verdict.reasons)
    flags = RowFlags(unknown_category=["cat"])
    verdict = assessor.assess({"x": 2.0, "cat": "nope"}, [0.0, 0.0], flags)
    assert verdict.status == "out_of_domain"
    in_dom = assessor.assess({"x": 2.0, "cat": "a"}, [0.5, 1.0], RowFlags())
    assert in_dom.status in ("in_domain", "sparse")


def test_conformal_calibrator_quantile_and_empty() -> None:
    cal = SplitConformalCalibrator(0.9)
    cal.fit([1.0, 2.0, 0.5, 3.0, 0.2])
    assert cal.calibrated
    lo, hi = cal.interval(10.0)  # type: ignore[misc]
    assert hi - lo == 2 * cal.half_width
    empty = SplitConformalCalibrator(0.9)
    empty.fit([])
    assert not empty.calibrated
    assert empty.interval(1.0) is None
    assert empty.report()["calibrated"] is False
    with pytest.raises(ValueError):
        SplitConformalCalibrator(1.5).fit([1.0])


def test_predictor_requires_labeled_examples() -> None:
    predictor = PropertyPredictor(
        scope={"target": "t", "method": "m", "unit": "u"},
        features=[FeatureSpec("x", NUMERIC)],
    )
    records = [SplitRecord("a", frozenset({"g1"}), None)]
    with pytest.raises(ValueError, match="not_ready"):
        predictor.fit(records, {"a": {"x": 1.0}}, {"a": "train"})


def test_readiness_respects_declared_minimum() -> None:
    records = [SplitRecord(f"r{i}", frozenset({f"g{i}"}), float(i)) for i in range(20)]
    ready = assess_readiness(records, min_labeled_examples=20)
    assert ready["capability"] == "ready"
    not_ready = assess_readiness(records, min_labeled_examples=21)
    assert not_ready["capability"] == "not_ready"
    assert "below_declared_minimum" in not_ready["blockers"]


def test_readiness_flags_empty_held_out() -> None:
    # Eight distinct groups cannot fill a mandatory final partition
    # under the default fractions — the gate says not_ready, honestly.
    records = [SplitRecord(f"r{i}", frozenset({f"g{i}"}), float(i)) for i in range(8)]
    report = assess_readiness(records)
    assert report["capability"] == "not_ready"
    assert "no_held_out_partition" in report["blockers"]


def test_predictor_no_interval_for_out_of_domain() -> None:
    predictor = PropertyPredictor(
        scope={"target": "t", "method": "m", "unit": "u"},
        features=[FeatureSpec("x", NUMERIC)],
    )
    records = [
        SplitRecord(f"t{i}", frozenset({"g"} if i < 6 else {f"g{i}"}), float(i)) for i in range(10)
    ]
    features = {f"t{i}": {"x": float(i)} for i in range(10)}
    assignment = {f"t{i}": ("train" if i < 6 else "calibration") for i in range(10)}
    predictor.fit(records, features, assignment)
    predictor.calibrate(records, features, assignment)
    in_dom = predictor.predict("q", {"x": 3.0})
    assert in_dom.applicability.status in ("in_domain", "sparse")
    ood = predictor.predict("q2", {"x": 500.0})
    assert ood.applicability.status == "out_of_domain"
    assert ood.interval is None
