"""CS-0701 engine tests — live xtb inside the pinned container.

AT-0701-1  benign reference geometry -> usable result within the
           documented method/version tolerance.
AT-0701-2  exit-0 failures and engine-reported failures are never
           usable; timeout/cancel/memory bounds all map to honest
           states, not success.

Every test SKIPS explicitly when the pinned image is absent — absence
is reported, never faked.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest
from workers.chemistry.quantum.runtime import IMAGE, IsolatedQuantum, available, capability

from engine_adapter_qcengine.contracts import EngineFailure, QuantumJobSpec
from engine_adapter_qcengine.validation import build_atomic_input

pytestmark = pytest.mark.engine

FIXTURE = json.loads(Path("fixtures/synthetic/quantum-water.json").read_text())
REFERENCE = FIXTURE["reference"]


@pytest.fixture()
def engine() -> IsolatedQuantum:
    if not available():
        pytest.skip(f"pinned worker image {IMAGE} not installed")
    return IsolatedQuantum()


def _spec(**over: object) -> QuantumJobSpec:
    raw = json.loads(json.dumps(FIXTURE["spec"]))
    for key, value in over.items():
        raw[key] = value
    return QuantumJobSpec.model_validate(raw)


def _payload(spec: QuantumJobSpec) -> dict:
    return build_atomic_input(spec)


# AT-0701-1 ---------------------------------------------------------------


def test_at0701_1_reference_water_energy(engine: IsolatedQuantum) -> None:
    spec = _spec()
    outcome = engine.compute(spec, payload=_payload(spec))
    assert outcome.usable and outcome.status == "succeeded"
    assert outcome.classification == "reference_integration"
    assert outcome.scientific_status == "not_validated"
    assert outcome.energy_hartree == pytest.approx(
        REFERENCE["energy_hartree"], abs=REFERENCE["tolerance_hartree"]
    )
    assert outcome.engine == "xtb" and outcome.engine_version == "22.1"
    assert outcome.qcengine_version == "0.51.0"
    assert outcome.qcelemental_version == "0.51.2"
    assert outcome.provenance.get("creator") == "xtb"
    assert outcome.isolation.get("backend") == "container"
    assert outcome.raw_stdout  # raw engine output preserved (bounded)


def test_at0701_1_gradient_driver(engine: IsolatedQuantum) -> None:
    spec = _spec(driver="gradient")
    outcome = engine.compute(spec, payload=_payload(spec))
    assert outcome.usable
    grad = outcome.return_result
    assert isinstance(grad, list) and len(grad) == 3
    assert all(len(row) == 3 for row in grad)


def test_capability_probe_reports_real_states(engine: IsolatedQuantum) -> None:
    probe = capability()
    assert probe is not None
    assert probe["programs"]["xtb"] == {"state": "available_tested", "version": "22.1"}
    assert probe["programs"]["psi4"]["state"] == "not_installed"
    assert probe["qcengine_version"] == "0.51.0"


# AT-0701-2 ---------------------------------------------------------------


def test_at0701_2_nonconvergence_is_not_usable(engine: IsolatedQuantum) -> None:
    """SCC capped at one iteration: the engine finishes its contract
    without converging — usable must be false, never a success."""
    spec = QuantumJobSpec.model_validate(FIXTURE["nonconvergence_example"])
    outcome = engine.compute(spec, payload=_payload(spec))
    assert outcome.status == "failed" and not outcome.usable
    assert outcome.classification == "engine_failure"
    assert outcome.converged is False
    assert "not converge" in (outcome.error or {}).get("message", "")


def test_engine_crash_reports_failure_not_partial(engine: IsolatedQuantum) -> None:
    """Uranium (Z=92) is past GFN parametrization (Z<=86): xtb-python
    segfaults rather than erroring — the container dies and the runtime
    reports failure, never a partial result."""
    spec = QuantumJobSpec.model_validate(FIXTURE["engine_crash_example"])
    with pytest.raises(EngineFailure) as exc:
        engine.compute(spec, payload=_payload(spec))
    assert exc.value.code == "ENGINE_UNAVAILABLE"


def test_at0701_2_drift_between_payload_and_spec_rejected(
    engine: IsolatedQuantum,
) -> None:
    """A persisted payload that does not match the declared spec is
    rejected inside the worker — bytes, not trust, are the contract."""
    spec = _spec()
    payload = _payload(spec)
    payload["molecule"]["molecular_charge"] = 1  # tampered after persist
    with pytest.raises(EngineFailure) as exc:
        engine.compute(spec, payload=payload)
    assert exc.value.code == "ENGINE_UNSUPPORTED_INPUT"


def test_timeout_maps_to_run_timeout(engine: IsolatedQuantum) -> None:
    spec = _spec(resources={"wall_seconds": 1, "memory_mebibytes": 1024, "ncores": 1})
    with pytest.raises(EngineFailure) as exc:
        engine.compute(spec, payload=_payload(spec))
    assert exc.value.code == "RUN_TIMEOUT"


def test_cancellation_maps_to_run_cancelled(engine: IsolatedQuantum) -> None:
    spec = _spec()
    cancel = threading.Event()
    threading.Timer(1.5, cancel.set).start()
    started = time.monotonic()
    with pytest.raises(EngineFailure) as exc:
        engine.compute(spec, payload=_payload(spec), cancel=cancel)
    assert exc.value.code == "RUN_CANCELLED"
    assert time.monotonic() - started < 30


def test_memory_bound_fails_not_succeeds(engine: IsolatedQuantum) -> None:
    """32 MiB cannot hold the interpreter: the container dies and the
    runtime reports failure, never a partial result."""
    spec = _spec(resources={"wall_seconds": 60, "memory_mebibytes": 32, "ncores": 1})
    with pytest.raises(EngineFailure) as exc:
        engine.compute(spec, payload=_payload(spec))
    assert exc.value.code == "ENGINE_UNAVAILABLE"
