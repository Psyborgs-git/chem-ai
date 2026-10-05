"""Versioned, deliberately narrow molecular-property contracts (CS-0604, §15.3).

A Chemprop fit is a *different representation* trained on the caller's
own partition — never a pretrained predictor for the user's chemistry.
Held-out labels cannot enter this contract: prediction rows have no
label field at all.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ENGINE_VERSION: Literal["2.3.1"] = "2.3.1"
ADAPTER_VERSION: Literal["chemprop-adapter/v1"] = "chemprop-adapter/v1"
REPRESENTATION: Literal["mpnn-dmpnn"] = "mpnn-dmpnn"
Number = Annotated[Decimal, Field(allow_inf_nan=False)]
RowId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:\-]{1,100}$")]
Name = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_.\-]{0,95}$")]

TRAIN_ROW_LIMIT = 20000
PREDICT_ROW_LIMIT = 512
MODEL_FILE_LIMIT = 8


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TargetScope(StrictModel):
    """The endpoint the model may answer about: name + unit + declared
    measurement-method context. A different endpoint or method is a
    different model, not a repurpose of this one."""

    name: Name
    unit: str = Field(min_length=1, max_length=64)
    method: str = Field(min_length=1, max_length=300)


class TrainRow(StrictModel):
    row_id: RowId
    smiles: Annotated[str, Field(min_length=1, max_length=512)]
    label: Number


class PredictRow(StrictModel):
    """Prediction rows never carry labels — withheld outcomes cannot
    reach the engine (§18.1)."""

    row_id: RowId
    smiles: Annotated[str, Field(min_length=1, max_length=512)]


class TrainSpec(StrictModel):
    """Everything the engine needs for one fit. Splitting is the
    caller's job (``domain/learning/splits.py``): the engine trains on
    exactly the rows supplied and never re-splits."""

    schema_version: Literal["1"] = "1"
    scope: TargetScope
    representation: Literal["mpnn-dmpnn"] = REPRESENTATION
    # Immutable representation/method context: grade, process, substrate, conditions.
    context: dict[str, str] = Field(min_length=1, max_length=30)
    rows: tuple[TrainRow, ...] = Field(min_length=1, max_length=TRAIN_ROW_LIMIT)
    seed: int = Field(ge=0, lt=2**32, strict=True)
    max_epochs: int = Field(default=30, ge=1, le=300, strict=True)
    ensemble_size: int = Field(default=4, ge=1, le=8, strict=True)
    hidden_dim: int = Field(default=300, ge=32, le=2048, strict=True)
    depth: int = Field(default=3, ge=1, le=12, strict=True)
    batch_size: int = Field(default=32, ge=1, le=1024, strict=True)

    @model_validator(mode="after")
    def support_matrix(self) -> TrainSpec:
        ids = [r.row_id for r in self.rows]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate training row ids")
        if any(len(k) > 100 or len(v) > 300 for k, v in self.context.items()):
            raise ValueError("context is bounded metadata, not free-text documents")
        return self

    def digest(self) -> str:
        import json

        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()


class PredictSpec(StrictModel):
    schema_version: Literal["1"] = "1"
    scope: TargetScope
    representation: Literal["mpnn-dmpnn"] = REPRESENTATION
    rows: tuple[PredictRow, ...] = Field(min_length=1, max_length=PREDICT_ROW_LIMIT)
    # Content digest of the train spec + artifact this prediction claims
    # lineage to — the runtime refuses a mismatched artifact.
    model_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def unique_ids(self) -> PredictSpec:
        ids = [r.row_id for r in self.rows]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate prediction row ids")
        return self


class EngineFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class TrainResult(StrictModel):
    status: Literal["trained"]
    model_files: list[str] = Field(min_length=1, max_length=MODEL_FILE_LIMIT)
    model_digest: str
    trained_rows: int
    ensemble_size: int
    epochs_ran: int
    seed: int
    representation: Literal["mpnn-dmpnn"]
    # Honest declaration: this is a fit on supplied data, not a
    # pretrained or scientifically validated predictor.
    pretrained: Literal[False] = False
    scientific_status: Literal["fixture_only", "not_validated"] = "not_validated"
    engine_version: Literal["2.3.1"] = ENGINE_VERSION
    adapter_version: Literal["chemprop-adapter/v1"] = ADAPTER_VERSION
    isolation: dict[str, Any] = Field(default_factory=dict)


class PredictionItem(StrictModel):
    row_id: RowId
    # Ensemble mean in the target's declared unit; members/variance
    # carry the engine-level disagreement, not a calibrated interval.
    value: float
    members: list[float] = Field(min_length=1, max_length=MODEL_FILE_LIMIT)
    variance: float | None = None


class PredictResult(StrictModel):
    status: Literal["predicted", "partial"]
    predictions: list[PredictionItem] = Field(max_length=PREDICT_ROW_LIMIT)
    rejected: dict[str, int]
    model_digest: str
    pretrained: Literal[False] = False
    scientific_status: Literal["fixture_only", "not_validated"] = "not_validated"
    engine_version: Literal["2.3.1"] = ENGINE_VERSION
    adapter_version: Literal["chemprop-adapter/v1"] = ADAPTER_VERSION
    isolation: dict[str, Any] = Field(default_factory=dict)
