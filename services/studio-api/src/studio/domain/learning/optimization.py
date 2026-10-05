"""Task/contract-scoped optimization. Only reviewed frozen measurement data is usable."""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from chem_studio_policy.capabilities import (
    CAP_MANAGE_MODELS,
    CAP_READ_PROJECT,
    CAP_REQUEST_COMPUTE,
    CAP_REVIEW_SCIENCE,
)
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from workers.optimization.campaign import Campaign, ReplayState
from workers.optimization.runtime import IsolatedBayBE

from engine_adapter_baybe import CampaignSpec, EngineFailure
from engine_adapter_baybe.validation import point, same_point
from studio.application.idempotency import request_digest
from studio.audit.log import record
from studio.auth.context import ServiceContext
from studio.config.settings import Settings
from studio.domain.learning.datasets import DatasetService
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import (
    DatasetSnapshot,
    Measurement,
    OptimizationCampaign,
    ResearchTask,
    SuccessContractRevision,
)


class OptimizationService:
    def __init__(self, db: Session, ctx: ServiceContext, settings: Settings) -> None:
        self.db, self.ctx, self.settings = db, ctx, settings

    def list(self, task_id: uuid.UUID) -> list[OptimizationCampaign]:
        self.ctx.require(CAP_READ_PROJECT, task_id)
        return list(
            self.db.scalars(
                select(OptimizationCampaign)
                .where(
                    OptimizationCampaign.workspace_id == self.ctx.workspace_id,
                    OptimizationCampaign.task_id == task_id,
                )
                .order_by(OptimizationCampaign.created_at.desc())
                .limit(50)
            )
        )

    def _get(self, campaign_id: uuid.UUID) -> OptimizationCampaign:
        row = self.db.scalar(
            select(OptimizationCampaign)
            .where(
                OptimizationCampaign.workspace_id == self.ctx.workspace_id,
                OptimizationCampaign.id == campaign_id,
            )
            .with_for_update()
        )
        if row is None:
            raise not_found("optimization campaign")
        return row

    def create(
        self, task_id: uuid.UUID, definition: dict[str, Any], key: str
    ) -> OptimizationCampaign:
        if self.ctx.principal_kind != "user":
            raise DomainError(ErrorCode.FORBIDDEN, "only humans can freeze a campaign definition")
        self.ctx.require(CAP_REVIEW_SCIENCE, task_id)
        self.ctx.require(CAP_MANAGE_MODELS, task_id)
        try:
            spec = CampaignSpec.model_validate(definition)
        except ValidationError as exc:
            raise DomainError(
                ErrorCode.ENGINE_UNSUPPORTED_INPUT,
                "unsupported campaign parameters/targets/constraints; nothing was dropped",
            ) from exc
        if not 1 <= len(key) <= 100:
            raise DomainError(ErrorCode.VALIDATION, "bounded idempotency key required")
        # Serialize create with the parent task lock; duplicate retries cannot create two rows.
        task = self.db.scalar(
            select(ResearchTask)
            .where(ResearchTask.id == task_id, ResearchTask.workspace_id == self.ctx.workspace_id)
            .with_for_update()
        )
        if task is None:
            raise not_found("task")
        old = self.db.scalar(
            select(OptimizationCampaign).where(
                OptimizationCampaign.workspace_id == self.ctx.workspace_id,
                OptimizationCampaign.task_id == task_id,
                OptimizationCampaign.creation_key == key,
            )
        )
        if old:
            if old.spec_digest != spec.digest():
                raise DomainError(
                    ErrorCode.IDEMPOTENCY_MISMATCH,
                    "creation key reused with a different definition",
                )
            return old
        if task.workflow_state != "active":
            raise DomainError(ErrorCode.CONFLICT, "campaign creation requires an active task")
        contract = (
            self.db.get(SuccessContractRevision, task.current_contract_revision_id)
            if task.current_contract_revision_id
            else None
        )
        if (
            not contract
            or contract.workspace_id != self.ctx.workspace_id
            or contract.status != "frozen"
        ):
            raise DomainError(
                ErrorCode.CONFLICT, "optimization requires a frozen task success contract"
            )
        metrics = contract.payload.get("metrics", [])
        if contract.payload.get("hard_constraints"):
            raise DomainError(
                ErrorCode.ENGINE_UNSUPPORTED_INPUT,
                "contract-level hard constraints need a reviewed mapping; none were dropped",
            )
        matching = [
            m
            for m in metrics
            if (
                m.get("id") == spec.target.name
                and m.get("unit") == spec.target.unit
                and str(m.get("method_revision_id")) == spec.target.method
            )
        ]
        if len(matching) != 1 or matching[0].get("value_kind") != "numeric":
            raise DomainError(
                ErrorCode.VALIDATION,
                "target metric, unit and method must match the pinned contract",
            )
        definition = matching[0]
        operator = str(definition.get("operator", ""))
        compatible_mode = {
            "gte": "maximize",
            "lte": "minimize",
            "eq": "match",
            "between": "match",
        }.get(operator)
        if spec.target.mode != compatible_mode:
            raise DomainError(
                ErrorCode.ENGINE_UNSUPPORTED_INPUT,
                "target direction lacks a reviewed contract mapping",
            )
        if spec.target.mode == "match":
            cutoffs = spec.target.match_bounds
            values = [Decimal(v) for v in definition.get("target_values", [])]
            if (
                not cutoffs
                or (operator == "between" and tuple(values) != cutoffs)
                or (operator == "eq" and (len(values) != 1 or sum(cutoffs) / 2 != values[0]))
            ):
                raise DomainError(
                    ErrorCode.ENGINE_UNSUPPORTED_INPUT,
                    "match transformation conflicts with frozen metric thresholds",
                )
        row = OptimizationCampaign(
            workspace_id=self.ctx.workspace_id,
            task_id=task_id,
            contract_revision_id=contract.id,
            definition=spec.model_dump(mode="json"),
            spec_digest=spec.digest(),
            replay=Campaign(spec).state.model_dump(mode="json"),
            revision=1,
            creation_key=key,
            commands={},
            created_by=self.ctx.principal_id,
        )
        self.db.add(row)
        self.db.flush()
        record(
            self.db,
            self.ctx,
            action="optimization.created",
            target_type="optimization_campaign",
            target_id=row.id,
        )
        return row

    def _load(self, row: OptimizationCampaign) -> Campaign:
        try:
            campaign = Campaign(
                CampaignSpec.model_validate(row.definition), ReplayState.model_validate(row.replay)
            )
        except (ValueError, ValidationError) as exc:
            raise DomainError(
                ErrorCode.CONFLICT, "campaign replay state failed version/definition checks"
            ) from exc
        task = self.db.get(ResearchTask, row.task_id)
        if (
            not task
            or task.current_contract_revision_id != row.contract_revision_id
            or task.workflow_state != "active"
        ):
            raise DomainError(
                ErrorCode.CONFLICT,
                "campaign task is inactive or contract changed; create a new campaign version",
            )
        # Recheck rights/provenance on every request; stale labels never silently train a GP.
        for e in campaign.state.experiments:
            if e.status == "observed":
                self._measurement(
                    row,
                    campaign,
                    e.id,
                    uuid.UUID(e.measurement_id or ""),
                    uuid.UUID(e.snapshot_id or ""),
                    expected_hash=e.source_hash,
                )
        return campaign

    def _measurement(
        self,
        row: OptimizationCampaign,
        campaign: Campaign,
        experiment_id: str,
        measurement_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        *,
        expected_hash: str | None = None,
    ) -> tuple[str, str]:
        ds = DatasetService(self.db, self.ctx)
        report = ds.prepare_run(snapshot_id)
        snap = self.db.get(DatasetSnapshot, snapshot_id)
        if (
            not report["ok"]
            or not snap
            or snap.task_id != row.task_id
            or snap.purpose != "property_prediction"
        ):
            raise DomainError(
                ErrorCode.EVAL_CONTAMINATION,
                "frozen task property dataset has drifted or is incompatible",
            )
        entry = next(
            (
                e
                for e in snap.manifest["entries"]
                if e["recordId"] == str(measurement_id)
                and not e["excluded"]
                and e["recordKind"] == "measurement"
                and e["rightsTraining"] in {"owned", "allowed"}
            ),
            None,
        )
        m = self.db.scalar(
            select(Measurement).where(
                Measurement.id == measurement_id, Measurement.workspace_id == self.ctx.workspace_id
            )
        )
        if (
            not entry
            or not m
            or m.status != "accepted"
            or not m.reviewed_by
            or not m.applicable
            or m.superseded_by
            or m.value_type != "numeric"
        ):
            raise DomainError(
                ErrorCode.VALIDATION,
                "observations require reviewed applicable numeric measurements with frozen rights",
            )
        target = campaign.spec.target
        if (
            m.metric != target.name
            or m.method != target.method
            or m.value.get("unit") != target.unit
        ):
            raise DomainError(
                ErrorCode.VALIDATION, "measurement metric/method/unit differs from campaign target"
            )
        actual = m.conditions.get("actual", {}).get("optimization", {})
        experiment = next((e for e in campaign.state.experiments if e.id == experiment_id), None)
        try:
            measured_point = point(campaign.spec, actual.get("parameters", {}))
            if (
                not experiment
                or not same_point(campaign.spec, experiment.parameters, measured_point)
                or actual.get("context") != campaign.spec.context
                or actual.get("campaignId") != str(row.id)
                or actual.get("experimentId") != experiment_id
            ):
                raise ValueError("measurement identity mismatch")
            value = Decimal(str(m.value["value"]))
            if not value.is_finite() or (expected_hash and entry["hash"] != expected_hash):
                raise ValueError("nonfinite or changed observation")
        except (ValueError, KeyError, InvalidOperation) as exc:
            raise DomainError(
                ErrorCode.VALIDATION,
                "reviewed actual optimization identity/outcome does not match the suggestion",
            ) from exc
        return str(value), str(entry["hash"])

    def command(
        self,
        campaign_id: uuid.UUID,
        *,
        expected_revision: int,
        key: str,
        operation: Literal["recommend", "cancelled", "failed", "observed"],
        batch_size: int = 1,
        experiment_id: str | None = None,
        measurement_id: uuid.UUID | None = None,
        snapshot_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> OptimizationCampaign:
        row = self._get(campaign_id)
        if operation != "recommend" and self.ctx.principal_kind != "user":
            raise DomainError(
                ErrorCode.FORBIDDEN,
                "only humans can record campaign lifecycle decisions",
            )
        self.ctx.require(
            CAP_REQUEST_COMPUTE if operation == "recommend" else CAP_REVIEW_SCIENCE, row.task_id
        )
        self.ctx.require(CAP_MANAGE_MODELS, row.task_id)
        digest = request_digest(
            {
                "operation": operation,
                "batchSize": batch_size,
                "experimentId": experiment_id,
                "measurementId": str(measurement_id),
                "snapshotId": str(snapshot_id),
                "reason": reason,
            }
        )
        if not 1 <= len(key) <= 100:
            raise DomainError(ErrorCode.VALIDATION, "idempotency envelope exceeded")
        if key in row.commands:
            if row.commands[key] != digest:
                raise DomainError(
                    ErrorCode.IDEMPOTENCY_MISMATCH, "command key reused with changed parameters"
                )
            return row
        if len(row.commands) >= 1000:
            raise DomainError(ErrorCode.VALIDATION, "idempotency envelope exceeded")
        if row.revision != expected_revision:
            raise DomainError(
                ErrorCode.REVISION_CONFLICT, "campaign revision changed; reload before retrying"
            )
        campaign = self._load(row)
        try:
            if operation == "recommend":
                if experiment_id or measurement_id or snapshot_id or reason:
                    raise ValueError("recommend cannot submit outcomes or lifecycle edits")
                if not self.settings.profile_optimization:
                    raise DomainError(
                        ErrorCode.ENGINE_UNAVAILABLE, "optimization profile is disabled"
                    )
                campaign.recommend(IsolatedBayBE(), batch_size)
            else:
                if not experiment_id:
                    raise ValueError("experiment id required")
                outcome, source_hash = None, None
                if operation == "observed":
                    if not measurement_id or not snapshot_id:
                        raise ValueError("observation requires measurement and frozen snapshot ids")
                    outcome, source_hash = self._measurement(
                        row, campaign, experiment_id, measurement_id, snapshot_id
                    )
                elif measurement_id or snapshot_id:
                    raise ValueError("cancelled/failed is not an observation")
                campaign.transition(
                    experiment_id,
                    operation,
                    outcome=outcome,
                    measurement_id=str(measurement_id) if measurement_id else None,
                    snapshot_id=str(snapshot_id) if snapshot_id else None,
                    source_hash=source_hash,
                    reason=reason,
                )
        except EngineFailure as exc:
            raise DomainError(ErrorCode(exc.code), exc.message) from exc
        except (ValueError, ValidationError) as exc:
            raise DomainError(ErrorCode.VALIDATION, str(exc)) from exc
        row.replay = campaign.state.model_dump(mode="json")
        row.commands = {**row.commands, key: digest}
        row.revision += 1
        self.db.flush()
        record(
            self.db,
            self.ctx,
            action=f"optimization.{operation}",
            target_type="optimization_campaign",
            target_id=row.id,
            detail={"revision": row.revision},
        )
        return row


def public_state(row: OptimizationCampaign) -> dict[str, Any]:
    # No engine/pickle state, vault paths or credentials cross GraphQL.
    return {
        "definition": row.definition,
        "specDigest": row.spec_digest,
        "state": row.replay,
        "scientificStatus": (
            "fixture_only"
            if row.definition.get("context", {}).get("fixture_only") == "true"
            else "not_validated"
        ),
        "capabilityStatus": "engine_smoke_passed" if row.replay.get("history") else "configured",
    }
