"""Versioned, deliberately narrow campaign mapping (CS-0603)."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ENGINE_VERSION: Literal["0.15.0"] = "0.15.0"
ADAPTER_VERSION: Literal["baybe-adapter/v1"] = "baybe-adapter/v1"
IDENTITY_VERSION: Literal["parameter-context/decimal-distance-v1"] = (
    "parameter-context/decimal-distance-v1"
)
TOLERANCE = Decimal("0.000001")
Number = Annotated[Decimal, Field(allow_inf_nan=False)]
Name = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Parameter(StrictModel):
    name: Name
    kind: Literal["continuous", "discrete", "categorical"]
    unit: str = Field(min_length=1, max_length=64)
    bounds: tuple[Number, Number] | None = None
    values: tuple[Number, ...] | None = Field(default=None, max_length=100)
    categories: tuple[str, ...] | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def supported(self) -> Parameter:
        if self.kind == "continuous":
            if not self.bounds or self.bounds[0] >= self.bounds[1]:
                raise ValueError("continuous parameter requires increasing finite bounds")
            if self.values is not None or self.categories is not None:
                raise ValueError("continuous parameters cannot contain discrete values")
        elif self.kind == "discrete":
            if not self.values or len(self.values) < 2 or len(set(self.values)) != len(self.values):
                raise ValueError("discrete parameter requires distinct finite values")
            if self.bounds is not None or self.categories is not None:
                raise ValueError("discrete parameter accepts values only")
        else:
            if not self.categories or len(self.categories) < 2:
                raise ValueError("categorical parameter requires at least two categories")
            if len(set(self.categories)) != len(self.categories) or any(
                not c or len(c) > 100 for c in self.categories
            ):
                raise ValueError("categories must be distinct nonempty bounded labels")
            if self.bounds is not None or self.values is not None:
                raise ValueError("categorical parameter accepts categories only")
        return self


class LinearConstraint(StrictModel):
    kind: Literal["linear"] = "linear"
    scope: Literal["point"] = "point"
    parameters: tuple[Name, ...] = Field(min_length=1, max_length=12)
    coefficients: tuple[Number, ...] = Field(min_length=1, max_length=12)
    operator: Literal["=", ">=", "<="]
    rhs: Number


class Target(StrictModel):
    name: Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,95}$")]
    mode: Literal["maximize", "minimize", "match"]
    unit: str = Field(min_length=1, max_length=64)
    method: str = Field(min_length=1, max_length=300)
    match_bounds: tuple[Number, Number] | None = None

    @model_validator(mode="after")
    def transformation(self) -> Target:
        if self.mode == "match":
            if not self.match_bounds or self.match_bounds[0] >= self.match_bounds[1]:
                raise ValueError("match target requires reviewed triangular cutoffs")
        elif self.match_bounds is not None:
            raise ValueError("cutoffs are supported only for match targets")
        return self


class Mixture(StrictModel):
    parameters: tuple[Name, ...] = Field(min_length=2, max_length=12)
    basis: Literal["as_supplied_mass"]
    unit: Literal["percent_m/m", "mass_fraction"]
    total: Number


class CampaignSpec(StrictModel):
    schema_version: Literal["1"] = "1"
    parameters: tuple[Parameter, ...] = Field(min_length=1, max_length=12)
    target: Target
    constraints: tuple[LinearConstraint, ...] = Field(default=(), max_length=24)
    mixture: Mixture | None = None
    # Immutable representation/method context: grade, process, substrate, conditions, etc.
    context: dict[str, str] = Field(min_length=1, max_length=30)
    seed: int = Field(ge=0, lt=2**32, strict=True)
    recommender: Literal["random", "two_phase"] = "two_phase"
    switch_after: int = Field(default=3, ge=1, le=500, strict=True)

    @model_validator(mode="after")
    def support_matrix(self) -> CampaignSpec:
        by_name = {p.name: p for p in self.parameters}
        if len(by_name) != len(self.parameters) or self.target.name in by_name:
            raise ValueError("parameter/target names must be distinct")
        if any(p.name in {"BatchNr", "FitNr", "Num_Experiments"} for p in self.parameters):
            raise ValueError("reserved BayBE metadata name")
        continuous = [p for p in self.parameters if p.kind == "continuous"]
        if continuous and len(continuous) != len(self.parameters):
            raise ValueError("hybrid spaces/constraints are unsupported; no constraints dropped")
        size = 1
        for p in self.parameters:
            size *= len(p.values or p.categories or ()) or 1
        if size > 10000:
            raise ValueError("finite enumeration exceeds 10000-point resource envelope")
        for c in self.constraints:
            if len(c.parameters) != len(c.coefficients) or len(set(c.parameters)) != len(
                c.parameters
            ):
                raise ValueError("linear constraint coefficients must match unique parameters")
            if not any(c.coefficients):
                raise ValueError("linear constraint requires a nonzero coefficient")
            if any(n not in by_name or by_name[n].kind == "categorical" for n in c.parameters):
                raise ValueError("linear constraints require defined numerical parameters")
        if self.mixture:
            m = self.mixture
            expected = Decimal(100) if m.unit == "percent_m/m" else Decimal(1)
            if m.total != expected or len(set(m.parameters)) != len(m.parameters):
                raise ValueError("mixture requires explicit unnormalized 100% or fraction total")
            for n in m.parameters:
                component = by_name.get(n)
                if not component or component.kind == "categorical" or component.unit != m.unit:
                    raise ValueError("mixture parameters must use the declared mass unit")
                vals = component.bounds or component.values or ()
                if min(vals) < 0 or max(vals) > m.total:
                    raise ValueError("mixture amounts must be nonnegative and within total")
        if any(len(k) > 100 or len(v) > 300 for k, v in self.context.items()):
            raise ValueError("context is bounded metadata, not free-text documents")
        return self

    def digest(self) -> str:
        import json

        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()


class EngineFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Recommendation(StrictModel):
    status: Literal["suggested", "partial", "exhausted", "no_feasible_suggestions"]
    suggestions: list[dict[str, str]] = Field(max_length=16)
    rejected: dict[str, int]
    engine_state: str | None = None
    engine_version: Literal["0.15.0"] = ENGINE_VERSION
    adapter_version: Literal["baybe-adapter/v1"] = ADAPTER_VERSION
    seed: int
    recommender: str
    acquisition: str | None = None
    scientific_status: Literal["fixture_only", "not_validated"] = "not_validated"
    isolation: dict[str, Any] = Field(default_factory=dict)
