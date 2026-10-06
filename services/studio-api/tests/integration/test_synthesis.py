"""CS-0903 integration — synthesis request validation, persistence,
admission, execution, and the capability surface.

AT-0903-1  a supported benign target + configured engine produces a
           run whose result summary labels routes ``proposed`` with
           full model/stock provenance.
AT-0903-2  a formulation / polymer-distribution / unknown / mixture
           input is BLOCKED as ``unsupported`` — never coerced.
AT-0903-3  a route whose precursors all resolve to the purchasable
           stock is still a hypothesis — ``assess_execution`` reports
           ``independent_plan_approval_required`` and executable=False.
License    an undeclared or unverifiable model/stock asset is BLOCKED
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

from engine_adapter_aizynthfinder.contracts import (
    DOES_NOT_ESTABLISH,
    EngineFailure,
    ProposedRoute,
    RouteOutcome,
)
from studio.api.capabilities import collect_capabilities
from studio.auth.context import load_context
from studio.config.settings import Settings
from studio.domain.chemistry.synthesis import SynthesisService
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
FIXTURE = json.loads(Path("fixtures/synthetic/synthesis-aizynthfinder.json").read_text())


@pytest.fixture()
def env(session: Session, tmp_path: Path):
    ws = Workspace(slug="synthesis", display_name="Synthesis tests")
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
    settings = Settings(profile_synthesis=True, vault_root=tmp_path / "vault")
    service = SynthesisService(session, ctx, settings, Vault(tmp_path / "vault"))
    return {"ctx": ctx, "service": service, "vault": tmp_path / "vault", "settings": settings}


# ------------------------------------------------- AT-0903-2: input kinds


@pytest.mark.parametrize(
    "key,capability",
    [
        ("formulation", "unsupported"),
        ("polymer_distribution", "unsupported"),
        ("unknown", "unsupported"),
        # A mixture is the right *kind* but not one defined molecule —
        # a structural reject (insufficient_inputs), still blocked
        # with no artifact and no attempt, never coerced.
        ("mixture_smiles", "insufficient_inputs"),
    ],
)
def test_at0903_2_unsupported_input_blocked(
    env, session: Session, key: str, capability: str
) -> None:
    """Formulation/polymer/unknown kinds AND multi-component SMILES
    are rejected — no artifact, no attempt, no coercion."""
    raw = json.loads(json.dumps(FIXTURE["spec"]))
    raw["target"] = FIXTURE["unsupported_input_examples"][key]["target"]
    run = env["service"].request(raw)
    session.flush()
    assert run.status == "blocked"
    detail = (run.error or {}).get("detail") or {}
    assert detail.get("capability") == capability
    assert run.request.get("rejected") is True
    assert session.query(Artifact).count() == 0
    assert session.query(RunAttempt).count() == 0


# ------------------------------------------------- U13: license gate


@pytest.mark.parametrize(
    "key,field",
    [
        ("unlicensed_stock", "stock"),
        ("undeclared_policy", "policy_model"),
        ("hash_mismatch_templates", "templates"),
    ],
)
def test_license_unavailable_blocked(env, session: Session, key: str, field: str) -> None:
    raw = json.loads(json.dumps(FIXTURE["spec"]))
    raw[field] = FIXTURE["license_examples"][key]
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
    monkeypatch.setattr("studio.domain.chemistry.synthesis.available", lambda: True)
    run = env["service"].request(FIXTURE["spec"])
    session.flush()
    assert run.status == "queued"
    artifact_id = run.request["input_artifact_id"]
    artifact = session.get(Artifact, uuid.UUID(artifact_id))
    assert artifact is not None and artifact.upload_state == "committed"
    blob = env["vault"] / "blobs" / str(env["ctx"].workspace_id) / artifact.storage_key
    payload = json.loads(blob.read_text())
    assert payload["schema_name"] == "aizynthfinder_route_job/v1"
    assert payload["method"] == "aizynthfinder-mcts-route"
    assert payload["target"]["smiles"] == "Cn1c(=O)c2c(ncn2C)n(C)c1=O"
    assert payload["stock"]["name"] == "zinc_stock"


def test_engine_not_installed_blocks_honestly(env, session: Session) -> None:
    from workers.chemistry.synthesis.runtime import available

    run = env["service"].request(FIXTURE["spec"])
    session.flush()
    if available():
        assert run.status == "queued"
    else:
        assert run.status == "blocked"
        assert (run.error or {}).get("detail", {}).get("capability") == "not_installed"


# ------------------------------------------------------------- execute


def _attempt(session: Session, run_id: uuid.UUID) -> RunAttempt:
    return session.execute(select(RunAttempt).where(RunAttempt.run_id == run_id)).scalars().one()


def _usable(solved: bool = True) -> RouteOutcome:
    return RouteOutcome(
        status="succeeded",
        usable=True,
        classification="reference_integration",
        routes=[
            ProposedRoute(
                rank=1,
                is_solved=solved,
                all_precursors_in_stock=solved,
                num_reactions=2,
                precursor_smiles=["CCO", "O=CC"],
                precursors_in_stock=["CCO", "O=CC"] if solved else [],
                score=0.9,
            )
        ],
        num_solved=1 if solved else 0,
        provenance={
            "policy_model": {"name": "uspto_expansion", "license": "cc-by-4.0"},
            "stock": {"name": "zinc_stock", "license": "mit"},
        },
        search_stats={"number_of_solved_routes": 1 if solved else 0},
        engine_version="4.4.1",
        isolation={"backend": "container", "enforced": True},
    )


def test_execute_commits_result_artifact_and_succeeds(
    env, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("studio.domain.chemistry.synthesis.available", lambda: True)
    service = env["service"]
    run = service.request(FIXTURE["spec"])
    attempt = _attempt(session, run.id)
    monkeypatch.setattr(service.engine, "compute", lambda *a, **k: _usable())
    run = service.execute(run.id, attempt.id)
    session.flush()
    assert run.status == "succeeded"
    summary = run.result_summary or {}
    assert summary["usable"] is True
    assert summary["label"] == "proposed"
    assert summary["num_solved"] == 1
    assert summary["execution_gate"] == "independent_plan_approval_required"
    assert summary["evidence_class"] == "proposed_route_hypothesis"
    assert summary["does_not_establish"] == list(DOES_NOT_ESTABLISH)
    result_artifact = session.get(Artifact, uuid.UUID(summary["result_artifact_id"]))
    assert result_artifact is not None
    stored = json.loads(
        (
            env["vault"] / "blobs" / str(env["ctx"].workspace_id) / result_artifact.storage_key
        ).read_text()
    )
    assert stored["label"] == "proposed"
    assert stored["routes"][0]["label"] == "proposed"


def test_execute_engine_failure_maps_to_failed(
    env, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("studio.domain.chemistry.synthesis.available", lambda: True)
    service = env["service"]
    run = service.request(FIXTURE["spec"])
    attempt = _attempt(session, run.id)

    def raise_license(*a: object, **k: object) -> None:
        raise EngineFailure("LICENSE_UNAVAILABLE", "unreviewed stock")

    monkeypatch.setattr(service.engine, "compute", raise_license)
    run = service.execute(run.id, attempt.id)
    session.flush()
    assert run.status == "failed"
    assert (run.error or {}).get("code") == "LICENSE_UNAVAILABLE"


def test_execute_cancel_and_timeout_map_to_terminal_states(
    env, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("studio.domain.chemistry.synthesis.available", lambda: True)
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


# --------------------------------------------- AT-0903-3: execution gate


def test_at0903_3_stock_resolved_route_still_needs_independent_approval(env) -> None:
    """A solved route with every precursor in the purchasable stock
    assesses as a hypothesis requiring independent plan approval —
    never an executable instruction."""
    verdict = env["service"].assess_execution(_usable(solved=True))
    assert verdict["executable"] is False
    assert verdict["verdict"] == "independent_plan_approval_required"
    assert verdict["basis"] == "proposed_route_is_hypothesis"
    assert verdict["num_stock_resolved_routes"] == 1


def test_assess_execution_on_failed_outcome_not_evaluated(env) -> None:
    bad = RouteOutcome(
        status="failed",
        usable=False,
        classification="unavailable",
        error={"code": "ENGINE_UNAVAILABLE", "message": "x"},
    )
    verdict = env["service"].assess_execution(bad)
    assert verdict["executable"] is False
    assert verdict["verdict"] == "not_evaluated"


# ------------------------------------------------- capability surface


def test_capability_card_reports_method_and_limits(env, monkeypatch: pytest.MonkeyPatch) -> None:
    probe = {
        "adapter_version": "aizynthfinder-adapter/v1",
        "engine": "aizynthfinder",
        "engine_version": "4.4.1",
        "state": "available_tested",
        "methods": {
            "aizynthfinder-mcts-route/v1": {
                "state": "available_tested",
                "endpoint": "proposed_retrosynthesis_routes",
                "domain": "retrosynthesis search over uspto policy + zinc stock",
                "benchmark": "bounded mcts emits a route manifest",
                "limitations": ["proposals only"],
                "assets": {
                    "uspto_expansion": {
                        "license": "cc-by-4.0",
                        "sha256_verified": True,
                        "state": "available_tested",
                    }
                },
            }
        },
    }
    monkeypatch.setattr("workers.chemistry.synthesis.runtime.capability", lambda: probe)
    monkeypatch.setattr("workers.chemistry.synthesis.runtime.available", lambda: True)
    report = collect_capabilities(env["settings"])
    assert report["profiles"]["synthesis"]["status"] == "available"
    card = report["engines"]["aizynthfinder"]
    assert card["status"] == "available"
    method = card["methods"]["aizynthfinder-mcts-route/v1"]
    assert method["endpoint"] == "proposed_retrosynthesis_routes"
    assert method["assets"]["uspto_expansion"]["license"] == "cc-by-4.0"


def test_capability_card_disabled_profile_is_honest() -> None:
    report = collect_capabilities(Settings())
    assert report["profiles"]["synthesis"]["status"] == "disabled"


def test_profile_off_fails_closed(env, session: Session) -> None:
    service = SynthesisService(session, env["ctx"], Settings(profile_synthesis=False))
    with pytest.raises(DomainError) as exc:
        service.request(FIXTURE["spec"])
    assert exc.value.code == ErrorCode.ENGINE_UNAVAILABLE
