"""eLabFTW <-> Studio mapping (CS-0506).

Pure functions — no I/O. ``entity_to_record`` validates an API-v2
payload into :class:`ElnEntityRecord`; ``to_export_payload`` assembles
the eLabFTW create/update body from a Studio export record with the
studio provenance stamp embedded in ``metadata`` so a reviewer on the
ELN side can see exactly which Studio object and adapter produced it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import (
    ADAPTER_VERSION,
    ELN_ENTITY_TYPES,
    ElnBadResponse,
    ElnEntityRecord,
    ElnInvalidInput,
    LocalExportRecord,
    utcnow,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    """Load a recorded eLabFTW API response shipped under the adapter's
    ``tests/fixtures/`` directory — labelled fixture data only."""
    path = FIXTURES_DIR / name
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ElnBadResponse(f"cannot load fixture {name}: {e}") from e
    if not isinstance(data, dict):
        raise ElnBadResponse(f"fixture {name} is not a JSON object")
    return data


def entity_to_record(payload: dict[str, Any]) -> ElnEntityRecord:
    """Parse an API-v2 entity JSON object. Malformed remote payloads are
    a typed failure, never a silent partial parse."""
    if not isinstance(payload, dict):
        raise ElnBadResponse("remote entity is not a JSON object")
    try:
        record = ElnEntityRecord.model_validate(payload)
    except Exception as e:
        raise ElnBadResponse(f"remote entity failed the v2 mapping: {e}") from e
    if record.type not in ELN_ENTITY_TYPES:
        raise ElnBadResponse(f"unsupported remote entity type '{record.type}'")
    return record


def to_export_payload(local: LocalExportRecord) -> dict[str, Any]:
    """Assemble the eLabFTW entity body for a Studio export.

    Studio provenance rides inside ``metadata.extra_fields`` the same
    way eLabFTW users attach structured fields: the remote side keeps a
    machine-readable pointer (system/local_ref/revision/digest) so the
    import path and human reviewers can trace the record home.
    """
    exported_at = utcnow().isoformat()
    provenance = {
        "source_system": "chemistry-studio",
        "adapter_version": ADAPTER_VERSION,
        "local_ref": local.local_ref,
        "local_revision": local.revision,
        "exported_at": exported_at,
        "sync_direction": "export-only; no bidirectional sync",
    }
    metadata: dict[str, Any] = {"extra_fields": {"studio_provenance": provenance}}
    for key, value in local.metadata.items():
        if key != "extra_fields":
            metadata[key] = value
        else:
            for fkey, fvalue in (value or {}).items():
                metadata["extra_fields"][fkey] = fvalue
    return {
        "title": local.title,
        "body": local.body,
        "content_type": 1,
        "metadata": metadata,
        "_exported_at": exported_at,
    }


def selector_from(value: Any) -> tuple[str, int, str | None]:
    """Normalize an import/export selector into (entity_type, entity_id,
    local_ref). Accepts an ElnLink-shaped mapping or a bare
    ``{"entity_type": ..., "entity_id": ...}`` selector."""
    if not isinstance(value, dict):
        raise ElnInvalidInput("selector must be a mapping")
    entity_type = value.get("entity_type")
    entity_id = value.get("entity_id")
    if entity_type not in ELN_ENTITY_TYPES:
        raise ElnInvalidInput(f"entity_type must be one of {ELN_ENTITY_TYPES}")
    if not isinstance(entity_id, int) or isinstance(entity_id, bool) or entity_id < 1:
        raise ElnInvalidInput("entity_id must be a positive integer")
    local_ref = value.get("local_ref")
    return entity_type, entity_id, local_ref if isinstance(local_ref, str) else None
