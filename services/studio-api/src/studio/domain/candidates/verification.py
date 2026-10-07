"""Deterministic candidate verification (§12, §13, §16).

Combines three independent, replayable check families into one typed
packet — structural (real RDKit via the adapter), formulation/identity
(declared totals, unresolved identities, duplicate lines), and basis —
then evaluates the frozen contract's evidence requirements against the
evidence *classes actually present*.

The packet's vocabulary stays honest (§12.1): a structural pass is
``descriptor`` evidence, not synthesis feasibility, safety, or a lab
result. ``closure`` reports per-metric missingness — a passed check
never substitutes for a required laboratory endpoint (AT-0404-3).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine_adapter_rdkit import EngineError, RDKitAdapter, StructuralResult
from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext
from studio.domain.tasks.contract import resolve_metrics
from studio.errors import not_found
from studio.persistence.models import (
    CandidateRevision,
    FormulationRevision,
    MaterialIdentity,
    ResearchTask,
    SuccessContractRevision,
)

# Evidence classes this verifier can itself produce.
VERIFIER_EVIDENCE = ("descriptor",)


@dataclass
class Finding:
    kind: str
    severity: str  # info | warning | blocking | unknown
    detail: str
    subject: str | None = None


@dataclass
class VerificationPacket:
    candidate_revision_id: uuid.UUID
    findings: list[Finding] = field(default_factory=list)
    structural: list[dict[str, Any]] = field(default_factory=list)
    evidence_types: list[str] = field(default_factory=list)
    closure: dict[str, Any] = field(default_factory=dict)
    engine: dict[str, Any] = field(default_factory=dict)


class VerificationService:
    def __init__(
        self,
        db: Session,
        ctx: ServiceContext,
        adapter: RDKitAdapter | None = None,
    ) -> None:
        self.db = db
        self.ctx = ctx
        self.adapter = adapter or RDKitAdapter()

    # -- structural check ---------------------------------------------

    def verify_structure(self, smiles: str) -> StructuralResult | EngineError:
        """One structural check through the real adapter — result is
        the engine's own report; unavailability is a typed error, not
        a fabricated descriptor."""
        self.ctx.require("request_compute")
        return self.adapter.describe(smiles=smiles)

    # -- candidate evaluation ------------------------------------------

    def evaluate_candidate(
        self, task_id: uuid.UUID, candidate_revision_id: uuid.UUID
    ) -> dict[str, Any]:
        """Run the deterministic check suite and assess the frozen
        contract's evidence requirements.

        Returns a packet dict: checks run (with the engine's real
        version), eligibility findings, the evidence classes present,
        and a per-metric closure table — ``lab_measurement``
        requirements are reported missing unless actual lab evidence
        exists (structural evidence never substitutes)."""
        self.ctx.require("request_compute")
        task = self.db.execute(
            select(ResearchTask).where(
                ResearchTask.workspace_id == self.ctx.workspace_id,
                ResearchTask.id == task_id,
            )
        ).scalar_one_or_none()
        if task is None:
            raise not_found("task")
        cand = self.db.execute(
            select(CandidateRevision).where(
                CandidateRevision.workspace_id == self.ctx.workspace_id,
                CandidateRevision.id == candidate_revision_id,
                CandidateRevision.task_id == task_id,
            )
        ).scalar_one_or_none()
        if cand is None:
            raise not_found("candidate revision")

        packet = VerificationPacket(candidate_revision_id=cand.id)
        formulation = self._formulation(cand)
        if formulation is not None:
            self._check_formulation(packet, formulation)
        self._check_structures(packet, formulation)
        packet.evidence_types = sorted(set(VERIFIER_EVIDENCE))
        packet.closure = self._closure(task, cand)
        cap = self.adapter.capability()
        packet.engine = {
            "id": "rdkit",
            "version": cap.version,
            "adapter": "rdkit-adapter/v1",
            "available": cap.available,
            "detail": cap.detail,
        }
        audit_record(
            self.db,
            self.ctx,
            action="candidate.verified",
            target_type="candidate_revision",
            target_id=cand.id,
            detail={
                "taskId": str(task_id),
                "findings": len(packet.findings),
                "blocking": sum(1 for f in packet.findings if f.severity == "blocking"),
            },
        )
        return self._serialize(packet)

    # -- checks ---------------------------------------------------------

    def _formulation(self, cand: CandidateRevision) -> FormulationRevision | None:
        if cand.entity_revision_id is None or cand.entity_kind != "formulation":
            return None
        return self.db.execute(
            select(FormulationRevision).where(
                FormulationRevision.workspace_id == self.ctx.workspace_id,
                FormulationRevision.id == cand.entity_revision_id,
            )
        ).scalar_one_or_none()

    def _check_formulation(
        self, packet: VerificationPacket, formulation: FormulationRevision
    ) -> None:
        payload = formulation.payload or {}
        ingredients = payload.get("ingredients", [])
        if not ingredients:
            packet.findings.append(Finding("empty_formulation", "warning", "no ingredient lines"))
            return
        seen: dict[str, int] = {}
        total = Decimal(0)
        missing_amount = 0
        for i, line in enumerate(ingredients):
            ident = str(
                line.get("materialId") or line.get("alias") or line.get("name") or f"line{i}"
            )
            seen[ident] = seen.get(ident, 0) + 1
            if seen[ident] > 1:
                packet.findings.append(
                    Finding(
                        "duplicate_ingredient_line",
                        "warning",
                        f"'{ident}' appears {seen[ident]} times",
                        subject=ident,
                    )
                )
            amount = line.get("amount") or {}
            value = amount.get("value") if isinstance(amount, dict) else line.get("fraction")
            if value is None:
                missing_amount += 1
                continue
            try:
                total += Decimal(str(value))
            except InvalidOperation:
                packet.findings.append(
                    Finding(
                        "invalid_amount",
                        "blocking",
                        f"ingredient {i} amount is not numeric",
                        subject=ident,
                    )
                )
        if missing_amount:
            packet.findings.append(
                Finding(
                    "missing_amount",
                    "warning",
                    f"{missing_amount} ingredient line(s) carry no amount",
                )
            )
        declared = payload.get("declaredTotal") or payload.get("declared_total")
        tolerance = payload.get("tolerance") or "0.001"
        if declared is not None:
            try:
                gap = abs(total - Decimal(str(declared)))
                if gap > Decimal(str(tolerance)):
                    packet.findings.append(
                        Finding(
                            "composition_total_mismatch",
                            "blocking",
                            f"ingredient sum {total} vs declared total {declared} "
                            f"exceeds tolerance {tolerance}",
                        )
                    )
                else:
                    packet.findings.append(
                        Finding(
                            "composition_total",
                            "info",
                            f"ingredient sum {total} matches declared total {declared} "
                            f"within tolerance {tolerance}",
                        )
                    )
            except InvalidOperation:
                packet.findings.append(
                    Finding(
                        "invalid_declared_total",
                        "blocking",
                        f"declared total '{declared}' is not numeric",
                    )
                )

    def _check_structures(
        self, packet: VerificationPacket, formulation: FormulationRevision | None
    ) -> None:
        """Structural checks for every resolvable structure in the
        formulation — unknown structure stays unknown, never guessed."""
        if formulation is None:
            return
        for i, line in enumerate((formulation.payload or {}).get("ingredients", [])):
            smiles: str | None = line.get("smiles")
            subject = str(line.get("materialId") or line.get("name") or f"line{i}")
            if smiles is None and line.get("materialId"):
                ident = self.db.execute(
                    select(MaterialIdentity).where(
                        MaterialIdentity.workspace_id == self.ctx.workspace_id,
                        MaterialIdentity.id == _as_uuid(line.get("materialId")),
                    )
                ).scalar_one_or_none()
                if ident is not None:
                    if ident.structure_status != "reviewed" or not ident.structure:
                        packet.findings.append(
                            Finding(
                                "structure_unresolved",
                                "unknown",
                                f"identity {subject} has no resolved structure "
                                f"(status={ident.structure_status}) — it is "
                                "reported unknown, not inferred",
                                subject=subject,
                            )
                        )
                        continue
                    smiles = ident.structure
            if smiles is None:
                packet.findings.append(
                    Finding(
                        "structure_missing",
                        "unknown",
                        f"ingredient {subject} carries no structure",
                        subject=subject,
                    )
                )
                continue
            result = self.adapter.describe(smiles=smiles)
            if isinstance(result, EngineError):
                packet.findings.append(
                    Finding(
                        "structure_invalid",
                        "blocking" if result.code != "ENGINE_UNAVAILABLE" else "unknown",
                        f"{result.code}: {result.message[:200]}",
                        subject=subject,
                    )
                )
                packet.structural.append({"subject": subject, "ok": False, "error": result.code})
            else:
                packet.structural.append(
                    {
                        "subject": subject,
                        "ok": True,
                        "canonical_smiles": result.canonical_smiles,
                        "formula": result.formula,
                        "descriptors": result.descriptors,
                        "engine_version": result.engine_version,
                        "evidence_type": "descriptor",
                    }
                )
                packet.findings.append(
                    Finding(
                        "structure_valid",
                        "info",
                        f"parsed + sanitized; canonical {result.canonical_smiles} "
                        f"(rdkit {result.engine_version})",
                        subject=subject,
                    )
                )

    def _closure(self, task: ResearchTask, cand: CandidateRevision) -> dict[str, Any]:
        """Per-metric evidence-requirement assessment (§12.3).

        The verifier's evidence is ``descriptor`` class. A metric
        requiring ``lab_measurement`` (or any class not present) is
        ``missing`` — a structural pass never satisfies a laboratory
        endpoint. The packet proposes a decision; only a human closes.
        """
        contract = None
        if task.current_contract_revision_id is not None:
            contract = self.db.execute(
                select(SuccessContractRevision).where(
                    SuccessContractRevision.id == task.current_contract_revision_id
                )
            ).scalar_one_or_none()
        if contract is None or contract.status != "frozen":
            return {
                "assessable": False,
                "reason": "no frozen contract",
                "metrics": [],
                "missingEvidence": [],
                "supportedSuccessEligible": False,
            }
        present = set(VERIFIER_EVIDENCE)
        metrics: list[dict[str, Any]] = []
        missing: list[str] = []
        # Same contract vocabulary as the task evaluator (PAR-01):
        # canonical 'metrics' wins; legacy 'requiredMetrics' payloads
        # resolve through the explicit read path rather than silently
        # reporting zero requirements.
        resolved = resolve_metrics(contract.payload)
        for m in resolved.metrics:
            required = m.get("required_evidence") or m.get("requiredEvidence") or []
            unmet = [e for e in required if e not in present]
            metrics.append(
                {
                    "id": m.get("id") or m.get("label"),
                    "requiredEvidence": required,
                    "satisfiedBy": sorted(present & set(required)),
                    "status": "evaluable" if not unmet else "missing",
                    "missing": unmet,
                }
            )
            missing.extend(unmet)
        eligible = not missing and bool(
            metrics or contract.payload.get("metrics") is not None
        )
        return {
            "assessable": True,
            "legacyPayload": resolved.legacy,
            "contractIssues": resolved.issues,
            "contractRevisionId": str(contract.id),
            "metrics": metrics,
            "missingEvidence": sorted(set(missing)),
            # Structural evidence alone can never make this true when a
            # lab endpoint is required — it is reported, not bent.
            "supportedSuccessEligible": bool(eligible and not missing),
            "suggestedDecision": "ready_for_review"
            if eligible and not missing
            else "insufficient_evidence",
        }

    @staticmethod
    def _serialize(packet: VerificationPacket) -> dict[str, Any]:
        return {
            "candidateRevisionId": str(packet.candidate_revision_id),
            "findings": [
                {"kind": f.kind, "severity": f.severity, "detail": f.detail, "subject": f.subject}
                for f in packet.findings
            ],
            "structural": packet.structural,
            "evidenceTypes": packet.evidence_types,
            "closure": packet.closure,
            "engine": packet.engine,
        }


def _as_uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None
