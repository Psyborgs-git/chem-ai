"""Authenticated outbound worker protocol; datasets and leases remain owner-scoped."""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select

from studio.domain.learning.workspace import LearningWorkspaceService, storage_preflight
from studio.domain.learning.workspace_runtime.dispatcher import (
    _register_result,
    _request,
    job_directory,
)
from studio.domain.learning.workspace_runtime.models import LearningJob, LearningModel
from studio.errors import DomainError, ErrorCode

MAX_ARTIFACT_BYTES = 256 * 1024 * 1024


def _worker_id(payload: dict[str, Any]) -> str:
    identifier = str(payload.get("workerId", ""))
    if not re.fullmatch(r"[A-Za-z0-9_.-]{8,100}", identifier):
        raise DomainError(
            ErrorCode.VALIDATION, "workerId must contain 8-100 letters, numbers or ._-"
        )
    return identifier


def lease(service: LearningWorkspaceService, payload: dict[str, Any]) -> dict[str, Any]:
    worker_id = _worker_id(payload)
    backends = payload.get("backends", [])
    if not isinstance(backends, list) or any(
        name not in {"transformers", "chemprop", "reinvent", "mlx"} for name in backends
    ):
        raise DomainError(ErrorCode.VALIDATION, "Worker must declare supported training backends")
    rows = service.db.execute(
        select(LearningJob)
        .where(
            LearningJob.workspace_id == service.ctx.workspace_id,
            LearningJob.owner_id == service.ctx.principal_id,
            LearningJob.state == "queued",
        )
        .order_by(LearningJob.created_at)
        .with_for_update(skip_locked=True)
    ).scalars()
    for job in rows:
        if (
            job.config.get("executionTarget") != "remote"
            or job.config.get("backend") not in backends
        ):
            continue
        request = _request(service.db, job, service.settings)
        if job.dataset_id:
            service.authorize_dataset_egress(str(job.dataset_id))
        if request["model"]:
            model = service._owned(LearningModel, str(job.model_id))
            # A remote machine receives a model ID/repository, never host filesystem paths.
            request["model"] = {
                "id": str(model.id),
                "backend": model.backend,
                "repo": model.details.get("repo"),
                "details": {
                    key: value
                    for key, value in model.details.items()
                    if key
                    in {
                        "license",
                        "catalogId",
                        "modelDigest",
                        "scope",
                        "trainingJobId",
                        "artifacts",
                        "baseModelId",
                        "revision",
                        "baseRevision",
                    }
                },
            }
        job.state, job.lease_owner = "running", worker_id
        job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=120)
        job.attempt += 1
        service.db.flush()
        return {
            "jobId": str(job.id),
            "request": request,
            "leaseSeconds": 120,
            "resumeAvailable": (job_directory(service.settings, job) / "output").exists(),
        }
    return {"jobId": None}


def _leased(service: LearningWorkspaceService, identifier: str, worker_id: str) -> LearningJob:
    job = service._owned(LearningJob, identifier)
    now = datetime.now(UTC)
    expiry = job.lease_expires_at
    if expiry is not None and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    if job.state != "running" or job.lease_owner != worker_id or expiry is None or expiry < now:
        raise DomainError(ErrorCode.CONFLICT, "Worker lease expired or does not own this job")
    return job


def heartbeat(
    service: LearningWorkspaceService, identifier: str, payload: dict[str, Any]
) -> dict[str, Any]:
    job = _leased(service, identifier, _worker_id(payload))
    try:
        _request(service.db, job, service.settings)
        if job.dataset_id:
            service.authorize_dataset_egress(str(job.dataset_id))
    except (ValueError, DomainError):
        job.cancel_requested = True
    job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=120)
    events = payload.get("events", [])
    if isinstance(events, list) and len(json.dumps(events)) < 100_000:
        job.events = [event for event in events[-100:] if isinstance(event, dict)]
    service.db.flush()
    return {"cancelRequested": job.cancel_requested, "leaseSeconds": 120}


def checkpoint_archive(service: LearningWorkspaceService, identifier: str, worker_id: str) -> bytes:
    job = _leased(service, identifier, worker_id)
    directory = job_directory(service.settings, job) / "output"
    buffer = io.BytesIO()
    if directory.exists():
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
            total = 0
            for path in directory.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    total += path.stat().st_size
                    if total > MAX_ARTIFACT_BYTES:
                        raise DomainError(
                            ErrorCode.VALIDATION, "Checkpoint exceeds remote transfer limit"
                        )
                    archive.write(path, str(path.relative_to(directory)))
    return buffer.getvalue()


def model_archive(service: LearningWorkspaceService, identifier: str, worker_id: str) -> bytes:
    job = _leased(service, identifier, worker_id)
    model = service._owned(LearningModel, str(job.model_id))
    source_id = model.details.get("trainingJobId")
    if not source_id:
        return b""
    source = service._owned(LearningJob, str(source_id))
    directory = job_directory(service.settings, source) / "output"
    buffer = io.BytesIO()
    total = 0
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for item in model.details.get("artifacts", []):
            path = (directory / item["path"]).resolve()
            if (
                not path.is_relative_to(directory.resolve())
                or not path.is_file()
                or path.is_symlink()
            ):
                raise DomainError(ErrorCode.NOT_FOUND, "Private model artifact unavailable")
            total += path.stat().st_size
            if total > MAX_ARTIFACT_BYTES:
                raise DomainError(
                    ErrorCode.VALIDATION, "Model artifacts exceed remote transfer limit"
                )
            archive.write(path, item["path"])
    return buffer.getvalue()


def complete(
    service: LearningWorkspaceService, identifier: str, payload: dict[str, Any], content: bytes
) -> dict[str, Any]:
    job = _leased(service, identifier, _worker_id(payload))
    if len(content) > MAX_ARTIFACT_BYTES:
        raise DomainError(ErrorCode.VALIDATION, "Artifacts exceed the 256 MiB upload limit")
    directory = job_directory(service.settings, job)
    output = directory / "output"
    staging = directory / "remote-staging"
    staging.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest: list[dict[str, Any]] = []
    try:
        if content:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                members = archive.infolist()
                if (
                    len(members) > 5000
                    or sum(item.file_size for item in members) > MAX_ARTIFACT_BYTES
                ):
                    raise ValueError("Artifact archive exceeds limits")
                capacity = storage_preflight(
                    service.settings, sum(item.file_size for item in members) + 16 * 1024**2
                )
                if not capacity["available"]:
                    raise ValueError("Insufficient free disk space to retain worker artifacts")
                for member in members:
                    name = Path(member.filename)
                    if name.is_absolute() or ".." in name.parts or "\\" in member.filename:
                        raise ValueError("Unsafe artifact path")
                    if member.is_dir():
                        continue
                    path = staging / name
                    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    data = archive.read(member)
                    path.write_bytes(data)
                    path.chmod(0o600)
                    manifest.append(
                        {
                            "path": str(name),
                            "bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest(),
                        }
                    )
        result = payload.get("result", {})
        if not isinstance(result, dict) or len(json.dumps(result)) > 1_000_000:
            raise ValueError("Result must contain bounded JSON metadata")
        # Never allow remote output to redirect preview/model loading to another host path.
        safe = {
            key: value
            for key, value in result.items()
            if key
            not in {
                "location",
                "baseLocation",
                "adapterPath",
                "artifacts",
                "registeredModelId",
                "active",
                "review",
                "activation",
                "approval",
            }
        }
        safe.update(
            {
                "backend": job.config["backend"],
                "artifacts": manifest,
                "scientificStatus": "not_validated",
                "execution": "authenticated_remote_worker",
            }
        )
        if job.config["backend"] in {"mlx", "transformers"}:
            base = service._owned(LearningModel, str(job.model_id))
            safe.update({"baseLocation": base.location, "adapterPath": str(output)})
        if job.config["backend"] == "reinvent":
            safe["location"] = str(
                output / ("trained.model" if job.kind == "molecular_transfer" else "trained.chkpt")
            )
        success = bool(result.get("ok")) and not job.cancel_requested
        if (
            success
            and job.kind in {"sft", "dpo", "grpo"}
            and not any(item["path"].endswith(".safetensors") for item in manifest)
        ):
            raise ValueError("Successful training must include adapter weights")
        if output.exists():
            shutil.rmtree(output)
        staging.replace(output)
        job.result = {**job.result, **safe}
        job.state = "completed" if success else ("cancelled" if job.cancel_requested else "failed")
        job.error = None if success else str(result.get("error", "Remote job stopped"))[:500]
        job.lease_owner, job.lease_expires_at = None, None
        if success:
            _register_result(service.db, job, directory)
        service.db.flush()
        return service._job(job)
    except (ValueError, zipfile.BadZipFile) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise DomainError(ErrorCode.VALIDATION, str(exc)) from exc
