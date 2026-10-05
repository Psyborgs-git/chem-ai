"""Versioned, deliberately narrow quantum-chemistry mapping (CS-0701).

Pinned runtime: QCEngine 0.51.0 + QCElemental 0.51.2 + xtb-python 22.1
(xtb 6.7.1) inside `chem-studio-qcengine:0.51.0-v1`. Psi4 1.10.2 is the
declared second engine — adapter-side support ships, the image does not,
so its capability state reports `not_installed` until it is added and
tested. Anything outside the support matrix below fails closed.
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

QCENGINE_VERSION: Literal["0.51.0"] = "0.51.0"
QCELEMENTAL_VERSION: Literal["0.51.2"] = "0.51.2"
ADAPTER_VERSION: Literal["qcengine-adapter/v1"] = "qcengine-adapter/v1"
SCHEMA_VERSION: Literal["qcschema_atomic_input/v1"] = "qcschema_atomic_input/v1"

# CODATA conversion used by QCElemental itself.
ANGSTROM_TO_BOHR = 1.8897261254578281

MAX_ATOMS = 200
MAX_WALL_SECONDS = 3600
MAX_MEMORY_MEBIBYTES = 65536
MAX_CORES = 32

# Engine states per handoff §16.1 — the adapter reports the real state,
# never a simulated one.
ENGINE_STATES = (
    "available_tested",
    "installed_unverified",
    "not_installed",
    "unsupported_platform",
)  # `insufficient_inputs` and `disabled_by_policy` are request-level, not install-level

# ------------------------------------------------------------------
# Support matrix — explicit method/driver/basis allowlists per program.
# A pair not listed here does not exist for this adapter.
# ------------------------------------------------------------------

XTB_SOLVENTS = (
    "acetone",
    "acetonitrile",
    "benzene",
    "ch2cl2",
    "chloroform",
    "dmf",
    "dmso",
    "ether",
    "methanol",
    "n-hexane",
    "thf",
    "toluene",
    "water",
)

# method name as written into QCSchema `model.method` -> supported drivers
XTB_METHODS: dict[str, frozenset[str]] = {
    "GFN2-xTB": frozenset({"energy", "gradient"}),
    "GFN1-xTB": frozenset({"energy", "gradient"}),
    "GFN0-xTB": frozenset({"energy", "gradient"}),
    "GFN-FF": frozenset({"energy", "gradient"}),
    "IPEA-xTB": frozenset({"energy"}),
}
XTB_KEYWORDS = frozenset({"solvent", "accuracy", "max_iterations"})

PSI4_BASES = ("sto-3g", "def2-svp", "cc-pvdz")
PSI4_METHODS: dict[str, frozenset[str]] = {
    "hf": frozenset({"energy", "gradient"}),
    "b3lyp": frozenset({"energy"}),
}
PSI4_KEYWORDS = frozenset(
    {"scf_type", "reference", "e_convergence", "d_convergence", "maxiter", "guess"}
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


class GeometryProvenance(StrictModel):
    """Where the coordinates came from — required, never defaulted."""

    kind: Literal["reference", "experimental", "optimized", "imported"]
    source: str = Field(min_length=1, max_length=200)


class Molecule(StrictModel):
    """One explicit molecular representation. Polymers, compositions,
    and mixtures cannot express one — they fail validation rather than
    being approximated by a surrogate (AT-0701-3)."""

    symbols: tuple[str, ...] = Field(min_length=1, max_length=MAX_ATOMS)
    geometry: tuple[float, ...] = Field(min_length=3)
    units: Literal["angstrom", "bohr"]
    charge: int = Field(strict=True)  # required — never inferred
    multiplicity: int = Field(ge=1, strict=True)  # required — never inferred
    name: str | None = Field(default=None, max_length=200)
    provenance: GeometryProvenance


class ResourceEnvelope(StrictModel):
    wall_seconds: int = Field(default=300, ge=1, le=MAX_WALL_SECONDS, strict=True)
    memory_mebibytes: int = Field(default=4096, ge=32, le=MAX_MEMORY_MEBIBYTES, strict=True)
    ncores: int = Field(default=1, ge=1, le=MAX_CORES, strict=True)


def program_support(program: str) -> dict[str, Any] | None:
    if program == "xtb":
        return {"methods": XTB_METHODS, "keywords": XTB_KEYWORDS, "needs_basis": False}
    if program == "psi4":
        return {
            "methods": PSI4_METHODS,
            "keywords": PSI4_KEYWORDS,
            "needs_basis": True,
            "bases": PSI4_BASES,
        }
    return None


class QuantumJobSpec(StrictModel):
    """The declared job. Validation lives here (structure-level) and in
    `validation.py` (physics-level: element symbols, charge/spin parity,
    geometry length/coincidence)."""

    schema_version: Literal["1"] = "1"
    program: Literal["xtb", "psi4"]
    method: str = Field(min_length=1, max_length=64)
    driver: Literal["energy", "gradient"]
    basis: str | None = Field(default=None, max_length=64)
    molecule: Molecule
    keywords: dict[str, str | int | float | bool] = Field(default_factory=dict, max_length=8)
    resources: ResourceEnvelope = Field(default_factory=ResourceEnvelope)

    @model_validator(mode="after")
    def support_matrix(self) -> QuantumJobSpec:
        support = program_support(self.program)
        if support is None:  # the Literal type guarantees this never fires
            raise ValueError(f"unknown program '{self.program}'")
        methods: dict[str, frozenset[str]] = support["methods"]
        canonical = next((m for m in methods if m.lower() == self.method.lower()), None)
        if canonical is None:
            raise ValueError(
                f"method '{self.method}' is not supported for {self.program}; "
                "no method is substituted"
            )
        if self.driver not in methods[canonical]:
            raise ValueError(f"driver '{self.driver}' is not supported for {canonical}")
        if support["needs_basis"]:
            if not self.basis:
                raise ValueError(f"{self.program} requires an explicit basis")
            if self.basis not in support["bases"]:
                raise ValueError(f"basis '{self.basis}' is not in the tested allowlist")
        elif self.basis is not None:
            raise ValueError(f"{self.program} does not take a basis; the request is rejected")
        allowed: frozenset[str] = support["keywords"]
        extra = [k for k in self.keywords if k not in allowed]
        if extra:
            raise ValueError(f"unsupported keywords for {self.program}: {sorted(extra)}")
        if "solvent" in self.keywords:
            solvent = self.keywords["solvent"]
            if self.program != "xtb" or not isinstance(solvent, str) or solvent not in XTB_SOLVENTS:
                raise ValueError(f"solvent '{solvent}' is not in the tested allowlist")
        if "max_iterations" in self.keywords:
            it = self.keywords["max_iterations"]
            if not isinstance(it, int) or isinstance(it, bool) or not 1 <= it <= 1000:
                raise ValueError("max_iterations must be an integer 1..1000")
        if "accuracy" in self.keywords:
            acc = self.keywords["accuracy"]
            if not isinstance(acc, (int, float)) or isinstance(acc, bool) or not 0 < acc <= 10:
                raise ValueError("accuracy must be a number in (0, 10]")
        return self

    def digest(self) -> str:
        import json

        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()


# ------------------------------------------------------------------
# Result shape
# ------------------------------------------------------------------


class QuantumOutcome(StrictModel):
    """What a run produced — honest classification, never 'exit 0 =
    success' (AT-0701-2)."""

    status: Literal["succeeded", "failed"]
    usable: bool  # scientifically usable: success + parsed + complete
    converged: bool | None = None  # only set where the engine reports it
    classification: Literal[
        "reference_integration",
        "engine_failure",
        "malformed_result",
        "not_converged",
        "unsupported_input",
        "unavailable",
    ]
    energy_hartree: float | None = None
    return_result: float | list[float] | list[list[float]] | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    engine: str
    engine_version: str | None = None
    qcengine_version: str | None = None
    qcelemental_version: str | None = None
    adapter_version: str = ADAPTER_VERSION
    input_digest: str = ""
    scientific_status: Literal["not_validated"] = "not_validated"
    error: dict[str, str] | None = None
    raw_stdout: str | None = None
    raw_stderr: str | None = None
    stdout_truncated: bool = False
    isolation: dict[str, Any] = Field(default_factory=dict)
