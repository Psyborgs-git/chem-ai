"""CS-0702 engine tests — live thermo inside the pinned container.

AT-0702-1  missing required parameters -> the job fails with
           MISSING_PARAMETERS / ENGINE_UNSUPPORTED_INPUT, never a
           silently zero-filled result.
AT-0702-3  the capability probe reports real per-method states with
           the documented benchmark/domain/limits.

Benchmarks assert documented qualitative LLE behavior
(water+1-butanol splits; water+ethanol/methanol and benzene+hexane are
homogeneous); the numeric gap bounds are an implementation regression
lock, not an experimental fit. Every test SKIPS explicitly when the
pinned image is absent — absence is reported, never faked.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from workers.chemistry.materials.runtime import IMAGE, IsolatedMaterials, available, capability

from engine_adapter_materials.contracts import EngineFailure, MaterialsJobSpec
from engine_adapter_materials.validation import build_job_payload

pytestmark = pytest.mark.engine

FIXTURE = json.loads(Path("fixtures/synthetic/materials-lle.json").read_text())
REFERENCE = FIXTURE["reference"]


@pytest.fixture()
def engine() -> IsolatedMaterials:
    if not available():
        pytest.skip(f"pinned worker image {IMAGE} not installed")
    return IsolatedMaterials()


_SPEC_KEYS = {"schema_version", "method", "components", "conditions", "grid_points", "resources"}


def _spec(raw: dict | None = None, **over: object) -> MaterialsJobSpec:
    src = raw if raw is not None else FIXTURE["spec"]
    base = {k: v for k, v in json.loads(json.dumps(src)).items() if k in _SPEC_KEYS}
    for key, value in over.items():
        base[key] = value
    return MaterialsJobSpec.model_validate(base)


def _payload(spec: MaterialsJobSpec) -> dict:
    return build_job_payload(spec)


# ------------------------------------------------------------- benchmark


def test_reference_butanol_split(engine: IsolatedMaterials) -> None:
    spec = _spec()
    outcome = engine.compute(spec, payload=_payload(spec))
    assert outcome.usable and outcome.status == "succeeded"
    assert outcome.classification == "reference_integration"
    assert outcome.scientific_status == "not_validated"
    assert outcome.evidence_class == "computed_equilibrium_proxy"
    assert outcome.phase_state == REFERENCE["phase_state"]
    proxy = outcome.equilibrium_proxy
    assert proxy["endpoint_class"] == "equilibrium_phase_behavior"
    assert len(proxy["miscibility_gaps"]) == 1
    gap = proxy["miscibility_gaps"][0]
    assert gap["x_lo"] == pytest.approx(REFERENCE["gap_lo"], abs=REFERENCE["gap_lo_tolerance"])
    assert gap["x_hi"] == pytest.approx(REFERENCE["gap_hi"], abs=REFERENCE["gap_hi_tolerance"])
    nominal = proxy["nominal_composition"]
    assert nominal["x1"] == 0.7 and nominal["inside_miscibility_gap"] is True
    assert outcome.engine_version == "0.6.1"
    assert outcome.input_digest == spec.digest()
    ctx = outcome.model_context
    assert ctx["ensemble"] == "isothermal_isobaric_two_liquid"
    assert ctx["sampling"]["grid_points"] == spec.grid_points
    assert ctx["calibration"].startswith("none")
    assert outcome.isolation.get("backend") == "container"


@pytest.mark.parametrize("key", ["water_ethanol", "water_methanol", "benzene_hexane"])
def test_documented_homogeneous_systems(engine: IsolatedMaterials, key: str) -> None:
    raw = FIXTURE["homogeneous_examples"][key]
    spec = _spec(raw)
    outcome = engine.compute(spec, payload=_payload(spec))
    assert outcome.usable and outcome.status == "succeeded"
    assert outcome.phase_state == raw["expected_phase_state"] == "homogeneous"
    assert outcome.equilibrium_proxy["miscibility_gaps"] == []


def test_capability_probe_reports_real_method_state(engine: IsolatedMaterials) -> None:
    probe = capability()
    assert probe is not None
    assert probe["engine_version"] == "0.6.1"
    assert probe["state"] == "available_tested"
    method = probe["methods"]["unifac-lle-miscibility-screen/v1"]
    assert method["state"] == "available_tested"
    assert method["endpoint"] == "equilibrium_miscibility"
    assert method["domain"]
    assert method["benchmark"]
    assert method["limitations"]


# ------------------------------------------------- AT-0702-1 in container


def test_missing_pair_fails_closed_not_zero_filled(engine: IsolatedMaterials) -> None:
    """Inside the worker the live LLEUFIP table is authoritative —
    DMSO/water has no regressed pair and the job fails MISSING_PARAMETERS
    instead of producing a zero-filled gamma field."""
    raw = FIXTURE["missing_parameters_example"]
    # Host-side payload build already fails coverage; construct the
    # request directly to exercise the container-side gate too.
    spec = _spec(raw)
    payload = {
        "schema_name": "materials_lle_job/v1",
        "schema_version": 1,
        "method": "unifac-lle-miscibility-screen",
        "method_version": "v1",
        "components": [
            {"name": "water", "unifac_groups": {"17": 1}},
            {"name": "dmso", "unifac_groups": {"57": 1}},
        ],
        "conditions": {"temperature_k": 298.15, "nominal_x1": None},
        "grid_points": 801,
        "adapter_version": "materials-adapter/v1",
    }
    with pytest.raises(EngineFailure) as exc:
        engine.compute(spec, payload=payload)
    assert exc.value.code == "MISSING_PARAMETERS"


def test_payload_drift_rejected(engine: IsolatedMaterials) -> None:
    spec = _spec()
    payload = _payload(spec)
    payload["components"][1]["unifac_groups"] = {"1": 1, "2": 2, "14": 1}
    with pytest.raises(EngineFailure) as exc:
        engine.compute(spec, payload=payload)
    assert exc.value.code == "ENGINE_UNSUPPORTED_INPUT"


def test_cancellation_maps_to_run_cancelled(engine: IsolatedMaterials) -> None:
    """A cancellation already raised when the run launches aborts it —
    RUN_CANCELLED, never a result committed."""
    spec = _spec()
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(EngineFailure) as exc:
        engine.compute(spec, payload=_payload(spec), cancel=cancel)
    assert exc.value.code == "RUN_CANCELLED"


# NOTE (honest coverage): this method's grid screen finishes in well
# under a second even at the maximum 4001-point grid, so no real run
# can outlast the minimum 1-second wall bound — a live RUN_TIMEOUT
# cannot be triggered without faking the engine, and we do not fake
# it. The timed_out -> RUN_TIMEOUT mapping is the same executor path
# CS-0701 tests live, and it is exercised at the service boundary in
# test_materials.py (integration).
