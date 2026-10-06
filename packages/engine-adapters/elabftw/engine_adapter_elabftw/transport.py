"""Transports for the eLabFTW bridge (CS-0506).

Two implementations, one honest split:

- ``HttpElnTransport`` — the real wire client for the eLabFTW API v2
  (``Authorization: <key>`` header, JSON GET/POST/PATCH, stdlib urllib
  so the adapter adds no dependency). It exists so a *configured and
  explicitly enabled* deployment can talk to a real instance; it is
  constructed only when the config is enabled and was never exercised
  against a live endpoint in this release (U16 — labelled, not hidden).
- ``FixtureElnTransport`` — the in-process double that serves recorded
  API-v2-shaped responses, records every outgoing call, and can be
  switched offline to simulate a disconnected ELN. This is the only
  transport the test suite exercises end to end.
"""

from __future__ import annotations

import copy
import json
import urllib.error
import urllib.request
from typing import Any, Protocol

from .contracts import ElnBadResponse, ElnConfig, ElnUnreachable

API_PREFIX = "/api/v2"


class ElnTransport(Protocol):
    """Minimal eLabFTW API v2 surface the adapter uses."""

    kind: str

    def get(self, path: str) -> dict[str, Any]: ...

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    def patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class HttpElnTransport:
    """Real eLabFTW API v2 client — opt-in connectivity only.

    The adapter builds this exclusively when ``config.state() ==
    "enabled"``; nothing else in the repository can reach it. The API
    token travels in the ``Authorization`` header exactly as eLabFTW
    documents and is never written into errors, results or logs.
    """

    kind = "http"

    def __init__(self, config: ElnConfig) -> None:
        if not config.configured:
            raise ElnBadResponse("HttpElnTransport requires a configured instance")
        if not config.enabled:
            raise ElnBadResponse("HttpElnTransport requires an enabled connector")
        self._config = config
        self._base = f"{config.base_url}{API_PREFIX}"

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None
    ) -> dict[str, Any]:
        url = f"{self._base}{path}"
        body = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=body, method=method)  # noqa: S310 — owner-configured host
        req.add_header("Authorization", self._config.api_token or "")
        if body is not None:
            req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(  # noqa: S310 — host is owner-configured
                req,
                timeout=self._config.timeout_seconds,
            ) as resp:
                raw = resp.read().decode()
        except urllib.error.HTTPError as e:
            raise ElnBadResponse(f"eLabFTW returned HTTP {e.code} for {method} {path}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ElnUnreachable(
                f"eLabFTW unreachable: {e.reason if hasattr(e, 'reason') else e}"
            ) from e
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except ValueError as e:
            raise ElnBadResponse(f"eLabFTW returned non-JSON for {method} {path}") from e
        if not isinstance(data, dict):
            raise ElnBadResponse(f"eLabFTW returned non-object JSON for {method} {path}")
        return data

    def get(self, path: str) -> dict[str, Any]:
        return self._request("GET", path, None)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, payload)

    def patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", path, payload)


class FixtureElnTransport:
    """In-process double serving recorded eLabFTW responses.

    ``entities`` maps ``{entity_type}/{entity_id}`` to API-v2-shaped
    JSON (see ``tests/fixtures/``). ``go_offline()`` simulates a
    disconnected ELN — every call raises ``ElnUnreachable`` until
    ``go_online()``. ``mutate_entity()`` is the lever tests use to
    simulate an *external* edit on the ELN side. All outgoing traffic
    is recorded in ``calls`` for assertion. ``kind`` honestly reports
    ``"fixture"`` — a double can never impersonate a live endpoint.
    """

    kind = "fixture"

    def __init__(self, entities: dict[str, dict[str, Any]] | None = None) -> None:
        self._entities: dict[str, dict[str, Any]] = {
            key: copy.deepcopy(value) for key, value in (entities or {}).items()
        }
        self._online = True
        self.calls: list[dict[str, Any]] = []
        self._next_id = (
            max(
                (v.get("id", 0) for v in self._entities.values() if isinstance(v.get("id"), int)),
                default=0,
            )
            + 1
        )

    # -- fixture control surface (not part of the API contract) -----------

    def go_offline(self) -> None:
        self._online = False

    def go_online(self) -> None:
        self._online = True

    def mutate_entity(self, entity_type: str, entity_id: int, **fields: Any) -> None:
        """Apply an external change to a fixture entity — what an ELN
        user editing the record out-of-band looks like to the bridge."""
        entity = self._entities[f"{entity_type}/{entity_id}"]
        entity.update(copy.deepcopy(fields))

    def entity(self, entity_type: str, entity_id: int) -> dict[str, Any]:
        return copy.deepcopy(self._entities[f"{entity_type}/{entity_id}"])

    # -- ElnTransport surface ----------------------------------------------

    def _guard(self, method: str, path: str, payload: dict[str, Any] | None) -> None:
        self.calls.append({"method": method, "path": path, "payload": copy.deepcopy(payload)})
        if not self._online:
            raise ElnUnreachable("fixture ELN is offline (recorded disconnect)")

    def get(self, path: str) -> dict[str, Any]:
        self._guard("GET", path, None)
        entity = self._entities.get(path.lstrip("/"))
        if entity is None:
            raise ElnBadResponse(f"fixture has no entity at {path}")
        return copy.deepcopy(entity)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._guard("POST", path, payload)
        entity_type = path.strip("/").split("/")[0]
        entity_id = self._next_id
        self._next_id += 1
        stamp = payload.get("_fixture_stamp", "2026-10-06 00:00:00")
        entity = {
            "type": entity_type,
            "id": entity_id,
            "title": payload.get("title", ""),
            "created_at": stamp,
            "modified_at": stamp,
            "date": payload.get("date", stamp[:10]),
            "body": payload.get("body"),
            "body_html": payload.get("body"),
            "content_type": payload.get("content_type", 1),
            "elabid": f"{stamp[:10].replace('-', '')}-fixture{entity_id:08x}",
            "userid": 0,
            "fullname": "fixture-double",
            "team": "fixture",
            "status": payload.get("status", 1),
            "status_title": "fixture",
            "category": payload.get("category"),
            "category_title": None,
            "state": 1,
            "metadata": payload.get("metadata"),
            "tags": payload.get("tags", []),
            "uploads": [],
            "comments": [],
            "items_links": [],
            "experiments_links": [],
            "sharelink": f"https://eln.fixture.invalid/{entity_type}.php?mode=view&id={entity_id}",
        }
        self._entities[f"{entity_type}/{entity_id}"] = entity
        return copy.deepcopy(entity)

    def patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._guard("PATCH", path, payload)
        key = path.lstrip("/")
        entity = self._entities.get(key)
        if entity is None:
            raise ElnBadResponse(f"fixture has no entity at {path}")
        entity.update(copy.deepcopy(payload))
        if "modified_at" not in payload:
            raise ElnBadResponse("fixture PATCH requires an explicit modified_at stamp")
        return copy.deepcopy(entity)


__all__ = ["ElnTransport", "FixtureElnTransport", "HttpElnTransport"]
