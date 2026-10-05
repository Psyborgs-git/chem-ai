"""Resource admission and budgets (§13.4, §20.1, §23.3).

Admission is decided against *observed* capacity minus a configured
reserve — headroom that keeps the OS/API/UI responsive while heavy work
runs (AT-0402-2). A denied admission is a ``blocked`` decision with
explicit per-dimension reasons and an ``export_review_proposal`` next
step: a proposal for human review, never an automatic submission and
never a cloud route (AT-0402-3, §20.1).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext
from studio.domain.runs.queue import RunService
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import (
    ResourceGroup,
    ResourceReservation,
    Run,
)

ENVELOPE_FIELDS = ("cpu_cores", "memory_bytes", "gpu_devices", "storage_bytes")
MAX_WALL_SECONDS = 7 * 24 * 3600  # a week — queued jobs carry budget caps (§13.4)
MAX_ENVELOPE_BYTES = 4096


@dataclass
class AdmissionDecision:
    admitted: bool
    run_id: uuid.UUID
    group: str | None = None
    reasons: list[dict[str, Any]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    # What a human may do next — a *proposal* for review. This is not
    # and cannot be a submission: no provider is configured (§20.2).
    next_step: str | None = None


def validate_envelope(envelope: dict[str, Any]) -> dict[str, int]:
    """Bounds-check an envelope: integer amounts only, no negative or
    unbounded requests, wall_seconds capped (§13.4)."""
    if not isinstance(envelope, dict):
        raise DomainError(ErrorCode.VALIDATION, "envelope must be an object")
    out: dict[str, int] = {}
    for dim in ENVELOPE_FIELDS:
        raw = envelope.get(dim, 0)
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"envelope.{dim} must be a non-negative integer",
                field_path=f"envelope.{dim}",
            )
        out[dim] = raw
    wall = envelope.get("wall_seconds", 3600)
    if not isinstance(wall, int) or isinstance(wall, bool) or wall <= 0 or wall > MAX_WALL_SECONDS:
        raise DomainError(
            ErrorCode.VALIDATION,
            f"envelope.wall_seconds must be 1-{MAX_WALL_SECONDS}",
            field_path="envelope.wall_seconds",
        )
    out["wall_seconds"] = wall
    return out


class AdmissionService:
    """Transactional admission: the group row is locked ``FOR UPDATE``
    while used capacity is summed, so two admissions can never oversell
    the same envelope."""

    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    # -- group management ----------------------------------------------

    def ensure_group(
        self,
        name: str,
        *,
        capacity: dict[str, Any],
        reserve: dict[str, Any] | None = None,
    ) -> ResourceGroup:
        group = self.db.execute(
            select(ResourceGroup).where(
                ResourceGroup.workspace_id == self.ctx.workspace_id,
                ResourceGroup.name == name,
            )
        ).scalar_one_or_none()
        if group is None:
            group = ResourceGroup(
                workspace_id=self.ctx.workspace_id,
                name=name,
                capacity=capacity,
                reserve=reserve or {},
            )
            self.db.add(group)
            self.db.flush()
        else:
            group.capacity = capacity
            if reserve is not None:
                group.reserve = reserve
            self.db.flush()
        return group

    def groups(self) -> list[ResourceGroup]:
        return list(
            self.db.execute(
                select(ResourceGroup).where(ResourceGroup.workspace_id == self.ctx.workspace_id)
            )
            .scalars()
            .all()
        )

    # -- admission ------------------------------------------------------

    def admit(
        self,
        run_id: uuid.UUID,
        envelope: dict[str, Any],
        *,
        group_name: str = "compute",
        queue_name: str = "runs",
    ) -> AdmissionDecision:
        """Decide and (on success) reserve + enqueue atomically.

        On failure the run becomes ``blocked`` with per-dimension
        reasons; ``next_step`` is an export-review *proposal* — no
        provider, payload, or network target exists here (§20.1-20.2)."""
        env = validate_envelope(envelope)
        runs = RunService(self.db, self.ctx)
        run = self.db.execute(
            select(Run)
            .where(Run.workspace_id == self.ctx.workspace_id, Run.id == run_id)
            .with_for_update()
        ).scalar_one_or_none()
        if run is None:
            raise not_found("run")
        group = self.db.execute(
            select(ResourceGroup)
            .where(
                ResourceGroup.workspace_id == self.ctx.workspace_id,
                ResourceGroup.name == group_name,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if group is None:
            return self._deny(
                runs,
                run,
                reasons=[{"dimension": "group", "detail": f"no group '{group_name}'"}],
                missing=[group_name],
            )
        reasons, missing = self._check(env, group)
        if reasons or missing:
            return self._deny(runs, run, reasons=reasons, missing=missing)
        reservation = ResourceReservation(
            workspace_id=self.ctx.workspace_id,
            group_id=group.id,
            run_id=run.id,
            envelope=env,
            expires_at=datetime.now(UTC) + timedelta(seconds=env["wall_seconds"]),
        )
        self.db.add(reservation)
        self.db.flush()
        runs.enqueue(run.id, queue_name=queue_name)
        audit_record(
            self.db,
            self.ctx,
            action="run.admitted",
            target_type="run",
            target_id=run.id,
            detail={"group": group_name, "envelope": env},
        )
        return AdmissionDecision(admitted=True, run_id=run.id, group=group_name)

    def release(self, run_id: uuid.UUID) -> int:
        """Release active reservations for a run (called when it leaves
        the queue or terminates). Returns the number released."""
        now = datetime.now(UTC)
        rows = (
            self.db.execute(
                select(ResourceReservation).where(
                    ResourceReservation.workspace_id == self.ctx.workspace_id,
                    ResourceReservation.run_id == run_id,
                    ResourceReservation.status == "active",
                )
            )
            .scalars()
            .all()
        )
        for r in rows:
            r.status = "released"
            r.released_at = now
        if rows:
            self.db.flush()
        return len(rows)

    def sweep_expired(self) -> int:
        """Mark reservations past expiry — a lost worker cannot hold
        capacity forever; expiry releases it for later admissions."""
        now = datetime.now(UTC)
        rows = (
            self.db.execute(
                select(ResourceReservation).where(
                    ResourceReservation.workspace_id == self.ctx.workspace_id,
                    ResourceReservation.status == "active",
                    ResourceReservation.expires_at.is_not(None),
                    ResourceReservation.expires_at < now,
                )
            )
            .scalars()
            .all()
        )
        for r in rows:
            r.status = "expired"
            r.released_at = now
        if rows:
            self.db.flush()
        return len(rows)

    def utilization(self, group_name: str = "compute") -> dict[str, Any]:
        """Observed utilization for reporting: capacity, reserve and the
        sum of live reservations per dimension."""
        group = self.db.execute(
            select(ResourceGroup).where(
                ResourceGroup.workspace_id == self.ctx.workspace_id,
                ResourceGroup.name == group_name,
            )
        ).scalar_one_or_none()
        if group is None:
            raise not_found("resource group")
        return {
            "group": group_name,
            "capacity": dict(group.capacity),
            "reserve": dict(group.reserve),
            "reserved": self._reserved(group),
        }

    # -- internals ------------------------------------------------------

    def _reserved(self, group: ResourceGroup) -> dict[str, int]:
        now = datetime.now(UTC)
        rows = (
            self.db.execute(
                select(ResourceReservation).where(
                    ResourceReservation.workspace_id == self.ctx.workspace_id,
                    ResourceReservation.group_id == group.id,
                    ResourceReservation.status == "active",
                )
            )
            .scalars()
            .all()
        )
        used = {d: 0 for d in ENVELOPE_FIELDS}
        used["concurrency"] = 0
        for r in rows:
            if r.expires_at is not None and r.expires_at < now:
                continue  # expired holds do not count (sweep marks them)
            for dim in ENVELOPE_FIELDS:
                used[dim] += int(r.envelope.get(dim, 0))
            used["concurrency"] += 1
        return used

    def _check(
        self, env: dict[str, int], group: ResourceGroup
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Compare envelope against capacity - reserve - reserved, per
        dimension. An unobserved capacity dimension (None) is a
        *missing* capability — never assumed sufficient."""
        cap, res = group.capacity, group.reserve
        used = self._reserved(group)
        reasons: list[dict[str, Any]] = []
        missing: list[str] = []
        for dim in ENVELOPE_FIELDS:
            want = env[dim]
            if want == 0:
                continue
            total = cap.get(dim)
            if total is None:
                missing.append(dim)
                continue
            headroom = int(res.get(dim, 0))
            available = int(total) - headroom - used[dim]
            if want > available:
                reasons.append(
                    {
                        "dimension": dim,
                        "required": want,
                        "available": max(available, 0),
                        "capacity": total,
                        "reserve": headroom,
                        "reserved": used[dim],
                    }
                )
        concurrency = int(cap.get("concurrency", 1))
        if used["concurrency"] + 1 > concurrency:
            reasons.append(
                {
                    "dimension": "concurrency",
                    "required": used["concurrency"] + 1,
                    "available": max(concurrency - used["concurrency"], 0),
                    "capacity": concurrency,
                    "reserved": used["concurrency"],
                }
            )
        return reasons, missing

    def _deny(
        self,
        runs: RunService,
        run: Run,
        *,
        reasons: list[dict[str, Any]],
        missing: list[str],
    ) -> AdmissionDecision:
        """Record a blocked admission: explicit reasons, honest next
        step. There is no cloud path in this codebase to fall through
        to — the only legal follow-up is a human export review."""
        detail = {"reasons": reasons, "missing": missing}
        if run.status in ("requested", "awaiting_approval"):
            runs.block(run.id, reason="insufficient_local_resources", detail=detail)
        audit_record(
            self.db,
            self.ctx,
            action="run.admission_denied",
            target_type="run",
            target_id=run.id,
            detail=detail,
        )
        return AdmissionDecision(
            admitted=False,
            run_id=run.id,
            reasons=reasons,
            missing=missing,
            next_step="export_review_proposal",
        )
