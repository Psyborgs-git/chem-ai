"""Real training worker. Optional science dependencies are imported only per job.

The host passes a private JSON request file, never credentials. Model code is
never downloaded/executed during training; assets are loaded locally without
``trust_remote_code``. Each invocation writes events and a result atomically.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def emit(directory: Path, event: str, **data: Any) -> None:
    with (directory / "events.jsonl").open("a") as handle:
        handle.write(json.dumps({"event": event, "at": time.time(), **data}, default=str) + "\n")
        handle.flush()


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


def _messages(row: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "user", "content": str(row["prompt"])},
        {"role": "assistant", "content": str(row["response"])},
    ]


def _mlx_train(request: dict[str, Any], directory: Path) -> dict[str, Any]:
    import mlx.core as mx
    import numpy as np
    from mlx.utils import tree_flatten
    from mlx_lm.lora import CONFIG_DEFAULTS, train_model
    from mlx_lm.tuner.datasets import load_dataset
    from mlx_lm.utils import load

    config = request["config"]
    data = directory / "data"
    data.mkdir(exist_ok=True)
    for partition, filename in [("train", "train"), ("development", "valid"), ("final", "test")]:
        records = [
            _messages(row)
            for row in _parts(request, partition)
            if row.get("prompt") and row.get("response")
        ]
        if records:
            (data / f"{filename}.jsonl").write_text(
                "\n".join(json.dumps({"messages": row}) for row in records) + "\n"
            )
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
    train, valid, _test = load_dataset(args, tokenizer)

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
            [{"messages": _messages(row)} for row in rows if "response" in row]
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


def _generate(request: dict[str, Any], prompt: str, *, adapter: bool = True) -> str:
    backend = request["model"]["backend"]
    details = request["model"].get("details", {})
    messages = request.get("messages") or [{"role": "user", "content": prompt}]
    tools = request.get("tools") or None
    if backend == "mlx":
        from mlx_lm import generate, load

        base = details.get("baseLocation", request["model"]["location"])
        model, tokenizer = load(
            base,
            adapter_path=details.get("adapterPath") if adapter else None,
            tokenizer_config={"trust_remote_code": False},
        )
        text = tokenizer.apply_chat_template(
            messages,
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
    import torch

    model, tokenizer = _hf_model(request, adapter=adapter)
    model.eval()
    try:
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
            tools=tools,
        )
    except ValueError:
        text = prompt
    inputs = tokenizer(text, return_tensors="pt")
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


def _evaluate(request: dict[str, Any], directory: Path) -> dict[str, Any]:
    final = _parts(request, "final")
    if not final:
        raise ValueError(
            "A final held-out partition is required for evaluation; add independent data groups"
        )
    examples = []
    for row in final[:100]:
        if not row.get("prompt"):
            continue
        expected = str(row.get("expected", row.get("response", "")))
        if not expected:
            continue
        base = _generate(request, str(row["prompt"]), adapter=False)
        candidate = _generate(request, str(row["prompt"]), adapter=True)
        examples.append(
            {
                "rowId": row["id"],
                "expected": expected,
                "base": base,
                "candidate": candidate,
                "baseExact": base.strip().casefold() == expected.strip().casefold(),
                "candidateExact": candidate.strip().casefold() == expected.strip().casefold(),
            }
        )
        emit(directory, "evaluation_example", completed=len(examples), total=min(100, len(final)))
    if not examples:
        raise ValueError("Held-out rows require prompt and expected/response fields")
    (directory / "output").mkdir(exist_ok=True)
    (directory / "output" / "evaluation.json").write_text(json.dumps(examples))
    return {
        "matchedExamples": len(examples),
        "baseExactMatch": sum(x["baseExact"] for x in examples) / len(examples),
        "candidateExactMatch": sum(x["candidateExact"] for x in examples) / len(examples),
        "partition": "final",
        "artifacts": artifact_manifest(directory / "output"),
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
    result: dict[str, Any] = {
        "backend": "chemprop",
        "propertyTask": property_task,
        "modelDigest": trained.model_digest,
        "scope": scope,
        "trainResult": trained.model_dump(mode="json"),
    }
    final = [row for row in _parts(request, "final") if "target" in row and "smiles" in row]
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
    result["artifacts"] = artifact_manifest(output)
    return result


def _predict(request: dict[str, Any], directory: Path) -> dict[str, Any]:
    from engine_adapter_chemprop import ChempropAdapter, PredictSpec

    details = request["model"]["details"]
    path = Path(request["model"]["location"])
    files = {
        item["path"]: (path / item["path"]).read_bytes()
        for item in details["artifacts"]
        if item["path"] != "train-spec.json"
    }
    for name, value in files.items():
        if Path(name).name != name:
            raise ValueError("Unsafe Chemprop artifact filename")
        (directory / name).write_bytes(value)
    spec = PredictSpec.model_validate(
        {
            "scope": details["scope"],
            "task_type": details.get("propertyTask", "regression"),
            "device": request["config"].get("device", "cpu"),
            "model_digest": details["modelDigest"],
            "rows": [
                {"row_id": row["id"], "smiles": row["smiles"]} for row in request["rows"][:512]
            ],
        }
    )
    return ChempropAdapter().predict(spec, files).model_dump(mode="json")


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
        from huggingface_hub import snapshot_download

        location = request["model"]["location"]
        snapshot_download(
            repo_id=request["config"]["repo"],
            local_dir=location,
            allow_patterns=[
                "*.json",
                "*.safetensors",
                "*.model",
                "*.txt",
                "*.tiktoken",
                "LICENSE*",
                "README.md",
            ],
        )
        return {
            "downloaded": True,
            "location": location,
            "files": [path.name for path in Path(location).glob("*.safetensors")],
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
        emit(directory, "completed")
    except Exception as exc:
        # No traceback or example text enters the job response.
        message = str(exc)
        if isinstance(exc, ImportError):
            message = "Required training dependency is unavailable"
        result = {"ok": False, "error": f"{type(exc).__name__}: {message[:500]}"}
        emit(directory, "failed", error=result["error"])
    temporary = directory / "result.tmp"
    temporary.write_text(json.dumps(result, default=str))
    temporary.replace(directory / "result.json")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
