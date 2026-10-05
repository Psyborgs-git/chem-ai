"""CS-0701 contract/validation unit tests — no engine required.

These run in the default suite: they cover the support matrix, the
physics-level validation, the persisted QCSchema shape, and the honest
result classifier (AT-0701-2 at the parsing boundary).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from engine_adapter_qcengine.contracts import (
    ADAPTER_VERSION,
    EngineFailure,
    QuantumJobSpec,
)
from engine_adapter_qcengine.validation import (
    ANGSTROM_TO_BOHR,
    build_atomic_input,
    canonical_method,
    classify_result,
)

FIXTURE = json.loads(Path("fixtures/synthetic/quantum-water.json").read_text())


def water_spec(**over: object) -> dict:
    spec = json.loads(json.dumps(FIXTURE["spec"]))
    for key, value in over.items():
        spec[key] = value
    return spec


def water_molecule(**over: object) -> dict:
    mol = json.loads(json.dumps(FIXTURE["spec"]["molecule"]))
    for key, value in over.items():
        mol[key] = value
    return mol


# ---------------------------------------------------------------- structure


def test_valid_water_spec_builds_pinned_qcschema() -> None:
    spec = QuantumJobSpec.model_validate(FIXTURE["spec"])
    payload = build_atomic_input(spec)
    assert payload["schema_name"] == "qcschema_input"
    assert payload["schema_version"] == 1
    assert payload["driver"] == "energy"
    assert payload["model"] == {"method": "GFN2-xTB"}
    mol = payload["molecule"]
    assert mol["symbols"] == ["O", "H", "H"]
    # angstrom -> bohr conversion, atom ordering preserved 1:1
    expected = [c * ANGSTROM_TO_BOHR for c in FIXTURE["spec"]["molecule"]["geometry"]]
    assert mol["geometry"] == pytest.approx(expected, rel=1e-12)
    assert mol["molecular_charge"] == 0
    assert mol["molecular_multiplicity"] == 1
    assert spec.digest() == spec.digest()  # deterministic


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        QuantumJobSpec.model_validate(water_spec(unknown_field=1))


def test_missing_charge_and_spin_are_not_defaulted() -> None:
    mol = water_molecule()
    del mol["charge"]
    with pytest.raises(ValidationError):
        QuantumJobSpec.model_validate(water_spec(molecule=mol))
    mol = water_molecule()
    del mol["multiplicity"]
    with pytest.raises(ValidationError):
        QuantumJobSpec.model_validate(water_spec(molecule=mol))


def test_missing_provenance_rejected() -> None:
    mol = water_molecule()
    del mol["provenance"]
    with pytest.raises(ValidationError):
        QuantumJobSpec.model_validate(water_spec(molecule=mol))


def test_polymer_composition_cannot_express_a_job() -> None:
    """A polymer/composition request has no explicit molecule — it is
    invalid input, never an occasion to invent a surrogate (AT-0701-3)."""
    polymer = {
        "program": "xtb",
        "method": "GFN2-xTB",
        "driver": "energy",
        "composition": {"polymer": "PEO", "salt": "LiTFSI", "ratio": "20:1"},
    }
    with pytest.raises(ValidationError):
        QuantumJobSpec.model_validate(polymer)


def test_unknown_element_rejected() -> None:
    with pytest.raises(EngineFailure) as exc:
        build_atomic_input(
            QuantumJobSpec.model_validate(
                water_spec(molecule=water_molecule(symbols=["O", "H", "Xx"]))
            )
        )
    assert exc.value.code == "ENGINE_UNSUPPORTED_INPUT"


def test_geometry_length_must_be_3n() -> None:
    with pytest.raises(EngineFailure) as exc:
        build_atomic_input(
            QuantumJobSpec.model_validate(
                water_spec(molecule=water_molecule(geometry=[0.0, 0.0, 0.0]))
            )
        )
    assert "3N" in exc.value.message


def test_nonfinite_and_coincident_geometry_rejected() -> None:
    with pytest.raises(EngineFailure):
        build_atomic_input(
            QuantumJobSpec.model_validate(
                water_spec(molecule=water_molecule(geometry=[0.0] * 8 + [float("nan")]))
            )
        )
    with pytest.raises(EngineFailure) as exc:
        build_atomic_input(
            QuantumJobSpec.model_validate(water_spec(molecule=water_molecule(geometry=[0.0] * 9)))
        )
    assert "coincide" in exc.value.message


def test_charge_spin_parity_enforced() -> None:
    # H2O has 10 electrons; a doublet (1 unpaired) is impossible (parity).
    # A triplet is legal — O2 is itself a triplet ground state.
    with pytest.raises(EngineFailure) as exc:
        build_atomic_input(
            QuantumJobSpec.model_validate(water_spec(molecule=water_molecule(multiplicity=2)))
        )
    assert "multiplicity" in exc.value.message
    # Stripping 11 electrons off H2O is impossible.
    with pytest.raises(EngineFailure):
        build_atomic_input(
            QuantumJobSpec.model_validate(
                water_spec(molecule=water_molecule(charge=11, multiplicity=1))
            )
        )


# ------------------------------------------------------------------- matrix


def test_unsupported_method_never_substituted() -> None:
    with pytest.raises(ValidationError) as exc:
        QuantumJobSpec.model_validate(water_spec(method="mp2/cc-pvtz"))
    assert "not supported" in str(exc.value)


def test_driver_must_be_in_matrix() -> None:
    with pytest.raises(ValidationError):
        QuantumJobSpec.model_validate(water_spec(method="IPEA-xTB", driver="gradient"))


def test_method_case_normalizes_to_canonical() -> None:
    spec = QuantumJobSpec.model_validate(water_spec(method="gfn2-xtb"))
    assert canonical_method(spec) == "GFN2-xTB"


def test_psi4_requires_explicit_basis_and_xtb_rejects_one() -> None:
    psi4 = water_spec(program="psi4", method="hf")
    with pytest.raises(ValidationError):
        QuantumJobSpec.model_validate(psi4)
    ok = QuantumJobSpec.model_validate({**psi4, "basis": "sto-3g"})
    assert build_atomic_input(ok)["model"] == {"method": "hf", "basis": "sto-3g"}
    with pytest.raises(ValidationError):
        QuantumJobSpec.model_validate(water_spec(basis="def2-svp"))


def test_keyword_and_solvent_allowlists() -> None:
    with pytest.raises(ValidationError):
        QuantumJobSpec.model_validate(water_spec(keywords={"savemos": True}))
    with pytest.raises(ValidationError):
        QuantumJobSpec.model_validate(water_spec(keywords={"solvent": "acetone-d6-unsupported"}))
    ok = QuantumJobSpec.model_validate(
        water_spec(keywords={"solvent": "water", "max_iterations": 200})
    )
    assert build_atomic_input(ok)["keywords"]["solvent"] == "water"


# ----------------------------------------------------- classifier (AT-0701-2)


def _result(**kw: object) -> dict:
    base = {
        "success": True,
        "return_result": -5.070371505959063,
        "properties": {"return_energy": -5.070371505959063},
        "provenance": {"creator": "xtb", "version": "1.0.0"},
    }
    base.update(kw)
    return base


def test_exit0_success_with_finite_output_is_usable() -> None:
    verdict = classify_result(program="xtb", driver="energy", result=_result())
    assert verdict["usable"] and verdict["classification"] == "reference_integration"


@pytest.mark.parametrize(
    "result",
    [
        _result(properties={}),  # exit-0, no energy — malformed
        _result(properties={"return_energy": float("nan")}),  # nonfinite
        _result(properties={"return_energy": "oops"}),
        _result(success=False, error={"error_message": "SCC not converged"}),
    ],
)
def test_malformed_or_failed_output_is_not_usable(result: dict) -> None:
    verdict = classify_result(program="xtb", driver="energy", result=result)
    assert not verdict["usable"]
    assert verdict["classification"] in {"malformed_result", "engine_failure"}


def test_gradient_requires_finite_vector() -> None:
    good = _result(
        return_result=[[0.0, 0.0, 0.01]] * 3,
        properties={"return_energy": -5.07},
    )
    assert classify_result(program="xtb", driver="gradient", result=good)["usable"]
    bad = _result(return_result=[[0.0, 0.0, float("inf")]] * 3)
    verdict = classify_result(program="xtb", driver="gradient", result=bad)
    assert not verdict["usable"] and verdict["classification"] == "malformed_result"


def test_missing_binaries_report_unavailable_not_success() -> None:
    """No image -> the runtime raises the honest unavailable state."""
    from workers.chemistry.quantum import runtime

    if runtime.available():
        pytest.skip("pinned image present — unavailable path exercised in CI")
    spec = QuantumJobSpec.model_validate(FIXTURE["spec"])
    with pytest.raises(EngineFailure) as exc:
        runtime.IsolatedQuantum().compute(spec, payload=build_atomic_input(spec))
    assert exc.value.code == "ENGINE_UNAVAILABLE"


def test_capability_probe_shape() -> None:
    from workers.chemistry.quantum import runtime

    if not runtime.available():
        pytest.skip("pinned image absent — probe covered by engine-marked tests")
    probe = runtime.capability()
    assert probe is not None
    assert probe["adapter_version"] == ADAPTER_VERSION
    assert probe["programs"]["xtb"]["state"] == "available_tested"
    assert probe["programs"]["psi4"]["state"] == "not_installed"
