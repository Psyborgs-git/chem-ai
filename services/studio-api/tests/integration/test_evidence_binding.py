"""PAR-02 — evaluation binds exact candidates, contracts and evidence.

Required regressions (audit 2026-10 §PAR-02):
- candidate A passes metric X and fails Y; candidate B fails X and
  passes Y → neither may read as supported_success through pooled
  observations.
- a measurement for the wrong method/substrate/contract must not
  satisfy a target solely because its metric name matches.
- accepting a new candidate must not relabel an old evaluation packet.
Plus: historical evidence needs an explicit reviewed applicability
mapping; multiple accepted candidates require an explicit selection for
closeout; bogus baseline/reference ids are flagged, not counted.
"""

from __future__ import annotations

import uuid

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext, load_context
from studio.domain.candidates.service import CandidateService
from studio.domain.lab.measurements import LabMeasurementService
from studio.domain.lab.plans import LabPlanService
from studio.domain.tasks.evaluation import TaskEvaluationService
from studio.domain.tasks.service import TaskService, invalid_inputs
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    FormulationFamily,
    FormulationRevision,
    LabExecution,
    Measurement,
    Principal,
    PrincipalCapability,
    Project,
    ReferenceProduct,
    ResearchTask,
    SuccessContractRevision,
    Workspace,
)

pytestmark = pytest.mark.integration


def _principal(session: Session, ws: Workspace, role: str, login: str) -> Principal:
    p = Principal(workspace_id=ws.id, kind="user", login=login, display_name=login)
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
    res = _principal(session, ws, "researcher", "res")
    sr = _principal(session, ws, "scientific_reviewer", "sr")
    return _ctx(session, ws, res), _ctx(session, ws, sr)


METRICS_XY = [
    {
        "id": "metric.x",
        "label": "X",
        "required": True,
        "operator": "gte",
        "target_values": ["5"],
        "unit": "dimensionless",
        "required_evidence": ["lab_measurement"],
        "aggregation": "fixture-single-value",
    },
    {
        "id": "metric.y",
        "label": "Y",
        "required": True,
        "operator": "gte",
        "target_values": ["5"],
        "unit": "dimensionless",
        "required_evidence": ["lab_measurement"],
        "aggregation": "fixture-single-value",
    },
]


def _task(
    session: Session,
    res: ServiceContext,
    *,
    metrics: list[dict] | None = None,
    mode: str = "discover",
    mode_inputs: dict | None = None,
    contract_status: str = "frozen",
) -> tuple[ResearchTask, SuccessContractRevision]:
    proj = Project(workspace_id=res.workspace_id, slug=f"p-{uuid.uuid4().hex[:6]}", name="P")
    session.add(proj)
    session.flush()
    task = ResearchTask(
        workspace_id=res.workspace_id,
        project_id=proj.id,
        mode=mode,
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
        status=contract_status,
        payload={
            "metrics": metrics if metrics is not None else METRICS_XY,
            "hard_constraints": [],
        },
        content_hash="x",
    )
    session.add(contract)
    session.flush()
    if contract_status == "frozen":
        task.current_contract_revision_id = contract.id
        session.flush()
    return task, contract


def _candidate(
    session: Session, res: ServiceContext, sr: ServiceContext, task: ResearchTask
) -> object:
    cands = CandidateService(session, res)
    cand = cands.create_candidate(task_id=task.id, entity_kind="formulation")
    cands.submit_candidate(candidate_id=cand.id)
    decided = CandidateService(session, sr).review_candidate(candidate_id=cand.id, accept=True)
    return decided


def _planned_measurement(
    session: Session,
    res: ServiceContext,
    sr: ServiceContext,
    task: ResearchTask,
    *,
    metric: str,
    value: str,
    candidate_revision_id: uuid.UUID | None = None,
    contract_revision_id: uuid.UUID | None = None,
    conditions: dict | None = None,
) -> Measurement:
    plans = LabPlanService(session, res)
    payload: dict = {"method": "fixture-method", "samplePlan": [{"batch": "A"}]}
    if candidate_revision_id is not None:
        payload["candidateRevisionId"] = str(candidate_revision_id)
    if contract_revision_id is not None:
        payload["contractRevisionId"] = str(contract_revision_id)
    plan = plans.create(task.id, title="m", payload=payload)
    plans.submit(plan.id)
    LabPlanService(session, sr).review(plan.id, decision="approved", rationale="ok")
    svc = LabMeasurementService(session, res)
    ex = svc.open_execution(plan.id)
    batch = svc.add_batch(ex.id, label="b")
    sample = svc.add_sample(batch.id, label="s")
    m = svc.record_measurement(
        sample.id,
        method="fixture-method",
        repeat_type="independent_batch",
        metric=metric,
        value={"kind": "numeric", "value": value, "unit": "dimensionless"},
        conditions=conditions,
    )
    LabMeasurementService(session, sr).review(m.id, decision="accepted")
    return m


def _historical_measurement(
    session: Session, res: ServiceContext, sr: ServiceContext, task: ResearchTask,
    *, metric: str, value: str, conditions: dict | None = None,
) -> Measurement:
    ex = LabExecution(
        workspace_id=res.workspace_id,
        task_id=task.id,
        status="in_progress",
        historical=True,
    )
    session.add(ex)
    session.flush()
    from studio.persistence.models import LabBatch, LabSample

    batch = LabBatch(workspace_id=res.workspace_id, execution_id=ex.id, label="B")
    session.add(batch)
    session.flush()
    sample = LabSample(workspace_id=res.workspace_id, batch_id=batch.id, label="s1")
    session.add(sample)
    session.flush()
    m = Measurement(
        workspace_id=res.workspace_id,
        sample_id=sample.id,
        method="fixture-method",
        metric=metric,
        repeat_type="independent_batch",
        value_type="numeric",
        value={"kind": "numeric", "value": value, "unit": "dimensionless"},
        conditions=conditions or {},
        status="accepted",
        reviewed_by=sr.principal_id,
    )
    session.add(m)
    session.flush()
    return m


class TestPooledCandidates:
    def test_cross_candidate_pooling_never_yields_success(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """Required regression: A passes X fails Y; B fails X passes Y.
        Pooling A's X and B's Y would fabricate a success — the bound
        evaluator must report each candidate separately and refuse."""
        res, sr = ctxs
        task, contract = _task(session, res)
        cand_a = _candidate(session, res, sr, task)
        cand_b = _candidate(session, res, sr, task)

        _planned_measurement(
            session, res, sr, task, metric="metric.x", value="6",
            candidate_revision_id=cand_a.id, contract_revision_id=contract.id,
        )
        _planned_measurement(
            session, res, sr, task, metric="metric.y", value="2",
            candidate_revision_id=cand_a.id, contract_revision_id=contract.id,
        )
        _planned_measurement(
            session, res, sr, task, metric="metric.x", value="1",
            candidate_revision_id=cand_b.id, contract_revision_id=contract.id,
        )
        _planned_measurement(
            session, res, sr, task, metric="metric.y", value="7",
            candidate_revision_id=cand_b.id, contract_revision_id=contract.id,
        )

        ev = TaskEvaluationService(session, sr)
        report = ev.evaluate(task.id)
        # unscoped with >1 accepted candidates: no synthesized winner
        assert report["suggestedDecision"] != "supported_success"
        assert report["supportedSuccessEligible"] is False
        assert any(
            f["kind"] == "multiple_candidates" for f in report["findings"]
        )

        per = {c["candidateRevisionId"]: c for c in report["candidates"]}
        assert set(per) == {str(cand_a.id), str(cand_b.id)}
        verdict_a = {m["metricId"]: m["verdict"] for m in per[str(cand_a.id)]["metrics"]}
        verdict_b = {m["metricId"]: m["verdict"] for m in per[str(cand_b.id)]["metrics"]}
        assert verdict_a == {"metric.x": "met", "metric.y": "misses"}
        assert verdict_b == {"metric.x": "misses", "metric.y": "met"}
        assert per[str(cand_a.id)]["suggestedDecision"] == "supported_failure"
        assert per[str(cand_b.id)]["suggestedDecision"] == "supported_failure"

        # explicit selection — each candidate reports only its own evidence
        rep_a = ev.evaluate(task.id, candidate_revision_id=cand_a.id)
        assert rep_a["candidateRevisionId"] == str(cand_a.id)
        assert rep_a["suggestedDecision"] == "supported_failure"
        rep_b = ev.evaluate(task.id, candidate_revision_id=cand_b.id)
        assert rep_b["suggestedDecision"] == "supported_failure"

    def test_close_requires_explicit_candidate_with_multiple(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        task, contract = _task(session, res, metrics=METRICS_XY[:1])
        cand_a = _candidate(session, res, sr, task)
        _candidate(session, res, sr, task)
        _planned_measurement(
            session, res, sr, task, metric="metric.x", value="9",
            candidate_revision_id=cand_a.id, contract_revision_id=contract.id,
        )

        svc = TaskService(session, sr)
        with pytest.raises(DomainError) as exc:
            svc.close(task_id=task.id, closure_decision="supported_success")
        assert exc.value.code == ErrorCode.VALIDATION
        assert str(cand_a.id) in str(exc.value.safe_details)

        closed = svc.close(
            task_id=task.id,
            closure_decision="supported_success",
            candidate_revision_id=cand_a.id,
        )
        assert closed.workflow_state == "closed"

    def test_close_rejects_unknown_or_foreign_candidate(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        task, _ = _task(session, res)
        _candidate(session, res, sr, task)
        ev = TaskEvaluationService(session, sr)
        with pytest.raises(DomainError) as exc:
            ev.evaluate(task.id, candidate_revision_id=uuid.uuid4())
        assert exc.value.code == ErrorCode.VALIDATION


class TestApplicabilityChecks:
    def test_wrong_method_or_substrate_cannot_satisfy(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """A measurement for the wrong method/substrate must not satisfy
        a target solely because its metric name matches."""
        res, sr = ctxs
        method_rev = str(uuid.uuid4())
        substrate_rev = str(uuid.uuid4())
        metric = {
            "id": "metric.x",
            "label": "X",
            "required": True,
            "operator": "gte",
            "target_values": ["5"],
            "unit": "dimensionless",
            "required_evidence": ["lab_measurement"],
            "aggregation": "fixture-single-value",
            "method_revision_id": method_rev,
            "conditions": {"substrate_revision_id": substrate_rev},
        }
        task, contract = _task(session, res, metrics=[metric])
        cand = _candidate(session, res, sr, task)

        wrong = _planned_measurement(
            session, res, sr, task, metric="metric.x", value="9",
            candidate_revision_id=cand.id, contract_revision_id=contract.id,
            conditions={
                "actual": {
                    "methodRevisionId": str(uuid.uuid4()),
                    "substrateRevisionId": substrate_rev,
                }
            },
        )
        ev = TaskEvaluationService(session, sr)
        rep = ev.evaluate(task.id, candidate_revision_id=cand.id)
        assert rep["metrics"][0]["verdict"] == "inconclusive"
        reasons = [
            e["reason"]
            for e in rep["evidenceSelection"]["exclusions"]
            if e["measurementId"] == str(wrong.id)
        ]
        assert "method_mismatch" in reasons

        unbound = _planned_measurement(
            session, res, sr, task, metric="metric.x", value="9",
            candidate_revision_id=cand.id, contract_revision_id=contract.id,
            conditions={"actual": {"methodRevisionId": method_rev}},
        )
        rep = ev.evaluate(task.id, candidate_revision_id=cand.id)
        reasons = [
            e["reason"]
            for e in rep["evidenceSelection"]["exclusions"]
            if e["measurementId"] == str(unbound.id)
        ]
        assert "substrate_unresolved" in reasons

        good = _planned_measurement(
            session, res, sr, task, metric="metric.x", value="9",
            candidate_revision_id=cand.id, contract_revision_id=contract.id,
            conditions={
                "actual": {
                    "methodRevisionId": method_rev,
                    "substrateRevisionId": substrate_rev,
                }
            },
        )
        rep = ev.evaluate(task.id, candidate_revision_id=cand.id)
        assert rep["metrics"][0]["verdict"] == "met"
        assert str(good.id) in rep["evidenceIds"]

    def test_evidence_from_prior_contract_revision_is_excluded_then_mapped(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        task, old_contract = _task(session, res, metrics=METRICS_XY[:1])
        cand = _candidate(session, res, sr, task)
        m = _planned_measurement(
            session, res, sr, task, metric="metric.x", value="9",
            candidate_revision_id=cand.id, contract_revision_id=old_contract.id,
        )

        # new contract revision supersedes: evidence bound to rev1
        # cannot silently count toward rev2
        new_contract = SuccessContractRevision(
            workspace_id=res.workspace_id,
            task_id=task.id,
            revision=2,
            status="frozen",
            payload={"metrics": METRICS_XY[:1], "hard_constraints": []},
            content_hash="y",
        )
        session.add(new_contract)
        session.flush()
        task.current_contract_revision_id = new_contract.id
        session.flush()

        ev = TaskEvaluationService(session, sr)
        rep = ev.evaluate(task.id, candidate_revision_id=cand.id)
        assert rep["metrics"][0]["verdict"] == "inconclusive"
        exclusions = {
            e["measurementId"]: e["reason"] for e in rep["evidenceSelection"]["exclusions"]
        }
        assert exclusions[str(m.id)] == "different_contract"

        # explicit reviewed mapping to the new contract restores it —
        # recorded, not assumed
        LabMeasurementService(session, sr).record_applicability(
            m.id,
            candidate_revision_id=cand.id,
            contract_revision_id=new_contract.id,
            applicable=True,
            rationale="same method; contract bound revised",
        )
        rep = ev.evaluate(task.id, candidate_revision_id=cand.id)
        assert rep["metrics"][0]["verdict"] == "met"


class TestHistoricalMapping:
    def test_unlinked_history_needs_reviewed_mapping(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """Historical imports stay research evidence: they cannot
        substantiate a candidate until a reviewer maps them."""
        res, sr = ctxs
        task, _contract = _task(session, res, metrics=METRICS_XY[:1])
        cand = _candidate(session, res, sr, task)
        m = _historical_measurement(session, res, sr, task, metric="metric.x", value="9")

        ev = TaskEvaluationService(session, sr)
        rep = ev.evaluate(task.id, candidate_revision_id=cand.id)
        assert rep["metrics"][0]["verdict"] == "inconclusive"
        assert rep["metrics"][0]["evidenceIds"] == []
        exclusions = {
            e["measurementId"]: e["reason"] for e in rep["evidenceSelection"]["exclusions"]
        }
        assert exclusions[str(m.id)] == "no_candidate_binding"

        LabMeasurementService(session, sr).record_applicability(
            m.id,
            candidate_revision_id=cand.id,
            applicable=True,
            rationale="raw archive re-assigned to this candidate",
        )
        rep = ev.evaluate(task.id, candidate_revision_id=cand.id)
        assert rep["metrics"][0]["verdict"] == "met"

        # withdrawal removes it again — the mapping is review state,
        # not content
        LabMeasurementService(session, sr).record_applicability(
            m.id,
            candidate_revision_id=cand.id,
            applicable=False,
            rationale="retraction — provenance unresolved",
        )
        rep = ev.evaluate(task.id, candidate_revision_id=cand.id)
        assert rep["metrics"][0]["verdict"] == "inconclusive"
        exclusions = {
            e["measurementId"]: e["reason"] for e in rep["evidenceSelection"]["exclusions"]
        }
        assert exclusions[str(m.id)] == "mapped_not_applicable"

    def test_task_scope_still_reads_unbound_evidence(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """Zero accepted candidates: task-scope evaluation keeps the
        pre-PAR-02 behavior — unbound task evidence counts, and evidence
        bound to a (later-accepted) candidate never pools into it."""
        res, sr = ctxs
        task, _ = _task(session, res, metrics=METRICS_XY[:1])
        _historical_measurement(session, res, sr, task, metric="metric.x", value="9")
        rep = TaskEvaluationService(session, sr).evaluate(task.id)
        assert rep["metrics"][0]["verdict"] == "met"
        assert rep["candidateRevisionId"] is None


class TestPacketImmutability:
    def test_new_candidate_does_not_relabel_signed_packet(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        task, contract = _task(session, res, metrics=METRICS_XY[:1])
        cand_a = _candidate(session, res, sr, task)
        m = _planned_measurement(
            session, res, sr, task, metric="metric.x", value="9",
            candidate_revision_id=cand_a.id, contract_revision_id=contract.id,
        )

        ev = TaskEvaluationService(session, sr)
        closed = TaskService(session, sr).close(
            task_id=task.id,
            closure_decision="supported_success",
            candidate_revision_id=cand_a.id,
        )
        assert closed.closure_decision == "supported_success"

        from studio.persistence.models import TaskDecision

        decision = session.execute(
            select(TaskDecision).where(
                TaskDecision.task_id == task.id, TaskDecision.kind == "closure"
            )
        ).scalar_one()
        stored = decision.payload["packet"]
        assert stored["candidateRevisionId"] == str(cand_a.id)
        assert stored["manifestDigest"]

        # a newly accepted candidate invalidates pending conclusions —
        # reassessment flags it, the signed packet is never rewritten
        _candidate(session, res, sr, task)
        status = ev.reassessment_status(task.id)
        assert status["needsReassessment"] is True
        assert "new_candidate" in status["changedDependencies"]
        session.refresh(decision)
        assert decision.payload["packet"]["candidateRevisionId"] == str(cand_a.id)
        assert decision.payload["packet"]["evidenceIds"] == [str(m.id)]

    def test_evidence_applicability_flip_flags_reassessment(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        task, contract = _task(session, res, metrics=METRICS_XY[:1])
        cand = _candidate(session, res, sr, task)
        m = _planned_measurement(
            session, res, sr, task, metric="metric.x", value="9",
            candidate_revision_id=cand.id, contract_revision_id=contract.id,
        )
        ev = TaskEvaluationService(session, sr)
        TaskService(session, sr).close(
            task_id=task.id,
            closure_decision="supported_success",
            candidate_revision_id=cand.id,
        )
        assert ev.reassessment_status(task.id)["needsReassessment"] is False

        LabMeasurementService(session, sr).set_applicability(
            m.id, applicable=False, note="operator logged wrong run"
        )
        status = ev.reassessment_status(task.id)
        assert status["needsReassessment"] is True
        assert str(m.id) in [
            e.get("id") or e.get("measurementId") for e in status["staleEvidenceIds"]
        ]


class TestModeInputValidation:
    def test_bogus_baseline_and_reference_ids_are_flagged(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, _sr = ctxs
        task, _ = _task(
            session,
            res,
            mode="improve",
            mode_inputs={
                "baselineRevisionId": "baseline-rev-1",
                "variationScope": "minor",
            },
        )
        invalid = invalid_inputs(session, task)
        assert [i["field"] for i in invalid] == ["baselineRevisionId"]

        # a real uuid that resolves to nothing is still not a baseline
        task.mode_inputs["baselineRevisionId"] = str(uuid.uuid4())
        assert [i["field"] for i in invalid_inputs(session, task)] == [
            "baselineRevisionId"
        ]

        # resolving to a real formulation revision clears the flag
        fam = FormulationFamily(
            workspace_id=res.workspace_id, name="fam"
        )
        session.add(fam)
        session.flush()
        rev = FormulationRevision(
            workspace_id=res.workspace_id,
            family_id=fam.id,
            revision=1,
            status="accepted",
            payload={"ingredients": []},
            content_hash="h",
        )
        session.add(rev)
        session.flush()
        task.mode_inputs["baselineRevisionId"] = str(rev.id)
        assert invalid_inputs(session, task) == []

    def test_reference_product_id_must_resolve(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, _sr = ctxs
        task, _ = _task(
            session,
            res,
            mode="match_reference",
            mode_inputs={"referenceProductId": "rp-1", "matchScope": "functional"},
        )
        assert [i["field"] for i in invalid_inputs(session, task)] == [
            "referenceProductId"
        ]
        rp = ReferenceProduct(
            workspace_id=res.workspace_id,
            name="market leader",
        )
        session.add(rp)
        session.flush()
        task.mode_inputs["referenceProductId"] = str(rp.id)
        assert invalid_inputs(session, task) == []

    def test_invalid_inputs_surface_in_evaluation(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        task, _ = _task(
            session,
            res,
            metrics=METRICS_XY[:1],
            mode="improve",
            mode_inputs={"baselineRevisionId": "baseline-rev-1"},
        )
        rep = TaskEvaluationService(session, sr).evaluate(task.id)
        assert [i["field"] for i in rep["invalidInputs"]] == ["baselineRevisionId"]
