"""Owner setup and login (§21.2).

One-time owner creation without a hardcoded password; argon2id password
hashing; role→capability grants.
"""

from __future__ import annotations

import uuid

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Principal,
    PrincipalCapability,
    Workspace,
)

_hasher = PasswordHasher()  # argon2id, library defaults


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise DomainError(ErrorCode.VALIDATION, "password must be at least 10 characters")
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        _hasher.verify(stored_hash, password)
        return True
    except (VerifyMismatchError, VerificationError):
        return False


def workspace_has_owner(db: Session, workspace_id: uuid.UUID) -> bool:
    return (
        db.execute(
            select(func.count(PrincipalCapability.id)).where(
                PrincipalCapability.workspace_id == workspace_id,
                PrincipalCapability.capability == "administer_workspace",
                PrincipalCapability.revoked_at.is_(None),
            )
        ).scalar_one()
        > 0
    )


def create_owner(
    db: Session,
    workspace: Workspace,
    login: str,
    display_name: str,
    password: str,
) -> Principal:
    """One-time owner bootstrap. Refuses when an owner already exists."""
    if workspace_has_owner(db, workspace.id):
        raise DomainError(ErrorCode.CONFLICT, "workspace already has an owner")
    principal = Principal(
        workspace_id=workspace.id,
        kind="user",
        login=login,
        display_name=display_name,
        credential_hash=hash_password(password),
    )
    db.add(principal)
    db.flush()
    grant_capabilities(db, workspace.id, principal, "owner", granted_by=principal.id)
    return principal


def grant_capabilities(
    db: Session,
    workspace_id: uuid.UUID,
    principal: Principal,
    role: str,
    granted_by: uuid.UUID | None,
) -> None:
    for cap in sorted(capabilities_for_role(role)):
        db.add(
            PrincipalCapability(
                workspace_id=workspace_id,
                principal_id=principal.id,
                capability=cap,
                scope_ref=None,
                granted_by=granted_by,
            )
        )
    db.flush()


def authenticate_password(
    db: Session, workspace_id: uuid.UUID, login: str, password: str
) -> Principal:
    principal = db.execute(
        select(Principal).where(
            Principal.workspace_id == workspace_id,
            Principal.login == login,
            Principal.kind == "user",
            Principal.disabled_at.is_(None),
        )
    ).scalar_one_or_none()
    if principal is None or principal.credential_hash is None:
        raise DomainError(ErrorCode.UNAUTHENTICATED, "invalid credentials")
    if not verify_password(principal.credential_hash, password):
        raise DomainError(ErrorCode.UNAUTHENTICATED, "invalid credentials")
    return principal
