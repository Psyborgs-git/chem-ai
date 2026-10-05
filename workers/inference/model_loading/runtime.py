"""Host-side isolated model-load runtime (CS-0802).

``ModelLoadRuntime`` runs the structural validation on the host (stdlib
— always, no image required) and, when the pinned
``chem-studio-model-load`` image is present, additionally performs the
real load + probe-parity inside the container with no network, a
read-only root, bounded memory/pids, and cancellation. Honest labels:
``mode`` says which levels actually ran — stdlib results are never
labeled as a verified load.
"""

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from typing import Any

from workers.common.executor import ContainerBackend, ExecLimits
from workers.inference.model_loading.contracts import (
    LoadRequest,
    LoadValidationReport,
    canonical_json,
)

IMAGE = "chem-studio-model-load:0.1.0"
_MAX_REPORT_BYTES = 4 * 1024 * 1024


def available() -> bool:
    return ContainerBackend.available(IMAGE)


def capability() -> str:
    return "live" if available() else "not_installed"


class ModelLoadRuntime:
    """Orchestrates stdlib + isolated compatibility validation."""

    # ------------------------------------------------------------- validation

    def validate(
        self,
        request: LoadRequest,
        *,
        adapter_bytes: bytes | None = None,
        bundle_bytes: bytes | None = None,
        cancel: threading.Event | None = None,
    ) -> LoadValidationReport:
        """Run validation for one registered release.

        Always performs the stdlib pass. When the pinned image is
        installed, performs the isolated pass as well and returns its
        verdict (which embeds the stdlib checks it re-ran). When absent,
        the stdlib report is returned with ``load_verified=False`` —
        never fabricated as a real load.
        """
        from workers.inference.model_loading.verify import validate_structural

        stdlib_report = validate_structural(
            base=request.base,
            tokenizer=request.tokenizer,
            adapter=request.adapter,
            serving_format=request.serving_format,
            adapter_bytes=adapter_bytes,
        )
        if not available():
            return stdlib_report
        inputs: dict[str, bytes] = {
            "request.json": canonical_json(request.model_dump(mode="json")).encode("utf-8"),
        }
        if adapter_bytes is not None:
            inputs["adapter.safetensors"] = adapter_bytes
        if bundle_bytes is not None:
            inputs["bundle.json"] = bundle_bytes
        try:
            result = ContainerBackend(IMAGE).run(
                ["python", "-m", "workers.inference.model_loading.runner"],
                inputs=inputs,
                limits=ExecLimits(
                    wall_seconds=240,
                    cpu_seconds=180,
                    memory_bytes=2 * 1024**3,
                    max_processes=64,
                    output_bytes=2 * 1024**2,
                    file_bytes=256 * 1024**2,
                ),
                cancel=cancel,
            )
        except Exception:
            return stdlib_report.model_copy(
                update={"detail": stdlib_report.detail + " (isolated runner unavailable)"}
            )
        scratch = Path(result.scratch_dir) if result.scratch_dir else None
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
        isolation = {
            "backend": result.profile.backend,
            "enforced": dict(result.profile.enforced),
            "image": IMAGE,
        }
        if result.timed_out or result.cancelled or result.exit_code != 0:
            reason = (
                "cancelled"
                if result.cancelled
                else ("timed out" if result.timed_out else f"exit {result.exit_code}")
            )
            return stdlib_report.model_copy(
                update={
                    "detail": stdlib_report.detail + f" (isolated runner {reason})",
                    "isolation": isolation,
                }
            )
        try:
            doc: dict[str, Any] = json.loads(
                result.stdout.strip().splitlines()[-1][: _MAX_REPORT_BYTES]
            )
        except (ValueError, IndexError):
            return stdlib_report.model_copy(
                update={
                    "detail": stdlib_report.detail + " (isolated runner output unreadable)",
                    "isolation": isolation,
                }
            )
        if isinstance(doc, dict) and "error" in doc:
            err = doc["error"]
            code = err.get("code", "unknown") if isinstance(err, dict) else "unknown"
            return stdlib_report.model_copy(
                update={
                    "detail": stdlib_report.detail + f" (isolated runner: {code})",
                    "isolation": isolation,
                }
            )
        try:
            report = LoadValidationReport.model_validate(doc)
        except Exception:
            return stdlib_report.model_copy(
                update={
                    "detail": stdlib_report.detail + " (isolated report invalid)",
                    "isolation": isolation,
                }
            )
        return report.model_copy(update={"isolation": isolation})


__all__ = ["IMAGE", "ModelLoadRuntime", "available", "capability"]
