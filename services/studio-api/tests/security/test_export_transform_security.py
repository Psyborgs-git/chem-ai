"""CS-1002 security tests — disclosure review never overstates safety.

AT-1002-1  names aliased but ratios/process remain → the scanner and
           the review surface do NOT label the payload anonymous or
           safe; the residual-risk report lists what remains exposed.
AT-1002-2  a hidden sensitive field in metadata/free text is flagged
           or excluded — and stays reviewable in the redaction report.
           Also: agents can never approve, and the module has no
           network surface at all.
"""

from __future__ import annotations

import inspect
import socket

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session

import studio.domain.learning.exports.transform as transform
from studio.application.idempotency import canonical_json
from studio.auth.context import load_context
from studio.domain.learning.datasets import DatasetService
from studio.domain.learning.exports.transform import TransformService
from studio.domain.runs.admission import AdmissionService
from studio.domain.runs.feasibility import FeasibilityService
from studio.domain.runs.queue import RunService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Approval,
    Artifact,
    EvidenceClaim,
    ExportProposal,
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
    Workspace,
)

pytestmark = pytest.mark.security

GB = 1024**3

HARDWARE_FIXTURE = {
    "os": "Linux",
    "arch": "x86_64",
    "python_version": "3.12",
    "observed_at": "2026-10-06T00:00:00+00:00",
    "memory_model": "unknown",
    "gpus": [],
    "runtimes": {},
    "isolation": {},
}


def _principal(session: Session, ws: Workspace, role: str, login: str, kind="user") -> Principal:
    p = Principal(workspace_id=ws.id, kind=kind, login=login, display_name=login)
    session.add(p)
    session.flush()
    for cap in sorted(capabilities_for_role(role)):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=p.id, capability=cap))
    session.flush()
    return p


def _task(session: Session, ctx) -> ResearchTask:
    proj = Project(workspace_id=ctx.workspace_id, slug="p", name="P")
    session.add(proj)
    session.flush()
    task = ResearchTask(
        workspace_id=ctx.workspace_id,
        project_id=proj.id,
        mode="improve",
        title="t",
        workflow_state="active",
        target_kind="formulation",
        objective="o",
    )
    session.add(task)
    session.flush()
    return task


def _measurement(session: Session, ctx, task: ResearchTask) -> Measurement:
    ex = LabExecution(
        workspace_id=ctx.workspace_id, task_id=task.id, status="in_progress", historical=True
    )
    session.add(ex)
    session.flush()
    batch = LabBatch(workspace_id=ctx.workspace_id, execution_id=ex.id, label="A")
    session.add(batch)
    session.flush()
    sample = LabSample(workspace_id=ctx.workspace_id, batch_id=batch.id, label="a1", kind="aliquot")
    session.add(sample)
    session.flush()
    m = Measurement(
        workspace_id=ctx.workspace_id,
        sample_id=sample.id,
        method="tack loop fixture",
        metric="metric.tack-4h",
        repeat_type="independent_batch",
        value_type="numeric",
        value={"kind": "numeric", "value": "4.2", "unit": "wt%"},
        conditions={"actual": {"temperature": 353.15, "rpm": 300, "hold_minutes": 45}},
        status="accepted",
    )
    session.add(m)
    session.flush()
    return m


def _claim(
    session: Session, ctx, *, rights: dict, statement: dict, subject: dict | None = None
) -> EvidenceClaim:
    art = Artifact(
        workspace_id=ctx.workspace_id,
        storage_key="aa/" + "b" * 62,
        media_type="text/csv",
        byte_size=4,
        checksum_sha256="b" * 64,
        original_name="acme-supplier-sheet.csv",
        rights=rights,
    )
    session.add(art)
    session.flush()
    batch = ImportBatch(
        workspace_id=ctx.workspace_id,
        artifact_id=art.id,
        checksum_sha256="b" * 64,
        original_name="acme-supplier-sheet.csv",
        detected_type="csv",
        parser_name="csv",
        parser_version="1",
        document_group=art.id,
        status="parsed",
    )
    session.add(batch)
    session.flush()
    rec = ExtractedRecord(
        workspace_id=ctx.workspace_id,
        batch_id=batch.id,
        kind="row",
        locator={"row": 1},
        original_text="supplier sheet",
        payload={},
        status="accepted",
    )
    session.add(rec)
    session.flush()
    claim = EvidenceClaim(
        workspace_id=ctx.workspace_id,
        kind="document_claim",
        status="accepted",
        subject=subject or {"ref": "acme-supplier-sheet.csv"},
        statement=statement,
        source_batch_id=batch.id,
        source_record_id=rec.id,
    )
    session.add(claim)
    session.flush()
    return claim


@pytest.fixture()
def env(session: Session):
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    owner = _principal(session, ws, "owner", "o")
    researcher = _principal(session, ws, "researcher", "r")
    # An agent principal explicitly granted approve_export — the
    # effective-grants ceiling still strips it (§21.1).
    agent = Principal(workspace_id=ws.id, kind="agent", login="bot", display_name="b")
    session.add(agent)
    session.flush()
    session.add(
        PrincipalCapability(workspace_id=ws.id, principal_id=agent.id, capability="approve_export")
    )
    for cap in sorted(capabilities_for_role("agent")):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=agent.id, capability=cap))
    session.flush()
    octx = load_context(session, ws.id, owner.id)
    rctx = load_context(session, ws.id, researcher.id)
    actx = load_context(session, ws.id, agent.id)
    adm = AdmissionService(session, rctx)
    adm.ensure_group(
        "compute",
        capacity={"cpu_cores": 8, "memory_bytes": 16 * GB, "gpu_devices": 0, "concurrency": 1},
        reserve={"memory_bytes": 2 * GB},
    )
    session.flush()
    return {
        "ws": ws,
        "octx": octx,
        "rctx": rctx,
        "actx": actx,
        "agent": agent,
        "runs": RunService(session, rctx),
        "feas": FeasibilityService(session, rctx),
        "datasets": DatasetService(session, octx),
        "svc": TransformService(session, octx),
    }


def _proposal(env, session: Session) -> ExportProposal:
    run = env["runs"].request(
        kind="simulation",
        request={
            "operation": "proprietary dft",
            "sizes": {"modelBytes": 2 * GB},
            "envelope": {"cpu_cores": 64, "memory_bytes": 256 * GB, "wall_seconds": 3600},
        },
    )
    decision = env["feas"].request_fallback(run.id, hardware=HARDWARE_FIXTURE)
    session.flush()
    assert decision.decision == "export_review_proposed"
    return session.execute(
        select(ExportProposal).where(ExportProposal.run_id == run.id)
    ).scalar_one()


def test_at_1002_1_aliases_never_imply_safe(env, session: Session) -> None:
    """Names are aliased — ratios, process windows, and outcomes remain
    exposed. The payload and every report/label refuse to claim
    'anonymous' or 'safe' (§20.3)."""
    task = _task(session, env["octx"])
    _measurement(session, env["octx"], task)
    _claim(
        session,
        env["octx"],
        rights={"training": "allowed", "export": "allowed"},
        statement={"claim": "acme-supplier-sheet.csv shows tack holding"},
    )
    snap = env["datasets"].build("property_prediction", "snap", task.id)
    session.flush()
    env["datasets"].freeze(snap.id)
    proposal = _proposal(env, session)

    row = env["svc"].prepare(proposal.id, snap.id)
    session.flush()

    blob = canonical_json(row.payload)
    # Identifiers were replaced by tokens — the originals are gone.
    assert "acme-supplier-sheet.csv" not in blob
    assert "metric.tack-4h" not in blob
    assert "a-" in blob or "mat-" in blob or "m-" in blob

    # …but the scientific content still discloses: wt% composition,
    # process windows, and the measured outcome are in the payload.
    assert "353.15" in blob or "wt%" in blob or "4.2" in blob
    residual = row.residual_report
    assert residual["verdict"] == "residual_disclosure"
    assert residual["anonymous"] is False
    assert residual["safe"] is False
    assert residual["certified"] is False
    kinds = {c["kind"] for c in residual["categories"]}
    assert {"outcomes", "process_windows", "metadata"} <= kinds
    # wt% unit → ratios category flagged as residual.
    assert "ratios" in kinds
    # The payload document itself carries the honest label.
    assert "NOT anonymous or safe" in row.payload["notes"]

    view = env["svc"].review_view(proposal.id)
    assert view["residual"]["anonymous"] is False
    assert view["approval"]["state"] == "none"  # no approval was minted


def test_at_1002_2_hidden_fields_flagged_and_reviewable(env, session: Session) -> None:
    """Hidden sensitive fields inside kept dicts are excluded and
    reported; sensitive content inside kept text is flagged. Both stay
    visible to a reviewer — nothing is silently dropped."""
    task = _task(session, env["octx"])
    _claim(
        session,
        env["octx"],
        rights={"training": "allowed", "export": "allowed"},
        statement={
            "claim": "viscosity 900 mPa·s — contact jdoe@acme.example",
            "internal_note": "supplier is also our bidder",  # hidden field
            "api_key": "sk-live-9911",  # secret-looking field
        },
    )
    snap = env["datasets"].build("property_prediction", "snap", task.id)
    session.flush()
    env["datasets"].freeze(snap.id)
    proposal = _proposal(env, session)

    row = env["svc"].prepare(proposal.id, snap.id)
    blob = canonical_json(row.payload)

    # Excluded keys' values never reach the payload…
    assert "supplier is also our bidder" not in blob
    assert "sk-live-9911" not in blob
    assert "jdoe@acme.example" not in blob
    # …but the removal stays reviewable in the redaction report.
    removed = {k["path"]: k for k in row.redaction_report["removedKeys"]}
    assert "statement.internal_note" in removed
    assert "statement.api_key" in removed
    # …and the free-text email is flagged, keeping the record reviewable.
    flags = row.residual_report["flags"]
    assert any(f["pattern"] == "email" for f in flags)
    assert row.residual_report["flaggedRecords"]


def test_agents_can_never_approve(env, session: Session) -> None:
    """§21.1: even an explicit approve_export grant on an agent-kind
    principal is stripped at context load — decide() is forbidden."""
    task = _task(session, env["octx"])
    _measurement(session, env["octx"], task)
    snap = env["datasets"].build("property_prediction", "snap", task.id)
    session.flush()
    env["datasets"].freeze(snap.id)
    proposal = _proposal(env, session)
    row = env["svc"].prepare(proposal.id, snap.id)

    agent_svc = TransformService(session, env["actx"])
    with pytest.raises(DomainError) as exc:
        agent_svc.decide(row.id, decision="approved")
    assert exc.value.code == ErrorCode.FORBIDDEN
    assert session.execute(select(Approval)).scalars().all() == []


def test_no_egress_and_no_network_surface(env, session: Session, monkeypatch) -> None:
    """The transform path never approaches the network — not for
    transfer, not for scanning, not for anything. Egress stays deny."""
    touched: list[str] = []

    class _NoNet:
        def __init__(self, *a, **k):  # pragma: no cover - must never run
            touched.append("socket")
            raise AssertionError("export transform touched the network")

    monkeypatch.setattr(socket, "socket", _NoNet)
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: touched.append("conn"))

    task = _task(session, env["octx"])
    _measurement(session, env["octx"], task)
    snap = env["datasets"].build("property_prediction", "snap", task.id)
    session.flush()
    env["datasets"].freeze(snap.id)
    proposal = _proposal(env, session)
    row = env["svc"].prepare(proposal.id, snap.id)
    env["svc"].review_view(proposal.id)

    assert touched == []
    assert row.manifest["egress"] == "deny"
    assert row.manifest["environment"]["containerDigest"] is None

    source = inspect.getsource(transform)
    for banned in (
        "import socket",
        "import httpx",
        "import urllib",
        "import boto",
        "requests.",
        "socket.socket",
        "urlopen",
        "boto3",
    ):
        assert banned not in source, f"transform module references {banned}"
