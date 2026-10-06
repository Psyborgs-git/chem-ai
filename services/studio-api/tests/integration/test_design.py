"""CS-0903 integration — design request validation, persistence,
admission, execution, and the capability surface.

AT-0903-1  a supported benign target + configured engine produces a
           run whose result summary labels candidates ``proposed``
           with full provenance.
AT-0903-2  a formulation / polymer-distribution / unknown input kind
           is BLOCKED as ``unsupported`` — never coerced.
License    an undeclared or unverifiable model is BLOCKED
           ``license_unavailable`` before any run attempt (U13).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine_adapter_reinvent.contracts import (
    DOES_NOT_ESTABLISH,
    DesignCandidate,
    DesignOutcome,
    EngineFailure,
)
from studio.api.capabilities import collect_capabilities
from studio.auth.context import load_context
from studio.config.settings import Settings
from studio.domain.chemistry.design import DesignService
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
FIXTURE = json.loads(Path("fixtures/synthetic/design-reinvent.json").read_text())


@pytest.fixture()
def env(session: Session, tmp_path: Path):
    ws = Workspace(slug="design", display_name="Design tests")
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
    settings = Settings(profile_design=True, vault_root=tmp_path / "vault")
    service = DesignService(session, ctx, settings, Vault(tmp_path / "vault"))
    return {"ctx": ctx, "service": service, "vault": tmp_path / "vault", "settings": settings}


# ------------------------------------------------- AT-0903-2: input kinds


@pytest.mark.parametrize("key", ["formulation", "polymer_distribution", "unknown"])
def test_at0903_2_unsupported_input_kind_blocked(env, session: Session, key: str) -> None:
    """Formulation/polymer/unknown input kinds are rejected as
    unsupported — no artifact, no attempt, no coercion."""
    raw = json.loads(json.dumps(FIXTURE["spec"]))
    raw["anchor"] = FIXTURE["unsupported_input_examples"][key]["anchor"]
    run = env["service"].request(raw)
    session.flush()
    assert run.status == "blocked"
    detail = (run.error or {}).get("detail") or {}
    assert detail.get("capability") == "unsupported"
    assert "unsupported" in (run.error or {}).get("message", "")
    assert run.request.get("rejected") is True
    assert session.query(Artifact).count() == 0
    assert session.query(RunAttempt).count() == 0


def test_at0903_2_polymer_smiles_blocked(env, session: Session) -> None:
    """Wildcard repeat-unit notation is not a defined molecule."""
    raw = json.loads(json.dumps(FIXTURE["spec"]))
    raw["anchor"] = FIXTURE["polymer_smiles_example"]["anchor"]
    run = env["service"].request(raw)
    session.flush()
    assert run.status == "blocked"
    assert session.query(RunAttempt).count() == 0


# ------------------------------------------------- U13: license gate


@pytest.mark.parametrize("key", ["unlicensed_license", "undeclared_model", "hash_mismatch"])
def test_license_unavailable_blocked(env, session: Session, key: str) -> None:
    raw = json.loads(json.dumps(FIXTURE["spec"]))
    raw["model"] = FIXTURE["license_examples"][key]
    run = env["service"].request(raw)
    session.flush()
    assert run.status == "blocked"
    detail = (run.error or {}).get("detail") or {}
    assert detail.get("capability") == "license_unavailable"
    assert session.query(Artifact).count() == 0
    assert session.query(RunAttempt).count() == 0


# ------------------------------------------------------------- request


def test_valid_request_persists_input_before_queueing(
    env, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("studio.domain.chemistry.design.available", lambda: True)
    run = env["service"].request(FIXTURE["spec"])
    session.flush()
    assert run.status == "queued"
    artifact_id = run.request["input_artifact_id"]
    artifact = session.get(Artifact, uuid.UUID(artifact_id))
    assert artifact is not None and artifact.upload_state == "committed"
    assert artifact.source_kind == "derived"
    blob = env["vault"] / "blobs" / str(env["ctx"].workspace_id) / artifact.storage_key
    payload = json.loads(blob.read_text())
    assert payload["schema_name"] == "reinvent_design_job/v1"
    assert payload["method"] == "reinvent-de-novo-sampling"
    assert payload["anchor"]["smiles"] == "c1ccncc1"
    assert run.request["method"] == "reinvent-de-novo-sampling"


def test_engine_not_installed_blocks_honestly(env, session: Session) -> None:
    """No monkeypatch: the real `available()` probe decides."""
    from workers.chemistry.design.runtime import available

    run = env["service"].request(FIXTURE["spec"])
    session.flush()
    if available():
        assert run.status == "queued"
    else:
        assert run.status == "blocked"
        detail = (run.error or {}).get("detail") or {}
        assert detail.get("capability") == "not_installed"


# ------------------------------------------------------------- execute


def _attempt(session: Session, run_id: uuid.UUID) -> RunAttempt:
    return session.execute(select(RunAttempt).where(RunAttempt.run_id == run_id)).scalars().one()


def _usable() -> DesignOutcome:
    return DesignOutcome(
        status="succeeded",
        usable=True,
        classification="reference_integration",
        candidates=[
            DesignCandidate(rank=1, smiles="CCO", nll=4.2, similarity_to_anchor=0.05),
            DesignCandidate(rank=2, smiles="CCCO", nll=4.6, similarity_to_anchor=0.04),
        ],
        num_generated=2,
        provenance={
            "model": {"name": "reinvent_pubchem", "license": "apache-2.0"},
            "num_smiles_requested": 2,
        },
        engine_version="4.8",
        isolation={"backend": "container", "enforced": True},
    )


def test_execute_commits_result_artifact_and_succeeds(
    env, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("studio.domain.chemistry.design.available", lambda: True)
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
    assert summary["label"] == "proposed"
    assert summary["execution_gate"] == "independent_plan_approval_required"
    assert summary["evidence_class"] == "proposed_candidates"
    assert summary["num_generated"] == 2
    assert summary["does_not_establish"] == list(DOES_NOT_ESTABLISH)
    result_artifact = session.get(Artifact, uuid.UUID(summary["result_artifact_id"]))
    assert result_artifact is not None
    stored = json.loads(
        (
            env["vault"] / "blobs" / str(env["ctx"].workspace_id) / result_artifact.storage_key
        ).read_text()
    )
    assert stored["label"] == "proposed"
    assert stored["candidates"][0]["label"] == "proposed"
    assert stored["does_not_establish"] == list(DOES_NOT_ESTABLISH)


def test_execute_engine_failure_maps_to_failed(
    env, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("studio.domain.chemistry.design.available", lambda: True)
    service = env["service"]
    run = service.request(FIXTURE["spec"])
    attempt = _attempt(session, run.id)

    def raise_license(*a: object, **k: object) -> None:
        raise EngineFailure("LICENSE_UNAVAILABLE", "unreviewed prior")

    monkeypatch.setattr(service.engine, "compute", raise_license)
    run = service.execute(run.id, attempt.id)
    session.flush()
    assert run.status == "failed"
    assert (run.error or {}).get("code") == "LICENSE_UNAVAILABLE"


def test_execute_cancel_and_timeout_map_to_terminal_states(
    env, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("studio.domain.chemistry.design.available", lambda: True)
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


# ------------------------------------------------- capability surface


def test_capability_card_reports_method_and_limits(env, monkeypatch: pytest.MonkeyPatch) -> None:
    """Profile enabled + image probed -> the card carries the method's
    domain/limits and the licensed asset registry, with real state."""
    probe = {
        "adapter_version": "reinvent-adapter/v1",
        "engine": "reinvent",
        "engine_version": "4.8",
        "state": "available_tested",
        "methods": {
            "reinvent-de-novo-sampling/v1": {
                "state": "available_tested",
                "endpoint": "de_novo_candidate_proposal",
                "domain": "small-molecule generation around a SMILES anchor",
                "benchmark": "pubchem prior emits diverse SMILES",
                "limitations": ["proposals only"],
                "assets": {
                    "reinvent_pubchem": {
                        "license": "apache-2.0",
                        "sha256_verified": True,
                        "state": "available_tested",
                    }
                },
            }
        },
    }
    monkeypatch.setattr("workers.chemistry.design.runtime.capability", lambda: probe)
    monkeypatch.setattr("workers.chemistry.design.runtime.available", lambda: True)
    report = collect_capabilities(env["settings"])
    assert report["profiles"]["design"]["status"] == "available"
    card = report["engines"]["reinvent"]
    assert card["status"] == "available"
    method = card["methods"]["reinvent-de-novo-sampling/v1"]
    assert method["endpoint"] == "de_novo_candidate_proposal"
    assert method["assets"]["reinvent_pubchem"]["license"] == "apache-2.0"


def test_capability_card_disabled_profile_is_honest() -> None:
    report = collect_capabilities(Settings())
    assert report["profiles"]["design"]["status"] == "disabled"


def test_profile_off_fails_closed(env, session: Session) -> None:
    service = DesignService(session, env["ctx"], Settings(profile_design=False))
    with pytest.raises(DomainError) as exc:
        service.request(FIXTURE["spec"])
    assert exc.value.code == ErrorCode.ENGINE_UNAVAILABLE
