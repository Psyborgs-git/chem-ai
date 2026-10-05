"""Chemprop MPNN adapter (CS-0604, §15.3). Runs inside the worker image.

The adapter performs a narrow mapping only: directed message-passing
regression on caller-supplied rows, an explicit ensemble for engine-level
disagreement, and content-addressed artifact lineage. It never re-splits
the data, never invents labels, and reports exactly what ran.
"""

from __future__ import annotations

import importlib.metadata
import json
from decimal import Decimal, InvalidOperation
from typing import Any

from .contracts import (
    ENGINE_VERSION,
    REPRESENTATION,
    EngineFailure,
    PredictionItem,
    PredictResult,
    PredictSpec,
    TrainResult,
    TrainSpec,
)
from .validation import check_rows, model_file_digest, validate_predictions


def _require_engine() -> None:
    try:
        installed = importlib.metadata.version("chemprop")
    except importlib.metadata.PackageNotFoundError as e:
        raise EngineFailure("ENGINE_UNAVAILABLE", "Chemprop 2.3.1 is not installed") from e
    if installed != ENGINE_VERSION:
        raise EngineFailure("ENGINE_UNAVAILABLE", f"Chemprop {installed} differs from tested 2.3.1")


def _finite_label(raw: Decimal, row_id: str) -> float:
    try:
        value = float(raw)
    except (InvalidOperation, ValueError, TypeError) as e:
        raise EngineFailure(
            "ENGINE_UNSUPPORTED_INPUT", f"row {row_id}: label is not a finite number"
        ) from e
    if value != value or value in (float("inf"), float("-inf")):
        raise EngineFailure(
            "ENGINE_UNSUPPORTED_INPUT", f"row {row_id}: label is not a finite number"
        )
    return value


def _trainer(max_epochs: int) -> Any:
    from lightning import pytorch as pl

    return pl.Trainer(
        logger=False,
        enable_checkpointing=False,
        enable_model_summary=False,
        enable_progress_bar=False,
        max_epochs=max_epochs,
        accelerator="cpu",
        devices=1,
        num_sanity_val_steps=0,
    )


class ChempropAdapter:
    def train(self, spec: TrainSpec) -> tuple[TrainResult, dict[str, bytes]]:
        """Fit an ensemble on the supplied rows; returns the result and
        the artifact files the runner wrote into scratch.

        The artifact set includes ``manifest.json`` recording the train
        spec digest — the model's lineage. ``model_digest`` covers the
        spec digest + every artifact file, so predictions bind to the
        exact ensemble and spec that produced it."""
        _require_engine()
        check_rows(spec.rows)
        # No optional science package is imported until an explicit request.
        import numpy as np
        from chemprop import data, featurizers, models, nn
        from lightning import pytorch as pl

        featurizer = featurizers.SimpleMoleculeMolGraphFeaturizer()
        points = []
        for r in spec.rows:
            try:
                points.append(
                    data.MoleculeDatapoint.from_smi(
                        r.smiles, np.array([_finite_label(r.label, r.row_id)])
                    )
                )
            except EngineFailure:
                raise
            except Exception as e:
                raise EngineFailure(
                    "ENGINE_UNSUPPORTED_INPUT",
                    f"row {r.row_id} could not be featurized; nothing was dropped or imputed",
                ) from e
        dset = data.MoleculeDataset(points, featurizer)
        scaler = dset.normalize_targets()
        loader = data.build_dataloader(
            dset,
            batch_size=min(spec.batch_size, len(spec.rows)),
            num_workers=0,
            seed=spec.seed,
            shuffle=True,
        )
        out_transform = nn.UnscaleTransform.from_standard_scaler(scaler)
        files: dict[str, bytes] = {}
        for i in range(spec.ensemble_size):
            pl.seed_everything(spec.seed + i, workers=True)
            mpnn = models.MPNN(
                nn.BondMessagePassing(d_h=spec.hidden_dim, depth=spec.depth),
                nn.MeanAggregation(),
                nn.RegressionFFN(input_dim=spec.hidden_dim, output_transform=out_transform),
                batch_norm=True,
            )
            try:
                _trainer(spec.max_epochs).fit(mpnn, loader)
            except Exception as e:
                raise EngineFailure(
                    "ENGINE_UNAVAILABLE", "Chemprop training failed; no artifact produced"
                ) from e
            name = f"model_{i}.pt"
            models.save_model(name, mpnn, [spec.scope.name])
            with open(name, "rb") as f:
                files[name] = f.read()
        files["manifest.json"] = json.dumps(
            {"spec_digest": spec.digest(), "scope": spec.scope.model_dump(mode="json")}
        ).encode()
        result = TrainResult(
            status="trained",
            model_files=sorted(files),
            model_digest=model_file_digest(spec.digest(), files),
            trained_rows=len(spec.rows),
            ensemble_size=spec.ensemble_size,
            epochs_ran=spec.max_epochs,
            seed=spec.seed,
            representation=REPRESENTATION,
        )
        return result, files

    def predict(self, spec: PredictSpec, model_files: dict[str, bytes]) -> PredictResult:
        """Score rows against the declared artifact set. The digest
        check binds predictions to the exact ensemble and scope that
        produced the artifact — a different, corrupted, or foreign
        artifact is refused, not scored."""
        _require_engine()
        check_rows(spec.rows)
        manifest_raw = model_files.get("manifest.json")
        if manifest_raw is None:
            raise EngineFailure(
                "ENGINE_UNSUPPORTED_INPUT",
                "model artifact set has no lineage manifest; provenance is required",
            )
        try:
            spec_digest = json.loads(manifest_raw)["spec_digest"]
        except (ValueError, KeyError, TypeError) as e:
            raise EngineFailure(
                "ENGINE_UNSUPPORTED_INPUT", "artifact manifest is unreadable"
            ) from e
        recomputed = model_file_digest(spec_digest, model_files)
        if recomputed != spec.model_digest:
            raise EngineFailure(
                "ENGINE_UNSUPPORTED_INPUT",
                "model artifact does not match the declared lineage digest",
            )
        import torch
        from chemprop import data, featurizers, models

        featurizer = featurizers.SimpleMoleculeMolGraphFeaturizer()
        points = []
        rejected: dict[str, int] = {"invalid": 0, "duplicate": 0}
        keep_ids: list[str] = []
        for r in spec.rows:
            try:
                points.append(data.MoleculeDatapoint.from_smi(r.smiles))
                keep_ids.append(r.row_id)
            except Exception:
                rejected["invalid"] += 1
        dset = data.MoleculeDataset(points, featurizer)
        loader = data.build_dataloader(
            dset, batch_size=max(len(points), 1), shuffle=False, num_workers=0
        )
        member_runs: list[list[float]] = []
        for name in sorted(n for n in model_files if n != "manifest.json"):
            # Artifacts already sit in the run scratch — the runner
            # read this same dict from disk; load them in place rather
            # than rewriting bytes (the bind mount is not rewritable).
            try:
                mpnn = models.load_model(name)
            except Exception as e:
                raise EngineFailure(
                    "ENGINE_UNSUPPORTED_INPUT",
                    "model artifact could not be loaded; no fallback prediction invented",
                ) from e
            with torch.inference_mode():
                batches = _trainer(0).predict(mpnn, loader)
            flat = [float(v) for b in batches for v in b.reshape(-1).tolist()]
            if len(flat) != len(points):
                raise EngineFailure(
                    "ENGINE_UNAVAILABLE", "engine returned a row count that does not match input"
                )
            member_runs.append(flat)
        if not member_runs:
            raise EngineFailure("ENGINE_UNSUPPORTED_INPUT", "artifact set contains no model files")
        raw: list[dict[str, Any]] = []
        for j, rid in enumerate(keep_ids):
            members = [run[j] for run in member_runs]
            raw.append({"row_id": rid, "value": sum(members) / len(members), "members": members})
        accepted, rejects = validate_predictions(keep_ids, raw, len(member_runs))
        rejected["invalid"] += rejects["invalid"]
        rejected["duplicate"] += rejects["duplicate"]
        predictions = [
            PredictionItem(
                row_id=p["row_id"],
                value=p["value"],
                members=p["members"],
                variance=_sample_variance(p["members"]),
            )
            for p in accepted
        ]
        return PredictResult(
            status="predicted" if len(predictions) == len(spec.rows) else "partial",
            predictions=predictions,
            rejected=rejected,
            model_digest=spec.model_digest,
        )


def _sample_variance(members: list[float]) -> float | None:
    n = len(members)
    if n < 2:
        return None
    mean = sum(members) / n
    return sum((m - mean) ** 2 for m in members) / (n - 1)
