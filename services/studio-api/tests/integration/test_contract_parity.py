"""PAR-01 — one canonical contract vocabulary end to end.

The pre-fix editor wrote ``requiredMetrics`` while the evaluator read
``metrics`` — a UI-saved contract evaluated as zero requirements.
These tests pin the shared schema: UI/canonical payloads round-trip
through draft → freeze → evaluation, legacy ``requiredMetrics``
payloads resolve through the explicit read path, and a payload that
carries nothing evaluable may not freeze (or, for already-persisted
history, evaluate as assessable).
"""

from __future__ import annotations

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext, load_context
from studio.domain.tasks.evaluation import TaskEvaluationService
from studio.domain.tasks.service import TaskService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    LabBatch,
    LabExecution,
    LabSample,
    Measurement,
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    SuccessContractRevision,
    Workspace,
)
from studio.persistence.revisions import content_hash

pytestmark = pytest.mark.integration


def _ctx(session: Session) -> tuple[ServiceContext, Project]:
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    p = Principal(workspace_id=ws.id, kind="user", login="res", display_name="res")
    session.add(p)
    session.flush()
    for cap in sorted(capabilities_for_role("researcher")):
        session.add(
            PrincipalCapability(workspace_id=ws.id, principal_id=p.id, capability=cap)
        )
    session.flush()
    proj = Project(workspace_id=ws.id, slug="p", name="P")
    session.add(proj)
    session.flush()
    return load_context(session, ws.id, p.id), proj


def _task(session: Session, ctx: ServiceContext, project: Project) -> ResearchTask:
    task = ResearchTask(
        workspace_id=ctx.workspace_id,
        project_id=project.id,
        mode="discover",
        title="t",
        workflow_state="active",
        target_kind="formulation",
        objective="o",
    )
    session.add(task)
    session.flush()
    return task


def _accepted_measurement(
    session: Session, ctx: ServiceContext, task: ResearchTask,
    *, metric: str, value: str, unit: str,
) -> None:
    ex = LabExecution(
        workspace_id=ctx.workspace_id,
        task_id=task.id,
        status="in_progress",
        historical=True,
    )
    session.add(ex)
    session.flush()
    batch = LabBatch(workspace_id=ctx.workspace_id, execution_id=ex.id, label="A")
    session.add(batch)
    session.flush()
    sample = LabSample(
        workspace_id=ctx.workspace_id, batch_id=batch.id, label="a1", kind="aliquot"
    )
    session.add(sample)
    session.flush()
    session.add(
        Measurement(
            workspace_id=ctx.workspace_id,
            sample_id=sample.id,
            method="fixture",
            metric=metric,
            repeat_type="independent_batch",
            value_type="numeric",
            value={"kind": "numeric", "value": value, "unit": unit},
            status="accepted",
        )
    )
    session.flush()


class TestServiceRoundTrip:
    def test_canonical_payload_round_trips_to_evaluator(
        self, session: Session
    ) -> None:
        """The exact id/operator/unit/target the editor emits reaches
        the evaluator — a measurement in the same unit meets it."""
        ctx, project = _ctx(session)
        task = _task(session, ctx, project)
        svc = TaskService(session, ctx)
        rev = svc.draft_contract(
            task_id=task.id,
            payload={
                "schema_version": "1.0.0",
                "fixture_only": True,
                "metrics": [
                    {
                        "id": "metric.viscosity",
                        "label": "viscosity",
                        "required": True,
                        "value_kind": "numeric",
                        "operator": "gte",
                        "target_values": ["500"],
                        "unit": "mPa·s",
                        "method_revision_id": None,
                        "conditions": {
                            "substrate_revision_id": None,
                            "description": "",
                        },
                        "required_evidence": ["lab_measurement"],
                        "aggregation": "single",
                        "replication_rule": None,
                    }
                ],
                "hard_constraints": [],
                "unknowns": [],
            },
        )
        svc.freeze_contract(revision_id=rev.id)
        _accepted_measurement(
            session, ctx, task, metric="metric.viscosity", value="600", unit="mPa·s"
        )
        report = TaskEvaluationService(session, ctx).evaluate(task.id)
        assert report["assessable"] is True
        assert report["legacyPayload"] is False
        m = report["metrics"][0]
        assert m["metricId"] == "metric.viscosity"
        assert m["verdict"] == "met"
        assert report["suggestedDecision"] == "supported_success"

    def test_legacy_ui_payload_evaluates_through_read_path(
        self, session: Session
    ) -> None:
        """The pre-PAR-01 editor shape — requiredMetrics with nested
        target {value, unit} — must keep evaluating (never silently
        zero metrics), flagged as a legacy payload for review."""
        ctx, project = _ctx(session)
        task = _task(session, ctx, project)
        svc = TaskService(session, ctx)
        rev = svc.draft_contract(
            task_id=task.id,
            payload={
                "requiredMetrics": [
                    {
                        "name": "viscosity",
                        "operator": ">=",
                        "target": {"value": "500", "unit": "mPa·s"},
                    }
                ]
            },
        )
        svc.freeze_contract(revision_id=rev.id)
        # the stored row is byte-identical — history is never rewritten
        stored = session.get(SuccessContractRevision, rev.id)
        assert stored is not None
        assert stored.payload["requiredMetrics"][0]["target"]["value"] == "500"
        _accepted_measurement(
            session, ctx, task, metric="viscosity", value="600", unit="mPa·s"
        )
        report = TaskEvaluationService(session, ctx).evaluate(task.id)
        assert report["assessable"] is True
        assert report["legacyPayload"] is True
        m = report["metrics"][0]
        assert m["metricId"] == "viscosity"
        # PAR-04: a legacy payload declares no scientifically reviewed
        # aggregation rule — unresolved/inconclusive, never best-of
        assert m["verdict"] == "inconclusive"
        assert any(f["kind"] == "aggregation_unresolved" for f in m["findings"])

    def test_ambiguous_legacy_entry_is_an_issue_not_a_verdict(
        self, session: Session
    ) -> None:
        """A legacy entry that cannot translate contributes an explicit
        review issue — it never reads as a satisfied or failed clause."""
        ctx, project = _ctx(session)
        task = _task(session, ctx, project)
        svc = TaskService(session, ctx)
        rev = svc.draft_contract(
            task_id=task.id,
            payload={
                "metrics": [{"name": "purity", "target": ">= 99"}],
                "requiredMetrics": [{"operator": ">="}],
            },
        )
        svc.freeze_contract(revision_id=rev.id)
        report = TaskEvaluationService(session, ctx).evaluate(task.id)
        # canonical metrics win; the ambiguous legacy entry is surfaced
        assert len(report["metrics"]) == 1
        assert report["metrics"][0]["metricId"] == "purity"
        assert any("requiredMetrics" in u for u in report["contractIssues"])


class TestFreezeGate:
    def test_unknown_fields_stay_draft(self, session: Session) -> None:
        """A draft preserves unknown fields; they cannot freeze into an
        assessable contract silently."""
        ctx, project = _ctx(session)
        task = _task(session, ctx, project)
        svc = TaskService(session, ctx)
        rev = svc.draft_contract(
            task_id=task.id,
            payload={
                "metrics": [{"name": "gloss", "target": ">= 80"}],
                "thresholds": {"gloss": ">80"},
            },
        )
        assert rev.status == "draft"
        with pytest.raises(DomainError) as exc:
            svc.freeze_contract(revision_id=rev.id)
        assert exc.value.code == ErrorCode.VALIDATION
        assert "thresholds" in exc.value.message
        session.refresh(rev)
        assert rev.status == "draft"

    def test_contract_without_metrics_cannot_freeze(
        self, session: Session
    ) -> None:
        ctx, project = _ctx(session)
        task = _task(session, ctx, project)
        svc = TaskService(session, ctx)
        rev = svc.draft_contract(task_id=task.id, payload={"unknowns": []})
        with pytest.raises(DomainError) as exc:
            svc.freeze_contract(revision_id=rev.id)
        assert "evaluable metrics" in exc.value.message

    def test_declared_unknowns_cannot_freeze(self, session: Session) -> None:
        ctx, project = _ctx(session)
        task = _task(session, ctx, project)
        svc = TaskService(session, ctx)
        rev = svc.draft_contract(
            task_id=task.id,
            payload={
                "metrics": [{"name": "gloss", "target": ">= 80"}],
                "unknowns": ["substrate unclear"],
            },
        )
        with pytest.raises(DomainError) as exc:
            svc.freeze_contract(revision_id=rev.id)
        assert "unknowns" in exc.value.message

    def test_malformed_metric_rejected_at_draft(self, session: Session) -> None:
        ctx, project = _ctx(session)
        task = _task(session, ctx, project)
        svc = TaskService(session, ctx)
        with pytest.raises(DomainError) as exc:
            svc.draft_contract(
                task_id=task.id, payload={"metrics": [{"id": "m.x", "bogus": 1}]}
            )
        assert exc.value.code == ErrorCode.VALIDATION

    def test_revision_identity_fields_rejected(self, session: Session) -> None:
        ctx, project = _ctx(session)
        task = _task(session, ctx, project)
        svc = TaskService(session, ctx)
        with pytest.raises(DomainError):
            svc.draft_contract(
                task_id=task.id,
                payload={"metrics": [{"name": "m", "target": ">= 1"}], "revision": 4},
            )


class TestPersistedNonCanonicalContracts:
    def test_persisted_payload_without_metrics_is_not_assessable(
        self, session: Session
    ) -> None:
        """Already-frozen history (e.g. thresholds-only payloads frozen
        before the gate existed) evaluates honestly: not assessable,
        inconclusive, with the reason reported — never rewritten."""
        ctx, project = _ctx(session)
        task = _task(session, ctx, project)
        payload = {"thresholds": {"gloss": ">80"}}
        contract = SuccessContractRevision(
            workspace_id=ctx.workspace_id,
            task_id=task.id,
            revision=1,
            status="frozen",
            payload=payload,
            content_hash=content_hash(payload),
        )
        session.add(contract)
        session.flush()
        task.current_contract_revision_id = contract.id
        session.flush()
        report = TaskEvaluationService(session, ctx).evaluate(task.id)
        assert report["assessable"] is False
        assert report["suggestedDecision"] == "inconclusive"
        assert report["supportedSuccessEligible"] is False
        assert report["contractIssues"]
        # stored bytes untouched
        session.refresh(contract)
        assert contract.payload == {"thresholds": {"gloss": ">80"}}
