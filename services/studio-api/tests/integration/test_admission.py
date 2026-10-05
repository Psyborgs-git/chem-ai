"""CS-0402 integration tests — transactional admission and headroom.

AT-0402-2  two heavy jobs exceed one envelope → only compatible work
           starts; headroom keeps the API/UI responsive
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import load_context
from studio.domain.runs.admission import AdmissionService
from studio.domain.runs.queue import RunService
from studio.persistence.models import (
    Principal,
    PrincipalCapability,
    ResourceReservation,
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
    return {"ws": ws, "ctx": ctx, "adm": adm, "runs": RunService(session, ctx)}


def _run(env) -> uuid.UUID:
    return env["runs"].request(kind="simulation", request={"k": "v"}).id


# AT-0402-2 -----------------------------------------------------------


def test_two_heavy_jobs_only_compatible_starts(env, session: Session) -> None:
    """Effective memory = 16GB - 4GB reserve = 12GB. Two 8GB jobs cannot
    both fit; the second is blocked while headroom (the reserve) keeps
    light work schedulable — the API never stalls behind heavy jobs."""
    run1, run2 = _run(env), _run(env)
    heavy = {"cpu_cores": 4, "memory_bytes": 8 * GB, "wall_seconds": 600}

    d1 = env["adm"].admit(run1, heavy)
    session.flush()
    assert d1.admitted is True
    assert env["runs"].get(run1).status == "queued"

    d2 = env["adm"].admit(run2, heavy)
    session.flush()
    assert d2.admitted is False
    mem = next(r for r in d2.reasons if r["dimension"] == "memory_bytes")
    assert mem["required"] == 8 * GB
    assert mem["available"] == 4 * GB  # 16 - 4 reserve - 8 reserved
    assert env["runs"].get(run2).status == "blocked"

    # The reserve headroom means small metadata work still starts —
    # the UI/API stay responsive while the heavy job runs.
    light = _run(env)
    d3 = env["adm"].admit(light, {"cpu_cores": 0, "memory_bytes": 1 * GB, "wall_seconds": 60})
    session.flush()
    assert d3.admitted is True


def test_reservation_released_frees_capacity(env, session: Session) -> None:
    run1 = _run(env)
    env["adm"].admit(run1, {"memory_bytes": 10 * GB, "wall_seconds": 600})
    session.flush()
    assert env["adm"].release(run1) == 1
    run2 = _run(env)
    d = env["adm"].admit(run2, {"memory_bytes": 10 * GB, "wall_seconds": 600})
    assert d.admitted is True


def test_expired_reservation_frees_capacity(env, session: Session) -> None:
    run1 = _run(env)
    env["adm"].admit(run1, {"memory_bytes": 10 * GB, "wall_seconds": 600})
    res = session.execute(select(ResourceReservation)).scalar_one()
    res.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.flush()
    run2 = _run(env)
    d = env["adm"].admit(run2, {"memory_bytes": 10 * GB, "wall_seconds": 600})
    assert d.admitted is True
    assert env["adm"].sweep_expired() == 1


def test_gpu_required_but_unobserved_is_missing(env) -> None:
    """gpu_devices capacity is 0/observed-none — a GPU job reports the
    missing/blocked dimension rather than being assumed feasible."""
    run = _run(env)
    d = env["adm"].admit(run, {"gpu_devices": 1, "wall_seconds": 60})
    assert d.admitted is False
    assert any(r["dimension"] == "gpu_devices" for r in d.reasons)


def test_unobserved_dimension_is_missing_not_assumed(env) -> None:
    """A capacity of None means unobserved → missing capability, never
    silently treated as sufficient (§20.1)."""
    env["adm"].ensure_group("gpu", capacity={"memory_bytes": None, "concurrency": 1}, reserve={})
    run = _run(env)
    d = env["adm"].admit(run, {"memory_bytes": 1 * GB}, group_name="gpu")
    assert d.admitted is False
    assert "memory_bytes" in d.missing


def test_admission_records_audit(env, session: Session) -> None:
    from studio.persistence.models import AuditEvent

    run = _run(env)
    env["adm"].admit(run, {"memory_bytes": 1 * GB, "wall_seconds": 60})
    session.flush()
    actions = [a.action for a in session.execute(select(AuditEvent)).scalars().all()]
    assert "run.admitted" in actions
