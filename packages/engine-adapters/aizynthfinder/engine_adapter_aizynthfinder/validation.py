"""License/provenance gating, the persisted job payload, and the
execution-assessment verdict (§16.4, AT-0903-3, U13).

Pure Python — no aizynthfinder/rdkit import — so the host process can
validate the declared job and persist the canonical payload without
science deps (E05). The registries below are the license-reviewed
asset set:

* ``KNOWN_MODELS``: USPTO expansion/filter policy ONNX files and the
  paired template table (Zenodo records 7797465 / 7341155, CC-BY-4.0).
* ``KNOWN_STOCKS``: the ZINC purchasable-compound list shipped with the
  AiZynthFinder figshare article (MIT).

Every entry pins the exact content hash — an asset that does not match
*both* license and digest is not the reviewed asset. The gate runs
before any download or run attempt; the container has no network, so
nothing is ever fetched at run time.
"""

from __future__ import annotations

from typing import Any

from .contracts import (
    ADAPTER_VERSION,
    ALLOWED_MODEL_LICENSES,
    DOES_NOT_ESTABLISH,
    METHOD_ID,
    METHOD_VERSION,
    SCHEMA_VERSION,
    SUPPORTED_INPUT_KINDS,
    EngineFailure,
    ModelAsset,
    RouteJobSpec,
    RouteOutcome,
)

# name -> reviewed asset. version strings name the upstream record so
# the provenance is auditable end to end.
KNOWN_MODELS: dict[str, ModelAsset] = {
    "uspto_expansion": ModelAsset(
        name="uspto_expansion",
        version="zenodo:7797465",
        license="cc-by-4.0",
        source="https://zenodo.org/records/7797465/files/uspto_model.onnx",
        sha256="bd0a3cb74cd7068de474c8fb789a00a66bc42c75636d66510ccac585ebe928f8",
    ),
    "uspto_templates": ModelAsset(
        name="uspto_templates",
        version="zenodo:7341155",
        license="cc-by-4.0",
        source=("https://zenodo.org/records/7341155/files/uspto_unique_templates.csv.gz"),
        sha256="a4f1945e90cfa195538320833d68aed38f14e2fcc2f8afb5d958bc920edcafbe",
    ),
    "uspto_filter": ModelAsset(
        name="uspto_filter",
        version="zenodo:7797465",
        license="cc-by-4.0",
        source="https://zenodo.org/records/7797465/files/uspto_filter_model.onnx",
        sha256="ad29aa32bdfcbe37065045546493806cf04899c55386c438905d83fb14bb6320",
    ),
}

KNOWN_STOCKS: dict[str, ModelAsset] = {
    "zinc_stock": ModelAsset(
        name="zinc_stock",
        version="figshare:23086469",
        license="mit",
        source="https://ndownloader.figshare.com/files/23086469",
        sha256="99d39a6f807c3e815487500bafc2b4a9dc66a31af189e3b1776874fb0d4a188d",
    ),
}

# Where the reviewed assets live inside the pinned image — the runner
# maps declared names to these baked-in paths; there is no download
# path at all (network is disabled at run time).
IMAGE_ASSET_PATHS: dict[str, str] = {
    "uspto_expansion": "/opt/models/uspto_model.onnx",
    "uspto_templates": "/opt/models/uspto_unique_templates.csv.gz",
    "uspto_filter": "/opt/models/uspto_filter_model.onnx",
    "zinc_stock": "/opt/models/zinc_stock.hdf5",
}


def check_asset_license(
    asset: ModelAsset, registry: dict[str, ModelAsset], role: str
) -> ModelAsset:
    """License/provenance gate (CS-0903 order-of-work item 1): the
    declared asset must be a reviewed registry entry — right name,
    version, license, source, and content hash — and its license must
    be in the project's allowed set. Anything else is
    ``LICENSE_UNAVAILABLE``; nothing is downloaded or substituted."""
    if asset.license.lower() not in ALLOWED_MODEL_LICENSES:
        raise EngineFailure(
            "LICENSE_UNAVAILABLE",
            f"declared license '{asset.license}' for {role} '{asset.name}' is not "
            "in the reviewed license set — the asset is blocked",
        )
    known = registry.get(asset.name)
    if known is None:
        raise EngineFailure(
            "LICENSE_UNAVAILABLE",
            f"{role} '{asset.name}' is not in the licensed-asset registry — "
            "no unreviewed asset may run",
        )
    for field in ("version", "license", "sha256"):
        if getattr(asset, field) != getattr(known, field):
            raise EngineFailure(
                "LICENSE_UNAVAILABLE",
                f"declared {field} for {role} '{asset.name}' does not match the "
                "reviewed registry entry — provenance cannot be verified",
            )
    return known


def check_input_kind(raw_kind: Any) -> None:
    """AT-0903-2: only an explicit small-molecule representation is
    supported. A formulation, a polymer distribution, or an unknown
    kind is unsupported input — rejected, never coerced to a generic
    molecule."""
    if raw_kind not in SUPPORTED_INPUT_KINDS:
        raise EngineFailure(
            "ENGINE_UNSUPPORTED_INPUT",
            f"input kind '{raw_kind}' is unsupported — this method accepts only "
            "an explicit small-molecule representation "
            f"{list(SUPPORTED_INPUT_KINDS)}; formulations, polymer "
            "distributions and unknown inputs are never approximated",
        )


def check_all_assets(spec: RouteJobSpec) -> None:
    """Apply the license gate to every declared asset — policy model,
    templates, stock list, and optional filter model."""
    check_asset_license(spec.policy_model, KNOWN_MODELS, "expansion policy")
    check_asset_license(spec.templates, KNOWN_MODELS, "template table")
    check_asset_license(spec.stock, KNOWN_STOCKS, "stock list")
    if spec.filter_model is not None:
        check_asset_license(spec.filter_model, KNOWN_MODELS, "filter policy")


def build_job_payload(spec: RouteJobSpec) -> dict[str, Any]:
    """The canonical persisted input — the exact bytes stored in the
    vault before execution and consumed inside the isolated worker."""
    check_all_assets(spec)
    return {
        "schema_name": SCHEMA_VERSION,
        "schema_version": 1,
        "method": METHOD_ID,
        "method_version": METHOD_VERSION,
        "target": {"kind": spec.target.kind, "smiles": spec.target.smiles},
        "policy_model": spec.policy_model.model_dump(mode="json"),
        "templates": spec.templates.model_dump(mode="json"),
        "stock": spec.stock.model_dump(mode="json"),
        "filter_model": (spec.filter_model.model_dump(mode="json") if spec.filter_model else None),
        "search": spec.search.model_dump(mode="json"),
        "adapter_version": ADAPTER_VERSION,
    }


# ------------------------------------------------------------------
# Execution scope (AT-0903-3) — a solved route is still a hypothesis
# ------------------------------------------------------------------


def evaluate_execution(outcome: RouteOutcome) -> dict[str, Any]:
    """Decide whether this route output may execute in the lab.

    The verdict is always a typed record: even a fully stock-resolved
    route is a *proposed hypothesis* — stock-list membership is not
    evidence of yield, selectivity, safety, or scale-up, and the system
    never auto-releases a lab protocol. Execution requires the
    independent experiment-plan approval path (§14.1), which only a
    human ``approve_experiment`` principal can grant (§21.1)."""
    if outcome.status != "succeeded" or not outcome.usable:
        return {
            "executable": False,
            "verdict": "not_evaluated",
            "basis": "no_usable_route_output",
            "detail": "the run produced no usable proposed-route output",
        }
    solved = [r for r in outcome.routes if r.is_solved]
    return {
        "executable": False,
        "verdict": "independent_plan_approval_required",
        "basis": "proposed_route_is_hypothesis",
        "num_stock_resolved_routes": len(solved),
        "detail": (
            f"{len(solved)} route(s) reach the declared stock list; stock "
            "membership establishes none of "
            f"{list(DOES_NOT_ESTABLISH)} — every route remains a "
            "proposed hypothesis that requires independent human plan "
            "approval before any lab execution; the system never "
            "auto-releases a protocol"
        ),
    }
