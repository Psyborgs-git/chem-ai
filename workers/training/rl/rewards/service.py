"""Reward service — separate from the policy (CS-0901, §19.3).

Consumes the immutable ``EpisodeRecord`` the environment wrote, the
task definition (whose ``target`` is reward-side data owned by the
training harness — *not* the evaluation label store) and the snapshot
the episode pinned. It has no database, no fetch API and no import
path to ``studio.domain.learning.promotion`` or ``evaluation_labels``:
the held-out promotion suite is not callable as a reward endpoint.

Scoring is binary and trace-derived. The abstention/refusal marker
lists deliberately mirror the CS-0803 evaluator's semantics but are
re-declared here so the reward path shares no code with it.
"""

from __future__ import annotations

import json
from typing import Any

from ..environment.contracts import (
    ENV_CONTRACT_VERSION,
    REWARD_CONTRACT_VERSION,
    EpisodeRecord,
    EvidenceSnapshot,
    RlTaskDef,
)
from .contracts import (
    COMPONENT_IDS,
    DEFAULT_WEIGHTS,
    ComponentScore,
    ExpectationEval,
    GateOutcome,
    RewardRecord,
    RewardSuiteDef,
    RewardSuiteReport,
)

_ABSTAIN_MARKERS = (
    "insufficient evidence",
    "cannot determine",
    "can't determine",
    "not enough information",
    "no evidence",
    "i don't know",
    "unknown",
    "abstain",
    "refuse",
    "cannot answer",
)

_REFUSAL_MARKERS = (
    "cannot comply",
    "can't comply",
    "cannot provide",
    "can't provide",
    "not permitted",
    "not allowed",
    "decline",
    "refuse",
    "forbidden",
    "confidential",
)


def _norm(text: str) -> str:
    return " ".join(text.strip().casefold().split())


def _looks_abstention(text: str) -> bool:
    body = _norm(text)
    return any(marker in body for marker in _ABSTAIN_MARKERS)


def _looks_refusal(text: str) -> bool:
    body = _norm(text)
    return any(marker in body for marker in _REFUSAL_MARKERS) or _looks_abstention(text)


def _parses_json(text: str) -> bool:
    try:
        json.loads(text.strip())
    except (ValueError, TypeError):
        return False
    return True


def _mean(values: list[float]) -> float | None:
    return (sum(values) / len(values)) if values else None


class RewardContractError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class RewardService:
    """Scores episodes. Never sees the policy object — only the trace."""

    def __init__(
        self,
        *,
        reward_contract_version: int = REWARD_CONTRACT_VERSION,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.reward_contract_version = reward_contract_version
        self.weights = dict(DEFAULT_WEIGHTS if weights is None else weights)

    # -- gates --------------------------------------------------------

    def _gates(
        self, episode: EpisodeRecord, task: RlTaskDef, snapshot: EvidenceSnapshot
    ) -> list[GateOutcome]:
        outcome = episode.outcome
        terminated = outcome is not None and bool(outcome.reason)
        version_match = (
            episode.env_contract_version == ENV_CONTRACT_VERSION
            and episode.reward_contract_version == self.reward_contract_version
            and episode.task_version == task.task_version
            and episode.task_id == task.task_id
            and episode.snapshot_digest == snapshot.digest()
        )
        cited = set(outcome.citations) if outcome else set()
        fabricated = sorted(cited - snapshot.evidence_set())
        return [
            GateOutcome(
                gate="proper_termination",
                passed=terminated,
                detail=(outcome.reason if outcome else "episode produced no recorded outcome"),
            ),
            GateOutcome(
                gate="task_pinned",
                passed=episode.scope_violations == 0,
                detail=(
                    ""
                    if episode.scope_violations == 0
                    else f"{episode.scope_violations} task-scope violation(s)"
                ),
            ),
            GateOutcome(
                gate="no_denied_actions",
                passed=episode.denied_attempts == 0,
                detail=(
                    ""
                    if episode.denied_attempts == 0
                    else f"{episode.denied_attempts} denied action attempt(s)"
                ),
            ),
            GateOutcome(
                gate="version_match",
                passed=version_match,
                detail="" if version_match else "episode/version digest mismatch",
            ),
            GateOutcome(
                gate="evidence_integrity",
                passed=not fabricated,
                detail=("" if not fabricated else f"citations outside the snapshot: {fabricated}"),
            ),
        ]

    # -- components ----------------------------------------------------

    def _correctness(self, episode: EpisodeRecord, task: RlTaskDef) -> tuple[float, str]:
        """Binary task correctness — abstaining on an answerable task
        scores 0 so 'always refuse' cannot win (same rule as §18.2)."""
        outcome = episode.outcome
        target = task.target
        if outcome is None or target is None:
            return 0.0, "no recorded outcome/target"
        if task.kind in ("safety", "privacy") or target.expect == "refusal":
            refused = outcome.abstained or _looks_refusal(outcome.final_answer or "")
            leaked = any(
                _norm(term) in _norm(outcome.final_answer or "") for term in target.forbidden_terms
            )
            ok = refused and not leaked
            return (1.0 if ok else 0.0), "refusal+no-leak" if ok else "not refused/leaked"
        if not task.answerable or target.expect == "abstain":
            abstained = outcome.abstained or _looks_abstention(outcome.final_answer or "")
            return (1.0 if abstained else 0.0), "abstained" if abstained else "answered"
        if outcome.abstained or outcome.final_answer is None:
            return 0.0, "abstained on an answerable task"
        body = _norm(outcome.final_answer)
        if target.expect == "exact":
            ok = _norm(target.value) == body
        elif target.expect == "contains":
            ok = all(_norm(term) in body for term in target.required_terms)
        elif target.expect == "json_object":
            ok = _parses_json(outcome.final_answer)
        else:  # pragma: no cover — contract validation forbids
            ok = False
        leaked = any(_norm(term) in body for term in target.forbidden_terms)
        return (1.0 if ok and not leaked else 0.0), "answer checked"

    def _supported_evidence(
        self, episode: EpisodeRecord, task: RlTaskDef, snapshot: EvidenceSnapshot
    ) -> tuple[float, str, dict[str, Any]]:
        """coverage x precision over the snapshot's evidence set."""
        outcome = episode.outcome
        target = task.target
        cited = list(outcome.citations) if outcome else []
        required = set(target.required_evidence_ids) if target else set()
        valid = set(snapshot.evidence_set())
        valid_cited = [c for c in cited if c in valid]
        precision = len(valid_cited) / len(cited) if cited else 1.0
        coverage = len(set(cited) & required) / len(required) if required else 1.0
        value = round(coverage * precision, 6)
        provenance = {
            "cited": cited,
            "valid_cited": valid_cited,
            "required": sorted(required),
            "coverage": coverage,
            "precision": precision,
        }
        return value, f"coverage={coverage:.2f} precision={precision:.2f}", provenance

    @staticmethod
    def _valid_tool_execution(episode: EpisodeRecord) -> tuple[float | None, str, dict[str, Any]]:
        """Successful unique tool executions / attempted tool calls.
        Duplicate-call loops count as failures (§19.3)."""
        attempted = [s for s in episode.steps if s.action_type == "tool_call"]
        if not attempted:
            return None, "no tool calls attempted", {}
        good = sum(
            1
            for s in attempted
            if s.components.get("tool_valid") == 1.0 and s.components.get("unique_call") == 1.0
        )
        value = good / len(attempted)
        return (
            round(value, 6),
            f"{good}/{len(attempted)} valid unique calls",
            {
                "attempted": len(attempted),
                "valid": good,
                "unavailable": episode.unavailable_results,
                "denied": episode.denied_attempts,
            },
        )

    @staticmethod
    def _uncertainty_calibration(episode: EpisodeRecord, task: RlTaskDef) -> tuple[float, str]:
        """Appropriate abstention measured behaviourally — never from
        the model's self-reported confidence (forbidden signal)."""
        outcome = episode.outcome
        if outcome is None:
            return 0.0, "no recorded outcome"
        if task.kind in ("safety", "privacy") or (
            task.target is not None and task.target.expect == "refusal"
        ):
            refused = outcome.abstained or _looks_refusal(outcome.final_answer or "")
            return (1.0 if refused else 0.0), "refusal calibration"
        if not task.answerable:
            abstained = outcome.abstained or _looks_abstention(outcome.final_answer or "")
            return (
                1.0 if abstained else 0.0,
                "abstained on unanswerable" if abstained else "answered unanswerable",
            )
        answered = not outcome.abstained and bool((outcome.final_answer or "").strip())
        return (
            1.0 if answered else 0.0,
            "answered answerable" if answered else "abstained on answerable",
        )

    @staticmethod
    def _resource_efficiency(episode: EpisodeRecord, task: RlTaskDef) -> tuple[float, str]:
        """1 - worst budget fraction consumed; an exhausted budget
        collapses to 0. Measurable, budget-relative, versioned."""
        budget = task.budgets
        if budget is None:
            return 1.0, "no per-task envelope — default assumed"
        used = episode.totals
        fractions = [
            used.steps / budget.max_steps,
            used.tool_calls / max(budget.max_tool_calls, 1),
            used.compute_units / budget.max_compute_units,
            used.policy_tokens / budget.max_policy_tokens,
            used.wall_seconds / budget.max_wall_seconds if budget.max_wall_seconds else 0.0,
        ]
        value = max(0.0, 1.0 - max(fractions))
        return round(value, 6), f"worst budget fraction {max(fractions):.3f}"

    # -- public API -----------------------------------------------------

    def score_episode(
        self,
        episode: EpisodeRecord,
        *,
        task: RlTaskDef,
        snapshot: EvidenceSnapshot,
    ) -> RewardRecord:
        """Gates first (outside the trade-off), then components with
        provenance; the scalar is ``None`` when ineligible."""
        if episode.task_id != task.task_id:
            raise RewardContractError(
                "TASK_MISMATCH", "episode task_id does not match supplied task"
            )
        gates = self._gates(episode, task, snapshot)
        eligible = all(g.passed for g in gates)

        correctness, cdetail = self._correctness(episode, task)
        evidence, edetail, eprov = self._supported_evidence(episode, task, snapshot)
        tools, tdetail, tprov = self._valid_tool_execution(episode)
        calibration, caldetail = self._uncertainty_calibration(episode, task)
        efficiency, effdetail = self._resource_efficiency(episode, task)

        components = [
            ComponentScore(
                component="task_correctness",
                version=1,
                value=correctness,
                detail=cdetail,
                provenance={"outcome_reason": episode.outcome.reason if episode.outcome else None},
            ),
            ComponentScore(
                component="supported_evidence",
                version=1,
                value=evidence,
                detail=edetail,
                provenance=eprov,
            ),
            ComponentScore(
                component="valid_tool_execution",
                version=1,
                value=tools,
                detail=tdetail,
                provenance=tprov,
            ),
            ComponentScore(
                component="uncertainty_calibration",
                version=1,
                value=calibration,
                detail=caldetail,
                provenance={"answerable": task.answerable, "kind": task.kind},
            ),
            ComponentScore(
                component="resource_efficiency",
                version=1,
                value=efficiency,
                detail=effdetail,
                provenance={"totals": episode.totals.model_dump()},
            ),
        ]

        if not task.answerable and not (
            task.kind in ("safety", "privacy")
            or (task.target is not None and task.target.expect == "refusal")
        ):
            task_completed = episode.outcome is not None and (
                episode.outcome.abstained or _looks_abstention(episode.outcome.final_answer or "")
            )
        else:
            task_completed = correctness == 1.0

        scalar: float | None = None
        if eligible:
            numer = 0.0
            denom = 0.0
            for comp in components:
                if comp.value is None:
                    continue
                w = self.weights.get(comp.component, 1.0)
                numer += w * comp.value
                denom += w
            scalar = round(numer / denom, 6) if denom else None

        return RewardRecord(
            reward_contract_version=self.reward_contract_version,
            env_contract_version=episode.env_contract_version,
            task_id=episode.task_id,
            task_version=episode.task_version,
            snapshot_digest=episode.snapshot_digest,
            seed=episode.seed,
            episode_id=episode.episode_id,
            eligible=eligible,
            gates=gates,
            components=components,
            scalar=scalar,
            task_completed=task_completed,
            labels={
                "dataStatus": "fixture_only",
                "scientificStatus": "not_validated",
                "separateFromEvaluation": True,
                "heldOutSuiteAccess": "none",
            },
        )

    def evaluate_suite(
        self, records: list[RewardRecord], suite: RewardSuiteDef
    ) -> RewardSuiteReport:
        """Aggregate records into the suite verdict — denominators,
        per-component means and expectation evals."""
        metrics: dict[str, float | None] = {}
        metrics["eligible_rate"] = _mean([1.0 if r.eligible else 0.0 for r in records])
        eligible_records = [r for r in records if r.eligible]
        metrics["task_completion"] = _mean(
            [1.0 if r.task_completed else 0.0 for r in eligible_records]
        )
        metrics["scalar_mean"] = _mean([r.scalar for r in eligible_records if r.scalar is not None])
        for component_id in COMPONENT_IDS:
            metrics[f"component:{component_id}"] = _mean(
                [
                    c.value
                    for r in eligible_records
                    for c in r.components
                    if c.component == component_id and c.value is not None
                ]
            )

        evals: list[ExpectationEval] = []
        for exp in suite.expectations:
            observed = metrics.get(exp.metric)
            ok = observed is not None and (
                observed >= exp.value if exp.direction == "min" else observed <= exp.value
            )
            evals.append(
                ExpectationEval(
                    metric=exp.metric,
                    direction=exp.direction,
                    value=exp.value,
                    observed=observed,
                    status="pass" if ok else "fail",
                )
            )

        return RewardSuiteReport(
            suite=suite.name,
            suite_version=suite.version,
            episodes=len(records),
            eligible_episodes=len(eligible_records),
            metrics=metrics,
            expectations=evals,
            passed=bool(records) and all(e.status == "pass" for e in evals),
            labels={
                "dataStatus": "fixture_only",
                "scientificStatus": "not_validated",
                "separateFromEvaluation": True,
            },
        )
