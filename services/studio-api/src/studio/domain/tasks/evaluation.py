"""Per-metric task evaluation and closeout packets (§12.3, CS-0503, PAR-02).

Gate-first evaluation against the *frozen* contract and explicitly
bound evidence: for every required metric, only measurements whose
lineage binds them to the *selected* candidate revision and the current
contract revision may count — evidence is never pooled across
candidates and attributed to a separately chosen one (PAR-02).

Scope model:
- ``candidate_revision_id`` given → evaluate exactly that revision.
- exactly one accepted candidate → that revision.
- zero accepted candidates → task scope: evidence with no candidate
  binding at all (a historical reading still describes *something*; it
  just cannot substantiate a named candidate).
- multiple accepted candidates and no selection → ``candidates[]``
  reports each separately and the top level is explicitly
  ``selection_required`` — never a synthesized winner from pooled
  metrics.

Lineage is resolved through the whole chain — measurement conditions →
sample → batch → execution actuals → experiment plan payload — and may
name a candidate revision directly or via a formulation revision the
candidate points at. Historical imports carry no candidate linkage;
they substantiate a candidate only through a reviewed
``EvidenceApplicability`` mapping (§12.3, PAR-02 §4), never by
assumption.

The evaluator only *suggests* a closure decision; a human reviewer
closes via ``TaskService.close`` with the bound packet + manifest. A
later amendment/revocation or applicability change marks the prior
conclusion as needing reassessment — the signed packet itself is never
rewritten (§7.1).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from chem_studio_policy.capabilities import CAP_READ_PROJECT
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext
from studio.domain.lab.units import compare, compatible, convert, metric_bound, to_decimal
from studio.domain.tasks.contract import resolve_metrics
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import (
    CandidateRevision,
    EvidenceApplicability,
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
EVALUATOR_VERSION = "par-02.1"

# Reference keys recorded at each lineage level (payloads carry both
# spellings historically — both are read, none is written).
_REF_CANDIDATE = ("candidateRevisionId", "candidate_revision_id")
_REF_FORMULATION = ("formulationRevisionId", "formulation_revision_id")
_REF_CONTRACT = ("contractRevisionId", "contract_revision_id")
_REF_METHOD = ("methodRevisionId", "method_revision_id")
_REF_SUBSTRATE = ("substrateRevisionId", "substrate_revision_id")


def _metric_id(metric: dict[str, Any]) -> str:
    return str(metric.get("id") or metric.get("name") or metric.get("label") or "")


def _refs(payload: Any, keys: tuple[str, ...]) -> set[uuid.UUID]:
    """UUID-valued references under ``keys`` at the top level of a
    payload and inside its ``planned``/``actual`` sub-objects."""
    out: set[uuid.UUID] = set()
    if not isinstance(payload, dict):
        return out
    layers: list[Any] = [payload]
    for sub in ("planned", "actual"):
        if isinstance(payload.get(sub), dict):
            layers.append(payload[sub])
    for layer in layers:
        for key in keys:
            raw = layer.get(key)
            if isinstance(raw, str):
                try:
                    out.add(uuid.UUID(raw))
                except ValueError:
                    continue
            elif isinstance(raw, uuid.UUID):
                out.add(raw)
    return out


def _manifest_digest(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(manifest, sort_keys=True, default=str).encode()
    ).hexdigest()


def assess_metric(metric: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure per-metric assessment (§12.3) — no DB, fully testable.

    ``rows`` are plain dicts ``{id, value_type, value, batch_id}`` of
    accepted, contract-applicable measurements already attributed to
    the metric *and bound to the evaluation scope*. Verdicts: ``met`` /
    ``misses`` / ``inconclusive``; missing, censored-unsupported or
    incompatible evidence is always inconclusive, never a forced
    verdict."""
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


@dataclass
class _Evidence:
    """One task measurement with its resolved lineage (PAR-02 §2)."""

    measurement: Measurement
    batch_id: uuid.UUID | None
    execution: LabExecution | None
    plan: ExperimentPlan | None
    lineage_candidates: set[uuid.UUID] = field(default_factory=set)
    lineage_contracts: set[uuid.UUID] = field(default_factory=set)
    mappings: dict[uuid.UUID, EvidenceApplicability] = field(default_factory=dict)
    # candidate_revision_id → non-revoked applicability row


@dataclass
class _Bound:
    included: bool
    reason: str | None = None
    detail: str | None = None
    via: str | None = None


class TaskEvaluationService:
    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    # ------------------------------------------------------------- api

    def evaluate(
        self,
        task_id: uuid.UUID,
        *,
        candidate_revision_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Gate-first per-metric evaluation (§12.2/§12.3), bound to an
        explicit candidate scope (PAR-02)."""
        task = self._task(task_id)
        self.ctx.require(CAP_READ_PROJECT, task.project_id)
        contract = self._frozen_contract(task)
        invalid = self._invalid_inputs(task)
        base: dict[str, Any] = {
            "taskId": str(task.id),
            "evaluationCycle": task.evaluation_cycle,
            "fixtureOnly": True,
            "evaluatorVersion": EVALUATOR_VERSION,
            "invalidInputs": invalid,
        }
        if contract is None:
            return {
                **base,
                "assessable": False,
                "reason": "no frozen contract",
                "candidateRevisionId": None,
                "candidates": [],
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
                "evidenceSelection": {"includedIds": [], "exclusions": []},
                "supportedSuccessEligible": False,
                "suggestedDecision": "inconclusive",
            }

        # Canonical + legacy vocabulary share one resolver (PAR-01):
        # 'metrics' is authoritative; pre-fix UI 'requiredMetrics'
        # payloads translate through the explicit legacy path with
        # review issues surfaced — never silently zero metrics.
        resolved = resolve_metrics(contract.payload)
        contract_issues = list(resolved.issues)
        assessable = bool(resolved.metrics or resolved.gates)
        if not assessable:
            contract_issues.append(
                "frozen contract carries no evaluable metrics or "
                "constraints — it cannot support a verdict"
            )

        accepted = self._accepted_candidates(task)
        evidence = self._evidence_rows(task)
        # Every accepted candidate is reported separately (PAR-02 §5).
        candidates = [
            self._evaluate_scope(task, contract, resolved, cand, evidence)
            for cand in accepted
        ]

        scope, scope_finding = self._resolve_scope(accepted, candidate_revision_id)
        if isinstance(scope, str):  # "multiple_candidates" — no top-level verdict
            metrics: list[dict[str, Any]] = []
            gates: list[dict[str, Any]] = []
            selection: dict[str, Any] = {"includedIds": [], "exclusions": []}
            evidence_ids: list[str] = []
            suggested = "inconclusive"
            scope_cand = None
        else:
            scope_cand = scope
            scoped = self._evaluate_scope(
                task, contract, resolved, scope_cand, evidence
            )
            metrics = scoped["metrics"]
            gates = scoped["gates"]
            selection = scoped["evidenceSelection"]
            evidence_ids = scoped["evidenceIds"]
            suggested = scoped["suggestedDecision"]

        unknowns = [
            u for m in metrics for u in (f["text"] for f in m["findings"] if f["kind"] == "unknown")
        ]
        unknowns += contract_issues
        unknowns += [
            f"hard constraint '{g['id']}' carries no evaluable check — human review required"
            for g in gates
            if g["verdict"] == "not_evaluated"
        ]
        unknowns += [
            f"invalid input: {i['field']} — {i['reason']}" for i in invalid
        ]

        findings: list[dict[str, Any]] = []
        if scope_finding is not None:
            findings.append(scope_finding)

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
            "candidateRevisionId": str(scope_cand.id) if scope_cand else None,
            "candidates": candidates,
            "metrics": metrics,
            "gates": gates,
            "findings": findings,
            "unknowns": unknowns,
            "evidenceIds": evidence_ids,
            "evidenceSelection": selection,
            "supportedSuccessEligible": eligible,
            "suggestedDecision": suggested,
        }

    def closeout_packet(
        self,
        task_id: uuid.UUID,
        *,
        candidate_revision_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Immutable-shape closure packet for ``task.close`` (§12.3).

        Binds the exact contract revision, the *selected* candidate
        revision, the full evidence-selection manifest (every considered
        row, included or excluded with reason) and the fixture-only
        status — nothing in it is re-derived at close time (PAR-02 §6)."""
        task = self._task(task_id)
        report = self.evaluate(task_id, candidate_revision_id=candidate_revision_id)
        manifest = self._manifest(task, report)
        return {
            "kind": "task_closeout",
            "taskId": str(task.id),
            "evaluationCycle": task.evaluation_cycle,
            "evaluatorVersion": EVALUATOR_VERSION,
            "contractRevisionId": report.get("contractRevisionId"),
            "candidateRevisionId": report.get("candidateRevisionId"),
            "candidates": report.get("candidates", []),
            "metrics": report["metrics"],
            "gates": report["gates"],
            "unknowns": report["unknowns"],
            "invalidInputs": report.get("invalidInputs", []),
            "evidenceIds": report["evidenceIds"],
            "evidenceSelection": report.get("evidenceSelection"),
            "evidenceSnapshot": report["metrics"],
            "legacyPayload": report.get("legacyPayload", False),
            "contractIssues": report.get("contractIssues", []),
            "suggestedDecision": report["suggestedDecision"],
            "supportedSuccessEligible": report["supportedSuccessEligible"],
            "manifest": manifest,
            "manifestDigest": _manifest_digest(manifest),
            "fixtureOnly": True,
            "scientificValidation": "not_validated",
        }

    def reassessment_status(self, task_id: uuid.UUID) -> dict[str, Any]:
        """Whether evidence bound into the latest closure packet has
        since changed (§12.3, PAR-02 §6) — flags reassessment without
        rewriting the signed packet: measurement status, applicability
        flips, contract revision moves, candidate set changes, new
        bound evidence, and applicability-mapping changes all count."""
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
            return {
                "needsReassessment": False,
                "staleEvidenceIds": [],
                "changedDependencies": [],
            }
        packet = (closure.payload.get("packet") or {})
        evidence_ids = packet.get("evidenceIds") or []
        manifest_evidence = {
            str(e.get("measurementId")): e
            for e in ((packet.get("manifest") or {}).get("evidence") or [])
        }
        stale: list[dict[str, str]] = []
        changes: set[str] = set()
        for raw in evidence_ids:
            try:
                m_uuid = uuid.UUID(str(raw))
            except ValueError:
                continue
            m = self.db.get(Measurement, m_uuid)
            if m is None:
                stale.append({"id": str(raw), "status": "missing"})
                continue
            if m.status in ("superseded", "rejected"):
                stale.append({"id": str(raw), "status": m.status})
            recorded = manifest_evidence.get(str(raw))
            if recorded is not None and recorded.get("applicable") is not None:
                if bool(m.applicable) != bool(recorded["applicable"]):
                    stale.append({"id": str(raw), "status": "applicability_changed"})
                    changes.add("applicability_changed")

        # contract revision moved since the packet was signed
        current_contract = str(task.current_contract_revision_id or "")
        if (packet.get("contractRevisionId") or "") != current_contract:
            changes.add("contract_revision_changed")

        # candidate set drift vs what the reviewer saw
        dependencies = (packet.get("manifest") or {}).get("dependencies") or {}
        recorded_cands = set(dependencies.get("candidateRevisionIds") or [])
        current_cands = {str(c.id) for c in self._accepted_candidates(task)}
        if current_cands - recorded_cands:
            changes.add("new_candidate")
        if recorded_cands - current_cands:
            changes.add("candidate_withdrawn")

        # applicability mappings touched: any changed row named in the
        # manifest, or a new mapping on the packet's candidate/evidence
        recorded_mappings = set(dependencies.get("applicabilityDecisionIds") or [])
        bound_cand = packet.get("candidateRevisionId")
        mapping_probe = select(EvidenceApplicability).where(
            EvidenceApplicability.workspace_id == self.ctx.workspace_id
        )
        current_mappings = list(self.db.execute(mapping_probe).scalars())
        for row in current_mappings:
            sid = str(row.id)
            in_scope = sid in recorded_mappings or (
                bound_cand and str(row.candidate_revision_id) == bound_cand
            ) or str(row.measurement_id) in set(evidence_ids)
            if not in_scope:
                continue
            if sid not in recorded_mappings:
                changes.add("applicability_changed")
            elif row.revoked_at is not None:
                changes.add("applicability_changed")
            else:
                recorded_status = (
                    (packet.get("manifest") or {})
                    .get("applicabilityDecisions", {})
                    .get(sid)
                )
                if recorded_status is not None and recorded_status != row.status:
                    changes.add("applicability_changed")

        # new bound evidence since the packet: recompute the selection
        # for the packet's scope and compare
        new_evidence: list[str] = []
        if packet.get("contractRevisionId"):
            try:
                scope_id = uuid.UUID(bound_cand) if bound_cand else None
                report = self.evaluate(task.id, candidate_revision_id=scope_id)
                known = set(evidence_ids) | {
                    e.get("measurementId")
                    for e in (
                        (packet.get("evidenceSelection") or {}).get("exclusions") or []
                    )
                }
                new_evidence = [
                    eid for eid in report.get("evidenceIds", []) if eid not in known
                ]
                if new_evidence:
                    changes.add("new_evidence")
            except DomainError:
                pass

        return {
            "needsReassessment": bool(stale or changes),
            "staleEvidenceIds": stale,
            "changedDependencies": sorted(changes),
            "newEvidenceIds": new_evidence,
            "closureDecisionId": str(closure.id),
            "closureDecision": closure.payload.get("closureDecision"),
        }

    # -------------------------------------------------------- metrics

    def _evaluate_metric(
        self, metric: dict[str, Any], bound: list[_Evidence]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Assess one metric over evidence already bound to the scope,
        applying method/substrate requirements from the contract before
        comparison (PAR-02 §3). Returns (metric report, exclusions)."""
        mid = _metric_id(metric)
        required_method = metric.get("method_revision_id")
        required_substrate = None
        conditions = metric.get("conditions")
        if isinstance(conditions, dict):
            required_substrate = conditions.get("substrate_revision_id")

        usable: list[_Evidence] = []
        exclusions: list[dict[str, Any]] = []
        for ev in bound:
            m = ev.measurement
            if required_method is not None:
                declared = self._declared_ref(ev, _REF_METHOD)
                if declared is None:
                    exclusions.append(
                        {
                            "measurementId": str(m.id),
                            "metricId": mid,
                            "reason": "method_unresolved",
                            "detail": "metric requires a method revision; "
                            "measurement records none",
                            "action": "record_method_revision",
                        }
                    )
                    continue
                if declared != str(required_method):
                    exclusions.append(
                        {
                            "measurementId": str(m.id),
                            "metricId": mid,
                            "reason": "method_mismatch",
                            "detail": f"measurement method revision "
                            f"{declared} ≠ contract {required_method}",
                            "action": "remeasure_or_review_mapping",
                        }
                    )
                    continue
            if required_substrate is not None:
                declared = self._declared_ref(ev, _REF_SUBSTRATE)
                if declared is None:
                    exclusions.append(
                        {
                            "measurementId": str(m.id),
                            "metricId": mid,
                            "reason": "substrate_unresolved",
                            "detail": "metric requires a substrate revision; "
                            "measurement records none",
                            "action": "record_substrate_revision",
                        }
                    )
                    continue
                if declared != str(required_substrate):
                    exclusions.append(
                        {
                            "measurementId": str(m.id),
                            "metricId": mid,
                            "reason": "substrate_mismatch",
                            "detail": f"measurement substrate revision "
                            f"{declared} ≠ contract {required_substrate}",
                            "action": "remeasure_or_review_mapping",
                        }
                    )
                    continue
            usable.append(ev)

        report = assess_metric(
            metric,
            [
                {
                    "id": str(ev.measurement.id),
                    "value_type": ev.measurement.value_type,
                    "value": ev.measurement.value,
                    "batch_id": ev.batch_id,
                }
                for ev in usable
                if ev.measurement.metric == mid
            ],
        )
        return report, exclusions

    # ---------------------------------------------------------- gates

    def _evaluate_gate(
        self,
        task: ResearchTask,
        gate: Any,
        scope: CandidateRevision | None,
        bound: list[_Evidence],
    ) -> dict[str, Any]:
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
            r, _excl = self._evaluate_metric(check, bound)
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
            present = False
            if scope is not None and scope.entity_revision_id is not None:
                formulation = self.db.get(FormulationRevision, scope.entity_revision_id)
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

    # -------------------------------------------------- scope / scope eval

    def _resolve_scope(
        self,
        accepted: list[CandidateRevision],
        candidate_revision_id: uuid.UUID | None,
    ) -> tuple[CandidateRevision | str | None, dict[str, Any] | None]:
        if candidate_revision_id is not None:
            for cand in accepted:
                if cand.id == candidate_revision_id:
                    return cand, None
            raise DomainError(
                ErrorCode.VALIDATION,
                "candidateRevisionId is not an accepted candidate on this task",
                field_path="candidateRevisionId",
            )
        if len(accepted) == 1:
            return accepted[0], None
        if not accepted:
            return None, None
        return "multiple_candidates", {
            "kind": "multiple_candidates",
            "text": f"{len(accepted)} accepted candidates — evaluation is "
            "reported per candidate; closeout requires an explicit "
            "candidateRevisionId",
            "action": "select_candidate_revision",
        }

    def _evaluate_scope(
        self,
        task: ResearchTask,
        contract: SuccessContractRevision,
        resolved: Any,
        scope: CandidateRevision | None,
        evidence: list[_Evidence],
    ) -> dict[str, Any]:
        bound: list[_Evidence] = []
        exclusions: list[dict[str, Any]] = []
        for ev in evidence:
            decision = self._bind(ev, scope, contract)
            if decision.included:
                bound.append(ev)
            else:
                exclusions.append(
                    {
                        "measurementId": str(ev.measurement.id),
                        "reason": decision.reason,
                        "detail": decision.detail,
                    }
                )

        metrics: list[dict[str, Any]] = []
        metric_exclusions: list[dict[str, Any]] = []
        for metric in resolved.metrics:
            rep, excl = self._evaluate_metric(metric, bound)
            metrics.append(rep)
            metric_exclusions.extend(excl)
        gates = [self._evaluate_gate(task, g, scope, bound) for g in resolved.gates]

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

        return {
            "candidateRevisionId": str(scope.id) if scope else None,
            "candidateRevision": scope.revision if scope else None,
            "entityKind": scope.entity_kind if scope else None,
            "entityRevisionId": (
                str(scope.entity_revision_id)
                if scope is not None and scope.entity_revision_id
                else None
            ),
            "eligibility": scope.eligibility if scope else None,
            "metrics": metrics,
            "gates": gates,
            "evidenceIds": sorted({e for m in metrics for e in m["evidenceIds"]}),
            "evidenceSelection": {
                "includedIds": [str(ev.measurement.id) for ev in bound],
                "exclusions": exclusions + metric_exclusions,
            },
            "suggestedDecision": suggested,
            "supportedSuccessEligible": suggested == "supported_success",
        }

    def _bind(
        self,
        ev: _Evidence,
        scope: CandidateRevision | None,
        contract: SuccessContractRevision,
    ) -> _Bound:
        """Whether ``ev`` may count in ``scope`` — the attribution rule
        the audit requires (PAR-02 §2-4)."""
        m = ev.measurement
        if m.status != "accepted":
            return _Bound(False, "status_not_accepted", f"status={m.status}")
        if not m.applicable:
            return _Bound(
                False,
                "marked_inapplicable",
                m.applicability_note or "marked inapplicable by reviewer",
            )

        mapped = {
            cid: row for cid, row in ev.mappings.items() if row.revoked_at is None
        }
        if scope is None:
            bound_elsewhere = ev.lineage_candidates | set(mapped.keys())
            if bound_elsewhere:
                return _Bound(
                    False,
                    "bound_to_candidate",
                    f"evidence binds to candidate revision(s) "
                    f"{sorted(str(c) for c in bound_elsewhere)} — it belongs "
                    "to their reports, not the task scope",
                )
        else:
            mapping = mapped.get(scope.id)
            if mapping is not None and mapping.status == "not_applicable":
                return _Bound(
                    False,
                    "mapped_not_applicable",
                    mapping.rationale,
                )
            lineage = ev.lineage_candidates | {
                cid for cid, row in mapped.items() if row.status == "applicable"
            }
            others = lineage - {scope.id}
            if len(lineage) > 1 or (others and scope.id in lineage):
                return _Bound(
                    False,
                    "conflicting_lineage",
                    "evidence names multiple candidate revisions "
                    f"{sorted(str(c) for c in lineage)}",
                )
            if scope.id not in lineage:
                if others:
                    return _Bound(
                        False,
                        "bound_to_other_candidate",
                        f"evidence binds to {sorted(str(c) for c in others)}",
                    )
                return _Bound(
                    False,
                    "no_candidate_binding",
                    "no plan/lineage or reviewed applicability mapping "
                    "binds this measurement to the selected candidate",
                )

        # contract binding (both scopes): declared contract refs that
        # are not the evaluated contract exclude the row unless a
        # reviewed mapping re-applies it to this contract.
        declared = ev.lineage_contracts
        if declared and contract.id not in declared:
            mapping = mapped.get(scope.id) if scope is not None else None
            mapped_contract = (
                mapping.contract_revision_id
                if mapping is not None and mapping.status == "applicable"
                else None
            )
            if mapped_contract != contract.id:
                return _Bound(
                    False,
                    "different_contract",
                    f"evidence was bound to contract revision(s) "
                    f"{sorted(str(c) for c in declared)}",
                )

        if scope is not None:
            via = "reviewed_mapping" if scope.id in mapped else "lineage"
            return _Bound(True, via=via)
        return _Bound(True, via="task_scope")

    def _declared_ref(self, ev: _Evidence, keys: tuple[str, ...]) -> str | None:
        """First declared reference found walking measurement conditions →
        sample → batch → execution actuals → plan payload."""
        for payload in self._payload_chain(ev):
            found = _refs(payload, keys)
            if found:
                return str(sorted(str(f) for f in found)[0])
        return None

    def _payload_chain(self, ev: _Evidence) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = [ev.measurement.conditions]
        sample = self.db.get(LabSample, ev.measurement.sample_id)
        if sample is not None:
            out.append(sample.payload)
        if ev.batch_id is not None:
            batch = self.db.get(LabBatch, ev.batch_id)
            if batch is not None:
                out.append(batch.payload)
        if ev.execution is not None:
            out.append(ev.execution.actual)
        if ev.plan is not None:
            out.append(ev.plan.payload)
        return [p for p in out if isinstance(p, dict)]

    # -------------------------------------------------- lineage gather

    def _evidence_rows(self, task: ResearchTask) -> list[_Evidence]:
        stmt = (
            select(Measurement, LabSample, LabBatch, LabExecution, ExperimentPlan)
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
        formulation_to_candidates = self._formulation_candidate_map(task)
        by_measurement: dict[uuid.UUID, dict[uuid.UUID, EvidenceApplicability]] = {}
        for row in self.db.execute(
            select(EvidenceApplicability).where(
                EvidenceApplicability.workspace_id == self.ctx.workspace_id,
            )
        ).scalars():
            by_measurement.setdefault(row.measurement_id, {})[
                row.candidate_revision_id
            ] = row

        rows: list[_Evidence] = []
        for m, sample, batch, execution, plan in self.db.execute(stmt).all():
            lineage_c: set[uuid.UUID] = set()
            lineage_k: set[uuid.UUID] = set()
            for payload in (
                m.conditions,
                sample.payload,
                batch.payload,
                execution.actual,
                plan.payload if plan is not None else None,
            ):
                lineage_c |= _refs(payload, _REF_CANDIDATE)
                lineage_k |= _refs(payload, _REF_CONTRACT)
                for f in _refs(payload, _REF_FORMULATION):
                    lineage_c |= formulation_to_candidates.get(f, set())
            rows.append(
                _Evidence(
                    measurement=m,
                    batch_id=sample.batch_id,
                    execution=execution,
                    plan=plan,
                    lineage_candidates=lineage_c,
                    lineage_contracts=lineage_k,
                    mappings=by_measurement.get(m.id, {}),
                )
            )
        return rows

    def _formulation_candidate_map(
        self, task: ResearchTask
    ) -> dict[uuid.UUID, set[uuid.UUID]]:
        """formulation_revision_id → candidate revisions on this task
        whose entity points at it (lineage may name either)."""
        out: dict[uuid.UUID, set[uuid.UUID]] = {}
        for cand in self.db.execute(
            select(CandidateRevision).where(
                CandidateRevision.workspace_id == self.ctx.workspace_id,
                CandidateRevision.task_id == task.id,
            )
        ).scalars():
            if cand.entity_revision_id is not None:
                out.setdefault(cand.entity_revision_id, set()).add(cand.id)
        return out

    def _manifest(self, task: ResearchTask, report: dict[str, Any]) -> dict[str, Any]:
        """The exact evidence-selection manifest bound into a closeout —
        what the reviewer saw, so any later change is detectable."""
        scope_id = report.get("candidateRevisionId")
        evidence = self._evidence_rows(task)
        entries: list[dict[str, Any]] = []
        app_decisions: dict[str, str] = {}
        plan_ids: set[str] = set()
        execution_ids: set[str] = set()
        mapping_ids: set[str] = set()
        for ev in evidence:
            m = ev.measurement
            entries.append(
                {
                    "measurementId": str(m.id),
                    "metric": m.metric,
                    "status": m.status,
                    "applicable": m.applicable,
                    "planId": str(ev.plan.id) if ev.plan else None,
                    "executionId": str(ev.execution.id) if ev.execution else None,
                    "lineageCandidates": sorted(str(c) for c in ev.lineage_candidates),
                    "lineageContracts": sorted(str(c) for c in ev.lineage_contracts),
                    "mappings": {
                        str(cid): {"id": str(row.id), "status": row.status}
                        for cid, row in ev.mappings.items()
                    },
                }
            )
            if ev.plan is not None:
                plan_ids.add(str(ev.plan.id))
            if ev.execution is not None:
                execution_ids.add(str(ev.execution.id))
            for row in ev.mappings.values():
                if row.revoked_at is None:
                    mapping_ids.add(str(row.id))
                    app_decisions[str(row.id)] = row.status
        candidates = self._accepted_candidates(task)
        return {
            "taskId": str(task.id),
            "evaluationCycle": task.evaluation_cycle,
            "contractRevisionId": report.get("contractRevisionId"),
            "contractHash": self._contract_hash(report),
            "candidateRevisionId": scope_id,
            "evaluatorVersion": EVALUATOR_VERSION,
            "evidence": entries,
            "applicabilityDecisions": app_decisions,
            "dependencies": {
                "planIds": sorted(plan_ids),
                "executionIds": sorted(execution_ids),
                "applicabilityDecisionIds": sorted(mapping_ids),
                "candidateRevisionIds": sorted(str(c.id) for c in candidates),
                "contractRevisionId": report.get("contractRevisionId"),
            },
        }

    def _contract_hash(self, report: dict[str, Any]) -> str | None:
        cid = report.get("contractRevisionId")
        if not cid:
            return None
        try:
            rev = self.db.get(SuccessContractRevision, uuid.UUID(str(cid)))
        except ValueError:
            return None
        return rev.content_hash if rev is not None else None

    def _invalid_inputs(self, task: ResearchTask) -> list[dict[str, str]]:
        from studio.domain.tasks.service import invalid_inputs

        return invalid_inputs(self.db, task)

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

    def _accepted_candidates(self, task: ResearchTask) -> list[CandidateRevision]:
        return list(
            self.db.execute(
                select(CandidateRevision)
                .where(
                    CandidateRevision.workspace_id == self.ctx.workspace_id,
                    CandidateRevision.task_id == task.id,
                    CandidateRevision.status == "accepted_for_research",
                )
                .order_by(CandidateRevision.revision)
            ).scalars()
        )
