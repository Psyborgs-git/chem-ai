"""Scoped service context (handoff §21.1).

Every application service executes inside a ``ServiceContext`` carrying
the authenticated principal, its workspace, and its effective grants.
Authorization is enforced here — resolvers never decide permissions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from chem_studio_policy.capabilities import (
    Grant,
    effective_grants,
    has_capability,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.errors import DomainError, ErrorCode, forbidden
from studio.persistence.models import Principal, PrincipalCapability


@dataclass(frozen=True)
class ServiceContext:
    """Immutable per-request authorization context."""

    session: Session
    workspace_id: uuid.UUID
    principal_id: uuid.UUID
    principal_kind: str
    grants: frozenset[Grant]
    auth_session_id: uuid.UUID | None = None

    def require(self, capability: str, scope_ref: uuid.UUID | None = None) -> None:
        ref = str(scope_ref) if scope_ref else None
        if not has_capability(self.grants, capability, ref):
            raise forbidden(f"capability '{capability}'")

    def has(self, capability: str, scope_ref: uuid.UUID | None = None) -> bool:
        ref = str(scope_ref) if scope_ref else None
        return has_capability(self.grants, capability, ref)


def load_context(
    session: Session,
    workspace_id: uuid.UUID,
    principal_id: uuid.UUID,
    auth_session_id: uuid.UUID | None = None,
) -> ServiceContext:
    """Build a ServiceContext from persisted grants.

    The principal must belong to the same workspace — a principal id
    from another workspace cannot be smuggled into this scope.
    """
    principal = session.execute(
        select(Principal).where(
            Principal.id == principal_id,
            Principal.workspace_id == workspace_id,
            Principal.disabled_at.is_(None),
        )
    ).scalar_one_or_none()
    if principal is None:
        raise DomainError(ErrorCode.UNAUTHENTICATED, "principal not recognized")

    rows = session.execute(
        select(PrincipalCapability).where(
            PrincipalCapability.principal_id == principal.id,
            PrincipalCapability.workspace_id == workspace_id,
            PrincipalCapability.revoked_at.is_(None),
        )
    ).scalars()
    grants = frozenset(
        Grant(capability=r.capability, scope_ref=str(r.scope_ref) if r.scope_ref else None)
        for r in rows
    )
    return ServiceContext(
        session=session,
        workspace_id=workspace_id,
        principal_id=principal.id,
        principal_kind=principal.kind,
        grants=effective_grants(principal.kind, grants),
        auth_session_id=auth_session_id,
    )
