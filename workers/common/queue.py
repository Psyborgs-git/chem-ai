"""Queue bridge (§13.1-13.5).

Procrastinate supplies the queue primitives [S05]; this module owns the
application-level contract:

* Queue payloads carry *scoped record IDs and bounded metadata only* —
  workers re-load authoritative state from Run/attempt rows.
* ``defer_attempt`` returns the queue job id, which the caller persists
  on the attempt as ``external_id`` and reconciles before any retry.
* ``AttemptRunner`` is the in-process execution boundary the worker
  invokes for a dequeued payload; execution itself is delegated to an
  injected ``executor`` callable (engine adapters arrive in CS-0402+).

The ``InMemoryConnector`` path exists for tests and local development —
queue *semantics* (defer + job id) are real Procrastinate behavior; no
execution is simulated behind the queue boundary.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any, Protocol

import procrastinate

QUEUE_NAME = "runs"
TASK_NAME = "runs.execute_attempt"


def queue_payload(
    *, workspace_id: uuid.UUID, run_id: uuid.UUID, attempt_id: uuid.UUID
) -> dict[str, str]:
    """The complete queue payload — scoped IDs only (§7.4)."""
    return {
        "workspace_id": str(workspace_id),
        "run_id": str(run_id),
        "attempt_id": str(attempt_id),
    }


def make_app(connector: Any | None = None) -> procrastinate.App:
    """Build the Procrastinate app. ``connector`` defaults to the
    in-memory connector (tests/dev); production wiring passes a real
    Psycopg connector."""
    from procrastinate.testing import InMemoryConnector

    app = procrastinate.App(connector=connector or InMemoryConnector())

    @app.task(name=TASK_NAME, queue=QUEUE_NAME)
    def execute_attempt(workspace_id: str, run_id: str, attempt_id: str) -> None:
        # Bound at worker startup via ``AttemptRunner``; the task body
        # is never invoked without one.
        raise RuntimeError("no AttemptRunner bound to the queue app")

    return app


def defer_attempt(
    app: procrastinate.App,
    *,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    attempt_id: uuid.UUID,
) -> str:
    """Enqueue the attempt; returns the queue job id for ``external_id``."""
    task = app.tasks[TASK_NAME]
    job_id = task.configure().defer(
        **queue_payload(workspace_id=workspace_id, run_id=run_id, attempt_id=attempt_id)
    )
    return str(job_id)


class _RunOps(Protocol):
    """The slice of RunService the worker boundary needs."""

    def accept_attempt(
        self,
        *,
        run_id: uuid.UUID,
        attempt_id: uuid.UUID,
        external_id: str,
        worker_id: str | None = None,
    ) -> Any: ...

    def start_attempt(
        self, *, run_id: uuid.UUID, attempt_id: uuid.UUID, worker_id: str | None = None
    ) -> Any: ...

    def complete_attempt(
        self,
        *,
        run_id: uuid.UUID,
        attempt_id: uuid.UUID,
        result_summary: dict[str, Any] | None = None,
    ) -> Any: ...

    def fail_attempt(
        self,
        *,
        run_id: uuid.UUID,
        attempt_id: uuid.UUID,
        code: str,
        message: str,
        retryable: bool = False,
    ) -> Any: ...


class AttemptRunner:
    """Worker-side boundary for a dequeued queue payload.

    ``ops`` is a RunService (or the workspace-scoped equivalent);
    ``executor(run, attempt) -> dict | None`` performs the actual work
    and returns a result summary. Executors signal a classified
    transient infrastructure failure by raising ``TransientInfraError``;
    any other exception is a non-retryable failure (§13.4)."""

    def __init__(
        self,
        ops: _RunOps,
        executor: Callable[[Any, Any], dict[str, Any] | None] | None = None,
        worker_id: str | None = None,
    ) -> None:
        self.ops = ops
        self.executor = executor
        self.worker_id = worker_id

    def handle(
        self, *, workspace_id: uuid.UUID, run_id: uuid.UUID, attempt_id: uuid.UUID, external_id: str
    ) -> Any:
        """Accept (idempotent under redelivery) then execute one attempt."""
        attempt = self.ops.accept_attempt(
            run_id=run_id,
            attempt_id=attempt_id,
            external_id=external_id,
            worker_id=self.worker_id,
        )
        if attempt.status != "queued":
            return attempt  # redelivery of an already-accepted attempt
        self.ops.start_attempt(run_id=run_id, attempt_id=attempt_id, worker_id=self.worker_id)
        if self.executor is None:
            return self.ops.fail_attempt(
                run_id=run_id,
                attempt_id=attempt_id,
                code="no_executor",
                message="no engine adapter is configured for this run kind",
                retryable=False,
            )
        try:
            summary = self.executor(run_id, attempt)
        except TransientInfraError as exc:
            return self.ops.fail_attempt(
                run_id=run_id,
                attempt_id=attempt_id,
                code=exc.code,
                message=str(exc),
                retryable=True,
            )
        except Exception as exc:
            return self.ops.fail_attempt(
                run_id=run_id,
                attempt_id=attempt_id,
                code=type(exc).__name__,
                message=str(exc)[:500],
                retryable=False,
            )
        return self.ops.complete_attempt(
            run_id=run_id, attempt_id=attempt_id, result_summary=summary
        )


class TransientInfraError(Exception):
    """Classified transient infrastructure failure (§13.4) — the only
    exception an executor may raise that is eligible for bounded retry."""

    def __init__(self, message: str, code: str = "transient_infra") -> None:
        super().__init__(message)
        self.code = code
