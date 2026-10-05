"""CS-0701 integration — validation, persistence, admission, execution.

AT-0701-3  a polymer composition (or any request missing required
           parameters) is BLOCKED — no surrogate molecule is invented.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine_adapter_qcengine.contracts import EngineFailure, QuantumOutcome
from studio.auth.context import load_context
from studio.config.settings import Settings
from studio.domain.chemistry.quantum import QuantumService
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
FIXTURE = json.loads(Path("fixtures/synthetic/quantum-water.json").read_text())


@pytest.fixture()
def env(session: Session, tmp_path: Path):
    ws = Workspace(slug="quantum", display_name="Quantum tests")
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
    settings = Settings(profile_quantum=True, vault_root=tmp_path / "vault")
    service = QuantumService(session, ctx, settings, Vault(tmp_path / "vault"))
    return {"ctx": ctx, "service": service, "vault": tmp_path / "vault"}


def _polymer_request() -> dict:
    """A polymer composition: real chemistry, no explicit molecule —
    the request cannot be honored and must be blocked (AT-0701-3)."""
    return {
        "program": "xtb",
        "method": "GFN2-xTB",
        "driver": "energy",
        "composition": {"polymer": "PEO", "salt": "LiTFSI", "ratio": "EO:Li = 20:1"},
    }


def test_at0701_3_polymer_composition_blocked_no_surrogate(env, session: Session) -> None:
    run = env["service"].request(_polymer_request())
    session.flush()
    assert run.status == "blocked"
    assert (run.error or {}).get("code") == "blocked"
    assert "insufficient_inputs" in (run.error or {}).get("message", "")
    detail = (run.error or {}).get("detail") or {}
    assert detail.get("capability") == "insufficient_inputs"
    # No molecule was synthesized: nothing was persisted, nothing queued.
    assert run.request.get("rejected") is True
    assert session.query(Artifact).count() == 0
    assert session.query(RunAttempt).count() == 0
    assert not (env["vault"] / "blobs").exists()


def test_at0701_3_missing_parameters_blocked(env, session: Session) -> None:
    """Explicit molecule shape but no charge/spin — still blocked."""
    raw = json.loads(json.dumps(FIXTURE["spec"]))
    del raw["molecule"]["charge"]
    del raw["molecule"]["multiplicity"]
    run = env["service"].request(raw)
    session.flush()
    assert run.status == "blocked"
    assert session.query(RunAttempt).count() == 0


def test_valid_request_persists_input_before_queueing(
    env, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("studio.domain.chemistry.quantum.available", lambda: True)
    run = env["service"].request(FIXTURE["spec"])
    session.flush()
    assert run.status == "queued"
    artifact_id = run.request["input_artifact_id"]
    artifact = session.get(Artifact, uuid.UUID(artifact_id))
    assert artifact is not None and artifact.upload_state == "committed"
    assert artifact.source_kind == "derived"
    blob = env["vault"] / "blobs" / str(env["ctx"].workspace_id) / artifact.storage_key
    payload = json.loads(blob.read_text())
    assert payload["schema_name"] == "qcschema_input"
    assert payload["molecule"]["symbols"] == ["O", "H", "H"]
    # QCSchema-native units: bohr, not the angstrom the caller sent.
    assert payload["molecule"]["geometry"][2] == pytest.approx(-0.73578586109551, rel=1e-9)


def test_engine_not_installed_blocks_honestly(env, session: Session) -> None:
    """No monkeypatch: the real `available()` probe decides. Either the
    image is present (admitted) or absent (blocked) — never a lie."""
    from workers.chemistry.quantum.runtime import available

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


def _usable() -> QuantumOutcome:
    return QuantumOutcome(
        status="succeeded",
        usable=True,
        converged=True,
        classification="reference_integration",
        energy_hartree=-5.070371505959063,
        engine="xtb",
        engine_version="22.1",
        qcengine_version="0.51.0",
        qcelemental_version="0.51.2",
        scientific_status="not_validated",
        raw_stdout="fixture engine output",
    )


def test_execute_commits_result_artifact_and_succeeds(
    env, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("studio.domain.chemistry.quantum.available", lambda: True)
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
    result_artifact = session.get(Artifact, uuid.UUID(summary["result_artifact_id"]))
    assert result_artifact is not None
    stored = json.loads(
        (
            env["vault"] / "blobs" / str(env["ctx"].workspace_id) / result_artifact.storage_key
        ).read_text()
    )
    assert stored["energy_hartree"] == pytest.approx(-5.070371505959063)
    assert stored["isolation"] == {}


def test_execute_malformed_outcome_fails_not_succeeds(
    env, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AT-0701-2 at the run boundary: exit-0-but-missing-outputs reaches
    failed, never succeeded."""
    monkeypatch.setattr("studio.domain.chemistry.quantum.available", lambda: True)
    service = env["service"]
    run = service.request(FIXTURE["spec"])
    attempt = _attempt(session, run.id)
    bad = QuantumOutcome(
        status="failed",
        usable=False,
        classification="malformed_result",
        engine="xtb",
        error={"code": "ENGINE_MALFORMED_OUTPUT", "message": "no return_energy"},
    )
    monkeypatch.setattr(service.engine, "compute", lambda *a, **k: bad)
    run = service.execute(run.id, attempt.id)
    session.flush()
    assert run.status == "failed"
    assert (run.error or {}).get("code") == "malformed_result"


def test_execute_cancel_and_timeout_map_to_terminal_states(
    env, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("studio.domain.chemistry.quantum.available", lambda: True)
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


def test_profile_off_fails_closed(env, session: Session) -> None:
    service = QuantumService(session, env["ctx"], Settings(profile_quantum=False))
    with pytest.raises(DomainError) as exc:
        service.request(FIXTURE["spec"])
    assert exc.value.code == ErrorCode.ENGINE_UNAVAILABLE
