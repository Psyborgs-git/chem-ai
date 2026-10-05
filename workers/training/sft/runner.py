"""Network-denied SFT trainer entrypoint; bounded JSON in/out.

Reads request.json (``{"spec": SftTrainSpec}``) plus the approved
dataset bytes in dataset.jsonl (one SftTrainingExample per line —
bytes hashed by the eligibility gate are the bytes consumed), runs the
pinned torch+PEFT trainer inside the container, and leaves all
artifacts — config.json, train.jsonl telemetry, ckpt-* dirs, adapter/,
result.json — in the scratch dir for the host to harvest into the
vault. A cancel kill leaves the newest checkpoint behind for resume
(AT-0801-3); nothing here depends on the network or writable root.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from engine_adapter_sft.contracts import TrainerFailure
from engine_adapter_sft.trainer import capability as trainer_capability
from engine_adapter_sft.trainer import train

_MAX_REQUEST = 2 * 1024 * 1024
_MAX_DATASET = 256 * 1024 * 1024


def run(request: dict[str, Any], dataset: list[dict[str, Any]]) -> dict[str, Any]:
    outcome = train({**request, "dataset": dataset}, Path.cwd())
    return outcome.model_dump(mode="json")


def _unpack_resume_tar() -> None:
    """Extract resume.tar into ./resume — tar members are constrained to
    relative checkpoint names, never absolute or parent-escaping."""
    import tarfile

    tar_path = Path("resume.tar")
    if not tar_path.is_file():
        return
    dest = Path("resume")
    dest.mkdir(exist_ok=True)
    with tarfile.open(tar_path, "r:*") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            name = Path(member.name)
            if name.is_absolute() or ".." in name.parts:
                raise ValueError("unsafe resume member")
            archive.extract(member, dest, filter="data")


if __name__ == "__main__":
    if sys.argv[1:] == ["--capability"]:
        try:
            print(json.dumps(trainer_capability()))
        except Exception:
            print(json.dumps({"error": "ENGINE_UNAVAILABLE", "message": "probe failed"}))
            sys.exit(2)
        sys.exit(0)
    try:
        # Artifacts the trainer writes must be readable by the host
        # harvester even though the container uid differs.
        os.umask(0o022)
        with open("request.json", "rb") as f:
            raw = f.read(_MAX_REQUEST + 1)
        if len(raw) > _MAX_REQUEST:
            raise ValueError("request too large")
        request = json.loads(raw)
        _unpack_resume_tar()
        with open("dataset.jsonl", "rb") as f:
            data = f.read(_MAX_DATASET + 1)
        if len(data) > _MAX_DATASET:
            raise ValueError("dataset too large")
        dataset = [json.loads(line) for line in data.splitlines() if line.strip()]
        result = run(request, dataset)
        # safetensors writes files mode 0600 — relax the whole output
        # tree so the host harvester can read every artifact.
        for path in Path(".").rglob("*"):
            if path.name.startswith(("resume", "request.json", "dataset.jsonl")):
                continue
            try:
                if path.is_dir():
                    path.chmod(0o755)
                elif path.is_file():
                    path.chmod(0o644)
            except PermissionError:
                continue  # input files are host-owned — outputs only
        print(json.dumps(result))
    except TrainerFailure as exc:
        print(json.dumps({"error": exc.code, "message": exc.message}))
        sys.exit(2)
    except MemoryError:
        print(
            json.dumps(
                {
                    "error": "ENGINE_UNAVAILABLE",
                    "message": "training run exceeded its memory envelope",
                }
            )
        )
        sys.exit(2)
    except Exception:
        # Tracebacks may contain confidential dataset fragments; never
        # emit them — a sanitized code is all the caller gets.
        print(
            json.dumps(
                {
                    "error": "ENGINE_UNSUPPORTED_INPUT",
                    "message": "trainer could not process the declared job",
                }
            )
        )
        sys.exit(2)
