"""CS-0506 integration tests — the optional eLabFTW bridge.

Drives the REAL adapter code path: ElnConfig (enabled) -> ElabftwAdapter
-> ElnTransport -> entity mapping -> link bookkeeping. The transport is
the in-process FixtureElnTransport serving recorded eLabFTW API v2
responses (``packages/engine-adapters/elabftw/tests/fixtures/``); no
network call is ever made — live eLabFTW sync is deferred (U16).

AT-0506-1: a fixture ELN response changes externally -> repeating the
import detects the version/hash drift and routes to review_required,
never a silent overwrite.

AT-0506-2: ELN disconnected -> opening a linked record keeps local
evidence intact and marks the ELN side stale/unavailable; no crash, no
fabricated "connected" state.
"""

from __future__ import annotations

import pytest

from engine_adapter_elabftw import (
    ElabftwAdapter,
    ElnConfig,
    FixtureElnTransport,
    LocalExportRecord,
    load_fixture,
)

pytestmark = pytest.mark.integration


def _adapter(entities: dict | None = None) -> tuple[ElabftwAdapter, FixtureElnTransport]:
    config = ElnConfig(
        base_url="https://eln.fixture.invalid",
        api_token="fixture-token-not-a-secret",
        enabled=True,
    )
    transport = FixtureElnTransport(entities)
    return ElabftwAdapter(config, transport=transport), transport


def _base_entities() -> dict:
    return {"experiments/42": load_fixture("elabftw_experiment_v1.json")}


def test_import_records_link_baseline() -> None:
    adapter, _ = _adapter(_base_entities())
    verdict = adapter.import_entity(
        {"entity_type": "experiments", "entity_id": 42, "local_ref": "task:task-1"}
    )
    assert verdict.outcome == "imported"
    link = verdict.link
    assert link is not None
    assert link.state == "synced"
    assert link.entity_type == "experiments" and link.entity_id == 42
    assert link.remote_version == "2026-09-29 14:02:11"
    assert len(link.remote_sha256) == 64
    assert link.snapshot["body"].startswith("<p>Fixture narrative")


def test_at_0506_1_external_change_routes_to_review() -> None:
    """AT-0506-1: repeat import after an external edit -> review_required."""
    adapter, transport = _adapter(_base_entities())
    first = adapter.import_entity({"entity_type": "experiments", "entity_id": 42})
    assert first.outcome == "imported"
    link = first.link
    assert link is not None
    baseline_version = link.remote_version
    baseline_sha = link.remote_sha256

    # An ELN-side user edits the record out-of-band.
    transport.mutate_entity(
        "experiments", 42, **load_fixture("elabftw_experiment_v2_external_edit.json")
    )
    second = adapter.import_entity({"entity_type": "experiments", "entity_id": 42})
    assert second.outcome == "review_required"
    assert second.link is not None and second.link.state == "review_required"
    review = second.link.review
    assert review is not None
    assert review["baseline_version"] == baseline_version
    assert review["baseline_sha256"] == baseline_sha
    assert review["observed_version"] == "2026-10-02 17:44:31"
    assert review["observed_sha256"] != baseline_sha
    # The agreed baseline + local snapshot are NOT overwritten.
    assert second.link.remote_version == baseline_version
    assert second.link.remote_sha256 == baseline_sha
    assert "revised" not in (second.link.snapshot["body"] or "")
    # The incoming record is preserved for the reviewer.
    assert second.incoming is not None and second.incoming.modified_at == "2026-10-02 17:44:31"

    # Still-in-review links keep reporting the conflict honestly.
    third = adapter.import_entity({"entity_type": "experiments", "entity_id": 42})
    assert third.outcome == "review_required"


def test_at_0506_1_review_resolutions() -> None:
    """Review lifecycle: accept_remote adopts the fresh read; keep_local
    keeps the Studio baseline without suppressing future detection."""
    adapter, transport = _adapter(_base_entities())
    link = adapter.import_entity({"entity_type": "experiments", "entity_id": 42}).link
    assert link is not None
    transport.mutate_entity(
        "experiments", 42, modified_at="2026-10-02 17:44:31", body="<p>edited</p>"
    )
    assert (
        adapter.import_entity({"entity_type": "experiments", "entity_id": 42}).outcome
        == "review_required"
    )

    resolved = adapter.resolve_review(link.link_id, "accept_remote")
    assert resolved["state"] == "synced"
    assert resolved["remote_version"] == "2026-10-02 17:44:31"
    assert link.snapshot["body"] == "<p>edited</p>"
    # Baseline adopted -> next import is unchanged.
    assert (
        adapter.import_entity({"entity_type": "experiments", "entity_id": 42}).outcome
        == "unchanged"
    )

    transport.mutate_entity(
        "experiments", 42, modified_at="2026-10-03 09:00:00", body="<p>edited again</p>"
    )
    assert (
        adapter.import_entity({"entity_type": "experiments", "entity_id": 42}).outcome
        == "review_required"
    )
    resolved = adapter.resolve_review(link.link_id, "keep_local")
    assert resolved["state"] == "synced"
    # keep_local keeps the baseline AND does not suppress detection.
    assert link.remote_version == "2026-10-02 17:44:31"
    assert (
        adapter.import_entity({"entity_type": "experiments", "entity_id": 42}).outcome
        == "review_required"
    )


def test_at_0506_2_disconnect_marks_stale_without_losing_evidence() -> None:
    """AT-0506-2: ELN unreachable -> linked record opens with local
    evidence intact, remote reported unavailable; nothing crashes."""
    adapter, transport = _adapter(_base_entities())
    link = adapter.import_entity(
        {"entity_type": "experiments", "entity_id": 42, "local_ref": "task:task-9"}
    ).link
    assert link is not None
    snapshot_before = dict(link.snapshot)

    transport.go_offline()
    status = adapter.link_status(link.link_id)
    assert status["remote"] == "unavailable"
    assert status["local_evidence"] == "intact"
    assert status["state"] == "stale"
    assert link.snapshot == snapshot_before  # local evidence untouched

    # Import while disconnected: verdict, not exception.
    verdict = adapter.import_entity({"entity_type": "experiments", "entity_id": 42})
    assert verdict.outcome == "unavailable"
    assert verdict.incoming is None

    # Recovery marks the link synced again after a clean read.
    transport.go_online()
    status = adapter.link_status(link.link_id)
    assert status["remote"] == "available"
    assert status["state"] == "synced"


def test_at_0506_2_disconnect_never_reports_connected() -> None:
    adapter, transport = _adapter(_base_entities())
    link = adapter.import_entity({"entity_type": "experiments", "entity_id": 42}).link
    assert link is not None
    transport.go_offline()
    assert adapter.link_status(link.link_id)["remote"] == "unavailable"
    capability = adapter.capability()
    # The connector surface never fabricates reachability either.
    assert capability["connectivity"] == "not_probed"
    assert capability["transport"] == "fixture"


def test_export_creates_linked_remote_record() -> None:
    adapter, transport = _adapter({})
    local = LocalExportRecord(
        local_ref="task:task-7",
        title="Studio task export",
        body="<p>fixture export body</p>",
        revision="rev-3",
    )
    result = adapter.export_record(local)
    assert result.outcome == "exported"
    assert result.link is not None and result.link.state == "synced"
    # The outgoing call carried the studio provenance stamp.
    posted = transport.calls[-1]
    assert posted["method"] == "POST" and posted["path"] == "experiments"
    provenance = posted["payload"]["metadata"]["extra_fields"]["studio_provenance"]
    assert provenance["source_system"] == "chemistry-studio"
    assert provenance["local_ref"] == "task:task-7"
    assert provenance["local_revision"] == "rev-3"
    # Importing the exported entity is unchanged vs the link baseline.
    assert (
        adapter.import_entity(
            {"entity_type": "experiments", "entity_id": result.link.entity_id}
        ).outcome
        == "unchanged"
    )


def test_export_update_refuses_overwrite_on_drift() -> None:
    """Both directions route conflicts to review: an export update over a
    remotely-edited record is refused, not silently overwritten."""
    adapter, transport = _adapter({})
    local = LocalExportRecord(local_ref="task:task-8", title="Export me", body="<p>v1</p>")
    result = adapter.export_record(local)
    link = result.link
    assert link is not None

    transport.mutate_entity(
        "experiments",
        link.entity_id,
        modified_at="2026-10-05 12:00:00",
        body="<p>eln-side edit</p>",
    )
    update = adapter.export_record(
        LocalExportRecord(local_ref="task:task-8", title="Export me v2", body="<p>v2</p>"),
        link_id=link.link_id,
    )
    assert update.outcome == "review_required"
    assert link.state == "review_required"
    # The remote still holds the ELN-side edit — the PATCH never ran.
    remote = transport.entity("experiments", link.entity_id)
    assert remote["body"] == "<p>eln-side edit</p>"
    assert not any(c["method"] == "PATCH" for c in transport.calls)


def test_export_update_clean_remote_succeeds() -> None:
    adapter, transport = _adapter({})
    local = LocalExportRecord(local_ref="task:task-10", title="Export", body="<p>v1</p>")
    result = adapter.export_record(local)
    link = result.link
    assert link is not None
    update = adapter.export_record(
        LocalExportRecord(local_ref="task:task-10", title="Export", body="<p>v2</p>"),
        link_id=link.link_id,
    )
    assert update.outcome == "updated"
    assert link.state == "synced"
    assert update.remote is not None
    remote = transport.entity("experiments", link.entity_id)
    assert remote["body"] == "<p>v2</p>"
    assert link.remote_sha256 == update.remote.remote_fingerprint()


def test_item_entities_are_supported_selectively() -> None:
    adapter, _ = _adapter({"items/15": load_fixture("elabftw_item_v1.json")})
    verdict = adapter.import_entity({"entity_type": "items", "entity_id": 15})
    assert verdict.outcome == "imported"
    assert verdict.incoming is not None and verdict.incoming.type == "items"
