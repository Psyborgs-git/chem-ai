"""Quantum jobs require OS-enforced no-egress execution (§13.3).

The pinned image `chem-studio-qcengine:0.51.0-v1` carries xtb 6.7.1
(xtb-python 22.1) on QCEngine 0.51.0/QCElemental 0.51.2. Psi4 is not
bundled — its capability state stays `not_installed` until a tested
image ships. There is intentionally no subprocess fallback: chemistry
outputs only come from the bounded container.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from typing import Any

from engine_adapter_qcengine.contracts import (
    EngineFailure,
    QuantumJobSpec,
    QuantumOutcome,
    ResourceEnvelope,
)
from workers.common.executor import ContainerBackend, ExecLimits

IMAGE = "chem-studio-qcengine:0.51.0-v1"


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
    """Per-program §16.1 states, probed inside the pinned image itself."""
    if not available():
        return None
    result = ContainerBackend(IMAGE).run(
        ["python", "-m", "workers.chemistry.quantum.runner", "--capability"],
        inputs={},
        limits=ExecLimits(
            wall_seconds=60,
            cpu_seconds=60,
            memory_bytes=1024**3,
            max_processes=32,
            output_bytes=64 * 1024,
        ),
    )
    if result.exit_code != 0 or result.timed_out:
        return None
    return result.json_stdout()


class IsolatedQuantum:
    """Runs one validated job in the pinned no-egress container."""

    def compute(
        self,
        spec: QuantumJobSpec,
        *,
        payload: dict[str, Any],
        cancel: threading.Event | None = None,
    ) -> QuantumOutcome:
        if not available():
            raise EngineFailure("ENGINE_UNAVAILABLE", "pinned QCEngine worker image unavailable")
        inputs = json.dumps({"spec": spec.model_dump(mode="json"), "input": payload}).encode()
        resources: ResourceEnvelope = spec.resources
        result = ContainerBackend(IMAGE).run(
            ["python", "-m", "workers.chemistry.quantum.runner"],
            inputs={"request.json": inputs},
            limits=ExecLimits(
                wall_seconds=resources.wall_seconds,
                cpu_seconds=resources.wall_seconds,
                memory_bytes=resources.memory_mebibytes * 1024**2,
                max_processes=64,
                output_bytes=2 * 1024**2,
                file_bytes=64 * 1024**2,
            ),
            cancel=cancel,
        )
        output = result.json_stdout()
        if result.cancelled:
            raise EngineFailure("RUN_CANCELLED", "quantum run was cancelled")
        if result.timed_out:
            raise EngineFailure("RUN_TIMEOUT", "quantum run exceeded its wall clock")
        if result.truncated or not output or result.exit_code != 0:
            code = output.get("error", "ENGINE_UNAVAILABLE") if output else "ENGINE_UNAVAILABLE"
            raise EngineFailure(str(code), "isolated quantum request failed; no result committed")
        outcome = QuantumOutcome.model_validate(output)
        return outcome.model_copy(
            update={
                "isolation": {
                    "backend": result.profile.backend,
                    "enforced": result.profile.enforced,
                }
            }
        )
