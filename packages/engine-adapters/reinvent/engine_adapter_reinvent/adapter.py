"""REINVENT execution adapter (CS-0903).

Runs inside the pinned worker image `chem-studio-reinvent:4.8-v1`
(reinvent 4.8 / torch / rdkit). The host process validates and persists
the job payload; this side re-parses it, drift-checks it against the
persisted spec, re-verifies the prior's declared license and content
hash against the baked-in file, runs the de novo sampling campaign on
CPU, and classifies the result honestly: parseable proposed candidates
only — never exit-0 equals success.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import os
import subprocess
import sys
import tempfile
from typing import Any

from .contracts import (
    ADAPTER_VERSION,
    DOES_NOT_ESTABLISH,
    METHOD_ID,
    METHOD_VERSION,
    REINVENT_VERSION,
    DesignCandidate,
    DesignJobSpec,
    DesignOutcome,
    EngineFailure,
)
from .validation import (
    IMAGE_MODEL_PATHS,
    KNOWN_PRIORS,
    build_job_payload,
    check_input_kind,
    check_model_license,
)

_RAW_NOTE = (
    "deterministic sampling from a generative prior; candidates are "
    "proposals — no experimental property is established"
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


def _version_line_ok(version: str | None) -> bool:
    """The tested pin is the 4.8 release *line* — upstream's installed
    dist reports a patch (e.g. ``4.8.24`` from the v4.8 tag)."""
    if not version:
        return False
    return tuple(version.split(".")[:2]) == tuple(REINVENT_VERSION.split("."))


class ReinventAdapter:
    """Thin wrapper over the REINVENT 4.8 sampling run mode with a
    fixed input contract — the only call surface the worker exposes."""

    def capability(self) -> dict[str, Any]:
        """Report what this environment can actually run (§16.1 labels)."""
        reinvent = _dist_version("reinvent")
        if reinvent is None:
            state = "not_installed"
        elif not _version_line_ok(reinvent):
            state = "installed_unverified"
        else:
            state = "available_tested"
        assets: dict[str, Any] = {}
        if state == "available_tested":
            for name, known in KNOWN_PRIORS.items():
                path = IMAGE_MODEL_PATHS[name]
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
            "engine": "reinvent",
            "engine_version": reinvent,
            "state": state,
            "methods": {
                f"{METHOD_ID}/{METHOD_VERSION}": {
                    "state": state,
                    "endpoint": "de_novo_candidate_proposal",
                    "domain": (
                        "small-molecule generation around an explicit SMILES "
                        "anchor using a licensed REINVENT prior (CPU)"
                    ),
                    "benchmark": (
                        "reinvent_pubchem prior emits structurally diverse "
                        "drug-like SMILES at num_smiles<=512 — plumbing "
                        "regression lock only, not a chemical claim"
                    ),
                    "limitations": [
                        "candidates are proposals — no activity, "
                        "synthesizability, safety or novelty claim",
                        "small-molecule SMILES input only; formulations, "
                        "polymer distributions and unknown kinds rejected",
                        "license-gated priors only — unreviewed models blocked",
                    ],
                    "assets": assets,
                }
            },
        }

    def compute(self, spec: DesignJobSpec, *, payload: dict[str, Any]) -> DesignOutcome:
        reinvent_v = _dist_version("reinvent")
        if reinvent_v is None:
            raise EngineFailure("ENGINE_UNAVAILABLE", "reinvent is not installed in this image")
        if not _version_line_ok(reinvent_v):
            raise EngineFailure(
                "ENGINE_UNAVAILABLE",
                f"reinvent {reinvent_v} differs from tested {REINVENT_VERSION} line",
            )

        # License + input-kind gates re-applied inside the container —
        # the persisted bytes are authoritative, never the caller.
        check_model_license(spec.model)
        check_input_kind(spec.anchor.kind)

        # Drift-check: the persisted payload must equal what this spec
        # would persist — otherwise the artifact was not produced by
        # this contract.
        expected = build_job_payload(spec)
        if _normalize(payload) != _normalize(expected):
            raise EngineFailure(
                "ENGINE_UNSUPPORTED_INPUT",
                "persisted job payload does not match the job spec digest",
            )

        # Verify the baked-in asset matches the declared provenance
        # byte-for-byte before invoking the engine — no download path
        # exists in this image at all.
        model_path = IMAGE_MODEL_PATHS.get(spec.model.name)
        if model_path is None or not os.path.exists(model_path):
            raise EngineFailure(
                "LICENSE_UNAVAILABLE",
                f"licensed prior '{spec.model.name}' is not baked into this image",
            )
        if _sha256_file(model_path) != spec.model.sha256:
            raise EngineFailure(
                "LICENSE_UNAVAILABLE",
                "baked prior content hash does not match the declared "
                "provenance — the asset is not the reviewed model",
            )

        # The anchor must be a molecule rdkit can actually parse —
        # the host-side gate is syntactic; the container is
        # authoritative on chemistry.
        from rdkit import Chem, DataStructs
        from rdkit.Chem import AllChem

        anchor_mol = Chem.MolFromSmiles(spec.anchor.smiles)
        if anchor_mol is None:
            raise EngineFailure(
                "ENGINE_UNSUPPORTED_INPUT",
                "anchor SMILES does not parse — not a defined molecule",
            )
        if anchor_mol.GetNumAtoms() < 2:
            raise EngineFailure(
                "ENGINE_UNSUPPORTED_INPUT",
                "anchor must contain at least two heavy atoms",
            )

        n = spec.num_smiles
        workdir = tempfile.mkdtemp(prefix="reinvent-")
        config_path = os.path.join(workdir, "sampling.toml")
        out_csv = os.path.join(workdir, "sampling.csv")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(
                'run_type = "sampling"\n'
                'device = "cpu"\n'
                'json_out_config = "_sampling.json"\n'
                "\n[parameters]\n"
                f'model_file = "{model_path}"\n'
                f'output_file = "{out_csv}"\n'
                f"num_smiles = {n}\n"
                f"unique_molecules = {'true' if spec.unique_molecules else 'false'}\n"
                f"randomize_smiles = {'true' if spec.randomize_smiles else 'false'}\n"
                "isomeric_smiles = true\n"
            )
        try:
            proc = subprocess.run(  # noqa: S603 — fixed argv inside container
                [
                    sys.executable,
                    "-m",
                    "reinvent.Reinvent",
                    config_path,
                    "--device",
                    "cpu",
                ],
                cwd=workdir,
                capture_output=True,
                timeout=spec.resources.wall_seconds,
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "HOME": workdir,
                    "OMP_NUM_THREADS": "1",
                    "MKL_NUM_THREADS": "1",
                    "OPENBLAS_NUM_THREADS": "1",
                    "PYTHONHASHSEED": "0",
                },
            )
        except subprocess.TimeoutExpired as e:
            raise EngineFailure(
                "ENGINE_FAILURE", "reinvent sampling exceeded its wall clock"
            ) from e
        if proc.returncode != 0:
            raise EngineFailure(
                "ENGINE_FAILURE",
                "reinvent sampling exited non-zero; see worker log",
            )
        if not os.path.exists(out_csv):
            raise EngineFailure("ENGINE_MALFORMED_OUTPUT", "reinvent produced no sampling CSV")

        rows: list[dict[str, str]] = []
        try:
            with open(out_csv, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None or "SMILES" not in reader.fieldnames:
                    raise EngineFailure(
                        "ENGINE_MALFORMED_OUTPUT",
                        "sampling CSV lacks the expected SMILES header",
                    )
                for row in reader:
                    rows.append(row)
        except EngineFailure:
            raise
        except Exception as e:
            raise EngineFailure(
                "ENGINE_MALFORMED_OUTPUT",
                f"could not parse sampling CSV: {type(e).__name__}",
            ) from e
        if not rows:
            raise EngineFailure("ENGINE_MALFORMED_OUTPUT", "reinvent emitted zero candidates")

        anchor_fp = AllChem.GetMorganFingerprintAsBitVect(anchor_mol, 2, nBits=2048)
        candidates: list[DesignCandidate] = []
        for i, row in enumerate(rows[:n], start=1):
            smi = (row.get("SMILES") or "").strip()
            if not smi:
                continue
            sim: float | None = None
            cand_mol = Chem.MolFromSmiles(smi)
            if cand_mol is not None:
                cand_fp = AllChem.GetMorganFingerprintAsBitVect(cand_mol, 2, nBits=2048)
                sim = round(float(DataStructs.TanimotoSimilarity(anchor_fp, cand_fp)), 4)
            try:
                nll = float(row["NLL"]) if row.get("NLL") else None
            except (TypeError, ValueError):
                nll = None
            candidates.append(
                DesignCandidate(rank=i, smiles=smi, nll=nll, similarity_to_anchor=sim)
            )
        if not candidates:
            raise EngineFailure("ENGINE_MALFORMED_OUTPUT", "reinvent emitted no parseable SMILES")

        anchor_digest = hashlib.sha256(spec.anchor.smiles.encode()).hexdigest()
        provenance = {
            "model": spec.model.model_dump(mode="json"),
            "model_file_sha256": spec.model.sha256,
            "anchor_digest": anchor_digest,
            "num_smiles_requested": n,
            "randomize_smiles": spec.randomize_smiles,
            "unique_molecules": spec.unique_molecules,
        }
        model_context = {
            "model": "REINVENT generative prior (SMILES token RNN)",
            "parameter_table": "none — learned prior parameters",
            "anchor_role": "context molecule; candidates report Tanimoto "
            "similarity (Morgan radius-2) to it — the anchor does not "
            "condition de novo sampling",
            "assumptions": [
                "prior sampled multinomially on CPU",
                "unique canonical SMILES when unique_molecules is set",
            ],
            "calibration": "none — pretrained prior as shipped; not fitted to task data",
        }
        return DesignOutcome(
            status="succeeded",
            usable=True,
            classification="reference_integration",
            candidates=candidates,
            num_generated=len(candidates),
            provenance=provenance,
            does_not_establish=DOES_NOT_ESTABLISH,
            model_context=model_context,
            engine_version=reinvent_v,
            input_digest=spec.digest(),
            error=None,
            isolation={"note": _RAW_NOTE},
        )


def _normalize(payload: dict[str, Any]) -> dict[str, Any]:
    """Structural equality for drift-checking: the persisted JSON object
    and the rebuilt payload must agree field-for-field."""
    return {
        "schema_name": payload.get("schema_name"),
        "schema_version": payload.get("schema_version"),
        "method": payload.get("method"),
        "method_version": payload.get("method_version"),
        "anchor": dict(payload.get("anchor") or {}),
        "model": dict(payload.get("model") or {}),
        "num_smiles": payload.get("num_smiles"),
        "unique_molecules": payload.get("unique_molecules"),
        "randomize_smiles": payload.get("randomize_smiles"),
        "adapter_version": payload.get("adapter_version"),
    }
