"""Matched base-vs-adapted comparison runner (CS-0803, §18.2).

Both arms see the SAME task list, the SAME pinned tool set and the
SAME frozen budget — the only thing that differs is which model the
backend executes. Hidden targets are supplied by the caller (the
service layer reads them under the evaluation service principal);
this module never sees persistence and never emits label values.
"""

from __future__ import annotations

from typing import Any

from .backend import EvaluationBackend
from .contracts import (
    SCORING_METRICS,
    EvalComparisonReport,
    EvalDenominators,
    EvalExampleResult,
    EvalMetricSummary,
    EvalSafetyRegression,
    EvalSubgroupSummary,
    EvalSuiteDef,
    EvalTarget,
    EvalThresholdEval,
)
from .scoring import aggregate_metrics, aggregate_subgroups, mean, score_example

ARMS = ("baseline", "candidate")

_EPSILON = 1e-9


def _allowed_tools(suite: EvalSuiteDef) -> list[str]:
    return [t["name"] for t in suite.tool_versions.tools if "name" in t]


def _safety_pass(result: dict[str, Any]) -> bool:
    scores = result.get("scores") or {}
    return scores.get("correctness") == 1.0


def run_matched_comparison(
    *,
    suite: EvalSuiteDef,
    targets: dict[str, EvalTarget],
    backend: EvaluationBackend,
    tool_names: list[str] | None = None,
) -> EvalComparisonReport:
    """Run both arms over the suite and produce the §18.2 report.

    ``targets`` are the hidden labels, already read under service
    authority. ``tool_names`` is the live catalog snapshot used to
    detect drift from the suite's frozen pins.
    """
    allowed = _allowed_tools(suite)
    pinned = set(allowed)
    live = set(tool_names or [])
    tool_diff = {
        "pinned": sorted(pinned),
        "missingNow": sorted(pinned - live),
        "addedNow": sorted(live - pinned) if tool_names is not None else [],
    }

    capability = backend.capability()
    results: list[dict[str, Any]] = []
    invalid: dict[str, list[str]] = {arm: [] for arm in ARMS}
    missing: dict[str, list[str]] = {arm: [] for arm in ARMS}

    for task in suite.tasks:
        target = targets.get(task.example_id)
        for arm in ARMS:
            if target is None:
                missing[arm].append(task.example_id)
                continue
            output = backend.run_example(
                arm=arm,
                task=task,
                allowed_tools=allowed,
                budget=suite.budget,
            )
            scores, reason = score_example(task, target, output)
            if reason is not None:
                invalid[arm].append(task.example_id)
            results.append(
                {
                    "example_id": task.example_id,
                    "arm": arm,
                    "kind": task.kind,
                    "subgroup": task.subgroup,
                    "answerable": task.answerable,
                    "invalid_reason": reason,
                    "scores": scores,
                }
            )

    scored = [r for r in results if r["invalid_reason"] is None]
    metric_names = [m for m in SCORING_METRICS]
    metrics_raw = aggregate_metrics(scored, metric_names)
    metrics = [EvalMetricSummary(metric=name, **values) for name, values in metrics_raw.items()]

    agg_base = mean([m.baseline for m in metrics if m.baseline is not None] or [])
    agg_cand = mean([m.candidate for m in metrics if m.candidate is not None] or [])
    aggregate = {"baseline": agg_base, "candidate": agg_cand}
    if agg_cand is None or agg_base is None:
        aggregate["delta"] = None
    else:
        aggregate["delta"] = agg_cand - agg_base

    safety = EvalSafetyRegression()
    task_kinds = {t.example_id: t.kind for t in suite.tasks}
    for r in scored:
        if task_kinds.get(r["example_id"]) not in ("safety", "privacy"):
            continue
        if r["arm"] == "candidate" and not _safety_pass(r):
            safety.candidate_failures.append(r["example_id"])
    for r in scored:
        if task_kinds.get(r["example_id"]) not in ("safety", "privacy"):
            continue
        if r["arm"] != "candidate" or _safety_pass(r):
            continue
        base = next(
            (o for o in scored if o["example_id"] == r["example_id"] and o["arm"] == "baseline"),
            None,
        )
        if base is not None and _safety_pass(base):
            safety.new_failures.append(r["example_id"])

    denominators = EvalDenominators(
        expected={arm: len(suite.tasks) for arm in ARMS},
        evaluated={arm: sum(1 for r in scored if r["arm"] == arm) for arm in ARMS},
        missing=missing,
        invalid=invalid,
        small_sample=len(suite.tasks) < 30,
    )

    subgroups = [
        EvalSubgroupSummary(
            subgroup=name,
            evaluated=v["evaluated"],
            baseline=v["baseline"],
            candidate=v["candidate"],
            small_sample=v["smallSample"],
        )
        for name, v in aggregate_subgroups(scored).items()
    ]

    thresholds: list[EvalThresholdEval] = []
    for th in suite.thresholds:
        observed = metrics_raw.get(th.metric, {}).get("candidate")
        if th.value is None:
            status = "unknown"
        elif observed is None:
            status = "fail"
        else:
            ok = observed >= th.value if th.direction == "min" else observed <= th.value
            status = "pass" if ok else "fail"
        thresholds.append(
            EvalThresholdEval(
                metric=th.metric,
                direction=th.direction,
                value=th.value,
                observed=observed,
                status=status,
            )
        )

    delta = aggregate["delta"]
    if delta is None:
        verdict = "incomplete"
    elif delta > _EPSILON:
        verdict = "improved"
    elif delta < -_EPSILON:
        verdict = "regressed"
    else:
        verdict = "flat"

    return EvalComparisonReport(
        suite_digest="",
        suite_kind=suite.kind,
        backend=capability or {"available": False},
        tool_diff=tool_diff,
        results=[EvalExampleResult(**r) for r in results],
        metrics=metrics,
        aggregate=aggregate,
        denominators=denominators,
        subgroups=subgroups,
        thresholds=thresholds,
        safety_regression=safety,
        verdict=verdict,
    )
