"""Samples, executions and measurement review (§6.3, §14.2, CS-0502).

Manual-first recording: an approved plan opens a ``LabExecution``;
the operator records actual materials/lots, deviations and
observations. Executions contain independent preparation *batches*;
batches yield *samples*; samples carry *measurements* with typed
value payloads and explicit repeat semantics — three readings of one
aliquot are ``same_sample`` repeats, never three independent batches
(AT-0502-1).

Measurements are reviewed for integrity and — separately — for
applicability to the original contract: a deviated measurement stays
scientifically useful while flagged inapplicable (§14.2). Correction
happens only through an amendment record; the original row keeps its
value and is marked ``superseded`` (AT-0502-3). Contract comparison
converts only whitelisted same-category units — an incompatible
unit/method yields ``inconclusive`` with an actionable finding, never
a forced verdict (§6.1, AT-0502-2).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from chem_studio_policy.capabilities import (
    CAP_EDIT_TASK,
    CAP_READ_PROJECT,
    CAP_REVIEW_MEASUREMENT,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext
from studio.domain.lab.plans import LabPlanService

# units shared with the task evaluator (§6.1): units.py holds the
# single whitelist/conversion table — both surfaces must agree.
from studio.domain.lab.units import (
    _UNIT_CATEGORY,
)
from studio.domain.lab.units import (
    convert as _convert,
)
from studio.domain.lab.units import (
    parse_target as _parse_target,
)
from studio.domain.lab.units import (
    to_decimal as _decimal,
)
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import (
    MEASUREMENT_VALUE_TYPES,
    MISSING_REASONS,
    REPEAT_TYPES,
    SAMPLE_KINDS,
    CandidateRevision,
    EvidenceApplicability,
    ExperimentPlan,
    LabBatch,
    LabExecution,
    LabSample,
    Measurement,
    MeasurementAmendment,
    ResearchTask,
    SuccessContractRevision,
)


def _validate_value(value_type: str, value: dict[str, Any]) -> None:
    """Typed value payload checks (§6.3) — nothing may be invented."""
    if not isinstance(value, dict):
        raise DomainError(ErrorCode.VALIDATION, "value must be an object")
    kind = value.get("kind", value_type)
    if kind != value_type:
        raise DomainError(
            ErrorCode.VALIDATION, "value.kind must match value_type", field_path="value.kind"
        )
    if kind == "numeric":
        if value.get("value") in (None, "") or not value.get("unit"):
            raise DomainError(
                ErrorCode.VALIDATION,
                "numeric value requires 'value' (decimal string) and 'unit'",
                field_path="value",
            )
        _decimal(value["value"])
    elif kind == "interval":
        if not value.get("unit") or value.get("low") is None or value.get("high") is None:
            raise DomainError(
                ErrorCode.VALIDATION,
                "interval requires 'low', 'high' and 'unit'",
                field_path="value",
            )
        if _decimal(value["low"]) > _decimal(value["high"]):
            raise DomainError(ErrorCode.VALIDATION, "interval low exceeds high", field_path="value")
    elif kind in ("below_detection", "above_quantification"):
        if value.get("limit") in (None, "") or not value.get("unit"):
            raise DomainError(
                ErrorCode.VALIDATION,
                f"{kind} requires 'limit' and 'unit'",
                field_path="value",
            )
        _decimal(value["limit"])
    elif kind == "ordinal":
        scale = value.get("scale")
        if not value.get("label") or not isinstance(scale, list) or value["label"] not in scale:
            raise DomainError(
                ErrorCode.VALIDATION,
                "ordinal requires 'label' within 'scale'",
                field_path="value",
            )
    elif kind == "categorical":
        if not value.get("label"):
            raise DomainError(
                ErrorCode.VALIDATION, "categorical requires 'label'", field_path="value"
            )
    elif kind == "missing":
        if value.get("reason") not in MISSING_REASONS:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"missing requires reason in {MISSING_REASONS}",
                field_path="value.reason",
            )


class LabMeasurementService:
    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    # ---------------------------------------------------------- executions

    def open_execution(self, plan_id: uuid.UUID) -> LabExecution:
        """Open a manual execution for an approved plan — the release
        approval is re-verified at open time, so a stale approval
        blocks recording just as it blocks packet export."""
        plan = self._plan(plan_id)
        task = self._task(plan.task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if plan.status != "approved":
            raise DomainError(ErrorCode.CONFLICT, "only an approved plan can be executed")
        LabPlanService(self.db, self.ctx).verify_release_approval(plan)
        ex = LabExecution(
            workspace_id=self.ctx.workspace_id,
            plan_id=plan.id,
            task_id=plan.task_id,
            status="in_progress",
            opened_by=self.ctx.principal_id,
        )
        self.db.add(ex)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="lab_execution.opened",
            target_type="lab_execution",
            target_id=ex.id,
            detail={"planId": str(plan.id)},
        )
        return ex

    def import_historical(self, task_id: uuid.UUID, *, payload: dict[str, Any]) -> LabExecution:
        """Historical experiments may be recorded without preapproval —
        they are marked ``historical`` and can never claim a release
        approval (§14.1)."""
        task = self._task(task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        ex = LabExecution(
            workspace_id=self.ctx.workspace_id,
            plan_id=None,
            task_id=task_id,
            status="in_progress",
            historical=True,
            actual=dict(payload),
            opened_by=self.ctx.principal_id,
        )
        self.db.add(ex)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="lab_execution.historical_import",
            target_type="lab_execution",
            target_id=ex.id,
            detail={"taskId": str(task_id)},
        )
        return ex

    def record_actuals(
        self,
        execution_id: uuid.UUID,
        *,
        actual: dict[str, Any] | None = None,
        deviations: list[dict[str, Any]] | None = None,
        observations: str | None = None,
    ) -> LabExecution:
        ex = self._execution(execution_id)
        self.ctx.require(CAP_EDIT_TASK, self._execution_project(ex))
        if ex.status != "in_progress":
            raise DomainError(ErrorCode.CONFLICT, "execution is closed")
        if actual is not None:
            ex.actual = dict(actual)
        if deviations is not None:
            ex.deviations = list(deviations)
        if observations is not None:
            ex.observations = observations
        self.db.flush()
        return ex

    def close_execution(
        self, execution_id: uuid.UUID, *, status: str = "completed"
    ) -> LabExecution:
        ex = self._execution(execution_id)
        self.ctx.require(CAP_EDIT_TASK, self._execution_project(ex))
        if status not in ("completed", "stopped"):
            raise DomainError(ErrorCode.VALIDATION, "status must be completed|stopped")
        if ex.status != "in_progress":
            raise DomainError(ErrorCode.CONFLICT, "execution is already closed")
        ex.status = status
        ex.closed_at = datetime.now(UTC)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="lab_execution.closed",
            target_type="lab_execution",
            target_id=ex.id,
            detail={"status": status},
        )
        return ex

    def list_executions(self, plan_id: uuid.UUID) -> list[LabExecution]:
        plan = self._plan(plan_id)
        self.ctx.require(CAP_READ_PROJECT, self._task(plan.task_id).project_id)
        return list(
            self.db.execute(
                select(LabExecution).where(
                    LabExecution.workspace_id == self.ctx.workspace_id,
                    LabExecution.plan_id == plan_id,
                )
            ).scalars()
        )

    # ---------------------------------------------------------- batches / samples

    def add_batch(
        self, execution_id: uuid.UUID, *, label: str, payload: dict[str, Any] | None = None
    ) -> LabBatch:
        ex = self._execution(execution_id)
        self.ctx.require(CAP_EDIT_TASK, self._execution_project(ex))
        if ex.status != "in_progress":
            raise DomainError(ErrorCode.CONFLICT, "execution is closed")
        if not label.strip():
            raise DomainError(ErrorCode.VALIDATION, "batch label required")
        batch = LabBatch(
            workspace_id=self.ctx.workspace_id,
            execution_id=execution_id,
            label=label.strip(),
            payload=dict(payload or {}),
        )
        self.db.add(batch)
        self.db.flush()
        return batch

    def add_sample(
        self,
        batch_id: uuid.UUID,
        *,
        label: str,
        kind: str = "aliquot",
        payload: dict[str, Any] | None = None,
    ) -> LabSample:
        batch = self._batch(batch_id)
        self.ctx.require(
            CAP_EDIT_TASK,
            self._execution_project(self._execution(batch.execution_id)),
        )
        if kind not in SAMPLE_KINDS:
            raise DomainError(ErrorCode.VALIDATION, f"kind must be in {SAMPLE_KINDS}")
        if not label.strip():
            raise DomainError(ErrorCode.VALIDATION, "sample label required")
        sample = LabSample(
            workspace_id=self.ctx.workspace_id,
            batch_id=batch_id,
            label=label.strip(),
            kind=kind,
            payload=dict(payload or {}),
        )
        self.db.add(sample)
        self.db.flush()
        return sample

    # ---------------------------------------------------------- measurements

    def record_measurement(
        self,
        sample_id: uuid.UUID,
        *,
        method: str,
        repeat_type: str,
        value: dict[str, Any],
        metric: str | None = None,
        value_type: str | None = None,
        conditions: dict[str, Any] | None = None,
        pipeline_version: str | None = None,
    ) -> Measurement:
        sample = self._sample(sample_id)
        batch = self._batch(sample.batch_id)
        ex = self._execution(batch.execution_id)
        self.ctx.require(CAP_EDIT_TASK, self._execution_project(ex))
        if ex.status != "in_progress":
            raise DomainError(ErrorCode.CONFLICT, "execution is closed")
        if not method.strip():
            raise DomainError(ErrorCode.VALIDATION, "method is required", field_path="method")
        if repeat_type not in REPEAT_TYPES:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"repeat_type must be in {REPEAT_TYPES}",
                field_path="repeatType",
            )
        vtype = value_type or (value.get("kind") if isinstance(value, dict) else None)
        if vtype not in MEASUREMENT_VALUE_TYPES:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"value_type must be in {MEASUREMENT_VALUE_TYPES}",
                field_path="valueType",
            )
        _validate_value(vtype, value)
        m = Measurement(
            workspace_id=self.ctx.workspace_id,
            sample_id=sample_id,
            method=method.strip(),
            metric=metric.strip() if metric else None,
            repeat_type=repeat_type,
            value_type=vtype,
            value=dict(value),
            conditions=dict(conditions or {}),
            pipeline_version=pipeline_version,
            created_by=self.ctx.principal_id,
        )
        self.db.add(m)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="measurement.recorded",
            target_type="measurement",
            target_id=m.id,
            detail={"sampleId": str(sample_id), "repeatType": repeat_type},
        )
        return m

    def review(
        self, measurement_id: uuid.UUID, *, decision: str, note: str | None = None
    ) -> Measurement:
        m = self._measurement(measurement_id)
        self.ctx.require(CAP_REVIEW_MEASUREMENT, self._measurement_project(m))
        if decision not in ("accepted", "rejected"):
            raise DomainError(ErrorCode.VALIDATION, "decision must be accepted|rejected")
        if m.status not in ("proposed",):
            raise DomainError(ErrorCode.CONFLICT, f"measurement in '{m.status}' cannot be reviewed")
        m.status = decision
        m.review_note = note
        m.reviewed_by = self.ctx.principal_id
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="measurement.reviewed",
            target_type="measurement",
            target_id=m.id,
            detail={"decision": decision},
        )
        return m

    def set_applicability(
        self, measurement_id: uuid.UUID, *, applicable: bool, note: str | None = None
    ) -> Measurement:
        """Integrity vs applicability are separate axes (§14.2): a
        deviated measurement may be accepted as raw yet inapplicable to
        the original contract."""
        m = self._measurement(measurement_id)
        self.ctx.require(CAP_REVIEW_MEASUREMENT, self._measurement_project(m))
        m.applicable = applicable
        m.applicability_note = note
        self.db.flush()
        return m

    def amend(
        self,
        measurement_id: uuid.UUID,
        *,
        reason: str,
        source: str | None = None,
        value: dict[str, Any],
        conditions: dict[str, Any] | None = None,
    ) -> MeasurementAmendment:
        """Correct an accepted measurement via amendment (§14.2,
        AT-0502-3): the original row keeps its value and flips to
        ``superseded`` — never overwritten."""
        m = self._measurement(measurement_id)
        self.ctx.require(CAP_REVIEW_MEASUREMENT, self._measurement_project(m))
        if m.status != "accepted":
            raise DomainError(ErrorCode.CONFLICT, "only an accepted measurement can be amended")
        if not reason.strip():
            raise DomainError(
                ErrorCode.VALIDATION, "amendment reason required", field_path="reason"
            )
        _validate_value(m.value_type, value)
        amd = MeasurementAmendment(
            workspace_id=self.ctx.workspace_id,
            measurement_id=m.id,
            reason=reason.strip(),
            source=source,
            value=dict(value),
            conditions=dict(conditions or {}),
            created_by=self.ctx.principal_id,
        )
        self.db.add(amd)
        self.db.flush()
        m.status = "superseded"
        m.superseded_by = amd.id
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="measurement.amended",
            target_type="measurement",
            target_id=m.id,
            detail={"amendmentId": str(amd.id), "reason": reason.strip()},
        )
        return amd

    def record_applicability(
        self,
        measurement_id: uuid.UUID,
        *,
        candidate_revision_id: uuid.UUID,
        contract_revision_id: uuid.UUID | None = None,
        applicable: bool,
        rationale: str,
    ) -> EvidenceApplicability:
        """Reviewed evidence→candidate applicability mapping (§12.3,
        PAR-02 §4): the only way evidence without plan/sample lineage
        — historical imports above all — can substantiate a specific
        candidate revision. ``applicable=False`` records the reviewed
        refusal; it never silently participates again. Re-recording a
        pair updates the same row (the unique pair) so the decision
        history stays one row, and a withdrawn mapping can be
        re-reviewed."""
        m = self._measurement(measurement_id)
        self.ctx.require(CAP_REVIEW_MEASUREMENT, self._measurement_project(m))
        if not rationale.strip():
            raise DomainError(
                ErrorCode.VALIDATION,
                "applicability mapping requires a rationale",
                field_path="rationale",
            )
        cand = self.db.execute(
            select(CandidateRevision).where(
                CandidateRevision.workspace_id == self.ctx.workspace_id,
                CandidateRevision.id == candidate_revision_id,
            )
        ).scalar_one_or_none()
        if cand is None:
            raise DomainError(
                ErrorCode.NOT_FOUND,
                "candidate revision not found",
                field_path="candidateRevisionId",
            )
        if contract_revision_id is not None:
            contract = self.db.execute(
                select(SuccessContractRevision).where(
                    SuccessContractRevision.workspace_id == self.ctx.workspace_id,
                    SuccessContractRevision.id == contract_revision_id,
                )
            ).scalar_one_or_none()
            if contract is None:
                raise DomainError(
                    ErrorCode.NOT_FOUND,
                    "contract revision not found",
                    field_path="contractRevisionId",
                )
        row = self.db.execute(
            select(EvidenceApplicability).where(
                EvidenceApplicability.workspace_id == self.ctx.workspace_id,
                EvidenceApplicability.measurement_id == m.id,
                EvidenceApplicability.candidate_revision_id == cand.id,
            )
        ).scalar_one_or_none()
        if row is None:
            row = EvidenceApplicability(
                workspace_id=self.ctx.workspace_id,
                measurement_id=m.id,
                candidate_revision_id=cand.id,
            )
            self.db.add(row)
        row.contract_revision_id = contract_revision_id
        row.status = "applicable" if applicable else "not_applicable"
        row.rationale = rationale.strip()
        row.reviewed_by = self.ctx.principal_id
        row.revoked_at = None
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="evidence.applicability_recorded",
            target_type="evidence_applicability",
            target_id=row.id,
            detail={
                "measurementId": str(m.id),
                "candidateRevisionId": str(cand.id),
                "contractRevisionId": str(contract_revision_id)
                if contract_revision_id
                else None,
                "status": row.status,
            },
        )
        return row

    def withdraw_applicability(
        self, measurement_id: uuid.UUID, *, candidate_revision_id: uuid.UUID
    ) -> EvidenceApplicability:
        """Withdraw a reviewed mapping (PAR-02 §6): the row is kept as
        review history; evaluators treat it as absent and the change
        marks dependent packets for reassessment."""
        m = self._measurement(measurement_id)
        self.ctx.require(CAP_REVIEW_MEASUREMENT, self._measurement_project(m))
        row = self.db.execute(
            select(EvidenceApplicability).where(
                EvidenceApplicability.workspace_id == self.ctx.workspace_id,
                EvidenceApplicability.measurement_id == m.id,
                EvidenceApplicability.candidate_revision_id == candidate_revision_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("applicability mapping")
        row.revoked_at = datetime.now(UTC)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="evidence.applicability_withdrawn",
            target_type="evidence_applicability",
            target_id=row.id,
            detail={
                "measurementId": str(m.id),
                "candidateRevisionId": str(candidate_revision_id),
            },
        )
        return row

    # ---------------------------------------------------------- assessment

    def replication_summary(self, execution_id: uuid.UUID) -> dict[str, Any]:
        """Repeat-type-aware replication accounting (§6.3, AT-0502-1):
        independent batches count once per batch — same-aliquot
        readings are observations, not independent trials."""
        ex = self._execution(execution_id)
        self.ctx.require(CAP_READ_PROJECT, self._execution_project(ex))
        batches = list(
            self.db.execute(
                select(LabBatch).where(
                    LabBatch.workspace_id == self.ctx.workspace_id,
                    LabBatch.execution_id == execution_id,
                )
            ).scalars()
        )
        by_repeat: dict[str, int] = {t: 0 for t in REPEAT_TYPES}
        observations = 0
        samples = 0
        for batch in batches:
            sample_rows = list(
                self.db.execute(
                    select(LabSample).where(
                        LabSample.workspace_id == self.ctx.workspace_id,
                        LabSample.batch_id == batch.id,
                    )
                ).scalars()
            )
            samples += len(sample_rows)
            for s in sample_rows:
                for m in self.db.execute(
                    select(Measurement).where(
                        Measurement.workspace_id == self.ctx.workspace_id,
                        Measurement.sample_id == s.id,
                    )
                ).scalars():
                    observations += 1
                    by_repeat[m.repeat_type] = by_repeat.get(m.repeat_type, 0) + 1
        return {
            "independentBatches": len(batches),
            "samples": samples,
            "observations": observations,
            "byRepeatType": by_repeat,
            "note": (
                "independent batches are the replication unit; same_sample/"
                "timepoint readings on one batch are repeated observations"
            ),
        }

    def compare_to_contract(
        self, measurement_id: uuid.UUID, metric: dict[str, Any]
    ) -> dict[str, Any]:
        """Compare a measurement against one contract metric
        (§6.1/§14.2, AT-0502-2). Incompatible unit/method/value type →
        ``inconclusive`` with an actionable finding; never a forced
        pass/fail."""
        m = self._measurement(measurement_id)
        self.ctx.require(CAP_READ_PROJECT, self._measurement_project(m))
        name = str(metric.get("name") or "")
        op, target_val, target_unit = _parse_target(str(metric.get("target") or ""))
        findings: list[dict[str, str]] = []

        if m.status == "superseded":
            findings.append(
                {
                    "kind": "superseded",
                    "text": "measurement superseded — compare the amendment value",
                    "action": "compare_latest",
                }
            )
            return {"verdict": "inconclusive", "metric": name, "findings": findings}
        if m.value_type != "numeric":
            findings.append(
                {
                    "kind": "value_type",
                    "text": f"value type '{m.value_type}' is not a numeric comparison input",
                    "action": "provide_numeric_measurement",
                }
            )
            return {"verdict": "inconclusive", "metric": name, "findings": findings}

        value = _decimal(m.value["value"])
        unit = str(m.value.get("unit") or "")
        if target_unit is None:
            findings.append(
                {
                    "kind": "unit_missing",
                    "text": "contract target carries no unit — comparison is not safe",
                    "action": "add_target_unit",
                }
            )
            return {"verdict": "inconclusive", "metric": name, "findings": findings}
        if (
            _UNIT_CATEGORY.get(unit) != _UNIT_CATEGORY.get(target_unit)
            or unit not in _UNIT_CATEGORY
        ):
            findings.append(
                {
                    "kind": "unit_incompatible",
                    "text": (
                        f"measurement unit '{unit}' is not comparable to target "
                        f"unit '{target_unit}' — remeasure with a compatible method "
                        "or supply a reviewed conversion (§6.1)"
                    ),
                    "action": "remeasure_or_review_conversion",
                }
            )
            return {"verdict": "inconclusive", "metric": name, "findings": findings}
        converted = _convert(value, unit, target_unit)
        if converted is None:
            findings.append(
                {
                    "kind": "conversion_missing",
                    "text": f"no whitelisted conversion {unit} → {target_unit}",
                    "action": "remeasure_or_review_conversion",
                }
            )
            return {"verdict": "inconclusive", "metric": name, "findings": findings}

        ok = {
            ">=": converted >= target_val,
            "<=": converted <= target_val,
            ">": converted > target_val,
            "<": converted < target_val,
            "=": converted == target_val,
        }[op]
        return {
            "verdict": "pass" if ok else "fail",
            "metric": name,
            "comparedValue": str(converted),
            "targetUnit": target_unit,
            "converted": unit != target_unit,
            "findings": findings,
        }

    # ---------------------------------------------------------- internals

    def _task(self, task_id: uuid.UUID) -> ResearchTask:
        task = self.db.execute(
            select(ResearchTask).where(
                ResearchTask.workspace_id == self.ctx.workspace_id,
                ResearchTask.id == task_id,
            )
        ).scalar_one_or_none()
        if task is None:
            raise not_found("task")
        return task

    def _plan(self, plan_id: uuid.UUID) -> ExperimentPlan:
        plan = self.db.execute(
            select(ExperimentPlan).where(
                ExperimentPlan.workspace_id == self.ctx.workspace_id,
                ExperimentPlan.id == plan_id,
            )
        ).scalar_one_or_none()
        if plan is None:
            raise not_found("experiment plan")
        return plan

    def _execution(self, execution_id: uuid.UUID) -> LabExecution:
        ex = self.db.execute(
            select(LabExecution).where(
                LabExecution.workspace_id == self.ctx.workspace_id,
                LabExecution.id == execution_id,
            )
        ).scalar_one_or_none()
        if ex is None:
            raise not_found("lab execution")
        return ex

    def _execution_project(self, ex: LabExecution) -> uuid.UUID:
        if ex.plan_id is not None:
            plan = self._plan(ex.plan_id)
            return self._task(plan.task_id).project_id
        if ex.task_id is not None:
            return self._task(ex.task_id).project_id
        raise DomainError(ErrorCode.VALIDATION, "execution has no scope")

    def _batch(self, batch_id: uuid.UUID) -> LabBatch:
        b = self.db.execute(
            select(LabBatch).where(
                LabBatch.workspace_id == self.ctx.workspace_id,
                LabBatch.id == batch_id,
            )
        ).scalar_one_or_none()
        if b is None:
            raise not_found("lab batch")
        return b

    def _sample(self, sample_id: uuid.UUID) -> LabSample:
        s = self.db.execute(
            select(LabSample).where(
                LabSample.workspace_id == self.ctx.workspace_id,
                LabSample.id == sample_id,
            )
        ).scalar_one_or_none()
        if s is None:
            raise not_found("lab sample")
        return s

    def _measurement(self, measurement_id: uuid.UUID) -> Measurement:
        m = self.db.execute(
            select(Measurement).where(
                Measurement.workspace_id == self.ctx.workspace_id,
                Measurement.id == measurement_id,
            )
        ).scalar_one_or_none()
        if m is None:
            raise not_found("measurement")
        return m

    def _measurement_project(self, m: Measurement) -> uuid.UUID:
        sample = self._sample(m.sample_id)
        batch = self._batch(sample.batch_id)
        return self._execution_project(self._execution(batch.execution_id))
