"""CS-0604 — property models, calibration and applicability (§15.3, §18.2).

AT-0604-1  held-out synthetic endpoint data → baseline/model
           comparison on the same examples and budget, explicit
           metrics (not a bare average)
AT-0604-2  out-of-domain input → applicability warning/denial, never
           invented confidence
"""

from __future__ import annotations

import json
from pathlib import Path

from workers.optimization.property_models import (
    FeatureSpec,
    PropertyPredictor,
    assess_readiness,
    evaluate_property_model,
)

from studio.domain.learning.splits import (
    SplitPolicy,
    SplitRecord,
    assign_partitions,
    build_groups,
)


def _fixture() -> dict:
    return json.loads(Path("fixtures/synthetic/property-endpoint.json").read_text())


def _records(fx: dict) -> list[SplitRecord]:
    return [
        SplitRecord(
            record_id=r["record_id"],
            group_keys=frozenset(r["group_keys"]),
            label=r["label"],
            eligible=r["eligible"],
        )
        for r in fx["records"]
    ]


def _features(fx: dict) -> dict[str, dict]:
    return {r["record_id"]: dict(r["features"]) for r in fx["records"]}


def _feature_spec(fx: dict) -> list[FeatureSpec]:
    return [
        FeatureSpec(name=f["name"], kind=f["kind"], required=f["required"]) for f in fx["features"]
    ]


def _setup(seed: int = 7):
    fx = _fixture()
    records = _records(fx)
    assignment = assign_partitions(records, SplitPolicy(seed=seed))
    return fx, records, assignment


class TestAT0604_1_MatchedComparison:
    """Same examples, same budget, explicit metrics."""

    def test_baseline_and_model_comparison(self) -> None:
        fx, records, assignment = _setup()
        report = evaluate_property_model(
            records=records,
            features=_features(fx),
            assignment=assignment,
            feature_spec=_feature_spec(fx),
            scope=fx["scope"],
        )
        # Every arm is scored on the identical held-out example set —
        # the budget declaration is explicit, not implied.
        assert report["budget"]["sameExamples"] is True
        assert report["budget"]["samePartitions"] is True
        final_ids = sorted(r for r, p in assignment.items() if p == report["evalPartition"])
        assert report["evaluatedExampleIds"] == final_ids
        for arm in ("ridge", "mean", "median"):
            m = report["models"][arm]
            assert m["mae"] is not None and m["evaluated"] > 0
            assert "smallSample" in m
        assert "rmse" in report["models"]["ridge"]
        # On a learnable synthetic signal the ridge model must do at
        # least as well as the matched mean baseline — the honest
        # comparison, not an invented accuracy bar.
        assert report["models"]["ridge"]["mae"] <= report["models"]["mean"]["mae"]
        # Denominators: held-out rows with no label are counted as
        # missing, never silently dropped.
        expected_missing = sum(
            1
            for r in records
            if assignment.get(r.record_id) == report["evalPartition"] and r.label is None
        )
        assert report["denominators"]["expected"] == len(final_ids)
        assert report["denominators"]["missing"] == expected_missing
        assert report["trainingCoverage"]["fitted"] > 0
        # Calibration fits on its own partition and reports honestly.
        cal = report["calibration"]
        assert cal["fittedOn"] == "calibration"
        assert cal["calibrationN"] > 0
        assert cal["halfWidth"] is not None and cal["halfWidth"] > 0
        assert report["manifest"]["scientificStatus"] == "not_validated"
        assert report["scientificStatus"] == "fixture_only"

    def test_related_records_never_cross_partitions(self) -> None:
        """Repeated readings / formula siblings stay together when the
        comparison is prepared — the §17.2 grouping guarantee."""
        _, records, assignment = _setup()
        groups = build_groups(records)
        seen: dict[str, str] = {}
        for rid, gid in groups.items():
            if rid not in assignment:  # ineligible rows get no partition
                continue
            part = assignment[rid]
            assert seen.setdefault(gid, part) == part


class TestAT0604_2_ApplicabilityDenial:
    """Out-of-domain input → warning/denial, not invented confidence."""

    def _predictor(self):
        fx, records, assignment = _setup()
        predictor = PropertyPredictor(scope=fx["scope"], features=_feature_spec(fx))
        predictor.fit(records, _features(fx), assignment)
        predictor.calibrate(records, _features(fx), assignment)
        return fx, predictor

    def test_out_of_domain_denial(self) -> None:
        fx, predictor = self._predictor()
        for row in fx["out_of_domain_rows"]:
            if row["expect"] != "out_of_domain":
                continue
            pred = predictor.predict(row["record_id"], row["features"])
            assert pred.applicability.status == "out_of_domain"
            assert pred.applicability.reasons  # explicit reasons, not silent
            # No calibrated interval is published for a denied row —
            # the value may be reviewed, not trusted.
            assert pred.interval is None

    def test_confidence_not_invented(self) -> None:
        _fx, predictor = self._predictor()
        unknown = predictor.predict(
            "x",
            {
                "solids_content": 50.0,
                "drying_temp": 80.0,
                "binder_family": "never-seen-polymer",
            },
        )
        assert unknown.applicability.status == "out_of_domain"
        assert any("unknown_category" in r for r in unknown.applicability.reasons)
        assert "out_of_domain" in predictor.manifest()["applicability"]["denialStates"]

    def test_manifest_publishes_scope_coverage_limitations(self) -> None:
        fx, predictor = self._predictor()
        manifest = predictor.manifest()
        assert manifest["scope"] == fx["scope"]
        assert manifest["trainingCoverage"]["fitPartitions"] == ["train"]
        assert manifest["calibration"]["fittedOn"] == "calibration"
        assert manifest["missingValuePolicy"]["categorical"]
        assert manifest["limitations"]


class TestReadiness:
    """Structural gates — no invented sample counts."""

    def test_insufficient_groups_not_ready(self) -> None:
        fx = _fixture()
        records = _records(fx)
        # Collapse every record into ONE lineage group: a held-out
        # partition can no longer exist.
        one_group = [
            SplitRecord(r.record_id, frozenset({"formula:only"}), r.label, r.eligible)
            for r in records
        ]
        report = assess_readiness(one_group)
        assert report["capability"] == "not_ready"
        assert "insufficient_groups" in report["blockers"]
        assert report["coverage"]["distinctGroups"] == 1

    def test_no_labels_not_ready(self) -> None:
        fx = _fixture()
        records = _records(fx)
        unlabeled = [SplitRecord(r.record_id, r.group_keys, None, r.eligible) for r in records]
        report = assess_readiness(unlabeled)
        assert report["capability"] == "not_ready"
        assert "no_labeled_examples" in report["blockers"]

    def test_ready_when_structure_allows(self) -> None:
        fx = _fixture()
        report = assess_readiness(_records(fx), fixture_only=True)
        assert report["capability"] == "fixture_ready"
        assert report["coverage"]["partitionSizes"]["final"] > 0
        assert report["blockers"] == []
