"""Retrosynthesis jobs require OS-enforced no-egress execution (§13.3).

The pinned image `chem-studio-aizynthfinder:4.4.1-v1` carries
aizynthfinder 4.4.1 (onnxruntime/rdkit stack) plus pydantic and the
licensed policy/template/stock files whose hashes are baked at build
time. There is intentionally no subprocess fallback: route outputs
only come from the bounded container.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from typing import Any

from engine_adapter_aizynthfinder.contracts import (
    EngineFailure,
    ResourceEnvelope,
    RouteJobSpec,
    RouteOutcome,
)
from workers.common.executor import ContainerBackend, ExecLimits

IMAGE = "chem-studio-aizynthfinder:4.4.1-v1"


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


def capability() -> dict[str, Any] | None:
    """§16.1 state probed inside the pinned image itself."""
    if not available():
        return None
    result = ContainerBackend(IMAGE).run(
        ["python", "-m", "workers.chemistry.synthesis.runner", "--capability"],
        inputs={},
        limits=ExecLimits(
            wall_seconds=120,
            cpu_seconds=120,
            memory_bytes=2048 * 1024**2,
            max_processes=64,
            output_bytes=64 * 1024,
        ),
    )
    if result.exit_code != 0 or result.timed_out:
        return None
    return result.json_stdout()


class IsolatedSynthesis:
    """Runs one validated job in the pinned no-egress container."""

    def compute(
        self,
        spec: RouteJobSpec,
        *,
        payload: dict[str, Any],
        cancel: threading.Event | None = None,
    ) -> RouteOutcome:
        if not available():
            raise EngineFailure(
                "ENGINE_UNAVAILABLE", "pinned aizynthfinder worker image unavailable"
            )
        inputs = json.dumps({"spec": spec.model_dump(mode="json"), "input": payload}).encode()
        resources: ResourceEnvelope = spec.resources
        result = ContainerBackend(IMAGE).run(
            ["python", "-m", "workers.chemistry.synthesis.runner"],
            inputs={"request.json": inputs},
            limits=ExecLimits(
                wall_seconds=resources.wall_seconds,
                cpu_seconds=resources.wall_seconds,
                memory_bytes=resources.memory_mebibytes * 1024**2,
                max_processes=128,
                output_bytes=4 * 1024**2,
                file_bytes=64 * 1024**2,
            ),
            cancel=cancel,
        )
        output = result.json_stdout()
        if result.cancelled:
            raise EngineFailure("RUN_CANCELLED", "synthesis run was cancelled")
        if result.timed_out:
            raise EngineFailure("RUN_TIMEOUT", "synthesis run exceeded its wall clock")
        if result.truncated or not output or result.exit_code != 0:
            code = output.get("error", "ENGINE_UNAVAILABLE") if output else "ENGINE_UNAVAILABLE"
            raise EngineFailure(str(code), "isolated synthesis request failed; no result committed")
        outcome = RouteOutcome.model_validate(output)
        return outcome.model_copy(
            update={
                "isolation": {
                    "backend": result.profile.backend,
                    "enforced": result.profile.enforced,
                }
            }
        )
