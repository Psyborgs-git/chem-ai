"""The RL trainer — real GRPO over the CS-0901 environment (§19.4).

Runs ONLY inside the pinned ``workers/training/rl/trainer`` image. The
host submits ``{"spec": RlTrainSpec, "corpus": {...}}``; the corpus is
re-validated against the REAL environment contracts here and its
canonical digest must equal the approval-bound ``spec.corpus_digest``
— the bytes the admission gate hashed are the bytes trained on.

Reward comes from CS-0901's ``RewardService.score_episode`` at the
frozen contract version, flowing into TRL through the rollout's
``extra_fields`` + a ``reward_funcs`` callable. Ineligible episodes
yield ``None`` (TRL maps them to NaN — honestly excluded from the
group baseline rather than silently zeroed).
"""

from __future__ import annotations

import json
import zlib
from pathlib import Path
from typing import Any

import torch
from workers.training.rl.environment.contracts import (
    ENV_CONTRACT_VERSION,
    REWARD_CONTRACT_VERSION,
)
from workers.training.rl.environment.environment import ResearchRlEnvironment
from workers.training.rl.rewards.service import RewardService

from .contracts import (
    RL_ARCHITECTURES,
    RlCheckpoint,
    RlEpisodeSummary,
    RlOutcome,
    RlParameterProof,
    RlTrainSpec,
    TrainerFailure,
)
from .pico_rl import PicoRLConfig, PicoRLForCausalLM, PicoRlTokenizer, state_dict_sha256
from .rollout import (
    BudgetExhausted,
    RolloutScheduler,
    corpus_digest,
    run_episode,
)


def capability() -> dict[str, Any]:
    """Honest engine capability — probed inside the pinned image."""
    return {
        "engine": "chem-studio-rl",
        "family": "grpo",
        "algorithm": "grpo/rollout_func",
        "adapter": "lora",
        "envContractVersion": ENV_CONTRACT_VERSION,
        "rewardContractVersion": REWARD_CONTRACT_VERSION,
        "labels": ["fixture_only", "not_validated"],
    }


def _write_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def _adapter_names(model: torch.nn.Module) -> list[str]:
    return [n for n, _ in model.named_parameters() if "lora_" in n]


def _frozen_names(model: torch.nn.Module) -> list[str]:
    return [n for n, _ in model.named_parameters() if "lora_" not in n]


def _file_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dep_version(name: str) -> str:
    try:
        import importlib.metadata

        return importlib.metadata.version(name)
    except Exception:
        return "unknown"


def train(request: dict[str, Any], output_dir: Path) -> RlOutcome:
    """Run one bounded RL job. ``request`` = {"spec", "corpus"}."""
    try:
        spec = RlTrainSpec.model_validate(request["spec"])
    except Exception as exc:
        raise TrainerFailure("ENGINE_UNSUPPORTED_INPUT", f"invalid spec: {exc}") from exc

    corpus = request.get("corpus") or {}
    try:
        from workers.training.rl.corpus import parse_corpus

        parsed_corpus = parse_corpus(corpus)
        tasks = parsed_corpus.tasks
        snapshot = parsed_corpus.snapshot
        policy = parsed_corpus.policy
    except TrainerFailure:
        raise
    except Exception as exc:
        raise TrainerFailure("ENGINE_UNSUPPORTED_INPUT", f"invalid corpus: {exc}") from exc
    if spec.reward_contract_version != REWARD_CONTRACT_VERSION:
        raise TrainerFailure(
            "ENGINE_UNSUPPORTED_INPUT",
            f"reward contract {spec.reward_contract_version} != pinned {REWARD_CONTRACT_VERSION}",
        )
    if (
        parsed_corpus.reward_contract_version != spec.reward_contract_version
        or parsed_corpus.env_contract_version != ENV_CONTRACT_VERSION
    ):
        raise TrainerFailure(
            "ENGINE_UNSUPPORTED_INPUT",
            "corpus contract versions do not match the pinned run versions",
        )
    if corpus_digest(tasks, snapshot, policy) != spec.corpus_digest:
        raise TrainerFailure(
            "ENGINE_UNSUPPORTED_INPUT",
            "corpus digest does not match the approval-bound spec",
        )

    from datasets import Dataset
    from peft import LoraConfig, PeftModel
    from transformers import TrainerCallback
    from trl import GRPOConfig, GRPOTrainer

    output_dir.mkdir(parents=True, exist_ok=True)
    episodes_dir = output_dir / "episodes"
    episodes_dir.mkdir(exist_ok=True)
    telemetry_path = output_dir / "train.jsonl"
    rewards_path = output_dir / "rewards.jsonl"

    # §17.4/§19.4 — the complete resolved config is persisted before a
    # single optimizer step runs (same convention as the SFT trainer).
    (output_dir / "config.json").write_text(
        json.dumps(
            {
                "spec": spec.model_dump(mode="json"),
                "deps": {
                    "torch": _dep_version("torch"),
                    "trl": _dep_version("trl"),
                    "peft": _dep_version("peft"),
                    "transformers": _dep_version("transformers"),
                },
                "contracts": {
                    "env": ENV_CONTRACT_VERSION,
                    "reward": REWARD_CONTRACT_VERSION,
                },
                "telemetryFile": "train.jsonl",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    torch.manual_seed(spec.model.init_seed)
    arch = RL_ARCHITECTURES[spec.model.architecture]
    tokenizer = PicoRlTokenizer()
    config = PicoRLConfig(
        vocab_size=tokenizer.vocab_size,
        n_embd=arch["n_embd"],
        n_head=arch["n_head"],
        n_layer=arch["n_layer"],
        block_size=arch["block_size"],
        tie_word_embeddings=bool(arch["tie_weights"]),
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
    )
    model = PicoRLForCausalLM(config)
    if tokenizer.pad_token_id is not None:
        model.config.pad_token_id = tokenizer.pad_token_id
        model.generation_config.pad_token_id = tokenizer.pad_token_id

    reward_service = RewardService(reward_contract_version=spec.reward_contract_version)
    scheduler = RolloutScheduler(spec.rollout_budget)
    task_map = {t.task_id: t for t in tasks}
    episode_counter: dict[str, int] = {}
    episode_rows: list[RlEpisodeSummary] = []
    reward_scalars: list[float] = []

    def rollout_func(prompts: list[Any], trainer: Any) -> dict[str, Any]:
        """TRL seam: one row = one episode; rows arrive already
        num_generations-duplicated by the RepeatSampler, so every
        prompt group is a same-task GRPO group."""
        out: dict[str, Any] = {
            "prompt_ids": [],
            "completion_ids": [],
            "logprobs": [],
            "env_mask": [],
            "reward_scalar": [],
        }
        for raw in prompts:
            task_id = raw if isinstance(raw, str) else str(raw)
            task = task_map.get(task_id)
            if task is None:
                raise TrainerFailure(
                    "ENGINE_UNSUPPORTED_INPUT", f"row names unknown task {task_id!r}"
                )
            n = episode_counter.get(task_id, 0)
            episode_counter[task_id] = n + 1
            seed = (
                spec.seed * 1_000_003 + zlib.crc32(task_id.encode("utf-8")) % 1_000_003 + n * 977
            ) % (2**31)
            env = ResearchRlEnvironment(
                tasks=tasks,
                reward_contract_version=spec.reward_contract_version,
            )
            rollout = run_episode(
                env,
                trainer.model,
                tokenizer,
                task,
                snapshot=snapshot,
                policy=policy,
                seed=seed,
                spec=spec.rollout,
                scheduler=scheduler,
                block_size=arch["block_size"],
            )
            record = rollout.record
            ep_path = episodes_dir / f"ep{len(episode_rows):04d}.json"
            ep_path.write_text(
                json.dumps(record.model_dump(mode="json"), sort_keys=True),
                encoding="utf-8",
            )
            reward = reward_service.score_episode(record, task=task, snapshot=snapshot)
            _write_jsonl(
                rewards_path,
                {
                    "episode": reward.episode_id,
                    "task": reward.task_id,
                    "rewardContractVersion": reward.reward_contract_version,
                    "envContractVersion": reward.env_contract_version,
                    "eligible": reward.eligible,
                    "scalar": reward.scalar,
                    "taskCompleted": reward.task_completed,
                    "gates": [g.model_dump(mode="json") for g in reward.gates],
                    "components": [c.model_dump(mode="json") for c in reward.components],
                    "labels": dict(reward.labels),
                },
            )
            reward_scalars.append(float(reward.scalar or 0.0))
            episode_rows.append(
                RlEpisodeSummary(
                    episode_id=record.episode_id,
                    task_id=task.task_id,
                    seed=seed,
                    eligible=reward.eligible,
                    scalar=reward.scalar,
                    task_completed=reward.task_completed,
                    outcome_reason=record.outcome.reason if record.outcome else None,
                    steps=len(record.steps),
                    tool_calls=record.totals.tool_calls,
                    compute_units=record.totals.compute_units,
                    policy_tokens=record.totals.policy_tokens,
                    artifact=str(ep_path.relative_to(output_dir)),
                )
            )
            out["prompt_ids"].append(rollout.prompt_ids)
            out["completion_ids"].append(rollout.completion_ids)
            out["logprobs"].append(rollout.logprobs)
            out["env_mask"].append(rollout.env_mask)
            # None (ineligible) → TRL maps to NaN: honestly excluded
            # from the group baseline rather than silently zeroed.
            out["reward_scalar"].append(reward.scalar)
        return out

    def reward_fn(**kwargs: Any) -> list[float | None]:
        return list(kwargs.get("reward_scalar") or [])

    rows_per_step = spec.algorithm.num_generations * spec.algorithm.tasks_per_batch
    total_rows = (spec.max_steps + 1) * spec.algorithm.tasks_per_batch
    ds = Dataset.from_dict({"prompt": [tasks[i % len(tasks)].task_id for i in range(total_rows)]})

    checkpoints: list[RlCheckpoint] = []

    class _HarvestCallback(TrainerCallback):  # type: ignore[misc]
        """Persists checkpoint metadata + mirrors trainer logs into
        train.jsonl — real telemetry only, never fabricated."""

        def on_save(self, args: Any, state: Any, control: Any, **kw: Any) -> None:
            for path in sorted(Path(args.output_dir).glob("checkpoint-*")):
                meta = path / "meta.json"
                if meta.exists():
                    continue
                adapter = path / "adapter_model.safetensors"
                sha = _file_sha256(adapter) if adapter.exists() else None
                meta.write_text(
                    json.dumps(
                        {
                            "step": state.global_step,
                            "configDigest": spec.digest(),
                            "adapterSha256": sha,
                        },
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
                if adapter.exists():
                    opt = path / "optimizer.pt"
                    checkpoints.append(
                        RlCheckpoint(
                            step=state.global_step,
                            sha256=sha or "",
                            # scratch-relative dir — the domain's harvest
                            # uses it as the artifact-key prefix
                            artifact=str(path.relative_to(output_dir)),
                            optimizer_sha256=_file_sha256(opt) if opt.exists() else None,
                        )
                    )

        def on_log(self, args: Any, state: Any, control: Any, **kw: Any) -> None:
            if state.log_history:
                _write_jsonl(telemetry_path, {"step": state.global_step, **state.log_history[-1]})

    peft_cfg = LoraConfig(
        r=spec.adapter.rank,
        lora_alpha=spec.adapter.alpha,
        lora_dropout=spec.adapter.dropout,
        target_modules=list(spec.adapter.target_modules),
        task_type="CAUSAL_LM",
    )
    grpo_args = GRPOConfig(
        output_dir=str(output_dir / "hf"),
        per_device_train_batch_size=rows_per_step,
        gradient_accumulation_steps=1,
        steps_per_generation=1,
        num_iterations=1,
        num_generations=spec.algorithm.num_generations,
        max_steps=spec.max_steps,
        learning_rate=spec.optimizer.learning_rate,
        lr_scheduler_type=spec.optimizer.scheduler,
        warmup_steps=spec.optimizer.warmup_steps,
        weight_decay=spec.optimizer.weight_decay,
        max_grad_norm=spec.optimizer.max_grad_norm,
        optim="adamw_torch",
        beta=spec.algorithm.beta,
        epsilon=spec.algorithm.epsilon,
        epsilon_high=spec.algorithm.epsilon_high,
        scale_rewards=spec.algorithm.scale_rewards,
        loss_type=spec.algorithm.loss_type,
        temperature=spec.algorithm.temperature,
        importance_sampling_level=spec.algorithm.importance_sampling_level,
        logging_steps=1,
        save_strategy="steps",
        save_steps=spec.checkpoint.every_steps,
        save_total_limit=spec.checkpoint.keep_last,
        report_to=[],
        use_cpu=True,
        bf16=False,
        fp16=False,
        seed=spec.seed,
        data_seed=spec.seed,
        dataloader_num_workers=0,
        remove_unused_columns=False,
        disable_tqdm=True,
        # The pico backbone is tiny — GC is pure overhead on CPU.
        gradient_checkpointing=False,
    )
    trainer = GRPOTrainer(
        model=model,
        args=grpo_args,
        processing_class=tokenizer,
        reward_funcs=[reward_fn],
        rollout_func=rollout_func,
        peft_config=peft_cfg,
        train_dataset=ds,
        callbacks=[_HarvestCallback()],
    )
    adapter_names = _adapter_names(trainer.model)
    frozen_names = _frozen_names(trainer.model)
    adapter_before = state_dict_sha256(trainer.model, adapter_names)
    frozen_before = state_dict_sha256(trainer.model, frozen_names)

    resume_path: Path | None = None
    if spec.resume is not None:
        resume_dir = Path("resume")
        if not resume_dir.is_dir():
            raise TrainerFailure(
                "ENGINE_UNSUPPORTED_INPUT",
                "resume declared but no checkpoint files were provisioned",
            )
        resume_path = resume_dir

    error: dict[str, Any] | None = None
    status = "succeeded"
    try:
        trainer.train(resume_from_checkpoint=str(resume_path) if resume_path else None)
    except BudgetExhausted as exc:
        status = "budget_exhausted"
        error = {"code": exc.code, "message": exc.message}
    except TrainerFailure:
        raise
    except Exception as exc:
        raise TrainerFailure(
            "ENGINE_UNAVAILABLE", f"trainer aborted: {type(exc).__name__}"
        ) from exc

    # ---- harvest + parameter proof (AT-0902-1) --------------------
    adapter_dir = output_dir / "adapter"
    adapter_dir.mkdir(exist_ok=True)
    trainer.save_model(str(adapter_dir))
    adapter_file = adapter_dir / "adapter_model.safetensors"
    adapter_sha = _file_sha256(adapter_file) if adapter_file.exists() else None

    adapter_after = state_dict_sha256(trainer.model, adapter_names)
    frozen_after = state_dict_sha256(trainer.model, frozen_names)
    reload_sha: str | None = None
    reload_matches = False
    if adapter_file.exists():
        # A real load: fresh base + saved adapter file → re-hash the
        # adapter tensors — the checkpoint roundtrip the AT requires.
        torch.manual_seed(spec.model.init_seed)
        fresh = PicoRLForCausalLM(config)
        loaded = PeftModel.from_pretrained(fresh, str(adapter_dir))
        reload_sha = state_dict_sha256(loaded, _adapter_names(loaded))
        reload_matches = reload_sha == adapter_after

    half = max(1, len(reward_scalars) // 2)
    first_mean = sum(reward_scalars[:half]) / half if reward_scalars else None
    last_mean = sum(reward_scalars[-half:]) / half if reward_scalars else None
    telemetry_tail: list[dict[str, Any]] = []
    if telemetry_path.exists():
        for line in telemetry_path.read_text(encoding="utf-8").splitlines()[-20:]:
            try:
                telemetry_tail.append(json.loads(line))
            except ValueError:
                continue

    classification = (
        "completed"
        if status == "succeeded"
        else "budget_exhausted"
        if status == "budget_exhausted"
        else "incomplete_run"
    )
    outcome = RlOutcome(
        status=status,
        usable=status == "succeeded" and adapter_sha is not None,
        classification=classification,
        base_model_id=spec.model.base_model_id,
        base_sha256=state_dict_sha256(model, _frozen_names(model)),
        tokenizer_sha256=tokenizer.digest(),
        adapter_sha256=adapter_sha,
        config_digest=spec.digest(),
        corpus_digest=spec.corpus_digest,
        optimizer_steps=trainer.state.global_step,
        episodes_completed=len(episode_rows),
        reward_first_mean=first_mean,
        reward_last_mean=last_mean,
        budget=scheduler.snapshot(),
        episodes=episode_rows,
        parameter_proof=RlParameterProof(
            adapter_before_sha256=adapter_before,
            adapter_after_sha256=adapter_after,
            frozen_before_sha256=frozen_before,
            frozen_after_sha256=frozen_after,
            adapter_changed=adapter_after != adapter_before,
            frozen_changed=frozen_after != frozen_before,
            reload_sha256=reload_sha,
            reload_matches=reload_matches,
        ),
        checkpoints=checkpoints,
        telemetry_tail=telemetry_tail,
        resume_from=spec.resume.model_dump(mode="json") if spec.resume else None,
        error=error,
        scientific_status="not_validated",
        isolation={"backend": "container", "network": "none"},
    )
    # Same convention as SFT: the committed result lands in the scratch
    # dir so the host harvests the byte-faithful outcome itself.
    (output_dir / "result.json").write_text(
        json.dumps(outcome.model_dump(mode="json"), sort_keys=True),
        encoding="utf-8",
    )
    return outcome
