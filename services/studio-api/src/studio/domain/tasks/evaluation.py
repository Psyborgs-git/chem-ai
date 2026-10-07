"""Per-metric task evaluation and closeout packets (§12.3, CS-0503, PAR-02/03).

Gate-first evaluation against the *frozen* contract and explicitly
bound evidence: for every required metric, only measurements whose
lineage binds them to the *selected* candidate revision and the current
contract revision may count — evidence is never pooled across
candidates and attributed to a separately chosen one (PAR-02).

Hard gates fail safe (PAR-03): an ``ingredient_absent`` check requires
a valid target identity, an applicable candidate representation and a
*reviewed, complete* composition for the precise claim — missing,
unknown or partially-known composition is ``not_evaluated``, never a
silent ``pass``. The claim is bounded: a declared-composition review is
not an analytical determination or a compliance certificate. Gate
evidence and gate dependencies join the signed manifest, and any
dependency change — including an ``applicable`` flip that leaves
integrity accepted — flags the packet for reassessment.

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
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from chem_studio_policy.capabilities import CAP_READ_PROJECT
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext
from studio.domain.lab.units import compare, compatible, convert, metric_bound, to_decimal
from studio.domain.materials.formulations import ingredient_key
from studio.domain.tasks.contract import resolve_metrics
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import (
    Approval,
    CandidateRevision,
    EvidenceApplicability,
    ExperimentPlan,
    FormulationRevision,
    IdentityMatch,
    LabBatch,
    LabExecution,
    LabSample,
    MaterialIdentity,
    Measurement,
    ReferenceProduct,
    ReferenceProductRevision,
    ResearchTask,
    SuccessContractRevision,
    TaskDecision,
)

EVIDENCE_CLASS_MEASUREMENT = "lab_measurement"
EVALUATOR_VERSION = "par-03.1"

# Ingredient-line keys that can carry a resolvable identity. Supplier
# strings resolve only against registered identifier values — an
# unmatched supplier identity stays unresolved, never a silent miss.
_LINE_TEXT_KEYS = ("alias", "name", "identifier", "supplierSku", "supplier")
_LINE_ID_KEYS = ("materialId", "material_id")
# Alias-record fields that carry a usable name (never 'source').
_ALIAS_NAME_KEYS = ("name", "alias", "value", "term")
# Material-identity kinds whose members carry no ingredient list —
# composition is unknowable from the identity alone.
_NON_COMPOSITION_KINDS = ("commercial_mixture", "substance_class", "unknown")

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
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, default=str).encode()).hexdigest()


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
        self._identity_index_cache: (
            tuple[
                dict[str, set[uuid.UUID]],
                set[uuid.UUID],
                dict[uuid.UUID, set[uuid.UUID]],
            ]
            | None
        ) = None

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
            self._evaluate_scope(task, contract, resolved, cand, evidence) for cand in accepted
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
            scoped = self._evaluate_scope(task, contract, resolved, scope_cand, evidence)
            metrics = scoped["metrics"]
            gates = scoped["gates"]
            selection = scoped["evidenceSelection"]
            evidence_ids = scoped["evidenceIds"]
            suggested = scoped["suggestedDecision"]

        unknowns = [
            u for m in metrics for u in (f["text"] for f in m["findings"] if f["kind"] == "unknown")
        ]
        unknowns += contract_issues
        for g in gates:
            if g["verdict"] != "not_evaluated":
                continue
            gate_unknowns = [f["text"] for f in g.get("findings", []) if f.get("text")]
            unknowns += gate_unknowns or [
                f"hard constraint '{g['id']}' carries no evaluable check — human review required"
            ]
        unknowns += [f"invalid input: {i['field']} — {i['reason']}" for i in invalid]

        findings: list[dict[str, Any]] = []
        if scope_finding is not None:
            findings.append(scope_finding)

        eligible = suggested == "supported_success"
        return {
            **base,
            "assessable": assessable,
            "reason": (
                None if assessable else "contract carries no evaluable metrics or constraints"
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
        packet = closure.payload.get("packet") or {}
        evidence_ids = packet.get("evidenceIds") or []
        manifest = packet.get("manifest") or {}
        manifest_evidence = {
            str(e.get("measurementId")): e for e in (manifest.get("evidence") or [])
        }
        dependencies = manifest.get("dependencies") or {}
        # The rows the conclusion actually rests on: packet evidence +
        # the recorded selection + gate evidence (PAR-03 §4 — a
        # gate-only row is a supporting dependency too).
        gate_evidence_ids = {
            str(e) for g in (packet.get("gates") or []) for e in (g.get("evidenceIds") or [])
        }
        for cand_report in packet.get("candidates") or []:
            for g in cand_report.get("gates") or []:
                gate_evidence_ids |= {str(e) for e in (g.get("evidenceIds") or [])}
        supporting = (
            set(str(e) for e in evidence_ids)
            | {str(e) for e in ((packet.get("evidenceSelection") or {}).get("includedIds") or [])}
            | gate_evidence_ids
        )
        stale: list[dict[str, str]] = []
        changes: set[str] = set()
        # Every recorded manifest row is a dependency: status drift on
        # any of them and applicability drift on the supporting set both
        # count — an ``applicable`` flip with integrity still
        # ``accepted`` is a real change (PAR-03 §4).
        for mid_str, recorded in manifest_evidence.items():
            try:
                m_uuid = uuid.UUID(mid_str)
            except ValueError:
                continue
            m = self.db.get(Measurement, m_uuid)
            if m is None:
                if mid_str in supporting or mid_str in evidence_ids:
                    stale.append({"id": mid_str, "status": "missing"})
                continue
            if (
                recorded.get("status") is not None and m.status != recorded["status"]
            ) or m.status in ("superseded", "rejected"):
                stale.append({"id": mid_str, "status": m.status})
            if mid_str in supporting and recorded.get("applicable") is not None:
                if bool(m.applicable) != bool(recorded["applicable"]):
                    stale.append({"id": mid_str, "status": "applicability_changed"})
                    changes.add("applicability_changed")

        # hard-gate dependencies: composition revision drift, target
        # identity edits and candidate entity-link moves all invalidate
        # the recorded verdict's basis
        bound_cand = packet.get("candidateRevisionId")
        for dep in manifest.get("gateDependencies") or []:
            dep_cand = dep.get("candidateRevisionId")
            if dep_cand is not None and bound_cand is not None and dep_cand != bound_cand:
                continue
            comp_id = dep.get("compositionRevisionId")
            comp_kind = dep.get("compositionKind")
            if comp_kind == "formulation" and comp_id:
                comp = None
                try:
                    comp = self.db.get(FormulationRevision, uuid.UUID(str(comp_id)))
                except ValueError:
                    comp = None
                if comp is None:
                    changes.add("composition_changed")
                else:
                    if dep.get("compositionContentHash") != comp.content_hash:
                        changes.add("composition_changed")
                    if dep.get("compositionStatus") != comp.status:
                        changes.add("composition_changed")
                    if dep.get("compositionCompleteness") != (comp.payload or {}).get(
                        "completeness"
                    ):
                        changes.add("composition_changed")
            elif comp_kind == "reference_product":
                product = None
                pid = dep.get("referenceProductId")
                if pid:
                    try:
                        product = self.db.get(ReferenceProduct, uuid.UUID(str(pid)))
                    except ValueError:
                        product = None
                if product is None:
                    changes.add("composition_changed")
                else:
                    if dep.get("compositionCompleteness") != product.composition_knowledge:
                        changes.add("composition_changed")
                    if (
                        dep.get("referenceProductVersion") is not None
                        and product.version != dep["referenceProductVersion"]
                    ):
                        changes.add("composition_changed")
                    if comp_id and str(product.current_revision_id) != str(comp_id):
                        changes.add("composition_changed")
                if comp_id:
                    try:
                        comp_rev = self.db.get(ReferenceProductRevision, uuid.UUID(str(comp_id)))
                    except ValueError:
                        comp_rev = None
                    if comp_rev is None or (
                        dep.get("compositionContentHash")
                        and comp_rev.content_hash != dep["compositionContentHash"]
                    ):
                        changes.add("composition_changed")
            elif comp_kind == "material_identity" and comp_id:
                try:
                    ident = self.db.get(MaterialIdentity, uuid.UUID(str(comp_id)))
                except ValueError:
                    ident = None
                if ident is None or (
                    dep.get("materialIdentityVersion") is not None
                    and ident.version != dep["materialIdentityVersion"]
                ):
                    changes.add("composition_changed")
            ident_id = dep.get("materialIdentityId")
            if ident_id:
                try:
                    ident = self.db.get(MaterialIdentity, uuid.UUID(str(ident_id)))
                except ValueError:
                    ident = None
                if ident is None:
                    changes.add("target_identity_changed")
                elif (
                    dep.get("targetIdentityVersion") is not None
                    and ident.version != dep["targetIdentityVersion"]
                ):
                    changes.add("target_identity_changed")
            dep_entity = dep.get("entityRevisionId")
            if dep_cand and dep_entity is not None:
                try:
                    cand_row = self.db.get(CandidateRevision, uuid.UUID(str(dep_cand)))
                except ValueError:
                    cand_row = None
                if cand_row is not None and str(cand_row.entity_revision_id) != str(dep_entity):
                    changes.add("candidate_entity_changed")

        # recorded approvals revoked/expired/decision-flipped —
        # pending approvals tied to the packet's dependencies are
        # invalidated (PAR-03 §4)
        for aid in dependencies.get("approvalIds") or []:
            try:
                approval = self.db.get(Approval, uuid.UUID(str(aid)))
            except ValueError:
                approval = None
            if (
                approval is None
                or approval.revoked_at is not None
                or approval.decision != "approved"
                or (approval.expires_at is not None and approval.expires_at < datetime.now(UTC))
            ):
                changes.add("approval_revoked")

        # recorded candidate details changed under a stable id set
        for rec in dependencies.get("candidates") or []:
            try:
                cand_row = self.db.get(CandidateRevision, uuid.UUID(str(rec.get("id"))))
            except (ValueError, TypeError):
                cand_row = None
            if cand_row is None:
                changes.add("candidate_withdrawn")
                continue
            if (
                rec.get("contentHash") is not None and cand_row.content_hash != rec["contentHash"]
            ) or (
                rec.get("entityRevisionId")
                != (str(cand_row.entity_revision_id) if cand_row.entity_revision_id else None)
            ):
                changes.add("candidate_changed")

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
            in_scope = (
                sid in recorded_mappings
                or (bound_cand and str(row.candidate_revision_id) == bound_cand)
                or str(row.measurement_id) in set(evidence_ids)
            )
            if not in_scope:
                continue
            if sid not in recorded_mappings:
                changes.add("applicability_changed")
            elif row.revoked_at is not None:
                changes.add("applicability_changed")
            else:
                recorded_status = (
                    (packet.get("manifest") or {}).get("applicabilityDecisions", {}).get(sid)
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
                    for e in ((packet.get("evidenceSelection") or {}).get("exclusions") or [])
                }
                new_evidence = [eid for eid in report.get("evidenceIds", []) if eid not in known]
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
                            "detail": "metric requires a method revision; measurement records none",
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
            return self._evaluate_absence_gate(task, gate, gid, check, scope)
        return {
            "id": gid,
            "text": gate.get("text") or gid,
            "verdict": "not_evaluated",
            "findings": [{"kind": "unknown", "text": f"unknown gate check {kind!r}"}],
        }

    # --------------------------------------------- ingredient_absent

    def _evaluate_absence_gate(
        self,
        task: ResearchTask,
        gate: Any,
        gid: str,
        check: dict[str, Any],
        scope: CandidateRevision | None,
    ) -> dict[str, Any]:
        """Declared-absence check (PAR-03 §1-2): ``pass`` only when the
        bound subject's *reviewed, complete* composition fully resolves
        and the excluded identity is not declared in it. Missing,
        unknown or partially-resolved composition is ``not_evaluated``
        — absence of data is never absence of ingredient."""
        material_id = str(check.get("materialIdentityId") or "").strip()
        subject = str(check.get("subject") or check.get("appliesTo") or "candidate")
        basis = str(check.get("basis") or "declared")
        deps: dict[str, Any] = {
            "subject": subject,
            "materialIdentityId": material_id or None,
            "basis": basis,
        }
        report: dict[str, Any] = {
            "id": gid,
            "text": gate.get("text") or f"ingredient {material_id} absent",
            "verdict": "not_evaluated",
            "findings": [],
            "evidenceIds": [],
            "dependencies": deps,
        }
        findings: list[dict[str, Any]] = report["findings"]

        if not material_id:
            findings.append(
                {
                    "kind": "target_identity_missing",
                    "text": "absence check names no materialIdentityId — "
                    "there is no target to exclude",
                    "action": "set_target_identity",
                }
            )
            return report
        target = self._identity_row(material_id)
        deps["materialIdentityResolved"] = target is not None
        deps["targetIdentityVersion"] = target.version if target else None
        target_label = target.name if target is not None else material_id
        if target is None:
            findings.append(
                {
                    "kind": "unknown",
                    "text": f"excluded identity {material_id!r} is not in the "
                    "materials registry — only literal identifier matching is "
                    "available for it",
                    "action": "register_material_identity",
                }
            )
        if basis != "declared":
            findings.append(
                {
                    "kind": "basis_not_supported",
                    "text": f"check basis {basis!r} requires analytically "
                    "established absence — a declared-composition review is "
                    "not an analytical determination or a compliance "
                    "certificate",
                    "action": "record_analytical_evidence",
                }
            )
            return report

        lines = self._gate_composition(task, scope, deps, findings)
        if lines is None:
            return report
        return self._scan_absence(report, material_id, target_label, lines, deps)

    def _identity_row(self, material_id: str) -> MaterialIdentity | None:
        try:
            iid = uuid.UUID(material_id)
        except ValueError:
            return None
        row = self.db.get(MaterialIdentity, iid)
        return row if row is not None and row.workspace_id == self.ctx.workspace_id else None

    def _record_revision_dep(self, deps: dict[str, Any], rev: Any) -> None:
        deps["compositionRevision"] = rev.revision
        deps["compositionContentHash"] = rev.content_hash
        deps["compositionStatus"] = rev.status
        deps["compositionApprovalId"] = (
            str(rev.approval_id) if getattr(rev, "approval_id", None) else None
        )

    def _gate_composition(
        self,
        task: ResearchTask,
        scope: CandidateRevision | None,
        deps: dict[str, Any],
        findings: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | None:
        """The declared composition for the gate's subject, with the
        revision-level dependencies recorded into ``deps``; ``None``
        when coverage is missing, unreviewed or incomplete — the
        finding stays with the candidate as its research block."""
        if deps["subject"] in ("reference_product", "referenceProduct", "reference"):
            return self._reference_composition(task, deps, findings)
        if deps["subject"] != "candidate":
            findings.append(
                {
                    "kind": "unknown",
                    "text": f"unknown absence-gate subject {deps['subject']!r}",
                }
            )
            return None
        if scope is None:
            findings.append(
                {
                    "kind": "no_bound_candidate",
                    "text": "no accepted candidate binds a composition — "
                    "absence cannot be evaluated",
                    "action": "accept_candidate",
                }
            )
            return None
        deps["candidateRevisionId"] = str(scope.id)
        deps["entityKind"] = scope.entity_kind
        if scope.entity_revision_id is None:
            findings.append(
                {
                    "kind": "entity_link_missing",
                    "text": f"candidate rev {scope.revision} carries no "
                    f"{scope.entity_kind} revision link — composition is "
                    "unknown",
                    "action": "link_entity_revision",
                }
            )
            return None
        deps["entityRevisionId"] = str(scope.entity_revision_id)
        if scope.entity_kind == "formulation":
            deps["compositionKind"] = "formulation"
            deps["compositionRevisionId"] = str(scope.entity_revision_id)
            rev = self.db.get(FormulationRevision, scope.entity_revision_id)
            if rev is None:
                findings.append(
                    {
                        "kind": "composition_revision_missing",
                        "text": "the linked formulation revision does not "
                        "exist — composition is unknown",
                        "action": "relink_candidate_entity",
                    }
                )
                return None
            self._record_revision_dep(deps, rev)
            if rev.status != "accepted":
                findings.append(
                    {
                        "kind": (
                            "composition_unreviewed"
                            if rev.status == "draft"
                            else "composition_superseded"
                        ),
                        "text": f"formulation revision {rev.revision} is "
                        f"'{rev.status}' — not a current reviewed "
                        "composition",
                        "action": "accept_formulation_revision",
                    }
                )
                return None
            return self._lines_or_unknown(rev.payload, deps, findings)
        if scope.entity_kind in ("molecule", "material"):
            deps["compositionKind"] = "material_identity"
            deps["compositionRevisionId"] = str(scope.entity_revision_id)
            ident = self.db.get(MaterialIdentity, scope.entity_revision_id)
            if ident is None:
                findings.append(
                    {
                        "kind": "composition_revision_missing",
                        "text": "the linked material identity does not exist",
                        "action": "relink_candidate_entity",
                    }
                )
                return None
            deps["materialIdentityVersion"] = ident.version
            deps["compositionCompleteness"] = "identity"
            deps["compositionStatus"] = ident.evidence_status
            if ident.kind in _NON_COMPOSITION_KINDS:
                findings.append(
                    {
                        "kind": "composition_unknown",
                        "text": f"candidate identity '{ident.name}' is a "
                        f"'{ident.kind}' — it carries no ingredient list "
                        "to exclude from",
                        "action": "link_composition_revision",
                    }
                )
                return None
            deps["identityOnly"] = True
            deps["ingredientCount"] = 1
            # a single-substance identity *is* the composition line
            return [{"materialId": str(ident.id)}]
        findings.append(
            {
                "kind": "entity_kind_unsupported",
                "text": f"entity kind {scope.entity_kind!r} carries no declared composition",
            }
        )
        return None

    def _reference_composition(
        self,
        task: ResearchTask,
        deps: dict[str, Any],
        findings: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | None:
        """Composition lines of the task's reference product — ``None``
        when the product's recipe is unknown/partial (AT-0203-1)."""
        deps["compositionKind"] = "reference_product"
        raw = (task.mode_inputs or {}).get("referenceProductId")
        deps["referenceProductId"] = str(raw) if raw else None
        product = None
        if raw:
            try:
                product = self.db.get(ReferenceProduct, uuid.UUID(str(raw)))
            except ValueError:
                product = None
        if product is None:
            findings.append(
                {
                    "kind": "reference_link_missing",
                    "text": "the task names no resolvable reference product",
                    "action": "set_reference_product",
                }
            )
            return None
        deps["compositionCompleteness"] = product.composition_knowledge
        deps["referenceProductVersion"] = product.version
        if product.composition_knowledge == "unknown":
            findings.append(
                {
                    "kind": "composition_unknown",
                    "text": "the reference product's composition is unknown — "
                    "no recipe exists to exclude from (AT-0203-1)",
                    "action": "record_reference_composition",
                }
            )
            return None
        if product.composition_knowledge == "partial":
            findings.append(
                {
                    "kind": "composition_incomplete",
                    "text": "the reference product's composition is only partially known",
                    "action": "complete_reference_composition",
                }
            )
            return None
        rev = (
            self.db.get(ReferenceProductRevision, product.current_revision_id)
            if product.current_revision_id
            else None
        )
        if rev is None:
            findings.append(
                {
                    "kind": "composition_revision_missing",
                    "text": "the reference product has no current content revision",
                    "action": "draft_reference_revision",
                }
            )
            return None
        deps["compositionRevisionId"] = str(rev.id)
        self._record_revision_dep(deps, rev)
        lines = (rev.payload or {}).get("composition")
        if not isinstance(lines, list) or not lines:
            findings.append(
                {
                    "kind": "composition_unknown",
                    "text": "the reference product revision carries no composition list",
                    "action": "record_reference_composition",
                }
            )
            return None
        deps["ingredientCount"] = len(lines)
        return lines

    def _lines_or_unknown(
        self,
        payload: dict[str, Any] | None,
        deps: dict[str, Any],
        findings: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | None:
        lines = (payload or {}).get("ingredients")
        deps["compositionCompleteness"] = (payload or {}).get("completeness")
        if not isinstance(lines, list):
            findings.append(
                {
                    "kind": "composition_unknown",
                    "text": "the composition payload carries no ingredient list",
                    "action": "record_composition",
                }
            )
            return None
        if not lines:
            findings.append(
                {
                    "kind": "composition_empty",
                    "text": "the declared composition is empty — absence "
                    "cannot be derived from an empty recipe",
                    "action": "record_composition",
                }
            )
            return None
        if deps["compositionCompleteness"] != "complete":
            findings.append(
                {
                    "kind": "composition_incomplete",
                    "text": f"composition completeness is "
                    f"'{deps['compositionCompleteness'] or 'draft'}' — a "
                    "partial recipe cannot prove absence",
                    "action": "complete_composition",
                }
            )
            return None
        deps["ingredientCount"] = len(lines)
        return lines

    def _scan_absence(
        self,
        report: dict[str, Any],
        material_id: str,
        target_label: str,
        lines: list[dict[str, Any]],
        deps: dict[str, Any],
    ) -> dict[str, Any]:
        """Scan resolved composition lines for the excluded identity.
        Every line must resolve — an unresolvable line keeps the gate
        ``not_evaluated`` because the material cannot be ruled out."""
        index, known_ids, equivalences = self._identity_index()
        try:
            target_uuid: uuid.UUID | None = uuid.UUID(material_id)
        except ValueError:
            target_uuid = None
        target_class = (
            equivalences.get(target_uuid, set()) | {target_uuid}
            if target_uuid is not None
            else {material_id}
        )
        present: list[str] = []
        unresolved: list[str] = []
        resolved_ids: set[str] = set()
        for line in lines:
            if not isinstance(line, dict):
                unresolved.append("unidentified")
                continue
            hit = self._resolve_line(
                line, material_id, target_class, index, known_ids, equivalences
            )
            if hit == "target":
                present.append(ingredient_key(line))
            elif hit == "unresolved":
                unresolved.append(ingredient_key(line))
            elif hit:
                resolved_ids.add(str(hit))
        deps["resolvedIngredientIds"] = sorted(resolved_ids)
        deps["unresolvedIngredientCount"] = len(unresolved)
        findings: list[dict[str, Any]] = report["findings"]
        entity = f"{deps.get('compositionKind')} {deps.get('compositionRevisionId')}"
        if present:
            report["verdict"] = "fail"
            report["claimBasis"] = (
                "declared_identity" if deps.get("identityOnly") else "declared_composition"
            )
            report["claimBound"] = (
                f"the excluded material is declared in {entity} — a "
                "composition-record finding, not a measured impurity"
            )
            findings.append(
                {
                    "kind": "excluded_ingredient_present",
                    "text": f"excluded material '{target_label}' is declared "
                    f"as {', '.join(sorted(set(present)))}",
                    "action": "revise_candidate",
                }
            )
            return report
        if unresolved:
            findings.append(
                {
                    "kind": "ingredient_identity_unresolved",
                    "text": f"{len(unresolved)} ingredient line(s) resolve to "
                    f"no registered identity ({', '.join(sorted(unresolved))}) "
                    "— the excluded material cannot be ruled out",
                    "action": "resolve_ingredient_identities",
                }
            )
            return report
        report["verdict"] = "pass"
        report["claimBasis"] = (
            "declared_identity" if deps.get("identityOnly") else "declared_composition"
        )
        report["claimBound"] = (
            f"'{target_label}' is absent from the declared composition of "
            f"{entity} — a declared-composition statement bounded to that "
            "revision, not an analytical determination or a compliance "
            "certificate"
        )
        return report

    def _resolve_line(
        self,
        line: dict[str, Any],
        material_id: str,
        target_class: set[Any],
        index: dict[str, set[uuid.UUID]],
        known_ids: set[uuid.UUID],
        equivalences: dict[uuid.UUID, set[uuid.UUID]],
    ) -> str | None:
        """Classify one composition line: ``'target'`` when it resolves
        to the excluded identity, an identity-id string when it resolves
        to another registered identity, ``'unresolved'`` otherwise."""
        raw_id = next((line.get(k) for k in _LINE_ID_KEYS if line.get(k) is not None), None)
        if raw_id is not None:
            raw = str(raw_id)
            if raw == material_id:
                return "target"
            try:
                iid = uuid.UUID(raw)
            except ValueError:
                iid = None
            if iid is not None:
                if iid in target_class:
                    return "target"
                if iid in known_ids:
                    return str(iid)
                return "unresolved"
            hits = index.get(raw.strip().lower())
            if hits:
                return "target" if hits & target_class else str(sorted(hits)[0])
            return "unresolved"
        for key in _LINE_TEXT_KEYS:
            value = line.get(key)
            probes: list[str] = []
            if isinstance(value, str):
                probes.append(value)
            elif isinstance(value, dict):
                probes.extend(str(v) for v in value.values() if v is not None)
                scheme, val = value.get("scheme"), value.get("value")
                if scheme and val:
                    probes.append(f"{scheme}:{val}")
            elif isinstance(value, list):
                probes.extend(str(v) for v in value)
            for probe in probes:
                hits = index.get(probe.strip().lower())
                if hits:
                    return "target" if hits & target_class else str(sorted(hits)[0])
        return "unresolved"

    def _identity_index(
        self,
    ) -> tuple[
        dict[str, set[uuid.UUID]],
        set[uuid.UUID],
        dict[uuid.UUID, set[uuid.UUID]],
    ]:
        """Workspace material identities → (name/alias/identifier index,
        known id set, accepted-equivalence classes). Built once per
        service instance."""
        if self._identity_index_cache is not None:
            return self._identity_index_cache
        rows = list(
            self.db.execute(
                select(MaterialIdentity).where(
                    MaterialIdentity.workspace_id == self.ctx.workspace_id
                )
            ).scalars()
        )
        index: dict[str, set[uuid.UUID]] = {}
        known_ids: set[uuid.UUID] = set()

        def add(term: Any, iid: uuid.UUID) -> None:
            if isinstance(term, str) and term.strip():
                index.setdefault(term.strip().lower(), set()).add(iid)

        for ident in rows:
            known_ids.add(ident.id)
            add(ident.name, ident.id)
            for alias in ident.aliases or []:
                if isinstance(alias, str):
                    add(alias, ident.id)
                elif isinstance(alias, dict):
                    for key, value in alias.items():
                        if key in _ALIAS_NAME_KEYS:
                            add(value, ident.id)
            for identifier in ident.identifiers or []:
                if not isinstance(identifier, dict):
                    continue
                add(identifier.get("value"), ident.id)
                scheme, value = identifier.get("scheme"), identifier.get("value")
                if scheme and value:
                    add(f"{scheme}:{value}", ident.id)

        # accepted identity matches make two ids the same material —
        # absence must see through a reviewed equivalence
        parent: dict[uuid.UUID, uuid.UUID] = {}

        def find(x: uuid.UUID) -> uuid.UUID:
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for match in self.db.execute(
            select(IdentityMatch).where(
                IdentityMatch.workspace_id == self.ctx.workspace_id,
                IdentityMatch.status == "accepted",
            )
        ).scalars():
            ra, rb = find(match.source_identity_id), find(match.candidate_identity_id)
            if ra != rb:
                parent[ra] = rb

        equivalences: dict[uuid.UUID, set[uuid.UUID]] = {}
        for iid in list(parent):
            equivalences.setdefault(find(iid), set()).add(iid)
        member_class: dict[uuid.UUID, set[uuid.UUID]] = {}
        for members in equivalences.values():
            for iid in members:
                member_class[iid] = members
        cached = (index, known_ids, member_class)
        self._identity_index_cache = cached
        return cached

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

        # Gate evidence joins the scope's evidence set: metric-based
        # hard gates carry their own bindings (PAR-03 §3).
        gate_evidence = {e for g in gates for e in g.get("evidenceIds", [])}
        # Non-passing gates are the candidate's research blocks — it
        # stays visible, with the reason, never silently dropped (§12.2).
        blocks = [f for g in gates if g["verdict"] != "pass" for f in g.get("findings", [])]

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
            "blocks": blocks,
            "evidenceIds": sorted({e for m in metrics for e in m["evidenceIds"]} | gate_evidence),
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

        mapped = {cid: row for cid, row in ev.mappings.items() if row.revoked_at is None}
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
            by_measurement.setdefault(row.measurement_id, {})[row.candidate_revision_id] = row

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

    def _formulation_candidate_map(self, task: ResearchTask) -> dict[uuid.UUID, set[uuid.UUID]]:
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
        what the reviewer saw, so any later change is detectable. PAR-03
        §3: hard-gate evidence and gate dependencies (composition
        revisions, material identities, approvals, methods, versions)
        are recorded the same way; ``included`` marks the rows the
        verdict actually rests on."""
        scope_id = report.get("candidateRevisionId")
        included_ids = set((report.get("evidenceSelection") or {}).get("includedIds") or [])
        evidence = self._evidence_rows(task)
        entries: list[dict[str, Any]] = []
        app_decisions: dict[str, str] = {}
        plan_ids: set[str] = set()
        execution_ids: set[str] = set()
        mapping_ids: set[str] = set()
        approval_ids: set[str] = set()
        for ev in evidence:
            m = ev.measurement
            entries.append(
                {
                    "measurementId": str(m.id),
                    "metric": m.metric,
                    "method": m.method,
                    "methodRevisionId": self._declared_ref(ev, _REF_METHOD),
                    "pipelineVersion": m.pipeline_version,
                    "valueHash": hashlib.sha256(
                        json.dumps(m.value, sort_keys=True, default=str).encode()
                    ).hexdigest(),
                    "status": m.status,
                    "applicable": m.applicable,
                    "supersededBy": str(m.superseded_by) if m.superseded_by else None,
                    "included": str(m.id) in included_ids,
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
                if ev.plan.approval_id is not None:
                    approval_ids.add(str(ev.plan.approval_id))
            if ev.execution is not None:
                execution_ids.add(str(ev.execution.id))
            for row in ev.mappings.values():
                if row.revoked_at is None:
                    mapping_ids.add(str(row.id))
                    app_decisions[str(row.id)] = row.status
        candidates = self._accepted_candidates(task)
        contract = None
        try:
            contract = self.db.get(
                SuccessContractRevision,
                uuid.UUID(str(report.get("contractRevisionId") or "")),
            )
        except ValueError:
            contract = None
        if contract is not None and contract.approval_id is not None:
            approval_ids.add(str(contract.approval_id))
        # Gate dependencies (PAR-03 §3): per evaluated gate, the
        # composition revision, target identity and entity link the
        # verdict rested on — plus the approvals those records cite.
        gate_deps: list[dict[str, Any]] = []
        material_identity_ids: set[str] = set()
        composition_revision_ids: set[str] = set()
        seen_gate_deps: set[tuple[str | None, str | None]] = set()
        dep_sources: list[dict[str, Any]] = list(report.get("candidates") or [])
        if not dep_sources:
            dep_sources = [report]
        for source in dep_sources:
            src_cand = source.get("candidateRevisionId")
            for g in source.get("gates", []):
                dep = g.get("dependencies")
                if not dep:
                    continue
                key = (g.get("id"), src_cand)
                if key in seen_gate_deps:
                    continue
                seen_gate_deps.add(key)
                gate_deps.append(
                    {
                        "gateId": g.get("id"),
                        "verdict": g.get("verdict"),
                        "candidateRevisionId": src_cand,
                        **dep,
                    }
                )
                if dep.get("materialIdentityId"):
                    material_identity_ids.add(str(dep["materialIdentityId"]))
                for rid in dep.get("resolvedIngredientIds") or []:
                    material_identity_ids.add(str(rid))
                if dep.get("compositionRevisionId"):
                    composition_revision_ids.add(str(dep["compositionRevisionId"]))
                if dep.get("compositionApprovalId"):
                    approval_ids.add(str(dep["compositionApprovalId"]))
        for cand in candidates:
            if cand.approval_id is not None:
                approval_ids.add(str(cand.approval_id))
        return {
            "taskId": str(task.id),
            "evaluationCycle": task.evaluation_cycle,
            "contractRevisionId": report.get("contractRevisionId"),
            "contractHash": self._contract_hash(report),
            "candidateRevisionId": scope_id,
            "evaluatorVersion": EVALUATOR_VERSION,
            "evidence": entries,
            "applicabilityDecisions": app_decisions,
            "gateDependencies": gate_deps,
            "dependencies": {
                "planIds": sorted(plan_ids),
                "executionIds": sorted(execution_ids),
                "applicabilityDecisionIds": sorted(mapping_ids),
                "candidateRevisionIds": sorted(str(c.id) for c in candidates),
                "candidates": [
                    {
                        "id": str(c.id),
                        "revision": c.revision,
                        "contentHash": c.content_hash,
                        "status": c.status,
                        "eligibility": c.eligibility,
                        "entityKind": c.entity_kind,
                        "entityRevisionId": (
                            str(c.entity_revision_id) if c.entity_revision_id else None
                        ),
                    }
                    for c in candidates
                ],
                "contractRevisionId": report.get("contractRevisionId"),
                "contractRevision": contract.revision if contract else None,
                "materialIdentityIds": sorted(material_identity_ids),
                "compositionRevisionIds": sorted(composition_revision_ids),
                "approvalIds": sorted(approval_ids),
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
