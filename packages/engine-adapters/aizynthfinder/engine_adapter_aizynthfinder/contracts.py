"""Versioned, deliberately narrow retrosynthesis contract (CS-0903).

Pinned runtime: AiZynthFinder 4.4.1 inside
`chem-studio-aizynthfinder:4.4.1-v1`. One method only (§16.4): the
MCTS retrosynthesis search `aizynthfinder-mcts-route/v1` — a search
over the licensed USPTO expansion policy against a licensed stock
list, producing *proposed* routes. Anything outside that method record
fails closed: no unlicensed model/stock, no polymer/formulation input
coerced to a generic molecule, no automatic execution of any route.

A route whose leaves land in the purchasable stock list is still a
hypothesis: it is NOT evidence of yield, selectivity, safety, or
scale-up feasibility, and it never releases a lab protocol — execution
requires independent plan approval (AT-0903-3).

contracts.py carries no science-package import: the host process
validates structure, input kind, and declared license/provenance
without aizynthfinder/rdkit (E05).
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AIZYNTHFINDER_VERSION: Literal["4.4.1"] = "4.4.1"
ADAPTER_VERSION: Literal["aizynthfinder-adapter/v1"] = "aizynthfinder-adapter/v1"
SCHEMA_VERSION: Literal["aizynthfinder_route_job/v1"] = "aizynthfinder_route_job/v1"
METHOD_ID: Literal["aizynthfinder-mcts-route"] = "aizynthfinder-mcts-route"
METHOD_VERSION: Literal["v1"] = "v1"

# The only small-molecule representation this method accepts (AT-0903-2,
# §16.4): formulations, polymer distributions, and unknown kinds are
# rejected at the kind field — never mapped onto a generic molecule.
SUPPORTED_INPUT_KINDS: tuple[str, ...] = ("small_molecule_smiles",)

# Licenses the project has reviewed for model/stock assets (U13).
ALLOWED_MODEL_LICENSES: frozenset[str] = frozenset(
    {"apache-2.0", "mit", "cc-by-4.0", "bsd-3-clause"}
)

SMILES_MAX_LEN = 400

SEARCH_TIME_MIN_S = 5
SEARCH_TIME_MAX_S = 900
SEARCH_ITERATIONS_MIN = 50
SEARCH_ITERATIONS_MAX = 50000
MAX_ROUTES_MAX = 20

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

# What a route manifest is allowed to claim. A stock-resolved route is
# a *proposed hypothesis*: it establishes nothing about yield,
# selectivity, safety, cost, or scale-up (§16.4, AT-0903-3). Encoded
# structurally, not as a disclaimer string.
DOES_NOT_ESTABLISH: tuple[str, ...] = (
    "yield",
    "selectivity",
    "safety",
    "scale_up_feasibility",
    "cost",
    "actual_purchasability",
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
    """Declared provenance of one model/stock/template asset — checked
    against the licensed-asset registry before anything runs."""

    name: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=120)
    license: str = Field(min_length=1, max_length=60)
    source: str = Field(min_length=1, max_length=500)
    sha256: str = Field(min_length=64, max_length=64)


class SmallMoleculeInput(StrictModel):
    """An explicit small-molecule representation — the only supported
    input kind (AT-0903-2)."""

    kind: Literal["small_molecule_smiles"]
    smiles: str = Field(min_length=1, max_length=SMILES_MAX_LEN)


class SearchBounds(StrictModel):
    """Bounded MCTS search — the run can never exceed these limits."""

    time_limit_seconds: int = Field(default=120, ge=SEARCH_TIME_MIN_S, le=SEARCH_TIME_MAX_S)
    iteration_limit: int = Field(default=5000, ge=SEARCH_ITERATIONS_MIN, le=SEARCH_ITERATIONS_MAX)
    max_routes: int = Field(default=5, ge=1, le=MAX_ROUTES_MAX)


class ResourceEnvelope(StrictModel):
    wall_seconds: int = Field(default=600, ge=30, le=MAX_WALL_SECONDS, strict=True)
    memory_mebibytes: int = Field(default=4096, ge=512, le=MAX_MEMORY_MEBIBYTES, strict=True)
    ncores: int = Field(default=2, ge=1, le=MAX_CORES, strict=True)


class RouteJobSpec(StrictModel):
    """The declared retrosynthesis job. Structural validation lives
    here; the license/input-kind/payload-level checks live in
    `validation.py`."""

    schema_version: Literal["1"] = "1"
    method: Literal["aizynthfinder_mcts_route"]
    # The benign target: one explicit small molecule to plan a route to.
    target: SmallMoleculeInput
    # Expansion policy model (USPTO-trained, ONNX), declared with full
    # provenance.
    policy_model: ModelAsset
    # Reaction-template table paired with the policy model.
    templates: ModelAsset
    # Purchasable-compound stock list the search scores leaves against.
    stock: ModelAsset
    # Optional quick-filter policy (onnx).
    filter_model: ModelAsset | None = None
    search: SearchBounds = Field(default_factory=SearchBounds)
    resources: ResourceEnvelope = Field(default_factory=ResourceEnvelope)

    @model_validator(mode="after")
    def check_target(self) -> RouteJobSpec:
        smiles = self.target.smiles
        for ch in smiles:
            if ch not in _SMILES_CHARSET:
                raise ValueError(
                    f"character {ch!r} is not SMILES syntax — the target must be "
                    "an explicit small-molecule representation"
                )
        if "*" in smiles:
            raise ValueError(
                "wildcard/dummy atoms (*) denote a polymer repeat unit or an "
                "undefined attachment — not an explicit defined molecule"
            )
        if "." in smiles:
            raise ValueError("multi-component SMILES ('.') is a mixture, not one target molecule")
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


_SMILES_CHARSET = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789@+-()[]=#%.\\/:$,~?&|!{}<>"
)


# ------------------------------------------------------------------
# Result shape
# ------------------------------------------------------------------


class ProposedRoute(StrictModel):
    """One proposed retrosynthesis route — always `proposed`; a
    stock-resolved route is a hypothesis for human review, never an
    executable protocol (AT-0903-3)."""

    rank: int = Field(ge=1)
    label: Literal["proposed"] = "proposed"
    is_solved: bool = False
    all_precursors_in_stock: bool = False
    num_reactions: int = 0
    precursor_smiles: list[str] = Field(default_factory=list)
    precursors_in_stock: list[str] = Field(default_factory=list)
    score: float | None = None
    reaction_tree: dict[str, Any] = Field(default_factory=dict)


class RouteOutcome(StrictModel):
    """What a route search produced — an honest manifest of proposed
    routes with full model/stock/license provenance. `usable` means the
    search completed and output parsed; `is_solved`/`in_stock` reflect
    only stock-list membership, never experimental feasibility."""

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
    routes: list[ProposedRoute] = Field(default_factory=list)
    num_solved: int = 0
    provenance: dict[str, Any] = Field(default_factory=dict)
    search_stats: dict[str, Any] = Field(default_factory=dict)
    does_not_establish: tuple[str, ...] = DOES_NOT_ESTABLISH
    execution_gate: Literal["independent_plan_approval_required"] = (
        "independent_plan_approval_required"
    )
    evidence_class: Literal["proposed_route_hypothesis"] = "proposed_route_hypothesis"
    model_context: dict[str, Any] = Field(default_factory=dict)
    engine: str = "aizynthfinder"
    engine_version: str | None = None
    adapter_version: str = ADAPTER_VERSION
    input_digest: str = ""
    scientific_status: Literal["not_validated"] = "not_validated"
    error: dict[str, str] | None = None
    isolation: dict[str, Any] = Field(default_factory=dict)
