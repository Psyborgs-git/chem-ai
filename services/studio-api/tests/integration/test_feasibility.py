"""CS-1001 integration tests — persisted feasibility evidence + proposal.

AT-1001-2  when every approved compatible local configuration fails
           feasibility, an evidence report exists and the export
           proposal remains unapproved.
"""

from __future__ import annotations

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import load_context
from studio.domain.runs.admission import AdmissionService
from studio.domain.runs.feasibility import FeasibilityService
from studio.domain.runs.queue import RunService
from studio.persistence.models import (
    Approval,
    ExportProposal,
    Principal,
    PrincipalCapability,
    Run,
    RunFeasibilityReport,
    Workspace,
)

pytestmark = pytest.mark.integration

GB = 1024**3


@pytest.fixture()
def env(session: Session):
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    user = Principal(workspace_id=ws.id, kind="user", login="r", display_name="r")
    session.add(user)
    session.flush()
    for cap in sorted(capabilities_for_role("researcher")):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=user.id, capability=cap))
    session.flush()
    ctx = load_context(session, ws.id, user.id)
    adm = AdmissionService(session, ctx)
    adm.ensure_group(
        "compute",
        capacity={
            "cpu_cores": 8,
            "memory_bytes": 16 * GB,
            "gpu_devices": 0,
            "storage_bytes": 100 * GB,
            "concurrency": 2,
        },
        reserve={"cpu_cores": 1, "memory_bytes": 4 * GB},
    )
    session.flush()
    return {
        "ws": ws,
        "ctx": ctx,
        "adm": adm,
        "runs": RunService(session, ctx),
        "svc": FeasibilityService(session, ctx),
    }


HARDWARE_FIXTURE = {
    "os": "Linux",
    "arch": "x86_64",
    "python_version": "3.12",
    "observed_at": "2026-10-06T00:00:00+00:00",
    "memory_model": "unknown",
    "cpu_count_logical": 8,
    "cpu_count_physical": 8,
    "ram_total_bytes": 16 * GB,
    "ram_available_bytes": 8 * GB,
    "disk_free_bytes": 50 * GB,
    "gpus": [],
    "runtimes": {},
    "isolation": {},
}


# AT-1001-2 -----------------------------------------------------------


def test_all_configs_fail_report_persisted_export_unapproved(env, session: Session) -> None:
    """Every approved compatible configuration exceeds observed
    capacity → the evidence report is persisted with per-configuration
    verdicts, the run is blocked, and the export proposal exists in the
    'proposed' state — unapproved (§20.1-20.2)."""
    run = env["runs"].request(
        kind="simulation",
        request={
            "operation": "large dft batch",
            "sizes": {"modelBytes": 2 * GB, "dataBytes": 500 * GB},
            "envelope": {"cpu_cores": 64, "memory_bytes": 256 * GB, "wall_seconds": 3600},
            "uncertainty": {"memory_bytes": "estimated"},
            "alternatives": [
                {
                    "name": "half-batch",
                    "kind": "batch_reduction",
                    "qualityImpact": "none",
                    "envelope": {"cpu_cores": 32, "memory_bytes": 128 * GB, "wall_seconds": 7200},
                },
                {
                    "name": "fp8-degraded",
                    "kind": "precision",
                    "qualityImpact": "material_needs_approval",
                    "envelope": {"memory_bytes": 4 * GB, "wall_seconds": 7200},
                },
            ],
        },
    )
    decision = env["svc"].request_fallback(run.id, hardware=HARDWARE_FIXTURE)
    session.flush()

    assert decision.decision == "export_review_proposed"
    assert decision.cloud_authorized is False
    assert decision.proposal_id is not None

    # Evidence report persisted with the full §20.1 shape.
    report = session.execute(
        select(RunFeasibilityReport).where(RunFeasibilityReport.run_id == run.id)
    ).scalar_one()
    assert report.verdict == "infeasible"
    assert report.operation == "large dft batch"
    assert report.sizes["modelBytes"] == 2 * GB
    assert report.hardware["os"] == "Linux"
    names = {c["name"]: c for c in report.configurations}
    assert names["approved"]["verdict"] == "infeasible"
    assert names["half-batch"]["verdict"] == "infeasible"
    # The material-quality configuration is recorded but excluded — it
    # cannot silently substitute for approval (§20.1).
    assert names["fp8-degraded"]["verdict"] == "excluded"
    assert names["fp8-degraded"]["requiresQualityApproval"] is True
    assert report.reasons  # per-configuration failure evidence on record

    # Run blocked with a pointer to the evidence.
    assert env["runs"].get(run.id).status == "blocked"
    assert env["runs"].get(run.id).error["detail"]["reportId"] == str(report.id)

    # Export proposal exists and stays unapproved — no Approval row.
    proposal = session.execute(
        select(ExportProposal).where(ExportProposal.run_id == run.id)
    ).scalar_one()
    assert proposal.status == "proposed"
    assert proposal.feasibility_report_id == report.id
    assert proposal.required_capability == "approve_export"
    assert session.execute(select(Approval)).scalars().all() == []

    view = env["svc"].fallback_view(run.id)
    assert view["proposal"]["approved"] is False
    assert view["proposal"]["status"] == "proposed"
    assert view["cloud"]["status"] == "not_configured"


def test_reevaluation_appends_report_and_reuses_proposal(env, session: Session) -> None:
    """Reports are append-only evidence; a repeated fallback request on
    an unchanged request reuses the open proposal rather than spawning
    duplicates."""
    request = {
        "operation": "simulation",
        "envelope": {"memory_bytes": 256 * GB, "wall_seconds": 600},
    }
    run = env["runs"].request(kind="simulation", request=request)
    d1 = env["svc"].request_fallback(run.id, hardware=HARDWARE_FIXTURE)
    d2 = env["svc"].request_fallback(run.id, hardware=HARDWARE_FIXTURE)
    session.flush()

    reports = (
        session.execute(select(RunFeasibilityReport).where(RunFeasibilityReport.run_id == run.id))
        .scalars()
        .all()
    )
    proposals = (
        session.execute(select(ExportProposal).where(ExportProposal.run_id == run.id))
        .scalars()
        .all()
    )
    assert len(reports) == 2
    assert len(proposals) == 1
    assert d1.proposal_id == d2.proposal_id
    assert proposals[0].feasibility_report_id == d2.report_id  # latest evidence


def test_feasible_run_produces_no_proposal(env, session: Session) -> None:
    run = env["runs"].request(
        kind="simulation",
        request={
            "operation": "small md",
            "envelope": {"cpu_cores": 2, "memory_bytes": 2 * GB, "wall_seconds": 600},
        },
    )
    decision = env["svc"].request_fallback(run.id, hardware=HARDWARE_FIXTURE)
    session.flush()
    assert decision.decision == "local_feasible"
    assert decision.proposal_id is None
    assert env["runs"].get(run.id).status == "requested"  # untouched
    assert session.execute(select(ExportProposal)).scalars().all() == []


def test_blocked_run_reevaluation_does_not_reblock(env, session: Session) -> None:
    """A run already blocked (e.g. by admission denial) can still be
    evaluated — the report records evidence without a second illegal
    blocked transition."""
    run = env["runs"].request(
        kind="simulation",
        request={"operation": "simulation", "envelope": {"memory_bytes": 256 * GB}},
    )
    env["adm"].admit(run.id, {"memory_bytes": 256 * GB, "wall_seconds": 600})
    session.flush()
    assert env["runs"].get(run.id).status == "blocked"

    decision = env["svc"].request_fallback(run.id, hardware=HARDWARE_FIXTURE)
    session.flush()
    assert decision.decision == "export_review_proposed"
    assert env["runs"].get(run.id).status == "blocked"


def test_capability_gate(env, session: Session) -> None:
    """No request_compute grant → no evaluation (server-side check)."""
    ws2 = Workspace(slug="w2", display_name="W2")
    session.add(ws2)
    session.flush()
    observer = Principal(workspace_id=ws2.id, kind="user", login="o", display_name="o")
    session.add(observer)
    session.flush()
    run = Run(
        workspace_id=ws2.id,
        kind="simulation",
        status="requested",
        request={},
        request_digest="0" * 64,
    )
    session.add(run)
    session.flush()
    ctx2 = load_context(session, ws2.id, observer.id)
    svc2 = FeasibilityService(session, ctx2)
    from studio.errors import DomainError, ErrorCode

    with pytest.raises(DomainError) as err:
        svc2.request_fallback(run.id)
    assert err.value.code == ErrorCode.FORBIDDEN
