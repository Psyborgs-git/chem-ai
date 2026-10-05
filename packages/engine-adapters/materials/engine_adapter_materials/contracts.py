"""Versioned, deliberately narrow materials/thermodynamics mapping (CS-0702).

Pinned runtime: thermo 0.6.1 inside `chem-studio-materials:0.6.1-v1`.
One method only (§16.3): the UNIFAC-LLE binary miscibility screen
`unifac-lle-miscibility-screen/v1` documented in
docs/science/methods/. Anything outside that method record fails closed —
no guessed force fields, no substituted binaries, no surrogate molecule
for a polymer distribution.

contracts.py carries no science-package import: the host process
validates structure and required-parameter coverage without thermo.
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

THERMO_VERSION: Literal["0.6.1"] = "0.6.1"
ADAPTER_VERSION: Literal["materials-adapter/v1"] = "materials-adapter/v1"
SCHEMA_VERSION: Literal["materials_lle_job/v1"] = "materials_lle_job/v1"
METHOD_ID: Literal["unifac-lle-miscibility-screen"] = "unifac-lle-miscibility-screen"
METHOD_VERSION: Literal["v1"] = "v1"

# Declared domain of the method record: binary condensed-liquid systems,
# ambient pressure, temperature in the band the LLE parameter table was
# regressed on (~5-60 °C). Outside this band the request is rejected —
# the method does not extrapolate (§16.3).
T_DOMAIN_MIN_K = 278.15
T_DOMAIN_MAX_K = 333.15

GRID_MIN_POINTS = 101
GRID_MAX_POINTS = 4001
GRID_DEFAULT_POINTS = 801

MAX_TOTAL_GROUPS = 64
MAX_WALL_SECONDS = 600
MAX_MEMORY_MEBIBYTES = 4096
MAX_CORES = 4

# Engine states per handoff §16.1 — the adapter reports the real state,
# never a simulated one.
ENGINE_STATES = (
    "available_tested",
    "installed_unverified",
    "not_installed",
    "unsupported_platform",
)  # `insufficient_inputs` and `disabled_by_policy` are request-level, not install-level

# The only endpoint this method answers. Everything else — storage or
# emulsion stability, adhesion, durability, any product-performance
# claim — is structurally out of scope (AT-0702-2): the distinction is
# encoded in the result manifest, not in a disclaimer string.
SUPPORTS_ENDPOINTS: tuple[str, ...] = ("equilibrium_miscibility",)
DOES_NOT_ESTABLISH: tuple[str, ...] = (
    "storage_stability",
    "emulsion_stability",
    "kinetic_stability",
    "product_performance",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EngineFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ------------------------------------------------------------------
# Request shape
# ------------------------------------------------------------------


class Component(StrictModel):
    """One explicit component as a UNIFAC-LLE subgroup decomposition.

    The subgroup decomposition IS the model's parameter set — a
    component that cannot be expressed in UNIFAC-LLE subgroups (a
    polymer distribution, a salt, an unknown purchased composition) is
    rejected, never approximated by a surrogate molecule (§16.3)."""

    name: str = Field(min_length=1, max_length=200)
    unifac_groups: dict[str, int] = Field(min_length=1, max_length=24)


class Conditions(StrictModel):
    temperature_k: float
    # Optional nominal composition of component 0 — where in the
    # composition range the caller's mixture sits. The screen always
    # covers the whole binary range; the nominal point only marks
    # which side a real recipe is on.
    nominal_x1: float | None = Field(default=None, gt=0.0, lt=1.0)


class ResourceEnvelope(StrictModel):
    wall_seconds: int = Field(default=60, ge=1, le=MAX_WALL_SECONDS, strict=True)
    memory_mebibytes: int = Field(default=512, ge=64, le=MAX_MEMORY_MEBIBYTES, strict=True)
    ncores: int = Field(default=1, ge=1, le=MAX_CORES, strict=True)


class MaterialsJobSpec(StrictModel):
    """The declared job. Structural validation lives here; the
    parameter/domain-level checks (known subgroup ids, interaction-
    parameter coverage) live in `validation.py`."""

    schema_version: Literal["1"] = "1"
    method: Literal["unifac_lle_screen"]
    components: tuple[Component, Component]
    conditions: Conditions
    grid_points: int = Field(default=GRID_DEFAULT_POINTS, ge=GRID_MIN_POINTS, le=GRID_MAX_POINTS)
    resources: ResourceEnvelope = Field(default_factory=ResourceEnvelope)

    @model_validator(mode="after")
    def check_components(self) -> MaterialsJobSpec:
        if len(self.components) != 2:
            raise ValueError("the method supports exactly two components")
        for comp in self.components:
            for key, count in comp.unifac_groups.items():
                if not key.isdigit() or int(key) <= 0:
                    raise ValueError(f"unifac_groups key '{key}' is not a UNIFAC-LLE subgroup id")
                if not isinstance(count, int) or count <= 0:
                    raise ValueError(f"unifac_groups[{key}] count must be a positive integer")
            if sum(comp.unifac_groups.values()) > MAX_TOTAL_GROUPS:
                raise ValueError(
                    f"component has >{MAX_TOTAL_GROUPS} total groups — not a "
                    "small-molecule decomposition"
                )
        t = self.conditions.temperature_k
        if not (T_DOMAIN_MIN_K <= t <= T_DOMAIN_MAX_K):
            raise ValueError(
                f"temperature {t} K outside the declared domain "
                f"[{T_DOMAIN_MIN_K}, {T_DOMAIN_MAX_K}] K — the method does not extrapolate"
            )
        return self

    def digest(self) -> str:
        import json

        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()


# ------------------------------------------------------------------
# Result shape
# ------------------------------------------------------------------


class MaterialsOutcome(StrictModel):
    """What a run produced — honest classification with the proxy
    structurally separated from product performance (§16.3, AT-0702-2).

    ``equilibrium_proxy`` is the only payload the method produces; it
    carries its own endpoint class so downstream consumers cannot read
    it as direct product-performance evidence."""

    status: Literal["succeeded", "failed"]
    usable: bool  # scientifically usable: success + parsed + finite
    classification: Literal[
        "reference_integration",
        "engine_failure",
        "malformed_result",
        "missing_parameters",
        "unsupported_input",
        "unavailable",
    ]
    method: str = METHOD_ID
    method_version: str = METHOD_VERSION
    phase_state: Literal["homogeneous", "phase_separated", "undetermined"] | None = None
    equilibrium_proxy: dict[str, Any] | None = None
    supports_endpoints: tuple[str, ...] = SUPPORTS_ENDPOINTS
    does_not_establish: tuple[str, ...] = DOES_NOT_ESTABLISH
    evidence_class: Literal["computed_equilibrium_proxy"] = "computed_equilibrium_proxy"
    model_context: dict[str, Any] = Field(default_factory=dict)
    engine: str = "thermo"
    engine_version: str | None = None
    adapter_version: str = ADAPTER_VERSION
    input_digest: str = ""
    scientific_status: Literal["not_validated"] = "not_validated"
    error: dict[str, str] | None = None
    isolation: dict[str, Any] = Field(default_factory=dict)
