"""CS-0901 security tests — denied actions and observation hygiene
(AT-0901-2, §19.1-19.3).

Proves three independent things:

1. Physical-experiment and export/egress attempts return ``denied``
   and *nothing executes* — the denial happens before any executor is
   consulted, no compute is debited, and the package has no
   lab-write/network path at all (source-level check).
2. The closed catalog plus the capability ceiling means approval or
   label-access verbs are unreachable — ``effective_grants`` strips
   them from an agent principal even when granted.
3. Observations never carry hidden labels, reward-only metadata or
   credentials — structurally (schema field set) and dynamically
   (canary scan across a full episode).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from chem_studio_policy.capabilities import (
    CAP_APPROVE_EXPERIMENT,
    CAP_APPROVE_EXPORT,
    CAP_APPROVE_MODEL,
    CAP_READ_EVAL_LABELS,
    Grant,
    capabilities_for_role,
    effective_grants,
)
from workers.training.rl.environment.contracts import (
    BudgetEnvelope,
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
    export_policy,
    label_probe_policy,
    physical_experiment_policy,
)
from workers.training.rl.environment.tools import FORBIDDEN_TOOLS

pytestmark = pytest.mark.security

AGENT_GRANTS = sorted(capabilities_for_role("agent"))
RL_ROOT = Path(__file__).resolve().parents[3] / "workers" / "training" / "rl"


def _snapshot() -> EvidenceSnapshot:
    return EvidenceSnapshot(
        snapshot_id="snap-sec",
        evidence_ids=["ev-1"],
        replay=[
            ReplayEntry(
                replay_id="r1",
                tool="search_evidence",
                arguments={"query": "q"},
                result={"results": []},
                provenance={},
            )
        ],
    )


def _task(**kw) -> RlTaskDef:
    return RlTaskDef(
        task_id="t-1",
        messages=[RlMessage(role="user", content="task")],
        allowed_tools=["search_evidence", "validate_formulation", "request_calculation"],
        budgets=kw.get("budgets", BudgetEnvelope(max_steps=10, max_tool_calls=6)),
        target=kw.get("target", RlTaskTarget(expect="exact", value="secret-target-7")),
    )


def _policy_ref(**kw) -> RlPolicyRef:
    return RlPolicyRef(policy_id="pol", grants=kw.get("grants", AGENT_GRANTS))


# ------------------------------------------------------------- AT-0901-2


@pytest.mark.parametrize(
    "policy_factory",
    [physical_experiment_policy, export_policy],
    ids=["physical_experiment", "export_egress"],
)
def test_denied_actions_never_execute(policy_factory) -> None:
    """AT-0901-2 — denied + observable, zero execution."""
    env = ResearchRlEnvironment(tasks=[_task()])
    record = run_episode(
        env,
        policy_factory(),
        task_id="t-1",
        seed=1,
        evidence_snapshot=_snapshot(),
        policy_ref=_policy_ref(),
    )
    denied = [s for s in record.steps if s.status == "denied"]
    assert len(denied) == 2
    for step in denied:
        assert step.observation.error is not None
        assert step.observation.error["code"] == "ACTION_DENIED"
        # the denial carries the required capability — observable
        assert "requires capability" in step.observation.error["message"]
        # no result payload was produced
        assert step.observation.result is None
        # no compute was debited — nothing ran
        assert step.cost.compute_units == 0.0
    assert record.denied_attempts == 2


def test_denied_attempt_debits_no_compute_or_tool_call() -> None:
    """A denied action consumes only a step — no executor is touched,
    no lab write, no network attempt exists to be made."""
    env = ResearchRlEnvironment(tasks=[_task()])
    env.reset(task_id="t-1", seed=1, evidence_snapshot=_snapshot(), policy=_policy_ref())
    step = env.step({"type": "tool_call", "tool": "run_physical_experiment", "arguments": {}})
    assert step.status == "denied"
    assert step.cost.tool_calls == 0
    assert step.cost.compute_units == 0.0
    record = env.terminate()
    assert record.totals.tool_calls == 0
    assert record.totals.compute_units == 0.0


def test_label_access_verbs_denied() -> None:
    env = ResearchRlEnvironment(tasks=[_task()])
    record = run_episode(
        env,
        label_probe_policy(),
        task_id="t-1",
        seed=1,
        evidence_snapshot=_snapshot(),
        policy_ref=_policy_ref(),
    )
    assert record.denied_attempts == 2
    assert all(s.status != "ok" for s in record.steps if s.action_type == "tool_call")


def test_all_forbidden_verbs_denied_parametric() -> None:
    env = ResearchRlEnvironment(
        tasks=[
            _task(
                budgets=BudgetEnvelope(
                    max_steps=len(FORBIDDEN_TOOLS) + 4,
                    max_tool_calls=len(FORBIDDEN_TOOLS) + 4,
                )
            )
        ]
    )
    env.reset(task_id="t-1", seed=1, evidence_snapshot=_snapshot(), policy=_policy_ref())
    for name in FORBIDDEN_TOOLS:
        step = env.step({"type": "tool_call", "tool": name, "arguments": {}})
        assert step.status == "denied", name
        assert step.observation.error["code"] == "ACTION_DENIED"  # type: ignore[index]


def test_denied_verbs_require_capabilities_no_agent_can_hold() -> None:
    """Every forbidden verb maps to a capability that
    ``effective_grants`` strips from an agent principal — even if a
    grant row existed, the policy still could not hold it."""
    agent = effective_grants(
        "agent", frozenset(Grant(capability=c) for c in FORBIDDEN_TOOLS.values())
    )
    assert agent == frozenset() or all(g.capability not in FORBIDDEN_TOOLS.values() for g in agent)
    forbidden_caps = {CAP_APPROVE_EXPERIMENT, CAP_APPROVE_EXPORT, CAP_APPROVE_MODEL}
    for cap in forbidden_caps:
        stripped = effective_grants("agent", frozenset({Grant(capability=cap)}))
        assert cap not in {g.capability for g in stripped}
    labels = effective_grants("agent", frozenset({Grant(capability=CAP_READ_EVAL_LABELS)}))
    assert CAP_READ_EVAL_LABELS not in {g.capability for g in labels}
    # service-only labels are stripped for non-service kinds entirely
    user = effective_grants("user", frozenset({Grant(capability=CAP_READ_EVAL_LABELS)}))
    assert not user


# ------------------------------------------------------------- no-egress structure


def test_rl_package_has_no_network_or_subprocess_path() -> None:
    """Source-level: nothing in workers/training/rl may open sockets,
    spawn processes, or write outside its own structures — there is
    no egress path for a denied action to reach."""
    banned = ("socket", "requests", "urllib", "httpx", "subprocess", "ftplib", "smtplib")
    offenders: list[str] = []
    for path in RL_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            if any(n in banned for n in names):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders


def test_rl_reward_path_cannot_reach_eval_labels() -> None:
    """The reward/env code has no import path to the promotion gate or
    the label store — the held-out suite is structurally not callable
    as a training reward endpoint."""
    banned = ("promotion", "evaluation_labels", "hidden_targets", "EvaluationService")
    offenders: list[str] = []
    for path in RL_ROOT.rglob("*.py"):
        text = path.read_text()
        for term in banned:
            if term in text:
                offenders.append(f"{path.name}: {term}")
    assert not offenders


# ------------------------------------------------------------- observation hygiene


def test_observation_schema_carries_no_secret_fields() -> None:
    """The policy-facing model has a fixed field set — no label,
    credential, or reward-component channel exists to leak through."""
    fields = set(Observation.model_fields)
    assert fields == {
        "status",
        "step_index",
        "done",
        "task",
        "result",
        "replay",
        "replay_id",
        "budgets_remaining",
        "constraints",
        "error",
    }


def test_full_episode_never_observes_target_or_reward_metadata() -> None:
    task = _task(target=RlTaskTarget(expect="exact", value="CANARY-TGT-31337"))
    env = ResearchRlEnvironment(tasks=[task])
    from workers.training.rl.environment.policies import ScriptedPolicy, final, tool_call

    policy = ScriptedPolicy(
        [
            tool_call("run_physical_experiment", {}),
            tool_call("search_evidence", {"query": "q"}),
            final("CANARY-TGT-31337"),
        ]
    )
    record = run_episode(
        env,
        policy,
        task_id="t-1",
        seed=5,
        evidence_snapshot=_snapshot(),
        policy_ref=_policy_ref(),
    )
    for step in record.steps:
        blob = json.dumps(step.observation.model_dump())
        assert "CANARY-TGT-31337" not in blob
        assert "reward" not in step.observation.model_dump().get("constraints", {})
        # reward components live on the step record, never the observation
        assert "components" not in step.observation.model_dump()
