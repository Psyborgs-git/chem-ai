"""CS-0506 security tests — the ELN bridge fails closed and honestly.

AT-0506-3: with no ELN account configured, the connector's settings/API
surface (``ElabftwAdapter.capability()`` — the status any settings UI
renders; no connector UI exists in apps/studio-web) shows no invented
account and no credentials, and every remote operation is refused with
a typed error. A configured-but-not-enabled endpoint is likewise inert:
connectivity is opt-in, never implied.
"""

from __future__ import annotations

import json
import re

import pytest

from engine_adapter_elabftw import (
    ElabftwAdapter,
    ElnConfig,
    ElnDisabled,
    ElnInvalidInput,
    ElnNotConfigured,
    FixtureElnTransport,
    LocalExportRecord,
    load_fixture,
)

pytestmark = pytest.mark.security

_ENV_CLEAR = {
    "STUDIO_ELN_BASE_URL": None,
    "STUDIO_ELN_API_TOKEN": None,
    "STUDIO_ELN_ENABLED": None,
    "STUDIO_ELN_TIMEOUT_SECONDS": None,
}


def _env(**over: str | None) -> dict[str, str]:
    env = {k: v for k, v in _ENV_CLEAR.items() if v}
    for k, v in over.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    return env


def test_no_config_reports_not_configured() -> None:
    """AT-0506-3: empty environment -> not_configured, no account, no
    credential material anywhere on the status surface."""
    config = ElnConfig.from_env(_env())
    assert config.state() == "not_configured"
    adapter = ElabftwAdapter(config)
    capability = adapter.capability()
    assert capability["state"] == "not_configured"
    assert capability["configured"] is False
    assert capability["enabled"] is False
    assert capability["account"] is None
    assert capability["base_url"] is None
    assert capability["token_present"] is False
    assert capability["transport"] == "none"


def test_no_config_operations_refused_with_typed_errors() -> None:
    adapter = ElabftwAdapter(ElnConfig.from_env(_env()))
    with pytest.raises(ElnNotConfigured) as e:
        adapter.import_entity({"entity_type": "experiments", "entity_id": 42})
    assert e.value.to_dict() == {
        "code": "ELN_NOT_CONFIGURED",
        "message": "no eLabFTW instance is configured",
    }
    with pytest.raises(ElnNotConfigured):
        adapter.export_record(LocalExportRecord(local_ref="task:x", title="t"))


def test_configured_but_not_enabled_is_disabled() -> None:
    """An endpoint + token WITHOUT the explicit enable flag is
    ``configured_disabled``: present on the surface, still inert."""
    env = _env(
        STUDIO_ELN_BASE_URL="https://eln.example.org",
        STUDIO_ELN_API_TOKEN="3-fixture-key",
    )
    config = ElnConfig.from_env(env)
    assert config.state() == "configured_disabled"
    adapter = ElabftwAdapter(config)
    capability = adapter.capability()
    assert capability["state"] == "configured_disabled"
    assert capability["enabled"] is False
    assert capability["base_url"] == "https://eln.example.org"
    assert capability["account"] is None
    with pytest.raises(ElnDisabled) as e:
        adapter.import_entity({"entity_type": "experiments", "entity_id": 42})
    assert e.value.code == "ELN_DISABLED"
    with pytest.raises(ElnDisabled):
        adapter.export_record(LocalExportRecord(local_ref="task:x", title="t"))


def test_token_never_appears_on_any_surface() -> None:
    probe = "3-cb2314b00d2845a0f0f0f0f0f0f0f0f0f0f0f0f0f0"
    config = ElnConfig.from_env(
        _env(
            # loopback discard port: deterministic refusal, no real egress
            STUDIO_ELN_BASE_URL="https://127.0.0.1:9",
            STUDIO_ELN_API_TOKEN=probe,
            STUDIO_ELN_ENABLED="1",
        )
    )
    adapter = ElabftwAdapter(config)
    surfaces = [
        repr(config),
        str(config.to_dict()),
        json.dumps(adapter.capability()),
        str(adapter.export_state()),
    ]
    try:
        adapter.import_entity({"entity_type": "experiments", "entity_id": 1})
    except Exception as e:  # unreachable/bad response — still token-free
        surfaces.append(str(e))
        if hasattr(e, "to_dict"):
            surfaces.append(json.dumps(e.to_dict()))
    for surface in surfaces:
        assert probe not in surface
    assert not re.search(r"cb2314|api_token=.{0,4}[0-9a-f]{4}", json.dumps(adapter.capability()))


def test_enabled_without_transport_never_dials() -> None:
    """Enabled config with no injected transport constructs the real
    HTTP transport lazily — capability() itself must not probe."""
    config = ElnConfig.from_env(
        _env(
            STUDIO_ELN_BASE_URL="https://eln.example.invalid",
            STUDIO_ELN_API_TOKEN="fixture-token",
            STUDIO_ELN_ENABLED="1",
        )
    )
    adapter = ElabftwAdapter(config)
    capability = adapter.capability()
    assert capability["state"] == "enabled"
    assert capability["connectivity"] == "not_probed"
    # capability() did not construct a transport or make a call.
    assert adapter._transport is None  # private read — asserting laziness


def test_offline_link_status_for_disabled_connector() -> None:
    """A linked record on a disabled connector reports honestly — local
    evidence intact, remote 'disabled', never a fabricated status."""
    config = ElnConfig(base_url="https://eln.fixture.invalid", api_token="t", enabled=True)
    adapter = ElabftwAdapter(
        config,
        transport=FixtureElnTransport(
            {"experiments/42": load_fixture("elabftw_experiment_v1.json")}
        ),
    )
    link = adapter.import_entity({"entity_type": "experiments", "entity_id": 42}).link
    assert link is not None

    disabled = ElabftwAdapter(
        ElnConfig(base_url="https://eln.fixture.invalid", api_token="t", enabled=False)
    )
    disabled.links[link.link_id] = link
    status = disabled.link_status(link.link_id)
    assert status["remote"] == "disabled"
    assert status["local_evidence"] == "intact"


def test_selector_and_link_validation_is_strict() -> None:
    adapter = ElabftwAdapter(
        ElnConfig(base_url="https://eln.fixture.invalid", api_token="t", enabled=True),
        transport=FixtureElnTransport({}),
    )
    for bad in (
        {"entity_type": "users", "entity_id": 1},
        {"entity_type": "experiments", "entity_id": 0},
        {"entity_type": "experiments"},
        "experiments/1",
    ):
        with pytest.raises(ElnInvalidInput):
            adapter.import_entity(bad)  # type: ignore[arg-type]
    with pytest.raises(ElnInvalidInput):
        adapter.link_status("eln-nope")
    with pytest.raises(ElnInvalidInput):
        adapter.resolve_review("eln-nope", "accept_remote")
