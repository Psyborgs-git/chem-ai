"""Materials/thermodynamics jobs require OS-enforced no-egress execution (§13.3).

The pinned image `chem-studio-materials:0.6.1-v1` carries thermo 0.6.1
(with its chemicals/fluids/scipy/pandas pins) plus pydantic. There is
intentionally no subprocess fallback: chemistry outputs only come from
the bounded container.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from typing import Any

from engine_adapter_materials.contracts import (
    EngineFailure,
    MaterialsJobSpec,
    MaterialsOutcome,
    ResourceEnvelope,
)
from workers.common.executor import ContainerBackend, ExecLimits

IMAGE = "chem-studio-materials:0.6.1-v1"


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
        ["python", "-m", "workers.chemistry.materials.runner", "--capability"],
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


class IsolatedMaterials:
    """Runs one validated job in the pinned no-egress container."""

    def compute(
        self,
        spec: MaterialsJobSpec,
        *,
        payload: dict[str, Any],
        cancel: threading.Event | None = None,
    ) -> MaterialsOutcome:
        if not available():
            raise EngineFailure("ENGINE_UNAVAILABLE", "pinned thermo worker image unavailable")
        inputs = json.dumps({"spec": spec.model_dump(mode="json"), "input": payload}).encode()
        resources: ResourceEnvelope = spec.resources
        result = ContainerBackend(IMAGE).run(
            ["python", "-m", "workers.chemistry.materials.runner"],
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
            raise EngineFailure("RUN_CANCELLED", "materials run was cancelled")
        if result.timed_out:
            raise EngineFailure("RUN_TIMEOUT", "materials run exceeded its wall clock")
        if result.truncated or not output or result.exit_code != 0:
            code = output.get("error", "ENGINE_UNAVAILABLE") if output else "ENGINE_UNAVAILABLE"
            raise EngineFailure(str(code), "isolated materials request failed; no result committed")
        outcome = MaterialsOutcome.model_validate(output)
        return outcome.model_copy(
            update={
                "isolation": {
                    "backend": result.profile.backend,
                    "enforced": result.profile.enforced,
                }
            }
        )
