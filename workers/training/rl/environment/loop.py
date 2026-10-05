"""Episode driver (CS-0901).

``run_episode`` is the thin loop a trainer (CS-0902) or a test uses:
``reset`` once, then feed the policy only ``Observation``s and hand
each returned action to ``env.step`` until ``done`` or the defensive
action cap, then ``terminate``. The loop never inspects rewards —
that stays with the separate reward service (§19.3).
"""

from __future__ import annotations

from typing import Any, Protocol

from .contracts import EpisodeRecord, EvidenceSnapshot, Observation, RlPolicyRef
from .environment import ResearchRlEnvironment

MAX_DRIVER_ACTIONS = 512  # defensive cap; real bounds are the budgets


class EpisodePolicy(Protocol):
    """Anything that maps an observation to a raw action dict."""

    def act(self, observation: Observation) -> dict[str, Any]: ...


def run_episode(
    env: ResearchRlEnvironment,
    policy: EpisodePolicy,
    *,
    task_id: str,
    seed: int,
    evidence_snapshot: EvidenceSnapshot,
    policy_ref: RlPolicyRef,
    max_actions: int = MAX_DRIVER_ACTIONS,
) -> EpisodeRecord:
    """Drive one policy to termination and return the episode record."""
    obs = env.reset(
        task_id=task_id,
        seed=seed,
        evidence_snapshot=evidence_snapshot,
        policy=policy_ref,
    )
    steps = 0
    while not obs.done and steps < max_actions:
        obs = env.step(policy.act(obs)).observation
        steps += 1
    return env.terminate("driver_end")
