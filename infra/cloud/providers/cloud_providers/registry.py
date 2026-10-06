"""Provider registration + honest capability reporting (CS-1004).

A confidential provider exists only where an owner approval binds a
concrete provider/account/region/environment. ``register`` refuses
missing, expired, or wrongly-scoped approval references, so the surface
can never silently become configured.

Until a live provider registers, ``confidential_capability`` reports
``not_configured`` — the truthful state of this deployment while
U08/U09/U11 remain open. Synthetic doubles are inventoried honestly and
never flip the status.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from cloud_broker.providers import ProviderNotConfigured
from cloud_providers.adapter import ConfidentialExecutionAdapter
from cloud_providers.backend import ConfidentialBackend
from cloud_providers.types import (
    ApprovalRef,
    ApprovedEnvironment,
)

# The approval capability an owner must hold to bind a cloud provider.
APPROVAL_CAPABILITY = "approve_export"

# Registered adapters keyed by provider name. Empty on a fresh
# deployment — honest ``not_configured``.
CONFIDENTIAL_ADAPTERS: dict[str, ConfidentialExecutionAdapter] = {}


class ApprovalRequired(Exception):
    """Registration attempted without a valid owner approval."""


def _bound_subject(spec: ApprovedEnvironment) -> str:
    return f"cloud_provider:{spec.provider}/{spec.account}/{spec.region}/{spec.environment}"


def register(
    *,
    spec: ApprovedEnvironment,
    approval: ApprovalRef | None,
    backend: ConfidentialBackend,
    now: datetime | None = None,
) -> ConfidentialExecutionAdapter:
    """Register a confidential adapter behind an owner approval.

    Refuses (ApprovalRequired) when the approval is missing, expired,
    not scoped to ``approve_export``, or bound to a different subject.
    """
    now = now or datetime.now(UTC)
    if approval is None:
        raise ApprovalRequired(
            "no owner approval supplied — the confidential-execution surface stays not_configured"
        )
    if approval.capability != APPROVAL_CAPABILITY:
        raise ApprovalRequired(
            f"approval capability {approval.capability!r} does not bind "
            f"cloud providers (requires {APPROVAL_CAPABILITY!r})"
        )
    if approval.expiry <= now:
        raise ApprovalRequired(
            f"approval {approval.digest} expired at {approval.expiry.isoformat()}"
        )
    if approval.bound != _bound_subject(spec):
        raise ApprovalRequired(
            "approval binds a different subject "
            f"({approval.bound!r} != {_bound_subject(spec)!r}) — refusing "
            "to register an adapter outside its approval"
        )
    adapter = ConfidentialExecutionAdapter(backend=backend, environment=spec, approval=approval)
    CONFIDENTIAL_ADAPTERS[spec.provider] = adapter
    return adapter


def resolve(provider: str) -> ConfidentialExecutionAdapter:
    """Return the registered adapter — ProviderNotConfigured if absent."""
    adapter = CONFIDENTIAL_ADAPTERS.get(provider)
    if adapter is None:
        raise ProviderNotConfigured(provider)
    return adapter


def clear() -> None:
    """Test hook: reset the registry to the empty honest state."""
    CONFIDENTIAL_ADAPTERS.clear()


def confidential_capability() -> dict[str, Any]:
    """Honest capability card for the confidential-execution surface.

    ``status`` answers the real question — can this deployment emit an
    approved payload to a live owner-approved provider? Only a
    ``kind="live"`` backend behind a valid approval flips it.
    """
    live = [adapter for adapter in CONFIDENTIAL_ADAPTERS.values() if adapter.kind == "live"]
    synthetic = [
        adapter.name for adapter in CONFIDENTIAL_ADAPTERS.values() if adapter.kind == "synthetic"
    ]
    status = "configured" if live else "not_configured"
    detail = (
        f"owner-approved confidential provider bound ({len(live)})"
        if live
        else "no owner-approved provider/account/region is bound "
        "(U08/U09/U11 open); the confidential-execution surface is inert"
    )
    return {
        "status": status,
        "live": bool(live),
        "providers": [
            {
                "name": a.name,
                "environment": a.environment.environment,
                "approved_by": a.approval.approver,
                "approval_digest": a.approval.digest,
            }
            for a in live
        ],
        "synthetic_adapters": sorted(synthetic),
        "egress": "deny" if not live else "via_broker",
        "detail": detail,
    }
