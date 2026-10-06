"""Versioned, deliberately narrow molecular-design contract (CS-0903).

Pinned runtime: REINVENT 4.8 inside `chem-studio-reinvent:4.8-v1`.
One method only (§16.4): the de novo sampling campaign
`reinvent-de-novo-sampling/v1` — a generative prior proposes candidate
small molecules around an anchor context. Anything outside that method
record fails closed: no unlicensed prior, no polymer/formulation input
coerced to a generic molecule, no optimization or RL stage.

contracts.py carries no science-package import: the host process
validates structure, input kind, and declared license/provenance
without torch/rdkit (E05).
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

REINVENT_VERSION: Literal["4.8"] = "4.8"
ADAPTER_VERSION: Literal["reinvent-adapter/v1"] = "reinvent-adapter/v1"
SCHEMA_VERSION: Literal["reinvent_design_job/v1"] = "reinvent_design_job/v1"
METHOD_ID: Literal["reinvent-de-novo-sampling"] = "reinvent-de-novo-sampling"
METHOD_VERSION: Literal["v1"] = "v1"

# The only small-molecule representation this method accepts. A polymer
# distribution, a formulation, or an unknown input kind is rejected at
# the kind field itself — never mapped onto a generic molecule
# (AT-0903-2, §16.4).
SUPPORTED_INPUT_KINDS: tuple[str, ...] = ("small_molecule_smiles",)

# Licenses the project has reviewed for model assets (U13). Anything
# undeclared or outside this set is `license_unavailable` — checked
# before any download or run attempt.
ALLOWED_MODEL_LICENSES: frozenset[str] = frozenset(
    {"apache-2.0", "mit", "cc-by-4.0", "bsd-3-clause"}
)

SMILES_MAX_LEN = 400
NUM_SMILES_MIN = 1
NUM_SMILES_MAX = 2048

MAX_WALL_SECONDS = 1800
MAX_MEMORY_MEBIBYTES = 8192
MAX_CORES = 8

# Engine states per handoff §16.1 — the adapter reports the real state,
# never a simulated one.
ENGINE_STATES = (
    "available_tested",
    "installed_unverified",
    "not_installed",
    "license_unavailable",
    "unsupported_platform",
)  # `insufficient_inputs`, `unsupported` and `disabled_by_policy` are request-level

# What a candidate manifest is allowed to claim. Sampling output is a
# list of *proposed* structures — it establishes nothing about activity,
# synthesizability, safety, novelty, or any experimental property
# (§16.4). Encoded structurally, not as a disclaimer string.
DOES_NOT_ESTABLISH: tuple[str, ...] = (
    "pharmacological_activity",
    "synthesizability",
    "safety",
    "novelty_vs_prior_art",
    "any_experimental_property",
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


class ModelAsset(StrictModel):
    """Declared provenance of one model/stock asset.

    The caller must declare name + version + license + source + sha256;
    `validation.check_model_license` compares the declaration against
    the licensed-asset registry before anything runs — an undeclared or
    differently-licensed asset is `license_unavailable`, never fetched."""

    name: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=120)
    license: str = Field(min_length=1, max_length=60)
    source: str = Field(min_length=1, max_length=500)
    sha256: str = Field(min_length=64, max_length=64)


class SmallMoleculeInput(StrictModel):
    """An explicit small-molecule representation — the only supported
    input kind (AT-0903-2). ``kind`` is a Literal: a formulation,
    polymer distribution, or unknown kind fails validation rather than
    being coerced."""

    kind: Literal["small_molecule_smiles"]
    smiles: str = Field(min_length=1, max_length=SMILES_MAX_LEN)


class ResourceEnvelope(StrictModel):
    wall_seconds: int = Field(default=600, ge=1, le=MAX_WALL_SECONDS, strict=True)
    memory_mebibytes: int = Field(default=4096, ge=256, le=MAX_MEMORY_MEBIBYTES, strict=True)
    ncores: int = Field(default=2, ge=1, le=MAX_CORES, strict=True)


class DesignJobSpec(StrictModel):
    """The declared design job. Structural validation lives here; the
    license/input-kind/payload-level checks live in `validation.py`."""

    schema_version: Literal["1"] = "1"
    method: Literal["reinvent_de_novo_sampling"]
    # The benign target: an explicit small molecule that anchors the
    # campaign context. De novo sampling generates around this anchor's
    # chemical space; the adapter reports each candidate's similarity
    # to it — the anchor is real input, never decoration.
    anchor: SmallMoleculeInput
    # The generative prior, declared with full provenance. Only entries
    # in the licensed-asset registry (validation.KNOWN_PRIORS) pass the
    # license gate.
    model: ModelAsset
    num_smiles: int = Field(default=64, ge=NUM_SMILES_MIN, le=NUM_SMILES_MAX)
    unique_molecules: bool = True
    randomize_smiles: bool = True
    resources: ResourceEnvelope = Field(default_factory=ResourceEnvelope)

    @model_validator(mode="after")
    def check_anchor(self) -> DesignJobSpec:
        smiles = self.anchor.smiles
        if "*" in smiles:
            raise ValueError(
                "wildcard/dummy atoms (*) denote a polymer repeat unit or an "
                "undefined attachment — not an explicit defined molecule"
            )
        for ch in smiles:
            if ch not in _SMILES_CHARSET:
                raise ValueError(
                    f"character {ch!r} is not SMILES syntax — the anchor must be "
                    "an explicit small-molecule representation"
                )
        if smiles.count("(") != smiles.count(")"):
            raise ValueError("unbalanced parentheses — not parseable SMILES")
        if smiles.count("[") != smiles.count("]"):
            raise ValueError("unbalanced brackets — not parseable SMILES")
        return self

    def digest(self) -> str:
        import json

        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()


# ASCII SMILES character set (OpenSMILES grammar symbols incl. ring
# closures, branches, charges, isotopes, aromatic atoms). Anything
# outside it — whitespace, units, punctuation from recipe/formulation
# notation — is not an explicit small-molecule representation.
_SMILES_CHARSET = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789@+-()[]=#%.\\/:$,~?&|!{}<>"
)


# ------------------------------------------------------------------
# Result shape
# ------------------------------------------------------------------


class DesignCandidate(StrictModel):
    """One proposed structure — always `proposed`, never a lead, hit,
    or validated compound (§16.4)."""

    rank: int = Field(ge=1)
    smiles: str
    nll: float | None = None
    similarity_to_anchor: float | None = None
    label: Literal["proposed"] = "proposed"


class DesignOutcome(StrictModel):
    """What a design run produced — an honest manifest of proposed
    candidates with full model/license/anchor provenance. `usable`
    means the run completed and the output parsed; it is not a claim
    about any molecular property."""

    status: Literal["succeeded", "failed"]
    usable: bool
    classification: Literal[
        "reference_integration",
        "engine_failure",
        "malformed_result",
        "unsupported_input",
        "license_unavailable",
        "unavailable",
    ]
    method: str = METHOD_ID
    method_version: str = METHOD_VERSION
    label: Literal["proposed"] = "proposed"
    candidates: list[DesignCandidate] = Field(default_factory=list)
    num_generated: int = 0  # actual emitted count — never the requested count
    provenance: dict[str, Any] = Field(default_factory=dict)
    does_not_establish: tuple[str, ...] = DOES_NOT_ESTABLISH
    execution_gate: Literal["independent_plan_approval_required"] = (
        "independent_plan_approval_required"
    )
    evidence_class: Literal["proposed_candidates"] = "proposed_candidates"
    model_context: dict[str, Any] = Field(default_factory=dict)
    engine: str = "reinvent"
    engine_version: str | None = None
    adapter_version: str = ADAPTER_VERSION
    input_digest: str = ""
    scientific_status: Literal["not_validated"] = "not_validated"
    error: dict[str, str] | None = None
    isolation: dict[str, Any] = Field(default_factory=dict)
