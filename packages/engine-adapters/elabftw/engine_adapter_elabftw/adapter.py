"""ElabftwAdapter — the optional explicit ELN bridge (CS-0506).

Sync model (handoff §14.3, U16 decision): Chemistry Studio is
authoritative for its native records. The bridge offers explicit
one-way **export** (Studio -> ELN payload assembly + create/update) and
**selective import** (ELN -> Studio read of one linked entity at a
time). Every remote observation is compared against the version/hash
baseline recorded on the link:

- identical      -> ``unchanged``     (link stays synced)
- differs        -> ``review_required`` (a conflict — never overwritten,
                    either direction; the link keeps the agreed baseline
                    and records what was observed for a reviewer)
- unreachable    -> ``unavailable``   (link marked stale; the local
                    snapshot — local evidence — stays intact)

A reviewer resolves a conflict explicitly via ``resolve_review`` —
``accept_remote`` adopts the freshly re-read remote as the new baseline,
``keep_local`` keeps Studio's baseline and does NOT suppress future
drift detection.

The adapter is inert unless enabled: with no configuration it reports
``not_configured`` and every remote operation raises a typed
``ElnNotConfigured``/``ElnDisabled`` — startup, health checks and core
workflows cannot observe it.
"""

from __future__ import annotations

import uuid
from typing import Any

from .contracts import (
    ADAPTER_VERSION,
    ElnConfig,
    ElnDisabled,
    ElnEntityRecord,
    ElnError,
    ElnInvalidInput,
    ElnLink,
    ElnNotConfigured,
    ElnUnreachable,
    ExportResult,
    ImportVerdict,
    LocalExportRecord,
    utcnow,
)
from .mapping import entity_to_record, selector_from, to_export_payload
from .transport import ElnTransport, HttpElnTransport


class ElabftwAdapter:
    """Optional eLabFTW bridge. ``transport`` is injectable so tests run
    the real code path against the in-process fixture double; when it is
    omitted a configured+enabled config builds ``HttpElnTransport``
    lazily on first use (never on construction — capability probing is
    not a network call)."""

    def __init__(
        self, config: ElnConfig | None = None, *, transport: ElnTransport | None = None
    ) -> None:
        self._config = config or ElnConfig.from_env()
        self._transport = transport
        self.links: dict[str, ElnLink] = {}

    # -- capability surface (the honest connector-status report) -----------

    def capability(self) -> dict[str, Any]:
        """What a connector-settings surface may render verbatim.

        Reports the real config state and the real transport kind;
        ``connectivity`` is never probed here (a status read must not
        hit the network) and never claims a "connected" account.
        """
        state = self._config.state()
        transport_kind = "none"
        if self._transport is not None:
            transport_kind = self._transport.kind
        elif state == "enabled":
            transport_kind = "http"
        details = {
            "not_configured": "no eLabFTW instance configured; live ELN "
            "integration deferred (U16) — nothing provisioned",
            "configured_disabled": "endpoint configured but connectivity "
            "is off; set STUDIO_ELN_ENABLED=1 to allow remote calls",
            "enabled": "connectivity enabled; no call has been made yet "
            "(connectivity not probed by this report)",
        }
        return {
            "adapter_version": ADAPTER_VERSION,
            "state": state,
            "configured": self._config.configured,
            "enabled": self._config.enabled,
            "base_url": self._config.base_url if self._config.configured else None,
            "account": None,  # eLabFTW API keys carry no account identity to show
            "token_present": bool(self._config.api_token),
            "transport": transport_kind,
            "connectivity": "not_probed",
            "sync_direction": "export + selective import; never bidirectional",
            "scientific_status": "not_validated",
            "detail": details[state],
        }

    # -- gates --------------------------------------------------------------

    def _remote_transport(self) -> ElnTransport:
        state = self._config.state()
        if state == "not_configured":
            raise ElnNotConfigured()
        if state == "configured_disabled":
            raise ElnDisabled()
        if self._transport is not None:
            return self._transport
        self._transport = HttpElnTransport(self._config)
        return self._transport

    def _fetch_remote(self, entity_type: str, entity_id: int) -> ElnEntityRecord:
        transport = self._remote_transport()
        payload = transport.get(f"{entity_type}/{entity_id}")
        return entity_to_record(payload)

    # -- link bookkeeping -----------------------------------------------------

    def _link_key(self, entity_type: str, entity_id: int, local_ref: str | None) -> str | None:
        for link in self.links.values():
            if link.entity_type == entity_type and link.entity_id == entity_id:
                if local_ref is None or link.local_ref == local_ref:
                    return link.link_id
        return None

    def _mark_stale(self, link: ElnLink) -> None:
        if link.state == "synced":
            link.state = "stale"
        link.last_checked_at = utcnow().isoformat()

    def _compare(self, link: ElnLink, incoming: ElnEntityRecord) -> str:
        if (
            incoming.modified_at == link.remote_version
            and incoming.remote_fingerprint() == link.remote_sha256
        ):
            return "unchanged"
        return "changed"

    def _flag_review(self, link: ElnLink, incoming: ElnEntityRecord) -> None:
        link.state = "review_required"
        link.review = {
            "reason": "remote record changed since the agreed baseline",
            "baseline_version": link.remote_version,
            "baseline_sha256": link.remote_sha256,
            "observed_version": incoming.modified_at,
            "observed_sha256": incoming.remote_fingerprint(),
            "observed_at": utcnow().isoformat(),
            "incoming": incoming.model_dump(mode="json"),
        }
        link.last_checked_at = utcnow().isoformat()

    # -- selective import (ELN -> Studio) ------------------------------------

    def import_entity(self, selector: dict[str, Any]) -> ImportVerdict:
        """Import one explicitly selected remote entity. Never bulk,
        never automatic — every call is a deliberate import of one link.

        On an unreachable remote the verdict is ``unavailable`` (not an
        exception): a linked Studio object must open without crashing,
        with its local evidence intact.
        """
        entity_type, entity_id, local_ref = selector_from(selector)
        try:
            incoming = self._fetch_remote(entity_type, entity_id)
        except ElnUnreachable as e:
            link_id = self._link_key(entity_type, entity_id, local_ref)
            link = self.links.get(link_id) if link_id else None
            if link is not None:
                self._mark_stale(link)
            return ImportVerdict(
                outcome="unavailable",
                link=link,
                incoming=None,
                detail=e.message,
            )
        key = self._link_key(entity_type, entity_id, local_ref)
        link = self.links.get(key) if key else None
        if link is None:
            link = ElnLink(
                link_id=f"eln-{uuid.uuid4().hex[:12]}",
                local_ref=local_ref or f"external:{entity_type}/{entity_id}",
                entity_type=entity_type,
                entity_id=entity_id,
                remote_version=incoming.modified_at,
                remote_sha256=incoming.remote_fingerprint(),
                snapshot=incoming.model_dump(mode="json"),
                imported_at=utcnow().isoformat(),
                last_checked_at=utcnow().isoformat(),
                state="synced",
            )
            self.links[link.link_id] = link
            return ImportVerdict(
                outcome="imported",
                link=link,
                incoming=incoming,
                detail="remote record imported; link baseline recorded",
            )
        verdict = self._compare(link, incoming)
        link.last_checked_at = utcnow().isoformat()
        if verdict == "unchanged":
            if link.state == "stale":
                link.state = "synced"
            if link.state == "review_required":
                # Remote reverted to the agreed baseline — the conflict
                # resolved itself; honestly clear it.
                link.state = "synced"
                link.review = None
            return ImportVerdict(
                outcome="unchanged",
                link=link,
                incoming=incoming,
                detail="remote matches the link baseline",
            )
        self._flag_review(link, incoming)
        return ImportVerdict(
            outcome="review_required",
            link=link,
            incoming=incoming,
            detail="remote version/hash differ from the link baseline; "
            "a reviewer must resolve the conflict",
        )

    def link_status(self, link_id: str) -> dict[str, Any]:
        """What opening a linked Studio record shows: local evidence plus
        the remote's honest availability. Never raises for transport or
        configuration state — a missing/unreachable ELN is a status, not
        a crash."""
        link = self.links.get(link_id)
        if link is None:
            raise ElnInvalidInput(f"unknown link '{link_id}'")
        try:
            snapshot = ElnEntityRecord.model_validate(link.snapshot)
            intact = snapshot.remote_fingerprint() == link.remote_sha256
        except Exception:
            intact = False
        state = self._config.state()
        if state != "enabled":
            remote = "disabled" if state == "configured_disabled" else "not_configured"
        else:
            try:
                incoming = self._fetch_remote(link.entity_type, link.entity_id)
            except ElnUnreachable:
                remote = "unavailable"
                self._mark_stale(link)
            except ElnError as e:
                remote = f"error:{e.code}"
            else:
                remote = "available"
                link.last_checked_at = utcnow().isoformat()
                # Opening a linked record refreshes the drift check too —
                # surfacing a conflict on open is more honest than
                # waiting for an explicit import to notice it.
                if self._compare(link, incoming) == "changed":
                    self._flag_review(link, incoming)
                elif link.state == "stale":
                    link.state = "synced"
        return {
            "link_id": link.link_id,
            "local_ref": link.local_ref,
            "entity_type": link.entity_type,
            "entity_id": link.entity_id,
            "local_evidence": "intact" if intact else "corrupted",
            "remote": remote,
            "state": link.state,
            "remote_version": link.remote_version,
            "remote_sha256": link.remote_sha256,
            "imported_at": link.imported_at,
            "last_checked_at": link.last_checked_at,
            "review": link.review,
        }

    # -- explicit export (Studio -> ELN) --------------------------------------

    def export_record(
        self,
        local: LocalExportRecord,
        *,
        entity_type: str = "experiments",
        link_id: str | None = None,
    ) -> ExportResult:
        """Assemble and send a one-way export. With an existing link the
        remote is re-read first: if it drifted from the baseline the
        update is refused with ``review_required`` — the bridge never
        silently overwrites in either direction."""
        if entity_type not in ("experiments", "items"):
            raise ElnInvalidInput(f"entity_type must be one of {('experiments', 'items')}")
        payload = to_export_payload(local)
        link = self.links.get(link_id) if link_id else None
        if link is None and link_id is not None:
            raise ElnInvalidInput(f"unknown link '{link_id}'")
        stamp = payload.pop("_exported_at")
        try:
            transport = self._remote_transport()
            if link is not None:
                remote_now = self._fetch_remote(link.entity_type, link.entity_id)
                if self._compare(link, remote_now) == "changed":
                    self._flag_review(link, remote_now)
                    return ExportResult(
                        outcome="review_required",
                        link=link,
                        remote=remote_now,
                        detail="remote record changed since baseline; "
                        "export update refused until a reviewer resolves it",
                    )
                body = dict(payload)
                body["modified_at"] = stamp.replace("T", " ")[:19]
                remote = entity_to_record(
                    transport.patch(f"{link.entity_type}/{link.entity_id}", body)
                )
                link.remote_version = remote.modified_at
                link.remote_sha256 = remote.remote_fingerprint()
                link.snapshot = remote.model_dump(mode="json")
                link.last_checked_at = utcnow().isoformat()
                link.state = "synced"
                link.review = None
                return ExportResult(
                    outcome="updated",
                    link=link,
                    remote=remote,
                    detail="remote record updated to the new Studio revision",
                )
            created = entity_to_record(transport.post(entity_type, payload))
        except ElnUnreachable as e:
            if link is not None:
                self._mark_stale(link)
            return ExportResult(outcome="unavailable", link=link, remote=None, detail=e.message)
        link = ElnLink(
            link_id=f"eln-{uuid.uuid4().hex[:12]}",
            local_ref=local.local_ref,
            entity_type=created.type,
            entity_id=created.id,
            remote_version=created.modified_at,
            remote_sha256=created.remote_fingerprint(),
            snapshot=created.model_dump(mode="json"),
            imported_at=utcnow().isoformat(),
            last_checked_at=utcnow().isoformat(),
            state="synced",
        )
        self.links[link.link_id] = link
        return ExportResult(
            outcome="exported",
            link=link,
            remote=created,
            detail="remote record created; link baseline recorded",
        )

    # -- review resolution -----------------------------------------------------

    def resolve_review(self, link_id: str, action: str) -> dict[str, Any]:
        """Explicit human resolution of a ``review_required`` link.

        ``accept_remote`` re-reads the remote NOW and adopts exactly what
        is observed as the new baseline. ``keep_local`` keeps Studio's
        baseline; it does not suppress future drift detection.
        """
        link = self.links.get(link_id)
        if link is None:
            raise ElnInvalidInput(f"unknown link '{link_id}'")
        if link.state != "review_required":
            raise ElnInvalidInput(f"link '{link_id}' is not in review_required state")
        if action == "accept_remote":
            incoming = self._fetch_remote(link.entity_type, link.entity_id)
            link.remote_version = incoming.modified_at
            link.remote_sha256 = incoming.remote_fingerprint()
            link.snapshot = incoming.model_dump(mode="json")
            link.state = "synced"
            link.review = None
            link.last_checked_at = utcnow().isoformat()
            return {
                "link_id": link.link_id,
                "state": link.state,
                "resolution": "accept_remote",
                "remote_version": link.remote_version,
                "remote_sha256": link.remote_sha256,
            }
        if action == "keep_local":
            resolution = {
                "action": "keep_local",
                "decided_at": utcnow().isoformat(),
                "detail": "Studio baseline kept; future remote drift still routes to review",
            }
            link.state = "synced"
            link.review = resolution
            link.last_checked_at = utcnow().isoformat()
            return {
                "link_id": link.link_id,
                "state": link.state,
                "resolution": "keep_local",
                "remote_version": link.remote_version,
                "remote_sha256": link.remote_sha256,
            }
        raise ElnInvalidInput("action must be 'accept_remote' or 'keep_local'")

    def export_state(self) -> dict[str, Any]:
        """Serialize the link registry — callers persist it; the adapter
        never invents persisted state of its own."""
        return {
            "adapter_version": ADAPTER_VERSION,
            "links": [link.model_dump(mode="json") for link in self.links.values()],
        }
