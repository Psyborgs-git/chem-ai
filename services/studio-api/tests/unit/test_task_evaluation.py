"""CS-0503 — pure per-metric evaluator semantics (§12.3).

AT-0503-1  one required metric unmeasured → overall stays inconclusive.
"""

from __future__ import annotations

from studio.domain.tasks.evaluation import assess_metric


def _metric(**over):
    m = {
        "id": "metric.synthetic-performance",
        "label": "Synthetic test-only index",
        "required": True,
        "operator": "gte",
        "target_values": ["5"],
        "unit": "dimensionless",
        "required_evidence": ["lab_measurement"],
        "aggregation": "fixture-single-value",
    }
    m.update(over)
    return m


def _row(value: str, unit: str = "dimensionless", vtype: str = "numeric", batch: str = "b1"):
    return {
        "id": f"m-{value}-{vtype}",
        "value_type": vtype,
        "value": {"kind": vtype, "value": value, "unit": unit},
        "batch_id": batch,
    }


class TestAssessMetric:
    def test_unmeasured_required_metric_is_inconclusive(self) -> None:
        """AT-0503-1: an unmeasured required metric never resolves —
        inconclusive, with an actionable missing finding."""
        r = assess_metric(_metric(), [])
        assert r["verdict"] == "inconclusive"
        assert r["findings"][0]["kind"] == "missing"
        assert r["findings"][0]["action"] == "record_or_accept_measurement"

    def test_meeting_numeric_evidence_is_met(self) -> None:
        r = assess_metric(_metric(), [_row("6"), _row("7")])
        assert r["verdict"] == "met"
        assert r["independentBatches"] == 1

    def test_failing_numeric_evidence_is_misses(self) -> None:
        r = assess_metric(_metric(), [_row("4"), _row("3")])
        assert r["verdict"] == "misses"

    def test_censored_evidence_never_forces_a_verdict(self) -> None:
        """Below-detection values cannot establish a bound (§6.3)."""
        r = assess_metric(_metric(), [_row("3", vtype="below_detection")])
        assert r["verdict"] == "inconclusive"
        assert r["findings"][0]["kind"] == "censored_unsupported"

    def test_incompatible_units_are_inconclusive(self) -> None:
        r = assess_metric(_metric(unit="mPa·s"), [_row("12.5", unit="g")])
        assert r["verdict"] == "inconclusive"
        assert r["findings"][0]["kind"] == "unit_incompatible"

    def test_whitelisted_conversion_compares(self) -> None:
        """0.15 Pa·s == 150 mPa·s — same-category conversion counts."""
        r = assess_metric(_metric(target_values=["100"], unit="mPa·s"), [_row("0.15", unit="Pa·s")])
        assert r["verdict"] == "met"

    def test_same_aliquot_repeats_do_not_satisfy_replication(self) -> None:
        """Three readings on one batch stay one independent trial (§14.4)."""
        metric = _metric(replication_rule={"minIndependentBatches": 2})
        rows = [_row("6"), _row("7"), _row("8")]  # all batch b1
        r = assess_metric(metric, rows)
        assert r["verdict"] == "inconclusive"
        assert r["findings"][0]["kind"] == "insufficient_replication"

    def test_two_independent_batches_satisfy_replication(self) -> None:
        metric = _metric(replication_rule={"minIndependentBatches": 2})
        rows = [_row("6", batch="b1"), _row("7", batch="b2")]
        r = assess_metric(metric, rows)
        assert r["verdict"] == "met"
        assert r["independentBatches"] == 2

    def test_unknown_aggregation_is_inconclusive(self) -> None:
        r = assess_metric(_metric(aggregation="geometric-mean"), [_row("9")])
        assert r["verdict"] == "inconclusive"
        assert r["findings"][0]["kind"] == "unknown"

    def test_nonmeasurement_evidence_class_unmet(self) -> None:
        r = assess_metric(
            _metric(required_evidence=["lab_measurement", "replication"]),
            [_row("9")],
        )
        assert r["verdict"] == "inconclusive"
        assert r["findings"][0]["kind"] == "evidence_class_missing"
