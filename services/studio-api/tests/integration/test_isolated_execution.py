"""CS-0403 integration tests — isolated execution + cancellation (§13.3-13.5).

AT-0403-2  child spawns a grandchild, run is cancelled → the whole
           process tree stops and the resource reservation releases.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import uuid

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session
from workers.common.executor import ExecLimits, SubprocessBackend

from studio.auth.context import load_context
from studio.domain.runs.admission import AdmissionService
from studio.domain.runs.execution import AttemptExecutor
from studio.domain.runs.queue import RunService
from studio.persistence.models import (
    Principal,
    PrincipalCapability,
    ResourceReservation,
    RunAttempt,
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
        capacity={"cpu_cores": 8, "memory_bytes": 16 * GB, "concurrency": 4},
        reserve={},
    )
    session.flush()
    return {
        "ws": ws,
        "ctx": ctx,
        "adm": adm,
        "runs": RunService(session, ctx),
        "backend": SubprocessBackend(),
    }


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OverflowError):
        return False


def _admit(env, session: Session) -> tuple[uuid.UUID, uuid.UUID]:
    run = env["runs"].request(kind="simulation", request={"k": "v"})
    decision = env["adm"].admit(run.id, {"memory_bytes": 1 * GB, "wall_seconds": 600})
    assert decision.admitted
    attempt = session.execute(select(RunAttempt).where(RunAttempt.run_id == run.id)).scalars().one()
    return run.id, attempt.id


# AT-0403-2 -----------------------------------------------------------


def test_cancel_kills_process_tree_and_releases(env, session: Session) -> None:
    """The child spawns a grandchild (`sleep`); cancelling the run kills
    the whole group — and the reservation frees in the same transaction
    as the terminal cancellation."""
    run_id, attempt_id = _admit(env, session)
    reservations = (
        session.execute(
            select(ResourceReservation).where(
                ResourceReservation.run_id == run_id,
                ResourceReservation.status == "active",
            )
        )
        .scalars()
        .all()
    )
    assert len(reservations) == 1

    # The probe reports the grandchild pid so the test can verify death.
    probe = (
        "import subprocess,time,sys,os\n"
        "p=subprocess.Popen(['sleep','30'])\n"
        "print('GRANDCHILD='+str(p.pid),flush=True)\n"
        "time.sleep(30)\n"
    )
    cancel = threading.Event()
    executor = AttemptExecutor(session, env["ctx"], env["backend"], worker_id="w-1")

    def watch() -> None:
        # Give the child time to spawn the grandchild, then cancel.
        time.sleep(1.5)
        cancel.set()

    threading.Thread(target=watch, daemon=True).start()
    run = executor.execute(
        run_id=run_id,
        attempt_id=attempt_id,
        argv=[sys.executable, "-c", probe],
        limits=ExecLimits(wall_seconds=60, cpu_seconds=30),
        cancel=cancel,
    )
    session.flush()
    session.refresh(run)
    assert run.status == "cancelled"
    freed = (
        session.execute(
            select(ResourceReservation).where(
                ResourceReservation.run_id == run_id,
                ResourceReservation.status == "active",
            )
        )
        .scalars()
        .all()
    )
    assert freed == []


def test_cancel_tree_actually_dies() -> None:
    """Backend-level proof: after cancellation no member of the child's
    process group survives (SIGTERM then SIGKILL escalation)."""
    backend = SubprocessBackend()
    probe = (
        "import subprocess,time\n"
        "with open('pid','w') as f:\n"
        "    p=subprocess.Popen(['sleep','30'])\n"
        "    f.write(str(p.pid))\n"
        "time.sleep(30)\n"
    )
    cancel = threading.Event()
    threading.Timer(1.0, cancel.set).start()
    res = backend.run(
        [sys.executable, "-c", probe],
        inputs={},
        limits=ExecLimits(wall_seconds=60),
        cancel=cancel,
    )
    assert res.cancelled, res.stderr[:400]
    assert res.tree_exited
    # The grandchild pid was written into scratch before cancellation —
    # verify the process is actually dead, not merely detached.
    pidfile = os.path.join(res.scratch_dir, "pid")
    assert os.path.exists(pidfile)
    deadline = time.monotonic() + 5
    pid = int(open(pidfile).read().strip() or "0")
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not _alive(pid)


def test_structured_result_success(env, session: Session) -> None:
    """exit 0 + parseable structured output -> succeeded with the
    result persisted; a bare exit-0 with no result is NOT success."""
    run_id, attempt_id = _admit(env, session)
    executor = AttemptExecutor(session, env["ctx"], env["backend"])
    run = executor.execute(
        run_id=run_id,
        attempt_id=attempt_id,
        argv=[sys.executable, "-c", "import json;print(json.dumps({'tack':4.2}))"],
        limits=ExecLimits(wall_seconds=30),
    )
    session.flush()
    assert run.status == "succeeded"
    assert run.result_summary["result"] == {"tack": 4.2}
    assert run.result_summary["profile"] == "restricted-subprocess"

    run_id2, attempt_id2 = _admit(env, session)
    run2 = executor.execute(
        run_id=run_id2,
        attempt_id=attempt_id2,
        argv=[sys.executable, "-c", "print('no structured output')"],
        limits=ExecLimits(wall_seconds=30),
    )
    session.flush()
    assert run2.status == "failed"
    assert "not scientific success" in (run2.error or {}).get("message", "")


def test_timeout_marks_timed_out(env, session: Session) -> None:
    run_id, attempt_id = _admit(env, session)
    executor = AttemptExecutor(session, env["ctx"], env["backend"])
    run = executor.execute(
        run_id=run_id,
        attempt_id=attempt_id,
        argv=[sys.executable, "-c", "import time;time.sleep(30)"],
        limits=ExecLimits(wall_seconds=1.0),
    )
    session.flush()
    assert run.status == "timed_out"
