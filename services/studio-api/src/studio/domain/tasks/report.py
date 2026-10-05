"""Task report composer (§25, CS-0504).

A structured, read-only view of one task for human review: hypotheses,
measurements, contradictions, unknowns and review scope — plus the
evaluator output. The report is a review aid, never a claim of
scientific validity: every report carries the fixture-only limitation,
and mode-specific honesty limits (e.g. a functional match says nothing
about composition) are stated explicitly.
"""

from __future__ import annotations

import uuid
from typing import Any

from chem_studio_policy.capabilities import CAP_READ_PROJECT
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext
from studio.domain.tasks.evaluation import TaskEvaluationService
from studio.domain.tasks.service import unresolved_inputs
from studio.errors import not_found
from studio.persistence.models import (
    CandidateRevision,
    ClaimLink,
    EvidenceClaim,
    ExperimentPlan,
    LabBatch,
    LabExecution,
    LabSample,
    Measurement,
    ResearchTask,
    SuccessContractRevision,
    TaskDecision,
    TaskQuestion,
)

# Honest limits the report states per mode — the UI must be able to
# display "what this task cannot conclude" without inventing it.
_MODE_LIMITS: dict[str, list[str]] = {
    "improve": [
        "deltas are reported only against compatible recorded baseline evidence",
    ],
    "match_reference": [
        "functional match says nothing about composition or identity — "
        "exact-identity claims are out of scope unless separately established",
        "supplier claims remain claims until independently measured",
    ],
    "discover": [
        "novelty is internal-corpus-only unless external evidence exists",
    ],
}


class TaskReportService:
    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    def report(self, task_id: uuid.UUID) -> dict[str, Any]:
        task = self._task(task_id)
        self.ctx.require(CAP_READ_PROJECT, task.project_id)
        ws = self.ctx.workspace_id

        contract = None
        if task.current_contract_revision_id is not None:
            contract = self.db.get(SuccessContractRevision, task.current_contract_revision_id)

        evaluation = TaskEvaluationService(self.db, self.ctx).evaluate(task.id)

        candidates = (
            self.db.execute(
                select(CandidateRevision)
                .where(
                    CandidateRevision.workspace_id == ws,
                    CandidateRevision.task_id == task.id,
                )
                .order_by(CandidateRevision.revision)
            )
            .scalars()
            .all()
        )
        hypotheses = [
            {
                "id": str(c.id),
                "revision": c.revision,
                "status": c.status,
                "hypothesis": (c.payload or {}).get("hypothesis"),
            }
            for c in candidates
        ]

        measurements = self._task_measurements(task)
        by_status: dict[str, int] = {}
        for m in measurements:
            by_status[m.status] = by_status.get(m.status, 0) + 1
        measurement_rows = [
            {
                "id": str(m.id),
                "metric": m.metric,
                "method": m.method,
                "status": m.status,
                "repeatType": m.repeat_type,
                "valueType": m.value_type,
                "applicable": m.applicable,
            }
            for m in measurements
        ]

        contradictions = self._contradictions()
        open_questions = (
            self.db.execute(
                select(TaskQuestion)
                .where(
                    TaskQuestion.workspace_id == ws,
                    TaskQuestion.task_id == task.id,
                    TaskQuestion.status == "open",
                )
                .order_by(TaskQuestion.created_at)
            )
            .scalars()
            .all()
        )
        decisions = (
            self.db.execute(
                select(TaskDecision)
                .where(
                    TaskDecision.workspace_id == ws,
                    TaskDecision.task_id == task.id,
                )
                .order_by(TaskDecision.created_at, TaskDecision.id)
            )
            .scalars()
            .all()
        )

        unknowns: list[str] = [f"unresolved input: {u}" for u in unresolved_inputs(task)]
        unknowns += [
            f"open question: {q.question}" + (" (blocking)" if q.blocking else "")
            for q in open_questions
        ]
        unknowns += [str(u) for u in evaluation.get("unknowns", [])]

        return {
            "task": {
                "id": str(task.id),
                "title": task.title,
                "mode": task.mode,
                "workflowState": task.workflow_state,
                "closureDecision": task.closure_decision,
                "evaluationCycle": task.evaluation_cycle,
                "targetKind": task.target_kind,
                "objective": task.objective,
                "modeInputs": task.mode_inputs,
            },
            "contract": {
                "id": str(contract.id),
                "revision": contract.revision,
                "status": contract.status,
                "metricCount": len((contract.payload or {}).get("metrics", [])),
                "gateCount": len(
                    (contract.payload or {}).get("hard_constraints", [])
                    or (contract.payload or {}).get("hardConstraints", [])
                    or []
                ),
            }
            if contract is not None
            else None,
            "evaluation": evaluation,
            "hypotheses": hypotheses,
            "measurements": {
                "rows": measurement_rows,
                "byStatus": by_status,
                "attributedCount": sum(1 for m in measurements if m.metric),
                "acceptedCount": by_status.get("accepted", 0),
            },
            "contradictions": contradictions,
            "unknowns": unknowns,
            "reviewScope": {
                "decisionCount": len(decisions),
                "closureRecorded": any(d.kind == "closure" for d in decisions),
                "humanReviewedMeasurements": by_status.get("accepted", 0)
                + by_status.get("rejected", 0)
                + by_status.get("superseded", 0),
                "pendingReviewMeasurements": by_status.get("proposed", 0),
            },
            "limitations": [
                "fixture-only software output — not scientific validation",
                *_MODE_LIMITS.get(task.mode, []),
            ],
        }

    # ------------------------------------------------------ internals

    def _task(self, task_id: uuid.UUID) -> ResearchTask:
        row = self.db.get(ResearchTask, task_id)
        if row is None or row.workspace_id != self.ctx.workspace_id:
            raise not_found("task")
        return row

    def _task_measurements(self, task: ResearchTask) -> list[Measurement]:
        stmt = (
            select(Measurement)
            .join(LabSample, Measurement.sample_id == LabSample.id)
            .join(LabBatch, LabSample.batch_id == LabBatch.id)
            .join(LabExecution, LabBatch.execution_id == LabExecution.id)
            .outerjoin(ExperimentPlan, LabExecution.plan_id == ExperimentPlan.id)
            .where(
                Measurement.workspace_id == self.ctx.workspace_id,
                or_(
                    ExperimentPlan.task_id == task.id,
                    LabExecution.task_id == task.id,
                ),
            )
            .order_by(Measurement.created_at, Measurement.id)
        )
        return list(self.db.execute(stmt).scalars().all())

    def _contradictions(self) -> list[dict[str, Any]]:
        """Accepted claims linked by `contradicts` — both sides stay
        visible with conditions; a contradiction never hides a claim
        (§10, AT-0302-2)."""
        links = (
            self.db.execute(
                select(ClaimLink).where(
                    ClaimLink.workspace_id == self.ctx.workspace_id,
                    ClaimLink.relation == "contradicts",
                )
            )
            .scalars()
            .all()
        )
        claim_ids = {link.from_claim_id for link in links} | {link.to_claim_id for link in links}
        if not claim_ids:
            return []
        claims = {
            c.id: c
            for c in self.db.execute(
                select(EvidenceClaim).where(
                    EvidenceClaim.workspace_id == self.ctx.workspace_id,
                    EvidenceClaim.id.in_(claim_ids),
                )
            ).scalars()
        }
        out = []
        for link in links:
            a, b = claims.get(link.from_claim_id), claims.get(link.to_claim_id)
            if a is None or b is None:
                continue
            out.append(
                {
                    "linkId": str(link.id),
                    "claims": [
                        {
                            "id": str(a.id),
                            "kind": a.kind,
                            "status": a.status,
                            "statement": a.statement,
                            "conditions": a.conditions,
                        },
                        {
                            "id": str(b.id),
                            "kind": b.kind,
                            "status": b.status,
                            "statement": b.statement,
                            "conditions": b.conditions,
                        },
                    ],
                }
            )
        return out
