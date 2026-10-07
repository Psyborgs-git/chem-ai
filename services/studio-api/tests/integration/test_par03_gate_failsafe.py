"""PAR-03 — hard gates fail safe on unknowns; dependency-aware reassessment.

Audit §PAR-03 regressions (all written failing-first):
- no composition never passes the absence gate — missing candidate,
  invalid entity links, empty/partial formulations, reference products
  with unknown recipes and unresolved ingredient identities all stay
  ``not_evaluated``
- a known excluded ingredient fails the gate
- supported absence passes only its explicitly bounded claim (a
  declared-composition statement — never a toxicology/compliance
  certificate)
- a gate-only measurement amendment/revocation or an applicability
  withdrawal marks the packet for reassessment even when every ordinary
  performance metric is unchanged
- the close command enforces the evidence gate server-side — no
  ``supported_success`` while a hard gate is unproven
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext, load_context
from studio.domain.lab.measurements import LabMeasurementService
from studio.domain.tasks.evaluation import TaskEvaluationService
from studio.domain.tasks.service import TaskService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Approval,
    CandidateRevision,
    FormulationFamily,
    FormulationRevision,
    LabBatch,
    LabExecution,
    LabSample,
    MaterialIdentity,
    Measurement,
    Principal,
    PrincipalCapability,
    Project,
    ReferenceProduct,
    ResearchTask,
    SuccessContractRevision,
    TaskDecision,
    Workspace,
)
from studio.persistence.revisions import content_hash

pytestmark = pytest.mark.integration

ORDINARY_METRIC = "metric.synthetic-performance"
GATE_METRIC = "gate.metric.solvent-index"


def _principal(session: Session, ws: Workspace, kind: str, role: str, login: str) -> Principal:
    p = Principal(workspace_id=ws.id, kind=kind, login=login, display_name=login)
    session.add(p)
    session.flush()
    for cap in sorted(capabilities_for_role(role)):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=p.id, capability=cap))
    session.flush()
    return p


def _ctx(session: Session, ws: Workspace, p: Principal) -> ServiceContext:
    return load_context(session, ws.id, p.id)


@pytest.fixture()
def ctxs(session: Session) -> tuple[ServiceContext, ServiceContext]:
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    res = _principal(session, ws, "user", "researcher", "res")
    sr = _principal(session, ws, "user", "scientific_reviewer", "sr")
    return _ctx(session, ws, res), _ctx(session, ws, sr)


def _identity(
    session: Session,
    ws: Workspace,
    *,
    name: str,
    kind: str = "defined_molecule",
    aliases: list[dict] | None = None,
    identifiers: list[dict] | None = None,
) -> MaterialIdentity:
    ident = MaterialIdentity(
        workspace_id=ws.id,
        kind=kind,
        name=name,
        identifiers=identifiers or [],
        aliases=aliases or [],
        structure_status="none",
        evidence_status="reviewed",
    )
    session.add(ident)
    session.flush()
    return ident


def _formulation(
    session: Session,
    ws: Workspace,
    *,
    lines: list[dict] | None,
    status: str = "accepted",
    completeness: str = "complete",
    approval_id: uuid.UUID | None = None,
    extra: dict | None = None,
) -> FormulationRevision:
    fam = FormulationFamily(workspace_id=ws.id, name="fam")
    session.add(fam)
    session.flush()
    payload: dict = {
        "ingredients": lines,
        "amountBasis": "mass_fraction_as_supplied",
        "declaredTotal": "1",
        "completeness": completeness,
    }
    if extra:
        payload.update(extra)
    rev = FormulationRevision(
        workspace_id=ws.id,
        family_id=fam.id,
        revision=1,
        status=status,
        payload=payload,
        content_hash=content_hash(payload),
        approval_id=approval_id,
    )
    session.add(rev)
    session.flush()
    return rev


def _candidate(
    session: Session,
    ws: Workspace,
    task: ResearchTask,
    *,
    entity_kind: str = "formulation",
    entity_revision_id: uuid.UUID | None = None,
    status: str = "accepted_for_research",
) -> CandidateRevision:
    cand = CandidateRevision(
        workspace_id=ws.id,
        task_id=task.id,
        revision=1,
        status=status,
        eligibility="not_assessed",
        entity_kind=entity_kind,
        entity_revision_id=entity_revision_id,
        contract_revision_id=task.current_contract_revision_id,
        payload={"proposedDifferences": []},
        content_hash=content_hash({"r": 1}),
    )
    session.add(cand)
    session.flush()
    return cand


def _task(
    session: Session,
    res: ServiceContext,
    *,
    gates: list[dict],
    metrics: list[dict] | None = None,
    mode_inputs: dict | None = None,
) -> ResearchTask:
    proj = Project(workspace_id=res.workspace_id, slug="p", name="P")
    session.add(proj)
    session.flush()
    task = ResearchTask(
        workspace_id=res.workspace_id,
        project_id=proj.id,
        mode="improve",
        title="t",
        workflow_state="awaiting_review",
        target_kind="formulation",
        objective="o",
        mode_inputs=mode_inputs or {},
    )
    session.add(task)
    session.flush()
    contract = SuccessContractRevision(
        workspace_id=res.workspace_id,
        task_id=task.id,
        revision=1,
        status="frozen",
        payload={
            "metrics": metrics
            if metrics is not None
            else [
                {
                    "id": ORDINARY_METRIC,
                    "label": "Synthetic index",
                    "required": True,
                    "operator": "gte",
                    "target_values": ["5"],
                    "unit": "dimensionless",
                    "required_evidence": ["lab_measurement"],
                    "aggregation": "fixture-single-value",
                }
            ],
            "hard_constraints": gates,
        },
        content_hash="x",
    )
    session.add(contract)
    session.flush()
    task.current_contract_revision_id = contract.id
    session.flush()
    return task


def _absent_gate(identity_id: uuid.UUID | str, **extra) -> dict:
    check = {"kind": "ingredient_absent", "materialIdentityId": str(identity_id)}
    check.update(extra)
    return {
        "id": "gate.solvent-absent",
        "text": "excluded solvent must not be present",
        "check": check,
    }


def _metric_gate() -> dict:
    return {
        "id": "gate.solvent-index",
        "text": "solvent index must stay under the gate limit",
        "check": {
            "kind": "metric",
            "id": GATE_METRIC,
            "operator": "lte",
            "target_values": ["0.1"],
            "unit": "dimensionless",
            "required_evidence": ["lab_measurement"],
            "aggregation": "fixture-single-value",
        },
    }


def _measurement(
    session: Session,
    res: ServiceContext,
    task: ResearchTask,
    *,
    metric: str = ORDINARY_METRIC,
    value: str = "6",
    method: str = "fixture-index",
    pipeline_version: str | None = "pipeline-a",
) -> Measurement:
    ex = LabExecution(
        workspace_id=res.workspace_id, task_id=task.id, status="in_progress", historical=True
    )
    session.add(ex)
    session.flush()
    batch = LabBatch(workspace_id=res.workspace_id, execution_id=ex.id, label="A")
    session.add(batch)
    session.flush()
    sample = LabSample(workspace_id=res.workspace_id, batch_id=batch.id, label="a1", kind="aliquot")
    session.add(sample)
    session.flush()
    m = Measurement(
        workspace_id=res.workspace_id,
        sample_id=sample.id,
        method=method,
        metric=metric,
        repeat_type="independent_batch",
        value_type="numeric",
        value={"kind": "numeric", "value": value, "unit": "dimensionless"},
        status="accepted",
        pipeline_version=pipeline_version,
    )
    session.add(m)
    session.flush()
    return m


def _bind(
    session: Session,
    sr: ServiceContext,
    m: Measurement,
    cand: CandidateRevision,
    *,
    contract_revision_id: uuid.UUID | None = None,
) -> None:
    LabMeasurementService(session, sr).record_applicability(
        m.id,
        candidate_revision_id=cand.id,
        contract_revision_id=contract_revision_id,
        applicable=True,
        rationale="reviewed binding for this candidate",
    )


def _close(
    session: Session,
    sr: ServiceContext,
    task: ResearchTask,
    cand: CandidateRevision | None = None,
) -> dict:
    ev = TaskEvaluationService(session, sr)
    packet = ev.closeout_packet(
        task.id,
        candidate_revision_id=cand.id if cand is not None else None,
    )
    TaskService(session, sr).close(
        task_id=task.id,
        closure_decision="supported_success",
        candidate_revision_id=cand.id if cand is not None else None,
        packet=packet,
    )
    return packet


def _gate(report: dict, gid: str = "gate.solvent-absent") -> dict:
    return next(g for g in report["gates"] if g["id"] == gid)


class TestAbsenceGateFailSafe:
    """Requirement 1-2: unknown or missing composition is never `pass`."""

    def test_no_candidate_never_passes(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        target = _identity(session, session.get(Workspace, res.workspace_id), name="solvent-x")
        task = _task(session, res, gates=[_absent_gate(target.id)])
        _measurement(session, res, task)  # ordinary metric satisfied
        report = TaskEvaluationService(session, sr).evaluate(task.id)
        gate = _gate(report)
        assert gate["verdict"] == "not_evaluated"
        assert gate["findings"][0]["kind"] == "no_bound_candidate"
        assert report["suggestedDecision"] == "inconclusive"
        assert report["supportedSuccessEligible"] is False
        # the server-side close guard — the button cannot be relied on
        with pytest.raises(DomainError) as exc:
            TaskService(session, sr).close(
                task_id=task.id, closure_decision="supported_success", packet={}
            )
        assert exc.value.code == ErrorCode.EVIDENCE_INSUFFICIENT

    def test_candidate_without_entity_link(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        ws = session.get(Workspace, res.workspace_id)
        target = _identity(session, ws, name="solvent-x")
        task = _task(session, res, gates=[_absent_gate(target.id)])
        cand = _candidate(session, ws, task, entity_revision_id=None)
        m = _measurement(session, res, task)
        _bind(session, sr, m, cand)
        report = TaskEvaluationService(session, sr).evaluate(task.id)
        gate = _gate(report)
        assert gate["verdict"] == "not_evaluated"
        assert gate["findings"][0]["kind"] == "entity_link_missing"
        # candidate still reported for research, carrying its block
        assert report["candidates"][0]["blocks"][0]["kind"] == "entity_link_missing"

    def test_invalid_entity_link(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        ws = session.get(Workspace, res.workspace_id)
        target = _identity(session, ws, name="solvent-x")
        task = _task(session, res, gates=[_absent_gate(target.id)])
        cand = _candidate(session, ws, task, entity_revision_id=uuid.uuid4())
        m = _measurement(session, res, task)
        _bind(session, sr, m, cand)
        report = TaskEvaluationService(session, sr).evaluate(task.id)
        assert _gate(report)["verdict"] == "not_evaluated"

    def test_draft_formulation_not_evaluated(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        ws = session.get(Workspace, res.workspace_id)
        target = _identity(session, ws, name="solvent-x")
        rev = _formulation(session, ws, lines=[{"materialId": str(target.id)}], status="draft")
        task = _task(session, res, gates=[_absent_gate(target.id)])
        cand = _candidate(session, ws, task, entity_revision_id=rev.id)
        m = _measurement(session, res, task)
        _bind(session, sr, m, cand)
        gate = _gate(TaskEvaluationService(session, sr).evaluate(task.id))
        assert gate["verdict"] == "not_evaluated"
        assert gate["findings"][0]["kind"] == "composition_unreviewed"

    def test_empty_ingredient_list_not_evaluated(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        ws = session.get(Workspace, res.workspace_id)
        target = _identity(session, ws, name="solvent-x")
        rev = _formulation(session, ws, lines=[])
        task = _task(session, res, gates=[_absent_gate(target.id)])
        cand = _candidate(session, ws, task, entity_revision_id=rev.id)
        m = _measurement(session, res, task)
        _bind(session, sr, m, cand)
        gate = _gate(TaskEvaluationService(session, sr).evaluate(task.id))
        assert gate["verdict"] == "not_evaluated"
        assert gate["findings"][0]["kind"] == "composition_empty"

    def test_partial_composition_not_evaluated(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        ws = session.get(Workspace, res.workspace_id)
        target = _identity(session, ws, name="solvent-x")
        # legacy/imported row accepted before the completeness rule
        rev = _formulation(
            session,
            ws,
            lines=[{"materialId": str(uuid.uuid4())}],
            completeness="draft",
        )
        task = _task(session, res, gates=[_absent_gate(target.id)])
        cand = _candidate(session, ws, task, entity_revision_id=rev.id)
        m = _measurement(session, res, task)
        _bind(session, sr, m, cand)
        gate = _gate(TaskEvaluationService(session, sr).evaluate(task.id))
        assert gate["verdict"] == "not_evaluated"
        assert gate["findings"][0]["kind"] == "composition_incomplete"

    def test_unresolved_ingredient_identity_blocks_pass(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        ws = session.get(Workspace, res.workspace_id)
        target = _identity(session, ws, name="solvent-x")
        other = _identity(session, ws, name="water")
        rev = _formulation(
            session,
            ws,
            lines=[
                {"materialId": str(other.id), "role": "carrier"},
                # supplier-only line — the registry cannot prove it is
                # (or is not) the excluded material
                {"supplier": "Acme Corp", "supplierSku": "A-991"},
            ],
        )
        task = _task(session, res, gates=[_absent_gate(target.id)])
        cand = _candidate(session, ws, task, entity_revision_id=rev.id)
        m = _measurement(session, res, task)
        _bind(session, sr, m, cand)
        gate = _gate(TaskEvaluationService(session, sr).evaluate(task.id))
        assert gate["verdict"] == "not_evaluated"
        kinds = {f["kind"] for f in gate["findings"]}
        assert "ingredient_identity_unresolved" in kinds

    def test_reference_product_unknown_recipe(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        ws = session.get(Workspace, res.workspace_id)
        target = _identity(session, ws, name="solvent-x")
        product = ReferenceProduct(
            workspace_id=ws.id, name="store-bought", composition_knowledge="unknown"
        )
        session.add(product)
        session.flush()
        task = _task(
            session,
            res,
            gates=[_absent_gate(target.id, subject="reference_product")],
            mode_inputs={"referenceProductId": str(product.id)},
        )
        _measurement(session, res, task)
        gate = _gate(TaskEvaluationService(session, sr).evaluate(task.id))
        assert gate["verdict"] == "not_evaluated"
        assert gate["findings"][0]["kind"] == "composition_unknown"

    def test_analytical_claim_not_supported_by_recipe(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """A recipe review never upgrades into an analytical absence."""
        res, sr = ctxs
        ws = session.get(Workspace, res.workspace_id)
        target = _identity(session, ws, name="solvent-x")
        other = _identity(session, ws, name="water")
        rev = _formulation(session, ws, lines=[{"materialId": str(other.id)}])
        task = _task(session, res, gates=[_absent_gate(target.id, basis="analytical")])
        cand = _candidate(session, ws, task, entity_revision_id=rev.id)
        m = _measurement(session, res, task)
        _bind(session, sr, m, cand)
        gate = _gate(TaskEvaluationService(session, sr).evaluate(task.id))
        assert gate["verdict"] == "not_evaluated"
        assert gate["findings"][0]["kind"] == "basis_not_supported"

    def test_missing_target_identity_id_not_evaluated(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        ws = session.get(Workspace, res.workspace_id)
        other = _identity(session, ws, name="water")
        rev = _formulation(session, ws, lines=[{"materialId": str(other.id)}])
        task = _task(
            session,
            res,
            gates=[
                {
                    "id": "gate.bad-target",
                    "text": "no target",
                    "check": {"kind": "ingredient_absent"},
                }
            ],
        )
        cand = _candidate(session, ws, task, entity_revision_id=rev.id)
        m = _measurement(session, res, task)
        _bind(session, sr, m, cand)
        report = TaskEvaluationService(session, sr).evaluate(task.id)
        gate = next(g for g in report["gates"] if g["id"] == "gate.bad-target")
        assert gate["verdict"] == "not_evaluated"
        assert gate["findings"][0]["kind"] == "target_identity_missing"


class TestAbsenceGateVerdicts:
    """Requirement 1: excluded ingredient fails; supported absence is bounded."""

    def _setup(
        self,
        session: Session,
        ctxs: tuple[ServiceContext, ServiceContext],
        lines: list[dict],
        target: MaterialIdentity,
    ) -> ResearchTask:
        res, sr = ctxs
        ws = session.get(Workspace, res.workspace_id)
        rev = _formulation(session, ws, lines=lines)
        task = _task(session, res, gates=[_absent_gate(target.id)])
        cand = _candidate(session, ws, task, entity_revision_id=rev.id)
        m = _measurement(session, res, task)
        _bind(session, sr, m, cand)
        return task

    def _target(self, session: Session, ws: Workspace) -> MaterialIdentity:
        return _identity(
            session,
            ws,
            name="heptane",
            aliases=[{"name": "n-heptane", "source": "import"}],
            identifiers=[{"scheme": "cas", "value": "142-82-5", "source": "import"}],
        )

    def test_excluded_ingredient_by_id_fails(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        ws = session.get(Workspace, res.workspace_id)
        target = self._target(session, ws)
        task = self._setup(
            session,
            ctxs,
            [{"materialId": str(target.id), "role": "solvent"}],
            target,
        )
        report = TaskEvaluationService(session, sr).evaluate(task.id)
        gate = _gate(report)
        assert gate["verdict"] == "fail"
        assert gate["findings"][0]["kind"] == "excluded_ingredient_present"
        assert report["suggestedDecision"] == "supported_failure"
        with pytest.raises(DomainError) as exc:
            TaskService(session, sr).close(
                task_id=task.id, closure_decision="supported_success", packet={}
            )
        assert exc.value.code == ErrorCode.EVIDENCE_INSUFFICIENT

    def test_excluded_ingredient_by_alias_fails(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """An ingredient line that names the target by alias fails."""
        ws = session.get(Workspace, ctxs[0].workspace_id)
        target = self._target(session, ws)
        task = self._setup(session, ctxs, [{"name": "n-heptane", "role": "solvent"}], target)
        report = TaskEvaluationService(session, ctxs[1]).evaluate(task.id)
        gate = _gate(report)
        assert gate["verdict"] == "fail"
        assert gate["findings"][0]["kind"] == "excluded_ingredient_present"

    def test_excluded_ingredient_by_identifier_fails(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        ws = session.get(Workspace, ctxs[0].workspace_id)
        target = self._target(session, ws)
        task = self._setup(
            session,
            ctxs,
            [{"identifier": {"scheme": "cas", "value": "142-82-5"}}],
            target,
        )
        report = TaskEvaluationService(session, ctxs[1]).evaluate(task.id)
        assert _gate(report)["verdict"] == "fail"

    def test_supported_absence_passes_bounded_claim(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        ws = session.get(Workspace, res.workspace_id)
        target = self._target(session, ws)
        water = _identity(session, ws, name="water")
        task = self._setup(
            session, ctxs, [{"materialId": str(water.id), "role": "carrier"}], target
        )
        report = TaskEvaluationService(session, sr).evaluate(task.id)
        gate = _gate(report)
        assert gate["verdict"] == "pass"
        # the claim is explicitly bounded — a declared-composition
        # statement, not an analytical or compliance certificate
        assert gate["claimBasis"] == "declared_composition"
        assert "declared composition" in gate["claimBound"]
        assert "not an analytical" in gate["claimBound"]
        assert report["suggestedDecision"] == "supported_success"
        assert report["supportedSuccessEligible"] is True


class TestGateEvidenceManifest:
    """Requirement 3: gate evidence + dependencies in the packet manifest."""

    def test_gate_evidence_joins_packet(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        ws = session.get(Workspace, res.workspace_id)
        target = _identity(session, ws, name="solvent-x")
        water = _identity(session, ws, name="water")
        rev = _formulation(session, ws, lines=[{"materialId": str(water.id)}])
        task = _task(session, res, gates=[_metric_gate(), _absent_gate(target.id)])
        cand = _candidate(session, ws, task, entity_revision_id=rev.id)
        ordinary = _measurement(session, res, task)
        gate_m = _measurement(
            session, res, task, metric=GATE_METRIC, value="0.05", method="fixture-gate"
        )
        contract_id = task.current_contract_revision_id
        _bind(session, sr, ordinary, cand, contract_revision_id=contract_id)
        _bind(session, sr, gate_m, cand, contract_revision_id=contract_id)

        ev = TaskEvaluationService(session, sr)
        packet = ev.closeout_packet(task.id, candidate_revision_id=cand.id)
        # gate evidence must appear alongside ordinary metric evidence
        assert str(gate_m.id) in packet["evidenceIds"]
        assert str(ordinary.id) in packet["evidenceIds"]

        manifest = packet["manifest"]
        rows = {e["measurementId"]: e for e in manifest["evidence"]}
        assert rows[str(gate_m.id)]["method"] == "fixture-gate"
        assert rows[str(gate_m.id)]["pipelineVersion"] == "pipeline-a"
        assert rows[str(gate_m.id)]["status"] == "accepted"

        # composition + identity dependencies are recorded
        deps = manifest["gateDependencies"]
        comp = next(d for d in deps if d["gateId"] == "gate.solvent-absent")
        assert comp["materialIdentityId"] == str(target.id)
        assert comp["compositionRevisionId"] == str(rev.id)
        assert comp["compositionContentHash"] == rev.content_hash
        assert comp["compositionCompleteness"] == "complete"
        assert comp["candidateRevisionId"] == str(cand.id)
        assert str(target.id) in manifest["dependencies"]["materialIdentityIds"]
        assert str(rev.id) in manifest["dependencies"]["compositionRevisionIds"]


class TestDependencyReassessment:
    """Requirement 4: any supporting-dependency change marks reassessment."""

    def _closed_gate_packet(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> tuple[ResearchTask, CandidateRevision, Measurement, Measurement]:
        res, sr = ctxs
        ws = session.get(Workspace, res.workspace_id)
        target = _identity(session, ws, name="solvent-x")
        water = _identity(session, ws, name="water")
        rev = _formulation(session, ws, lines=[{"materialId": str(water.id)}])
        task = _task(session, res, gates=[_metric_gate(), _absent_gate(target.id)])
        cand = _candidate(session, ws, task, entity_revision_id=rev.id)
        ordinary = _measurement(session, res, task)
        gate_m = _measurement(
            session, res, task, metric=GATE_METRIC, value="0.05", method="fixture-gate"
        )
        _bind(session, sr, ordinary, cand)
        _bind(session, sr, gate_m, cand)
        packet = _close(session, sr, task, cand)
        assert str(gate_m.id) in packet["evidenceIds"]
        assert (
            TaskEvaluationService(session, sr).reassessment_status(task.id)["needsReassessment"]
            is False
        )
        return task, cand, ordinary, gate_m

    def test_gate_only_amendment_marks_reassessment(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """Amending a measurement used only by a hard gate flags the
        packet even though every ordinary metric row is untouched."""
        task, _cand, ordinary, gate_m = self._closed_gate_packet(session, ctxs)
        sr = ctxs[1]
        LabMeasurementService(session, sr).amend(
            gate_m.id,
            reason="gate value was misread",
            value={"kind": "numeric", "value": "0.2", "unit": "dimensionless"},
        )
        status = TaskEvaluationService(session, sr).reassessment_status(task.id)
        assert status["needsReassessment"] is True
        stale = {s["id"]: s["status"] for s in status["staleEvidenceIds"]}
        assert stale[str(gate_m.id)] == "superseded"
        assert str(ordinary.id) not in stale
        # signed packet untouched
        decision = session.execute(
            select(TaskDecision).where(
                TaskDecision.task_id == task.id, TaskDecision.kind == "closure"
            )
        ).scalar_one()
        assert str(gate_m.id) in decision.payload["packet"]["evidenceIds"]

    def test_applicability_withdrawal_marks_reassessment(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """Withdrawal keeps integrity `accepted` yet flips applicability —
        still a reassessment trigger."""
        task, cand, _ordinary, gate_m = self._closed_gate_packet(session, ctxs)
        sr = ctxs[1]
        LabMeasurementService(session, sr).withdraw_applicability(
            gate_m.id, candidate_revision_id=cand.id
        )
        session.refresh(gate_m)
        assert gate_m.status == "accepted"  # integrity untouched
        status = TaskEvaluationService(session, sr).reassessment_status(task.id)
        assert status["needsReassessment"] is True
        assert "applicability_changed" in status["changedDependencies"]

    def test_inapplicability_flag_marks_reassessment(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """set_applicability(False) on gate-only evidence — accepted status
        preserved — flags reassessment."""
        task, _cand, _ordinary, gate_m = self._closed_gate_packet(session, ctxs)
        sr = ctxs[1]
        LabMeasurementService(session, sr).set_applicability(
            gate_m.id, applicable=False, note="deviated from gate protocol"
        )
        session.refresh(gate_m)
        assert gate_m.status == "accepted"
        status = TaskEvaluationService(session, sr).reassessment_status(task.id)
        assert status["needsReassessment"] is True
        assert "applicability_changed" in status["changedDependencies"]

    def test_composition_dependency_drift_marks_reassessment(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """Superseding the formulation revision the gate relied on flags
        the packet even though measurements are unchanged."""
        task, _cand, _ordinary, _gate_m = self._closed_gate_packet(session, ctxs)
        sr = ctxs[1]
        deps = (
            session.execute(
                select(TaskDecision).where(
                    TaskDecision.task_id == task.id, TaskDecision.kind == "closure"
                )
            )
            .scalar_one()
            .payload["packet"]["manifest"]["gateDependencies"]
        )
        comp = next(d for d in deps if d["gateId"] == "gate.solvent-absent")
        rev = session.get(FormulationRevision, uuid.UUID(comp["compositionRevisionId"]))
        # a newer revision in the same family supersedes the bound one
        rev.status = "superseded"
        session.flush()
        status = TaskEvaluationService(session, sr).reassessment_status(task.id)
        assert status["needsReassessment"] is True
        assert "composition_changed" in status["changedDependencies"]

    def test_target_identity_change_marks_reassessment(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """Editing the excluded material's identity after closeout (e.g.
        new accepted alias that would match an ingredient) flags it."""
        task, _cand, _ordinary, _gate_m = self._closed_gate_packet(session, ctxs)
        sr = ctxs[1]
        deps = (
            session.execute(
                select(TaskDecision).where(
                    TaskDecision.task_id == task.id, TaskDecision.kind == "closure"
                )
            )
            .scalar_one()
            .payload["packet"]["manifest"]["gateDependencies"]
        )
        target = session.get(MaterialIdentity, uuid.UUID(deps[0]["materialIdentityId"]))
        target.aliases = [{"name": "water", "source": "post-hoc merge"}]
        target.version += 1
        session.flush()
        status = TaskEvaluationService(session, sr).reassessment_status(task.id)
        assert status["needsReassessment"] is True
        assert "target_identity_changed" in status["changedDependencies"]

    def test_approval_revocation_marks_reassessment(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """Revoking a source approval recorded in the manifest flags it —
        the mechanism by which pending approvals are invalidated."""
        res, sr = ctxs
        ws = session.get(Workspace, res.workspace_id)
        target = _identity(session, ws, name="solvent-x")
        water = _identity(session, ws, name="water")
        # frozen revisions are immutable — the source approval is bound
        # at revision creation, as the real accept flow does
        approval = Approval(
            workspace_id=ws.id,
            action="formulation.revision.accept",
            decision="approved",
            decided_by=sr.principal_id,
            bound_digest="d" * 64,
            bound_inputs={"formulation": "fam"},
            policy_version="p1",
        )
        session.add(approval)
        session.flush()
        rev = _formulation(
            session,
            ws,
            lines=[{"materialId": str(water.id)}],
            approval_id=approval.id,
        )
        task = _task(session, res, gates=[_metric_gate(), _absent_gate(target.id)])
        cand = _candidate(session, ws, task, entity_revision_id=rev.id)
        ordinary = _measurement(session, res, task)
        gate_m = _measurement(
            session, res, task, metric=GATE_METRIC, value="0.05", method="fixture-gate"
        )
        _bind(session, sr, ordinary, cand)
        _bind(session, sr, gate_m, cand)

        ev = TaskEvaluationService(session, sr)
        packet = ev.closeout_packet(task.id, candidate_revision_id=cand.id)
        approval_ids = packet["manifest"]["dependencies"]["approvalIds"]
        assert str(approval.id) in approval_ids
        TaskService(session, sr).close(
            task_id=task.id,
            closure_decision="supported_success",
            candidate_revision_id=cand.id,
            packet=packet,
        )

        approval.revoked_at = datetime.now(UTC)
        session.flush()
        status = ev.reassessment_status(task.id)
        assert status["needsReassessment"] is True
        assert "approval_revoked" in status["changedDependencies"]
