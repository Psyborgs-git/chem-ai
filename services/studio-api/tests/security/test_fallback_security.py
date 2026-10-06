"""CS-1001 security test — fallback produces no external job or spend.

AT-1001-3  with no cloud budget/account configured, fallback processing
           cannot produce an external job or spend: the module contains
           no network code, the proposal is inert, no approval is
           minted, and no run attempt/job is created.
"""

from __future__ import annotations

import inspect
import socket

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session

import studio.domain.runs.feasibility as feasibility
from studio.auth.context import load_context
from studio.domain.runs.admission import AdmissionService
from studio.domain.runs.feasibility import FeasibilityService, cloud_capability
from studio.domain.runs.queue import RunService
from studio.persistence.models import (
    Approval,
    ExportProposal,
    Principal,
    PrincipalCapability,
    RunAttempt,
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
    return {
        "ws": ws,
        "ctx": ctx,
        "adm": adm,
        "runs": RunService(session, ctx),
        "svc": FeasibilityService(session, ctx),
    }


def test_fallback_no_egress_no_spend(env, session: Session, monkeypatch) -> None:
    """Any socket use by the fallback path would raise — it does not,
    because the module contains no network code at all. The proposal is
    a review row: unapproved, no external job, no spend (§20.2)."""
    touched: list[str] = []

    class _NoNet:
        def __init__(self, *a, **k):  # pragma: no cover - must never run
            touched.append("socket")
            raise AssertionError("fallback touched the network")

    monkeypatch.setattr(socket, "socket", _NoNet)
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: touched.append("conn"))

    run = env["runs"].request(
        kind="proprietary_simulation",
        request={
            "operation": "proprietary dft",
            "envelope": {"cpu_cores": 32, "memory_bytes": 256 * GB, "wall_seconds": 3600},
        },
    )
    hardware = {
        "os": "Linux",
        "arch": "x86_64",
        "python_version": "3.12",
        "observed_at": "2026-10-06T00:00:00+00:00",
        "memory_model": "unknown",
        "gpus": [],
        "runtimes": {},
        "isolation": {},
    }
    decision = env["svc"].request_fallback(run.id, hardware=hardware)
    session.flush()

    assert touched == []  # the network was never approached
    assert decision.decision == "export_review_proposed"
    assert decision.cloud_authorized is False

    # No external job exists: the blocked run has no attempt rows and
    # no queue external_id — nothing was submitted anywhere.
    assert env["runs"].get(run.id).status == "blocked"
    assert (
        session.execute(select(RunAttempt).where(RunAttempt.run_id == run.id)).scalars().all() == []
    )

    # The proposal is inert: proposed (not approved), no Approval row
    # exists, and no spend/budget fields carry values.
    proposal = session.execute(
        select(ExportProposal).where(ExportProposal.run_id == run.id)
    ).scalar_one()
    assert proposal.status == "proposed"
    view = env["svc"].fallback_view(run.id)
    assert view["proposal"]["approved"] is False
    assert view["proposal"]["sideEffects"] == "none"
    assert session.execute(select(Approval)).scalars().all() == []

    # Honest capability: no provider/account/budget — a stored credential
    # would still not be an approval (§20.2).
    cap = cloud_capability()
    assert cap["status"] == "not_configured"
    assert cap["provider"] is None
    assert cap["account"] is None
    assert cap["budget"] is None
    assert cap["egress"] == "deny"


def test_module_has_no_network_surface() -> None:
    """Structural check: the feasibility module imports no network or
    cloud-SDK clients — there is no code path that could send bytes."""
    source = inspect.getsource(feasibility)
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
        assert banned not in source, f"feasibility module references {banned}"
