"""Durable JSON-only campaign replay/lifecycle. Suggestions confer no approvals."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Literal, Protocol

from pydantic import Field

from engine_adapter_baybe.contracts import (
    ADAPTER_VERSION,
    ENGINE_VERSION,
    IDENTITY_VERSION,
    CampaignSpec,
    Recommendation,
    StrictModel,
)
from engine_adapter_baybe.validation import point, same_point, validate_batch


class Experiment(StrictModel):
    id: str
    parameters: dict[str, str]
    status: Literal["pending", "observed", "cancelled", "failed"] = "pending"
    outcome: str | None = None
    measurement_id: str | None = None
    snapshot_id: str | None = None
    source_hash: str | None = None
    reason: str | None = None


class ReplayState(StrictModel):
    schema_version: Literal["1"] = "1"
    engine_version: Literal["0.15.0"] = ENGINE_VERSION
    adapter_version: Literal["baybe-adapter/v1"] = ADAPTER_VERSION
    identity_version: Literal["parameter-context/decimal-distance-v1"] = IDENTITY_VERSION
    spec_digest: str
    request_index: int = Field(default=0, ge=0, lt=2**32, strict=True)
    experiments: tuple[Experiment, ...] = Field(default=(), max_length=5000)
    history: tuple[dict[str, Any], ...] = Field(default=(), max_length=1000)


class Adapter(Protocol):
    def recommend(
        self,
        spec: CampaignSpec,
        *,
        batch_size: int,
        request_index: int,
        observations: list[dict[str, str]],
        reserved: list[dict[str, str]],
        pending: list[dict[str, str]],
    ) -> Recommendation: ...


class Campaign:
    def __init__(self, spec: CampaignSpec, state: ReplayState | None = None) -> None:
        self.spec = spec
        self.state = state or ReplayState(spec_digest=spec.digest())
        if self.state.spec_digest != spec.digest():
            raise ValueError("campaign definition changed; create a new campaign version")
        ids: set[str] = set()
        points: list[dict[str, str]] = []
        measurements: set[str] = set()
        for e in self.state.experiments:
            p = point(spec, e.parameters)
            if e.id in ids or any(same_point(spec, p, q) for q in points):
                raise ValueError("duplicate experiment identity in replay state")
            if e.status == "observed":
                if not e.outcome or not e.measurement_id or not e.snapshot_id or not e.source_hash:
                    raise ValueError("observed experiment requires reviewed measurement provenance")
                if not Decimal(e.outcome).is_finite() or e.measurement_id in measurements:
                    raise ValueError("invalid or duplicated measurement outcome")
                measurements.add(e.measurement_id)
            elif e.outcome is not None or e.measurement_id is not None:
                raise ValueError("pending/cancelled/failed experiments cannot be outcomes")
            ids.add(e.id)
            points.append(p)

    def recommend(self, adapter: Adapter, batch_size: int) -> Recommendation:
        if isinstance(batch_size, bool) or not 1 <= batch_size <= 16:
            raise ValueError("bounded recommendation batch must be 1..16")
        if len(self.state.experiments) + batch_size > 5000 or len(self.state.history) >= 1000:
            raise ValueError("campaign resource envelope exhausted; create a new version")
        es = self.state.experiments
        result = adapter.recommend(
            self.spec,
            batch_size=batch_size,
            request_index=self.state.request_index,
            observations=[
                {**e.parameters, self.spec.target.name: e.outcome}
                for e in es
                if e.status == "observed" and e.outcome is not None
            ],
            reserved=[e.parameters for e in es],
            pending=[e.parameters for e in es if e.status == "pending"],
        )
        if len(result.suggestions) > batch_size:
            raise ValueError("engine returned more than requested bounded batch")
        accepted, rejected = validate_batch(
            self.spec, result.suggestions, [e.parameters for e in es]
        )
        if any(rejected.values()):
            raise ValueError("worker output failed controller-side independent validation")
        new = tuple(Experiment(id=str(uuid.uuid4()), parameters=p) for p in accepted)
        history = {
            "requestIndex": self.state.request_index,
            "batchSize": batch_size,
            "seed": self.spec.seed,
            "effectiveSeed": (self.spec.seed + self.state.request_index) % 2**32,
            "status": result.status,
            "rejected": result.rejected,
            "recommender": result.recommender,
            "acquisition": result.acquisition,
            "isolation": result.isolation,
            "suggestionIds": [e.id for e in new],
        }
        self.state = self.state.model_copy(
            update={
                "experiments": (*es, *new),
                "request_index": self.state.request_index + 1,
                "history": (*self.state.history, history),
            }
        )
        return result

    def transition(
        self,
        experiment_id: str,
        status: Literal["observed", "cancelled", "failed"],
        *,
        outcome: str | None = None,
        measurement_id: str | None = None,
        snapshot_id: str | None = None,
        source_hash: str | None = None,
        reason: str | None = None,
    ) -> None:
        if status not in {"observed", "cancelled", "failed"}:
            raise ValueError("unsupported lifecycle state")
        e = next((e for e in self.state.experiments if e.id == experiment_id), None)
        if e is None:
            raise ValueError("unknown experiment")
        if status != "observed" and any(
            v is not None for v in (outcome, measurement_id, snapshot_id, source_hash)
        ):
            raise ValueError("cancelled/failed experiments are not zero outcomes")
        replacement = e.model_copy(
            update={
                "status": status,
                "outcome": outcome,
                "measurement_id": measurement_id,
                "snapshot_id": snapshot_id,
                "source_hash": source_hash,
                "reason": reason,
            }
        )
        if e == replacement:
            return
        if e.status != "pending":
            raise ValueError(
                "terminal experiment is immutable; create a new campaign for corrections"
            )
        if status in {"cancelled", "failed"} and (
            not reason or not reason.strip() or len(reason) > 1000
        ):
            raise ValueError("cancellation/failure requires a reason")
        changed = self.state.model_copy(
            update={
                "experiments": tuple(
                    replacement if x.id == e.id else x for x in self.state.experiments
                )
            }
        )
        Campaign(self.spec, changed)
        self.state = changed
