"""Versioned, deliberately narrow eLabFTW bridge contract (CS-0506).

The ELN bridge is an OPTIONAL integration (handoff §14.3). Chemistry
Studio stays the authoritative system for its native records; the
adapter only ever performs explicit one-way export plus selective
import with version/hash mapping. There is no bidirectional
synchronization and no silent overwrite: any drift between a linked
remote record and the agreed baseline routes to REVIEW.

Configuration is opt-in and off by default (U16 decision):

- ``STUDIO_ELN_BASE_URL`` — eLabFTW instance URL (e.g.
  ``https://eln.example.org``). Never provisioned by the adapter.
- ``STUDIO_ELN_API_TOKEN`` — instance API key. Read from the
  environment, never defaulted, never echoed into results, logs or
  error payloads.
- ``STUDIO_ELN_ENABLED`` — explicit enable switch. Even a fully
  configured endpoint refuses to run until this is truthy.
- ``STUDIO_ELN_TIMEOUT_SECONDS`` — per-request timeout (default 10).

With no configuration the whole surface reports ``not_configured`` and
stays inert — the rest of the application cannot observe the adapter's
absence of config.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ADAPTER_VERSION: Literal["elabftw-adapter/v1"] = "elabftw-adapter/v1"

ELN_ENTITY_TYPES = ("experiments", "items")

# Configuration states — honest labels only; there is no "connected"
# state the adapter invents without an explicit enable + endpoint.
CONFIG_STATES = ("not_configured", "configured_disabled", "enabled")

# Link lifecycle states.
LINK_STATES = ("synced", "review_required", "stale")

_TRUE = {"1", "true", "yes", "on"}


def utcnow() -> datetime:
    return datetime.now(UTC)


def digest_doc(doc: dict[str, Any]) -> str:
    """Canonical sha256 over a JSON-serializable document."""
    return hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class ElnError(Exception):
    """Typed adapter refusal/failure — always {code, message}."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class ElnNotConfigured(ElnError):
    def __init__(self, message: str = "no eLabFTW instance is configured") -> None:
        super().__init__("ELN_NOT_CONFIGURED", message)


class ElnDisabled(ElnError):
    def __init__(self, message: str = "eLabFTW connectivity is disabled") -> None:
        super().__init__("ELN_DISABLED", message)


class ElnUnreachable(ElnError):
    def __init__(self, message: str = "eLabFTW instance is unreachable") -> None:
        super().__init__("ELN_UNREACHABLE", message)


class ElnBadResponse(ElnError):
    def __init__(self, message: str) -> None:
        super().__init__("ELN_BAD_RESPONSE", message)


class ElnInvalidInput(ElnError):
    def __init__(self, message: str) -> None:
        super().__init__("ELN_INVALID_INPUT", message)


# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------


@dataclass(frozen=True)
class ElnConfig:
    """Connector configuration resolved from the environment.

    ``api_token`` is the only secret field: it is excluded from repr and
    never appears in ``to_dict``/capability output. ``enabled`` is the
    explicit opt-in gate — a configured endpoint that is not enabled is
    reported ``configured_disabled`` and refuses every remote call.
    """

    base_url: str | None = None
    api_token: str | None = field(default=None, repr=False)
    enabled: bool = False
    timeout_seconds: int = 10
    verify_tls: bool = True

    @property
    def configured(self) -> bool:
        return bool(self.base_url) and bool(self.api_token)

    def state(self) -> str:
        if not self.configured:
            return "not_configured"
        if not self.enabled:
            return "configured_disabled"
        return "enabled"

    def to_dict(self) -> dict[str, Any]:
        """What a settings surface may show — no secrets, no invented
        account. ``account`` stays absent by construction (eLabFTW API
        keys carry no account identity the adapter can claim)."""
        return {
            "state": self.state(),
            "configured": self.configured,
            "enabled": self.enabled,
            "base_url": self.base_url if self.configured else None,
            "token_present": bool(self.api_token),
            "timeout_seconds": self.timeout_seconds,
            "verify_tls": self.verify_tls,
        }

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> ElnConfig:
        source = os.environ if env is None else env

        def _get(name: str) -> str | None:
            value = source.get(name)
            return value if value else None

        timeout_raw = _get("STUDIO_ELN_TIMEOUT_SECONDS") or "10"
        try:
            timeout = int(timeout_raw)
        except ValueError:
            timeout = 10
        return cls(
            base_url=(_get("STUDIO_ELN_BASE_URL") or "").rstrip("/") or None,
            api_token=_get("STUDIO_ELN_API_TOKEN"),
            enabled=(_get("STUDIO_ELN_ENABLED") or "").lower() in _TRUE,
            timeout_seconds=max(1, timeout),
            verify_tls=(_get("STUDIO_ELN_VERIFY_TLS") or "true").lower() in _TRUE,
        )


# ------------------------------------------------------------------
# Remote entity (eLabFTW API v2 shape — fixture fidelity, see
# tests/fixtures/)
# ------------------------------------------------------------------


class ElnEntityRecord(BaseModel):
    """One eLabFTW entity as returned by ``GET /api/v2/{type}/{id}``.

    Extra fields are tolerated (``extra="ignore"``) so a newer instance
    adding fields never breaks the mapping; the fields below are the
    documented v2 surface the adapter reasons about.
    """

    model_config = ConfigDict(extra="ignore")

    type: str = Field(min_length=1, max_length=64)  # "experiments" | "items" | ...
    id: int = Field(ge=1)
    title: str = ""
    created_at: str | None = None  # eLabFTW emits "YYYY-MM-DD HH:MM:SS"
    modified_at: str | None = None
    date: str | None = None
    body: str | None = None
    body_html: str | None = None
    content_type: int | None = None
    elabid: str | None = None
    userid: int | None = None
    fullname: str | None = None
    team: str | None = None
    status: int | None = None
    status_title: str | None = None
    category: int | None = None
    category_title: str | None = None
    state: int | None = None
    metadata: dict[str, Any] | str | None = None
    tags: list[dict[str, Any]] = Field(default_factory=list)
    uploads: list[dict[str, Any]] = Field(default_factory=list)
    comments: list[dict[str, Any]] = Field(default_factory=list)
    items_links: list[dict[str, Any]] = Field(default_factory=list)
    experiments_links: list[dict[str, Any]] = Field(default_factory=list)
    sharelink: str | None = None

    def fingerprint_doc(self) -> dict[str, Any]:
        """Canonical content the version/hash mapping watches."""
        return {
            "title": self.title,
            "body": self.body,
            "metadata": self.metadata,
            "status": self.status,
            "category": self.category,
            "state": self.state,
        }

    def remote_fingerprint(self) -> str:
        return digest_doc(self.fingerprint_doc())


# ------------------------------------------------------------------
# Local export record + link bookkeeping
# ------------------------------------------------------------------


class LocalExportRecord(BaseModel):
    """What a Studio caller asks to export — a snapshot reference, not
    the authoritative row (which always stays in Studio)."""

    model_config = ConfigDict(extra="forbid")

    local_ref: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(default="", max_length=1_000_000)
    revision: str = Field(default="", max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ElnLink(BaseModel):
    """Bookkeeping binding one Studio object to one remote entity.

    ``remote_version``/``remote_sha256`` are the baseline both sides
    agreed on at last sync; ``snapshot`` is the remote record as last
    imported — local evidence that survives a disconnect. The link is
    a mutable record (sync lifecycle), but only through adapter
    transitions: tests and callers never hand-edit it into a "synced"
    state the evidence does not support.
    """

    model_config = ConfigDict(extra="forbid")

    link_id: str = Field(min_length=1, max_length=120)
    local_ref: str = Field(min_length=1, max_length=200)
    entity_type: str = Field(min_length=1, max_length=64)
    entity_id: int = Field(ge=1)
    remote_version: str | None = None  # remote modified_at at last sync
    remote_sha256: str = Field(min_length=64, max_length=64)
    snapshot: dict[str, Any] = Field(default_factory=dict)
    imported_at: str
    last_checked_at: str | None = None
    state: str = "synced"
    review: dict[str, Any] | None = None


@dataclass(frozen=True)
class ImportVerdict:
    """Outcome of one selective import attempt."""

    outcome: Literal["imported", "unchanged", "review_required", "unavailable"]
    link: ElnLink | None
    incoming: ElnEntityRecord | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "link": self.link.model_dump(mode="json") if self.link else None,
            "incoming": self.incoming.model_dump(mode="json") if self.incoming else None,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ExportResult:
    """Outcome of one explicit export attempt."""

    outcome: Literal["exported", "updated", "review_required", "unavailable"]
    link: ElnLink | None
    remote: ElnEntityRecord | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "link": self.link.model_dump(mode="json") if self.link else None,
            "remote": self.remote.model_dump(mode="json") if self.remote else None,
            "detail": self.detail,
        }
