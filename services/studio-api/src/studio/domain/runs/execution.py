"""Attempt execution glue (§13.3-13.5).

Ties the queue's authoritative Run records to an isolated backend:
admit -> execute attempt -> translate the result into run semantics.
A zero exit code alone is NOT scientific success — the executor must
return a parseable structured result or the attempt fails with an
explicit state. On cancellation the reservation is released in the
same transaction as the terminal cancellation (AT-0403-2).
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

from sqlalchemy.orm import Session
from workers.common.executor import ExecLimits, ExecutionBackend

from studio.auth.context import ServiceContext
from studio.domain.runs.admission import AdmissionService
from studio.domain.runs.queue import RunService


class AttemptExecutor:
    """Run one queued attempt inside an isolation backend."""

    def __init__(
        self,
        db: Session,
        ctx: ServiceContext,
        backend: ExecutionBackend,
        worker_id: str | None = None,
    ) -> None:
        self.db = db
        self.ctx = ctx
        self.backend = backend
        self.worker_id = worker_id
        self.runs = RunService(db, ctx)
        self.admission = AdmissionService(db, ctx)

    def execute(
        self,
        *,
        run_id: uuid.UUID,
        attempt_id: uuid.UUID,
        argv: list[str],
        inputs: dict[str, bytes] | None = None,
        limits: ExecLimits | None = None,
        external_id: str | None = None,
        cancel: threading.Event | None = None,
    ) -> Any:
        """Execute argv in isolation; map the outcome onto the run.

        - exit 0 + parseable JSON result -> succeeded (result persisted)
        - cancelled event -> cancelled terminal + reservation release
        - timeout -> timed_out (watchdog cancelled the attempt)
        - anything else -> failed with the executor's reported state
        """
        profile = self.backend.profile
        if not profile.enforces("argv_only_no_shell"):
            return self.runs.fail_attempt(
                run_id=run_id,
                attempt_id=attempt_id,
                code="profile_unavailable",
                message="backend cannot honor argv-only execution",
                retryable=False,
            )
        self.runs.accept_attempt(
            run_id=run_id,
            attempt_id=attempt_id,
            external_id=external_id or f"local-{attempt_id}",
            worker_id=self.worker_id,
        )
        self.runs.start_attempt(run_id=run_id, attempt_id=attempt_id, worker_id=self.worker_id)
        result = self.backend.run(
            argv,
            inputs=inputs or {},
            limits=limits or ExecLimits(),
            cancel=cancel,
        )
        if result.cancelled or (cancel is not None and cancel.is_set()):
            # Reservation release rides the same transaction as the
            # terminal cancellation (§13.5, AT-0403-2).
            self.runs.confirm_cancelled(run_id)
            self.admission.release(run_id)
            return self.runs.get(run_id)
        if result.timed_out:
            self.admission.release(run_id)
            return self.runs.timeout_attempt(run_id=run_id, attempt_id=attempt_id)
        parsed = result.json_stdout()
        if result.exit_code == 0 and parsed is not None:
            self.admission.release(run_id)
            return self.runs.complete_attempt(
                run_id=run_id,
                attempt_id=attempt_id,
                result_summary={
                    "result": parsed,
                    "files": result.scratch_files,
                    "truncated": result.truncated,
                    "wall_seconds": round(result.wall_seconds, 3),
                    "profile": result.profile.backend,
                },
            )
        self.admission.release(run_id)
        return self.runs.fail_attempt(
            run_id=run_id,
            attempt_id=attempt_id,
            code=f"exit_{result.exit_code}" if result.exit_code is not None else "no_result",
            message=(
                "process produced no parseable structured result — exit "
                "code alone is not scientific success (§7.3); "
                f"stderr tail: {result.stderr[-300:]}"
            ),
            retryable=False,
        )
