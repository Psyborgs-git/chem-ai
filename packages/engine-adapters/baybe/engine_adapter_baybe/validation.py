"""Independent decimal checks. No BayBE feasibility or normalization is trusted."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .contracts import TOLERANCE, CampaignSpec


def point(spec: CampaignSpec, raw: dict[str, Any]) -> dict[str, str]:
    if set(raw) != {p.name for p in spec.parameters}:
        raise ValueError("unexpected or missing parameter columns")
    out: dict[str, str] = {}
    for p in spec.parameters:
        value = raw[p.name]
        if p.kind == "categorical":
            if value not in (p.categories or ()):
                raise ValueError("unknown category")
            out[p.name] = str(value)
            continue
        try:
            if isinstance(value, bool):
                raise ValueError("boolean is not a scientific number")
            number = Decimal(str(value))
        except (InvalidOperation, TypeError) as e:
            raise ValueError("invalid scientific number") from e
        if not number.is_finite():
            raise ValueError("nonfinite suggestion")
        if p.bounds and not p.bounds[0] <= number <= p.bounds[1]:
            raise ValueError("parameter outside declared bounds")
        if p.values and number not in p.values:
            raise ValueError("parameter outside declared discrete values")
        out[p.name] = str(number)
    for c in spec.constraints:
        lhs = sum(
            (Decimal(out[n]) * coef for n, coef in zip(c.parameters, c.coefficients, strict=True)),
            Decimal(0),
        )
        if (
            (c.operator == "=" and abs(lhs - c.rhs) > TOLERANCE)
            or (c.operator == "<=" and lhs > c.rhs + TOLERANCE)
            or (c.operator == ">=" and lhs < c.rhs - TOLERANCE)
        ):
            raise ValueError("independent linear constraint violation")
    if spec.mixture:
        total = sum((Decimal(out[n]) for n in spec.mixture.parameters), Decimal(0))
        if abs(total - spec.mixture.total) > TOLERANCE:
            raise ValueError("independent composition total violation; never normalize")
    return out


def same_point(spec: CampaignSpec, a: dict[str, str], b: dict[str, str]) -> bool:
    return all(
        a[p.name] == b[p.name]
        if p.kind == "categorical"
        else abs(Decimal(a[p.name]) - Decimal(b[p.name]))
        <= (TOLERANCE if p.kind == "continuous" else 0)
        for p in spec.parameters
    )


def validate_batch(
    spec: CampaignSpec, raw: list[dict[str, Any]], existing: list[dict[str, str]]
) -> tuple[list[dict[str, str]], dict[str, int]]:
    accepted: list[dict[str, str]] = []
    rejected = {"invalid": 0, "duplicate": 0}
    for r in raw:
        try:
            p = point(spec, r)
        except ValueError:
            rejected["invalid"] += 1
            continue
        if any(same_point(spec, p, q) for q in [*existing, *accepted]):
            rejected["duplicate"] += 1
            continue
        accepted.append(p)
    return accepted, rejected
