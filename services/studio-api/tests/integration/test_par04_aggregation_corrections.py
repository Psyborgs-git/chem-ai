"""PAR-04 — explicit aggregation rules + verified correction lineage.

Audit §PAR-04 regressions (all written failing-first):
- two conflicting readings cannot pass ``single`` merely because one
  passes — conflicting usable readings are inconclusive, never best-of
- an unspecified live aggregation rule is unresolved → inconclusive
  (``fixture-single-value`` was never a safe default for a real rule)
- repeated readings on one batch never inflate the independent-batch
  count, and ``mean`` weighs independent batches — not instrument
  readings — so a batch with more repeats is not overweighted
- a reviewed correction (MeasurementAmendment) supersedes the original
  row: the effective result uses the corrected value exactly once, the
  old signed packet is flagged for reassessment without rewriting it,
  and dataset snapshots carry the corrected value once
- ``supported_failure`` beyond the evaluator's suggestion requires the
  reviewer's own bound evidence and rationale — an unmeasured or
  unsupported experiment cannot be recorded as a measured failure
"""

from __future__ import annotations

import uuid

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext, load_context
from studio.domain.lab.measurements import LabMeasurementService
from studio.domain.learning.datasets import DatasetService
from studio.domain.tasks.evaluation import TaskEvaluationService
from studio.domain.tasks.service import TaskService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    CandidateRevision,
    LabBatch,
    LabExecution,
    LabSample,
    Measurement,
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    SuccessContractRevision,
    TaskDecision,
    Workspace,
)
from studio.persistence.revisions import content_hash

pytestmark = pytest.mark.integration

ORDINARY_METRIC = "metric.synthetic-performance"


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


def _metric(**over) -> dict:
    m = {
        "id": ORDINARY_METRIC,
        "label": "Synthetic index",
        "required": True,
        "operator": "gte",
        "target_values": ["5"],
        "unit": "dimensionless",
        "required_evidence": ["lab_measurement"],
        "aggregation": "single",
    }
    m.update(over)
    return m


def _task(
    session: Session,
    res: ServiceContext,
    *,
    metrics: list[dict] | None = None,
    gates: list[dict] | None = None,
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
    )
    session.add(task)
    session.flush()
    contract = SuccessContractRevision(
        workspace_id=res.workspace_id,
        task_id=task.id,
        revision=1,
        status="frozen",
        payload={
            "metrics": metrics if metrics is not None else [_metric()],
            "hard_constraints": gates or [],
        },
        content_hash="x",
    )
    session.add(contract)
    session.flush()
    task.current_contract_revision_id = contract.id
    session.flush()
    return task


def _candidate(session: Session, ws: Workspace, task: ResearchTask) -> CandidateRevision:
    cand = CandidateRevision(
        workspace_id=ws.id,
        task_id=task.id,
        revision=1,
        status="accepted_for_research",
        eligibility="not_assessed",
        entity_kind="formulation",
        entity_revision_id=None,
        contract_revision_id=task.current_contract_revision_id,
        payload={"proposedDifferences": []},
        content_hash=content_hash({"r": 1}),
    )
    session.add(cand)
    session.flush()
    return cand


def _measurement(
    session: Session,
    res: ServiceContext,
    task: ResearchTask,
    *,
    metric: str = ORDINARY_METRIC,
    value: str = "6",
    batch: LabBatch | None = None,
    sample: LabSample | None = None,
    repeat_type: str = "independent_batch",
) -> Measurement:
    if sample is None:
        if batch is None:
            ex = LabExecution(
                workspace_id=res.workspace_id,
                task_id=task.id,
                status="in_progress",
                historical=True,
            )
            session.add(ex)
            session.flush()
            batch = LabBatch(workspace_id=res.workspace_id, execution_id=ex.id, label="A")
            session.add(batch)
            session.flush()
        sample = LabSample(
            workspace_id=res.workspace_id, batch_id=batch.id, label="a1", kind="aliquot"
        )
        session.add(sample)
        session.flush()
    m = Measurement(
        workspace_id=res.workspace_id,
        sample_id=sample.id,
        method="fixture-index",
        metric=metric,
        repeat_type=repeat_type,
        value_type="numeric",
        value={"kind": "numeric", "value": value, "unit": "dimensionless"},
        status="accepted",
    )
    session.add(m)
    session.flush()
    return m


def _bind(
    session: Session,
    sr: ServiceContext,
    m: Measurement,
    cand: CandidateRevision,
) -> None:
    LabMeasurementService(session, sr).record_applicability(
        m.id,
        candidate_revision_id=cand.id,
        applicable=True,
        rationale="reviewed binding for this candidate",
    )


class TestExplicitAggregation:
    """Requirements 1-2: no silent defaults, no silent best-of."""

    def test_conflicting_readings_cannot_pass_single(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """One passing reading must not outweigh a conflicting accepted
        reading under a single-observation rule (§12.3, audit §PAR-04)."""
        res, sr = ctxs
        task = _task(session, res)
        _measurement(session, res, task, value="6")
        _measurement(session, res, task, value="3")
        report = TaskEvaluationService(session, sr).evaluate(task.id)
        m = report["metrics"][0]
        assert m["verdict"] == "inconclusive"
        assert m["findings"][0]["kind"] == "conflicting_readings"
        assert report["suggestedDecision"] == "inconclusive"
        with pytest.raises(DomainError) as exc:
            TaskService(session, sr).close(
                task_id=task.id, closure_decision="supported_success", packet={}
            )
        assert exc.value.code == ErrorCode.EVIDENCE_INSUFFICIENT

    def test_agreeing_repeats_corroborate_single(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """Same-aliquot repeats that agree do corroborate — the verdict
        is unambiguous and every reading is retained in the report."""
        res, sr = ctxs
        task = _task(session, res)
        m1 = _measurement(session, res, task, value="6")
        m2 = _measurement(session, res, task, value="7")
        report = TaskEvaluationService(session, sr).evaluate(task.id)
        metric = report["metrics"][0]
        assert metric["verdict"] == "met"
        assert sorted(metric["evidenceIds"]) == sorted([str(m1.id), str(m2.id)])

    def test_unspecified_aggregation_is_unresolved(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """No declared aggregation → unresolved, never best-of. A
        passing reading still cannot carry the metric."""
        res, sr = ctxs
        metric = _metric()
        del metric["aggregation"]
        task = _task(session, res, metrics=[metric])
        _measurement(session, res, task, value="9")
        report = TaskEvaluationService(session, sr).evaluate(task.id)
        m = report["metrics"][0]
        assert m["verdict"] == "inconclusive"
        assert m["findings"][0]["kind"] == "aggregation_unresolved"
        assert report["suggestedDecision"] == "inconclusive"
        with pytest.raises(DomainError) as exc:
            TaskService(session, sr).close(
                task_id=task.id, closure_decision="supported_success", packet={}
            )
        assert exc.value.code == ErrorCode.EVIDENCE_INSUFFICIENT

    def test_blank_aggregation_is_unresolved(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        task = _task(session, res, metrics=[_metric(aggregation="  ")])
        _measurement(session, res, task, value="9")
        m = TaskEvaluationService(session, sr).evaluate(task.id)["metrics"][0]
        assert m["verdict"] == "inconclusive"
        assert m["findings"][0]["kind"] == "aggregation_unresolved"


class TestReplicationUnits:
    """Requirement 3: batches are the independent-preparation unit;
    instrument repeats never inflate them and never outweigh them."""

    def test_repeated_readings_do_not_inflate_independent_batches(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        metric = _metric(
            aggregation="mean",
            replication_rule={"minIndependentBatches": 3},
        )
        task = _task(session, res, metrics=[metric])
        # batch A: one batch, three same-sample readings
        ex = LabExecution(
            workspace_id=res.workspace_id, task_id=task.id, status="in_progress", historical=True
        )
        session.add(ex)
        session.flush()
        batch_a = LabBatch(workspace_id=res.workspace_id, execution_id=ex.id, label="A")
        session.add(batch_a)
        session.flush()
        aliquot = LabSample(
            workspace_id=res.workspace_id, batch_id=batch_a.id, label="a1", kind="aliquot"
        )
        session.add(aliquot)
        session.flush()
        for v in ("9", "9", "9"):
            _measurement(
                session, res, task, value=v, sample=aliquot, repeat_type="same_sample"
            )
        _measurement(session, res, task, value="9")  # batch B, one reading
        m = TaskEvaluationService(session, sr).evaluate(task.id)["metrics"][0]
        assert m["verdict"] == "inconclusive"
        assert m["findings"][0]["kind"] == "insufficient_replication"
        assert m["independentBatches"] == 2

    def test_mean_weighs_batches_not_readings(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """batch A [9,9,9] + batch B [1] → per-batch means 9 and 1 →
        mean 5 < 6 misses; the flat mean over readings (7) would have
        let the over-sampled batch carry the verdict."""
        res, sr = ctxs
        metric = _metric(aggregation="mean", target_values=["6"])
        task = _task(session, res, metrics=[metric])
        ex = LabExecution(
            workspace_id=res.workspace_id, task_id=task.id, status="in_progress", historical=True
        )
        session.add(ex)
        session.flush()
        batch_a = LabBatch(workspace_id=res.workspace_id, execution_id=ex.id, label="A")
        session.add(batch_a)
        session.flush()
        aliquot = LabSample(
            workspace_id=res.workspace_id, batch_id=batch_a.id, label="a1", kind="aliquot"
        )
        session.add(aliquot)
        session.flush()
        for v in ("9", "9", "9"):
            _measurement(
                session, res, task, value=v, sample=aliquot, repeat_type="same_sample"
            )
        _measurement(session, res, task, value="1")
        m = TaskEvaluationService(session, sr).evaluate(task.id)["metrics"][0]
        assert m["verdict"] == "misses"
        assert m["independentBatches"] == 2


class TestCorrectionLineage:
    """Requirements 4-5: a reviewed correction yields an immutable
    successor whose reviewed value is used exactly once; signed packets
    and frozen dataset lineage are flagged, never rewritten."""

    def test_reviewed_correction_changes_effective_result(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        task = _task(session, res)
        m = _measurement(session, res, task, value="4")

        ev = TaskEvaluationService(session, sr)
        report = ev.evaluate(task.id)
        assert report["metrics"][0]["verdict"] == "misses"
        assert report["suggestedDecision"] == "supported_failure"
        TaskService(session, sr).close(
            task_id=task.id,
            closure_decision="supported_failure",
            packet=None,
        )
        assert ev.reassessment_status(task.id)["needsReassessment"] is False

        amd = LabMeasurementService(session, sr).amend(
            m.id,
            reason="transcription error — vial label misread",
            source="lab notebook L-114",
            value={"kind": "numeric", "value": "7", "unit": "dimensionless"},
        )

        # the immutable original row is untouched; the correction is
        # the reviewable successor version
        session.refresh(m)
        assert m.status == "superseded"
        assert m.superseded_by == amd.id
        assert m.value["value"] == "4"
        assert amd.reason == "transcription error — vial label misread"
        assert amd.source == "lab notebook L-114"
        assert amd.created_by == sr.principal_id

        # the effective result uses the corrected value — exactly once
        report = ev.evaluate(task.id)
        metric = report["metrics"][0]
        assert metric["verdict"] == "met"
        assert metric["evidenceIds"] == [str(m.id)]
        assert metric["amendedIds"] == [str(m.id)]

        # the old signed packet is flagged — not rewritten
        status = ev.reassessment_status(task.id)
        assert status["needsReassessment"] is True
        assert str(m.id) in {s["id"] for s in status["staleEvidenceIds"]}
        decision = session.execute(
            select(TaskDecision).where(
                TaskDecision.task_id == task.id, TaskDecision.kind == "closure"
            )
        ).scalar_one()
        assert decision.payload["closureDecision"] == "supported_failure"
        manifest_entry = next(
            e
            for e in decision.payload["packet"]["manifest"]["evidence"]
            if e["measurementId"] == str(m.id)
        )
        assert manifest_entry["status"] == "accepted"  # recorded at signing

        # a packet signed after the correction records the effective
        # version explicitly and is not itself stale
        packet = ev.closeout_packet(task.id)
        entry = next(
            e
            for e in packet["manifest"]["evidence"]
            if e["measurementId"] == str(m.id)
        )
        assert entry["status"] == "superseded"
        assert entry["effectiveAmendmentId"] == str(amd.id)
        assert entry["amendment"]["reason"] == "transcription error — vial label misread"
        assert entry["amendment"]["source"] == "lab notebook L-114"
        assert entry["amendment"]["createdBy"] == str(sr.principal_id)
        assert entry["included"] is True

    def test_correction_invalidates_training_lineage_once(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """A frozen dataset snapshot drifts on amend; a new snapshot
        carries the corrected value exactly once — never the old value
        after supersession, never both."""
        res, sr = ctxs
        task = _task(session, res)
        m = _measurement(session, res, task, value="4")

        # snapshots are a governance action — manage_models lives with
        # the workspace owner, not the scientific reviewer
        ws = session.get(Workspace, res.workspace_id)
        owner = _ctx(session, ws, _principal(session, ws, "user", "owner", "own"))
        ds = DatasetService(session, owner)
        snap = ds.build("property_prediction", "d", task_id=task.id)
        entry = next(
            e for e in snap.manifest["entries"] if e["recordId"] == str(m.id)
        )
        assert entry["excluded"] is False
        ds.freeze(snap.id)

        amd = LabMeasurementService(session, sr).amend(
            m.id,
            reason="transcription error",
            source="lab notebook L-114",
            value={"kind": "numeric", "value": "7", "unit": "dimensionless"},
        )
        drift = ds.drift_status(snap.id)
        assert drift["drift"] is True
        assert str(m.id) in drift["changed"]

        snap2 = ds.build("property_prediction", "d2", task_id=task.id)
        entries = [e for e in snap2.manifest["entries"] if e["recordId"] == str(m.id)]
        assert len(entries) == 1
        assert entries[0]["excluded"] is False
        assert entries[0]["semantics"]["effectiveFromAmendment"] == str(amd.id)
        assert entries[0]["semantics"]["correctionReason"] == "transcription error"

    def test_superseded_without_amendment_stays_excluded(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """A superseded row whose amendment is unreachable stays
        excluded — the old value never re-enters evaluation."""
        res, sr = ctxs
        task = _task(session, res)
        m = _measurement(session, res, task, value="9")
        m.status = "superseded"
        m.superseded_by = uuid.uuid4()  # dangling — no amendment row
        session.flush()
        m_report = TaskEvaluationService(session, sr).evaluate(task.id)["metrics"][0]
        assert m_report["verdict"] == "inconclusive"
        assert m_report["findings"][0]["kind"] == "missing"


class TestOutcomeLabels:
    """Requirement 6: outcome labels cannot make an unmeasured or
    unsupported experiment into a recorded failure either — a
    reviewer-recorded supported_failure beyond the evaluator's
    suggestion needs bound evidence and a rationale."""

    def test_evaluator_supported_failure_needs_no_extra_packet(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        task = _task(session, res)
        _measurement(session, res, task, value="3")
        report = TaskEvaluationService(session, sr).evaluate(task.id)
        assert report["suggestedDecision"] == "supported_failure"
        closed = TaskService(session, sr).close(
            task_id=task.id, closure_decision="supported_failure", packet=None
        )
        assert closed.closure_decision == "supported_failure"

    def test_unmeasured_supported_failure_rejected(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        task = _task(session, res)
        report = TaskEvaluationService(session, sr).evaluate(task.id)
        assert report["suggestedDecision"] == "inconclusive"
        with pytest.raises(DomainError) as exc:
            TaskService(session, sr).close(
                task_id=task.id, closure_decision="supported_failure", packet=None
            )
        assert exc.value.code == ErrorCode.EVIDENCE_INSUFFICIENT
        with pytest.raises(DomainError) as exc:
            TaskService(session, sr).close(
                task_id=task.id,
                closure_decision="supported_failure",
                packet={"rationale": "saw it fail"},
            )
        assert exc.value.code == ErrorCode.EVIDENCE_INSUFFICIENT

    def test_reviewer_supported_failure_needs_bound_evidence(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """Evaluator says success; the reviewer may still record a
        supported failure — but only with their rationale and evidence
        bound into the packet they saw."""
        res, sr = ctxs
        task = _task(session, res)
        m = _measurement(session, res, task, value="6")
        report = TaskEvaluationService(session, sr).evaluate(task.id)
        assert report["suggestedDecision"] == "supported_success"

        # rationale without bound evidence → rejected
        with pytest.raises(DomainError) as exc:
            TaskService(session, sr).close(
                task_id=task.id,
                closure_decision="supported_failure",
                packet={"rationale": "vial cracked on inspection"},
            )
        assert exc.value.code == ErrorCode.EVIDENCE_INSUFFICIENT

        # evidence without rationale → rejected
        with pytest.raises(DomainError) as exc:
            TaskService(session, sr).close(
                task_id=task.id,
                closure_decision="supported_failure",
                packet={"evidenceIds": [str(m.id)]},
            )
        assert exc.value.code == ErrorCode.EVIDENCE_INSUFFICIENT

        # evidence the reviewer never saw (not bound into the packet)
        # → rejected
        with pytest.raises(DomainError) as exc:
            TaskService(session, sr).close(
                task_id=task.id,
                closure_decision="supported_failure",
                packet={
                    "rationale": "vial cracked on inspection",
                    "evidenceIds": [str(uuid.uuid4())],
                },
            )
        assert exc.value.code == ErrorCode.EVIDENCE_INSUFFICIENT

        closed = TaskService(session, sr).close(
            task_id=task.id,
            closure_decision="supported_failure",
            packet={
                "rationale": "vial cracked on inspection — measurement "
                "moot (lab notebook L-114)",
                "evidenceIds": [str(m.id)],
            },
        )
        assert closed.closure_decision == "supported_failure"
