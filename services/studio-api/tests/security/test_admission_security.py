"""CS-0402 security test — blocked local capacity never routes outward.

AT-0402-3  local limits reject a proprietary job → no cloud request,
           no network export: the admission path is physically incapable
           of either (there is no egress code to call), and the recorded
           next step is a review *proposal* for a human, not a submission.
"""

from __future__ import annotations

import socket

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import load_context
from studio.domain.runs.admission import AdmissionService
from studio.domain.runs.queue import RunService
from studio.persistence.models import (
    AuditEvent,
    Principal,
    PrincipalCapability,
    Workspace,
)

pytestmark = pytest.mark.security

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
        capacity={"cpu_cores": 8, "memory_bytes": 16 * GB, "gpu_devices": 0, "concurrency": 1},
        reserve={"memory_bytes": 2 * GB},
    )
    session.flush()
    return {"ws": ws, "ctx": ctx, "adm": adm, "runs": RunService(session, ctx)}


def test_rejected_job_no_egress(env, session: Session, monkeypatch) -> None:
    """Any socket use by the admission path would raise — it does not,
    because the module contains no network code at all. The denial is
    recorded with reasons; the only follow-up offered is a human
    export-review proposal (§20.1-20.2)."""
    touched: list[str] = []

    class _NoNet:
        def __init__(self, *a, **k):  # pragma: no cover - must never run
            touched.append("socket")
            raise AssertionError("admission touched the network")

    monkeypatch.setattr(socket, "socket", _NoNet)
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: touched.append("conn"))

    run = env["runs"].request(
        kind="proprietary_simulation",
        request={"candidateRevisionId": "f" * 32},
    )
    decision = env["adm"].admit(
        run.id, {"cpu_cores": 32, "memory_bytes": 256 * GB, "wall_seconds": 3600}
    )
    session.flush()

    assert touched == []  # the network was never approached
    assert decision.admitted is False
    assert decision.next_step == "export_review_proposal"  # proposal ≠ submission
    assert env["runs"].get(run.id).status == "blocked"
    detail = next(
        a.detail
        for a in session.execute(select(AuditEvent)).scalars().all()
        if a.action == "run.admission_denied"
    )
    assert detail["reasons"]  # per-dimension reasons are on record
