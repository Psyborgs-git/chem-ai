"""Tiny real SFT trainer — torch + PEFT LoRA on the local pico base.

Runs only inside the pinned ``workers/training/sft`` environment
(``--network none``, read-only root, non-root, bounded resources). The
host passes a complete ``SftTrainSpec`` plus the approved dataset bytes;
this module updates real weights, writes telemetry + checkpoints into
the scratch dir, and returns an honest ``SftOutcome``.

Rendering / masking (§17.3 "mask loss on input context"): each example
is rendered as
    context: task=<id> session=<id>
    <role>: <content>
    tool_call <name>: <json args>
    tool_result <name>: <content>
    response:
    <reviewed response>
Loss applies ONLY to tokens after the ``response:\n`` marker; context,
messages, tool calls and results are visible but never supervised.
Only ``train``-partition examples enter the loss; ``development`` feeds
eval-loss telemetry; ``calibration``/``final`` are never read for
updates — the held-out set stays untouched (§17.2).
"""

from __future__ import annotations

import json
import math
import shutil
import time
from pathlib import Path
from typing import Any

from engine_adapter_sft.contracts import (
    BASE_ARCHITECTURES,
    SftCheckpoint,
    SftOutcome,
    SftParameterProof,
    SftTrainingExample,
    SftTrainSpec,
    TrainerFailure,
    sha256_bytes,
)

TELEMETRY_FILE = "train.jsonl"
FINAL_ADAPTER_DIR = "adapter"
CHECKPOINT_PREFIX = "ckpt-"
RESPONSE_MARKER = "\nresponse:\n"


def render_example(example: SftTrainingExample) -> tuple[str, str]:
    """(context_text, response_text) — the mask boundary is explicit."""
    lines = [
        f"context: task={example.context.task_id or 'none'} "
        f"session={example.context.session_id or 'none'}"
    ]
    for message in example.messages:
        lines.append(f"{message.role}: {message.content}")
    for call in example.tool_calls:
        lines.append(f"tool_call {call.name}: {json.dumps(call.arguments, sort_keys=True)}")
    for result in example.tool_results:
        lines.append(f"tool_result {result.name}: {result.content}")
    return "\n".join(lines) + RESPONSE_MARKER, example.response.content


def _encode_dataset(
    examples: list[SftTrainingExample], tokenizer: Any, seq_length: int
) -> tuple[list[tuple[list[int], list[int]]], int]:
    """Tokenize + mask. Returns (pairs, skipped_too_short)."""
    pairs: list[tuple[list[int], list[int]]] = []
    skipped = 0
    for example in examples:
        context_text, response_text = render_example(example)
        context_ids = tokenizer.encode(context_text)
        response_ids = tokenizer.encode(response_text)
        ids = (context_ids + response_ids)[:seq_length]
        mask_len = min(len(context_ids), len(ids))
        if len(ids) - mask_len < 2:
            skipped += 1
            continue
        labels = [-100] * mask_len + ids[mask_len:]
        pad = seq_length - len(ids)
        ids = ids + [tokenizer.pad_id] * pad
        labels = labels + [-100] * pad
        pairs.append((ids, labels))
    return pairs, skipped


def _mean_eval_loss(model: Any, pairs: list[tuple[list[int], list[int]]]) -> float | None:
    import torch

    if not pairs:
        return None
    model.eval()
    total = 0.0
    count = 0
    with torch.no_grad():
        for ids, labels in pairs:
            x = torch.tensor([ids], dtype=torch.long)
            y = torch.tensor([labels], dtype=torch.long)
            _, loss = model(input_ids=x, labels=y)
            if loss is not None and math.isfinite(loss.item()):
                total += float(loss.item())
                count += 1
    model.train()
    return total / count if count else None


def _hash_names(model: Any, names: list[str]) -> str:
    from engine_adapter_sft.pico import state_dict_sha256

    return state_dict_sha256(model, names)


def _adapter_param_names(model: Any) -> list[str]:
    return sorted(name for name, p in model.named_parameters() if p.requires_grad)


def _frozen_param_names(model: Any) -> list[str]:
    return sorted(name for name, p in model.named_parameters() if not p.requires_grad)


def _save_checkpoint(
    model: Any,
    optimizer: Any,
    step: int,
    workdir: Path,
    spec: SftTrainSpec,
    lineage: list[dict[str, Any]],
) -> SftCheckpoint:
    ckpt_dir = workdir / f"{CHECKPOINT_PREFIX}{step:06d}"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(ckpt_dir))
    adapter_path = ckpt_dir / "adapter_model.safetensors"
    adapter_sha = sha256_bytes(adapter_path.read_bytes())
    import torch

    optim_path = ckpt_dir / "optimizer.pt"
    torch.save(optimizer.state_dict(), optim_path)
    meta = {
        "step": step,
        "configDigest": spec.digest(),
        "datasetDigest": spec.dataset_digest,
        "seed": spec.seed,
        "lineage": lineage,
    }
    (ckpt_dir / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    _relax(ckpt_dir)
    return SftCheckpoint(
        step=step,
        sha256=adapter_sha,
        artifact=str(ckpt_dir.relative_to(workdir)),
        optimizer_sha256=sha256_bytes(optim_path.read_bytes()),
    )


def _relax(path: Path) -> None:
    """safetensors writes mode 0600; the host harvester runs under a
    different uid — every persisted file must be world-readable."""
    for p in path.rglob("*") if path.is_dir() else [path]:
        if p.is_dir():
            p.chmod(0o755)
        elif p.is_file():
            p.chmod(0o644)


def _prune_checkpoints(workdir: Path, keep_last: int) -> None:
    dirs = sorted(
        (p for p in workdir.glob(f"{CHECKPOINT_PREFIX}*") if p.is_dir()),
        key=lambda p: int(p.name[len(CHECKPOINT_PREFIX) :]),
    )
    for stale in dirs[:-keep_last]:
        shutil.rmtree(stale, ignore_errors=True)


def _load_resume(model: Any, optimizer: Any, resume_dir: Path) -> tuple[int, dict[str, Any]]:
    """Restore adapter + optimizer state from a harvested checkpoint."""
    import torch
    from peft import set_peft_model_state_dict
    from safetensors.torch import load_file

    adapter_path = resume_dir / "adapter_model.safetensors"
    meta_path = resume_dir / "meta.json"
    optim_path = resume_dir / "optimizer.pt"
    if not adapter_path.is_file() or not meta_path.is_file():
        raise TrainerFailure(
            "RESUME_CHECKPOINT_INVALID",
            "resume checkpoint is missing adapter weights or meta.json",
        )
    meta = json.loads(meta_path.read_text())
    state = load_file(str(adapter_path))
    set_peft_model_state_dict(model, state, adapter_name="default")
    if optim_path.is_file():
        optimizer.load_state_dict(torch.load(optim_path, weights_only=True))
    return int(meta["step"]), meta


def train(request: dict[str, Any], workdir: Path) -> SftOutcome:
    """Execute one bounded SFT run; writes all artifacts under ``workdir``."""
    import torch
    from peft import LoraConfig, get_peft_model

    try:
        spec = SftTrainSpec.model_validate(request["spec"])
    except Exception as exc:
        raise TrainerFailure("ENGINE_UNSUPPORTED_INPUT", f"invalid train spec: {exc}") from exc

    raw_examples = request.get("dataset") or []
    if not raw_examples:
        raise TrainerFailure("DATASET_EMPTY", "no training examples were provided")
    examples: list[SftTrainingExample] = []
    for index, raw in enumerate(raw_examples):
        try:
            examples.append(SftTrainingExample.model_validate(raw))
        except Exception as exc:
            raise TrainerFailure(
                "DATASET_INVALID", f"example {index} failed the dataset contract: {exc}"
            ) from exc

    train_examples = [e for e in examples if e.partition == "train"]
    eval_examples = [e for e in examples if e.partition == "development"]
    if not train_examples:
        raise TrainerFailure(
            "DATASET_EMPTY", "no train-partition examples — held-out data is never trained on"
        )

    from engine_adapter_sft.pico import CharTokenizer, PicoGPT

    tokenizer = CharTokenizer()
    arch = BASE_ARCHITECTURES[spec.model.architecture]
    if tokenizer.vocab_size != int(arch["vocab_size"]):
        raise TrainerFailure(
            "ENGINE_UNSUPPORTED_INPUT",
            f"tokenizer vocab {tokenizer.vocab_size} != arch vocab {arch['vocab_size']}",
        )

    torch.manual_seed(int(spec.model.init_seed))
    base = PicoGPT(
        vocab_size=int(arch["vocab_size"]),
        n_embd=int(arch["n_embd"]),
        n_head=int(arch["n_head"]),
        n_layer=int(arch["n_layer"]),
        block_size=int(arch["block_size"]),
        tie_weights=bool(arch["tie_weights"]),
    )
    base_sha256 = _hash_names(base, sorted(n for n, _ in base.named_parameters()))

    lora = LoraConfig(
        r=spec.adapter.rank,
        lora_alpha=spec.adapter.alpha,
        lora_dropout=spec.adapter.dropout,
        target_modules=list(spec.adapter.target_modules),
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(base, lora)
    model.train()
    adapter_names = _adapter_param_names(model)
    frozen_names = _frozen_param_names(model)
    adapter_before = _hash_names(model, adapter_names)
    frozen_before = _hash_names(model, frozen_names)

    train_pairs, skipped_train = _encode_dataset(train_examples, tokenizer, spec.seq_length)
    eval_pairs, _ = _encode_dataset(eval_examples, tokenizer, spec.seq_length)
    if not train_pairs:
        raise TrainerFailure(
            "DATASET_EMPTY",
            f"all {len(train_examples)} train examples were empty after masking",
        )

    optimizer = torch.optim.AdamW(
        (p for p in model.parameters() if p.requires_grad),
        lr=spec.optimizer.learning_rate,
        weight_decay=spec.optimizer.weight_decay,
    )
    total = spec.max_steps

    def lr_scale(step: int) -> float:
        if spec.optimizer.scheduler == "constant":
            return 1.0
        warm = spec.optimizer.warmup_steps
        if step < warm:
            return (step + 1) / max(1, warm)
        return max(0.0, (total - step) / max(1, total - warm))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_scale)

    start_step = 0
    lineage: list[dict[str, Any]] = [{"event": "train_start", "configDigest": spec.digest()}]
    resume_from: dict[str, Any] | None = None
    if spec.resume is not None:
        resume_dir = workdir / "resume"
        start_step, meta = _load_resume(model, optimizer, resume_dir)
        if spec.resume.from_step != start_step:
            raise TrainerFailure(
                "RESUME_CHECKPOINT_INVALID",
                f"resume spec step {spec.resume.from_step} != checkpoint step {start_step}",
            )
        lineage = [
            *(meta.get("lineage") or lineage),
            {
                "event": "resume",
                "fromStep": start_step,
                "sourceRunId": spec.resume.source_run_id,
                "sourceAttemptId": spec.resume.source_attempt_id,
                "checkpointSha256": spec.resume.checkpoint_sha256,
            },
        ]
        resume_from = spec.resume.model_dump(mode="json")

    # Resolved config artifact — persisted before the first update.
    resolved = {
        "spec": spec.model_dump(mode="json"),
        "specDigest": spec.digest(),
        "baseModel": {
            "baseModelId": spec.model.base_model_id,
            "architecture": spec.model.architecture,
            "initSeed": spec.model.init_seed,
            "baseSha256": base_sha256,
            "licenseId": spec.model.license_id,
            "parameterCount": sum(p.numel() for p in base.parameters()),
        },
        "tokenizer": {"kind": "char-v1", "sha256": tokenizer.digest()},
        "dependencies": {
            "torch": torch.__version__,
            "peft": _dep_version("peft"),
        },
        "preprocessing": {
            "render": "context/messages/tool calls/response marker",
            "mask": "loss only after 'response:' marker; -100 elsewhere",
            "trainablePartitions": ["train"],
            "evalPartitions": ["development"],
            "skippedTooShort": skipped_train,
        },
        "telemetryFile": TELEMETRY_FILE,
    }
    (workdir / "config.json").write_text(json.dumps(resolved, indent=2, sort_keys=True))

    telemetry_path = workdir / TELEMETRY_FILE
    telemetry = telemetry_path.open("a", encoding="utf-8")
    rng = torch.Generator().manual_seed(int(spec.seed))
    checkpoints: list[SftCheckpoint] = []
    tail: list[dict[str, Any]] = []
    steps_completed = start_step
    final_train_loss: float | None = None
    final_eval_loss = _mean_eval_loss(model, eval_pairs)
    started = time.monotonic()

    def log_step(record: dict[str, Any]) -> None:
        telemetry.write(json.dumps(record, sort_keys=True) + "\n")
        telemetry.flush()
        tail.append(record)
        del tail[:-20]

    log_step(
        {
            "event": "train_start",
            "step": start_step,
            "trainExamples": len(train_pairs),
            "evalExamples": len(eval_pairs),
            "resumeFrom": resume_from,
        }
    )

    for step in range(start_step + 1, total + 1):
        order = torch.randperm(len(train_pairs), generator=rng).tolist()
        optimizer.zero_grad(set_to_none=True)
        step_loss = 0.0
        micro = 0
        # One deterministic pass per optimizer step, batched.
        for offset in range(0, len(order), spec.batch_size):
            batch_ids = order[offset : offset + spec.batch_size]
            xs = torch.tensor([train_pairs[i][0] for i in batch_ids], dtype=torch.long)
            ys = torch.tensor([train_pairs[i][1] for i in batch_ids], dtype=torch.long)
            _, loss = model(input_ids=xs, labels=ys)
            if loss is None or not math.isfinite(loss.item()):
                continue
            (loss / max(1, spec.grad_accumulation)).backward()
            step_loss += float(loss.item())
            micro += 1
            if micro % max(1, spec.grad_accumulation) == 0:
                break
        if micro == 0:
            raise TrainerFailure(
                "TRAINING_DIVERGED", "no finite loss at optimizer step — refusing to update"
            )
        torch.nn.utils.clip_grad_norm_(
            (p for p in model.parameters() if p.requires_grad),
            spec.optimizer.max_grad_norm,
        )
        optimizer.step()
        scheduler.step()
        steps_completed = step
        final_train_loss = step_loss / micro
        record: dict[str, Any] = {
            "event": "step",
            "step": step,
            "loss": round(final_train_loss, 6),
            "lr": optimizer.param_groups[0]["lr"],
            "wallSeconds": round(time.monotonic() - started, 3),
        }
        if step % spec.eval_every == 0 or step == total:
            final_eval_loss = _mean_eval_loss(model, eval_pairs)
            record["evalLoss"] = round(final_eval_loss, 6) if final_eval_loss is not None else None
        log_step(record)
        if step % spec.checkpoint.every_steps == 0:
            ckpt = _save_checkpoint(model, optimizer, step, workdir, spec, lineage)
            checkpoints.append(ckpt)
            _prune_checkpoints(workdir, spec.checkpoint.keep_last)

    # Final checkpoint + adapter artifact (kept even beyond keep_last).
    final_ckpt = _save_checkpoint(model, optimizer, steps_completed, workdir, spec, lineage)
    if not checkpoints or checkpoints[-1].step != steps_completed:
        checkpoints.append(final_ckpt)
        _prune_checkpoints(workdir, spec.checkpoint.keep_last)

    final_dir = workdir / FINAL_ADAPTER_DIR
    final_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(final_dir))
    adapter_path = final_dir / "adapter_model.safetensors"
    adapter_sha = sha256_bytes(adapter_path.read_bytes())
    (final_dir / "meta.json").write_text(
        json.dumps(
            {
                "finalStep": steps_completed,
                "configDigest": spec.digest(),
                "datasetDigest": spec.dataset_digest,
                "lineage": lineage,
            },
            indent=2,
            sort_keys=True,
        )
    )
    _relax(final_dir)

    adapter_after = _hash_names(model, adapter_names)
    frozen_after = _hash_names(model, frozen_names)

    # AT-0801-1 roundtrip: reload the persisted adapter file into a
    # fresh seeded base and verify the trained tensors land byte-equal.
    torch.manual_seed(int(spec.model.init_seed))
    reloaded_base = PicoGPT(
        vocab_size=int(arch["vocab_size"]),
        n_embd=int(arch["n_embd"]),
        n_head=int(arch["n_head"]),
        n_layer=int(arch["n_layer"]),
        block_size=int(arch["block_size"]),
        tie_weights=bool(arch["tie_weights"]),
    )
    reloaded = get_peft_model(reloaded_base, lora)
    from peft import set_peft_model_state_dict
    from safetensors.torch import load_file

    reloaded_state = load_file(str(adapter_path))
    set_peft_model_state_dict(reloaded, reloaded_state, adapter_name="default")
    reload_sha = _hash_names(reloaded, adapter_names)
    reload_matches = reload_sha == adapter_after

    proof = SftParameterProof(
        adapter_before_sha256=adapter_before,
        adapter_after_sha256=adapter_after,
        frozen_before_sha256=frozen_before,
        frozen_after_sha256=frozen_after,
        adapter_changed=adapter_before != adapter_after,
        frozen_changed=frozen_before != frozen_after,
        reload_sha256=reload_sha,
        reload_matches=reload_matches,
    )

    telemetry.close()
    outcome = SftOutcome(
        status="succeeded",
        usable=proof.adapter_changed and not proof.frozen_changed and reload_matches,
        classification="completed",
        base_model_id=spec.model.base_model_id,
        base_sha256=base_sha256,
        tokenizer_sha256=tokenizer.digest(),
        adapter_sha256=adapter_sha,
        config_digest=spec.digest(),
        steps_completed=steps_completed,
        train_examples=len(train_pairs),
        eval_examples=len(eval_pairs),
        final_train_loss=final_train_loss,
        final_eval_loss=final_eval_loss,
        parameter_proof=proof,
        checkpoints=checkpoints,
        telemetry_tail=tail,
        resume_from=resume_from,
        isolation={},
    )
    (workdir / "result.json").write_text(
        json.dumps(outcome.model_dump(mode="json"), indent=2, sort_keys=True)
    )
    return outcome


def _dep_version(name: str) -> str:
    try:
        import importlib.metadata

        return importlib.metadata.version(name)
    except Exception:
        return "unknown"


def capability() -> dict[str, Any]:
    try:
        import torch

        return {
            "backend": "local-pico",
            "modelIds": ["pico-gpt-char-v1"],
            "parameterCount": "pico (~0.9M)",
            "torch": torch.__version__,
            "peft": _dep_version("peft"),
            "isolation": ["network:none", "read_only_root", "non_root", "bounded"],
            "capabilityStatus": "fixture_only",
            "scientificStatus": "not_validated",
        }
    except Exception:
        return {"error": "ENGINE_UNAVAILABLE", "message": "trainer deps missing"}
