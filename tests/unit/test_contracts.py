"""Fixture/schema conformance tests (AT-0003-3, contracts-check target).

Validates every synthetic fixture against the canonical domain schema
and its declared expectation in ``fixtures/index.json``, plus selected
semantic invariants the schema cannot express. These prove contract
conformance only — they are not scientific validation.
"""

from __future__ import annotations

import decimal
import json
from pathlib import Path

import jsonschema
import pytest

PACK = Path(__file__).resolve().parents[2] / "docs" / "chemistry-studio"
SCHEMA = json.loads((PACK / "contracts" / "domain.schema.json").read_text())
INDEX = json.loads((PACK / "fixtures" / "index.json").read_text())

# Software-fixture tolerance only (contracts/README.md) — not a product
# standard and not permission to normalize real formulations.
FIXTURE_TOLERANCE = decimal.Decimal("0.000001")


def _schema_for(definition: str) -> dict:
    return {"$ref": f"#/$defs/{definition}", "$defs": SCHEMA["$defs"]}


@pytest.mark.parametrize("case", INDEX["fixtures"], ids=lambda c: c["path"])
def test_fixture_matches_expectation(case: dict) -> None:
    payload = json.loads((PACK / case["path"]).read_text())
    validator = jsonschema.Draft202012Validator(_schema_for(case["definition"]))
    errors = list(validator.iter_errors(payload))
    if case["expected_valid"]:
        assert not errors, f"{case['path']} should validate: {errors[:3]}"


def test_all_valid_fixtures_are_marked_fixture_only() -> None:
    """AT-0003-3: no real-recipe/lab claim — fixture_only must be true."""
    for case in INDEX["fixtures"]:
        if not case["expected_valid"]:
            continue
        payload = json.loads((PACK / case["path"]).read_text())
        if "fixture_only" in payload:
            assert payload["fixture_only"] is True, case["path"]


def test_accepted_formulation_total_within_fixture_tolerance() -> None:
    """invalid-formula-total must fail the composition invariant."""
    results = {}
    for name in ("formulation-synthetic", "invalid-formula-total"):
        payload = json.loads((PACK / "fixtures" / f"{name}.json").read_text())
        if payload["status"] != "accepted":
            results[name] = None
            continue
        total = sum(decimal.Decimal(i["fraction"]) for i in payload["ingredients"])
        declared = decimal.Decimal(payload["declared_total"])
        results[name] = abs(total - declared) <= FIXTURE_TOLERANCE
    assert results["formulation-synthetic"] is True
    assert results["invalid-formula-total"] is False


def test_frozen_improve_contract_requires_baseline() -> None:
    payload = json.loads((PACK / "fixtures" / "invalid-improve-without-baseline.json").read_text())
    assert payload["status"] == "frozen" and payload["mode"] == "improve"
    assert payload["baseline_revision_id"] is None  # the semantic defect


def test_failed_run_cannot_meet_target() -> None:
    payload = json.loads((PACK / "fixtures" / "invalid-failed-run-meets.json").read_text())
    assert payload["execution_status"] == "failed"
    assert payload["acceptance"] == "meets"  # invalid combination by rule
