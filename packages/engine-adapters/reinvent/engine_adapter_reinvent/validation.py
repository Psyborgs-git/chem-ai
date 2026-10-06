"""License/provenance gating and the persisted job payload (§16.4, U13).

Pure Python — no torch/rdkit import — so the host process can validate
the declared job and persist the canonical payload without science deps
(E05). The registry below is the license-reviewed model set:

* ``KNOWN_PRIORS``: REINVENT prior files whose upstream license was
  verified (Zenodo record 20701824, Apache-2.0). Each entry pins the
  exact content hash — a prior that does not match *both* license and
  digest is not the reviewed asset.

The gate matters because the ticket requires license + provenance
checks *before* any download or run attempt: the adapter never fetches
assets at run time (the container has no network); it only verifies
that the baked-in files match the declared registry.
"""

from __future__ import annotations

from typing import Any

from .contracts import (
    ADAPTER_VERSION,
    ALLOWED_MODEL_LICENSES,
    METHOD_ID,
    METHOD_VERSION,
    SCHEMA_VERSION,
    SUPPORTED_INPUT_KINDS,
    DesignJobSpec,
    EngineFailure,
    ModelAsset,
)

# name -> reviewed asset. version strings name the upstream record so
# the provenance is auditable end to end.
KNOWN_PRIORS: dict[str, ModelAsset] = {
    "reinvent_pubchem": ModelAsset(
        name="reinvent_pubchem",
        version="zenodo:20701824",
        license="apache-2.0",
        source="https://zenodo.org/records/20701824/files/reinvent_pubchem.prior",
        sha256="fe8cd1678452ad292a8f93e97cb19a85959b729e17113e157180d5e69ae89ef3",
    ),
}

# Where the reviewed assets live inside the pinned image — the runner
# maps declared names to these baked-in paths; there is no download
# path at all (network is disabled at run time).
IMAGE_MODEL_PATHS: dict[str, str] = {
    "reinvent_pubchem": "/opt/models/reinvent_pubchem.prior",
}


def check_model_license(asset: ModelAsset) -> ModelAsset:
    """License/provenance gate (CS-0903 order-of-work item 1): the
    declared model must be a reviewed registry asset — right name,
    version, license, source, and content hash — and its license must
    be in the project's allowed set. Anything else is
    ``LICENSE_UNAVAILABLE``; nothing is downloaded or substituted."""
    if asset.license.lower() not in ALLOWED_MODEL_LICENSES:
        raise EngineFailure(
            "LICENSE_UNAVAILABLE",
            f"declared license '{asset.license}' for model '{asset.name}' is not "
            "in the reviewed license set — the model is blocked",
        )
    known = KNOWN_PRIORS.get(asset.name)
    if known is None:
        raise EngineFailure(
            "LICENSE_UNAVAILABLE",
            f"model '{asset.name}' is not in the licensed-asset registry — "
            "no unreviewed model may run",
        )
    for field in ("version", "license", "sha256"):
        if getattr(asset, field) != getattr(known, field):
            raise EngineFailure(
                "LICENSE_UNAVAILABLE",
                f"declared {field} for '{asset.name}' does not match the "
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


def build_job_payload(spec: DesignJobSpec) -> dict[str, Any]:
    """The canonical persisted input — the exact bytes stored in the
    vault before execution and consumed inside the isolated worker."""
    check_model_license(spec.model)
    return {
        "schema_name": SCHEMA_VERSION,
        "schema_version": 1,
        "method": METHOD_ID,
        "method_version": METHOD_VERSION,
        "anchor": {"kind": spec.anchor.kind, "smiles": spec.anchor.smiles},
        "model": spec.model.model_dump(mode="json"),
        "num_smiles": spec.num_smiles,
        "unique_molecules": spec.unique_molecules,
        "randomize_smiles": spec.randomize_smiles,
        "adapter_version": ADAPTER_VERSION,
    }
