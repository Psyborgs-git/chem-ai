"""Stdlib rollout planning for GRPO over the CS-0901 environment.

Split from ``rollout.py`` so the host can import — and unit-test —
the run-level compute envelope and the legal-action enumerator
WITHOUT torch. The sampler that consumes this module is the
torch-only half; these pieces are pure env-contract logic:

- ``RolloutScheduler`` is the run-level compute envelope
  (AT-0902-3): it admits episodes only while every meter (episodes,
  tool calls, compute units, policy tokens, wall seconds) stays inside
  the approved ``RlRolloutBudget``; the first admission that would
  exceed it raises ``BudgetExhausted`` and work STOPS. There is
  deliberately no fallback or remote-offload path — P10 cloud
  dispatch is still disabled by design.
- ``enumerate_candidates`` + ``render_observation`` + ``marker_text``
  define the menu-choice action encoding the policy actually
  manipulates: the legal typed actions at an observation, rendered as
  compact canonical action markers.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from workers.training.rl.environment.contracts import (
    EpisodeRecord,
    EvidenceSnapshot,
    Observation,
    RlPolicyRef,
    RlTaskDef,
    canonical_json,
)

from .contracts import RlRolloutBudget, TrainerFailure


class BudgetExhausted(TrainerFailure):
    """Compute-envelope exhaustion — the scheduler stops the run."""

    def __init__(self, detail: str, meter: str) -> None:
        super().__init__(
            "BUDGET_EXHAUSTED",
            f"rollout envelope exhausted on {meter}: {detail}",
        )
        self.meter = meter


def _compact_result(result: dict[str, Any], *, limit: int = 64) -> str:
    """Observation result → short stable text (policy-visible only —
    the Observation contract never carries hidden labels)."""
    ids: list[str] = []
    for value in result.values():
        if isinstance(value, list):
            for item in value[:4]:
                if isinstance(item, dict):
                    for key in ("evidence_id", "id", "name"):
                        if key in item:
                            ids.append(str(item[key]))
                            break
    if ids:
        return "|".join(ids)[:limit]
    keys = sorted(str(k) for k in result.keys())
    return "|".join(keys)[:limit]


def render_observation(obs: Observation) -> str:
    """Canonical compact render of the policy-visible observation.

    ``|``-joined and newline-free on purpose: ``\\n`` is the
    tokenizer's eos — the trainer masks a completion after its first
    eos, so episode text must never emit it (the loss then covers
    every action marker in the episode, not just the first)."""
    parts = [f"S:{obs.status}"]
    task = obs.task
    if task is not None:
        text = " ".join(m.content for m in task.messages).replace("\n", " ")
        parts.append(f"T:{task.task_id}>{text[:80]}")
        if task.allowed_tools:
            parts.append("W:" + ",".join(task.allowed_tools))
    if obs.result is not None:
        parts.append(f"R:{_compact_result(obs.result).replace(chr(10), ' ')}")
    if obs.error:
        parts.append(f"E:{obs.error.get('code', 'x')}")
    rem = obs.budgets_remaining
    parts.append(
        f"B:{int(rem.get('steps', 0))},{int(rem.get('tool_calls', 0))},"
        f"{int(rem.get('compute_units', 0))}"
    )
    return "|".join(parts)


def marker_text(index: int) -> str:
    """The canonical action marker the policy emits for candidate
    ``index`` — compact, newline-free (eos stays out of completions)."""
    return f"A{index:02d}"


def enumerate_candidates(
    obs: Observation,
    task: RlTaskDef,
    snapshot: EvidenceSnapshot,
    *,
    max_tool_calls: int = 6,
) -> list[dict[str, Any]]:
    """The legal action set at this observation — replayed tool calls
    plus task-shaped terminal actions, deduplicated canonically.

    Only tools the environment permits THIS policy (the reset
    constraint carries the server-side grant resolution) and only
    arguments pinned in the snapshot's replay table are offered —
    free-form action text is never invented."""
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _offer(action: dict[str, Any]) -> None:
        key = canonical_json(action)
        if key not in seen:
            seen.add(key)
            candidates.append(action)

    if not obs.done:
        permitted = set(obs.constraints.get("allowed_tools") or [])
        if task.allowed_tools:
            permitted &= set(task.allowed_tools)
        calls = 0
        for entry in snapshot.replay:
            if calls >= max_tool_calls:
                break
            if entry.tool in permitted:
                _offer(
                    {
                        "type": "tool_call",
                        "tool": entry.tool,
                        "arguments": dict(entry.arguments),
                    }
                )
                calls += 1
        # The local computational checker needs no replay row.
        if "validate_formulation" in permitted and calls < max_tool_calls:
            _offer(
                {
                    "type": "tool_call",
                    "tool": "validate_formulation",
                    "arguments": {"formulation": {"objective": task.task_id}},
                }
            )

    target = task.target
    if task.kind in ("safety", "privacy") or (target is not None and target.expect == "refusal"):
        _offer(
            {
                "type": "final_answer",
                "answer": "I decline to provide that.",
                "citations": [],
            }
        )
        _offer(
            {
                "type": "final_answer",
                "answer": "Here is the restricted content.",
                "citations": [],
            }
        )
    elif target is not None and target.expect == "exact":
        _offer(
            {
                "type": "final_answer",
                "answer": target.value,
                "citations": list(target.required_evidence_ids),
            }
        )
        _offer({"type": "final_answer", "answer": "The value is 42.", "citations": []})
        _offer({"type": "final_answer", "answer": target.value, "citations": []})
    elif target is not None and target.expect == "contains":
        _offer(
            {
                "type": "final_answer",
                "answer": " ".join(target.required_terms),
                "citations": list(target.required_evidence_ids),
            }
        )
        _offer({"type": "final_answer", "answer": "Unrelated result.", "citations": []})
    elif target is not None and target.expect == "json_object":
        _offer(
            {
                "type": "final_answer",
                "answer": json.dumps({"value": target.value or "unknown"}),
                "citations": list(target.required_evidence_ids),
            }
        )
        _offer({"type": "final_answer", "answer": "not a json object", "citations": []})
    if not task.answerable or (target is not None and target.expect == "abstain"):
        _offer({"type": "abstain", "reason": "not enough information"})
        _offer({"type": "final_answer", "answer": "Guessing: 7.", "citations": []})
    else:
        _offer({"type": "abstain", "reason": "insufficient evidence"})
    _offer({"type": "terminate", "reason": "policy_terminate"})
    return candidates


@dataclass
class RolloutScheduler:
    """The run-level compute envelope + bounded concurrency gate.

    Sequential in v1 — ``in_flight`` never exceeds 1, always inside
    the declared ``max_concurrent_rollouts`` ceiling. Admission checks
    happen BEFORE an episode starts; charge happens after it ends —
    an exhausted meter raises ``BudgetExhausted`` and no further work
    is admitted."""

    budget: RlRolloutBudget
    started: float = field(default_factory=time.monotonic)
    episodes: int = 0
    tool_calls: int = 0
    compute_units: float = 0.0
    policy_tokens: int = 0
    in_flight: int = 0

    def _check(self) -> None:
        if self.episodes >= self.budget.max_episodes:
            raise BudgetExhausted(
                f"{self.episodes}/{self.budget.max_episodes} episodes", "episodes"
            )
        if self.compute_units >= self.budget.max_compute_units:
            raise BudgetExhausted(
                f"{self.compute_units:.1f}/{self.budget.max_compute_units} compute units",
                "compute_units",
            )
        if self.policy_tokens >= self.budget.max_policy_tokens:
            raise BudgetExhausted(
                f"{self.policy_tokens}/{self.budget.max_policy_tokens} policy tokens",
                "policy_tokens",
            )
        elapsed = time.monotonic() - self.started
        if elapsed >= self.budget.max_wall_seconds:
            raise BudgetExhausted(
                f"{elapsed:.1f}/{self.budget.max_wall_seconds} wall seconds",
                "wall_seconds",
            )

    def admit(self) -> None:
        if self.in_flight + 1 > self.budget.max_concurrent_rollouts:
            raise BudgetExhausted(
                f"{self.in_flight + 1}>{self.budget.max_concurrent_rollouts} rollouts",
                "concurrency",
            )
        self._check()
        self.in_flight += 1

    def charge(self, episode: EpisodeRecord, *, policy_tokens: int) -> None:
        self.in_flight = max(0, self.in_flight - 1)
        self.episodes += 1
        self.tool_calls += episode.totals.tool_calls
        self.compute_units += episode.totals.compute_units
        self.policy_tokens += policy_tokens

    def snapshot(self) -> dict[str, Any]:
        return {
            "episodes": self.episodes,
            "toolCalls": self.tool_calls,
            "computeUnits": round(self.compute_units, 4),
            "policyTokens": self.policy_tokens,
            "wallSeconds": round(time.monotonic() - self.started, 3),
            "envelope": self.budget.model_dump(mode="json"),
            "concurrencyBound": self.budget.max_concurrent_rollouts,
            "cloudFallback": "none — exhausted envelopes stop work by design",
        }


def corpus_digest(tasks: list[RlTaskDef], snapshot: EvidenceSnapshot, policy: RlPolicyRef) -> str:
    """sha256 of the canonical corpus document — the digest stamped
    into the spec and the approval's bound inputs. Delegates to the
    shared ``RlCorpus`` contract so the host and the container compute
    the identical digest."""
    from workers.training.rl.corpus import RlCorpus

    return RlCorpus(tasks=tasks, snapshot=snapshot, policy=policy).digest()
