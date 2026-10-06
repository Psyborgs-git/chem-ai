"""CS-0506 unit tests — config parsing, v2 mapping, fingerprints, and
the export payload assembly. Pure in-process, no transport."""

from __future__ import annotations

import pytest

from engine_adapter_elabftw import (
    ElnBadResponse,
    ElnConfig,
    ElnEntityRecord,
    LocalExportRecord,
    entity_to_record,
    load_fixture,
    to_export_payload,
)


def test_config_from_env_defaults_to_not_configured() -> None:
    config = ElnConfig.from_env({})
    assert config.state() == "not_configured"
    assert config.configured is False
    assert config.enabled is False
    assert config.timeout_seconds == 10
    assert config.verify_tls is True


def test_config_enable_requires_full_endpoint() -> None:
    """ENABLED=1 alone is not enough — no invented endpoint."""
    config = ElnConfig.from_env({"STUDIO_ELN_ENABLED": "1"})
    assert config.state() == "not_configured"


def test_config_state_transitions() -> None:
    partial = ElnConfig.from_env({"STUDIO_ELN_BASE_URL": "https://eln.example.org/"})
    assert partial.state() == "not_configured"  # URL without token
    configured = ElnConfig.from_env(
        {"STUDIO_ELN_BASE_URL": "https://eln.example.org/", "STUDIO_ELN_API_TOKEN": "k"}
    )
    assert configured.state() == "configured_disabled"
    assert configured.base_url == "https://eln.example.org"  # trailing slash stripped
    enabled = ElnConfig.from_env(
        {
            "STUDIO_ELN_BASE_URL": "https://eln.example.org",
            "STUDIO_ELN_API_TOKEN": "k",
            "STUDIO_ELN_ENABLED": "yes",
        }
    )
    assert enabled.state() == "enabled"


def test_entity_mapping_parses_real_v2_shape() -> None:
    record = entity_to_record(load_fixture("elabftw_experiment_v1.json"))
    assert isinstance(record, ElnEntityRecord)
    assert record.type == "experiments" and record.id == 42
    assert record.modified_at == "2026-09-29 14:02:11"
    assert record.elabid == "20260928-aa11bb22cc33dd44ee55ff66aa77bb88cc99dd00"
    assert record.tags[0]["tag"] == "fixture"


def test_entity_mapping_tolerates_extra_fields_and_rejects_bad() -> None:
    payload = load_fixture("elabftw_item_v1.json")
    payload["future_field"] = {"anything": True}
    assert entity_to_record(payload).id == 15
    for bad in ("not-a-dict", {}, {"type": "experiments", "id": -1}, []):
        with pytest.raises(ElnBadResponse):
            entity_to_record(bad)  # type: ignore[arg-type]
    with pytest.raises(ElnBadResponse):
        entity_to_record({"type": "users", "id": 1})


def test_fingerprint_distinguishes_content_edits() -> None:
    v1 = entity_to_record(load_fixture("elabftw_experiment_v1.json"))
    v2 = entity_to_record(load_fixture("elabftw_experiment_v2_external_edit.json"))
    assert v1.remote_fingerprint() != v2.remote_fingerprint()
    same = entity_to_record(dict(load_fixture("elabftw_experiment_v1.json")))
    assert same.remote_fingerprint() == v1.remote_fingerprint()


def test_export_payload_embeds_studio_provenance() -> None:
    local = LocalExportRecord(
        local_ref="task:abc",
        title="Task export",
        body="<p>body</p>",
        revision="rev-2",
        metadata={"extra_fields": {"priority": {"type": "text", "value": "p1"}}},
    )
    payload = to_export_payload(local)
    assert payload["title"] == "Task export"
    extra = payload["metadata"]["extra_fields"]
    assert extra["studio_provenance"]["local_ref"] == "task:abc"
    assert extra["studio_provenance"]["local_revision"] == "rev-2"
    assert extra["studio_provenance"]["sync_direction"].startswith("export-only")
    assert extra["priority"]["value"] == "p1"


def test_fixtures_are_labelled_fixture_content() -> None:
    """Fixture fidelity check: the shipped recordings carry the
    eLabFTW v2 field names and identify themselves as fixtures."""
    for name in (
        "elabftw_experiment_v1.json",
        "elabftw_experiment_v2_external_edit.json",
        "elabftw_item_v1.json",
    ):
        payload = load_fixture(name)
        assert payload["type"] in ("experiments", "items")
        assert "modified_at" in payload and "created_at" in payload
        assert "fixture" in payload["fullname"].lower()
        assert "fixture.invalid" in payload["sharelink"]
