"""Chemprop runs ONLY under the OS-enforced no-egress container
profile (CS-0604). The heavy torch stack stays out of the core
profile; the pinned worker image is probed, never assumed."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

from workers.common.executor import ContainerBackend, ExecLimits

from engine_adapter_chemprop.contracts import (
    EngineFailure,
    PredictResult,
    PredictSpec,
    TrainResult,
    TrainSpec,
)

IMAGE = "chem-studio-chemprop:2.3.1-v1"

_LIMITS = ExecLimits(
    wall_seconds=600,
    cpu_seconds=600,
    memory_bytes=6 * 1024**3,
    max_processes=256,
    output_bytes=2 * 1024**2,
    file_bytes=256 * 1024**2,
)


def available() -> bool:
    docker = shutil.which("docker")
    if not docker:
        return False
    try:
        return (
            subprocess.run(  # noqa: S603 — fixed image probe
                [docker, "image", "inspect", IMAGE], capture_output=True, timeout=5
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def _failure(result: Any, noun: str) -> EngineFailure:
    output = result.json_stdout()
    code = output.get("error", "ENGINE_UNAVAILABLE") if output else "ENGINE_UNAVAILABLE"
    return EngineFailure(str(code), f"isolated Chemprop {noun} failed; nothing was produced")


class IsolatedChemprop:
    def train(self, spec: TrainSpec) -> tuple[TrainResult, dict[str, bytes], dict[str, Any]]:
        """Run one bounded training request. Returns the validated
        result, the artifact files recovered from the run scratch, and
        the isolation profile that was actually enforced."""
        if not available():
            raise EngineFailure("ENGINE_UNAVAILABLE", "pinned Chemprop worker image unavailable")
        inputs = json.dumps({"operation": "train", "spec": spec.model_dump(mode="json")}).encode()
        result = ContainerBackend(IMAGE).run(
            [
                "python",
                "-m",
                "workers.optimization.property_models.chemprop.runner",
            ],
            inputs={"request.json": inputs},
            limits=_LIMITS,
        )
        output = result.json_stdout()
        if result.timed_out or result.truncated or not output or result.exit_code != 0:
            raise _failure(result, "train")
        trained = TrainResult.model_validate(output)
        files: dict[str, bytes] = {}
        for name in result.scratch_files:
            if name == "request.json" or name not in trained.model_files:
                continue
            with open(os.path.join(result.scratch_dir, name), "rb") as f:
                files[name] = f.read()
        if sorted(files) != trained.model_files:
            raise EngineFailure(
                "ENGINE_UNAVAILABLE", "worker artifact set does not match its manifest"
            )
        return (
            trained,
            files,
            {
                "backend": result.profile.backend,
                "enforced": result.profile.enforced,
            },
        )

    def predict(
        self, spec: PredictSpec, model_files: dict[str, bytes]
    ) -> tuple[PredictResult, dict[str, Any]]:
        """Score rows against the declared artifact set — the digest
        binds the exact ensemble and train spec."""
        if not available():
            raise EngineFailure("ENGINE_UNAVAILABLE", "pinned Chemprop worker image unavailable")
        inputs: dict[str, bytes] = {
            "request.json": json.dumps(
                {"operation": "predict", "spec": spec.model_dump(mode="json")}
            ).encode(),
            **model_files,
        }
        result = ContainerBackend(IMAGE).run(
            [
                "python",
                "-m",
                "workers.optimization.property_models.chemprop.runner",
            ],
            inputs=inputs,
            limits=_LIMITS,
        )
        output = result.json_stdout()
        if result.timed_out or result.truncated or not output or result.exit_code != 0:
            raise _failure(result, "predict")
        return PredictResult.model_validate(output), {
            "backend": result.profile.backend,
            "enforced": result.profile.enforced,
        }
