"""Real training worker. Optional science dependencies are imported only per job.

The host passes a private JSON request file, never credentials. Model code is
never downloaded/executed during training; assets are loaded locally without
``trust_remote_code``. Each invocation writes events and a result atomically.
"""

from __future__ import annotations

import fnmatch
import gc
import hashlib
import json
import math
import numbers
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast


def emit(directory: Path, event: str, **data: Any) -> None:
    payload = {"event": event, "at": time.time(), **data}
    invalid = _non_finite_paths(payload)
    if invalid:
        raise ValueError(
            f"Non-finite numeric metric in {event} at {', '.join(invalid[:5])}; "
            "training stopped instead of persisting invalid metrics"
        )
    encoded = json.dumps(payload, default=str, allow_nan=False)
    with (directory / "events.jsonl").open("a") as handle:
        handle.write(encoded + "\n")
        handle.flush()


def _non_finite_paths(value: Any, path: str = "") -> list[str]:
    if isinstance(value, dict):
        return [
            item
            for key, child in value.items()
            for item in _non_finite_paths(child, f"{path}.{key}" if path else str(key))
        ]
    if isinstance(value, (tuple, list)):
        return [
            item
            for index, child in enumerate(value)
            for item in _non_finite_paths(child, f"{path}[{index}]")
        ]
    if isinstance(value, numbers.Number):
        try:
            return [] if math.isfinite(float(cast(Any, value))) else [path or "$"]
        except (ValueError, OverflowError, TypeError):
            return [path or "$"]
    return []


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def artifact_manifest(path: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": str(file.relative_to(path)),
            "bytes": file.stat().st_size,
            "sha256": sha256_file(file),
        }
        for file in sorted(path.rglob("*"))
        if file.is_file() and not file.is_symlink()
    ]


def _parts(request: dict[str, Any], partition: str) -> list[dict[str, Any]]:
    return [
        row
        for row in request.get("rows", [])
        if request.get("splits", {}).get(row["id"]) == partition
    ]


def _messages(row: dict[str, Any]) -> list[dict[str, Any]]:
    if row.get("messages"):
        return list(row["messages"])
    return [
        {"role": "user", "content": str(row["prompt"])},
        {"role": "assistant", "content": str(row["response"])},
    ]


def _mlx_training_records(
    request: dict[str, Any], directory: Path
) -> dict[str, list[dict[str, Any]]]:
    """Export only train/development; final answers never enter the training loader."""
    data = directory / "data"
    data.mkdir(exist_ok=True)
    partitions = {}
    for partition, filename in (("train", "train"), ("development", "valid")):
        records = [
            {"messages": _messages(row), **({"tools": row["tools"]} if row.get("tools") else {})}
            for row in _parts(request, partition)
            if row.get("messages") or (row.get("prompt") and row.get("response"))
        ]
        partitions[partition] = records
        (data / f"{filename}.jsonl").write_text(
            "\n".join(json.dumps(row) for row in records) + "\n"
        )
    return partitions


def _validate_mlx_tokens(partitions: dict[str, Any], max_tokens: int, directory: Path) -> None:
    """Inspect every cached token/offset pair before MLX can truncate or optimize."""
    summary = []
    failures: list[str] = []
    for partition, dataset in partitions.items():
        maximum = 0
        minimum_targets = None
        overlong = no_targets = 0
        for index in range(len(dataset)):
            tokens, offset = dataset[index]
            length = len(tokens)
            supervised = length - 1 - int(offset)
            maximum = max(maximum, length)
            minimum_targets = (
                supervised if minimum_targets is None else min(minimum_targets, supervised)
            )
            if length > max_tokens:
                overlong += 1
                if len(failures) < 10:
                    failures.append(
                        f"{partition} row {index + 1}: {length} tokens "
                        f"exceeds maxTokens={max_tokens}"
                    )
            if int(offset) < 0 or int(offset) >= length - 1:
                no_targets += 1
                if len(failures) < 10:
                    failures.append(
                        f"{partition} row {index + 1}: prompt offset {offset} "
                        "leaves no supervised target tokens"
                    )
        if not len(dataset):
            failures.append(f"{partition} partition is empty")
        summary.append(
            {
                "partition": partition,
                "rows": len(dataset),
                "maxSequenceTokens": maximum,
                "minimumSupervisedTokens": minimum_targets,
                "overlongRows": overlong,
                "zeroTargetRows": no_targets,
            }
        )
    emit(
        directory,
        "tokenization_preflight",
        passed=not failures,
        maxTokens=max_tokens,
        partitions=summary,
    )
    if failures:
        raise ValueError(
            "MLX tokenization preflight failed before optimization: "
            + "; ".join(failures[:3])
            + ". Shorten examples or increase sequence length; "
            "targets are never silently truncated."
        )


def _mlx_train(request: dict[str, Any], directory: Path) -> dict[str, Any]:
    import mlx.core as mx
    import numpy as np
    from mlx.utils import tree_flatten
    from mlx_lm.lora import CONFIG_DEFAULTS, train_model
    from mlx_lm.tuner.datasets import CacheDataset, create_dataset
    from mlx_lm.utils import load

    config = request["config"]
    records = _mlx_training_records(request, directory)
    data = directory / "data"
    output = directory / "output"
    output.mkdir(exist_ok=True)
    previous = output / "adapters.safetensors"
    details = request["model"].get("details", {})
    source_adapter = Path(details.get("adapterPath", "")) / "adapters.safetensors"
    warm_start = (
        previous if previous.exists() else (source_adapter if source_adapter.exists() else None)
    )
    options = {
        **CONFIG_DEFAULTS,
        "model": details.get("baseLocation", request["model"]["location"]),
        "train": True,
        "data": str(data),
        "iters": config["maxSteps"],
        "batch_size": config["batchSize"],
        "num_layers": -1,
        "max_seq_length": config["maxTokens"],
        "seed": config["seed"],
        "learning_rate": config["learningRate"],
        "adapter_path": str(output),
        "save_every": min(config["saveEvery"], config["maxSteps"]),
        "steps_per_report": 1,
        "steps_per_eval": config["saveEvery"],
        "val_batches": -1,
        "mask_prompt": True,
        "trust_remote_code": False,
        "lora_parameters": {"rank": config["rank"], "dropout": 0.0, "scale": 20.0},
        "resume_adapter_file": str(warm_start) if warm_start else None,
    }
    args = SimpleNamespace(**options)
    np.random.seed(config["seed"])
    mx.random.seed(config["seed"])
    model, tokenizer = load(
        args.model, tokenizer_config={"trust_remote_code": False}, trust_remote_code=False
    )
    train = create_dataset(records["train"], tokenizer, args)
    valid = create_dataset(records["development"], tokenizer, args)
    _validate_mlx_tokens(
        {"train": CacheDataset(train), "development": CacheDataset(valid)},
        config["maxTokens"],
        directory,
    )

    class Progress:
        def on_train_loss_report(self, info: dict[str, Any]) -> None:
            emit(directory, "training_step", **info)

        def on_val_loss_report(self, info: dict[str, Any]) -> None:
            emit(directory, "validation", **info)

    train_model(args, model, train, valid, Progress())
    mx.eval(model.trainable_parameters())
    trainable_count = sum(value.size for _name, value in tree_flatten(model.trainable_parameters()))
    if not previous.is_file() or trainable_count == 0:
        raise ValueError("Training produced no adapter weights")
    return {
        "backend": "mlx",
        "adapterPath": str(output),
        "baseLocation": args.model,
        "stepsCompleted": config["maxSteps"],
        "trainableParameters": trainable_count,
        "resumeMode": "adapter_warm_start" if options["resume_adapter_file"] else None,
        "artifacts": artifact_manifest(output),
    }


def _hf_model(
    request: dict[str, Any], *, adapter: bool = True, trainable_adapter: bool = False
) -> tuple[Any, Any]:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model_info = request["model"]
    details = model_info.get("details", {})
    base = details.get("baseLocation", model_info["location"])
    tokenizer = AutoTokenizer.from_pretrained(base, local_files_only=True, trust_remote_code=False)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        base,
        local_files_only=True,
        trust_remote_code=False,
        use_safetensors=True,
        dtype=torch.float32,
    )
    if adapter and details.get("adapterPath"):
        from peft import PeftModel

        model = PeftModel.from_pretrained(
            model, details["adapterPath"], is_trainable=trainable_adapter
        )
    return model, tokenizer


def _transformers_train(request: dict[str, Any], directory: Path) -> dict[str, Any]:
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import TrainerCallback, set_seed
    from trl import DPOConfig, DPOTrainer, GRPOConfig, GRPOTrainer, SFTConfig, SFTTrainer

    config, kind = request["config"], request["kind"]
    set_seed(config["seed"])
    inherited_adapter = bool(request["model"].get("details", {}).get("adapterPath"))
    model, tokenizer = _hf_model(request, adapter=inherited_adapter, trainable_adapter=True)
    output = directory / "output"
    output.mkdir(exist_ok=True)
    rows = _parts(request, "train")
    valid = _parts(request, "development")
    device = config.get("device", "auto")
    if device not in {"auto", "cpu", "cuda", "mps"}:
        raise ValueError("Unsupported execution device")
    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA requested but unavailable")
    if device == "mps" and not torch.backends.mps.is_available():
        raise ValueError("MPS requested but unavailable")
    shared = {
        "output_dir": str(output),
        "max_steps": config["maxSteps"],
        "per_device_train_batch_size": config["batchSize"],
        "learning_rate": config["learningRate"],
        "logging_steps": 1,
        "save_steps": min(config["saveEvery"], config["maxSteps"]),
        "save_total_limit": 3,
        "report_to": "none",
        "seed": config["seed"],
        "bf16": False,
        "fp16": False,
        "use_cpu": device == "cpu",
        "dataloader_pin_memory": False,
        "save_safetensors": True,
    }
    lora = LoraConfig(
        r=config["rank"],
        lora_alpha=config["rank"] * 2,
        target_modules="all-linear",
        task_type="CAUSAL_LM",
        lora_dropout=0.0,
        bias="none",
    )

    class Progress(TrainerCallback):  # type: ignore[misc]
        def on_log(
            self, args: Any, state: Any, control: Any, logs: Any = None, **kwargs: Any
        ) -> None:
            emit(
                directory,
                "training_step",
                step=state.global_step,
                **{
                    key: value
                    for key, value in (logs or {}).items()
                    if isinstance(value, (int, float))
                },
            )

    common = {
        "model": model,
        "processing_class": tokenizer,
        "peft_config": None if inherited_adapter else lora,
        "callbacks": [Progress()],
    }
    if kind == "sft":
        train_data = Dataset.from_list(
            [
                {
                    "messages": _messages(row),
                    **({"tools": row["tools"]} if row.get("tools") else {}),
                }
                for row in rows
                if row.get("messages") or "response" in row
            ]
        )
        args = SFTConfig(**shared, max_length=config["maxTokens"], completion_only_loss=False)
        trainer = SFTTrainer(**common, args=args, train_dataset=train_data)
    elif kind == "dpo":
        train_data = Dataset.from_list(
            [
                {key: str(row[key]) for key in ("prompt", "chosen", "rejected")}
                for row in rows
                if "chosen" in row and "rejected" in row
            ]
        )
        trainer = DPOTrainer(
            **common,
            args=DPOConfig(**shared, max_length=config["maxTokens"]),
            train_dataset=train_data,
        )
    else:
        train_data = Dataset.from_list(
            [
                {"prompt": str(row["prompt"]), "expected": str(row["expected"])}
                for row in rows
                if "expected" in row
            ]
        )

        def grounded_reward(
            completions: list[Any], expected: list[str], **kwargs: Any
        ) -> list[float]:
            values = []
            for response, target in zip(completions, expected, strict=True):
                text = response if isinstance(response, str) else response[-1].get("content", "")
                values.append(float(text.strip().casefold() == target.strip().casefold()))
            return values

        generations = int(config.get("numGenerations", 2))
        shared["gradient_accumulation_steps"] = generations
        args = GRPOConfig(
            **shared,
            num_generations=generations,
            max_completion_length=config["maxTokens"],
            use_vllm=False,
            reward_weights=[1.0],
        )
        trainer = GRPOTrainer(
            **common, args=args, train_dataset=train_data, reward_funcs=grounded_reward
        )
    checkpoints = sorted(
        output.glob("checkpoint-*"), key=lambda path: int(path.name.rsplit("-", 1)[-1])
    )
    resume = str(checkpoints[-1]) if checkpoints else None
    outcome = trainer.train(resume_from_checkpoint=resume)
    trainer.save_model(str(output))
    tokenizer.save_pretrained(str(output))
    emit(directory, "saved", step=trainer.state.global_step)
    return {
        "backend": "transformers",
        "baseLocation": request["model"]
        .get("details", {})
        .get("baseLocation", request["model"]["location"]),
        "adapterPath": str(output),
        "stepsCompleted": trainer.state.global_step,
        "metrics": outcome.metrics,
        "developmentRows": len(valid),
        "resumeMode": "optimizer_checkpoint"
        if resume
        else ("adapter_warm_start" if inherited_adapter else None),
        "artifacts": artifact_manifest(output),
    }


def _load_generator(request: dict[str, Any], *, adapter: bool = True) -> Callable[..., str]:
    """Load one immutable base/candidate session for an entire inference pass."""
    backend = request["model"]["backend"]
    details = request["model"].get("details", {})
    if backend == "mlx":
        from mlx_lm import generate, load

        base = details.get("baseLocation", request["model"]["location"])
        model, tokenizer = load(
            base,
            adapter_path=details.get("adapterPath") if adapter else None,
            tokenizer_config={"trust_remote_code": False},
            trust_remote_code=False,
        )

        def mlx_generate(prompt: str, *, messages: Any = None, tools: Any = None) -> str:
            text = tokenizer.apply_chat_template(
                messages or [{"role": "user", "content": prompt}],
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
                tools=tools,
            )
            return str(
                generate(
                    model,
                    tokenizer,
                    prompt=text,
                    max_tokens=request["config"].get("maxTokens", 128),
                    verbose=False,
                )
            )

        return mlx_generate
    import torch

    model, tokenizer = _hf_model(request, adapter=adapter)
    model.eval()

    def hf_generate(prompt: str, *, messages: Any = None, tools: Any = None) -> str:
        text = tokenizer.apply_chat_template(
            messages or [{"role": "user", "content": prompt}],
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
            tools=tools,
        )
        inputs = tokenizer(text, return_tensors="pt").to(model.device)
        with torch.no_grad():
            output = model.generate(
                **inputs,
                max_new_tokens=request["config"].get("maxTokens", 128),
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
            )
        return str(
            tokenizer.decode(output[0, inputs["input_ids"].shape[-1] :], skip_special_tokens=True)
        )

    return hf_generate


def _generate(request: dict[str, Any], prompt: str, *, adapter: bool = True) -> str:
    from studio.domain.learning.workspace_runtime.evaluation import visible_answer

    return visible_answer(
        _load_generator(request, adapter=adapter)(
            prompt, messages=request.get("messages"), tools=request.get("tools")
        )
    )


def _evaluate(request: dict[str, Any], directory: Path) -> dict[str, Any]:
    from studio.domain.learning.workspace_runtime.evaluation import aggregate_checks, answer_checks

    final = _parts(request, "final")
    if not final:
        raise ValueError(
            "A final held-out partition is required for evaluation; add independent data groups"
        )
    examples = []
    tasks = []
    for row in final[:100]:
        messages = row.get("messages")
        if messages:
            expected_turn = messages[-1]
            expected = str(
                expected_turn.get("content") or json.dumps(expected_turn.get("tool_calls", []))
            )
            context = messages[:-1]
            prompt = ""
        else:
            expected = str(row.get("expected", row.get("response", "")))
            prompt = str(row.get("prompt", ""))
            context = None
        if not expected or (not prompt and not context):
            continue
        tasks.append((row, prompt, context))
        examples.append({"rowId": row["id"], "expected": expected})
    if not examples:
        raise ValueError(
            "Held-out rows require prompts and expected/response fields or complete conversations"
        )
    for adapter, name in ((False, "base"), (True, "candidate")):
        generate = _load_generator(request, adapter=adapter)
        for index, (row, prompt, context) in enumerate(tasks):
            answer = generate(prompt, messages=context, tools=row.get("tools"))
            item = examples[index]
            item[name] = answer
            item[name + "Exact"] = answer.strip().casefold() == item["expected"].strip().casefold()
            item[name + "Checks"] = answer_checks(answer, row)
            emit(
                directory,
                "evaluation_example",
                phase=name,
                completed=index + 1,
                total=len(examples),
            )
        del generate
        gc.collect()
        if request["model"]["backend"] == "mlx":
            import mlx.core as mx

            mx.clear_cache()
    output = directory / "output"
    output.mkdir(exist_ok=True)
    (output / "evaluation.json").write_text(json.dumps(examples, indent=2))
    return {
        "matchedExamples": len(examples),
        "baseExactMatch": sum(item["baseExact"] for item in examples) / len(examples),
        "candidateExactMatch": sum(item["candidateExact"] for item in examples) / len(examples),
        "metrics": {
            "base": aggregate_checks(examples, "baseChecks"),
            "candidate": aggregate_checks(examples, "candidateChecks"),
        },
        "partition": "final",
        "artifacts": artifact_manifest(output),
    }


def _chemprop(request: dict[str, Any], directory: Path) -> dict[str, Any]:
    from engine_adapter_chemprop import ChempropAdapter, PredictSpec, TrainSpec

    config = request["config"]
    property_task = config.get("propertyTask", "regression")
    scope = {
        "name": str(config.get("target", "property")),
        "unit": "1" if property_task == "classification" else str(config.get("unit", "1")),
        "method": str(config.get("method", "custom_dataset")),
    }
    spec = TrainSpec.model_validate(
        {
            "task_type": property_task,
            "device": config.get("device", "cpu"),
            "scope": scope,
            "context": {"source": "private_custom_dataset"},
            "rows": [
                {"row_id": row["id"], "smiles": row["smiles"], "label": row["target"]}
                for row in _parts(request, "train")
                if "target" in row and "smiles" in row
            ],
            "seed": config["seed"],
            "max_epochs": min(300, config["maxSteps"]),
            "ensemble_size": int(config.get("ensembleSize", 2)),
            "hidden_dim": int(config.get("hiddenDim", 64)),
            "depth": int(config.get("depth", 2)),
            "batch_size": config["batchSize"],
        }
    )
    adapter = ChempropAdapter()
    trained, files = adapter.train(spec)
    output = directory / "output"
    output.mkdir(exist_ok=True)
    for name, value in files.items():
        file = output / name
        if file.resolve().parent != output.resolve():
            raise ValueError("Unsafe model artifact name")
        file.write_bytes(value)
    (output / "train-spec.json").write_text(spec.model_dump_json())
    training = [row for row in _parts(request, "train") if "target" in row and "smiles" in row]
    training_mean = sum(float(row["target"]) for row in training) / len(training)
    baseline = {
        "strategy": "majority_class" if property_task == "classification" else "training_mean",
        "value": float(training_mean >= 0.5)
        if property_task == "classification"
        else training_mean,
        "unit": scope["unit"],
        "fitPartition": "train",
    }
    domain: dict[str, Any] = {
        "smiles": list(dict.fromkeys(str(row["smiles"]) for row in training)),
        "scope": scope,
        "conditions": [row["conditions"] for row in training if row.get("conditions")],
        "baseline": baseline,
    }
    (output / "applicability.json").write_text(json.dumps(domain))
    result: dict[str, Any] = {
        "backend": "chemprop",
        "learningRateSchedule": config.get(
            "learningRateSchedule",
            {
                "engine": "chemprop-2.3.1-default",
                "initial": 0.0001,
                "maximum": 0.001,
                "final": 0.0001,
                "warmupEpochs": 2,
            },
        ),
        "propertyTask": property_task,
        "modelDigest": trained.model_digest,
        "scope": scope,
        "trainResult": trained.model_dump(mode="json"),
        "trainingBaseline": baseline,
        "trainingConditions": list(
            {
                json.dumps(row["conditions"], sort_keys=True): row["conditions"]
                for row in training
                if row.get("conditions")
            }.values()
        ),
        "applicabilityDomain": {
            "artifact": "applicability.json",
            "trainingStructures": len(domain["smiles"]),
            "method": "Morgan1024_radius2_Tanimoto",
            "threshold": 0.25,
            "calibrated": False,
        },
    }
    final = [row for row in _parts(request, "final") if "target" in row and "smiles" in row][:512]
    if final:
        predicted = adapter.predict(
            PredictSpec.model_validate(
                {
                    "scope": scope,
                    "task_type": property_task,
                    "device": config.get("device", "cpu"),
                    "model_digest": trained.model_digest,
                    "rows": [{"row_id": row["id"], "smiles": row["smiles"]} for row in final],
                }
            ),
            files,
        )
        labels = {row["id"]: row["target"] for row in final}
        errors = [item.value - labels[item.row_id] for item in predicted.predictions]
        result["evaluation"] = (
            {
                "partition": "final",
                "rows": len(errors),
                "mae": sum(abs(x) for x in errors) / len(errors),
                "rmse": math.sqrt(sum(x * x for x in errors) / len(errors)),
            }
            if errors
            else {"rows": 0}
        )
        if property_task == "classification" and errors:
            from sklearn.metrics import roc_auc_score

            actual = [int(labels[item.row_id]) for item in predicted.predictions]
            probabilities = [item.value for item in predicted.predictions]
            result["evaluation"] = {
                "partition": "final",
                "rows": len(actual),
                "accuracy": sum(
                    int(p >= 0.5) == y for p, y in zip(probabilities, actual, strict=True)
                )
                / len(actual),
                "auroc": float(roc_auc_score(actual, probabilities))
                if len(set(actual)) == 2
                else None,
                "aurocUnavailableReason": None
                if len(set(actual)) == 2
                else "Held-out partition contains one class",
            }
        from studio.domain.learning.workspace_runtime.evaluation import (
            applicability,
            regression_metrics,
        )

        matched = [float(labels[item.row_id]) for item in predicted.predictions]
        if property_task == "classification":
            baseline_metrics = (
                {
                    "accuracy": sum(int(baseline["value"]) == value for value in matched)
                    / len(matched)
                }
                if matched
                else {}
            )
        else:
            baseline_metrics = (
                regression_metrics(matched, [float(baseline["value"])] * len(matched))
                if matched
                else {}
            )
        result["evaluation"]["baseline"] = baseline_metrics
        result["evaluation"]["baselineStrategy"] = baseline["strategy"]
        coverage = applicability(domain["smiles"], [row["smiles"] for row in final])
        result["evaluation"]["applicability"] = {
            "inDomain": sum(row["inDomain"] for row in coverage),
            "total": len(coverage),
            "calibrated": False,
        }
    result["artifacts"] = artifact_manifest(output)
    return result


def _predict(request: dict[str, Any], directory: Path) -> dict[str, Any]:
    from engine_adapter_chemprop import ChempropAdapter, PredictSpec

    details = request["model"]["details"]
    path = Path(request["model"]["location"])
    files = {
        item["path"]: (path / item["path"]).read_bytes()
        for item in details["artifacts"]
        if item["path"] == "manifest.json" or item["path"].endswith(".pt")
    }
    for name, value in files.items():
        if Path(name).name != name:
            raise ValueError("Unsafe Chemprop artifact filename")
        (directory / name).write_bytes(value)
    rows = _parts(request, "final") if request["kind"] == "evaluate" else request["rows"]
    rows = rows[:512]
    spec = PredictSpec.model_validate(
        {
            "scope": details["scope"],
            "task_type": details.get("propertyTask", "regression"),
            "device": request["config"].get("device", "cpu"),
            "model_digest": details["modelDigest"],
            "rows": [{"row_id": row["id"], "smiles": row["smiles"]} for row in rows],
        }
    )
    predicted = ChempropAdapter().predict(spec, files).model_dump(mode="json")
    from studio.domain.learning.workspace_runtime.evaluation import (
        applicability,
        regression_metrics,
    )

    domain_path = path / "applicability.json"
    if domain_path.is_file():
        domain = json.loads(domain_path.read_text())
    else:
        old_spec = json.loads((path / "train-spec.json").read_text())
        train = old_spec["rows"]
        mean = sum(float(row["label"]) for row in train) / len(train)
        domain = {
            "smiles": [row["smiles"] for row in train],
            "baseline": {"strategy": "training_mean", "value": mean},
        }
    coverage = applicability(domain["smiles"], [row["smiles"] for row in rows])
    predicted["applicabilityDomain"] = {
        row["id"]: result for row, result in zip(rows, coverage, strict=True)
    }
    if request["kind"] != "evaluate":
        return predicted
    lookup = {row["id"]: row for row in rows}
    actual = [float(lookup[item["row_id"]]["target"]) for item in predicted["predictions"]]
    values = [float(item["value"]) for item in predicted["predictions"]]
    if not actual:
        raise ValueError("Property evaluation produced no matched predictions")
    baseline = domain["baseline"]
    metrics: dict[str, Any]
    if details.get("propertyTask") == "classification":
        from sklearn.metrics import roc_auc_score

        metrics = {
            "accuracy": sum(
                int(value >= 0.5) == label for value, label in zip(values, actual, strict=True)
            )
            / len(actual),
            "auroc": float(roc_auc_score(actual, values)) if len(set(actual)) == 2 else None,
        }
        base_value = int(float(baseline["value"]) >= 0.5)
        baseline_metrics = {"accuracy": sum(base_value == label for label in actual) / len(actual)}
    else:
        metrics = regression_metrics(actual, values)
        baseline_metrics = regression_metrics(actual, [float(baseline["value"])] * len(actual))
    output = directory / "output"
    output.mkdir(exist_ok=True)
    report = {
        "partition": "final",
        "matchedExamples": len(actual),
        "metrics": metrics,
        "baseline": baseline_metrics,
        "baselineStrategy": baseline["strategy"],
        "scope": details["scope"],
        "predictions": predicted,
        "coverage": {
            "inDomain": sum(item["inDomain"] for item in coverage),
            "total": len(coverage),
            "calibrated": False,
        },
    }
    (output / "evaluation.json").write_text(json.dumps(report, indent=2))
    return {**report, "artifacts": artifact_manifest(output), "scientificStatus": "not_validated"}


def _reinvent(request: dict[str, Any], directory: Path) -> dict[str, Any]:
    config = request["config"]
    prior = request["model"]["location"]
    output = directory / "output"
    output.mkdir(exist_ok=True)
    train_path, valid_path = directory / "train.smi", directory / "valid.smi"
    train_path.write_text(
        "\n".join(row["smiles"] for row in _parts(request, "train") if "smiles" in row) + "\n"
    )
    valid_path.write_text(
        "\n".join(row["smiles"] for row in _parts(request, "development") if "smiles" in row) + "\n"
    )
    device = config.get("device", "cpu")
    if device not in {"cpu", "cuda", "cuda:0", "mps", "auto"}:
        raise ValueError("Unsupported device")
    if device == "auto":
        import torch

        device = (
            "cuda"
            if torch.cuda.is_available()
            else ("mps" if torch.backends.mps.is_available() else "cpu")
        )
    if device in {"cuda", "cuda:0", "mps"}:
        import torch

        if device.startswith("cuda") and not torch.cuda.is_available():
            raise ValueError("CUDA was selected but is unavailable")
        if device == "mps" and not torch.backends.mps.is_available():
            raise ValueError("MPS was selected but is unavailable")
    quote = json.dumps
    header = (
        f"device = {quote(device)}\n"
        f"json_out_config = {quote(str(output / 'resolved-config.json'))}\n"
    )
    if request["kind"] == "molecular_transfer":
        final_path = output / "trained.model"
        transfer_input = str(final_path) if final_path.exists() else prior
        text = 'run_type = "transfer_learning"\n' + header + "\n[parameters]\n"
        text += (
            f"input_model_file = {quote(transfer_input)}\n"
            f"smiles_file = {quote(str(train_path))}\n"
            f"output_model_file = {quote(str(final_path))}\n"
        )
        if valid_path.stat().st_size > 1:
            text += f"validation_smiles_file = {quote(str(valid_path))}\n"
        text += (
            f"num_epochs = {min(config['maxSteps'], 1000)}\n"
            f"save_every_n_epochs = {config['saveEvery']}\n"
            f"batch_size = {config['batchSize']}\nnum_refs = 0\nsample_batch_size = 16\n"
        )
    else:
        final_path = output / "trained.chkpt"
        prior_checkpoint = final_path if final_path.exists() else Path(prior)
        component = {"qed": "QED", "molecular_weight": "MolecularWeight", "logp": "Slogp"}[
            config.get("reward", "qed")
        ]
        text = 'run_type = "staged_learning"\n' + header + "\n[parameters]\n"
        text += (
            f"prior_file = {quote(prior)}\nagent_file = {quote(str(prior_checkpoint))}\n"
            f"summary_csv_prefix = {quote(str(output / 'scores'))}\n"
            f"batch_size = {max(2, config['batchSize'])}\nrandomize_smiles = true\n"
        )
        # Inception focuses the generative RL loop on the train partition only.
        text += (
            f"\n[inception]\nsmiles_file = {quote(str(train_path))}\n"
            "memory_size = 100\nsample_size = 2\n"
        )
        text += (
            f'\n[learning_strategy]\ntype = "dap"\nsigma = 128\nrate = {config["learningRate"]}\n'
        )
        text += (
            f"\n[[stage]]\nchkpt_file = {quote(str(final_path))}\n"
            'termination = "simple"\nmax_score = 1.0\nmin_steps = 1\n'
            f"max_steps = {config['maxSteps']}\n"
        )
        text += (
            '\n[stage.scoring]\ntype = "geometric_mean"\n[[stage.scoring.component]]\n'
            f"[stage.scoring.component.{component}]\n"
            f"[[stage.scoring.component.{component}.endpoint]]\n"
            'name = "Declared research objective"\nweight = 1.0\n'
        )
        if component != "QED":
            low, high = float(config.get("rewardMin", 200)), float(config.get("rewardMax", 500))
            if not math.isfinite(low) or not math.isfinite(high) or high <= low:
                raise ValueError("Molecular reward range must have finite increasing limits")
            text += (
                'transform.type = "double_sigmoid"\n'
                f"transform.low = {low}\ntransform.high = {high}\n"
                f"transform.coef_div = {max(1.0, high)}\n"
                "transform.coef_si = 20.0\ntransform.coef_se = 20.0\n"
            )
    config_path = directory / "reinvent.toml"
    config_path.write_text(text)
    emit(directory, "training_started", engine="reinvent", mode=request["kind"])
    subprocess.run(  # noqa: S603 — fixed REINVENT module, constrained generated TOML
        [sys.executable, "-m", "reinvent.Reinvent", str(config_path), "--device", device],
        cwd=directory,
        check=True,
        timeout=config["maxSeconds"],
    )
    if not final_path.exists():
        raise ValueError("REINVENT did not produce the declared model/checkpoint")
    return {
        "backend": "reinvent",
        "location": str(final_path),
        "objective": config.get("reward"),
        "stepsRequested": config["maxSteps"],
        "artifacts": artifact_manifest(output),
    }


def execute(request: dict[str, Any], directory: Path) -> dict[str, Any]:
    kind = request["kind"]
    emit(directory, "started", kind=kind, backend=request["config"]["backend"])
    if kind == "download_model":
        from huggingface_hub import HfApi, snapshot_download

        location = request["model"]["location"]
        config = request["config"]
        revision = config.get("revision")
        if (
            not isinstance(revision, str)
            or len(revision) != 40
            or any(character not in "0123456789abcdef" for character in revision)
        ):
            raise ValueError("Catalog model downloads require an immutable commit revision")
        info = HfApi(token=False).model_info(config["repo"], revision=revision, files_metadata=True)
        if info.sha != revision:
            raise ValueError("Model repository did not resolve to the pinned revision")
        patterns = [
            "*.json",
            "*.safetensors",
            "*.model",
            "*.txt",
            "*.tiktoken",
            "*.jinja",
            "LICENSE*",
            "README.md",
        ]
        remote_files = [
            item
            for item in info.siblings
            if any(fnmatch.fnmatch(item.rfilename, pattern) for pattern in patterns)
        ]
        if not any(item.rfilename.endswith(".safetensors") for item in remote_files):
            raise ValueError("The pinned model contains no safetensors weights")
        if any(
            Path(item.rfilename).is_absolute() or ".." in Path(item.rfilename).parts
            for item in remote_files
        ):
            raise ValueError("Model manifest contains an unsafe relative path")
        storage_path = Path(location)
        while not storage_path.exists() and storage_path != storage_path.parent:
            storage_path = storage_path.parent
        required = (
            int(sum(getattr(item, "size", 0) or 0 for item in remote_files) * 1.25) + 64 * 1024**2
        )
        if config.get("workflowId"):
            required += 5 * 1024**3
        if shutil.disk_usage(storage_path).free < required:
            raise ValueError(
                "Insufficient free disk space for the pinned model and storage reserve"
            )
        snapshot_download(
            repo_id=config["repo"],
            revision=revision,
            local_dir=location,
            allow_patterns=[item.rfilename for item in remote_files],
            token=False,
        )
        files = []
        for item in remote_files:
            path = Path(location) / item.rfilename
            sha = sha256_file(path)
            expected = getattr(item.lfs, "sha256", None) if item.lfs else None
            if expected and sha != expected:
                raise ValueError("Downloaded model failed its Hugging Face SHA-256 verification")
            files.append(
                {
                    "path": item.rfilename,
                    "bytes": path.stat().st_size,
                    "sha256": sha,
                    "hubSha256": expected,
                }
            )
        manifest = {
            "repo": config["repo"],
            "revision": revision,
            "license": config.get("license"),
            "files": files,
        }
        (Path(location) / "studio-model-manifest.json").write_text(json.dumps(manifest, indent=2))
        return {
            "downloaded": True,
            "location": location,
            "files": [item["path"] for item in files],
            "manifest": manifest,
        }
    if kind == "preview":
        return {
            "text": _generate(request, request["prompt"]),
            "backend": request["model"]["backend"],
        }
    if kind == "evaluate":
        if request["model"]["backend"] == "chemprop":
            return _predict(request, directory)
        return _evaluate(request, directory)
    if kind == "predict":
        return _predict(request, directory)
    if kind == "chemprop":
        result = _chemprop(request, directory)
    elif kind in {"molecular_transfer", "molecular_rl"}:
        result = _reinvent(request, directory)
    elif request["config"]["backend"] == "mlx":
        result = _mlx_train(request, directory)
    else:
        result = _transformers_train(request, directory)
    result["scientificStatus"] = "not_validated"
    result["isolation"] = {
        "backend": "native_subprocess",
        "networkDenied": False,
        "offlineModelLoading": True,
        "credentialEnvironment": "scrubbed",
    }
    return result


def main() -> int:
    directory = Path(sys.argv[1]).resolve()
    os.chdir(directory)
    os.umask(0o077)
    request = json.loads((directory / "request.json").read_text())
    try:
        result = {"ok": True, **execute(request, directory)}
        invalid = _non_finite_paths(result)
        if invalid:
            raise ValueError(
                "Worker result contains non-finite numeric values at " + ", ".join(invalid[:5])
            )
        encoded = json.dumps(result, default=str, allow_nan=False)
        emit(directory, "completed")
    except Exception as exc:
        # No traceback or example text enters the job response.
        message = str(exc)
        if isinstance(exc, ImportError):
            message = "Required training dependency is unavailable"
        result = {"ok": False, "error": f"{type(exc).__name__}: {message[:500]}"}
        emit(directory, "failed", error=result["error"])
        encoded = json.dumps(result, default=str, allow_nan=False)
    temporary = directory / "result.tmp"
    temporary.write_text(encoded)
    temporary.replace(directory / "result.json")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
