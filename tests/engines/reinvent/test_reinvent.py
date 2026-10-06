"""CS-0903 engine tests — live REINVENT inside the pinned container.

AT-0903-1  a supported benign target + configured engine produces a
           design outcome with every candidate labeled ``proposed`` and
           full model/license provenance.
License    an undeclared or unverifiable model is blocked
           ``LICENSE_UNAVAILABLE`` before the engine runs (U13).

The benchmark asserts only plumbing: a completed sampling run emits
parseable SMILES candidates with provenance fields populated. No
chemical or model-quality claim is made. Every test SKIPS explicitly
when the pinned image is absent — absence is reported, never faked.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from workers.chemistry.design.runtime import IMAGE, IsolatedDesign, available, capability

from engine_adapter_reinvent.contracts import DesignJobSpec, EngineFailure
from engine_adapter_reinvent.validation import build_job_payload

pytestmark = pytest.mark.engine

FIXTURE = json.loads(Path("fixtures/synthetic/design-reinvent.json").read_text())

_SPEC_KEYS = {
    "schema_version",
    "method",
    "anchor",
    "model",
    "num_smiles",
    "unique_molecules",
    "randomize_smiles",
    "resources",
}


@pytest.fixture()
def engine() -> IsolatedDesign:
    if not available():
        pytest.skip(f"pinned worker image {IMAGE} not installed")
    return IsolatedDesign()


def _spec(raw: dict | None = None, **over: object) -> DesignJobSpec:
    src = raw if raw is not None else FIXTURE["spec"]
    base = {k: v for k, v in json.loads(json.dumps(src)).items() if k in _SPEC_KEYS}
    for key, value in over.items():
        base[key] = value
    return DesignJobSpec.model_validate(base)


def _payload(spec: DesignJobSpec) -> dict:
    return build_job_payload(spec)


# ------------------------------------------------------------- benchmark


def test_sampling_emits_labeled_proposed_candidates(engine: IsolatedDesign) -> None:
    """AT-0903-1: benign small-molecule anchor + licensed prior ->
    candidates all labeled proposed with model/version/stock provenance."""
    spec = _spec(num_smiles=16)
    outcome = engine.compute(spec, payload=_payload(spec))
    assert outcome.usable and outcome.status == "succeeded"
    assert outcome.classification == "reference_integration"
    assert outcome.label == "proposed"
    assert outcome.scientific_status == "not_validated"
    assert outcome.evidence_class == "proposed_candidates"
    assert outcome.execution_gate == "independent_plan_approval_required"
    assert 0 < outcome.num_generated <= spec.num_smiles
    assert len(outcome.candidates) == outcome.num_generated
    for cand in outcome.candidates:
        assert cand.label == "proposed"
        assert cand.smiles
    prov = outcome.provenance
    assert prov["model"]["name"] == "reinvent_pubchem"
    assert prov["model"]["license"] == "apache-2.0"
    assert prov["model"]["sha256"] == spec.model.sha256
    assert prov["num_smiles_requested"] == spec.num_smiles
    assert outcome.engine_version and outcome.engine_version.startswith("4.8")
    assert outcome.input_digest == spec.digest()
    assert "safety" in outcome.does_not_establish
    assert outcome.isolation.get("backend") == "container"


def test_capability_probe_reports_real_method_state(engine: IsolatedDesign) -> None:
    probe = capability()
    assert probe is not None
    assert probe["engine_version"].startswith("4.8")
    assert probe["state"] == "available_tested"
    method = probe["methods"]["reinvent-de-novo-sampling/v1"]
    assert method["state"] == "available_tested"
    assert method["domain"]
    assert method["limitations"]
    asset = method["assets"]["reinvent_pubchem"]
    assert asset["license"] == "apache-2.0"
    assert asset["sha256_verified"] is True


# ------------------------------------------------- gates in container


def test_unverifiable_model_blocked_in_container(engine: IsolatedDesign) -> None:
    """A model whose declared hash does not match the reviewed registry
    fails LICENSE_UNAVAILABLE — before the engine is invoked."""
    spec = _spec(model=FIXTURE["license_examples"]["hash_mismatch"])
    payload = dict(_payload(_spec()))
    payload["model"] = dict(spec.model.model_dump(mode="json"))
    with pytest.raises(EngineFailure) as exc:
        engine.compute(spec, payload=payload)
    assert exc.value.code == "LICENSE_UNAVAILABLE"


def test_payload_drift_rejected(engine: IsolatedDesign) -> None:
    spec = _spec()
    payload = _payload(spec)
    payload["num_smiles"] = spec.num_smiles + 1
    with pytest.raises(EngineFailure) as exc:
        engine.compute(spec, payload=payload)
    assert exc.value.code == "ENGINE_UNSUPPORTED_INPUT"


def test_cancellation_maps_to_run_cancelled(engine: IsolatedDesign) -> None:
    spec = _spec()
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(EngineFailure) as exc:
        engine.compute(spec, payload=_payload(spec), cancel=cancel)
    assert exc.value.code == "RUN_CANCELLED"


# NOTE (honest coverage): sampling is bounded by the declared wall
# envelope; a live RUN_TIMEOUT requires a run that outlasts the
# minimum resource bound, which cannot be triggered without faking the
# engine — the mapping is exercised at the service boundary in
# test_design.py (integration).
