"""Bounded RL environment — reset/step/terminate (CS-0901, §19.2).

The environment owns every hard budget counter (steps, wall time,
policy tokens, tool calls, compute units) — they are enforced here,
independently of the model, and debited *before* a tool executes.

Action handling per ``step``:

1. validate the typed action (malformed payloads are observable
   ``invalid_action`` errors and still consume budget);
2. check budgets and permissions (catalog membership, per-task allow
   list, policy tool allow list, the required capability through the
   shared ``effective_grants`` ceiling — a policy can never hold an
   approval or service-only capability);
3. execute an approved tool (pure computation) or a replay lookup
   (matched → marked replay; unmatched → explicit ``unavailable``);
4. return an observable result, the incurred cost and the raw reward
   components — the policy sees only ``observation``.

Denied actions are refused *before* any executor is consulted: no lab
write and no network path exist anywhere in this package.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

import jsonschema
from chem_studio_policy.capabilities import Grant, effective_grants, has_capability
from pydantic import TypeAdapter, ValidationError

from .contracts import (
    ENV_CONTRACT_VERSION,
    REWARD_CONTRACT_VERSION,
    AbstainAction,
    BudgetEnvelope,
    EnvConfigError,
    EpisodeOutcome,
    EpisodeRecord,
    EvidenceSnapshot,
    FinalAnswerAction,
    Observation,
    RlAction,
    RlCost,
    RlPolicyRef,
    RlStep,
    RlTaskDef,
    SwitchTaskAction,
    TerminateAction,
    ToolCallAction,
    canonical_json,
)
from .tools import FORBIDDEN_TOOLS, EnvTool, ToolUnavailable, default_catalog

_ACTION_ADAPTER: TypeAdapter[Any] = TypeAdapter(RlAction)


class _Episode:
    """Mutable internal episode state — converted to the immutable
    ``EpisodeRecord`` at terminate()."""

    def __init__(
        self,
        *,
        task: RlTaskDef,
        seed: int,
        snapshot: EvidenceSnapshot,
        policy: RlPolicyRef,
        budget: BudgetEnvelope,
        started: float,
    ) -> None:
        self.task = task
        self.seed = seed
        self.snapshot = snapshot
        self.policy = policy
        self.budget = budget
        self.started = started
        self.steps: list[RlStep] = []
        self.calls_seen: set[str] = set()
        self.done = False
        self.outcome: EpisodeOutcome | None = None
        self.record: EpisodeRecord | None = None
        self.totals = {
            "steps": 0,
            "tool_calls": 0,
            "compute_units": 0.0,
            "policy_tokens": 0,
        }
        self.denied_attempts = 0
        self.invalid_actions = 0
        self.unavailable_results = 0
        self.scope_violations = 0
        self.replay_hits = 0


class ResearchRlEnvironment:
    """One pinned task set + closed tool catalog + frozen versions."""

    def __init__(
        self,
        *,
        tasks: list[RlTaskDef],
        tools: list[EnvTool] | None = None,
        reward_contract_version: int = REWARD_CONTRACT_VERSION,
        default_budget: BudgetEnvelope | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._tasks = {t.task_id: t for t in tasks}
        if len(self._tasks) != len(tasks):
            raise EnvConfigError("DUPLICATE_TASK", "duplicate task_id in registry")
        self._tools = {t.name: t for t in (tools or default_catalog())}
        self.reward_contract_version = reward_contract_version
        self.default_budget = default_budget or BudgetEnvelope()
        self._clock = clock or time.monotonic
        self._ep: _Episode | None = None

    # -- reset ------------------------------------------------------

    def reset(
        self,
        *,
        task_id: str,
        seed: int,
        evidence_snapshot: EvidenceSnapshot,
        policy: RlPolicyRef,
    ) -> Observation:
        """Pin task/versions/budgets; return permitted observations +
        constraints only (§19.2)."""
        task = self._tasks.get(task_id)
        if task is None:
            raise EnvConfigError("UNKNOWN_TASK", f"no task '{task_id}'")
        if policy.kind != "agent":
            raise EnvConfigError("POLICY_NOT_AGENT", "the RL policy principal must be kind='agent'")
        for tool_name in task.allowed_tools:
            if tool_name not in self._tools:
                raise EnvConfigError("UNKNOWN_TOOL", f"task allows unregistered tool '{tool_name}'")
        missing_evidence = set()
        if task.target is not None:
            missing_evidence = set(task.target.required_evidence_ids) - set(
                evidence_snapshot.evidence_ids
            )
        if missing_evidence:
            raise EnvConfigError(
                "SNAPSHOT_INCOMPLETE",
                f"snapshot lacks required evidence ids: {sorted(missing_evidence)}",
            )
        budget = task.budgets or self.default_budget
        self._ep = _Episode(
            task=task,
            seed=seed,
            snapshot=evidence_snapshot,
            policy=policy,
            budget=budget,
            started=self._clock(),
        )
        return self._observation(
            status="ready",
            task=task.public(),
            constraints={
                "allowed_action_types": [
                    "tool_call",
                    "final_answer",
                    "abstain",
                    "terminate",
                ],
                "allowed_tools": self._permitted_tools(task, policy),
                "budgets": budget.model_dump(),
            },
        )

    # -- step -------------------------------------------------------

    def step(self, action: dict[str, Any] | RlAction) -> RlStep:
        ep = self._require_episode()
        if ep.done:
            return self._record(
                ep,
                action_type="after_done",
                status="invalid_action",
                done=True,
                error_code="EPISODE_FINISHED",
                result=None,
                error_message="episode already terminated",
            )

        # hard budgets are env-owned — checked before anything runs
        exhausted = self._budget_exhausted(ep)
        if exhausted is not None:
            return self._budget_stop(ep, exhausted)

        ep.totals["steps"] += 1
        index = len(ep.steps)

        if isinstance(action, dict):
            try:
                parsed = _ACTION_ADAPTER.validate_python(action)
            except ValidationError:
                ep.invalid_actions += 1
                return self._record(
                    ep,
                    action_type="invalid",
                    status="invalid_action",
                    done=False,
                    error_code="INVALID_ACTION",
                    error_message="action payload failed typed validation",
                )
        else:
            parsed = action

        # policy-reported token usage counts against the hard envelope
        usage = getattr(parsed, "usage", None)
        if usage is not None:
            ep.totals["policy_tokens"] += usage.prompt_tokens + usage.completion_tokens
        if ep.totals["policy_tokens"] > ep.budget.max_policy_tokens:
            return self._budget_stop(ep, "policy_tokens", last_index=index)

        if isinstance(parsed, ToolCallAction):
            return self._tool_step(ep, parsed, index)
        if isinstance(parsed, FinalAnswerAction):
            return self._terminal_step(ep, parsed, index)
        if isinstance(parsed, AbstainAction):
            ep.done = True
            ep.outcome = EpisodeOutcome(
                reason="abstain", abstained=True, detail=parsed.reason[:300]
            )
            return self._record(
                ep,
                action_type="abstain",
                status="finished",
                done=True,
                components={"terminated": 1.0},
            )
        if isinstance(parsed, SwitchTaskAction):
            # easier-task switching is denied — the episode stays pinned
            ep.scope_violations += 1
            return self._record(
                ep,
                action_type="switch_task",
                status="denied",
                done=False,
                error_code="TASK_PINNED",
                error_message="task is pinned at reset; mid-episode switching is denied",
                components={"task_scope_violation": 1.0},
            )
        if isinstance(parsed, TerminateAction):
            ep.done = True
            ep.outcome = EpisodeOutcome(reason="policy_terminate", detail=parsed.reason[:300])
            return self._record(
                ep,
                action_type="terminate",
                status="finished",
                done=True,
                components={"terminated": 1.0},
            )
        raise AssertionError("unreachable action type")  # pragma: no cover

    # -- terminate ---------------------------------------------------

    def terminate(self, reason: str = "terminated") -> EpisodeRecord:
        """Record the final outcome — idempotent, returns the record."""
        ep = self._require_episode()
        if ep.record is not None:
            return ep.record
        if ep.outcome is None:
            ep.outcome = EpisodeOutcome(reason="error", detail=reason[:300])
        totals = RlCost(
            steps=int(ep.totals["steps"]),
            tool_calls=int(ep.totals["tool_calls"]),
            compute_units=float(ep.totals["compute_units"]),
            policy_tokens=int(ep.totals["policy_tokens"]),
            wall_seconds=round(self._clock() - ep.started, 6),
        )
        record = EpisodeRecord(
            episode_id=str(uuid.uuid4()),
            task_id=ep.task.task_id,
            task_version=ep.task.task_version,
            seed=ep.seed,
            env_contract_version=ENV_CONTRACT_VERSION,
            reward_contract_version=self.reward_contract_version,
            snapshot_digest=ep.snapshot.digest(),
            policy_id=ep.policy.policy_id,
            steps=list(ep.steps),
            outcome=ep.outcome,
            totals=totals,
            denied_attempts=ep.denied_attempts,
            invalid_actions=ep.invalid_actions,
            unavailable_results=ep.unavailable_results,
            scope_violations=ep.scope_violations,
            replay_hits=ep.replay_hits,
            capability={
                "dataStatus": "fixture_only",
                "scientificStatus": "not_validated",
                "execution": "computational/replay only — no physical experiment autonomy",
                "heldOutSuiteAccess": "none — the promotion suite is not a reward endpoint",
            },
        )
        ep.record = record
        return record

    # -- internals ---------------------------------------------------

    def _require_episode(self) -> _Episode:
        if self._ep is None:
            raise EnvConfigError("NO_EPISODE", "call reset() before step/terminate")
        return self._ep

    def _permitted_tools(self, task: RlTaskDef, policy: RlPolicyRef) -> list[str]:
        permitted = set(task.allowed_tools or self._tools.keys())
        if policy.allowed_tools is not None:
            permitted &= set(policy.allowed_tools)
        grants = effective_grants("agent", frozenset(Grant(capability=g) for g in policy.grants))
        out = []
        for name, tool in self._tools.items():
            if name not in permitted:
                continue
            if not has_capability(grants, tool.required_capability):
                continue
            out.append(name)
        return sorted(out)

    def _budget_exhausted(self, ep: _Episode) -> str | None:
        if ep.totals["steps"] >= ep.budget.max_steps:
            return "steps"
        if self._clock() - ep.started > ep.budget.max_wall_seconds:
            return "wall_seconds"
        return None

    def _budget_stop(self, ep: _Episode, which: str, last_index: int | None = None) -> RlStep:
        ep.done = True
        ep.outcome = EpisodeOutcome(reason="budget_exhausted", detail=f"{which} budget exhausted")
        return self._record(
            ep,
            action_type="budget",
            status="budget_exhausted",
            done=True,
            error_code="BUDGET_EXHAUSTED",
            error_message=f"{which} budget exhausted",
            index=last_index,
            components={"budget_exhausted": 1.0},
        )

    def _tool_step(self, ep: _Episode, action: ToolCallAction, index: int) -> RlStep:
        name = action.tool
        if ep.totals["tool_calls"] >= ep.budget.max_tool_calls:
            return self._budget_stop(ep, "tool_calls", last_index=index)

        # denied verbs: refused before ANY executor is consulted — the
        # attempt is observable, nothing executes (AT-0901-2)
        if name in FORBIDDEN_TOOLS:
            ep.denied_attempts += 1
            required = FORBIDDEN_TOOLS[name]
            return self._record(
                ep,
                action_type="tool_call",
                tool=name,
                status="denied",
                done=False,
                error_code="ACTION_DENIED",
                error_message=(
                    f"'{name}' requires capability '{required}', "
                    "which a policy principal cannot hold"
                ),
                components={"denied_attempt": 1.0},
            )

        tool = self._tools.get(name)
        if tool is None:
            return self._record(
                ep,
                action_type="tool_call",
                tool=name,
                status="unknown_tool",
                done=False,
                error_code="UNKNOWN_TOOL",
                error_message=f"no registered tool '{name}'",
                components={"tool_valid": 0.0, "unique_call": 1.0},
            )

        permitted = set(ep.task.allowed_tools or self._tools.keys())
        if ep.policy.allowed_tools is not None:
            permitted &= set(ep.policy.allowed_tools)
        if name not in permitted:
            ep.denied_attempts += 1
            return self._record(
                ep,
                action_type="tool_call",
                tool=name,
                status="denied",
                done=False,
                error_code="TOOL_NOT_PERMITTED",
                error_message=f"tool '{name}' is not permitted for this task/policy",
                components={"denied_attempt": 1.0},
            )

        grants = effective_grants("agent", frozenset(Grant(capability=g) for g in ep.policy.grants))
        if not has_capability(grants, tool.required_capability):
            ep.denied_attempts += 1
            return self._record(
                ep,
                action_type="tool_call",
                tool=name,
                status="denied",
                done=False,
                error_code="CAPABILITY_DENIED",
                error_message=(f"tool '{name}' requires capability '{tool.required_capability}'"),
                components={"denied_attempt": 1.0},
            )

        # task-scope arguments may not point at another task
        arg_task = action.arguments.get("task_id")
        if arg_task is not None and str(arg_task) != ep.task.task_id:
            ep.scope_violations += 1
            return self._record(
                ep,
                action_type="tool_call",
                tool=name,
                status="denied",
                done=False,
                error_code="TASK_SCOPE_VIOLATION",
                error_message="arguments reference a task outside this episode",
                components={"task_scope_violation": 1.0},
            )

        try:
            jsonschema.validate(action.arguments, tool.input_schema)
        except jsonschema.ValidationError as exc:
            ep.invalid_actions += 1
            return self._record(
                ep,
                action_type="tool_call",
                tool=name,
                status="invalid_action",
                done=False,
                error_code="INVALID_INPUT",
                error_message=f"arguments: {exc.message[:200]}",
                components={"tool_valid": 0.0, "unique_call": 1.0},
            )

        # compute budget is debited BEFORE the tool runs
        if ep.totals["compute_units"] + tool.compute_cost > ep.budget.max_compute_units:
            return self._budget_stop(ep, "compute_units", last_index=index)
        ep.totals["tool_calls"] += 1
        ep.totals["compute_units"] += tool.compute_cost

        call_key = f"{name}:{self._canon(action.arguments)}"
        unique = call_key not in ep.calls_seen
        ep.calls_seen.add(call_key)

        try:
            result, entry = tool.execute(action.arguments, ep.snapshot)
        except ToolUnavailable as exc:
            ep.unavailable_results += 1
            return self._record(
                ep,
                action_type="tool_call",
                tool=name,
                status="unavailable",
                done=False,
                error_code="UNAVAILABLE",
                error_message=str(exc)[:300],
                components={
                    "tool_valid": 0.0,
                    "unique_call": 1.0 if unique else 0.0,
                    "compute_cost": tool.compute_cost,
                },
            )
        except Exception:
            ep.unavailable_results += 1
            return self._record(
                ep,
                action_type="tool_call",
                tool=name,
                status="unavailable",
                done=False,
                error_code="TOOL_ERROR",
                error_message="tool failed; error is an observation, not a result",
                components={
                    "tool_valid": 0.0,
                    "unique_call": 1.0 if unique else 0.0,
                    "compute_cost": tool.compute_cost,
                },
            )

        if entry is not None:
            ep.replay_hits += 1
        return self._record(
            ep,
            action_type="tool_call",
            tool=name,
            status="ok",
            done=False,
            result=result,
            replay=entry is not None,
            replay_id=entry.replay_id if entry is not None else None,
            provenance=dict(entry.provenance) if entry is not None else {},
            components={
                "tool_valid": 1.0,
                "unique_call": 1.0 if unique else 0.0,
                "compute_cost": tool.compute_cost,
            },
        )

    def _terminal_step(self, ep: _Episode, action: FinalAnswerAction, index: int) -> RlStep:
        ep.done = True
        ep.outcome = EpisodeOutcome(
            reason="final_answer",
            final_answer=action.answer,
            citations=list(action.citations),
        )
        return self._record(
            ep,
            action_type="final_answer",
            status="finished",
            done=True,
            result=None,
            components={"terminated": 1.0},
        )

    def _record(
        self,
        ep: _Episode,
        *,
        action_type: str,
        status: str,
        done: bool,
        tool: str | None = None,
        result: dict[str, Any] | None = None,
        replay: bool = False,
        replay_id: str | None = None,
        provenance: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        components: dict[str, float] | None = None,
        index: int | None = None,
    ) -> RlStep:
        idx = index if index is not None else len(ep.steps)
        observation = self._observation(
            status=status,
            step_index=idx,
            done=done,
            task=ep.task.public(),
            result=result,
            replay=replay,
            replay_id=replay_id,
            error=(
                {"code": error_code, "message": error_message} if error_code is not None else None
            ),
        )
        step = RlStep(
            index=idx,
            action_type=action_type,
            tool=tool,
            status=status,
            done=done,
            observation=observation,
            cost=RlCost(
                steps=1,
                tool_calls=1 if tool and status in ("ok", "unavailable") else 0,
                compute_units=(components or {}).get("compute_cost", 0.0),
            ),
            components=components or {},
            error_code=error_code,
            provenance=provenance or {},
        )
        ep.steps.append(step)
        return step

    def _observation(self, *, status: str, **kwargs: Any) -> Observation:
        ep = self._ep
        remaining: dict[str, float] = {}
        if ep is not None:
            remaining = {
                "steps": max(0.0, ep.budget.max_steps - ep.totals["steps"]),
                "tool_calls": max(0.0, ep.budget.max_tool_calls - ep.totals["tool_calls"]),
                "compute_units": max(0.0, ep.budget.max_compute_units - ep.totals["compute_units"]),
                "policy_tokens": max(0.0, ep.budget.max_policy_tokens - ep.totals["policy_tokens"]),
                "wall_seconds": max(0.0, ep.budget.max_wall_seconds - (self._clock() - ep.started)),
            }
        return Observation(status=status, budgets_remaining=remaining, **kwargs)

    @staticmethod
    def _canon(arguments: dict[str, Any]) -> str:
        return canonical_json(arguments)
