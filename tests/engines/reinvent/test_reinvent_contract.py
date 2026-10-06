"""CS-0903 contract/validation unit tests — no engine required.

Covers the strict spec shape, the small-molecule-only input contract
(AT-0903-2 at the validation boundary), the license/provenance gate
(U13 — checked before any download or run attempt), and the
`proposed`-labeled outcome shape (AT-0903-1).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from engine_adapter_reinvent.contracts import (
    DOES_NOT_ESTABLISH,
    METHOD_ID,
    SUPPORTED_INPUT_KINDS,
    DesignCandidate,
    DesignJobSpec,
    DesignOutcome,
    EngineFailure,
)
from engine_adapter_reinvent.validation import (
    KNOWN_PRIORS,
    build_job_payload,
    check_input_kind,
    check_model_license,
)

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


def _spec_dict(raw: dict) -> dict:
    return {k: v for k, v in raw.items() if k in _SPEC_KEYS}


def _spec(**over: object) -> dict:
    spec = json.loads(json.dumps(FIXTURE["spec"]))
    for key, value in over.items():
        spec[key] = value
    return spec


# ---------------------------------------------------------------- structure


def test_valid_spec_builds_pinned_payload() -> None:
    spec = DesignJobSpec.model_validate(FIXTURE["spec"])
    payload = build_job_payload(spec)
    assert payload["schema_name"] == "reinvent_design_job/v1"
    assert payload["method"] == METHOD_ID
    assert payload["method_version"] == "v1"
    assert payload["anchor"]["smiles"] == "c1ccncc1"
    assert payload["model"]["name"] == "reinvent_pubchem"
    assert payload["model"]["sha256"] == KNOWN_PRIORS["reinvent_pubchem"].sha256
    assert payload["num_smiles"] == 32
    assert spec.digest() == spec.digest()  # deterministic


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        DesignJobSpec.model_validate(_spec(unknown_field=1))


def test_num_smiles_bounded() -> None:
    with pytest.raises(ValidationError):
        DesignJobSpec.model_validate(_spec(num_smiles=0))
    with pytest.raises(ValidationError):
        DesignJobSpec.model_validate(_spec(num_smiles=4096))


def test_anchor_smiles_syntax_gate() -> None:
    """Wildcard atoms, unbalanced branches, and non-SMILES characters
    are not explicit defined molecules — rejected structurally."""
    for bad in ("*CC*", "CC(C", "CC]O", "oil 80%", "mol\necule"):
        with pytest.raises(ValidationError):
            DesignJobSpec.model_validate(
                _spec(anchor={"kind": "small_molecule_smiles", "smiles": bad})
            )


# -------------------------------------------------- AT-0903-2: input kinds


def test_supported_input_kinds_are_small_molecule_only() -> None:
    assert SUPPORTED_INPUT_KINDS == ("small_molecule_smiles",)


@pytest.mark.parametrize("key", ["formulation", "polymer_distribution", "unknown"])
def test_unsupported_input_kind_rejected(key: str) -> None:
    raw = FIXTURE["unsupported_input_examples"][key]
    with pytest.raises(EngineFailure) as exc:
        check_input_kind(raw["anchor"]["kind"])
    assert exc.value.code == "ENGINE_UNSUPPORTED_INPUT"
    with pytest.raises(ValidationError):
        DesignJobSpec.model_validate(_spec(anchor=raw["anchor"]))


def test_polymer_smiles_rejected_even_at_right_kind() -> None:
    raw = FIXTURE["polymer_smiles_example"]
    with pytest.raises(ValidationError, match="wildcard"):
        DesignJobSpec.model_validate(_spec(anchor=raw["anchor"]))


# ------------------------------------------------- U13: license/provenance


def test_registry_model_passes_gate() -> None:
    spec = DesignJobSpec.model_validate(FIXTURE["spec"])
    known = check_model_license(spec.model)
    assert known is KNOWN_PRIORS["reinvent_pubchem"]


@pytest.mark.parametrize("key", ["unlicensed_license", "undeclared_model", "hash_mismatch"])
def test_unverifiable_model_is_license_unavailable(key: str) -> None:
    spec = DesignJobSpec.model_validate(_spec(model=FIXTURE["license_examples"][key]))
    with pytest.raises(EngineFailure) as exc:
        check_model_license(spec.model)
    assert exc.value.code == "LICENSE_UNAVAILABLE"
    with pytest.raises(EngineFailure) as exc2:
        build_job_payload(spec)
    assert exc2.value.code == "LICENSE_UNAVAILABLE"


# ------------------------------------------------- AT-0903-1: outcome shape


def test_outcome_labels_everything_proposed() -> None:
    outcome = DesignOutcome(
        status="succeeded",
        usable=True,
        classification="reference_integration",
        candidates=[DesignCandidate(rank=1, smiles="CCO", nll=1.5, similarity_to_anchor=0.1)],
        num_generated=1,
        engine_version="4.8",
    )
    assert outcome.label == "proposed"
    assert outcome.candidates[0].label == "proposed"
    assert outcome.execution_gate == "independent_plan_approval_required"
    assert outcome.scientific_status == "not_validated"
    assert outcome.evidence_class == "proposed_candidates"
    for claim in ("safety", "synthesizability", "pharmacological_activity"):
        assert claim in outcome.does_not_establish
    assert DOES_NOT_ESTABLISH


def test_failed_outcome_carries_error_code() -> None:
    outcome = DesignOutcome(
        status="failed",
        usable=False,
        classification="license_unavailable",
        error={"code": "LICENSE_UNAVAILABLE", "message": "unreviewed model"},
    )
    assert outcome.usable is False
    assert outcome.error["code"] == "LICENSE_UNAVAILABLE"
