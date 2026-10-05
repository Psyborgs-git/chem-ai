"""CS-0702 contract/validation unit tests — no engine required.

Covers the strict spec shape, the required-parameter coverage rules
(AT-0702-1 at the validation boundary), the convex-hull criterion on
synthetic curves, and the typed proxy/endpoint verdicts (AT-0702-2).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from engine_adapter_materials.contracts import (
    DOES_NOT_ESTABLISH,
    METHOD_ID,
    SUPPORTS_ENDPOINTS,
    EngineFailure,
    MaterialsJobSpec,
)
from engine_adapter_materials.validation import (
    build_job_payload,
    check_parameter_coverage,
    evaluate_endpoint,
    gibbs_mixing_surface,
    lower_convex_hull,
    miscibility_gaps,
)

FIXTURE = json.loads(Path("fixtures/synthetic/materials-lle.json").read_text())


_SPEC_KEYS = {"schema_version", "method", "components", "conditions", "grid_points", "resources"}


def _spec_dict(raw: dict) -> dict:
    return {k: v for k, v in raw.items() if k in _SPEC_KEYS}


def butanol_spec(**over: object) -> dict:
    spec = json.loads(json.dumps(FIXTURE["spec"]))
    for key, value in over.items():
        spec[key] = value
    return spec


# ---------------------------------------------------------------- structure


def test_valid_spec_builds_pinned_payload() -> None:
    spec = MaterialsJobSpec.model_validate(FIXTURE["spec"])
    payload = build_job_payload(spec)
    assert payload["schema_name"] == "materials_lle_job/v1"
    assert payload["method"] == METHOD_ID
    assert payload["method_version"] == "v1"
    assert payload["components"][0]["unifac_groups"] == {"17": 1}
    assert payload["components"][1]["unifac_groups"] == {"1": 1, "2": 3, "14": 1}
    assert payload["conditions"]["temperature_k"] == 298.15
    assert spec.digest() == spec.digest()  # deterministic


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        MaterialsJobSpec.model_validate(butanol_spec(unknown_field=1))


def test_component_count_must_be_two() -> None:
    spec = butanol_spec()
    spec["components"] = spec["components"][:1]
    with pytest.raises(ValidationError):
        MaterialsJobSpec.model_validate(spec)
    spec = butanol_spec()
    spec["components"] = spec["components"] * 2
    with pytest.raises(ValidationError):
        MaterialsJobSpec.model_validate(spec)


def test_empty_groups_and_bad_ids_rejected() -> None:
    spec = butanol_spec()
    spec["components"][1]["unifac_groups"] = {}
    with pytest.raises(ValidationError):
        MaterialsJobSpec.model_validate(spec)
    spec = butanol_spec()
    spec["components"][1]["unifac_groups"] = {"abc": 1}
    with pytest.raises(ValidationError):
        MaterialsJobSpec.model_validate(spec)
    spec = butanol_spec()
    spec["components"][1]["unifac_groups"] = {"2": 0}
    with pytest.raises(ValidationError):
        MaterialsJobSpec.model_validate(spec)


def test_temperature_outside_domain_rejected() -> None:
    spec = butanol_spec()
    spec["conditions"]["temperature_k"] = 373.15  # water+butanol boiling —
    # the LLE table was not regressed here; the method does not extrapolate
    with pytest.raises(ValidationError, match="domain"):
        MaterialsJobSpec.model_validate(spec)
    spec = butanol_spec()
    spec["conditions"]["temperature_k"] = 250.0
    with pytest.raises(ValidationError):
        MaterialsJobSpec.model_validate(spec)


def test_nominal_x1_must_be_strictly_inside_unit_interval() -> None:
    spec = butanol_spec()
    spec["conditions"]["nominal_x1"] = 1.0
    with pytest.raises(ValidationError):
        MaterialsJobSpec.model_validate(spec)


# -------------------------------------------------- AT-0702-1: parameters


def test_unknown_subgroup_id_is_unsupported() -> None:
    spec = MaterialsJobSpec.model_validate(_spec_dict(FIXTURE["unsupported_subgroups_example"]))
    with pytest.raises(EngineFailure) as exc:
        check_parameter_coverage(spec)
    assert exc.value.code == "ENGINE_UNSUPPORTED_INPUT"
    assert "99" in exc.value.message


def test_missing_interaction_pair_is_missing_parameters() -> None:
    """DMSO (main 32) vs water (main 8): the LLEUFIP table never
    regressed the pair — blocked, never zero-filled."""
    spec = MaterialsJobSpec.model_validate(_spec_dict(FIXTURE["missing_parameters_example"]))
    with pytest.raises(EngineFailure) as exc:
        check_parameter_coverage(spec)
    assert exc.value.code == "MISSING_PARAMETERS"
    assert "8->32" in exc.value.message or "32->8" in exc.value.message


def test_build_payload_runs_coverage_check() -> None:
    spec = MaterialsJobSpec.model_validate(_spec_dict(FIXTURE["missing_parameters_example"]))
    with pytest.raises(EngineFailure) as exc:
        build_job_payload(spec)
    assert exc.value.code == "MISSING_PARAMETERS"


# ------------------------------------------------- convex-hull criterion


def test_convex_surface_is_homogeneous() -> None:
    """Ideal mixing (x ln x + (1-x) ln(1-x)) is convex — the hull is the
    curve itself, no gap."""
    xs = [i / 100 for i in range(1, 100)]
    surface = [x * math.log(x) + (1 - x) * math.log(1 - x) for x in xs]
    hull = lower_convex_hull(xs, surface)
    assert miscibility_gaps(xs, surface) == []
    assert hull[0] == (xs[0], surface[0]) and hull[-1] == (xs[-1], surface[-1])


def test_unfavorable_surface_yields_one_gap() -> None:
    """g_mix = ideal + chi*x*(1-x) with chi=3: a documented model of
    liquid-liquid demixing — the hull cuts across between the two
    minima, producing one symmetric gap (~[0.071, 0.929])."""
    xs = [i / 200 for i in range(1, 200)]
    surface = [x * math.log(x) + (1 - x) * math.log(1 - x) + 3.0 * x * (1 - x) for x in xs]
    gaps = miscibility_gaps(xs, surface)
    assert len(gaps) == 1
    lo, hi = gaps[0]
    assert lo == pytest.approx(0.071, abs=0.02)
    assert hi == pytest.approx(0.929, abs=0.02)


def test_gibbs_surface_rejects_nonpositive_gamma() -> None:
    with pytest.raises(EngineFailure) as exc:
        gibbs_mixing_surface([0.5], [(-1.0, 1.0)])
    assert exc.value.code == "ENGINE_MALFORMED_OUTPUT"


# ------------------------------------------------- AT-0702-2: endpoints


def test_supported_endpoint_is_within_proxy_scope() -> None:
    v = evaluate_endpoint(SUPPORTS_ENDPOINTS, "equilibrium_miscibility")
    assert v["established"] is True
    assert v["verdict"] == "within_proxy_scope"
    assert "computed equilibrium proxy" in v["detail"]


def test_storage_stability_is_never_established() -> None:
    for endpoint in DOES_NOT_ESTABLISH:
        v = evaluate_endpoint(SUPPORTS_ENDPOINTS, endpoint)
        assert v["established"] is False
        assert v["verdict"] == "not_established"
        assert v["basis"] == "proxy_scope_gap"


def test_arbitrary_endpoint_is_never_established() -> None:
    v = evaluate_endpoint(SUPPORTS_ENDPOINTS, "adhesion_performance")
    assert v["established"] is False
    assert v["basis"] == "proxy_scope_gap"


def test_contract_declares_proxy_scope_structurally() -> None:
    assert SUPPORTS_ENDPOINTS == ("equilibrium_miscibility",)
    assert "storage_stability" in DOES_NOT_ESTABLISH
    assert "product_performance" in DOES_NOT_ESTABLISH
