"""RL training requires OS-enforced no-egress execution (§19.4).

The pinned image ``chem-studio-rl:0.1.0-v1`` carries torch CPU + trl +
peft + the locally constructed pico-RL policy on a frozen
requirements.lock, plus the CS-0901 environment + reward service and
the shared capability vocabulary (the environment re-resolves policy
grants server-side inside the container).

There is intentionally no subprocess fallback and no cloud offload:
``available()``/``capability()`` report honest states when the image
is absent (missing GPU/toolchain → engine tests skip; the run fails
closed). An exhausted rollout envelope stops work inside the run —
``status="budget_exhausted"`` with the counters persisted — and a
cancelled/timed-out run still yields its newest ``checkpoint-*`` dir
for provenance-preserving resume (same convention as SFT AT-0801-3).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine_adapter_rl.contracts import (
    RlCheckpoint,
    RlOutcome,
    RlTrainSpec,
    TrainerFailure,
    sha256_bytes,
)
from workers.common.executor import ContainerBackend, ExecLimits

IMAGE = "chem-studio-rl:0.1.0-v1"

_MAX_ARTIFACT_BYTES = 256 * 1024**2
_MAX_FILE_BYTES = 64 * 1024**2


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
    """Probe inside the pinned image itself — honest state only."""
    if not available():
        return None
    result = ContainerBackend(IMAGE).run(
        ["python", "-m", "workers.training.rl.trainer.runner", "--capability"],
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


def _harvest(scratch: Path) -> dict[str, bytes]:
    """Pull bounded artifacts out of the run scratch (already stopped)."""
    artifacts: dict[str, bytes] = {}
    total = 0
    for path in sorted(scratch.rglob("*")):
        if not path.is_file():
            continue
        if path.name in ("request.json", "corpus.json") or path.name.startswith("resume"):
            continue
        size = path.stat().st_size
        if size > _MAX_FILE_BYTES or total + size > _MAX_ARTIFACT_BYTES:
            continue
        try:
            artifacts[str(path.relative_to(scratch))] = path.read_bytes()
        except PermissionError:
            continue  # mid-write kill can leave an unreadable file
        total += size
    return artifacts


def _checkpoints_from_meta(artifacts: dict[str, bytes]) -> list[RlCheckpoint]:
    """Reconstruct checkpoint records when result.json was never
    written (kill mid-run) — meta.json per checkpoint dir carries step
    + config digest; adapter sha re-hashed over harvested bytes."""
    points: list[RlCheckpoint] = []
    for name, data in artifacts.items():
        if "checkpoint-" not in name or not name.endswith("adapter_model.safetensors"):
            continue
        meta_name = name.rsplit("/", 1)[0] + "/meta.json"
        meta: dict[str, Any] = {}
        if meta_name in artifacts:
            try:
                meta = json.loads(artifacts[meta_name])
            except (ValueError, UnicodeDecodeError):
                meta = {}
        points.append(
            RlCheckpoint(
                step=int(meta.get("step", 0)),
                sha256=sha256_bytes(data),
                artifact=name.rsplit("/", 1)[0],
                optimizer_sha256=None,
            )
        )
    return sorted(points, key=lambda c: c.step)


def _pack_resume_tar(resume_files: dict[str, bytes]) -> bytes:
    """Pack the harvested checkpoint files as one tar — inputs are
    basename-only so a single archive keeps the resume/ tree intact."""
    import io
    import tarfile

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, data in sorted(resume_files.items()):
            safe = Path(name)
            if safe.name != name or ".." in safe.parts:
                continue
            info = tarfile.TarInfo(str(safe))
            info.size = len(data)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


@dataclass
class RlRunResult:
    """Everything the host needs from one bounded RL run."""

    status: str  # succeeded | failed | cancelled | timed_out | budget_exhausted
    outcome: RlOutcome | None = None
    artifacts: dict[str, bytes] = field(default_factory=dict)
    checkpoints: list[RlCheckpoint] = field(default_factory=list)
    error: dict[str, Any] | None = None
    isolation: dict[str, Any] = field(default_factory=dict)


class IsolatedRl:
    """Runs one approved RL job in the pinned no-egress container."""

    def train(
        self,
        spec: RlTrainSpec,
        *,
        corpus: bytes,
        resume_files: dict[str, bytes] | None = None,
        cancel: threading.Event | None = None,
    ) -> RlRunResult:
        if not available():
            raise TrainerFailure("ENGINE_UNAVAILABLE", "pinned RL worker image unavailable")
        request = {"spec": spec.model_dump(mode="json")}
        inputs: dict[str, bytes] = {
            "request.json": json.dumps(request).encode("utf-8"),
            # Byte-faithful: the same corpus bytes the approval bound
            # are the bytes the trainer parses (like AT-0801-2).
            "corpus.json": corpus,
        }
        if resume_files:
            inputs["resume.tar"] = _pack_resume_tar(resume_files)
        resources = spec.resources
        result = ContainerBackend(IMAGE).run(
            ["python", "-m", "workers.training.rl.trainer.runner"],
            inputs=inputs,
            limits=ExecLimits(
                wall_seconds=resources.wall_seconds,
                cpu_seconds=resources.wall_seconds,
                memory_bytes=resources.memory_mebibytes * 1024**2,
                max_processes=64,
                output_bytes=4 * 1024**2,
                file_bytes=_MAX_FILE_BYTES,
            ),
            cancel=cancel,
        )
        scratch = Path(result.scratch_dir) if result.scratch_dir else None
        artifacts = _harvest(scratch) if scratch and scratch.is_dir() else {}
        if scratch and scratch.is_dir():
            shutil.rmtree(scratch, ignore_errors=True)
        isolation = {
            "backend": result.profile.backend,
            "enforced": result.profile.enforced,
        }

        if result.cancelled:
            outcome = self._partial_outcome("cancelled", "cancelled", spec, artifacts)
            return RlRunResult(
                status="cancelled",
                outcome=outcome.model_copy(update={"isolation": isolation}),
                artifacts=artifacts,
                checkpoints=_checkpoints_from_meta(artifacts),
                isolation=isolation,
            )
        if result.timed_out:
            outcome = self._partial_outcome("timed_out", "timed_out", spec, artifacts)
            return RlRunResult(
                status="timed_out",
                outcome=outcome.model_copy(update={"isolation": isolation}),
                artifacts=artifacts,
                checkpoints=_checkpoints_from_meta(artifacts),
                isolation=isolation,
            )
        output = result.json_stdout()
        if result.truncated or not output or result.exit_code != 0:
            code = output.get("error", "ENGINE_UNAVAILABLE") if output else "ENGINE_UNAVAILABLE"
            raise TrainerFailure(str(code), "isolated RL request failed; no result committed")
        outcome = RlOutcome.model_validate(output)
        checkpoints = (
            outcome.checkpoints if outcome.checkpoints else _checkpoints_from_meta(artifacts)
        )
        if outcome.status == "budget_exhausted":
            status = "budget_exhausted"
        else:
            status = "succeeded" if outcome.usable else "failed"
        return RlRunResult(
            status=status,
            outcome=outcome.model_copy(update={"isolation": isolation}),
            artifacts=artifacts,
            checkpoints=checkpoints,
            error=outcome.error,
            isolation=isolation,
        )

    @staticmethod
    def _partial_outcome(
        status: str, classification: str, spec: RlTrainSpec, artifacts: dict[str, bytes]
    ) -> RlOutcome:
        """Honest outcome for a killed run — no fabricated telemetry."""
        tail: list[dict[str, Any]] = []
        if "train.jsonl" in artifacts:
            lines = artifacts["train.jsonl"].decode("utf-8", "replace").splitlines()
            for line in lines[-20:]:
                try:
                    tail.append(json.loads(line))
                except ValueError:
                    continue
        steps = 0
        for record in tail:
            if isinstance(record.get("step"), int):
                steps = max(steps, record["step"])
        return RlOutcome(
            status=status,
            usable=False,
            classification=classification,
            base_model_id=spec.model.base_model_id,
            config_digest=spec.digest(),
            corpus_digest=spec.corpus_digest,
            optimizer_steps=steps,
            telemetry_tail=tail,
            resume_from=spec.resume.model_dump(mode="json") if spec.resume else None,
            error={"code": f"RUN_{status.upper()}", "message": f"run {status}"},
            scientific_status="not_validated",
        )
