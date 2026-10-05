"""Approval envelopes (§7.4).

An approval binds: principal, action, the exact bound-input digest,
policy version, permitted envelope and expiry. It never binds to a
mutable task id. Re-validation happens at *execution* time — not only
at request time — so a stale, expired or revoked approval blocks the
action even if it was valid when the request was queued.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from chem_studio_policy.capabilities import (
    CAP_APPROVE_EXPERIMENT,
    CAP_APPROVE_EXPORT,
    CAP_APPROVE_MODEL,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.application.idempotency import request_digest
from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext
from studio.errors import DomainError, ErrorCode, forbidden
from studio.persistence.models import Approval

# Which capability may grant an approval for a given action (§21.1).
APPROVAL_CAPABILITY: dict[str, str] = {
    "experiment_release": CAP_APPROVE_EXPERIMENT,
    "model_release": CAP_APPROVE_MODEL,
    "export": CAP_APPROVE_EXPORT,
}


def bound_digest(bound_inputs: dict[str, Any]) -> str:
    """sha256 over the canonical bound-input document — exact revisions,
    contract revision, method/policy versions, envelope, recipient."""
    return request_digest(bound_inputs)


def grant(
    db: Session,
    ctx: ServiceContext,
    *,
    action: str,
    bound_inputs: dict[str, Any],
    decision: str = "approved",
    ttl_seconds: int | None = None,
    envelope: dict[str, Any] | None = None,
    policy_version: str = "1.0",
    rationale: str | None = None,
    capability: str | None = None,
) -> Approval:
    """Record an approval decision. Granting requires the approval
    capability for the action (agents can never hold it)."""
    required = capability or APPROVAL_CAPABILITY.get(action)
    if required is None:
        raise DomainError(ErrorCode.VALIDATION, f"no approval capability defined for '{action}'")
    ctx.require(required)
    if decision not in ("approved", "rejected"):
        raise DomainError(ErrorCode.VALIDATION, "decision must be approved|rejected")
    approval = Approval(
        workspace_id=ctx.workspace_id,
        action=action,
        decision=decision,
        decided_by=ctx.principal_id,
        bound_digest=bound_digest(bound_inputs),
        bound_inputs=bound_inputs,
        policy_version=policy_version,
        envelope=envelope,
        rationale=rationale,
        expires_at=(
            datetime.now(UTC) + timedelta(seconds=ttl_seconds) if ttl_seconds is not None else None
        ),
    )
    db.add(approval)
    db.flush()
    audit_record(
        db,
        ctx,
        action="approval.grant",
        target_type="approval",
        target_id=approval.id,
        detail={"action": action, "decision": decision},
    )
    return approval


def require_valid(
    db: Session,
    ctx: ServiceContext,
    *,
    action: str,
    bound_inputs: dict[str, Any],
    now: datetime | None = None,
) -> Approval:
    """Re-validate the newest approval for ``action`` at execution.

    Order matters: a revoked approval is forbidden outright; expiry and
    bound-digest drift are their own typed codes so the client can act
    on them (re-request vs fix inputs).
    """
    approval = db.execute(
        select(Approval)
        .where(Approval.workspace_id == ctx.workspace_id, Approval.action == action)
        .order_by(Approval.created_at.desc(), Approval.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if approval is None or approval.decision != "approved":
        raise forbidden(f"approval for '{action}'")
    if approval.revoked_at is not None:
        raise forbidden(f"approval for '{action}' (revoked)")
    now = now or datetime.now(UTC)
    expires = approval.expires_at
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires <= now:
            raise DomainError(
                ErrorCode.APPROVAL_EXPIRED,
                "the approval for this action has expired; request a new one",
                retryable=False,
            )
    if approval.bound_digest != bound_digest(bound_inputs):
        raise DomainError(
            ErrorCode.APPROVAL_STALE,
            "bound inputs changed since approval; request a fresh approval",
            safe_details={"approvalId": str(approval.id)},
        )
    audit_record(
        db,
        ctx,
        action="approval.use",
        target_type="approval",
        target_id=approval.id,
        detail={"action": action},
    )
    return approval


def revoke(
    db: Session,
    ctx: ServiceContext,
    *,
    approval_id: uuid.UUID,
    capability: str | None = None,
) -> Approval:
    approval = db.execute(
        select(Approval).where(
            Approval.id == approval_id,
            Approval.workspace_id == ctx.workspace_id,
        )
    ).scalar_one_or_none()
    if approval is None:
        from studio.errors import not_found

        raise not_found("approval")
    required = capability or APPROVAL_CAPABILITY.get(approval.action)
    if required is not None:
        ctx.require(required)
    approval.revoked_at = datetime.now(UTC)
    db.flush()
    audit_record(
        db,
        ctx,
        action="approval.revoke",
        target_type="approval",
        target_id=approval.id,
        detail={"action": approval.action},
    )
    return approval
