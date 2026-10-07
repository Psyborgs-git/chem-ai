"""PAR-05 — record-derived provenance vs scientific validation.

Audit repair: the closeout packet's ``fixtureOnly`` was a hardcoded
constant and the UI rendered a fixture-only badge unconditionally.
Provenance is now derived per record from the fields the domain
already stores — declared markers, naming markers, import provenance
(``LabExecution.historical``), review state — and the packet flag is
derived over the *bound* evidence:

- all-synthetic → ``fixtureOnly`` stays true (existing synthetic tests
  keep passing as synthetic);
- mixed → the packet lists which origin classes are present;
- real-origin-only → provenance is real while ``scientificValidation``
  stays ``not_validated`` (a real upload never upgrades the method /
  independent-validation axes — U14 stays unresolved);
- unclassifiable → ``unknown``, honestly.

Corpus plane: dataset manifests label every record's origin; an
``unknown`` origin is excluded at build and an included record without
established provenance blocks ``freeze`` — the same plane that blocks
unresolved training rights (AT-0601-2). The SFT eligibility gate
re-derives provenance live so a record whose origin drifts to
``unknown``/mismatched after freeze cannot train (AT-0801-2). Export
carries each record's origin and refuses ``unknown``.
"""

from __future__ import annotations

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext, load_context
from studio.domain.learning.datasets import DatasetService
from studio.domain.learning.exports.transform import TransformService
from studio.domain.learning.property_models import PropertyModelService
from studio.domain.tasks.evaluation import TaskEvaluationService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Artifact,
    EvidenceClaim,
    ExtractedRecord,
    ImportBatch,
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

pytestmark = pytest.mark.integration


def _principal(session: Session, ws: Workspace, role: str, login: str) -> Principal:
    p = Principal(workspace_id=ws.id, kind="user", login=login, display_name=login)
    session.add(p)
    session.flush()
    for cap in sorted(capabilities_for_role(role)):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=p.id, capability=cap))
    session.flush()
    return p


@pytest.fixture()
def ctxs(session: Session) -> tuple[ServiceContext, ServiceContext, ServiceContext]:
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    res = _principal(session, ws, "researcher", "res")
    sr = _principal(session, ws, "scientific_reviewer", "sr")
    own = _principal(session, ws, "owner", "own")
    return (
        load_context(session, ws.id, res.id),
        load_context(session, ws.id, sr.id),
        load_context(session, ws.id, own.id),
    )


def _task(session: Session, res: ServiceContext) -> ResearchTask:
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
            "metrics": [
                {
                    "id": "metric.synthetic-performance",
                    "label": "Synthetic test-only index",
                    "required": True,
                    "operator": "gte",
                    "target_values": ["5"],
                    "unit": "dimensionless",
                    "required_evidence": ["lab_measurement"],
                    "aggregation": "fixture-single-value",
                }
            ],
            "hard_constraints": [],
        },
        content_hash="x",
    )
    session.add(contract)
    session.flush()
    task.current_contract_revision_id = contract.id
    session.flush()
    return task


def _measurement(
    session: Session,
    res: ServiceContext,
    task: ResearchTask,
    *,
    method: str = "fixture-index",
    metric: str = "metric.synthetic-performance",
    value: str = "6",
    historical: bool = True,
    conditions: dict | None = None,
    pipeline_version: str | None = None,
    status: str = "accepted",
) -> Measurement:
    ex = LabExecution(
        workspace_id=res.workspace_id,
        task_id=task.id,
        status="in_progress",
        historical=historical,
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
        status=status,
        conditions=conditions or {},
        pipeline_version=pipeline_version,
    )
    session.add(m)
    session.flush()
    return m


def _supplier_claim(
    session: Session,
    ws: Workspace,
    *,
    training_rights: str = "allowed",
    kind: str = "document_claim",
    resolvable: bool = True,
) -> EvidenceClaim:
    art = Artifact(
        workspace_id=ws.id,
        storage_key="aa/" + "a" * 62,
        media_type="text/csv",
        byte_size=4,
        checksum_sha256="a" * 64,
        original_name="supplier.csv",
        rights={"training": training_rights, "export": "allowed"},
    )
    session.add(art)
    session.flush()
    batch = ImportBatch(
        workspace_id=ws.id,
        artifact_id=art.id,
        checksum_sha256="a" * 64,
        original_name="supplier.csv",
        detected_type="csv",
        parser_name="csv",
        parser_version="1",
        document_group=art.id,
        status="parsed",
    )
    session.add(batch)
    session.flush()
    rec = ExtractedRecord(
        workspace_id=ws.id,
        batch_id=batch.id,
        kind="row",
        locator={"row": 1},
        original_text="supplier says viscosity 900",
        payload={},
        status="accepted",
    )
    session.add(rec)
    session.flush()
    claim = EvidenceClaim(
        workspace_id=ws.id,
        kind=kind,
        status="accepted",
        subject={"ref": "supplier.csv"},
        statement={"claim": "viscosity 900 mPa·s"},
        source_batch_id=batch.id if resolvable else None,
        source_record_id=rec.id if resolvable else None,
    )
    session.add(claim)
    session.flush()
    return claim


# ------------------------------------------------------------ packets


class TestPacketProvenance:
    """The packet's fixture flag is derived from bound evidence — it
    can never un-label a synthetic record or upgrade validation."""

    def test_all_synthetic_stays_fixture_only(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
    ) -> None:
        res, sr, _own = ctxs
        task = _task(session, res)
        m = _measurement(session, res, task)
        report = TaskEvaluationService(session, sr).evaluate(task.id)
        assert report["fixtureOnly"] is True
        prov = report["provenance"]
        assert prov["evidenceOrigin"]["composition"] == "synthetic_only"
        assert prov["evidenceOrigin"]["counts"] == {"synthetic_fixture": 1}
        assert prov["methodValidation"]["status"] == "missing"
        assert prov["independentValidation"]["status"] == "not_validated"

        packet = TaskEvaluationService(session, sr).closeout_packet(task.id)
        assert packet["fixtureOnly"] is True
        assert packet["scientificValidation"] == "not_validated"
        assert packet["provenance"]["evidenceOrigin"]["composition"] == "synthetic_only"
        manifest_row = {e["measurementId"]: e for e in packet["manifest"]["evidence"]}[str(m.id)]
        assert manifest_row["origin"] == "synthetic_fixture"

    def test_real_record_does_not_relabel_fixtures(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
    ) -> None:
        """Adding a real-origin record must not relabel the fixture
        history nor set scientific validation to true — the packet
        decomposes honestly into mixed."""
        res, sr, _own = ctxs
        task = _task(session, res)
        fixture = _measurement(session, res, task)
        real = _measurement(session, res, task, method="hplc-assay", metric="metric.viscosity")

        report = TaskEvaluationService(session, sr).evaluate(task.id)
        assert report["fixtureOnly"] is False
        prov = report["provenance"]
        assert prov["evidenceOrigin"]["composition"] == "mixed"
        assert prov["evidenceOrigin"]["counts"]["synthetic_fixture"] == 1
        assert prov["evidenceOrigin"]["counts"]["historical_report"] == 1

        packet = TaskEvaluationService(session, sr).closeout_packet(task.id)
        assert packet["fixtureOnly"] is False
        assert packet["scientificValidation"] == "not_validated"
        by_id = {e["measurementId"]: e for e in packet["manifest"]["evidence"]}
        # the fixture record keeps its synthetic label — not laundered
        assert by_id[str(fixture.id)]["origin"] == "synthetic_fixture"
        assert by_id[str(real.id)]["origin"] == "historical_report"
        assert packet["provenance"]["evidenceOrigin"]["composition"] == "mixed"
        # real evidence present still says what is missing
        assert any("method" in m for m in packet["provenance"]["missingScientificInputs"])

    def test_real_only_packet_keeps_validation_absent(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
    ) -> None:
        res, sr, _own = ctxs
        task = _task(session, res)
        _measurement(session, res, task, method="hplc-assay", metric="metric.viscosity")
        report = TaskEvaluationService(session, sr).evaluate(task.id)
        prov = report["provenance"]
        assert report["fixtureOnly"] is False
        assert prov["evidenceOrigin"]["composition"] == "real_only"
        assert prov["evidenceOrigin"]["counts"] == {"historical_report": 1}
        # provenance real; the other axes stay missing — no upgrade
        assert prov["methodValidation"]["status"] == "missing"
        assert prov["independentValidation"]["status"] == "not_validated"
        axes = {a["axis"]: a["status"] for a in prov["readiness"]}
        assert axes["evidence_origin"] == "real"
        assert axes["engine_applicability"] == "per_record"
        assert axes["method_validation"] == "missing"
        assert axes["independent_validation"] == "not_validated"

    def test_plan_recorded_measurement_is_lab_observation(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
    ) -> None:
        res, sr, _own = ctxs
        task = _task(session, res)
        m = _measurement(
            session,
            res,
            task,
            method="hplc-assay",
            metric="metric.viscosity",
            historical=False,
        )
        report = TaskEvaluationService(session, sr).evaluate(task.id)
        assert report["provenance"]["evidenceOrigin"]["composition"] == "real_only"
        manifest = TaskEvaluationService(session, sr).closeout_packet(task.id)["manifest"]
        row = {e["measurementId"]: e for e in manifest["evidence"]}[str(m.id)]
        assert row["origin"] == "lab_observation"

    def test_prediction_and_unknown_origins(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
    ) -> None:
        res, sr, _own = ctxs
        task = _task(session, res)
        pred = _measurement(session, res, task, method="prediction-qcengine", metric="metric.dft")
        unk = _measurement(
            session,
            res,
            task,
            method="hplc-assay",
            metric="metric.ph",
            conditions={"provenance": {"origin": "an-undeclared-source"}},
        )
        report = TaskEvaluationService(session, sr).evaluate(task.id)
        prov = report["provenance"]
        assert report["fixtureOnly"] is False
        assert prov["evidenceOrigin"]["composition"] == "mixed"
        counts = prov["evidenceOrigin"]["counts"]
        assert counts["prediction"] == 1
        assert counts["unknown"] == 1

        packet = TaskEvaluationService(session, sr).closeout_packet(task.id)
        by_id = {e["measurementId"]: e for e in packet["manifest"]["evidence"]}
        assert by_id[str(pred.id)]["origin"] == "prediction"
        assert by_id[str(unk.id)]["origin"] == "unknown"


# ------------------------------------------------------------ corpus


class TestCorpusProvenance:
    """Corpus plane: manifest entries carry origin, unknown provenance
    is excluded at build, and an included record without established
    provenance blocks freeze — the same plane as rights."""

    def test_manifest_entries_label_origin(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
    ) -> None:
        res, _sr, own = ctxs
        task = _task(session, res)
        fixture = _measurement(session, res, task)
        real = _measurement(session, res, task, method="hplc-assay", metric="metric.viscosity")
        claim = _supplier_claim(session, _ws(session, res))
        svc = DatasetService(session, own)
        snap = svc.build("property_prediction", "ds", task_id=task.id)
        by_id = {e["recordId"]: e for e in snap.manifest["entries"]}
        assert by_id[str(fixture.id)]["evidenceOrigin"] == "synthetic_fixture"
        assert by_id[str(real.id)]["evidenceOrigin"] == "historical_report"
        assert by_id[str(claim.id)]["evidenceOrigin"] == "historical_report"
        prov = snap.manifest["provenance"]["evidenceOrigin"]
        assert prov["composition"] == "mixed"
        assert snap.manifest["scientificStatus"] == "not_validated"

    def test_unknown_origin_excluded_at_build(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
    ) -> None:
        res, _sr, own = ctxs
        task = _task(session, res)
        m = _measurement(
            session,
            res,
            task,
            method="hplc-assay",
            metric="metric.viscosity",
            conditions={"evidenceOrigin": "bogus-class"},
        )
        svc = DatasetService(session, own)
        snap = svc.build("property_prediction", "ds", task_id=task.id)
        entry = {e["recordId"]: e for e in snap.manifest["entries"]}[str(m.id)]
        assert entry["evidenceOrigin"] == "unknown"
        assert entry["excluded"] is True
        assert entry["exclusionReason"] == "provenance:unknown"

    def test_unprovenanced_included_record_blocks_freeze(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
    ) -> None:
        """A manifest built before provenance existed (entries without
        ``evidenceOrigin``) cannot freeze — provenance is established
        at build, and the freeze gate refuses silent records."""
        res, _sr, own = ctxs
        task = _task(session, res)
        m = _measurement(session, res, task, method="hplc-assay", metric="metric.viscosity")
        svc = DatasetService(session, own)
        snap = svc.build("property_prediction", "ds", task_id=task.id)
        for e in snap.manifest["entries"]:
            e.pop("evidenceOrigin", None)
        session.flush()
        with pytest.raises(DomainError) as ei:
            svc.freeze(snap.id)
        assert ei.value.code == ErrorCode.PROVENANCE_UNKNOWN
        assert str(m.id) in ei.value.safe_details["recordIds"]

    def test_synthetic_corpus_stays_fixture_only_label(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
    ) -> None:
        res, _sr, own = ctxs
        task = _task(session, res)
        _measurement(session, res, task)
        svc = DatasetService(session, own)
        snap = svc.build("property_prediction", "ds", task_id=task.id)
        svc.freeze(snap.id)
        assert snap.manifest["provenance"]["evidenceOrigin"]["composition"] == "synthetic_only"
        assert snap.manifest["scientificStatus"] == "not_validated"

    def test_readiness_lists_missing_real_evidence(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
    ) -> None:
        """Synthetic records never count as real property-model
        evidence — readiness exposes the missing input as an
        exclusion, never as an engineering success."""
        res, _sr, own = ctxs
        task = _task(session, res)
        _measurement(session, res, task)
        svc = DatasetService(session, own)
        snap = svc.build("property_prediction", "ds", task_id=task.id)
        svc.freeze(snap.id)
        report = PropertyModelService(session, own).readiness(
            snap.id,
            target={
                "name": "metric.synthetic-performance",
                "method": "fixture-index",
                "unit": "dimensionless",
            },
        )
        assert report["capability"] == "not_ready"
        assert report["exclusions"]["evidence_origin:synthetic_fixture"] == 1
        assert report["coverage"]["eligible"] == 0
        assert report["scientificStatus"] == "not_validated"

    def test_readiness_accepts_real_origin_records(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
    ) -> None:
        res, _sr, own = ctxs
        task = _task(session, res)
        _measurement(session, res, task, method="hplc-assay", metric="metric.viscosity")
        svc = DatasetService(session, own)
        snap = svc.build("property_prediction", "ds", task_id=task.id)
        svc.freeze(snap.id)
        report = PropertyModelService(session, own).readiness(
            snap.id,
            target={
                "name": "metric.viscosity",
                "method": "hplc-assay",
                "unit": "dimensionless",
            },
        )
        assert report["capability"] == "not_ready"
        assert "evidence_origin:synthetic_fixture" not in report["exclusions"]
        assert report["coverage"]["eligible"] == 1


def _ws(session: Session, ctx: ServiceContext) -> Workspace:
    return session.get(Workspace, ctx.workspace_id)


# ---------------------------------------------------- gate / export


class TestProvenanceGate:
    """The run-time plane re-derives provenance live — a record whose
    origin drifted or is unclassifiable cannot enter a run."""

    def test_provenance_drift_blocks_queue(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
    ) -> None:
        res, _sr, own = ctxs
        task = _task(session, res)
        m = _measurement(session, res, task, method="hplc-assay", metric="metric.viscosity")
        svc = DatasetService(session, own)
        snap = svc.build("property_prediction", "ds", task_id=task.id)
        svc.freeze(snap.id)
        entry = {e["recordId"]: e for e in snap.manifest["entries"]}[str(m.id)]
        assert entry["evidenceOrigin"] == "historical_report"

        # mutate a provenance-relevant field that is NOT part of the
        # content hash — provenance drift without content drift
        session.refresh(m)
        m.pipeline_version = "synthetic-pipe-v9"
        session.flush()

        violations = DatasetService(session, own).provenance_violations(snap.id)
        assert str(m.id) in violations
        assert violations[str(m.id)]["recorded"] == "historical_report"
        assert violations[str(m.id)]["current"] == "synthetic_fixture"

        drift = svc.drift_status(snap.id)
        assert drift["drift"] is False  # content hash unchanged

    def test_prepare_run_blocks_unprovenanced(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
    ) -> None:
        res, _sr, own = ctxs
        task = _task(session, res)
        m = _measurement(session, res, task, method="hplc-assay", metric="metric.viscosity")
        svc = DatasetService(session, own)
        snap = svc.build("property_prediction", "ds", task_id=task.id)
        for e in snap.manifest["entries"]:
            e.pop("evidenceOrigin", None)
        # a legacy manifest cannot freeze — but even if frozen state
        # were forced, prepare_run re-checks live provenance
        snap.state = "frozen"
        session.flush()
        session.refresh(m)
        # pipeline_version is not hashed — provenance drifts while
        # content drift stays clean, so the provenance plane itself
        # is the blocker
        m.pipeline_version = "synthetic-pipe-v9"
        session.flush()
        run = svc.prepare_run(snap.id)
        assert run["ok"] is False
        assert run["reason"] == "provenance_unresolved"
        assert str(m.id) in run["recordIds"]


class TestExportProvenance:
    def test_export_records_carry_origin(
        self, session: Session, ctxs: tuple[ServiceContext, ServiceContext, ServiceContext]
    ) -> None:
        res, _sr, own = ctxs
        task = _task(session, res)
        m = _measurement(session, res, task, method="hplc-assay", metric="metric.viscosity")
        claim = _supplier_claim(session, _ws(session, res))
        svc = DatasetService(session, own)
        snap = svc.build("property_prediction", "ds")
        svc.freeze(snap.id)

        from studio.domain.learning.exports.transform import _Scan

        ts = TransformService(session, own)
        records, excluded, _merged = ts._collect(snap, _Scan())
        origins = {r["kind"]: r["evidenceOrigin"] for r in records}
        assert origins["measurement"] == "historical_report"
        assert origins["claim"] == "historical_report"
        assert str(m.id) not in {e["recordId"] for e in excluded}
        assert str(claim.id) not in {e["recordId"] for e in excluded}
