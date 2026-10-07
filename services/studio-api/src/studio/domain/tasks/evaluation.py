"""Per-metric task evaluation and closeout packets (§12.3, CS-0503).

Gate-first evaluation against the *frozen* contract and the permitted
evidence snapshot: for every required metric, find accepted,
contract-applicable measurements attributed to that metric with
compatible method/units/repeat requirements. Units convert only through
the recorded whitelist (``domain.lab.units``). Missing, censored-
unsupported, incompatible or insufficiently replicated evidence is
``inconclusive`` — never forced into pass/fail.

Hard constraints evaluate independently and are never compensated by
metric performance (AT-0503-2): a failed safety/identity gate is a
definitive negative, reported as ``supported_failure`` to a human
reviewer — no reward term can offset it.

The evaluator only *suggests* a closure decision; a human reviewer
closes via ``TaskService.close`` with the bound packet. A later
amended/superseded measurement marks the prior conclusion as needing
reassessment — the signed packet itself is never rewritten (§7.1).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from chem_studio_policy.capabilities import CAP_READ_PROJECT
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext
from studio.domain.lab.units import compare, compatible, convert, metric_bound, to_decimal
from studio.domain.tasks.contract import resolve_metrics
from studio.errors import DomainError, not_found
from studio.persistence.models import (
    CandidateRevision,
    ExperimentPlan,
    FormulationRevision,
    LabBatch,
    LabExecution,
    LabSample,
    Measurement,
    ResearchTask,
    SuccessContractRevision,
    TaskDecision,
)

EVIDENCE_CLASS_MEASUREMENT = "lab_measurement"


def _metric_id(metric: dict[str, Any]) -> str:
    return str(metric.get("id") or metric.get("name") or metric.get("label") or "")


def assess_metric(metric: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure per-metric assessment (§12.3) — no DB, fully testable.

    ``rows`` are plain dicts ``{id, value_type, value, batch_id}`` of
    accepted, contract-applicable measurements already attributed to
    the metric. Verdicts: ``met`` / ``misses`` / ``inconclusive``;
    missing, censored-unsupported or incompatible evidence is always
    inconclusive, never a forced verdict."""
    mid = _metric_id(metric)
    required = bool(metric.get("required", True))
    findings: list[dict[str, str]] = []
    report: dict[str, Any] = {
        "metricId": mid,
        "label": metric.get("label") or metric.get("name") or mid,
        "required": required,
        "verdict": "inconclusive",
        "evidenceIds": [],
        "findings": findings,
    }
    try:
        bound = metric_bound(metric)
    except DomainError as exc:
        findings.append({"kind": "unknown", "text": f"unparseable metric bound: {exc.message}"})
        return report
    if bound is None:
        findings.append({"kind": "unknown", "text": "metric carries no bound"})
        return report
    op, target_val, target_unit = bound

    required_evidence = metric.get("required_evidence") or metric.get("requiredEvidence") or []
    if not rows:
        findings.append(
            {
                "kind": "missing",
                "text": "no accepted, contract-applicable measurement attributed to this metric",
                "action": "record_or_accept_measurement",
            }
        )
        return report

    satisfying: list[tuple[str, Decimal, Any]] = []
    batches: set[Any] = set()
    for row in rows:
        report["evidenceIds"].append(str(row["id"]))
        vtype = row["value_type"]
        value = row["value"]
        if vtype == "missing":
            findings.append(
                {
                    "kind": "missing_value",
                    "text": f"measurement {row['id']} is marked missing "
                    f"({value.get('reason', 'unspecified')}) — not usable",
                    "action": "remeasure",
                }
            )
            continue
        if vtype in ("below_detection", "above_quantification"):
            findings.append(
                {
                    "kind": "censored_unsupported",
                    "text": f"measurement {row['id']} is censored "
                    f"({vtype}) — cannot establish the bound (§6.3)",
                    "action": "remeasure_above_limit",
                }
            )
            continue
        if vtype != "numeric":
            findings.append(
                {
                    "kind": "value_type",
                    "text": f"measurement {row['id']} is '{vtype}', not a numeric comparison input",
                    "action": "provide_numeric_measurement",
                }
            )
            continue
        try:
            raw = to_decimal(value["value"])
        except (DomainError, KeyError):
            findings.append(
                {
                    "kind": "value_invalid",
                    "text": f"measurement {row['id']} numeric payload is not a decimal string",
                    "action": "amend_value",
                }
            )
            continue
        unit = str(value.get("unit") or "")
        if target_unit is None:
            findings.append(
                {
                    "kind": "unit_missing",
                    "text": "contract metric carries no unit — comparison is not safe",
                    "action": "add_target_unit",
                }
            )
            continue
        if not compatible(unit, target_unit):
            findings.append(
                {
                    "kind": "unit_incompatible",
                    "text": f"unit '{unit}' cannot be compared to '{target_unit}' (§6.1)",
                    "action": "remeasure_or_review_conversion",
                }
            )
            continue
        converted = convert(raw, unit, target_unit)
        if converted is None:
            findings.append(
                {
                    "kind": "conversion_missing",
                    "text": f"no whitelisted conversion {unit} → {target_unit}",
                    "action": "remeasure_or_review_conversion",
                }
            )
            continue
        satisfying.append((str(row["id"]), converted, row.get("batch_id")))
        if row.get("batch_id") is not None:
            batches.add(row["batch_id"])

    if not satisfying:
        return report  # findings already explain why inconclusive

    aggregation = str(metric.get("aggregation") or "fixture-single-value").strip()
    values = [v for _, v, _ in satisfying]
    if aggregation in ("fixture-single-value", "single"):
        ok = any(compare(v, op, target_val) for v in values)
    elif aggregation == "min":
        ok = compare(min(values), op, target_val)
    elif aggregation == "max":
        ok = compare(max(values), op, target_val)
    elif aggregation == "mean":
        ok = compare(sum(values) / Decimal(len(values)), op, target_val)
    else:
        findings.append(
            {
                "kind": "unknown",
                "text": f"unknown aggregation {aggregation!r} — cannot combine evidence safely",
            }
        )
        return report

    replication = metric.get("replication_rule") or metric.get("replicationRule")
    if isinstance(replication, dict) and replication.get("minIndependentBatches"):
        need = int(replication["minIndependentBatches"])
        if len(batches) < need:
            findings.append(
                {
                    "kind": "insufficient_replication",
                    "text": f"{len(batches)} independent batch(es) < required "
                    f"{need} — same-aliquot repeats do not count (§14.4)",
                    "action": "prepare_independent_batch",
                }
            )
            return report

    unmet_classes = [c for c in required_evidence if c != EVIDENCE_CLASS_MEASUREMENT]
    if unmet_classes:
        findings.append(
            {
                "kind": "evidence_class_missing",
                "text": f"metric requires evidence classes "
                f"{unmet_classes} — lab measurement alone cannot satisfy",
                "action": "provide_required_evidence",
            }
        )
        return report

    report["verdict"] = "met" if ok else "misses"
    report["comparedAgainst"] = f"{op} {target_val} {target_unit or ''}".strip()
    report["aggregation"] = aggregation
    report["independentBatches"] = len(batches)
    return report


class TaskEvaluationService:
    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    # ------------------------------------------------------------- api

    def evaluate(self, task_id: uuid.UUID) -> dict[str, Any]:
        """Gate-first per-metric evaluation (§12.2/§12.3)."""
        task = self._task(task_id)
        self.ctx.require(CAP_READ_PROJECT, task.project_id)
        contract = self._frozen_contract(task)
        base: dict[str, Any] = {
            "taskId": str(task.id),
            "evaluationCycle": task.evaluation_cycle,
            "fixtureOnly": True,
        }
        if contract is None:
            return {
                **base,
                "assessable": False,
                "reason": "no frozen contract",
                "metrics": [],
                "gates": [],
                "findings": [
                    {
                        "kind": "contract_missing",
                        "text": "no frozen success contract — freeze one before closure review",
                        "action": "freeze_contract",
                    }
                ],
                "unknowns": [],
                "evidenceIds": [],
                "supportedSuccessEligible": False,
                "suggestedDecision": "inconclusive",
            }

        # Canonical + legacy vocabulary share one resolver (PAR-01):
        # 'metrics' is authoritative; pre-fix UI 'requiredMetrics'
        # payloads translate through the explicit legacy path with
        # review issues surfaced — never silently zero metrics.
        resolved = resolve_metrics(contract.payload)
        metrics = [self._evaluate_metric(task, m) for m in resolved.metrics]
        gates = [self._evaluate_gate(task, g) for g in resolved.gates]
        contract_issues = list(resolved.issues)
        # A frozen contract with nothing evaluable is *not* assessable:
        # unknown/legacy fields may not quietly read as a contract with
        # zero requirements. The report still explains why.
        assessable = bool(resolved.metrics or resolved.gates)
        if not assessable:
            contract_issues.append(
                "frozen contract carries no evaluable metrics or "
                "constraints — it cannot support a verdict"
            )
        unknowns = [
            u for m in metrics for u in (f["text"] for f in m["findings"] if f["kind"] == "unknown")
        ]
        unknowns += contract_issues
        unknowns += [
            f"hard constraint '{g['id']}' carries no evaluable check — human review required"
            for g in gates
            if g["verdict"] == "not_evaluated"
        ]

        gate_failed = any(g["verdict"] == "fail" for g in gates)
        gate_unproven = any(g["verdict"] != "pass" for g in gates)
        required = [m for m in metrics if m["required"]]
        all_met = bool(required) and all(m["verdict"] == "met" for m in required)
        any_misses = any(m["verdict"] == "misses" for m in required)

        if gate_failed or any_misses:
            suggested = "supported_failure"
        elif all_met and not gate_unproven:
            suggested = "supported_success"
        else:
            suggested = "inconclusive"

        eligible = suggested == "supported_success"
        return {
            **base,
            "assessable": assessable,
            "reason": (
                None
                if assessable
                else "contract carries no evaluable metrics or constraints"
            ),
            "legacyPayload": resolved.legacy,
            "contractIssues": contract_issues,
            "contractRevisionId": str(contract.id),
            "contractRevision": contract.revision,
            "metrics": metrics,
            "gates": gates,
            "findings": [],
            "unknowns": unknowns,
            "evidenceIds": sorted({e for m in metrics for e in m["evidenceIds"]}),
            "supportedSuccessEligible": eligible,
            "suggestedDecision": suggested,
        }

    def closeout_packet(self, task_id: uuid.UUID) -> dict[str, Any]:
        """Immutable-shape closure packet for ``task.close`` (§12.3).

        Binds the exact contract revision, the bound candidate revision,
        the evidence snapshot and the fixture-only status — nothing in
        it is re-derived at close time."""
        task = self._task(task_id)
        report = self.evaluate(task_id)
        candidate = self._bound_candidate(task)
        return {
            "kind": "task_closeout",
            "taskId": str(task.id),
            "evaluationCycle": task.evaluation_cycle,
            "contractRevisionId": report.get("contractRevisionId"),
            "candidateRevisionId": str(candidate.id) if candidate else None,
            "metrics": report["metrics"],
            "gates": report["gates"],
            "unknowns": report["unknowns"],
            "evidenceIds": report["evidenceIds"],
            "evidenceSnapshot": report["metrics"],
            "legacyPayload": report.get("legacyPayload", False),
            "contractIssues": report.get("contractIssues", []),
            "suggestedDecision": report["suggestedDecision"],
            "supportedSuccessEligible": report["supportedSuccessEligible"],
            "fixtureOnly": True,
            "scientificValidation": "not_validated",
        }

    def reassessment_status(self, task_id: uuid.UUID) -> dict[str, Any]:
        """Whether evidence bound into the latest closure packet has
        since been superseded/revoked (§12.3) — flags reassessment
        without rewriting the signed packet."""
        task = self._task(task_id)
        self.ctx.require(CAP_READ_PROJECT, task.project_id)
        closure = self.db.execute(
            select(TaskDecision)
            .where(
                TaskDecision.workspace_id == self.ctx.workspace_id,
                TaskDecision.task_id == task.id,
                TaskDecision.kind == "closure",
            )
            .order_by(TaskDecision.created_at.desc(), TaskDecision.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if closure is None:
            return {"needsReassessment": False, "staleEvidenceIds": []}
        evidence_ids = (closure.payload.get("packet") or {}).get("evidenceIds") or []
        stale: list[dict[str, str]] = []
        for raw in evidence_ids:
            try:
                m_uuid = uuid.UUID(str(raw))
            except ValueError:
                continue
            m = self.db.get(Measurement, m_uuid)
            if m is None:
                stale.append({"id": str(raw), "status": "missing"})
            elif m.status in ("superseded", "rejected"):
                stale.append({"id": str(raw), "status": m.status})
        return {
            "needsReassessment": bool(stale),
            "staleEvidenceIds": stale,
            "closureDecisionId": str(closure.id),
            "closureDecision": closure.payload.get("closureDecision"),
        }

    # -------------------------------------------------------- metrics

    def _evaluate_metric(self, task: ResearchTask, metric: dict[str, Any]) -> dict[str, Any]:
        mid = _metric_id(metric)
        rows = self._task_measurements(task, mid)
        return assess_metric(
            metric,
            [
                {
                    "id": str(m.id),
                    "value_type": m.value_type,
                    "value": m.value,
                    "batch_id": batch_id,
                }
                for m, batch_id in rows
            ],
        )

    # ---------------------------------------------------------- gates

    def _evaluate_gate(self, task: ResearchTask, gate: Any) -> dict[str, Any]:
        """Hard constraint — never a reward term (§12.2, AT-0503-2)."""
        if isinstance(gate, str):
            return {
                "id": gate[:80],
                "text": gate,
                "verdict": "not_evaluated",
                "findings": [],
            }
        gid = str(gate.get("id") or gate.get("text") or "")[:120]
        check = gate.get("check")
        if not isinstance(check, dict):
            return {
                "id": gid,
                "text": gate.get("text") or gid,
                "verdict": "not_evaluated",
                "findings": [],
            }
        kind = check.get("kind")
        if kind == "metric":
            r = self._evaluate_metric(task, check)
            verdict = {"met": "pass", "misses": "fail"}.get(r["verdict"], "not_evaluated")
            return {
                "id": gid,
                "text": gate.get("text") or gid,
                "verdict": verdict,
                "metricVerdict": r["verdict"],
                "findings": r["findings"],
                "evidenceIds": r["evidenceIds"],
            }
        if kind == "ingredient_absent":
            material_id = str(check.get("materialIdentityId") or "")
            cand = self._bound_candidate(task)
            present = False
            if cand is not None and cand.entity_revision_id is not None:
                formulation = self.db.get(FormulationRevision, cand.entity_revision_id)
                ingredients = (
                    (formulation.payload or {}).get("ingredients") or []
                    if formulation is not None
                    else []
                )
                present = any(
                    str(i.get("materialId") or i.get("material_id") or "") == material_id
                    for i in ingredients
                    if isinstance(i, dict)
                )
            return {
                "id": gid,
                "text": gate.get("text") or f"ingredient {material_id} absent",
                "verdict": "fail" if present else "pass",
                "findings": [
                    {
                        "kind": "excluded_ingredient_present",
                        "text": "excluded material present in bound candidate",
                        "action": "revise_candidate",
                    }
                ]
                if present
                else [],
            }
        return {
            "id": gid,
            "text": gate.get("text") or gid,
            "verdict": "not_evaluated",
            "findings": [{"kind": "unknown", "text": f"unknown gate check {kind!r}"}],
        }

    # ------------------------------------------------------ internals

    def _task(self, task_id: uuid.UUID) -> ResearchTask:
        row = self.db.get(ResearchTask, task_id)
        if row is None or row.workspace_id != self.ctx.workspace_id:
            raise not_found("task")
        return row

    def _frozen_contract(self, task: ResearchTask) -> SuccessContractRevision | None:
        if task.current_contract_revision_id is None:
            return None
        rev = self.db.get(SuccessContractRevision, task.current_contract_revision_id)
        return rev if rev is not None and rev.status == "frozen" else None

    def _bound_candidate(self, task: ResearchTask) -> CandidateRevision | None:
        """Latest research-accepted candidate revision on the task."""
        return self.db.execute(
            select(CandidateRevision)
            .where(
                CandidateRevision.workspace_id == self.ctx.workspace_id,
                CandidateRevision.task_id == task.id,
                CandidateRevision.status == "accepted_for_research",
            )
            .order_by(CandidateRevision.revision.desc())
            .limit(1)
        ).scalar_one_or_none()

    def _task_measurements(
        self, task: ResearchTask, metric_id: str
    ) -> list[tuple[Measurement, uuid.UUID | None]]:
        """Accepted, contract-applicable measurements attributed to
        ``metric_id`` on this task's executions (plan-linked or
        direct historical link). Superseded rows are excluded — the
        amendment's corrected reading is the live one."""
        stmt = (
            select(Measurement, LabSample.batch_id)
            .join(LabSample, Measurement.sample_id == LabSample.id)
            .join(LabBatch, LabSample.batch_id == LabBatch.id)
            .join(LabExecution, LabBatch.execution_id == LabExecution.id)
            .outerjoin(ExperimentPlan, LabExecution.plan_id == ExperimentPlan.id)
            .where(
                Measurement.workspace_id == self.ctx.workspace_id,
                Measurement.metric == metric_id,
                Measurement.status == "accepted",
                Measurement.applicable.is_(True),
                or_(
                    ExperimentPlan.task_id == task.id,
                    LabExecution.task_id == task.id,
                ),
            )
            .order_by(Measurement.created_at, Measurement.id)
        )
        return [(m, b) for m, b in self.db.execute(stmt).all() if m.metric is not None]
