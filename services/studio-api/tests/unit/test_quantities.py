"""CS-0202 tests — quantities, basis and missingness.

AT-0202-1  volume without applicable density -> mass conversion blocked
AT-0202-2  missing/below-detection -> never silently zero-filled
AT-0202-3  property: finite decimals roundtrip exactly; dimensional
           validation holds; NaN/float inputs rejected
"""

from __future__ import annotations

import itertools
import json
from decimal import Decimal
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from studio.domain.materials.quantities import (
    BASIS_REQUIRED_DIMENSIONS,
    UNIT_REGISTRY,
    Density,
    MeasurementValue,
    Quantity,
    check_declared_total,
    dimension_of,
)
from studio.errors import DomainError, ErrorCode


def _density() -> Density:
    return Density.create(
        "1.05",
        "g_per_mL",
        conditions="25 C, 1 atm",
        source="supplier COA lot 7",
        applicability="aqueous sugar syrup, lot-specific",
    )


class TestMissingDensityBlocks:
    """AT-0202-1: volume -> mass without applicable density is blocked."""

    def test_volume_to_mass_without_density_blocked(self) -> None:
        q = Quantity.create("250", "mL")
        with pytest.raises(DomainError) as exc:
            q.convert("g")
        assert exc.value.code == ErrorCode.VALIDATION
        assert "density" in exc.value.safe_details["missing"]

    def test_mass_to_volume_without_density_blocked(self) -> None:
        q = Quantity.create("1.5", "kg")
        with pytest.raises(DomainError) as exc:
            q.convert("L")
        assert exc.value.code == ErrorCode.VALIDATION

    def test_incomplete_density_rejected(self) -> None:
        for kwargs in (
            {"conditions": "", "source": "s", "applicability": "a"},
            {"conditions": "c", "source": "", "applicability": "a"},
            {"conditions": "c", "source": "s", "applicability": ""},
        ):
            with pytest.raises(DomainError) as exc:
                Density.create("1.0", "g_per_mL", **kwargs)
            assert exc.value.code == ErrorCode.VALIDATION
            assert exc.value.safe_details["missing"]

    def test_density_conversion_math(self) -> None:
        # 2.1 kg of 1.05 g/mL material -> exactly 2 L
        vol = Quantity.create("2.1", "kg").convert("L", density=_density())
        assert vol.unit == "L"
        assert abs(vol.value - Decimal("2")) < Decimal("1e-30")
        # provenance records the density used
        rec = vol.provenance[-1]
        assert rec["kind"] == "density"
        assert rec["density"]["source"] == "supplier COA lot 7"
        # and back: 2 L -> 2.1 kg
        mass = Quantity.create("2", "L").convert("kg", density=_density())
        assert abs(mass.value - Decimal("2.1")) < Decimal("1e-30")

    def test_molar_mass_bridge(self) -> None:
        mm = Quantity.create("58.44", "g_per_mol")
        grams = Quantity.create("2", "mol").convert("g", molar_mass=mm)
        assert abs(grams.value - Decimal("116.88")) < Decimal("1e-30")
        with pytest.raises(DomainError) as exc:
            Quantity.create("2", "mol").convert("g")
        assert exc.value.code == ErrorCode.VALIDATION

    def test_no_bridge_for_unknown_transforms(self) -> None:
        with pytest.raises(DomainError) as exc:
            Quantity.create("10", "g").convert("Pa")
        assert exc.value.code == ErrorCode.INVALID_UNIT
        # mole fraction -> mass fraction: never guessed for mixtures
        with pytest.raises(DomainError) as exc:
            Quantity.create("0.4", "mole_fraction", basis="as_supplied").convert("mass_fraction")
        assert exc.value.code == ErrorCode.INVALID_UNIT


class TestNoSilentZeroFill:
    """AT-0202-2: missing/censored never becomes 0."""

    def test_below_detection_is_not_zero(self) -> None:
        mv = MeasurementValue.below_detection(Quantity.create("0.02", "g"))
        assert mv.feature_scalar() is None

    def test_missing_is_not_zero(self) -> None:
        for reason in ("not_measured", "instrument_failure", "sample_lost", "unknown"):
            assert MeasurementValue.missing(reason).feature_scalar() is None

    def test_missing_requires_reason(self) -> None:
        with pytest.raises(DomainError):
            MeasurementValue.missing("because")

    def test_ordinal_and_categorical_excluded(self) -> None:
        assert MeasurementValue.ordinal("3").feature_scalar() is None
        assert MeasurementValue.categorical("pass").feature_scalar() is None

    def test_interval_midpoint_opt_in_only(self) -> None:
        mv = MeasurementValue.interval(Quantity.create("1", "g"), Quantity.create("3", "g"))
        assert mv.feature_scalar() is None
        assert mv.feature_scalar(allow_interval_midpoint=True) == 2.0

    def test_numeric_yields_float(self) -> None:
        mv = MeasurementValue.numeric(Quantity.create("0.001", "kg"))
        assert mv.feature_scalar() == 0.001


class TestPropertyRoundtrips:
    """AT-0202-3: exact storage + dimensional validation."""

    def test_decimal_storage_is_exact(self) -> None:
        q = Quantity.create("0.1", "g")
        assert q.value == Decimal("0.1")
        assert str(q.value) == "0.1"  # not 0.1000000000000000055511151231257827
        for s in ("0.100000000000000000001", "123456789.987654321", "1E-7"):
            q = Quantity.create(s, "mg")
            assert q.value == Decimal(s)

    def test_to_dict_from_dict_roundtrip(self) -> None:
        q = Quantity.create("0.1", "g").convert("kg").convert("mg")
        restored = Quantity.from_dict(q.to_dict())
        assert restored.value == q.value
        assert restored.unit == q.unit
        assert restored.provenance == q.provenance
        mv = MeasurementValue.below_detection(q, repeat_kind="same_sample_reading")
        mv2 = MeasurementValue.from_dict(mv.to_dict())
        assert mv2.kind == "below_detection"
        assert mv2.limit is not None and mv2.limit.value == q.value

    def test_same_dimension_roundtrip_grid(self) -> None:
        """Property: converting A -> B -> A returns the original value
        within conversion tolerance for every unit pair and a grid of
        finite decimals."""
        values = [Decimal(v) for v in ("0.001", "1", "3.14159", "999999.999")]
        for dim, units in UNIT_REGISTRY.items():
            basis = "as_supplied" if dim in BASIS_REQUIRED_DIMENSIONS else None
            for u_a, u_b in itertools.permutations(units, 2):
                for v in values:
                    q = Quantity.create(str(v), u_a, basis=basis)
                    back = q.convert(u_b).convert(u_a)
                    assert abs(back.value - q.value) < Decimal("1e-20"), (
                        f"{u_a}->{u_b}->{u_a} of {v} drifted: {back.value}"
                    )

    def test_reject_nan_infinity_and_float(self) -> None:
        for bad in ("NaN", "Infinity", "-Infinity", "abc"):
            with pytest.raises(DomainError) as exc:
                Quantity.create(bad, "g")
            assert exc.value.code == ErrorCode.INVALID_UNIT
        with pytest.raises(DomainError):
            Quantity.create(0.1, "g")  # binary float is not authoritative

    def test_dimensional_validation(self) -> None:
        with pytest.raises(DomainError) as exc:
            Quantity.create("1", "g").convert("K")
        assert exc.value.code == ErrorCode.INVALID_UNIT
        with pytest.raises(DomainError):
            Quantity.create("1", "furlong")
        # absolute temperature is not a temperature difference
        with pytest.raises(DomainError) as exc:
            Quantity.create("20", "degC").convert("d_degF")
        assert exc.value.code == ErrorCode.INVALID_UNIT
        # but degC -> degF absolute works
        f = Quantity.create("100", "degC").convert("degF")
        assert abs(f.value - Decimal("212")) < Decimal("1e-30")

    def test_unknown_unit_blocked(self) -> None:
        with pytest.raises(DomainError):
            Quantity.create("1", "smoot")
        assert dimension_of("smoot") is None


class TestBasisAndContext:
    def test_fraction_requires_basis(self) -> None:
        for dim in BASIS_REQUIRED_DIMENSIONS:
            unit = next(iter(UNIT_REGISTRY[dim]))
            with pytest.raises(DomainError) as exc:
                Quantity.create("0.5", unit)
            assert exc.value.code == ErrorCode.UNKNOWN_BASIS

    def test_basis_transform_never_guessed(self) -> None:
        q = Quantity.create("0.60", "mass_fraction", basis="as_supplied")
        with pytest.raises(DomainError) as exc:
            q.change_basis("active_solids")
        assert exc.value.code == ErrorCode.VALIDATION
        active = q.change_basis(
            "active_solids", transform=Quantity.create("0.80", "mass_fraction", basis="as_supplied")
        )
        assert active.basis == "active_solids"
        assert abs(active.value - Decimal("0.48")) < Decimal("1e-30")
        assert active.provenance[-1]["op"] == "basis_transform"

    def test_unknown_basis_rejected(self) -> None:
        with pytest.raises(DomainError) as exc:
            Quantity.create("0.5", "mass_fraction", basis="wet-ish")
        assert exc.value.code == ErrorCode.UNKNOWN_BASIS


class TestDeclaredTotals:
    def test_total_within_and_beyond_tolerance(self) -> None:
        amounts = [
            Quantity.create("0.4", "mass_fraction", basis="as_supplied"),
            Quantity.create("0.59", "mass_fraction", basis="as_supplied"),
        ]
        actual = check_declared_total(amounts, declared_total="1.0", tolerance="0.011")
        assert actual == Decimal("0.99")
        with pytest.raises(DomainError) as exc:
            check_declared_total(amounts, declared_total="1.0", tolerance="0.001")
        assert exc.value.code == ErrorCode.COMPOSITION_TOTAL_INVALID
        # mixed dimensions never silently sum
        with pytest.raises(DomainError):
            check_declared_total(
                [amounts[0], Quantity.create("5", "g")],
                declared_total="1",
                tolerance="0.1",
            )

    def test_mass_percent_sums_in_first_unit(self) -> None:
        amounts = [
            Quantity.create("40", "mass_percent", basis="as_supplied"),
            Quantity.create("0.6", "mass_fraction", basis="as_supplied"),
        ]
        # canonical sum = 0.4 + 0.6 = 1.0 fraction -> reported back in
        # the first amount's unit (mass_percent) as 100
        actual = check_declared_total(amounts, declared_total="100", tolerance="0.001")
        assert abs(actual - Decimal("100")) < Decimal("1e-30")


_SCHEMA = json.loads(
    (Path(__file__).parents[4] / "packages/contracts/domain.schema.json").read_text()
)


def _measured_value_validator() -> Draft202012Validator:
    """A validator rooted at #/$defs/MeasuredValue."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "#/$defs/MeasuredValue",
        "$defs": _SCHEMA["$defs"],
    }
    return Draft202012Validator(schema)


class TestContractConformance:
    """to_dto() must satisfy domain.schema.json exactly."""

    @pytest.mark.parametrize(
        "mv",
        [
            MeasurementValue.numeric(Quantity.create("0.001", "g", original_text="1 mg")),
            MeasurementValue.interval(
                Quantity.create("80", "degC"),
                Quantity.create("90", "degC"),
            ),
            MeasurementValue.below_detection(Quantity.create("0.02", "mg")),
            MeasurementValue.above_quantification(Quantity.create("1E-7", "mol")),
            MeasurementValue.ordinal("3", scale_revision_id="b3b3b3b3-b3b3-b3b3-b3b3-b3b3b3b3b3b3"),
            MeasurementValue.categorical(
                "pass", scale_revision_id="b3b3b3b3-b3b3-b3b3-b3b3-b3b3b3b3b3b3"
            ),
            MeasurementValue.missing("instrument_failure"),
            MeasurementValue.missing("cancelled"),
        ],
    )
    def test_dto_validates_against_domain_schema(self, mv: MeasurementValue) -> None:
        errors = list(_measured_value_validator().iter_errors(mv.to_dto()))
        assert errors == [], [e.message for e in errors]

    def test_dto_roundtrip(self) -> None:
        mv = MeasurementValue.interval(
            Quantity.create("1", "g", original_text="1 g"),
            Quantity.create("3", "g"),
        )
        back = MeasurementValue.from_dto(mv.to_dto())
        assert back.kind == "interval"
        assert back.low is not None and back.low.value == Decimal("1")
        # decimal strings in the DTO carry no exponent (pattern-bound)
        dto = MeasurementValue.numeric(Quantity.create("1E-7", "mol")).to_dto()
        assert dto["quantity"]["value"] == "0.0000001"
