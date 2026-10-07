"""Quantities, basis and missingness (§6.1, §6.3).

The authoritative stored value is a decimal string plus a whitelisted
unit id, a dimensional category, basis/context, and the original
input — never the browser's float. Conversions are recorded in the
quantity's provenance log. Nothing is guessed: mass↔volume requires
an applicable density with units/conditions/source/applicability,
mole↔mass requires an explicit molar mass, fraction bases never
transform without an explicit reviewed transform, and missing or
censored measurements are never silently zero-filled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any, Literal, Self

from studio.errors import DomainError, ErrorCode

# Conversions are computed at 50 significant digits; the recorded
# tolerance documents that anything below it is conversion noise, not
# signal. Decimal storage itself is exact — this only bounds
# factor/affine arithmetic that cannot terminate (e.g. °F scale).
CONVERSION_PRECISION = 50
CONVERSION_TOLERANCE = Decimal("1e-40")


class _Unset:
    """Sentinel: 'argument not provided' distinct from explicit None."""


_UNSET = _Unset()

# ------------------------------------------------------------------
# unit registry (§6.1: vetted whitelist, dimensional categories)
#
# Each entry: dimension -> unit id -> (scale, offset) such that
# canonical = raw * scale + offset. Offsets exist only for absolute
# temperatures; the affine path keeps °F's 5/9 exact by carrying a
# (num, den) rational pair instead of a rounded decimal.
# ------------------------------------------------------------------

# (pre_offset, scale_num, scale_den, post_offset) — rational scale
# keeps °F's 5/9 exact instead of a rounded decimal factor.
_Affine = tuple[Decimal, Decimal, Decimal, Decimal]
_LINEAR = Decimal(0)
_ONE = Decimal(1)


def _lin(scale: str) -> _Affine:
    return (_LINEAR, Decimal(scale), _ONE, _LINEAR)


def _affine(pre_offset: str, num: int, den: int, post_offset: str = "0") -> _Affine:
    return (Decimal(pre_offset), Decimal(num), Decimal(den), Decimal(post_offset))


UNIT_REGISTRY: dict[str, dict[str, _Affine]] = {
    "mass": {
        "kg": _lin("1"),
        "g": _lin("0.001"),
        "mg": _lin("0.000001"),
        "ug": _lin("0.000000001"),
        "lb": _lin("0.45359237"),  # exact international definition
    },
    "volume": {
        "m3": _lin("1"),
        "L": _lin("0.001"),
        "mL": _lin("0.000001"),
        "uL": _lin("0.000000001"),
        "gal_us": _lin("0.003785411784"),  # exact
    },
    "amount": {
        "mol": _lin("1"),
        "mmol": _lin("0.001"),
        "umol": _lin("0.000001"),
    },
    "molar_mass": {
        "g_per_mol": _lin("1"),
        "kg_per_mol": _lin("1000"),
    },
    "density": {
        "g_per_mL": _lin("1"),
        "kg_per_L": _lin("1"),
        "g_per_L": _lin("0.001"),
        "kg_per_m3": _lin("0.001"),
    },
    # Absolute vs difference temperatures are distinct dimensions —
    # 10 °C above ambient is not 283.15 K of anything.
    "temperature_absolute": {
        "K": _lin("1"),
        "degC": _affine("273.15", 1, 1),
        "degF": _affine("459.67", 5, 9),
    },
    "temperature_delta": {
        "dK": _lin("1"),
        "d_degC": _lin("1"),
        "d_degF": _affine("0", 5, 9),
    },
    "pressure": {
        "Pa": _lin("1"),
        "kPa": _lin("1000"),
        "MPa": _lin("1000000"),
        "bar": _lin("100000"),
        "psi": _lin("6894.757293168361"),
    },
    "viscosity": {
        "Pa_s": _lin("1"),
        "mPa_s": _lin("0.001"),
    },
    # Fractions are dimensionless numbers with *different* meaning —
    # they are separate dimensions so nothing converts between them
    # implicitly (§6.1: no mole↔mass fraction transforms by default).
    "mass_fraction": {
        "mass_fraction": _lin("1"),
        "mass_percent": _lin("0.01"),
    },
    "volume_fraction": {
        "volume_fraction": _lin("1"),
        "volume_percent": _lin("0.01"),
    },
    "mole_fraction": {
        "mole_fraction": _lin("1"),
        "mole_percent": _lin("0.01"),
    },
}

_DIMENSIONS = frozenset(UNIT_REGISTRY)

# Concentration-style dimensions carry a basis (§6.1): a fraction
# without basis is incomplete.
BASIS_REQUIRED_DIMENSIONS = frozenset({"mass_fraction", "volume_fraction", "mole_fraction"})

BASES = ("as_supplied", "active_solids")

# quantity context (§6.1): formulation amount ≠ application dosage
CONTEXTS = ("formulation_amount", "application_dosage")

# Bridges that are legal *only* with the named extra information.
# Everything else — mole↔mass-fraction of a mixture, percent↔ppm of
# an unknown matrix — has no bridge at all (§6.1).
_BRIDGE_NEEDS = {
    frozenset({"mass", "volume"}): "density",
    frozenset({"amount", "mass"}): "molar_mass",
}


def dimension_of(unit: str) -> str | None:
    for dim, units in UNIT_REGISTRY.items():
        if unit in units:
            return dim
    return None


def _invalid_unit(msg: str, **details: Any) -> DomainError:
    return DomainError(ErrorCode.INVALID_UNIT, msg, safe_details=details or {})


def _to_decimal(value: str | int | Decimal, *, field_path: str = "value") -> Decimal:
    """Authoritative parse: decimal strings/ints only.

    Floats are rejected at the boundary — a binary float can never be
    an authoritative stored value (§6.1). Non-finite values are
    rejected outright.
    """
    if isinstance(value, float):
        raise _invalid_unit(
            "float input is not an authoritative value; pass a decimal string",
            fieldPath=field_path,
        )
    try:
        d = Decimal(value)
    except InvalidOperation as exc:
        raise _invalid_unit(f"'{value}' is not a decimal", fieldPath=field_path) from exc
    if not d.is_finite():
        raise _invalid_unit("value must be finite (no NaN/Infinity)", fieldPath=field_path)
    return d


def _canonical(value: Decimal, affine: _Affine) -> Decimal:
    pre, num, den, post = affine
    with localcontext() as ctx:
        ctx.prec = CONVERSION_PRECISION
        return (value + pre) * num / den + post


def _from_canonical(canonical: Decimal, affine: _Affine) -> Decimal:
    pre, num, den, post = affine
    with localcontext() as ctx:
        ctx.prec = CONVERSION_PRECISION
        return (canonical - post) * den / num - pre


@dataclass(frozen=True)
class Density:
    """An applicable density (§6.1) — all metadata is mandatory; an
    unsourced number cannot move mass into volume."""

    value: Decimal
    unit: str
    conditions: str
    source: str
    applicability: str

    @classmethod
    def create(
        cls,
        value: str | int | Decimal,
        unit: str,
        conditions: str,
        source: str,
        applicability: str,
    ) -> Self:
        missing = [
            name
            for name, v in (
                ("conditions", conditions),
                ("source", source),
                ("applicability", applicability),
            )
            if not v
        ]
        if missing:
            raise DomainError(
                ErrorCode.VALIDATION,
                "density is incomplete — mass/volume conversion is blocked",
                safe_details={"missing": missing},
            )
        if dimension_of(unit) != "density":
            raise _invalid_unit(f"'{unit}' is not a density unit", unit=unit)
        return cls(
            value=_to_decimal(value),
            unit=unit,
            conditions=conditions,
            source=source,
            applicability=applicability,
        )


@dataclass(frozen=True)
class Quantity:
    """A finite decimal value + whitelisted unit + basis/context +
    provenance. Immutable; ``convert`` returns a new quantity with an
    appended provenance entry."""

    value: Decimal
    unit: str
    basis: str | None = None
    context: str | None = None
    original_text: str | None = None
    provenance: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @classmethod
    def create(
        cls,
        value: str | int | Decimal,
        unit: str,
        *,
        basis: str | None = None,
        context: str | None = None,
        original_text: str | None = None,
    ) -> Self:
        dim = dimension_of(unit)
        if dim is None:
            raise _invalid_unit(f"unsupported unit '{unit}'", unit=unit)
        if basis is not None and basis not in BASES:
            raise DomainError(
                ErrorCode.UNKNOWN_BASIS,
                f"unknown basis '{basis}'",
                safe_details={"basis": basis, "allowed": list(BASES)},
            )
        if dim in BASIS_REQUIRED_DIMENSIONS and basis is None:
            raise DomainError(
                ErrorCode.UNKNOWN_BASIS,
                "a concentration without basis is incomplete",
                safe_details={"missing": ["basis"]},
            )
        if context is not None and context not in CONTEXTS:
            raise _invalid_unit(
                f"unknown context '{context}'", context=context, allowed=list(CONTEXTS)
            )
        return cls(
            value=_to_decimal(value),
            unit=unit,
            basis=basis,
            context=context,
            original_text=original_text,
        )

    @property
    def dimension(self) -> str:
        dim = dimension_of(self.unit)
        if dim is None:  # pragma: no cover - create() guards this
            raise _invalid_unit(f"unsupported unit '{self.unit}'")
        return dim

    # --------------------------------------------------------------

    def convert(
        self,
        to_unit: str,
        *,
        density: Density | None = None,
        molar_mass: Quantity | None = None,
    ) -> Quantity:
        """Convert to another unit. Same-dimension factor/affine
        conversions are unconditional; mass↔volume needs a Density;
        mole↔mass needs a molar-mass Quantity. Every conversion
        appends a provenance record."""
        to_dim = dimension_of(to_unit)
        if to_dim is None:
            raise _invalid_unit(f"unsupported unit '{to_unit}'", unit=to_unit)
        from_dim = self.dimension
        if to_dim == from_dim:
            out = _from_canonical(
                _canonical(self.value, UNIT_REGISTRY[from_dim][self.unit]),
                UNIT_REGISTRY[to_dim][to_unit],
            )
            record = {
                "op": "convert",
                "from": self.unit,
                "to": to_unit,
                "kind": "factor" if from_dim != "temperature_absolute" else "affine",
                "tolerance": str(CONVERSION_TOLERANCE),
            }
            return self._derived(out, to_unit, record)
        need = _BRIDGE_NEEDS.get(frozenset({from_dim, to_dim}))
        if need == "density":
            return self._via_density(to_unit, to_dim, density)
        if need == "molar_mass":
            return self._via_molar_mass(to_unit, to_dim, molar_mass)
        raise _invalid_unit(
            f"no conversion between '{from_dim}' and '{to_dim}' — this transform is never guessed",
            fromDimension=from_dim,
            toDimension=to_dim,
        )

    def change_basis(self, to_basis: str, *, transform: Quantity | None = None) -> Quantity:
        """Move between as_supplied and active_solids. Never guessed:
        the caller supplies the reviewed multiplier (e.g. active
        fraction) or the conversion is blocked."""
        if to_basis not in BASES:
            raise DomainError(
                ErrorCode.UNKNOWN_BASIS,
                f"unknown basis '{to_basis}'",
                safe_details={"basis": to_basis, "allowed": list(BASES)},
            )
        if self.dimension not in BASIS_REQUIRED_DIMENSIONS:
            raise _invalid_unit("only concentration quantities carry a basis")
        if to_basis == self.basis:
            return self
        if transform is None:
            raise DomainError(
                ErrorCode.VALIDATION,
                "basis transform requires an explicit reviewed fraction "
                f"({self.basis} -> {to_basis} is never guessed)",
                safe_details={"missing": ["transform"]},
            )
        if transform.dimension != "mass_fraction":
            raise _invalid_unit("basis transform must be a mass_fraction quantity")
        record = {
            "op": "basis_transform",
            "fromBasis": self.basis,
            "toBasis": to_basis,
            "transform": str(transform.value),
            "tolerance": str(CONVERSION_TOLERANCE),
        }
        return self._derived(self.value * transform.value, self.unit, record, basis=to_basis)

    # -------------------------------------------------- serializing

    def to_dict(self) -> dict[str, Any]:
        """Full internal serialization (storage payloads carry context
        and the conversion provenance)."""
        return {
            "value": str(self.value),
            "unit": self.unit,
            "basis": self.basis,
            "context": self.context,
            "original_text": self.original_text,
            "provenance": list(self.provenance),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        q = cls.create(
            data["value"],
            data["unit"],
            basis=data.get("basis"),
            context=data.get("context"),
            original_text=data.get("original_text"),
        )
        return cls(
            value=q.value,
            unit=q.unit,
            basis=q.basis,
            context=q.context,
            original_text=q.original_text,
            provenance=tuple(dict(p) for p in data.get("provenance", [])),
        )

    def to_dto(self) -> dict[str, Any]:
        """The strict interchange DTO (domain.schema.json ``Quantity``):
        exactly {value, unit, basis, original_text} — provenance and
        context are internal detail, not interchange fields. ``value``
        is emitted as a plain decimal (the pattern forbids exponent
        notation)."""
        return {
            "value": format(self.value, "f"),
            "unit": self.unit,
            "basis": self.basis,
            "original_text": self.original_text,
        }

    @classmethod
    def from_dto(cls, data: dict[str, Any]) -> Self:
        if not isinstance(data, dict):
            raise DomainError(
                ErrorCode.VALIDATION, "quantity must be an object", field_path="amount"
            )
        if "value" not in data or "unit" not in data:
            raise DomainError(
                ErrorCode.VALIDATION,
                "quantity requires 'value' and 'unit'",
                field_path="amount",
                safe_details={"missing": [k for k in ("value", "unit") if k not in data]},
            )
        return cls.create(
            data["value"],
            data["unit"],
            basis=data.get("basis"),
            original_text=data.get("original_text"),
        )

    # ----------------------------------------------------- internals

    def _derived(
        self,
        value: Decimal,
        unit: str,
        record: dict[str, Any],
        *,
        basis: str | _Unset | None = _UNSET,
    ) -> Quantity:
        return Quantity(
            value=value,
            unit=unit,
            basis=self.basis if isinstance(basis, _Unset) else basis,
            context=self.context,
            original_text=self.original_text,
            provenance=(*self.provenance, record),
        )

    def _via_density(self, to_unit: str, to_dim: str, density: Density | None) -> Quantity:
        if density is None:
            raise DomainError(
                ErrorCode.VALIDATION,
                "mass/volume conversion requires an applicable density "
                "with units, conditions, source and applicability",
                safe_details={"missing": ["density"]},
            )
        d_canonical = _canonical(density.value, UNIT_REGISTRY["density"][density.unit])
        with localcontext() as ctx:
            ctx.prec = CONVERSION_PRECISION
            own = _canonical(self.value, UNIT_REGISTRY[self.dimension][self.unit])
            # density canonical: g/mL; mass canonical: kg; volume: m3
            # kg -> m3 : v = m / (d * 1000)   (g/mL == 1000 kg/m3)
            # m3 -> kg : m = v * d * 1000
            if self.dimension == "mass":
                out_canonical = own / (d_canonical * Decimal(1000))
            else:
                out_canonical = own * d_canonical * Decimal(1000)
            out = _from_canonical(out_canonical, UNIT_REGISTRY[to_dim][to_unit])
        record = {
            "op": "convert",
            "from": self.unit,
            "to": to_unit,
            "kind": "density",
            "density": {
                "value": str(density.value),
                "unit": density.unit,
                "conditions": density.conditions,
                "source": density.source,
                "applicability": density.applicability,
            },
            "tolerance": str(CONVERSION_TOLERANCE),
        }
        return self._derived(out, to_unit, record)

    def _via_molar_mass(self, to_unit: str, to_dim: str, molar_mass: Quantity | None) -> Quantity:
        if molar_mass is None:
            raise DomainError(
                ErrorCode.VALIDATION,
                "mole/mass conversion requires an explicit molar mass — "
                "it is never inferred for unknown-composition mixtures",
                safe_details={"missing": ["molar_mass"]},
            )
        if molar_mass.dimension != "molar_mass":
            raise _invalid_unit("molar_mass must be a molar_mass quantity")
        mm_canonical = _canonical(
            molar_mass.value, UNIT_REGISTRY["molar_mass"][molar_mass.unit]
        )  # g/mol
        with localcontext() as ctx:
            ctx.prec = CONVERSION_PRECISION
            own = _canonical(self.value, UNIT_REGISTRY[self.dimension][self.unit])
            if self.dimension == "amount":
                # mol -> kg : m = n * M / 1000
                out_canonical = own * mm_canonical / Decimal(1000)
            else:
                # kg -> mol : n = m * 1000 / M
                out_canonical = own * Decimal(1000) / mm_canonical
            out = _from_canonical(out_canonical, UNIT_REGISTRY[to_dim][to_unit])
        record = {
            "op": "convert",
            "from": self.unit,
            "to": to_unit,
            "kind": "molar_mass",
            "molarMass": {"value": str(molar_mass.value), "unit": molar_mass.unit},
            "tolerance": str(CONVERSION_TOLERANCE),
        }
        return self._derived(out, to_unit, record)


# ------------------------------------------------------------------
# measurement value types (§6.3)
# ------------------------------------------------------------------

VALUE_KINDS = (
    "numeric",
    "interval",
    "below_detection",
    "above_quantification",
    "ordinal",
    "categorical",
    "missing",
)

MISSING_REASONS = ("not_measured", "instrument_failure", "sample_lost", "unknown", "cancelled")

# Repeat types are preserved (§6.3): three readings of one aliquot are
# not three independent formulation successes.
REPEAT_TYPES = (
    "same_sample_reading",
    "independent_batch",
    "independent_lab",
    "timepoint",
)

# §6.4 historical failure taxonomy — instrument failures can train
# operational reliability, never negative chemistry labels.
FAILURE_REASONS = (
    "performance_miss",
    "instability_observed",
    "process_failure",
    "safety_stop",
    "instrument_failure",
    "cancelled",
    "sample_lost",
    "incomplete",
    "unknown",
)

ValueKind = Literal[
    "numeric",
    "interval",
    "below_detection",
    "above_quantification",
    "ordinal",
    "categorical",
    "missing",
]


@dataclass(frozen=True)
class MeasurementValue:
    """One typed measurement result. A censored value is not zero; an
    ordinal label that looks like a digit is not interval-scale; a
    missing value must say why."""

    kind: ValueKind
    value: Quantity | None = None
    low: Quantity | None = None
    high: Quantity | None = None
    limit: Quantity | None = None
    label: str | None = None
    scale_revision_id: str | None = None
    missing_reason: str | None = None
    repeat_kind: str | None = None

    @classmethod
    def numeric(cls, q: Quantity, *, repeat_kind: str | None = None) -> Self:
        return cls(kind="numeric", value=q, repeat_kind=cls._check_repeat(repeat_kind))

    @classmethod
    def interval(cls, low: Quantity, high: Quantity, *, repeat_kind: str | None = None) -> Self:
        if low.dimension != high.dimension:
            raise _invalid_unit(
                "interval bounds must share a dimension",
                low=low.dimension,
                high=high.dimension,
            )
        lo = low.convert(high.unit)
        lo_c = _canonical(lo.value, UNIT_REGISTRY[lo.dimension][lo.unit])
        hi_c = _canonical(high.value, UNIT_REGISTRY[high.dimension][high.unit])
        if lo_c > hi_c:
            raise DomainError(ErrorCode.VALIDATION, "interval low bound exceeds high bound")
        return cls(kind="interval", low=low, high=high, repeat_kind=cls._check_repeat(repeat_kind))

    @classmethod
    def below_detection(cls, limit: Quantity, *, repeat_kind: str | None = None) -> Self:
        return cls(kind="below_detection", limit=limit, repeat_kind=cls._check_repeat(repeat_kind))

    @classmethod
    def above_quantification(cls, limit: Quantity, *, repeat_kind: str | None = None) -> Self:
        return cls(
            kind="above_quantification", limit=limit, repeat_kind=cls._check_repeat(repeat_kind)
        )

    @classmethod
    def ordinal(
        cls,
        label: str,
        *,
        scale_revision_id: str | None = None,
        repeat_kind: str | None = None,
    ) -> Self:
        if not label:
            raise DomainError(ErrorCode.VALIDATION, "ordinal label is required")
        return cls(
            kind="ordinal",
            label=label,
            scale_revision_id=scale_revision_id,
            repeat_kind=cls._check_repeat(repeat_kind),
        )

    @classmethod
    def categorical(
        cls,
        label: str,
        *,
        scale_revision_id: str | None = None,
        repeat_kind: str | None = None,
    ) -> Self:
        if not label:
            raise DomainError(ErrorCode.VALIDATION, "categorical label is required")
        return cls(
            kind="categorical",
            label=label,
            scale_revision_id=scale_revision_id,
            repeat_kind=cls._check_repeat(repeat_kind),
        )

    @classmethod
    def missing(cls, reason: str) -> Self:
        if reason not in MISSING_REASONS:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"missing reason must be one of {', '.join(MISSING_REASONS)}",
                field_path="missingReason",
            )
        return cls(kind="missing", missing_reason=reason)

    @staticmethod
    def _check_repeat(repeat_kind: str | None) -> str | None:
        if repeat_kind is not None and repeat_kind not in REPEAT_TYPES:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"repeat_kind must be one of {', '.join(REPEAT_TYPES)}",
                field_path="repeatType",
            )
        return repeat_kind

    # --------------------------------------------------------------
    # feature/score conversion (§6.3): unsupported value types are
    # excluded — never silently zero-filled.

    def feature_scalar(self, *, allow_interval_midpoint: bool = False) -> float | None:
        """A scalar for a model adapter, or ``None`` meaning *exclude
        this observation* (with a report upstream).

        - numeric  -> float (adapter boundary; stored value stays decimal)
        - interval -> midpoint only when the caller explicitly opts in
        - censored / missing / ordinal / categorical -> None, always
        """
        if self.kind == "numeric" and self.value is not None:
            return float(self.value.value)
        if self.kind == "interval" and allow_interval_midpoint:
            if self.low is None or self.high is None:  # pragma: no cover
                return None
            lo = self.low.convert(self.high.unit)
            return float((lo.value + self.high.value) / 2)
        return None

    # --------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value.to_dict() if self.value else None,
            "low": self.low.to_dict() if self.low else None,
            "high": self.high.to_dict() if self.high else None,
            "limit": self.limit.to_dict() if self.limit else None,
            "label": self.label,
            "scale_revision_id": self.scale_revision_id,
            "missing_reason": self.missing_reason,
            "repeat_kind": self.repeat_kind,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            kind=data["kind"],
            value=Quantity.from_dict(data["value"]) if data.get("value") else None,
            low=Quantity.from_dict(data["low"]) if data.get("low") else None,
            high=Quantity.from_dict(data["high"]) if data.get("high") else None,
            limit=Quantity.from_dict(data["limit"]) if data.get("limit") else None,
            label=data.get("label"),
            scale_revision_id=data.get("scale_revision_id"),
            missing_reason=data.get("missing_reason"),
            repeat_kind=data.get("repeat_kind"),
        )

    def to_dto(self) -> dict[str, Any]:
        """The strict interchange DTO (domain.schema.json
        ``MeasuredValue``): exactly the fields each kind defines."""
        kind = self.kind
        if kind == "numeric":
            return {
                "kind": "numeric",
                "quantity": self.value.to_dto() if self.value else None,
            }
        if kind == "interval":
            return {
                "kind": "interval",
                "lower": self.low.to_dto() if self.low else None,
                "upper": self.high.to_dto() if self.high else None,
            }
        if kind in ("below_detection", "above_quantification"):
            return {
                "kind": kind,
                "limit": self.limit.to_dto() if self.limit else None,
            }
        if kind in ("ordinal", "categorical"):
            return {
                "kind": kind,
                "label": self.label,
                "scale_revision_id": self.scale_revision_id,
            }
        return {"kind": "missing", "reason": self.missing_reason}

    @classmethod
    def from_dto(cls, data: dict[str, Any]) -> Self:
        kind = data["kind"]
        if kind == "numeric":
            return cls(
                kind=kind,
                value=Quantity.from_dto(data["quantity"]),
            )
        if kind == "interval":
            return cls(
                kind=kind,
                low=Quantity.from_dto(data["lower"]),
                high=Quantity.from_dto(data["upper"]),
            )
        if kind in ("below_detection", "above_quantification"):
            return cls(kind=kind, limit=Quantity.from_dto(data["limit"]))
        if kind in ("ordinal", "categorical"):
            return cls(
                kind=kind,
                label=data["label"],
                scale_revision_id=data.get("scale_revision_id"),
            )
        if kind == "missing":
            return cls.missing(data["reason"])
        raise DomainError(ErrorCode.VALIDATION, f"unknown MeasuredValue kind '{kind}'")


# ------------------------------------------------------------------
# composition totals (§6.2): never silently normalized
# ------------------------------------------------------------------


def check_declared_total(
    amounts: list[Quantity],
    *,
    declared_total: Decimal | str | int,
    tolerance: Decimal | str | int,
) -> Decimal:
    """Compare the sum of same-dimension amounts against the declared
    total within an explicitly versioned tolerance. Returns the actual
    sum; raises COMPOSITION_TOTAL_INVALID when outside tolerance. The
    caller decides what to do — the sum is never rewritten."""
    if not amounts:
        return Decimal(0)
    dim = amounts[0].dimension
    canonical_sum = Decimal(0)
    with localcontext() as ctx:
        ctx.prec = CONVERSION_PRECISION
        for a in amounts:
            if a.dimension != dim:
                raise _invalid_unit(
                    "composition amounts must share a dimension",
                    expected=dim,
                    got=a.dimension,
                )
            canonical_sum += _canonical(a.value, UNIT_REGISTRY[dim][a.unit])
        actual = _from_canonical(canonical_sum, UNIT_REGISTRY[dim][amounts[0].unit])
    declared = _to_decimal(declared_total, field_path="declaredTotal")
    tol = _to_decimal(tolerance, field_path="tolerance")
    if abs(actual - declared) > tol:
        raise DomainError(
            ErrorCode.COMPOSITION_TOTAL_INVALID,
            f"declared total {declared} differs from actual {actual} (beyond tolerance {tol})",
            safe_details={
                "declared": str(declared),
                "actual": str(actual),
                "tolerance": str(tol),
            },
        )
    return actual
