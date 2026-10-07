"""Typed domain errors (handoff §8.3).

Services raise ``DomainError``; the API layer serializes it. Raw paths,
credentials, tool stdout and SQL stack traces never reach clients.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    IDEMPOTENCY_MISMATCH = "IDEMPOTENCY_MISMATCH"
    INVALID_UNIT = "INVALID_UNIT"
    UNKNOWN_BASIS = "UNKNOWN_BASIS"
    COMPOSITION_TOTAL_INVALID = "COMPOSITION_TOTAL_INVALID"
    MISSING_IDENTITY = "MISSING_IDENTITY"
    METHOD_INCOMPATIBLE = "METHOD_INCOMPATIBLE"
    METRIC_NOT_DEFINED = "METRIC_NOT_DEFINED"
    EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"
    QUALITY_REVIEW_REQUIRED = "QUALITY_REVIEW_REQUIRED"
    SAFETY_REVIEW_REQUIRED = "SAFETY_REVIEW_REQUIRED"
    APPROVAL_STALE = "APPROVAL_STALE"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    ENGINE_UNAVAILABLE = "ENGINE_UNAVAILABLE"
    ENGINE_UNSUPPORTED_INPUT = "ENGINE_UNSUPPORTED_INPUT"
    NONCONVERGED = "NONCONVERGED"
    RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"
    LOCAL_INFEASIBLE = "LOCAL_INFEASIBLE"
    EXPORT_NOT_APPROVED = "EXPORT_NOT_APPROVED"
    EXPORT_DIGEST_MISMATCH = "EXPORT_DIGEST_MISMATCH"
    DATA_RIGHTS_UNKNOWN = "DATA_RIGHTS_UNKNOWN"
    PROVENANCE_UNKNOWN = "PROVENANCE_UNKNOWN"
    EVAL_CONTAMINATION = "EVAL_CONTAMINATION"
    MODEL_NOT_PROMOTABLE = "MODEL_NOT_PROMOTABLE"
    MODEL_INCOMPATIBLE = "MODEL_INCOMPATIBLE"
    RUN_ALREADY_TERMINAL = "RUN_ALREADY_TERMINAL"
    VALIDATION = "VALIDATION"
    CONFLICT = "CONFLICT"


@dataclass
class DomainError(Exception):
    """One typed, client-safe error entry."""

    code: ErrorCode
    message: str
    field_path: str | None = None
    retryable: bool = False
    safe_details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover - debugging aid
        return f"{self.code}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": str(self.code),
            "message": self.message,
            "fieldPath": self.field_path,
            "retryable": self.retryable,
            "safeDetails": self.safe_details,
        }


def not_found(what: str = "record") -> DomainError:
    return DomainError(ErrorCode.NOT_FOUND, f"{what} not found or not accessible")


def forbidden(what: str = "action") -> DomainError:
    return DomainError(ErrorCode.FORBIDDEN, f"{what} is not permitted for this principal")


def revision_conflict(what: str = "record") -> DomainError:
    return DomainError(
        ErrorCode.REVISION_CONFLICT,
        f"{what} changed since the expected version; reload and retry",
        retryable=True,
    )
