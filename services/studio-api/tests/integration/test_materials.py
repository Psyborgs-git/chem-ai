"""CS-0702 integration — validation, persistence, admission, execution,
and the endpoint-evaluation surface.

AT-0702-1  a request missing required parameters (an unparameterized
           pair or an unknowable decomposition) is BLOCKED — nothing is
           substituted.
AT-0702-2  evaluating a product-performance endpoint on equilibrium
           output returns a typed ``not_established`` verdict — no
           direct stability proof is ever claimed.
AT-0702-3  the capability card exposes benchmark/domain/limits with the
           real probed state.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine_adapter_materials.contracts import (
    DOES_NOT_ESTABLISH,
    SUPPORTS_ENDPOINTS,
    EngineFailure,
    MaterialsOutcome,
)
from studio.api.capabilities import collect_capabilities
from studio.auth.context import load_context
from studio.config.settings import Settings
from studio.domain.chemistry.materials import MaterialsService
from studio.domain.evidence.vault import Vault
from studio.domain.runs.admission import AdmissionService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Artifact,
    Principal,
    PrincipalCapability,
    RunAttempt,
    Workspace,
)

pytestmark = pytest.mark.integration

GB = 1024**3
FIXTURE = json.loads(Path("fixtures/synthetic/materials-lle.json").read_text())
_SPEC_KEYS = {"schema_version", "method", "components", "conditions", "grid_points", "resources"}


def _as_spec(raw: dict) -> dict:
    """Drop fixture bookkeeping keys (note/expected_*) — the contract is
    strict on extras."""
    return {k: v for k, v in raw.items() if k in _SPEC_KEYS}


@pytest.fixture()
def env(session: Session, tmp_path: Path):
    ws = Workspace(slug="materials", display_name="Materials tests")
    session.add(ws)
    session.flush()
    user = Principal(workspace_id=ws.id, kind="user", login="r", display_name="r")
    session.add(user)
    session.flush()
    for cap in sorted(capabilities_for_role("researcher")):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=user.id, capability=cap))
    session.flush()
    ctx = load_context(session, ws.id, user.id)
    AdmissionService(session, ctx).ensure_group(
        "compute",
        capacity={
            "cpu_cores": 8,
            "memory_bytes": 16 * GB,
            "storage_bytes": 256 * GB,
            "concurrency": 4,
        },
        reserve={},
    )
    session.flush()
    settings = Settings(profile_materials=True, vault_root=tmp_path / "vault")
    service = MaterialsService(session, ctx, settings, Vault(tmp_path / "vault"))
    return {"ctx": ctx, "service": service, "vault": tmp_path / "vault", "settings": settings}


def test_at0702_1_missing_parameter_pair_blocked(env, session: Session) -> None:
    """DMSO/water has no regressed interaction pair — blocked run, no
    artifact, no attempt, no substituted parameter."""
    run = env["service"].request(_as_spec(FIXTURE["missing_parameters_example"]))
    session.flush()
    assert run.status == "blocked"
    assert "insufficient_inputs" in (run.error or {}).get("message", "")
    detail = (run.error or {}).get("detail") or {}
    assert detail.get("capability") == "insufficient_inputs"
    assert "not regressed" in detail.get("detail", "")
    assert run.request.get("rejected") is True
    assert session.query(Artifact).count() == 0
    assert session.query(RunAttempt).count() == 0


def test_at0702_1_unknown_subgroup_blocked(env, session: Session) -> None:
    run = env["service"].request(_as_spec(FIXTURE["unsupported_subgroups_example"]))
    session.flush()
    assert run.status == "blocked"
    assert session.query(RunAttempt).count() == 0


def test_at0702_1_temperature_outside_domain_blocked(env, session: Session) -> None:
    raw = json.loads(json.dumps(FIXTURE["spec"]))
    raw["conditions"]["temperature_k"] = 373.15
    run = env["service"].request(raw)
    session.flush()
    assert run.status == "blocked"
    assert session.query(RunAttempt).count() == 0


def test_valid_request_persists_input_before_queueing(
    env, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("studio.domain.chemistry.materials.available", lambda: True)
    run = env["service"].request(FIXTURE["spec"])
    session.flush()
    assert run.status == "queued"
    artifact_id = run.request["input_artifact_id"]
    artifact = session.get(Artifact, uuid.UUID(artifact_id))
    assert artifact is not None and artifact.upload_state == "committed"
    assert artifact.source_kind == "derived"
    blob = env["vault"] / "blobs" / str(env["ctx"].workspace_id) / artifact.storage_key
    payload = json.loads(blob.read_text())
    assert payload["schema_name"] == "materials_lle_job/v1"
    assert payload["method"] == "unifac-lle-miscibility-screen"
    assert payload["components"][0]["unifac_groups"] == {"17": 1}
    assert run.request["method"] == "unifac-lle-miscibility-screen"


def test_engine_not_installed_blocks_honestly(env, session: Session) -> None:
    """No monkeypatch: the real `available()` probe decides."""
    from workers.chemistry.materials.runtime import available

    run = env["service"].request(FIXTURE["spec"])
    session.flush()
    if available():
        assert run.status == "queued"
    else:
        assert run.status == "blocked"
        detail = (run.error or {}).get("detail") or {}
        assert detail.get("capability") == "not_installed"


def _attempt(session: Session, run_id: uuid.UUID) -> RunAttempt:
    return session.execute(select(RunAttempt).where(RunAttempt.run_id == run_id)).scalars().one()


def _usable() -> MaterialsOutcome:
    return MaterialsOutcome(
        status="succeeded",
        usable=True,
        classification="reference_integration",
        phase_state="phase_separated",
        equilibrium_proxy={
            "endpoint_class": "equilibrium_phase_behavior",
            "phase_state": "phase_separated",
            "miscibility_gaps": [{"x_lo": 0.534, "x_hi": 0.981}],
        },
        engine_version="0.6.1",
        isolation={"backend": "container", "enforced": True},
    )


def test_execute_commits_result_artifact_and_succeeds(
    env, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("studio.domain.chemistry.materials.available", lambda: True)
    service = env["service"]
    run = service.request(FIXTURE["spec"])
    attempt = _attempt(session, run.id)
    monkeypatch.setattr(service.engine, "compute", lambda *a, **k: _usable())
    run = service.execute(run.id, attempt.id)
    session.flush()
    assert run.status == "succeeded"
    summary = run.result_summary or {}
    assert summary["usable"] is True
    assert summary["scientific_status"] == "not_validated"
    assert summary["evidence_class"] == "computed_equilibrium_proxy"
    assert summary["phase_state"] == "phase_separated"
    assert summary["supports_endpoints"] == list(SUPPORTS_ENDPOINTS)
    assert summary["does_not_establish"] == list(DOES_NOT_ESTABLISH)
    result_artifact = session.get(Artifact, uuid.UUID(summary["result_artifact_id"]))
    assert result_artifact is not None
    stored = json.loads(
        (
            env["vault"] / "blobs" / str(env["ctx"].workspace_id) / result_artifact.storage_key
        ).read_text()
    )
    assert stored["phase_state"] == "phase_separated"
    assert stored["does_not_establish"] == list(DOES_NOT_ESTABLISH)


def test_execute_engine_failure_maps_to_failed(
    env, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("studio.domain.chemistry.materials.available", lambda: True)
    service = env["service"]
    run = service.request(FIXTURE["spec"])
    attempt = _attempt(session, run.id)

    def raise_missing(*a: object, **k: object) -> None:
        raise EngineFailure("MISSING_PARAMETERS", "no regressed pair")

    monkeypatch.setattr(service.engine, "compute", raise_missing)
    run = service.execute(run.id, attempt.id)
    session.flush()
    assert run.status == "failed"
    assert (run.error or {}).get("code") == "MISSING_PARAMETERS"


def test_execute_cancel_and_timeout_map_to_terminal_states(
    env, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("studio.domain.chemistry.materials.available", lambda: True)
    service = env["service"]

    def raise_cancel(*a: object, **k: object) -> None:
        raise EngineFailure("RUN_CANCELLED", "cancelled")

    monkeypatch.setattr(service.engine, "compute", raise_cancel)
    run = service.request(FIXTURE["spec"])
    run = service.execute(run.id, _attempt(session, run.id).id)
    session.flush()
    assert run.status == "cancelled"

    def raise_timeout(*a: object, **k: object) -> None:
        raise EngineFailure("RUN_TIMEOUT", "timed out")

    monkeypatch.setattr(service.engine, "compute", raise_timeout)
    run = service.request(FIXTURE["spec"])
    run = service.execute(run.id, _attempt(session, run.id).id)
    session.flush()
    assert run.status == "timed_out"


# ------------------------------------------------- AT-0702-2: evaluation


def test_at0702_2_storage_stability_never_established(env, session: Session) -> None:
    """Given equilibrium miscibility output exists, evaluating storage
    stability returns a typed verdict — never a proof."""
    service = env["service"]
    outcome = _usable()
    for endpoint in DOES_NOT_ESTABLISH:
        verdict = service.assess_endpoint(outcome, endpoint)
        assert verdict["established"] is False
        assert verdict["verdict"] == "not_established"
        assert verdict["basis"] == "proxy_scope_gap"


def test_at0702_2_in_scope_endpoint_is_within_proxy_only(env, session: Session) -> None:
    verdict = env["service"].assess_endpoint(_usable(), "equilibrium_miscibility")
    assert verdict["established"] is True
    assert verdict["verdict"] == "within_proxy_scope"


def test_at0702_2_failed_outcome_evaluates_nothing(env, session: Session) -> None:
    bad = MaterialsOutcome(
        status="failed",
        usable=False,
        classification="missing_parameters",
        error={"code": "MISSING_PARAMETERS", "message": "no pair"},
    )
    verdict = env["service"].assess_endpoint(bad, "equilibrium_miscibility")
    assert verdict["established"] is False
    assert verdict["verdict"] == "not_evaluated"


# ------------------------------------------------- AT-0702-3: capability


def test_at0702_3_capability_card_reports_method_and_limits(
    env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Profile enabled + image probed -> the card carries the method's
    benchmark/domain/limits verbatim, with its real state."""
    probe = {
        "adapter_version": "materials-adapter/v1",
        "engine": "thermo",
        "engine_version": "0.6.1",
        "state": "available_tested",
        "methods": {
            "unifac-lle-miscibility-screen/v1": {
                "state": "available_tested",
                "endpoint": "equilibrium_miscibility",
                "domain": "binary liquids, 278.15-333.15 K",
                "benchmark": "water+1-butanol split; water+ethanol homogeneous",
                "limitations": ["equilibrium proxy only", "no polymers"],
            }
        },
    }
    monkeypatch.setattr("workers.chemistry.materials.runtime.capability", lambda: probe)
    monkeypatch.setattr("workers.chemistry.materials.runtime.available", lambda: True)
    report = collect_capabilities(env["settings"])
    assert report["profiles"]["materials"]["status"] == "available"
    card = report["engines"]["materials"]
    assert card["status"] == "available"
    method = card["methods"]["unifac-lle-miscibility-screen/v1"]
    assert method["endpoint"] == "equilibrium_miscibility"
    assert "1-butanol" in method["benchmark"]
    assert "278.15" in method["domain"]
    assert any("proxy" in lim for lim in method["limitations"])


def test_capability_card_disabled_profile_is_honest() -> None:
    report = collect_capabilities(Settings())
    assert report["profiles"]["materials"]["status"] == "disabled"


def test_profile_off_fails_closed(env, session: Session) -> None:
    service = MaterialsService(session, env["ctx"], Settings(profile_materials=False))
    with pytest.raises(DomainError) as exc:
        service.request(FIXTURE["spec"])
    assert exc.value.code == ErrorCode.ENGINE_UNAVAILABLE
