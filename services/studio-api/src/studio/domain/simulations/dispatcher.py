"""Durable native MD dispatch with bounded resources and process-group cancellation."""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

from studio.domain.simulations.models import SimulationJob
from studio.domain.simulations.service import job_directory, runtime_python


def _kill(process: subprocess.Popen[Any]) -> None:
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)


def _environment(directory: Path) -> dict[str, str]:
    env = {
        key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TMPDIR") if key in os.environ
    }
    env.update(
        {
            # Optional scientific dependencies must resolve from this worker's
            # interpreter, never from the API environment's site-packages.
            "PYTHONPATH": str(Path(__file__).resolve().parents[6]),
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "OMP_NUM_THREADS": "2",
            "MPLCONFIGDIR": str(directory / "cache"),
            "MPLBACKEND": "Agg",
            "HF_HUB_OFFLINE": "1",
            "DO_NOT_TRACK": "1",
        }
    )
    if os.environ.get("STUDIO_LAMMPS_EXEC"):
        env["STUDIO_LAMMPS_EXEC"] = os.environ["STUDIO_LAMMPS_EXEC"]
    return env


def _events(directory: Path) -> list[dict[str, Any]]:
    path = directory / "events.jsonl"
    if not path.exists():
        return []
    with path.open("rb") as handle:
        if path.stat().st_size > 1024 * 1024:
            handle.seek(-1024 * 1024, 2)
            handle.readline()
        lines = handle.read().splitlines()[-200:]
    result = []
    for line in lines:
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                result.append(value)
        except ValueError:
            pass
    return result


def _lease(directory: Path) -> None:
    path = directory / "lease.json"
    temporary = directory / "lease.tmp"
    temporary.write_text(json.dumps({"expiresAt": time.time() + 20}))
    temporary.replace(path)


def _final_result(
    previous: dict[str, Any], result: dict[str, Any], elapsed: float, *, succeeded: bool
) -> dict[str, Any]:
    merged = {**previous, **result, "elapsedSeconds": elapsed}
    if succeeded:
        # The previous failure remains in its event/attempt archive. It must
        # not masquerade as an error in the successful current-attempt result.
        merged.pop("error", None)
    return merged


class SimulationDispatcher:
    def __init__(self, factory: Any, settings: Any) -> None:
        self.factory, self.settings = factory, settings
        self.stop = threading.Event()
        self.identity = f"simulation-{uuid.uuid4().hex}"
        self.thread = threading.Thread(target=self._loop, name="simulation-dispatch", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def shutdown(self) -> None:
        self.stop.set()
        self.thread.join(timeout=10)

    def _recover(self) -> None:
        with self.factory() as db:
            rows = db.scalars(
                select(SimulationJob).where(
                    SimulationJob.state == "running",
                    SimulationJob.lease_expires_at < datetime.now(UTC),
                )
            )
            for job in rows:
                job.state, job.error = (
                    "interrupted",
                    "Worker lease expired; completed stages and raw artifacts remain available",
                )
                job.lease_owner, job.lease_expires_at = None, None
                job.finished_at = datetime.now(UTC)
            db.commit()

    def _claim(self) -> uuid.UUID | None:
        from studio.domain.learning.workspace_runtime.models import LearningJob

        with self.factory() as db:
            if db.bind.dialect.name == "postgresql":
                # Same advisory key is used by local learning admission/dispatch.
                if not db.scalar(text("SELECT pg_try_advisory_xact_lock(917431102)")):
                    return None
            for cls in (LearningJob, SimulationJob):
                if db.scalar(
                    select(cls.id)
                    .where(cls.state == "running", cls.lease_expires_at > datetime.now(UTC))
                    .limit(1)
                ):
                    return None
            job = db.scalar(
                select(SimulationJob)
                .where(SimulationJob.state == "queued")
                .order_by(SimulationJob.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return None
            job.state, job.lease_owner = "running", self.identity
            job.attempt += 1
            job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=60)
            job.started_at = job.started_at or datetime.now(UTC)
            identifier: uuid.UUID = job.id
            db.commit()
            return identifier

    def _loop(self) -> None:
        while not self.stop.is_set():
            try:
                self._recover()
                identifier = self._claim()
                if identifier:
                    self._execute(identifier)
            except Exception as exc:
                # Recover through the persisted lease; never create fixture success.
                logging.getLogger(__name__).warning(
                    "Simulation dispatcher tick failed (%s)", type(exc).__name__
                )
            self.stop.wait(1)

    def _execute(self, identifier: uuid.UUID) -> None:
        import shutil

        with self.factory() as db:
            job = db.get(SimulationJob, identifier)
            directory = job_directory(self.settings, job)
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            directory.chmod(0o700)
            remaining = max(0, job.config["maxWallSeconds"] - job.elapsed_seconds)
            if remaining < 1 or shutil.disk_usage(directory).free < 512 * 1024 * 1024:
                job.state, job.error = (
                    "blocked",
                    "Simulation compute or storage budget is exhausted",
                )
                job.lease_owner, job.lease_expires_at = None, None
                db.commit()
                return
            (directory / "request.json").write_text(
                json.dumps({"config": job.config, "remainingSeconds": remaining})
            )
            (directory / "request.json").chmod(0o600)
            (directory / "result.json").unlink(missing_ok=True)
            prior_elapsed = job.elapsed_seconds
        process: subprocess.Popen[Any] | None = None
        started = time.monotonic()
        stopped = None
        try:
            _lease(directory)
            with (directory / f"worker-attempt-{job.attempt}.log").open("wb") as log:
                process = subprocess.Popen(  # noqa: S603 — fixed isolated worker
                    [
                        runtime_python(),
                        "-m",
                        "workers.simulation.radonpy_worker",
                        str(directory.resolve()),
                    ],
                    cwd=directory,
                    env=_environment(directory),
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
                while process.poll() is None:
                    with self.factory() as db:
                        current = db.get(SimulationJob, identifier)
                        if current.lease_owner != self.identity:
                            stopped = "interrupted"
                        elif current.cancel_requested:
                            stopped = "cancelled"
                        elif self.stop.is_set():
                            stopped = "interrupted"
                        elif time.monotonic() - started >= remaining:
                            stopped = "timed_out"
                        elif shutil.disk_usage(directory).free < 64 * 1024 * 1024:
                            stopped = "blocked"
                        current.events = _events(directory)
                        current.elapsed_seconds = prior_elapsed + time.monotonic() - started
                        current.result = {
                            **current.result,
                            "elapsedSeconds": current.elapsed_seconds,
                        }
                        current.lease_expires_at = datetime.now(UTC) + timedelta(seconds=60)
                        db.commit()
                    if stopped:
                        _kill(process)
                        break
                    _lease(directory)
                    self.stop.wait(1)
            result_path = directory / "result.json"
            result = (
                json.loads(result_path.read_text())
                if result_path.is_file() and result_path.stat().st_size < 5 * 1024 * 1024
                else {}
            )
            with self.factory() as db:
                current = db.get(SimulationJob, identifier)
                current.events = _events(directory)
                current.elapsed_seconds = prior_elapsed + time.monotonic() - started
                current.finished_at = datetime.now(UTC)
                current.lease_owner, current.lease_expires_at = None, None
                current.result = _final_result(
                    current.result,
                    result,
                    current.elapsed_seconds,
                    succeeded=not stopped and bool(result.get("ok")) and process.returncode == 0,
                )
                if stopped:
                    current.state, current.error = (
                        stopped,
                        f"Simulation {stopped}; completed stages and engine artifacts are retained",
                    )
                    current.result = {**current.result, "trainingEligible": False}
                elif result.get("ok") and process.returncode == 0:
                    current.state, current.error = "completed", None
                else:
                    current.state, current.error = (
                        "failed",
                        result.get("error", "Native worker exited without a complete result"),
                    )
                    current.result = {**current.result, "trainingEligible": False}
                db.commit()
        except Exception as exc:
            if process:
                _kill(process)
            with self.factory() as db:
                current = db.get(SimulationJob, identifier)
                current.state, current.error = (
                    "failed",
                    f"Simulation worker failed ({type(exc).__name__}); raw artifacts are retained",
                )
                current.elapsed_seconds = prior_elapsed + time.monotonic() - started
                current.finished_at = datetime.now(UTC)
                current.result = {
                    **current.result,
                    "elapsedSeconds": current.elapsed_seconds,
                    "trainingEligible": False,
                }
                current.lease_owner, current.lease_expires_at = None, None
                db.commit()
        finally:
            if process:
                _kill(process)


def start_simulation_dispatcher(app: Any) -> None:
    dispatcher = SimulationDispatcher(app.state.session_factory, app.state.settings)
    app.state.simulation_dispatcher = dispatcher
    dispatcher.start()


def stop_simulation_dispatcher(app: Any) -> None:
    dispatcher = getattr(app.state, "simulation_dispatcher", None)
    if dispatcher:
        dispatcher.shutdown()
