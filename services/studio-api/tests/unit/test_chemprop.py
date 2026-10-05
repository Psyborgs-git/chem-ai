"""CS-0604 chemprop contract/validation tests — no engine required.

Fixture-only software tests; the real engine runs only in the pinned
container (engines/test_chemprop.py, honest skip when absent)."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from engine_adapter_chemprop import PredictSpec, TrainSpec
from engine_adapter_chemprop.contracts import PredictRow, TrainRow
from engine_adapter_chemprop.validation import (
    check_smiles,
    model_file_digest,
    validate_predictions,
)


def _rows(n: int = 4) -> list[TrainRow]:
    return [TrainRow(row_id=f"r{i}", smiles="CCO", label=Decimal(f"{i}.5")) for i in range(n)]


def _spec(**kw: object) -> dict:
    base = {
        "schema_version": "1",
        "scope": {"name": "metric.x", "unit": "MPa", "method": "m1"},
        "representation": "mpnn-dmpnn",
        "context": {"grade": "fixture"},
        "rows": [r.model_dump(mode="json") for r in _rows()],
        "seed": 11,
    }
    base.update(kw)
    return base


def _predict_spec(**kw: object) -> dict:
    spec = _spec()
    # PredictSpec has no context/seed/hyperparameters and never sees labels.
    for key in (
        "context",
        "seed",
        "max_epochs",
        "ensemble_size",
        "hidden_dim",
        "depth",
        "batch_size",
    ):
        spec.pop(key, None)
    spec["rows"] = [{"row_id": f"r{i}", "smiles": "CCO"} for i in range(2)]
    spec["model_digest"] = "a" * 64
    spec.update(kw)
    return spec


class TestContracts:
    def test_train_spec_accepts_and_digest_stable(self) -> None:
        spec = TrainSpec.model_validate(_spec())
        assert spec.digest() == TrainSpec.model_validate(_spec()).digest()
        changed = _spec(seed=12)
        assert spec.digest() != TrainSpec.model_validate(changed).digest()

    def test_predict_row_has_no_label_field(self) -> None:
        with pytest.raises(ValidationError):
            PredictRow.model_validate({"row_id": "x", "smiles": "CCO", "label": "1.0"})

    def test_duplicate_row_ids_rejected(self) -> None:
        rows = _spec()["rows"]
        rows[1] = rows[0]
        with pytest.raises(ValidationError):
            TrainSpec.model_validate(_spec(rows=rows))

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TrainSpec.model_validate(_spec(pretrained=True, hyperopt=True))
        with pytest.raises(ValidationError):
            TrainSpec.model_validate(_spec(representation="gcn-other"))

    def test_bounds(self) -> None:
        with pytest.raises(ValidationError):
            TrainSpec.model_validate(_spec(max_epochs=0))
        with pytest.raises(ValidationError):
            TrainSpec.model_validate(_spec(ensemble_size=9))
        with pytest.raises(ValidationError):
            PredictSpec.model_validate(_predict_spec(rows=[]))
        with pytest.raises(ValidationError):
            PredictSpec.model_validate(_predict_spec(model_digest="not-hex"))
        with pytest.raises(ValidationError):
            PredictSpec.model_validate(_predict_spec(label="1.0"))


class TestValidation:
    def test_smiles_rejects_whitespace_and_controls(self) -> None:
        check_smiles("CCO")
        for bad in (" CCO", "CCO ", "CC\nO", "C\x00CO"):  # empty caught by contract min_length
            with pytest.raises(ValueError):
                check_smiles(bad)

    def test_model_file_digest_covers_every_file(self) -> None:
        files = {"model_0.pt": b"aaa", "model_1.pt": b"bbb"}
        d1 = model_file_digest("spec-x", files)
        assert d1 != model_file_digest("spec-y", files)
        assert d1 != model_file_digest("spec-x", {"model_0.pt": b"aaa"})
        assert d1 != model_file_digest("spec-x", {**files, "extra": b"z"})

    def test_validate_predictions_independent_checks(self) -> None:
        ok, rej = validate_predictions(
            ["a", "b"],
            [
                {"row_id": "a", "value": 1.0, "members": [1.0, 1.1]},
                {"row_id": "b", "value": 2.0, "members": [2.0, 2.1]},
            ],
            2,
        )
        assert len(ok) == 2 and rej == {"invalid": 0, "duplicate": 0}
        # Non-finite, bool, wrong member count, unknown id, dup id.
        bad, rej = validate_predictions(
            ["a", "b"],
            [
                {"row_id": "a", "value": float("nan"), "members": [1.0, 1.0]},
                {"row_id": "b", "value": True, "members": [1.0, 1.0]},
                {"row_id": "c", "value": 1.0, "members": [1.0, 1.0]},
                {"row_id": "a", "value": 1.0, "members": [1.0, 1.0]},
            ],
            2,
        )
        assert bad == [] and rej["invalid"] == 3 and rej["duplicate"] == 1
        bad, rej = validate_predictions(["a"], [{"row_id": "a", "value": 1.0, "members": [1.0]}], 2)
        assert rej["invalid"] == 1


class TestDigestLineage:
    def test_json_shape(self) -> None:
        # The digest a runtime recomputes must be a plain sha256 hex
        # over canonical JSON — no pickle, no engine internals.
        files = {"model_0.pt": b"x"}
        d = model_file_digest("s", files)
        parts = [f"model_0.pt:{hashlib.sha256(b'x').hexdigest()}"]
        expected = hashlib.sha256(
            json.dumps(["s", *parts], separators=(",", ":")).encode()
        ).hexdigest()
        assert d == expected
