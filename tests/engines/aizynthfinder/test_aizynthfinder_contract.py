"""CS-0903 contract/validation unit tests — no engine required.

Covers the strict spec shape, the small-molecule-only input contract
(AT-0903-2 at the validation boundary), the license/provenance gate
on every declared asset (U13), and the `proposed`/approval-gated
outcome semantics (AT-0903-1, AT-0903-3).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from engine_adapter_aizynthfinder.contracts import (
    DOES_NOT_ESTABLISH,
    METHOD_ID,
    SUPPORTED_INPUT_KINDS,
    EngineFailure,
    ProposedRoute,
    RouteJobSpec,
    RouteOutcome,
)
from engine_adapter_aizynthfinder.validation import (
    KNOWN_MODELS,
    KNOWN_STOCKS,
    build_job_payload,
    check_all_assets,
    check_input_kind,
    evaluate_execution,
)

FIXTURE = json.loads(Path("fixtures/synthetic/synthesis-aizynthfinder.json").read_text())

_SPEC_KEYS = {
    "schema_version",
    "method",
    "target",
    "policy_model",
    "templates",
    "stock",
    "filter_model",
    "search",
    "resources",
}


def _spec(**over: object) -> dict:
    spec = json.loads(json.dumps(FIXTURE["spec"]))
    for key, value in over.items():
        spec[key] = value
    return spec


# ---------------------------------------------------------------- structure


def test_valid_spec_builds_pinned_payload() -> None:
    spec = RouteJobSpec.model_validate(FIXTURE["spec"])
    payload = build_job_payload(spec)
    assert payload["schema_name"] == "aizynthfinder_route_job/v1"
    assert payload["method"] == METHOD_ID
    assert payload["method_version"] == "v1"
    assert payload["target"]["smiles"] == "Cn1c(=O)c2c(ncn2C)n(C)c1=O"
    assert payload["policy_model"]["name"] == "uspto_expansion"
    assert payload["stock"]["name"] == "zinc_stock"
    assert payload["search"]["max_routes"] == 5
    assert spec.digest() == spec.digest()  # deterministic


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        RouteJobSpec.model_validate(_spec(unknown_field=1))


def test_search_bounds_bounded() -> None:
    with pytest.raises(ValidationError):
        RouteJobSpec.model_validate(
            _spec(search={"time_limit_seconds": 1, "iteration_limit": 5000, "max_routes": 5})
        )
    with pytest.raises(ValidationError):
        RouteJobSpec.model_validate(
            _spec(
                search={
                    "time_limit_seconds": 120,
                    "iteration_limit": 999999,
                    "max_routes": 5,
                }
            )
        )


def test_target_smiles_syntax_gate() -> None:
    for bad in ("*CC*", "CC(C", "oil 80%"):
        with pytest.raises(ValidationError):
            RouteJobSpec.model_validate(
                _spec(target={"kind": "small_molecule_smiles", "smiles": bad})
            )


def test_mixture_smiles_rejected() -> None:
    raw = FIXTURE["unsupported_input_examples"]["mixture_smiles"]
    with pytest.raises(ValidationError, match=r"mixture|multi-component"):
        RouteJobSpec.model_validate(_spec(target=raw["target"]))


# -------------------------------------------------- AT-0903-2: input kinds


def test_supported_input_kinds_are_small_molecule_only() -> None:
    assert SUPPORTED_INPUT_KINDS == ("small_molecule_smiles",)


@pytest.mark.parametrize("key", ["formulation", "polymer_distribution", "unknown"])
def test_unsupported_input_kind_rejected(key: str) -> None:
    raw = FIXTURE["unsupported_input_examples"][key]
    with pytest.raises(EngineFailure) as exc:
        check_input_kind(raw["target"]["kind"])
    assert exc.value.code == "ENGINE_UNSUPPORTED_INPUT"
    with pytest.raises(ValidationError):
        RouteJobSpec.model_validate(_spec(target=raw["target"]))


# ------------------------------------------------- U13: license/provenance


def test_registry_assets_pass_gate() -> None:
    spec = RouteJobSpec.model_validate(FIXTURE["spec"])
    check_all_assets(spec)  # no raise
    assert KNOWN_MODELS["uspto_expansion"].license == "cc-by-4.0"
    assert KNOWN_STOCKS["zinc_stock"].license == "mit"


def test_unlicensed_stock_is_license_unavailable() -> None:
    spec = RouteJobSpec.model_validate(_spec(stock=FIXTURE["license_examples"]["unlicensed_stock"]))
    with pytest.raises(EngineFailure) as exc:
        check_all_assets(spec)
    assert exc.value.code == "LICENSE_UNAVAILABLE"
    assert "zinc_stock" in exc.value.message


def test_undeclared_policy_is_license_unavailable() -> None:
    spec = RouteJobSpec.model_validate(
        _spec(policy_model=FIXTURE["license_examples"]["undeclared_policy"])
    )
    with pytest.raises(EngineFailure) as exc:
        build_job_payload(spec)
    assert exc.value.code == "LICENSE_UNAVAILABLE"


def test_hash_mismatch_templates_is_license_unavailable() -> None:
    spec = RouteJobSpec.model_validate(
        _spec(templates=FIXTURE["license_examples"]["hash_mismatch_templates"])
    )
    with pytest.raises(EngineFailure) as exc:
        check_all_assets(spec)
    assert exc.value.code == "LICENSE_UNAVAILABLE"
    assert "provenance" in exc.value.message


def test_no_filter_model_is_fine() -> None:
    spec = RouteJobSpec.model_validate(_spec(filter_model=None))
    payload = build_job_payload(spec)
    assert payload["filter_model"] is None


# ------------------------------------------- AT-0903-1/3: outcome shape


def _usable(solved: bool) -> RouteOutcome:
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
                score=0.83,
            )
        ],
        num_solved=1 if solved else 0,
        provenance={"stock": {"name": "zinc_stock"}},
        engine_version="4.4.1",
    )


def test_outcome_labels_everything_proposed() -> None:
    outcome = _usable(solved=True)
    assert outcome.label == "proposed"
    assert outcome.routes[0].label == "proposed"
    assert outcome.execution_gate == "independent_plan_approval_required"
    assert outcome.scientific_status == "not_validated"
    assert outcome.evidence_class == "proposed_route_hypothesis"
    for claim in ("yield", "selectivity", "safety", "scale_up_feasibility"):
        assert claim in outcome.does_not_establish
    assert "cost" in DOES_NOT_ESTABLISH


def test_solved_route_still_requires_independent_approval() -> None:
    """AT-0903-3 core rule: all precursors in the purchasable stock
    list does NOT make a route executable."""
    verdict = evaluate_execution(_usable(solved=True))
    assert verdict["executable"] is False
    assert verdict["verdict"] == "independent_plan_approval_required"
    assert verdict["basis"] == "proposed_route_is_hypothesis"
    assert verdict["num_stock_resolved_routes"] == 1
    assert "never" in verdict["detail"] or "independent" in verdict["detail"]


def test_unsolved_outcome_same_gate() -> None:
    verdict = evaluate_execution(_usable(solved=False))
    assert verdict["executable"] is False
    assert verdict["verdict"] == "independent_plan_approval_required"


def test_failed_outcome_not_evaluated() -> None:
    bad = RouteOutcome(
        status="failed",
        usable=False,
        classification="unavailable",
        error={"code": "ENGINE_UNAVAILABLE", "message": "x"},
    )
    verdict = evaluate_execution(bad)
    assert verdict["executable"] is False
    assert verdict["verdict"] == "not_evaluated"
