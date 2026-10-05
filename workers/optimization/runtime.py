"""Production recommendations require OS-enforced no-egress execution."""

from __future__ import annotations

import json
import shutil
import subprocess

from workers.common.executor import ContainerBackend, ExecLimits

from engine_adapter_baybe.contracts import CampaignSpec, EngineFailure, Recommendation

IMAGE = "chem-studio-baybe:0.15.0-v1"


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


class IsolatedBayBE:
    def recommend(
        self,
        spec: CampaignSpec,
        *,
        batch_size: int,
        request_index: int,
        observations: list[dict[str, str]],
        reserved: list[dict[str, str]],
        pending: list[dict[str, str]],
    ) -> Recommendation:
        if not available():
            raise EngineFailure("ENGINE_UNAVAILABLE", "pinned BayBE worker image unavailable")
        inputs = json.dumps(
            {
                "spec": spec.model_dump(mode="json"),
                "batch_size": batch_size,
                "request_index": request_index,
                "observations": observations,
                "reserved": reserved,
                "pending": pending,
            }
        ).encode()
        result = ContainerBackend(IMAGE).run(
            ["python", "-m", "workers.optimization.runner"],
            inputs={"request.json": inputs},
            limits=ExecLimits(
                wall_seconds=120,
                cpu_seconds=120,
                memory_bytes=4 * 1024**3,
                max_processes=256,
                output_bytes=2 * 1024**2,
            ),
        )
        output = result.json_stdout()
        if result.timed_out or result.truncated or not output or result.exit_code != 0:
            code = output.get("error", "ENGINE_UNAVAILABLE") if output else "ENGINE_UNAVAILABLE"
            raise EngineFailure(
                str(code), "isolated BayBE request failed; no suggestions committed"
            )
        recommendation = Recommendation.model_validate(output)
        return recommendation.model_copy(
            update={
                "isolation": {
                    "backend": result.profile.backend,
                    "enforced": result.profile.enforced,
                }
            }
        )
