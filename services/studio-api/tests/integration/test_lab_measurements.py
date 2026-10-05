"""CS-0502 — samples, executions and measurement review.

AT-0502-1  three readings of one aliquot are not three independent
           batches (repeat-type-aware replication accounting)
AT-0502-2  incompatible unit/method → contract comparison is
           inconclusive with an actionable finding
AT-0502-3  amendment corrects without overwriting — original stays
           immutable and is flagged superseded
"""

from __future__ import annotations

import uuid

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext, load_context
from studio.domain.lab.measurements import LabMeasurementService
from studio.domain.lab.plans import LabPlanService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    LabExecution,
    Measurement,
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    Workspace,
)

pytestmark = pytest.mark.integration


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
    researcher = _principal(session, ws, "user", "researcher", "res")
    reviewer = _principal(session, ws, "user", "scientific_reviewer", "sr")
    return _ctx(session, ws, researcher), _ctx(session, ws, reviewer)


def _task(session: Session, workspace_id: uuid.UUID) -> ResearchTask:
    proj = Project(workspace_id=workspace_id, slug="p", name="P")
    session.add(proj)
    session.flush()
    task = ResearchTask(
        workspace_id=workspace_id,
        project_id=proj.id,
        mode="discover",
        title="t",
        workflow_state="active",
        target_kind="formulation",
        objective="o",
    )
    session.add(task)
    session.flush()
    return task


def _approved_plan(session: Session, res: ServiceContext, sr: ServiceContext, task: ResearchTask):
    svc = LabPlanService(session, res)
    plan = svc.create(
        task.id,
        title="viscosity confirmation",
        payload={
            "method": "ASTM D2196",
            "samplePlan": [{"batch": "A", "aliquots": 2}],
            "acceptanceCriteria": "viscosity within band",
            "hazardNotes": "none",
            "resourceNeeds": "viscometer",
        },
    )
    svc.submit(plan.id)
    LabPlanService(session, sr).review(plan.id, decision="approved", rationale="ok")
    return plan


def _sample(session: Session, res: ServiceContext, ex: LabExecution):
    svc = LabMeasurementService(session, res)
    batch = svc.add_batch(ex.id, label="batch-A")
    return svc, svc.add_sample(batch.id, label="aliquot-1")


def _numeric(value: str, unit: str) -> dict:
    return {"kind": "numeric", "value": value, "unit": unit}


class TestReplicationAccounting:
    def test_three_readings_one_aliquot_not_three_batches(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """AT-0502-1: three ``same_sample`` readings on one aliquot are
        repeated observations — the independent-batch count stays 1."""
        res, sr = ctxs
        task = _task(session, res.workspace_id)
        plan = _approved_plan(session, res, sr, task)
        svc = LabMeasurementService(session, res)
        ex = svc.open_execution(plan.id)
        _, sample = _sample(session, res, ex)

        for v in ("612", "608", "615"):
            svc.record_measurement(
                sample.id,
                method="ASTM D2196",
                repeat_type="same_sample",
                value=_numeric(v, "mPa·s"),
            )

        summary = svc.replication_summary(ex.id)
        assert summary["independentBatches"] == 1
        assert summary["observations"] == 3
        assert summary["byRepeatType"]["same_sample"] == 3
        assert summary["byRepeatType"]["independent_batch"] == 0

    def test_independent_batches_count_as_replicates(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """Two independently prepared batches ARE two independent
        trials — the distinction is recorded, not inferred."""
        res, sr = ctxs
        task = _task(session, res.workspace_id)
        plan = _approved_plan(session, res, sr, task)
        svc = LabMeasurementService(session, res)
        ex = svc.open_execution(plan.id)
        for label in ("batch-A", "batch-B"):
            b = svc.add_batch(ex.id, label=label)
            s = svc.add_sample(b.id, label="aliquot-1")
            svc.record_measurement(
                s.id,
                method="ASTM D2196",
                repeat_type="independent_batch",
                value=_numeric("610", "mPa·s"),
            )
        summary = svc.replication_summary(ex.id)
        assert summary["independentBatches"] == 2
        assert summary["byRepeatType"]["independent_batch"] == 2


class TestContractComparison:
    def _measurement(
        self, session: Session, res: ServiceContext, sr: ServiceContext, value: dict
    ) -> Measurement:
        task = _task(session, res.workspace_id)
        plan = _approved_plan(session, res, sr, task)
        svc = LabMeasurementService(session, res)
        ex = svc.open_execution(plan.id)
        _, sample = _sample(session, res, ex)
        return svc.record_measurement(
            sample.id, method="ASTM D2196", repeat_type="same_sample", value=value
        )

    def test_incompatible_unit_is_inconclusive_with_action(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """AT-0502-2: mass_fraction vs a viscosity target is a
        dimensional mismatch → inconclusive + actionable finding,
        never a forced verdict."""
        res, sr = ctxs
        m = self._measurement(session, res, sr, _numeric("0.4", "mass_fraction"))
        svc = LabMeasurementService(session, res)
        out = svc.compare_to_contract(m.id, {"name": "viscosity", "target": ">= 500 mPa·s"})
        assert out["verdict"] == "inconclusive"
        kinds = {f["kind"] for f in out["findings"]}
        assert "unit_incompatible" in kinds
        assert any(f["action"] for f in out["findings"])

    def test_convertible_unit_passes(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """0.65 Pa·s converts to 650 mPa·s — same-category whitelisted
        conversion yields a real verdict."""
        res, sr = ctxs
        m = self._measurement(session, res, sr, _numeric("0.65", "Pa·s"))
        svc = LabMeasurementService(session, res)
        out = svc.compare_to_contract(m.id, {"name": "viscosity", "target": ">= 500 mPa·s"})
        assert out["verdict"] == "pass"
        assert out["converted"] is True

    def test_missing_value_type_inconclusive(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        m = self._measurement(session, res, sr, {"kind": "missing", "reason": "instrument_failure"})
        svc = LabMeasurementService(session, res)
        out = svc.compare_to_contract(m.id, {"name": "viscosity", "target": ">= 500 mPa·s"})
        assert out["verdict"] == "inconclusive"
        assert out["findings"][0]["kind"] == "value_type"


class TestAmendment:
    def test_amendment_supersedes_without_overwrite(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """AT-0502-3: the original value row is never overwritten;
        status flips to superseded and points at the amendment."""
        res, sr = ctxs
        task = _task(session, res.workspace_id)
        plan = _approved_plan(session, res, sr, task)
        svc = LabMeasurementService(session, res)
        ex = svc.open_execution(plan.id)
        _, sample = _sample(session, res, ex)
        m = svc.record_measurement(
            sample.id,
            method="ASTM D2196",
            repeat_type="same_sample",
            value=_numeric("615", "mPa·s"),
        )
        LabMeasurementService(session, sr).review(m.id, decision="accepted")

        amd = LabMeasurementService(session, sr).amend(
            m.id,
            reason="transcription error — raw file reads 650",
            source="operator notebook p.12",
            value=_numeric("650", "mPa·s"),
        )
        session.refresh(m)
        assert m.status == "superseded"
        assert m.superseded_by == amd.id
        assert m.value["value"] == "615"  # original preserved
        assert amd.value["value"] == "650"
        assert amd.reason == "transcription error — raw file reads 650"

    def test_amend_rejected_when_not_accepted(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        task = _task(session, res.workspace_id)
        plan = _approved_plan(session, res, sr, task)
        svc = LabMeasurementService(session, res)
        ex = svc.open_execution(plan.id)
        _, sample = _sample(session, res, ex)
        m = svc.record_measurement(
            sample.id,
            method="ASTM D2196",
            repeat_type="same_sample",
            value=_numeric("615", "mPa·s"),
        )
        with pytest.raises(DomainError) as err:
            LabMeasurementService(session, sr).amend(
                m.id, reason="fix", value=_numeric("650", "mPa·s")
            )
        assert err.value.code == ErrorCode.CONFLICT

    def test_applicability_is_separate_from_integrity(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """§14.2: accepted as raw, rejected for the contract — both
        facts coexist."""
        res, sr = ctxs
        task = _task(session, res.workspace_id)
        plan = _approved_plan(session, res, sr, task)
        svc = LabMeasurementService(session, res)
        ex = svc.open_execution(plan.id)
        _, sample = _sample(session, res, ex)
        m = svc.record_measurement(
            sample.id,
            method="ASTM D2196",
            repeat_type="same_sample",
            value=_numeric("615", "mPa·s"),
            conditions={"planned": {"temperature": "25 °C"}, "actual": {"temperature": "40 °C"}},
        )
        rev = LabMeasurementService(session, sr)
        rev.review(m.id, decision="accepted")
        rev.set_applicability(
            m.id, applicable=False, note="temperature deviation outside contract band"
        )
        session.refresh(m)
        assert m.status == "accepted"
        assert m.applicable is False
        assert "temperature" in (m.applicability_note or "")

    def test_historical_execution_is_marked_and_unapproved(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """§14.1: historical experiments record without preapproval —
        marked historical; no release approval is fabricated."""
        res, _sr = ctxs
        task = _task(session, res.workspace_id)
        svc = LabMeasurementService(session, res)
        ex = svc.import_historical(task.id, payload={"method": "legacy notebook"})
        assert ex.historical is True
        assert ex.plan_id is None

        # an unapproved plan can never open an execution
        plan = LabPlanService(session, res).create(
            task.id, title="draft plan", payload={"method": "m"}
        )
        with pytest.raises(DomainError) as err:
            svc.open_execution(plan.id)
        assert err.value.code == ErrorCode.CONFLICT

    def test_stale_approval_blocks_execution_open(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        """Same stale-approval semantics as packet export: an edit
        after approval blocks a new execution (AT-0501-1 extended)."""
        res, sr = ctxs
        task = _task(session, res.workspace_id)
        plan = _approved_plan(session, res, sr, task)
        svc = LabMeasurementService(session, res)
        svc.open_execution(plan.id)  # valid while untouched

        LabPlanService(session, res).update(plan.id, payload={"method": "ASTM D4402"})
        with pytest.raises(DomainError) as err:
            svc.open_execution(plan.id)
        assert err.value.code == ErrorCode.APPROVAL_STALE

    def test_closed_execution_rejects_writes(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext]
    ) -> None:
        res, sr = ctxs
        task = _task(session, res.workspace_id)
        plan = _approved_plan(session, res, sr, task)
        svc = LabMeasurementService(session, res)
        ex = svc.open_execution(plan.id)
        batch = svc.add_batch(ex.id, label="batch-A")
        sample = svc.add_sample(batch.id, label="aliquot-1")
        svc.close_execution(ex.id)
        with pytest.raises(DomainError) as err:
            svc.record_measurement(
                sample.id,
                method="ASTM D2196",
                repeat_type="same_sample",
                value=_numeric("1", "mPa·s"),
            )
        assert err.value.code == ErrorCode.CONFLICT
