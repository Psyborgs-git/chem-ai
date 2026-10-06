"""CS-0902 unit tests — the stdlib rollout plan, run-level budget
envelope (AT-0902-3) and corpus contract.

These run on the host without torch: ``rollout_plan`` + ``corpus`` are
deliberately importable stdlib modules — the compute envelope and the
legal-action enumerator are exercised honestly here; the torch sampler
that consumes them is engine-tested in ``tests/engines/rl``.
"""

from __future__ import annotations

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from pydantic import ValidationError
from workers.training.rl.corpus import RlCorpus, parse_corpus
from workers.training.rl.environment.contracts import (
    EpisodeOutcome,
    EpisodeRecord,
    EvidenceSnapshot,
    Observation,
    ReplayEntry,
    RlCost,
    RlPolicyRef,
    RlTaskDef,
    RlTaskPublic,
)

from engine_adapter_rl.contracts import (
    RlAlgorithmSpec,
    RlRolloutBudget,
    RlTrainSpec,
    TrainerFailure,
)
from engine_adapter_rl.rollout_plan import (
    BudgetExhausted,
    RolloutScheduler,
    corpus_digest,
    enumerate_candidates,
    marker_text,
    render_observation,
)

AGENT_GRANTS = sorted(capabilities_for_role("agent"))

_TOOLS = ["search_evidence", "get_evidence_record", "validate_formulation"]


def _policy(**over: object) -> RlPolicyRef:
    base = {"policy_id": "policy-1", "kind": "agent", "grants": AGENT_GRANTS}
    base.update(over)
    return RlPolicyRef.model_validate(base)


def _task(**over: object) -> RlTaskDef:
    base: dict = {
        "task_id": "t-1",
        "messages": [{"role": "user", "content": "what is the viscosity?"}],
        "answerable": True,
        "allowed_tools": list(_TOOLS),
        "budgets": {"max_steps": 20, "max_tool_calls": 8},
        "target": {
            "expect": "exact",
            "value": "900 mPa·s",
            "required_evidence_ids": ["ev-a"],
        },
    }
    base.update(over)
    return RlTaskDef.model_validate(base)


def _snapshot() -> EvidenceSnapshot:
    return EvidenceSnapshot(
        snapshot_id="snap-1",
        evidence_ids=["ev-a"],
        replay=[
            ReplayEntry(
                replay_id="r-a",
                tool="search_evidence",
                arguments={"query": "viscosity"},
                result={"results": [{"evidence_id": "ev-a"}]},
                provenance={},
            ),
            # a tool the policy does NOT hold — must never be offered
            ReplayEntry(
                replay_id="r-x",
                tool="export_data",
                arguments={"key": "k"},
                result={"ok": True},
                provenance={},
            ),
        ],
    )


def _obs(
    *,
    done: bool = False,
    allowed_tools: list[str] | None = None,
) -> Observation:
    task = _task()
    return Observation(
        status="finished" if done else "ready",
        step_index=0,
        done=done,
        task=RlTaskPublic(
            task_id=task.task_id,
            task_version=task.task_version,
            kind=task.kind,
            messages=task.messages,
            context_refs=[],
            subgroup=task.subgroup,
            answerable=task.answerable,
            allowed_tools=task.allowed_tools,
            budgets=task.budgets,
        ),
        result=None,
        replay=False,
        budgets_remaining={"steps": 10, "tool_calls": 5, "compute_units": 3.0},
        constraints={
            "allowed_tools": _TOOLS if allowed_tools is None else allowed_tools,
        },
        error=None,
    )


def _episode_record() -> EpisodeRecord:
    return EpisodeRecord(
        episode_id="ep-1",
        task_id="t-1",
        task_version=1,
        seed=0,
        env_contract_version=1,
        reward_contract_version=1,
        snapshot_digest="a" * 64,
        policy_id="policy-1",
        steps=[],
        outcome=EpisodeOutcome(
            reason="final_answer",
            final_answer="900 mPa·s",
            abstained=False,
            citations=["ev-a"],
            detail="",
        ),
        totals=RlCost(steps=3, tool_calls=2, compute_units=4.5, policy_tokens=100),
    )


# ----------------------------------------------------------- corpus


class TestCorpusContract:
    def _doc(self) -> dict:
        return {
            "tasks": [_task().model_dump(mode="json")],
            "snapshot": _snapshot().model_dump(mode="json"),
            "policy": _policy().model_dump(mode="json"),
        }

    def test_valid_corpus_digests_deterministically(self) -> None:
        corpus = parse_corpus(self._doc())
        d1 = corpus.digest()
        d2 = parse_corpus(self._doc()).digest()
        assert d1 == d2 and len(d1) == 64

    def test_duplicate_task_ids_rejected(self) -> None:
        doc = self._doc()
        doc["tasks"].append(dict(doc["tasks"][0]))
        with pytest.raises(ValueError, match="duplicate task_id"):
            parse_corpus(doc)

    def test_digest_changes_with_policy(self) -> None:
        d1 = corpus_digest([_task()], _snapshot(), _policy())
        d2 = corpus_digest([_task()], _snapshot(), _policy(policy_id="other"))
        assert d1 != d2

    def test_trainer_and_service_agree_on_digest(self) -> None:
        """The adapter-side digest equals the shared corpus digest —
        the approval binds to the same bytes the runner re-hashes."""
        corpus = parse_corpus(self._doc())
        assert corpus_digest(corpus.tasks, corpus.snapshot, corpus.policy) == corpus.digest()


# ----------------------------------------------------------- scheduler (AT-0902-3)


class TestRolloutScheduler:
    def test_admits_and_charges_within_envelope(self) -> None:
        sched = RolloutScheduler(RlRolloutBudget(max_episodes=4, max_compute_units=100.0))
        sched.admit()
        sched.charge(_episode_record(), policy_tokens=50)
        snap = sched.snapshot()
        assert snap["episodes"] == 1
        assert snap["toolCalls"] == 2
        assert snap["computeUnits"] == 4.5
        assert snap["policyTokens"] == 50
        assert snap["concurrencyBound"] == 1
        assert "none" in snap["cloudFallback"]

    def test_episode_meter_stops_admission(self) -> None:
        sched = RolloutScheduler(RlRolloutBudget(max_episodes=2))
        sched.admit()
        sched.charge(_episode_record(), policy_tokens=0)
        sched.admit()
        sched.charge(_episode_record(), policy_tokens=0)
        with pytest.raises(BudgetExhausted) as exc:
            sched.admit()
        assert exc.value.code == "BUDGET_EXHAUSTED"
        assert exc.value.meter == "episodes"

    def test_compute_meter_stops_admission(self) -> None:
        sched = RolloutScheduler(RlRolloutBudget(max_episodes=10, max_compute_units=5.0))
        sched.admit()
        sched.charge(_episode_record(), policy_tokens=0)  # 4.5 units
        sched.admit()
        sched.charge(_episode_record(), policy_tokens=0)  # 9.0 units
        with pytest.raises(BudgetExhausted) as exc:
            sched.admit()
        assert exc.value.meter == "compute_units"

    def test_token_meter_stops_admission(self) -> None:
        sched = RolloutScheduler(RlRolloutBudget(max_policy_tokens=1100))
        sched.admit()
        sched.charge(_episode_record(), policy_tokens=1000)
        sched.admit()
        sched.charge(_episode_record(), policy_tokens=200)
        with pytest.raises(BudgetExhausted) as exc:
            sched.admit()
        assert exc.value.meter == "policy_tokens"

    def test_concurrency_bound_enforced(self) -> None:
        sched = RolloutScheduler(RlRolloutBudget(max_concurrent_rollouts=1))
        sched.admit()
        with pytest.raises(BudgetExhausted) as exc:
            sched.admit()  # a second in-flight episode is refused
        assert exc.value.meter == "concurrency"

    def test_failure_is_a_structured_trainer_failure(self) -> None:
        sched = RolloutScheduler(RlRolloutBudget(max_concurrent_rollouts=1))
        sched.admit()
        with pytest.raises(TrainerFailure):
            sched.admit()


# ----------------------------------------------------------- candidates


class TestEnumerateCandidates:
    def test_offers_only_permitted_replay_tools(self) -> None:
        actions = enumerate_candidates(_obs(), _task(), _snapshot())
        tools = {a.get("tool") for a in actions if a["type"] == "tool_call"}
        # export_data is never offered — forbidden verb, not permitted
        assert "export_data" not in tools
        assert "search_evidence" in tools
        # replay arguments come from the pinned snapshot, never invented
        call = next(a for a in actions if a["type"] == "tool_call")
        assert call["arguments"] == {"query": "viscosity"}

    def test_forbidden_tool_never_offered_even_if_replayed(self) -> None:
        obs = _obs(allowed_tools=[*_TOOLS, "export_data"])
        actions = enumerate_candidates(obs, _task(), _snapshot())
        # allowed_tools is the server-resolved constraint: export_data
        # can appear there only if grants said so — a policy can never
        # hold approve_export, so offering is unreachable in practice;
        # the driver still intersects with the task's own allow-list.
        tools = {a.get("tool") for a in actions if a["type"] == "tool_call"}
        assert "export_data" not in tools  # task.allowed_tools excludes it

    def test_terminal_actions_match_task_shape(self) -> None:
        actions = enumerate_candidates(_obs(), _task(), _snapshot())
        answers = [a for a in actions if a["type"] == "final_answer"]
        good = next(a for a in answers if a["answer"] == "900 mPa·s" and a["citations"])
        assert good["citations"] == ["ev-a"]
        # a wrong-answer and a citation-free variant are also offered —
        # the reward distinguishes them, not the driver
        assert any(a["answer"] != "900 mPa·s" for a in answers)
        assert any(not a["citations"] for a in answers)
        assert any(a["type"] == "terminate" for a in actions)

    def test_safety_task_offers_refusal(self) -> None:
        task = _task(kind="safety", target={"expect": "refusal"})
        actions = enumerate_candidates(_obs(), task, _snapshot())
        answers = [a["answer"] for a in actions if a["type"] == "final_answer"]
        assert any("decline" in a for a in answers)
        assert any("restricted" in a for a in answers)

    def test_unanswerable_task_offers_abstain(self) -> None:
        task = _task(answerable=False, target={"expect": "abstain"})
        actions = enumerate_candidates(_obs(), task, _snapshot())
        assert any(a["type"] == "abstain" for a in actions)

    def test_done_observation_offers_no_tools(self) -> None:
        actions = enumerate_candidates(_obs(done=True), _task(), _snapshot())
        assert all(a["type"] != "tool_call" for a in actions)


class TestObservationRender:
    def test_render_is_newline_free_and_compact(self) -> None:
        text = render_observation(_obs())
        assert "\n" not in text
        assert "t-1" in text
        assert text.startswith("S:")

    def test_marker_text_is_newline_free(self) -> None:
        for i in (0, 7, 23):
            assert marker_text(i) == f"A{i:02d}"
            assert "\n" not in marker_text(i)


# ----------------------------------------------------------- spec contract


class TestSpecContract:
    def _spec(self, **over: object) -> dict:
        corpus = RlCorpus(tasks=[_task()], snapshot=_snapshot(), policy=_policy())
        base: dict = {
            "schema_name": "rl_train_spec",
            "schema_version": 1,
            "model": {
                "base_model_id": "pico-rl-char-v1",
                "architecture": "pico-rl-v1",
                "init_seed": 0,
                "license_id": "fixture-internal",
            },
            "corpus_digest": corpus.digest(),
        }
        base.update(over)
        return base

    def test_default_spec_validates(self) -> None:
        spec = RlTrainSpec.model_validate(self._spec())
        assert spec.algorithm.family == "grpo"
        assert spec.rollout_budget.max_episodes == 256
        assert spec.digest()

    def test_unknown_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RlTrainSpec.model_validate(self._spec(bogus_field=1))

    def test_beta_must_be_zero(self) -> None:
        """The KL reference path is unsupported for this environment —
        a non-zero beta is rejected, not silently ignored."""
        with pytest.raises(ValidationError):
            RlAlgorithmSpec.model_validate({"beta": 0.1})

    def test_rollout_budget_bounds(self) -> None:
        with pytest.raises(ValidationError):
            RlRolloutBudget.model_validate({"max_episodes": 0})
        with pytest.raises(ValidationError):
            RlRolloutBudget.model_validate({"max_concurrent_rollouts": 0})

    def test_license_training_denied_rejected(self) -> None:
        spec = self._spec(
            model={
                "base_model_id": "pico-rl-char-v1",
                "architecture": "pico-rl-v1",
                "init_seed": 0,
                "license_id": "unknown-license",
            }
        )
        with pytest.raises(ValidationError):
            RlTrainSpec.model_validate(spec)
