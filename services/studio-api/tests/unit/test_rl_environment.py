"""CS-0901 unit tests — bounded RL environment mechanics (§19.2).

Covers reset/step/terminate, typed-action validation, replay
provenance (matched AND unmatched — AT-0901-3), hard budgets enforced
independently of the model, task pinning and observation hygiene.
Pure worker layer — no DB.
"""

from __future__ import annotations

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from workers.training.rl.environment.contracts import (
    ENV_CONTRACT_VERSION,
    REWARD_CONTRACT_VERSION,
    BudgetEnvelope,
    EnvConfigError,
    EvidenceSnapshot,
    Observation,
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
    abstain,
    final,
    switch_task,
    tool_call,
)

AGENT_GRANTS = sorted(capabilities_for_role("agent"))


def _snapshot() -> EvidenceSnapshot:
    return EvidenceSnapshot(
        snapshot_id="snap-1",
        evidence_ids=["ev-1", "ev-2"],
        replay=[
            ReplayEntry(
                replay_id="r-search",
                tool="search_evidence",
                arguments={"query": "solubility"},
                result={"results": [{"evidence_id": "ev-1", "text": "0.42 g/L"}]},
                provenance={"run_id": "run-9", "artifact_ids": ["art-1"]},
            ),
            ReplayEntry(
                replay_id="r-ev",
                tool="get_evidence_record",
                arguments={"evidence_id": "ev-1"},
                result={"evidence_id": "ev-1", "text": "full record"},
                provenance={"run_id": "run-9"},
            ),
        ],
    )


def _task(**kw) -> RlTaskDef:
    return RlTaskDef(
        task_id=kw.get("task_id", "t-1"),
        task_version=kw.get("task_version", 3),
        kind=kw.get("kind", "task"),
        messages=[RlMessage(role="user", content="what is the solubility?")],
        subgroup=kw.get("subgroup", "default"),
        answerable=kw.get("answerable", True),
        allowed_tools=kw.get(
            "allowed_tools",
            [
                "search_evidence",
                "get_evidence_record",
                "summarize_task_evidence",
                "request_calculation",
                "validate_formulation",
            ],
        ),
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


def _policy_ref(**kw) -> RlPolicyRef:
    return RlPolicyRef(
        policy_id=kw.get("policy_id", "pol-1"),
        grants=kw.get("grants", AGENT_GRANTS),
        allowed_tools=kw.get("allowed_tools"),
    )


def _env(task: RlTaskDef, **kw) -> ResearchRlEnvironment:
    return ResearchRlEnvironment(tasks=kw.get("tasks", [task]), clock=kw.get("clock"))


def _reset(env: ResearchRlEnvironment, task_id: str = "t-1", **kw) -> Observation:
    return env.reset(
        task_id=task_id,
        seed=kw.get("seed", 7),
        evidence_snapshot=kw.get("snapshot", _snapshot()),
        policy=kw.get("policy", _policy_ref()),
    )


# ---------------------------------------------------------------- reset


def test_reset_returns_public_task_and_constraints_only() -> None:
    env = _env(_task())
    obs = _reset(env)
    assert obs.status == "ready"
    assert obs.task is not None and obs.task.task_id == "t-1"
    assert "allowed_tools" in obs.constraints
    assert obs.constraints["budgets"]["max_steps"] == 8
    # reward-side data is not observable
    assert "target" not in obs.task.model_dump()


def test_reset_unknown_task_refused() -> None:
    env = _env(_task())
    with pytest.raises(EnvConfigError) as exc:
        _reset(env, task_id="missing")
    assert exc.value.code == "UNKNOWN_TASK"


def test_reset_rejects_non_agent_policy() -> None:
    env = _env(_task())
    with pytest.raises(EnvConfigError):
        env.reset(
            task_id="t-1",
            seed=1,
            evidence_snapshot=_snapshot(),
            policy=RlPolicyRef.model_construct(policy_id="svc", kind="service"),
        )


def test_reset_requires_snapshot_evidence_for_target() -> None:
    env = _env(_task())
    snap = EvidenceSnapshot(snapshot_id="s", evidence_ids=["other"], replay=[])
    with pytest.raises(EnvConfigError) as exc:
        env.reset(task_id="t-1", seed=1, evidence_snapshot=snap, policy=_policy_ref())
    assert exc.value.code == "SNAPSHOT_INCOMPLETE"


def test_reset_validates_task_tool_names() -> None:
    task = _task(allowed_tools=["no_such_tool"])
    env = _env(task)
    with pytest.raises(EnvConfigError) as exc:
        _reset(env)
    assert exc.value.code == "UNKNOWN_TOOL"


# ---------------------------------------------------------------- step


def test_replay_match_returns_marked_result_with_provenance() -> None:
    env = _env(_task())
    _reset(env)
    step = env.step(tool_call("search_evidence", {"query": "solubility"}))
    assert step.status == "ok"
    assert step.observation.replay is True
    assert step.observation.replay_id == "r-search"
    assert step.observation.result == {"results": [{"evidence_id": "ev-1", "text": "0.42 g/L"}]}
    assert step.provenance["run_id"] == "run-9"
    assert step.components["tool_valid"] == 1.0


def test_unmatched_replay_returns_explicit_unavailable() -> None:
    """AT-0901-3 — an unmatched action is an explicit unavailable
    result, never an invented oracle output."""
    env = _env(_task())
    _reset(env)
    step = env.step(tool_call("search_evidence", {"query": "unrecorded query"}))
    assert step.status == "unavailable"
    assert step.observation.error is not None
    assert step.observation.error["code"] == "UNAVAILABLE"
    assert step.observation.result is None
    assert step.observation.replay is False
    # and the episode records the miss
    record = env.terminate()
    assert record.unavailable_results == 1


def test_unavailable_is_not_an_oracle() -> None:
    """AT-0901-3 — a replay miss must not produce fabricated data the
    policy could mistake for a real answer."""
    env = _env(_task())
    _reset(env)
    step = env.step(tool_call("request_calculation", {"kind": "dft", "request": {"x": 1}}))
    assert step.status == "unavailable"
    assert step.observation.result is None


def test_unknown_tool_name_rejected() -> None:
    env = _env(_task())
    _reset(env)
    step = env.step(tool_call("made_up_tool", {}))
    assert step.status == "unknown_tool"
    assert step.observation.error["code"] == "UNKNOWN_TOOL"  # type: ignore[index]


def test_malformed_action_is_invalid_and_consumes_budget() -> None:
    env = _env(_task())
    _reset(env)
    step = env.step({"type": "nonsense"})
    assert step.status == "invalid_action"
    step2 = env.step({"tool": "search_evidence"})  # missing type discriminator
    assert step2.status == "invalid_action"
    record = env.terminate()
    assert record.invalid_actions == 2
    assert record.totals.steps == 2


def test_tool_not_permitted_for_task_is_denied() -> None:
    task = _task(allowed_tools=["search_evidence"])
    env = _env(task)
    _reset(env)
    step = env.step(tool_call("validate_formulation", {"formulation": {}}))
    assert step.status == "denied"
    assert env.terminate().denied_attempts == 1


def test_missing_capability_denies_tool() -> None:
    env = _env(_task())
    _reset(env, policy=_policy_ref(grants=["read_project"]))  # no request_compute
    step = env.step(tool_call("validate_formulation", {"formulation": {"components": []}}))
    assert step.status == "denied"
    assert step.observation.error["code"] == "CAPABILITY_DENIED"  # type: ignore[index]


def test_task_scoped_argument_mismatch_denied() -> None:
    env = _env(_task())
    _reset(env)
    step = env.step(tool_call("summarize_task_evidence", {"task_id": "other-task"}))
    assert step.status == "denied"
    assert step.observation.error["code"] == "TASK_SCOPE_VIOLATION"  # type: ignore[index]
    assert env.terminate().scope_violations == 1


def test_switch_task_denied_and_episode_stays_pinned() -> None:
    other = _task(task_id="t-easy", target=RlTaskTarget(expect="exact", value="easy"))
    env = _env(_task(), tasks=[_task(), other])
    _reset(env)
    step = env.step(switch_task("t-easy"))
    assert step.status == "denied"
    assert step.observation.error["code"] == "TASK_PINNED"  # type: ignore[index]
    # episode still on the original task
    assert step.observation.task is not None
    assert step.observation.task.task_id == "t-1"
    assert env.terminate().scope_violations == 1


def test_computational_tool_executes_live() -> None:
    env = _env(_task())
    _reset(env)
    step = env.step(
        tool_call(
            "validate_formulation",
            {"formulation": {"components": [{"name": "a", "fraction": 1.0}]}},
        )
    )
    assert step.status == "ok"
    assert step.observation.replay is False
    assert step.observation.result is not None
    assert step.observation.result["valid"] is True


# ---------------------------------------------------------------- budgets


def test_step_budget_exhaustion_ends_episode() -> None:
    task = _task(budgets=BudgetEnvelope(max_steps=2, max_tool_calls=8))
    env = _env(task)
    _reset(env)
    env.step(tool_call("search_evidence", {"query": "solubility"}))
    env.step(tool_call("search_evidence", {"query": "solubility"}))
    step = env.step(tool_call("search_evidence", {"query": "solubility"}))
    assert step.status == "budget_exhausted"
    record = env.terminate()
    assert record.outcome is not None
    assert record.outcome.reason == "budget_exhausted"


def test_tool_call_budget_independent_of_steps() -> None:
    task = _task(budgets=BudgetEnvelope(max_steps=16, max_tool_calls=1))
    env = _env(task)
    _reset(env)
    assert env.step(tool_call("search_evidence", {"query": "solubility"})).status == "ok"
    step = env.step(tool_call("search_evidence", {"query": "solubility"}))
    assert step.status == "budget_exhausted"
    assert env.terminate().outcome.reason == "budget_exhausted"  # type: ignore[union-attr]


def test_wall_budget_uses_env_clock_not_policy() -> None:
    clock_state = {"now": 1000.0}
    task = _task(budgets=BudgetEnvelope(max_wall_seconds=5.0))
    env = _env(task, clock=lambda: clock_state["now"])
    _reset(env)
    clock_state["now"] += 10.0  # policy cannot turn back the clock
    step = env.step(tool_call("search_evidence", {"query": "solubility"}))
    assert step.status == "budget_exhausted"


def test_token_budget_counts_policy_reported_usage() -> None:
    task = _task(budgets=BudgetEnvelope(max_policy_tokens=10))
    env = _env(task)
    _reset(env)
    step = env.step(
        {
            "type": "tool_call",
            "tool": "search_evidence",
            "arguments": {"query": "solubility"},
            "usage": {"prompt_tokens": 8, "completion_tokens": 8},
        }
    )
    assert step.status == "budget_exhausted"


def test_compute_budget_debited_before_execution() -> None:
    task = _task(budgets=BudgetEnvelope(max_compute_units=0.4))
    env = _env(task)
    _reset(env)
    # validate_formulation costs 0.1 → 4 calls fit; the 5th must stop
    ok = 0
    for _ in range(5):
        step = env.step(
            tool_call(
                "validate_formulation",
                {"formulation": {"components": [{"name": "a", "fraction": 1.0}]}},
            )
        )
        if step.status == "ok":
            ok += 1
        else:
            assert step.status == "budget_exhausted"
            break
    assert ok == 4


# ---------------------------------------------------------------- hygiene


def test_observation_never_carries_reward_data() -> None:
    """Canary: the target value must not appear anywhere in any
    observation across a whole episode."""
    task = _task(
        target=RlTaskTarget(
            expect="exact",
            value="CANARY-SECRET-9182",
            required_evidence_ids=["ev-1"],
        )
    )
    env = _env(task)
    obs = _reset(env)
    assert "CANARY-SECRET-9182" not in obs.model_dump_json()
    policy = ScriptedPolicy(
        [
            tool_call("search_evidence", {"query": "solubility"}),
            tool_call("search_evidence", {"query": "miss"}),
            final("CANARY-SECRET-9182"),  # a correct guess
        ]
    )
    record = run_episode(
        env,
        policy,
        task_id="t-1",
        seed=1,
        evidence_snapshot=_snapshot(),
        policy_ref=_policy_ref(),
    )
    for step in record.steps:
        if step.observation.status == "finished":
            continue  # the finished marker carries no result payload
        assert "CANARY-SECRET-9182" not in step.observation.model_dump_json()


def test_replay_results_are_always_marked() -> None:
    env = _env(_task())
    _reset(env)
    policy = ScriptedPolicy(
        [
            tool_call("search_evidence", {"query": "solubility"}),
            tool_call("get_evidence_record", {"evidence_id": "ev-1"}),
            final("0.42", ["ev-1"]),
        ]
    )
    record = run_episode(
        env,
        policy,
        task_id="t-1",
        seed=1,
        evidence_snapshot=_snapshot(),
        policy_ref=_policy_ref(),
    )
    replay_steps = [s for s in record.steps if s.tool in ("search_evidence", "get_evidence_record")]
    assert len(replay_steps) == 2
    assert all(s.observation.replay and s.observation.replay_id for s in replay_steps)


def test_terminate_records_outcome_and_versions() -> None:
    env = _env(_task())
    _reset(env)
    env.step(final("0.42", ["ev-1"]))
    record = env.terminate()
    assert record.outcome is not None
    assert record.outcome.reason == "final_answer"
    assert record.outcome.citations == ["ev-1"]
    assert record.env_contract_version == ENV_CONTRACT_VERSION
    assert record.reward_contract_version == REWARD_CONTRACT_VERSION
    assert record.task_version == 3
    assert record.snapshot_digest == _snapshot().digest()
    # idempotent
    assert env.terminate() is record


def test_episode_record_serializes_cleanly() -> None:
    env = _env(_task())
    _reset(env)
    env.step(tool_call("search_evidence", {"query": "solubility"}))
    env.step(abstain("not enough evidence"))
    record = env.terminate()
    payload = record.model_dump_json()
    assert '"reason":"abstain"' in payload
    assert record.outcome is not None and record.outcome.abstained
