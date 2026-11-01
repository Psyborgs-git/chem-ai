"""Durable local job dispatch, process-tree cancellation and checkpoint recovery."""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select

from studio.config.settings import Settings
from studio.domain.learning.workspace_runtime.models import (
    LearningDataset,
    LearningJob,
    LearningModel,
)
from studio.errors import DomainError, ErrorCode


def job_directory(settings: Settings, job: LearningJob) -> Path:
    return (
        settings.vault_root
        / str(job.workspace_id)
        / "learning"
        / str(job.owner_id)
        / "jobs"
        / str(job.id)
    )


def _environment(directory: Path, *, download: bool = False) -> dict[str, str]:
    env = {
        key: os.environ[key]
        for key in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "TMPDIR")
        if key in os.environ
    }
    env.update(
        {
            "HF_HOME": str(directory / "cache" / "huggingface"),
            "XDG_CACHE_HOME": str(directory / "cache"),
            "PYTHONPATH": os.pathsep.join(path for path in sys.path if path),
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "DO_NOT_TRACK": "1",
            "WANDB_MODE": "disabled",
            "OMP_NUM_THREADS": "2",
            "MKL_NUM_THREADS": "2",
        }
    )
    if not download:
        env.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    return env


def _request(db: Any, job: LearningJob, settings: Settings | None = None) -> dict[str, Any]:
    # Recheck the exact owner at dispatch rather than trusting request-time identifiers.
    dataset = db.get(LearningDataset, job.dataset_id) if job.dataset_id else None
    model = db.get(LearningModel, job.model_id) if job.model_id else None
    for record in (dataset, model):
        if record is not None and (
            record.workspace_id != job.workspace_id or record.owner_id != job.owner_id
        ):
            raise ValueError("Job source ownership mismatch")
    if job.kind != "download_model" and (
        dataset is None or dataset.state != "frozen" or dataset.rights not in {"owned", "allowed"}
    ):
        raise ValueError("The approved private dataset is unavailable")
    if dataset is not None:
        from studio.auth.context import load_context
        from studio.domain.learning.workspace import LearningWorkspaceService, check_dataset_sources

        try:
            check_dataset_sources(db, dataset)
            context = load_context(db, job.workspace_id, job.owner_id)
            LearningWorkspaceService(
                db, context, settings or Settings()
            ).authorize_dataset_training(str(dataset.id))
        except DomainError as exc:
            raise ValueError(exc.message) from exc
    return {
        "kind": job.kind,
        "config": job.config,
        "rows": dataset.rows if dataset else [],
        "splits": dataset.splits if dataset else {},
        "datasetDigest": dataset.digest if dataset else None,
        "model": {"location": model.location, "backend": model.backend, "details": model.details}
        if model
        else None,
    }


def _kill(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=8)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def _events(directory: Path) -> list[dict[str, Any]]:
    file = directory / "events.jsonl"
    if not file.exists():
        return []
    with file.open("rb") as handle:
        size = file.stat().st_size
        if size > 1024 * 1024:
            handle.seek(size - 1024 * 1024)
            handle.readline()
        lines = handle.read().splitlines()[-200:]
    result = []
    for line in lines:
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                result.append(value)
        except ValueError:
            continue
    return result


def _register_result(db: Any, job: LearningJob, directory: Path) -> None:
    if job.kind == "download_model":
        model = db.get(LearningModel, job.model_id)
        if model:
            model.details = {**model.details, "state": "ready", "download": job.result}
        return
    if job.kind not in {"sft", "dpo", "grpo", "chemprop", "molecular_transfer", "molecular_rl"}:
        return
    base = db.get(LearningModel, job.model_id) if job.model_id else None
    model = LearningModel(
        workspace_id=job.workspace_id,
        owner_id=job.owner_id,
        name=job.name,
        backend=job.result.get("backend", job.config["backend"]),
        location=str(job.result.get("location", directory / "output")),
        details={
            **job.result,
            "state": "ready",
            "trainingJobId": str(job.id),
            "datasetId": str(job.dataset_id),
            "license": base.details.get("license", "unknown") if base else "owned",
            "baseModelId": str(base.id) if base else None,
            "repo": base.details.get("repo") if base else None,
        },
    )
    db.add(model)
    db.flush()
    job.result = {**job.result, "registeredModelId": str(model.id)}


class LearningDispatcher:
    def __init__(self, factory: Any, settings: Settings) -> None:
        self.factory, self.settings = factory, settings
        self.stop = threading.Event()
        self.identity = f"local-{uuid.uuid4().hex}"
        self.thread = threading.Thread(target=self._loop, daemon=True, name="learning-dispatch")

    def start(self) -> None:
        self.thread.start()

    def shutdown(self) -> None:
        self.stop.set()
        self.thread.join(timeout=15)

    def _loop(self) -> None:
        while not self.stop.is_set():
            try:
                self._recover()
                identifier = self._claim()
                if identifier:
                    self._execute(identifier)
                    continue
            except Exception as exc:
                # A DB outage or unapplied migration must not crash the application.
                logging.getLogger(__name__).warning(
                    "Learning dispatcher unavailable (%s)", type(exc).__name__
                )
            self.stop.wait(2)

    def _recover(self) -> None:
        with self.factory() as db:
            rows = db.execute(
                select(LearningJob)
                .where(
                    LearningJob.state == "running", LearningJob.lease_expires_at < datetime.now(UTC)
                )
                .with_for_update(skip_locked=True)
            ).scalars()
            for job in rows:
                job.state, job.error = (
                    "interrupted",
                    "Worker lease expired; resume from the latest saved checkpoint",
                )
                job.lease_owner, job.lease_expires_at = None, None
            db.commit()

    def _claim(self) -> uuid.UUID | None:
        with self.factory() as db:
            rows = db.execute(
                select(LearningJob)
                .where(LearningJob.state == "queued")
                .order_by(LearningJob.created_at)
                .limit(50)
                .with_for_update(skip_locked=True)
            ).scalars()
            for job in rows:
                if job.config.get("executionTarget") == "remote":
                    continue
                job.state, job.lease_owner = "running", self.identity
                job.attempt += 1
                job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=60)
                identifier: uuid.UUID = job.id
                db.commit()
                return identifier
            db.commit()
        return None

    def _execute(self, identifier: uuid.UUID) -> None:
        from studio.domain.learning.workspace import (
            job_storage_requirement,
            runtime_python,
            storage_preflight,
        )

        with self.factory() as db:
            job = db.get(LearningJob, identifier)
            required = job.config.get(
                "requiredFreeBytes", job_storage_requirement(job.kind, job.config)
            )
            storage = storage_preflight(self.settings, required)
            if not storage["available"]:
                job.state, job.error = (
                    "blocked",
                    "Insufficient free disk space; job outputs were not modified",
                )
                job.lease_owner, job.lease_expires_at = None, None
                job.result = {**job.result, "storagePreflight": storage}
                db.commit()
                return
            directory = job_directory(self.settings, job)
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)
            try:
                payload = _request(db, job, self.settings)
            except ValueError as exc:
                job.state, job.error = "failed", str(exc)
                db.commit()
                return
            backend = job.config["backend"]
            timeout = job.config.get("maxSeconds", 3600)
            (directory / "request.json").write_text(json.dumps(payload))
            (directory / "request.json").chmod(0o600)
            (directory / "result.json").unlink(missing_ok=True)
        process: subprocess.Popen[Any] | None = None
        try:
            with (directory / "worker.log").open("wb") as log:
                process = subprocess.Popen(  # noqa: S603 — fixed worker module, configured interpreter
                    [
                        runtime_python(backend),
                        "-m",
                        "studio.domain.learning.workspace_runtime.worker",
                        str(directory),
                    ],
                    cwd=directory,
                    env=_environment(directory, download=backend == "download"),
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
                started = time.monotonic()
                stopped = None
                while process.poll() is None:
                    with self.factory() as db:
                        current = db.get(LearningJob, identifier)
                        try:
                            _request(db, current, self.settings)
                        except ValueError:
                            current.cancel_requested = True
                        if current.lease_owner != self.identity:
                            stopped = "interrupted"
                        elif current.cancel_requested:
                            stopped = "cancelled"
                        elif self.stop.is_set():
                            stopped = "interrupted"
                        elif time.monotonic() - started > timeout:
                            stopped = "timed_out"
                        current.events = _events(directory)
                        current.lease_expires_at = datetime.now(UTC) + timedelta(seconds=60)
                        db.commit()
                    if stopped:
                        _kill(process)
                        break
                    self.stop.wait(1)
            result_path = directory / "result.json"
            result = (
                json.loads(result_path.read_text())
                if result_path.exists() and result_path.stat().st_size < 5 * 1024 * 1024
                else {}
            )
            with self.factory() as db:
                job = db.get(LearningJob, identifier)
                job.events = _events(directory)
                job.lease_owner, job.lease_expires_at = None, None
                checkpoints = [
                    str(path.relative_to(directory))
                    for path in sorted((directory / "output").rglob("*"))
                    if path.is_file() and ("checkpoint" in str(path) or "adapter" in path.name)
                ]
                job.result = {**job.result, **result, "checkpoints": checkpoints[-100:]}
                if stopped:
                    job.state, job.error = stopped, f"Job {stopped}; saved checkpoints are retained"
                elif result.get("ok"):
                    job.state, job.error = "completed", None
                    _register_result(db, job, directory)
                else:
                    job.state, job.error = (
                        "failed",
                        result.get(
                            "error", "Worker exited without a result; inspect the local worker log"
                        ),
                    )
                    if job.kind == "download_model" and job.model_id:
                        model = db.get(LearningModel, job.model_id)
                        model.details = {**model.details, "state": "failed"}
                db.commit()
        except Exception as exc:
            if process is not None:
                _kill(process)
            with self.factory() as db:
                job = db.get(LearningJob, identifier)
                job.state, job.error = "failed", f"Worker execution failed ({type(exc).__name__})"
                job.lease_owner, job.lease_expires_at = None, None
                db.commit()
        finally:
            if process is not None:
                _kill(process)


def start_learning_dispatcher(app: Any) -> None:
    dispatcher = LearningDispatcher(app.state.session_factory, app.state.settings)
    app.state.learning_dispatcher = dispatcher
    dispatcher.start()


def stop_learning_dispatcher(app: Any) -> None:
    dispatcher = getattr(app.state, "learning_dispatcher", None)
    if dispatcher:
        dispatcher.shutdown()


def run_preview(
    model: LearningModel,
    prompt: str,
    max_tokens: int,
    settings: Settings,
    *,
    messages: list[dict[str, Any]] | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from studio.domain.learning.workspace import (
        runtime_capability,
        runtime_python,
        storage_preflight,
    )

    if not runtime_capability(model.backend)["available"]:
        raise DomainError(
            ErrorCode.ENGINE_UNAVAILABLE, "Install the model's local runtime to preview it"
        )
    if not storage_preflight(settings, 16 * 1024**2)["available"]:
        raise DomainError(
            ErrorCode.RESOURCE_UNAVAILABLE, "Insufficient free disk space for model preview"
        )
    directory = (
        settings.vault_root
        / str(model.workspace_id)
        / "learning"
        / str(model.owner_id)
        / "previews"
        / uuid.uuid4().hex
    )
    directory.mkdir(parents=True, mode=0o700)
    payload = {
        "kind": "preview",
        "prompt": prompt,
        "config": {"backend": model.backend, "maxTokens": max_tokens},
        "model": {"location": model.location, "backend": model.backend, "details": model.details},
        "messages": messages,
        "tools": tools,
    }
    (directory / "request.json").write_text(json.dumps(payload))
    try:
        subprocess.run(  # noqa: S603 — fixed worker module, configured interpreter
            [
                runtime_python(model.backend),
                "-m",
                "studio.domain.learning.workspace_runtime.worker",
                str(directory),
            ],
            cwd=directory,
            env=_environment(directory),
            capture_output=True,
            timeout=120,
            check=False,
            start_new_session=True,
        )
        result = json.loads((directory / "result.json").read_text())
        if not result.get("ok"):
            raise DomainError(ErrorCode.ENGINE_UNAVAILABLE, result.get("error", "Preview failed"))
        return cast(dict[str, Any], result)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise DomainError(
            ErrorCode.ENGINE_UNAVAILABLE, "Local model preview failed or timed out"
        ) from exc
    finally:
        shutil.rmtree(directory, ignore_errors=True)
