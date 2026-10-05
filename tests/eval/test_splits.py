"""CS-0602 — leakage-safe splits and baseline evaluation (§17.2, §18).

AT-0602-1  related formula variants + repeated readings → related
           examples never cross prohibited partitions
AT-0602-2  held-out label in summary / predictor lineage →
           contamination check blocks evaluation prep
AT-0602-3  scalers/calibration fit on allowed partitions only
"""

from __future__ import annotations

from typing import Any

import pytest
from workers.optimization.baselines import MeanBaseline, evaluate_baseline

from studio.domain.learning.splits import (
    SplitPolicy,
    SplitRecord,
    assign_partitions,
    build_groups,
    contamination_check,
    denominator_report,
    fit_transform,
    prepare_evaluation,
)
from studio.errors import DomainError, ErrorCode


def _records() -> list[SplitRecord]:
    # Two formula variants of one family + two readings of one sample,
    # plus unrelated records.
    return [
        SplitRecord("m1", frozenset({"formula:fam-a", "sample:s1"}), 1.0),
        SplitRecord("m2", frozenset({"formula:fam-a"}), 2.0),  # sibling formula
        SplitRecord("m3", frozenset({"sample:s1"}), 1.1),  # repeated reading
        SplitRecord("m4", frozenset({"formula:fam-b"}), 9.0),
        SplitRecord("m5", frozenset({"doc:doc-x"}), 3.0),
        SplitRecord("m6", frozenset({"doc:doc-x"}), 3.1),  # derived document
        *[SplitRecord(f"u{i}", frozenset(), float(i)) for i in range(7, 30)],
    ]


class TestGroupingAndPartitions:
    """AT-0602-1."""

    def test_related_records_share_group(self) -> None:
        groups = build_groups(_records())
        assert groups["m1"] == groups["m2"] == groups["m3"]
        assert groups["m5"] == groups["m6"]
        assert groups["m1"] != groups["m4"]

    def test_related_never_cross_partitions(self) -> None:
        records = _records()
        assignment = assign_partitions(records, SplitPolicy(seed=7))
        groups = build_groups(records)
        by_group: dict[str, set[str]] = {}
        for rid, gid in groups.items():
            by_group.setdefault(gid, set()).add(assignment[rid])
        for gid, parts in by_group.items():
            assert len(parts) == 1, f"group {gid} crossed partitions {parts}"
        assert "final" in set(assignment.values())

    def test_deterministic_for_seed(self) -> None:
        records = _records()
        a = assign_partitions(records, SplitPolicy(seed=7))
        b = assign_partitions(records, SplitPolicy(seed=7))
        assert a == b

    def test_final_partition_mandatory(self) -> None:
        with pytest.raises(DomainError):
            assign_partitions(_records(), SplitPolicy(fractions={"train": 1.0, "final": 0.0}))


class TestContamination:
    """AT-0602-2."""

    def _setup(self) -> tuple[list[SplitRecord], dict[str, str]]:
        records = _records()
        assignment = assign_partitions(records, SplitPolicy(seed=7))
        return records, assignment

    def test_lineage_leak_blocks(self) -> None:
        records, assignment = self._setup()
        held_out = {r for r, p in assignment.items() if p == "final"}
        leaked = set(held_out)
        with pytest.raises(DomainError) as ei:
            prepare_evaluation(
                records=records,
                assignment=assignment,
                predictor_lineage_ids=leaked,  # model trained on held-out ids
                context_texts=[],
            )
        assert ei.value.code == ErrorCode.EVAL_CONTAMINATION

    def test_label_leak_in_summary_blocks(self) -> None:
        records, assignment = self._setup()
        held_out = {r for r, p in assignment.items() if p == "final"}
        leaked_label = next(str(r.label) for r in records if r.record_id in held_out and r.label)
        with pytest.raises(DomainError) as ei:
            prepare_evaluation(
                records=records,
                assignment=assignment,
                predictor_lineage_ids=set(),
                context_texts=[f"summary mentions label {leaked_label} openly"],
            )
        assert ei.value.code == ErrorCode.EVAL_CONTAMINATION

    def test_clean_passes_with_manifest(self) -> None:
        records, assignment = self._setup()
        manifest = prepare_evaluation(
            records=records,
            assignment=assignment,
            predictor_lineage_ids=set(),
            context_texts=["no leakage here"],
        )
        assert manifest["contamination"] == {"checked": True, "findings": []}
        assert manifest["heldOutCount"] > 0
        assert manifest["scientificStatus"] == "not_validated"

    def test_contamination_report_function(self) -> None:
        rep = contamination_check(
            held_out_ids={"h1"},
            held_out_labels={"9.0"},
            predictor_lineage_ids={"h1"},
            context_texts=["value 9.0 leaked"],
        )
        assert rep.contaminated
        assert len(rep.findings) == 2


class Recorder:
    """Transform that records every row it was fit on."""

    def __init__(self) -> None:
        self.fit_ids: list[str] = []
        self.mean = 0.0

    def fit(self, rows: list[dict[str, Any]]) -> None:
        self.fit_ids = [str(r["id"]) for r in rows]
        self.mean = sum(float(r["x"]) for r in rows) / max(len(rows), 1)

    def transform(self, row: dict[str, Any]) -> dict[str, Any]:
        return {**row, "x_centered": float(row["x"]) - self.mean}


class TestPartitionOnlyFitting:
    """AT-0602-3."""

    def test_fit_sees_only_allowed_partitions(self) -> None:
        records = _records()
        assignment = assign_partitions(records, SplitPolicy(seed=3))
        features = {r.record_id: {"id": r.record_id, "x": float(i)} for i, r in enumerate(records)}
        scaler = Recorder()
        out = fit_transform(records, features, assignment, scaler, allowed=("train",))
        train_ids = {r for r, p in assignment.items() if p == "train"}
        assert set(scaler.fit_ids) <= train_ids
        assert not (set(scaler.fit_ids) & {r for r, p in assignment.items() if p == "final"})
        # transform still covers every eligible record
        assert set(out) == {r.record_id for r in records}

    def test_baseline_matches_partition(self) -> None:
        records = _records()
        assignment = assign_partitions(records, SplitPolicy(seed=3))
        train_labels = [
            r.label for r in records if assignment.get(r.record_id) == "train" and r.label
        ]
        final_labels = [r.label for r in records if assignment.get(r.record_id) == "final"]
        base = MeanBaseline()
        base.fit(train_labels)
        report = evaluate_baseline(base, final_labels)
        assert report["evaluated"] == len([x for x in final_labels if x is not None])
        assert report["missing"] == 0
        assert report["mae"] is not None

    def test_denominator_report_honest(self) -> None:
        rep = denominator_report(
            expected=4,
            results=[{"value": 1.0}, {"value": None}, {"valid": False}],
            partition_sizes={"train": 20, "final": 3},
        )
        assert rep["valid"] == 1
        assert rep["missing"] == 1
        assert rep["invalid"] == 2
        assert rep["uncertainty"]["smallSample"] is True
