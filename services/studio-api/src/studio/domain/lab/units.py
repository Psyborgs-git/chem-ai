"""Shared quantity parsing and whitelisted unit conversion (§6.1).

One conversion table for the whole lab surface — measurement
comparison (CS-0502) and the per-metric task evaluator (CS-0503) must
agree on what is convertible. Comparisons stay inside a dimensional
category; mass↔volume is absent by design (needs density +
conditions); absolute temperature conversions are deliberately
excluded (absolute vs difference ambiguity).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from studio.errors import DomainError, ErrorCode

# dimensional category per supported unit id
_UNIT_CATEGORY = {
    "mPa·s": "viscosity",
    "cP": "viscosity",
    "Pa·s": "viscosity",
    "mass_fraction": "fraction",
    "mass_percent": "fraction",
    "%": "fraction",
    "g": "mass",
    "kg": "mass",
    "mL": "volume",
    "L": "volume",
    "s": "time",
    "min": "time",
    "h": "time",
    "°C": "temperature_abs",
    "K": "temperature_abs",
    "°F": "temperature_abs",
    "dimensionless": "dimensionless",
    "1": "dimensionless",
}

# multiplier: value_in_from * factor = value_in_to. Only same-category,
# well-defined linear conversions.
_CONVERSIONS: dict[tuple[str, str], Decimal] = {
    ("mPa·s", "Pa·s"): Decimal("0.001"),
    ("Pa·s", "mPa·s"): Decimal("1000"),
    ("cP", "mPa·s"): Decimal("1"),
    ("cP", "Pa·s"): Decimal("0.001"),
    ("mass_percent", "mass_fraction"): Decimal("0.01"),
    ("%", "mass_fraction"): Decimal("0.01"),
    ("mass_fraction", "mass_percent"): Decimal("100"),
    ("mass_fraction", "%"): Decimal("100"),
    ("g", "kg"): Decimal("0.001"),
    ("kg", "g"): Decimal("1000"),
    ("mL", "L"): Decimal("0.001"),
    ("L", "mL"): Decimal("1000"),
    ("min", "s"): Decimal("60"),
    ("h", "min"): Decimal("60"),
    ("h", "s"): Decimal("3600"),
    ("s", "min"): Decimal(1) / Decimal(60),
    ("min", "h"): Decimal(1) / Decimal(60),
}

_TARGET_RE = re.compile(r"^\s*(>=|\x3c=|>|\x3c|=)\s*(\S+)(?:\s+(\S.*))?$")

_OPERATOR_NAMES = {
    "gte": ">=",
    "gt": ">",
    "lte": "<=",
    "lt": "<",
    "eq": "=",
}


def parse_target(target: str) -> tuple[str, Decimal, str | None]:
    """Contract metric target like ``">= 500 mPa·s"`` or ``"= pass"``."""
    m = _TARGET_RE.match(target or "")
    if not m:
        raise DomainError(
            ErrorCode.VALIDATION,
            f"unparseable contract target {target!r}",
            field_path="target",
        )
    op, raw, unit = m.group(1), m.group(2), (m.group(3) or "").strip() or None
    try:
        return op, Decimal(raw), unit
    except InvalidOperation:
        raise DomainError(
            ErrorCode.VALIDATION,
            f"non-numeric contract target {target!r}",
            field_path="target",
        ) from None


def metric_bound(metric: dict[str, Any]) -> tuple[str, Decimal, str | None] | None:
    """Normalise the two bound shapes to ``(op, value, unit)``:

    fixture schema — ``{"operator": "gte", "target_values": ["5"],
    "unit": "dimensionless"}``; loose app drafts —
    ``{"target": ">= 100 mPa·s"}``. ``None`` when no bound exists.
    """
    operator = str(metric.get("operator") or "").strip().lower()
    values = metric.get("target_values") or metric.get("targetValues") or []
    if operator and values:
        op = _OPERATOR_NAMES.get(operator, operator)
        if op not in (">=", "<=", ">", "<", "="):
            raise DomainError(
                ErrorCode.VALIDATION,
                f"unknown metric operator {operator!r}",
                field_path="operator",
            )
        unit = str(metric.get("unit") or "").strip() or None
        try:
            return op, Decimal(str(values[0])), unit
        except InvalidOperation:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"non-numeric metric target {values[0]!r}",
                field_path="targetValues",
            ) from None
    target = str(metric.get("target") or "").strip()
    if target:
        return parse_target(target)
    return None


def to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise DomainError(ErrorCode.VALIDATION, "value is not a decimal string") from None


def convert(value: Decimal, from_unit: str, to_unit: str) -> Decimal | None:
    """Same-category whitelisted conversion; ``None`` when impossible."""
    if from_unit == to_unit:
        return value
    factor = _CONVERSIONS.get((from_unit, to_unit))
    if factor is None:
        return None
    return value * factor


def compatible(from_unit: str, to_unit: str) -> bool:
    """Unit categories must match and both units must be whitelisted."""
    return from_unit in _UNIT_CATEGORY and _UNIT_CATEGORY.get(from_unit) == _UNIT_CATEGORY.get(
        to_unit
    )


def compare(value: Decimal, op: str, target: Decimal) -> bool:
    return {
        ">=": value >= target,
        "<=": value <= target,
        ">": value > target,
        "<": value < target,
        "=": value == target,
    }[op]
