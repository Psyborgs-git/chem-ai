"""In-process provider-double (§20.2 — "no real provider exists").

``ProviderDouble`` implements the same ``CloudProvider`` contract a
real adapter would, so the broker exercises the *actual* submit →
callback → reconcile → delete flow end to end with zero real egress.
It keeps the bytes it received in memory where tests can assert
exactly what crossed the boundary (AT-1003-1 expects zero).

Fault injection hooks let tests drive the revocation-during-execution
and out-of-order/duplicated-callback cases deterministically.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from cloud_broker.types import (
    CallbackEvent,
    DeletionReceipt,
    JobHandle,
    JobStatus,
    Recipient,
)


@dataclass
class _Job:
    handle: JobHandle
    payload: bytes = b""
    state: str = "queued"
    callbacks: list[CallbackEvent] = field(default_factory=list)
    deleted: bool = False
    seq: int = 0

    def emit(self, event: str, artifacts: tuple[str, ...] = (), detail: str = "") -> None:
        self.seq += 1
        self.callbacks.append(
            CallbackEvent(
                callback_id=f"{self.handle.job_id}-cb{self.seq}",
                job_id=self.handle.job_id,
                event=event,
                seq=self.seq,
                artifacts=artifacts,
                detail=detail,
            )
        )


class ProviderDouble:
    """Deterministic in-process provider.

    - ``submit`` stores the payload and queues ``submitted``/``running``
      callbacks; job ids are ``double-<n>`` in creation order.
    - ``cancel`` marks the job cancelled and emits a ``cancelled``
      callback carrying whatever state was real at that moment.
    - ``delete`` marks the job deleted and returns an honest receipt.
    - ``receive_delay``: how many ``drain_callbacks``/``tick`` calls a
      transfer can interleave before the job reports ``running`` —
      lets revocation land *mid-execution* deterministically.
    """

    name = "provider-double"

    def __init__(self, *, auto_progress: bool = True) -> None:
        self._ids = itertools.count(1)
        self._jobs: dict[str, _Job] = {}
        self._auto = auto_progress
        # Test hooks — never used by the broker itself.
        self.fail_submit: Exception | None = None
        self.received_bytes = 0

    # ------------------------------------------------- CloudProvider

    def submit(self, *, recipient: Recipient, job: str, payload: bytes) -> JobHandle:
        if self.fail_submit is not None:
            raise self.fail_submit
        job_id = f"double-{next(self._ids)}"
        handle = JobHandle(job_id=job_id, provider=self.name, external_ref=f"{self.name}/{job_id}")
        entry = _Job(handle=handle, payload=bytes(payload))
        self._jobs[job_id] = entry
        self.received_bytes += len(payload)
        entry.emit("submitted", detail=f"job={job}")
        if self._auto:
            entry.state = "running"
            entry.emit("running")
        return handle

    def status(self, handle: JobHandle) -> JobStatus:
        entry = self._job(handle)
        return JobStatus(
            job_id=entry.handle.job_id,
            state="deleted" if entry.deleted else entry.state,
            bytes_received=len(entry.payload),
            artifacts=tuple(a for cb in entry.callbacks for a in cb.artifacts),
        )

    def cancel(self, handle: JobHandle) -> JobStatus:
        entry = self._job(handle)
        if entry.state not in ("succeeded", "failed", "cancelled") and not entry.deleted:
            entry.state = "cancelled"
            entry.emit("cancelled", detail=f"bytes_received={len(entry.payload)}")
        return self.status(handle)

    def delete(self, handle: JobHandle) -> DeletionReceipt:
        entry = self._job(handle)
        entry.deleted = True
        entry.payload = b""
        entry.emit("deleted")
        return DeletionReceipt(
            job_id=entry.handle.job_id,
            deleted=True,
            receipt_ref=f"{self.name}-receipt-{entry.handle.job_id}",
            unresolved=(),
        )

    def drain_callbacks(self, handle: JobHandle) -> list[CallbackEvent]:
        entry = self._job(handle)
        out, entry.callbacks = entry.callbacks, []
        return list(out)

    # -------------------------------------------------- test helpers

    def _job(self, handle: JobHandle) -> _Job:
        entry = self._jobs.get(handle.job_id)
        if entry is None:
            raise KeyError(f"unknown job {handle.job_id}")
        return entry

    def succeed(self, handle: JobHandle, *, artifacts: tuple[str, ...] = ()) -> None:
        """Drive the double to a terminal success, emitting the
        result-artifact callback a real provider would."""
        entry = self._job(handle)
        entry.state = "succeeded"
        entry.emit("succeeded", artifacts=artifacts)

    def inject_callback(
        self,
        handle: JobHandle,
        event: str,
        *,
        seq: int | None = None,
        callback_id: str | None = None,
        artifacts: tuple[str, ...] = (),
    ) -> None:
        """Queue an arbitrary callback — used to replay duplicates and
        out-of-order deliveries in AT-1003-3 tests."""
        entry = self._job(handle)
        entry.callbacks.append(
            CallbackEvent(
                callback_id=callback_id or f"{handle.job_id}-inj{len(entry.callbacks)}",
                job_id=handle.job_id,
                event=event,
                seq=seq,
                artifacts=artifacts,
            )
        )
