"""AiZynthFinder execution adapter (CS-0903).

Runs inside the pinned worker image
`chem-studio-aizynthfinder:4.4.1-v1` (aizynthfinder 4.4.1 / onnxruntime
/ rdkit). The host process validates and persists the job payload; this
side re-parses it, drift-checks it against the persisted spec,
re-verifies every declared model/stock/template asset against the
baked-in files, runs the bounded MCTS search, and classifies the
result honestly: parseable proposed routes only — a stock-resolved
route is a hypothesis, never an executable protocol (AT-0903-3).
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
from typing import Any

from .contracts import (
    ADAPTER_VERSION,
    AIZYNTHFINDER_VERSION,
    DOES_NOT_ESTABLISH,
    METHOD_ID,
    METHOD_VERSION,
    EngineFailure,
    ProposedRoute,
    RouteJobSpec,
    RouteOutcome,
)
from .validation import (
    IMAGE_ASSET_PATHS,
    KNOWN_MODELS,
    KNOWN_STOCKS,
    build_job_payload,
    check_all_assets,
    check_input_kind,
)

_RAW_NOTE = (
    "bounded MCTS retrosynthesis over licensed policy/stock assets; "
    "routes are hypotheses — stock membership is not experimental evidence"
)


def _dist_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class AiZynthAdapter:
    """Thin wrapper over AiZynthFinder 4.4.1 with a fixed input
    contract — the only call surface the worker exposes."""

    def capability(self) -> dict[str, Any]:
        """Report what this environment can actually run (§16.1 labels)."""
        azf = _dist_version("aizynthfinder")
        if azf is None:
            state = "not_installed"
        elif azf != AIZYNTHFINDER_VERSION:
            state = "installed_unverified"
        else:
            state = "available_tested"
        assets: dict[str, Any] = {}
        if state == "available_tested":
            registry = dict(KNOWN_MODELS)
            registry.update(KNOWN_STOCKS)
            for name, known in registry.items():
                path = IMAGE_ASSET_PATHS[name]
                ok = os.path.exists(path) and _sha256_file(path) == known.sha256
                assets[name] = {
                    "license": known.license,
                    "source": known.source,
                    "path": path,
                    "sha256_verified": ok,
                    "state": "available_tested" if ok else "installed_unverified",
                }
                if not ok:
                    state = "installed_unverified"
        return {
            "adapter_version": ADAPTER_VERSION,
            "engine": "aizynthfinder",
            "engine_version": azf,
            "state": state,
            "methods": {
                f"{METHOD_ID}/{METHOD_VERSION}": {
                    "state": state,
                    "endpoint": "proposed_retrosynthesis_routes",
                    "domain": (
                        "single-target small-molecule retrosynthesis with the "
                        "licensed USPTO policy + templates against the "
                        "licensed ZINC stock list (bounded MCTS, CPU)"
                    ),
                    "benchmark": (
                        "well-documented simple targets (e.g. caffeine, "
                        "ibuprofen) produce route candidates — a plumbing "
                        "regression lock only, not route quality validation"
                    ),
                    "limitations": [
                        "routes are proposed hypotheses — stock membership is "
                        "not yield, selectivity, safety or scale-up evidence",
                        "no automatic lab execution — independent plan "
                        "approval required (AT-0903-3)",
                        "small-molecule SMILES input only; formulations, "
                        "polymer distributions and unknown kinds rejected",
                        "license-gated assets only — unreviewed models or stock lists blocked",
                    ],
                    "assets": assets,
                }
            },
        }

    def compute(self, spec: RouteJobSpec, *, payload: dict[str, Any]) -> RouteOutcome:
        azf_v = _dist_version("aizynthfinder")
        if azf_v is None:
            raise EngineFailure(
                "ENGINE_UNAVAILABLE", "aizynthfinder is not installed in this image"
            )
        if azf_v != AIZYNTHFINDER_VERSION:
            raise EngineFailure(
                "ENGINE_UNAVAILABLE",
                f"aizynthfinder {azf_v} differs from tested {AIZYNTHFINDER_VERSION}",
            )

        # License + input-kind gates re-applied inside the container —
        # the persisted bytes are authoritative, never the caller.
        check_all_assets(spec)
        check_input_kind(spec.target.kind)

        expected = build_job_payload(spec)
        if _normalize(payload) != _normalize(expected):
            raise EngineFailure(
                "ENGINE_UNSUPPORTED_INPUT",
                "persisted job payload does not match the job spec digest",
            )

        # Verify every baked-in asset matches its declared provenance
        # byte-for-byte before invoking the engine — no download path
        # exists in this image at all.
        declared = {
            spec.policy_model.name: spec.policy_model,
            spec.templates.name: spec.templates,
            spec.stock.name: spec.stock,
        }
        if spec.filter_model is not None:
            declared[spec.filter_model.name] = spec.filter_model
        for name, asset in declared.items():
            path = IMAGE_ASSET_PATHS.get(name)
            if path is None or not os.path.exists(path):
                raise EngineFailure(
                    "LICENSE_UNAVAILABLE",
                    f"licensed asset '{name}' is not baked into this image",
                )
            if _sha256_file(path) != asset.sha256:
                raise EngineFailure(
                    "LICENSE_UNAVAILABLE",
                    f"baked '{name}' content hash does not match the declared "
                    "provenance — the asset is not the reviewed file",
                )

        # The target must be a molecule rdkit can actually parse — the
        # container is authoritative on chemistry.
        from aizynthfinder.aizynthfinder import AiZynthFinder
        from aizynthfinder.chem import Molecule

        try:
            target_mol = Molecule(smiles=spec.target.smiles)
        except Exception as e:
            raise EngineFailure(
                "ENGINE_UNSUPPORTED_INPUT",
                "target SMILES does not parse — not a defined molecule",
            ) from e

        expansion = {
            "uspto": [IMAGE_ASSET_PATHS["uspto_expansion"], IMAGE_ASSET_PATHS["uspto_templates"]]
        }
        config: dict[str, Any] = {
            "expansion": expansion,
            "stock": {"zinc": IMAGE_ASSET_PATHS["zinc_stock"]},
            "search": {
                "algorithm": "mcts",
                "time_limit": spec.search.time_limit_seconds,
                "iteration_limit": spec.search.iteration_limit,
            },
            "post_processing": {
                "min_routes": 1,
                "max_routes": spec.search.max_routes,
                "all_routes": False,
            },
        }
        if spec.filter_model is not None:
            config["filter"] = {"uspto": IMAGE_ASSET_PATHS["uspto_filter"]}

        try:
            finder = AiZynthFinder(configdict=config)
        except Exception as e:
            raise EngineFailure(
                "ENGINE_FAILURE", f"engine configuration failed: {type(e).__name__}"
            ) from e
        finder.expansion_policy.select("uspto")
        finder.stock.select("zinc")
        if spec.filter_model is not None:
            finder.filter_policy.select("uspto")
        finder.target_mol = target_mol
        try:
            finder.tree_search()
            finder.build_routes()
        except Exception as e:
            raise EngineFailure(
                "ENGINE_FAILURE", f"retrosynthesis search failed: {type(e).__name__}"
            ) from e

        try:
            stats = finder.extract_statistics()
        except Exception:
            stats = {}

        routes: list[ProposedRoute] = []
        n_solved = 0
        for i, tree in enumerate(finder.routes.reaction_trees, start=1):
            meta = dict(tree.metadata)
            leafs = list(tree.leafs())
            in_stock = [tree.in_stock(m) for m in leafs]
            leaf_smiles = [str(m.smiles) for m in leafs]
            solved = bool(meta.get("is_solved"))
            if solved:
                n_solved += 1
            score = meta.get("score")
            try:
                tree_dict = tree.to_dict(include_metadata=False)
            except Exception:
                tree_dict = {}
            n_reactions = _count_reactions(tree_dict)
            routes.append(
                ProposedRoute(
                    rank=i,
                    is_solved=solved,
                    all_precursors_in_stock=bool(in_stock) and all(in_stock),
                    num_reactions=n_reactions,
                    precursor_smiles=leaf_smiles,
                    precursors_in_stock=[
                        s for s, ok in zip(leaf_smiles, in_stock, strict=True) if ok
                    ],
                    score=float(score) if isinstance(score, int | float) else None,
                    reaction_tree=tree_dict,
                )
            )

        target_digest = hashlib.sha256(spec.target.smiles.encode()).hexdigest()
        provenance = {
            "policy_model": spec.policy_model.model_dump(mode="json"),
            "templates": spec.templates.model_dump(mode="json"),
            "stock": spec.stock.model_dump(mode="json"),
            "filter_model": (
                spec.filter_model.model_dump(mode="json") if spec.filter_model else None
            ),
            "target_digest": target_digest,
            "search": spec.search.model_dump(mode="json"),
        }
        model_context = {
            "model": "USPTO-trained template-based expansion policy (ONNX) + MCTS search",
            "stock_basis": "ZINC purchasable-compound list — stock membership "
            "is catalog presence only, not supply or suitability",
            "assumptions": [
                "bounded search: declared time/iteration limits",
                "route ranking by engine default scorer",
            ],
            "calibration": "none — pretrained policy as shipped; not fitted to task data",
        }
        return RouteOutcome(
            status="succeeded",
            usable=True,
            classification="reference_integration",
            routes=routes,
            num_solved=n_solved,
            provenance=provenance,
            search_stats={k: v for k, v in stats.items() if _jsonable(v)},
            does_not_establish=DOES_NOT_ESTABLISH,
            model_context=model_context,
            engine_version=azf_v,
            input_digest=spec.digest(),
            error=None,
            isolation={"note": _RAW_NOTE},
        )


def _count_reactions(tree_dict: dict[str, Any]) -> int:
    """Count RetroReaction nodes in the emitted reaction tree."""
    if not tree_dict:
        return 0
    node_type = tree_dict.get("type")
    children = tree_dict.get("children") or []
    n = 1 if node_type == "reaction" else 0
    for child in children:
        if isinstance(child, dict):
            n += _count_reactions(child)
    return n


def _jsonable(v: Any) -> bool:
    return v is None or isinstance(v, str | int | float | bool | list | dict)


def _normalize(payload: dict[str, Any]) -> dict[str, Any]:
    """Structural equality for drift-checking: the persisted JSON object
    and the rebuilt payload must agree field-for-field."""
    return {
        "schema_name": payload.get("schema_name"),
        "schema_version": payload.get("schema_version"),
        "method": payload.get("method"),
        "method_version": payload.get("method_version"),
        "target": dict(payload.get("target") or {}),
        "policy_model": dict(payload.get("policy_model") or {}),
        "templates": dict(payload.get("templates") or {}),
        "stock": dict(payload.get("stock") or {}),
        "filter_model": dict(payload.get("filter_model") or {})
        if payload.get("filter_model")
        else None,
        "search": dict(payload.get("search") or {}),
        "adapter_version": payload.get("adapter_version"),
    }
