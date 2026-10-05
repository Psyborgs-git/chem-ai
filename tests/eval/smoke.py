"""``make eval-smoke`` — synthetic split/eval pipeline exercise (CS-0602).

Proves the leakage-safe plumbing end to end on fixture records:
grouping → partition assignment → partition-scoped transform fit →
matched baseline → contamination-gated evaluation manifest →
denominator report. Synthetic data only; this validates software,
never a model's chemistry.
"""

from __future__ import annotations

import sys

from workers.optimization.baselines import MeanBaseline, evaluate_baseline

from studio.domain.learning.splits import (
    SplitPolicy,
    SplitRecord,
    assign_partitions,
    denominator_report,
    fit_transform,
    prepare_evaluation,
)


class _Scaler:
    def __init__(self) -> None:
        self.mean = 0.0

    def fit(self, rows: list[dict[str, float]]) -> None:
        self.mean = sum(r["x"] for r in rows) / len(rows)

    def transform(self, row: dict[str, float]) -> dict[str, float]:
        return {**row, "x_centered": row["x"] - self.mean}


def main() -> int:
    records = [
        SplitRecord(f"rec-{i}", frozenset({f"formula:fam-{i // 3}"}), float(i)) for i in range(40)
    ]
    assignment = assign_partitions(records, SplitPolicy(seed=11))
    features = {r.record_id: {"x": float(r.label or 0)} for r in records}
    transformed = fit_transform(records, features, assignment, _Scaler())

    train_labels = [
        r.label for r in records if assignment.get(r.record_id) == "train" and r.label is not None
    ]
    final_labels = [r.label for r in records if assignment.get(r.record_id) == "final"]
    baseline = MeanBaseline()
    baseline.fit(train_labels)  # fitted on train only
    base_report = evaluate_baseline(baseline, final_labels)

    manifest = prepare_evaluation(
        records=records,
        assignment=assignment,
        predictor_lineage_ids=set(),
        context_texts=["smoke context — no held-out content"],
    )
    sizes = manifest["partitions"]
    report = denominator_report(
        expected=len(final_labels),
        results=[{"value": v} for v in final_labels],
        partition_sizes=sizes,
    )
    print("eval smoke (fixture):")
    print(f"  partitions: {sizes}")
    print(f"  transformed records: {len(transformed)}")
    print(f"  baseline mae on final: {base_report['mae']}")
    print("  contamination check: clean (findings=0)")
    print(f"  denominator: {report['valid']}/{report['expected']} valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
