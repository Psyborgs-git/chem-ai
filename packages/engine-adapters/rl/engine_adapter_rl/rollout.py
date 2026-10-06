"""Bounded rollout driver for GRPO over the CS-0901 environment (§19.4).

The policy never emits free-form JSON: at every step the driver
enumerates the *legal typed actions* — tool calls replayed from the
frozen evidence snapshot plus task-shaped terminal actions — renders
each as a canonical action marker, teacher-forces the model over
``prefix + marker`` and softmax-samples the choice. The chosen action
dict goes through the real ``env.step`` validation; the marker tokens
(``env_mask=1``) and the rendered observation tokens
(``env_mask=0``) interleave in the completion so the trainer's
recomputed logprobs see exactly the conditioning the sampler used.

This module holds the torch half of the driver; the stdlib plan —
``RolloutScheduler`` (the AT-0902-3 compute envelope), candidate
enumeration, observation rendering and the corpus digest — lives in
``rollout_plan.py`` so the host can exercise it without the training
stack. The plan symbols are re-exported here so the two halves read
as one driver.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import torch
from workers.training.rl.environment.contracts import (
    EpisodeRecord,
    EvidenceSnapshot,
    RlPolicyRef,
    RlTaskDef,
)
from workers.training.rl.environment.environment import ResearchRlEnvironment

from .contracts import RlRolloutSpec
from .pico_rl import PicoRlTokenizer
from .rollout_plan import (
    BudgetExhausted,
    RolloutScheduler,
    corpus_digest,
    enumerate_candidates,
    marker_text,
    render_observation,
)

__all__ = [
    "BudgetExhausted",
    "EpisodeRollout",
    "RolloutScheduler",
    "corpus_digest",
    "enumerate_candidates",
    "marker_text",
    "render_observation",
    "run_episode",
]


@dataclass
class EpisodeRollout:
    """One episode's completion + its trace record."""

    record: EpisodeRecord
    prompt_ids: list[int]
    completion_ids: list[int]
    logprobs: list[float]
    env_mask: list[int]


@torch.no_grad()  # type: ignore[untyped-decorator]
def _score_candidates(
    model: Any,
    prefix_ids: list[int],
    marker_ids: list[list[int]],
    device: torch.device,
) -> torch.Tensor:
    """Teacher-forced per-candidate scores: sum of marker-token logps
    conditioned on the running transcript prefix."""
    scores = []
    for ids in marker_ids:
        seq = torch.tensor([prefix_ids + ids], dtype=torch.long, device=device)
        logits = model(input_ids=seq).logits[0]
        # logits[t] predicts token t+1 — the marker occupies the tail.
        start = len(prefix_ids) - 1
        span = logits[start : start + len(ids)]
        logp = torch.log_softmax(span, dim=-1)
        tok = torch.tensor(ids, dtype=torch.long, device=device)
        scores.append(logp.gather(1, tok[:, None]).sum())
    return torch.stack(scores)


def run_episode(
    env: ResearchRlEnvironment,
    model: Any,
    tokenizer: PicoRlTokenizer,
    task: RlTaskDef,
    *,
    snapshot: EvidenceSnapshot,
    policy: RlPolicyRef,
    seed: int,
    spec: RlRolloutSpec,
    scheduler: RolloutScheduler,
    block_size: int,
) -> EpisodeRollout:
    """Drive ONE episode through the real environment; the sampled
    action markers + interleaved observations become the completion."""
    scheduler.admit()
    device = next(model.parameters()).device
    generator = torch.Generator(device="cpu").manual_seed(seed)
    obs = env.reset(task_id=task.task_id, seed=seed, evidence_snapshot=snapshot, policy=policy)

    prompt_text = render_observation(obs)
    prompt_ids = tokenizer.encode(prompt_text)[-spec.prompt_max_tokens :] or [0]
    transcript = list(prompt_ids)
    completion_ids: list[int] = []
    logprobs: list[float] = []
    env_mask: list[int] = []
    policy_tokens = len(prompt_ids)

    steps = 0
    max_actions = min(spec.max_episode_actions, task.budgets.max_steps if task.budgets else 16)
    while not obs.done and steps < max_actions:
        candidates = enumerate_candidates(obs, task, snapshot)[: spec.max_candidates]
        marker_ids = [tokenizer.encode(marker_text(i)) for i in range(len(candidates))]
        # Clamp the scoring prefix so prefix + longest marker fits the
        # block — the tail of a long transcript is still conditioned on.
        room = block_size - max(len(m) for m in marker_ids)
        prefix = transcript[-room:] if len(transcript) > room else transcript
        scores = _score_candidates(model, prefix, marker_ids, device)
        policy_tokens += sum(len(prefix) + len(m) for m in marker_ids)
        probs = torch.softmax(scores, dim=-1)
        choice = int(torch.multinomial(probs, 1, generator=generator).item())
        chosen = marker_ids[choice]
        if len(completion_ids) + len(chosen) > spec.completion_max_tokens:
            break

        # The marker tokens carry the SAMPLING logprobs; the
        # observation render follows masked (env feedback).
        marker_logps = _marker_token_logps(model, prefix, chosen, device)
        completion_ids.extend(chosen)
        logprobs.extend(marker_logps)
        env_mask.extend([1] * len(chosen))
        transcript.extend(chosen)
        policy_tokens += len(chosen)

        step = env.step(candidates[choice])
        obs = step.observation
        steps += 1
        obs_room = spec.completion_max_tokens - len(completion_ids)
        if obs_room <= 0:
            break
        obs_ids = tokenizer.encode(render_observation(obs))[:obs_room]
        completion_ids.extend(obs_ids)
        logprobs.extend([0.0] * len(obs_ids))
        env_mask.extend([0] * len(obs_ids))
        transcript.extend(obs_ids)
    record = env.terminate("driver_end")
    scheduler.charge(record, policy_tokens=policy_tokens)
    return EpisodeRollout(
        record=record,
        prompt_ids=prompt_ids,
        completion_ids=completion_ids[: spec.completion_max_tokens],
        logprobs=logprobs[: spec.completion_max_tokens],
        env_mask=env_mask[: spec.completion_max_tokens],
    )


@torch.no_grad()  # type: ignore[untyped-decorator]
def _marker_token_logps(
    model: Any,
    prefix: list[int],
    marker_ids: list[int],
    device: torch.device,
) -> list[float]:
    seq = torch.tensor([prefix + marker_ids], dtype=torch.long, device=device)
    logits = model(input_ids=seq).logits[0]
    start = len(prefix) - 1
    span = logits[start : start + len(marker_ids)]
    logp = torch.log_softmax(span, dim=-1)
    tok = torch.tensor(marker_ids, dtype=torch.long, device=device)
    return cast(list[float], logp.gather(1, tok[:, None]).squeeze(1).tolist())
