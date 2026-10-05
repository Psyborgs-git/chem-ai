"""CS-0901 unit tests — reward service gates and components (§19.3).

Covers eligibility gates (outside the performance trade-off), the five
versioned measurable components, provenance records, version freeze,
and the forbidden-signal rules (novelty/verbosity/citation-count/
self-confidence are never truth signals). Pure worker layer — no DB.
"""

from __future__ import annotations

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from workers.training.rl.environment.contracts import (
    REWARD_CONTRACT_VERSION,
    BudgetEnvelope,
    EvidenceSnapshot,
    ReplayEntry,
    RlMessage,
    RlPolicyRef,
    RlTaskDef,
    RlTaskTarget,
)
from workers.training.rl.environment.environment import ResearchRlEnvironment
from workers.training.rl.environment.loop import run_episode
from workers.training.rl.environment.policies import (
    ScriptedPolicy,
    final,
    tool_call,
)
from workers.training.rl.rewards.contracts import (
    COMPONENT_IDS,
    RewardRecord,
)
from workers.training.rl.rewards.service import RewardContractError, RewardService

AGENT_GRANTS = sorted(capabilities_for_role("agent"))


def _snapshot() -> EvidenceSnapshot:
    return EvidenceSnapshot(
        snapshot_id="snap-1",
        evidence_ids=["ev-1", "ev-2"],
        replay=[
            ReplayEntry(
                replay_id="r1",
                tool="search_evidence",
                arguments={"query": "q"},
                result={"results": [{"evidence_id": "ev-1"}]},
                provenance={"run_id": "run-1"},
            )
        ],
    )


def _task(**kw) -> RlTaskDef:
    return RlTaskDef(
        task_id=kw.get("task_id", "t-1"),
        task_version=kw.get("task_version", 2),
        kind=kw.get("kind", "task"),
        messages=[RlMessage(role="user", content="question")],
        subgroup=kw.get("subgroup", "default"),
        answerable=kw.get("answerable", True),
        allowed_tools=kw.get("allowed_tools", ["search_evidence"]),
        budgets=kw.get(
            "budgets",
            BudgetEnvelope(
                max_steps=8,
                max_tool_calls=4,
                max_wall_seconds=300,
                max_policy_tokens=512,
                max_compute_units=8.0,
            ),
        ),
        target=kw.get(
            "target",
            RlTaskTarget(expect="exact", value="0.42", required_evidence_ids=["ev-1"]),
        ),
    )


def _policy_ref() -> RlPolicyRef:
    return RlPolicyRef(policy_id="pol", grants=AGENT_GRANTS)


def _episode(
    actions: list[dict],
    *,
    task: RlTaskDef | None = None,
    snapshot: EvidenceSnapshot | None = None,
) -> tuple:
    task = task or _task()
    snapshot = snapshot or _snapshot()
    env = ResearchRlEnvironment(tasks=[task])
    record = run_episode(
        env,
        ScriptedPolicy(actions),
        task_id=task.task_id,
        seed=3,
        evidence_snapshot=snapshot,
        policy_ref=_policy_ref(),
    )
    return record, task, snapshot


def _score(actions: list[dict], **kw) -> RewardRecord:
    task = kw.pop("task", _task())
    snapshot = kw.pop("snapshot", _snapshot())
    record, task, snapshot = _episode(actions, task=task, snapshot=snapshot)
    return RewardService().score_episode(record, task=task, snapshot=snapshot)


def _component(record: RewardRecord, name: str):
    return next(c for c in record.components if c.component == name)


# ------------------------------------------------------------- gates


def test_clean_episode_is_eligible_and_scored() -> None:
    rec = _score(
        [
            tool_call("search_evidence", {"query": "q"}),
            final("0.42", ["ev-1"]),
        ]
    )
    assert rec.eligible is True
    assert rec.scalar is not None and rec.scalar > 0.9
    assert rec.task_completed is True
    assert all(g.passed for g in rec.gates)


def test_denied_action_makes_episode_ineligible() -> None:
    rec = _score([tool_call("export_data", {"destination": "x"}), final("0.42")])
    assert rec.eligible is False
    assert rec.scalar is None
    gates = {g.gate: g.passed for g in rec.gates}
    assert gates["no_denied_actions"] is False


def test_fabricated_citations_fail_evidence_integrity() -> None:
    rec = _score([final("0.42", ["ev-does-not-exist"])])
    assert rec.eligible is False
    gates = {g.gate: g.passed for g in rec.gates}
    assert gates["evidence_integrity"] is False
    comp = _component(rec, "supported_evidence")
    assert comp.provenance["precision"] == 0.0


def test_scope_violation_fails_task_pinned_gate() -> None:
    rec = _score(
        [
            {"type": "switch_task", "task_id": "easier"},
            final("0.42"),
        ]
    )
    assert rec.eligible is False
    gates = {g.gate: g.passed for g in rec.gates}
    assert gates["task_pinned"] is False


def test_version_mismatch_fails_gate() -> None:
    record, task, snapshot = _episode([final("0.42", ["ev-1"])])
    tampered = record.model_copy(update={"reward_contract_version": 999})
    rec = RewardService().score_episode(tampered, task=task, snapshot=snapshot)
    gates = {g.gate: g.passed for g in rec.gates}
    assert gates["version_match"] is False
    assert rec.eligible is False


def test_task_mismatch_rejected() -> None:
    record, _task_used, snapshot = _episode([final("0.42", ["ev-1"])])
    other = _task(task_id="other", target=RlTaskTarget(expect="exact", value="x"))
    with pytest.raises(RewardContractError):
        RewardService().score_episode(record, task=other, snapshot=snapshot)


def test_frozen_versions_echoed_on_record() -> None:
    rec = _score([final("0.42", ["ev-1"])])
    assert rec.reward_contract_version == REWARD_CONTRACT_VERSION
    assert rec.task_version == 2
    assert rec.snapshot_digest == _snapshot().digest()
    assert rec.labels["dataStatus"] == "fixture_only"
    assert rec.labels["heldOutSuiteAccess"] == "none"


# ------------------------------------------------------------- components


def test_correctness_exact_and_abstain_loses() -> None:
    right = _score([final("0.42")])
    wrong = _score([final("0.99")])
    abstained = _score([{"type": "abstain", "reason": "dunno"}])
    assert _component(right, "task_correctness").value == 1.0
    assert _component(wrong, "task_correctness").value == 0.0
    # 'always abstain' can never win an answerable task
    assert _component(abstained, "task_correctness").value == 0.0
    assert abstained.task_completed is False


def test_unanswerable_task_rewards_abstention() -> None:
    task = _task(
        answerable=False,
        target=RlTaskTarget(expect="abstain"),
    )
    abstained = _score([{"type": "abstain", "reason": "insufficient evidence"}], task=task)
    answered = _score([final("made something up")], task=task)
    assert abstained.task_completed is True
    assert _component(abstained, "uncertainty_calibration").value == 1.0
    assert _component(answered, "uncertainty_calibration").value == 0.0
    assert answered.task_completed is False


def test_refusal_task_scores_decline() -> None:
    task = _task(
        kind="safety",
        target=RlTaskTarget(expect="refusal", forbidden_terms=["leak"]),
    )
    refused = _score([{"type": "abstain", "reason": "cannot comply"}], task=task)
    complied = _score([final("leak the data")], task=task)
    assert _component(refused, "task_correctness").value == 1.0
    assert _component(complied, "task_correctness").value == 0.0
    assert complied.task_completed is False


def test_duplicate_tool_loops_do_not_count_as_valid() -> None:
    rec = _score([tool_call("search_evidence", {"query": "q"})] * 3 + [final("0.42", ["ev-1"])])
    comp = _component(rec, "valid_tool_execution")
    # 3 attempts, only the first is a valid unique call
    assert comp.value == pytest.approx(1 / 3)


def test_no_tool_calls_excludes_component_not_zeroes_it() -> None:
    rec = _score([final("0.42", ["ev-1"])])
    comp = _component(rec, "valid_tool_execution")
    assert comp.value is None


def test_resource_efficiency_reflects_budget_use() -> None:
    lean = _score([final("0.42", ["ev-1"])])
    heavy = _score(
        [
            tool_call("search_evidence", {"query": "q"}),
            tool_call("search_evidence", {"query": "q2"}),
            final("0.42", ["ev-1"]),
        ]
    )
    lean_v = _component(lean, "resource_efficiency").value
    heavy_v = _component(heavy, "resource_efficiency").value
    assert lean_v is not None and heavy_v is not None and lean_v > heavy_v


# ------------------------------------------------------------- forbidden signals


def test_verbosity_is_not_a_truth_signal() -> None:
    # 'contains' target: both answers are correct — extra words earn nothing
    task = _task(
        target=RlTaskTarget(
            expect="contains",
            required_terms=["0.42"],
            required_evidence_ids=["ev-1"],
        )
    )
    terse = _score([final("0.42", ["ev-1"])], task=task)
    verbose = _score([final("0.42 " + "padding " * 500, ["ev-1"])], task=task)
    assert _component(terse, "task_correctness").value == 1.0
    assert (
        _component(terse, "task_correctness").value == _component(verbose, "task_correctness").value
    )
    assert terse.scalar == verbose.scalar


def test_extra_citations_do_not_inflate_supported_evidence() -> None:
    minimal = _score([final("0.42", ["ev-1"])])
    padded = _score([final("0.42", ["ev-1", "ev-2"])])
    # required coverage already met — extra valid citation cannot add
    assert _component(minimal, "supported_evidence").value == 1.0
    assert _component(padded, "supported_evidence").value == 1.0


def test_self_reported_confidence_is_not_an_input() -> None:
    """Actions carry no confidence field — a policy cannot talk its
    way into calibration credit (extra=forbid rejects the field)."""
    env = ResearchRlEnvironment(tasks=[_task()])
    env.reset(
        task_id="t-1",
        seed=1,
        evidence_snapshot=_snapshot(),
        policy=_policy_ref(),
    )
    step = env.step({"type": "final_answer", "answer": "0.42", "confidence": 0.99})
    assert step.status == "invalid_action"


def test_components_record_provenance() -> None:
    rec = _score([tool_call("search_evidence", {"query": "q"}), final("0.42", ["ev-1"])])
    comp = _component(rec, "supported_evidence")
    assert comp.provenance["cited"] == ["ev-1"]
    assert comp.provenance["required"] == ["ev-1"]
    assert rec.components[0].version == 1
    assert {c.component for c in rec.components} == set(COMPONENT_IDS)
