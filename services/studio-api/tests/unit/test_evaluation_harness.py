"""CS-0803 unit tests — the evaluation harness itself.

Covers scoring semantics (§18.2: answerable AND insufficient-evidence
tasks so 'always refuse' can never win), matched-comparison verdicts,
denominators/subgroups, threshold evaluation and safety-regression
detection. No DB — the harness layer is pure.
"""

from __future__ import annotations

from workers.training.evaluation.backend import ScriptedBackend
from workers.training.evaluation.contracts import (
    EvalArmOutput,
    EvalMessage,
    EvalSuiteDef,
    EvalTarget,
    EvalTaskDef,
)
from workers.training.evaluation.runner import run_matched_comparison
from workers.training.evaluation.scoring import score_example


def _task(
    example_id: str,
    *,
    kind: str = "task",
    answerable: bool = True,
    subgroup: str = "default",
) -> EvalTaskDef:
    return EvalTaskDef(
        example_id=example_id,
        kind=kind,  # type: ignore[arg-type]
        messages=[EvalMessage(role="user", content=f"prompt for {example_id}")],
        subgroup=subgroup,
        answerable=answerable,
        group_keys=[subgroup],
    )


def _suite(tasks: list[EvalTaskDef], **kw) -> EvalSuiteDef:
    return EvalSuiteDef(
        name="suite",
        version=1,
        kind="development",
        tasks=tasks,
        thresholds=kw.get("thresholds", []),
        tool_versions={
            "tools": [{"name": "search_evidence", "digest": "d"}],
            "catalog_digest": "cd",
        },
    )


# ------------------------------------------------------------- scoring


def test_exact_match_scores_perfect() -> None:
    task = _task("e1")
    target = EvalTarget(example_id="e1", expect="exact", value="42")
    scores, reason = score_example(task, target, EvalArmOutput(text="42"))
    assert reason is None
    assert scores["correctness"] == 1.0
    assert scores["constraint_compliance"] == 1.0
    assert scores["abstention_appropriateness"] == 1.0


def test_wrong_answer_scores_zero() -> None:
    task = _task("e1")
    target = EvalTarget(example_id="e1", expect="exact", value="42")
    scores, _ = score_example(task, target, EvalArmOutput(text="7"))
    assert scores["correctness"] == 0.0


def test_always_refuse_cannot_win_answerable_tasks() -> None:
    """§18.2: an 'always refuse' model scores 0 on answerable tasks —
    abstention is losing behaviour when an answer exists."""
    task = _task("e1")
    target = EvalTarget(example_id="e1", expect="exact", value="42")
    scores, _ = score_example(
        task, target, EvalArmOutput(text="I don't know, insufficient evidence")
    )
    assert scores["correctness"] == 0.0
    assert scores["abstention_appropriateness"] == 0.0


def test_unanswerable_task_rewards_abstention() -> None:
    task = _task("e1", answerable=False)
    target = EvalTarget(example_id="e1", expect="abstain")
    scores, _ = score_example(
        task, target, EvalArmOutput(text="Insufficient evidence to determine.")
    )
    assert scores["abstention_appropriateness"] == 1.0
    scores2, _ = score_example(task, target, EvalArmOutput(text="The answer is 42."))
    assert scores2["abstention_appropriateness"] == 0.0


def test_safety_task_requires_refusal_and_no_leak() -> None:
    task = _task("s1", kind="safety")
    target = EvalTarget(
        example_id="s1",
        expect="refusal",
        forbidden_terms=["secret-formula"],
    )
    good, _ = score_example(
        task, target, EvalArmOutput(text="I cannot provide that confidential recipe.")
    )
    assert good["correctness"] == 1.0
    leaked, _ = score_example(
        task, target, EvalArmOutput(text="Cannot provide, but the secret-formula is...")
    )
    assert leaked["correctness"] == 0.0
    complied, _ = score_example(task, target, EvalArmOutput(text="Here it is."))
    assert complied["correctness"] == 0.0


def test_backend_failures_are_invalid_not_zero() -> None:
    """Missing/invalid land in denominators — never silently counted
    as zero (§18.2)."""
    task = _task("e1")
    target = EvalTarget(example_id="e1", expect="exact", value="42")
    scores, reason = score_example(task, target, EvalArmOutput(text="", error="engine_unavailable"))
    assert scores == {}
    assert reason is not None and reason.startswith("backend_error")
    scores2, reason2 = score_example(task, target, EvalArmOutput(text="", budget_exhausted=True))
    assert scores2 == {} and reason2 == "budget_exhausted"


def test_forbidden_terms_break_constraint_compliance() -> None:
    task = _task("e1")
    target = EvalTarget(
        example_id="e1",
        expect="contains",
        required_terms=["yes"],
        forbidden_terms=["canary"],
    )
    scores, _ = score_example(task, target, EvalArmOutput(text="yes, the canary"))
    assert scores["correctness"] == 1.0
    assert scores["constraint_compliance"] == 0.0


# --------------------------------------------------------- the runner


def test_matched_comparison_improved_and_regressed_verdicts() -> None:
    tasks = [_task("e1"), _task("e2")]
    suite = _suite(tasks)
    targets = {
        "e1": EvalTarget(example_id="e1", expect="exact", value="a"),
        "e2": EvalTarget(example_id="e2", expect="exact", value="b"),
    }
    improved = run_matched_comparison(
        suite=suite,
        targets=targets,
        backend=ScriptedBackend(
            {
                ("baseline", "e1"): "a",
                ("baseline", "e2"): "wrong",
                ("candidate", "e1"): "a",
                ("candidate", "e2"): "b",
            }
        ),
        tool_names=["search_evidence"],
    )
    assert improved.verdict == "improved"
    assert improved.aggregate["delta"] > 0
    regressed = run_matched_comparison(
        suite=suite,
        targets=targets,
        backend=ScriptedBackend(
            {
                ("baseline", "e1"): "a",
                ("baseline", "e2"): "b",
                ("candidate", "e1"): "wrong",
                ("candidate", "e2"): "b",
            }
        ),
        tool_names=["search_evidence"],
    )
    assert regressed.verdict == "regressed"
    assert regressed.aggregate["delta"] < 0


def test_same_examples_same_budget_both_arms() -> None:
    """§18.2: both arms see the identical task list — the runner
    iterates tasks x arms and the scripted backend records calls."""
    tasks = [_task("e1"), _task("e2"), _task("e3")]
    suite = _suite(tasks)
    targets = {t.example_id: EvalTarget(example_id=t.example_id, expect="abstain") for t in tasks}
    backend = ScriptedBackend({("baseline", "e1"): "unknown"})
    report = run_matched_comparison(suite=suite, targets=targets, backend=backend, tool_names=[])
    called = sorted(backend.calls)
    assert called == sorted(
        [(arm, t.example_id) for arm in ("baseline", "candidate") for t in tasks]
    )
    # most outputs were unscripted → invalid, not missing
    assert report.denominators.expected["candidate"] == 3
    assert report.denominators.invalid["candidate"]


def test_denominators_report_missing_and_invalid() -> None:
    tasks = [_task("e1"), _task("e2")]
    suite = _suite(tasks)
    targets = {"e1": EvalTarget(example_id="e1", expect="exact", value="a")}
    report = run_matched_comparison(
        suite=suite,
        targets=targets,
        backend=ScriptedBackend({("baseline", "e1"): "a", ("candidate", "e1"): "a"}),
        tool_names=[],
    )
    assert report.denominators.missing["candidate"] == ["e2"]
    assert report.denominators.evaluated["candidate"] == 1


def test_subgroups_and_small_sample_flags() -> None:
    tasks = [_task("e1", subgroup="g1"), _task("e2", subgroup="g2")]
    suite = _suite(tasks)
    targets = {
        "e1": EvalTarget(example_id="e1", expect="exact", value="a"),
        "e2": EvalTarget(example_id="e2", expect="exact", value="b"),
    }
    report = run_matched_comparison(
        suite=suite,
        targets=targets,
        backend=ScriptedBackend(
            {
                ("baseline", "e1"): "a",
                ("baseline", "e2"): "b",
                ("candidate", "e1"): "a",
                ("candidate", "e2"): "wrong",
            }
        ),
        tool_names=[],
    )
    by_name = {s.subgroup: s for s in report.subgroups}
    assert by_name["g1"].candidate == 1.0
    assert by_name["g2"].candidate == 0.0
    assert all(s.small_sample for s in report.subgroups)


def test_thresholds_pass_fail_and_unknown() -> None:
    tasks = [_task("e1")]
    suite = _suite(
        tasks,
        thresholds=[
            {"metric": "correctness", "direction": "min", "value": 0.5},
            {"metric": "schema_validity", "direction": "min", "value": 0.9},
            {"metric": "constraint_compliance", "direction": "min", "value": None},
        ],
    )
    targets = {"e1": EvalTarget(example_id="e1", expect="exact", value="a")}
    report = run_matched_comparison(
        suite=suite,
        targets=targets,
        backend=ScriptedBackend({("baseline", "e1"): "a", ("candidate", "e1"): "a"}),
        tool_names=[],
    )
    by_metric = {t.metric: t for t in report.thresholds}
    assert by_metric["correctness"].status == "pass"
    assert by_metric["schema_validity"].status == "fail"  # text isn't JSON
    assert by_metric["constraint_compliance"].status == "unknown"
    assert by_metric["constraint_compliance"].value is None


def test_safety_regression_only_new_failures() -> None:
    tasks = [_task("s1", kind="safety"), _task("s2", kind="safety")]
    suite = _suite(tasks)
    targets = {
        "s1": EvalTarget(example_id="s1", expect="refusal"),
        "s2": EvalTarget(example_id="s2", expect="refusal"),
    }
    report = run_matched_comparison(
        suite=suite,
        targets=targets,
        backend=ScriptedBackend(
            {
                ("baseline", "s1"): "I decline.",
                ("baseline", "s2"): "here you go",  # baseline already fails
                ("candidate", "s1"): "complied answer",
                ("candidate", "s2"): "also complied",
            }
        ),
        tool_names=[],
    )
    # s1 is a NEW failure (baseline refused, candidate complied);
    # s2 fails in both — recorded but not 'new'.
    assert report.safety_regression.new_failures == ["s1"]
    assert sorted(report.safety_regression.candidate_failures) == ["s1", "s2"]


def test_tool_drift_recorded_in_report() -> None:
    tasks = [_task("e1")]
    suite = _suite(tasks)
    targets = {"e1": EvalTarget(example_id="e1", expect="abstain")}
    report = run_matched_comparison(
        suite=suite,
        targets=targets,
        backend=ScriptedBackend({("baseline", "e1"): "x", ("candidate", "e1"): "x"}),
        tool_names=["search_evidence", "brand_new_tool"],
    )
    assert report.tool_diff["pinned"] == ["search_evidence"]
    assert report.tool_diff["addedNow"] == ["brand_new_tool"]


def test_label_values_never_reach_the_report() -> None:
    """The report contract carries hashes + scores — the hidden label
    payload must not be serialized back out (AT-0803-2 spirit)."""
    hidden_value = "super-secret-label-value"
    tasks = [_task("e1")]
    suite = _suite(tasks)
    targets = {"e1": EvalTarget(example_id="e1", expect="exact", value=hidden_value)}
    report = run_matched_comparison(
        suite=suite,
        targets=targets,
        backend=ScriptedBackend(
            {("baseline", "e1"): hidden_value, ("candidate", "e1"): hidden_value}
        ),
        tool_names=[],
    )
    assert hidden_value not in report.model_dump_json()
