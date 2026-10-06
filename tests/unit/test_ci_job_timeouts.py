"""AT-1103-3 — every CI job terminates within its configured cap (§23.3).

A hung job must be killed by the platform, not left running: every job
in ci.yml declares ``timeout-minutes``, and the value stays inside the
§23.3 budget for its class — static/schema work ≤ 10 minutes, core
unit/integration and browser tests ≤ 20 minutes, anything else only
with an explicit, still-bounded timeout.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# §23.3 budget classes, matched on the GitHub job *id*. First match wins;
# unmatched jobs fall through to the core cap (20) and must still declare
# an explicit timeout — a job can never opt out of the bound.
_STATIC = re.compile(r"lint|typecheck|contract|schema|static", re.IGNORECASE)
_BROWSER = re.compile(r"e2e|browser|playwright", re.IGNORECASE)

CAP_STATIC_MIN = 10
CAP_CORE_MIN = 20


def _cap_minutes(job_id: str) -> int:
    if _STATIC.search(job_id):
        return CAP_STATIC_MIN
    if _BROWSER.search(job_id):
        return CAP_CORE_MIN
    return CAP_CORE_MIN


@pytest.fixture(scope="module")
def workflow() -> dict:
    doc = yaml.safe_load(CI_YML.read_text())
    assert isinstance(doc, dict), "ci.yml must parse to a mapping"
    return doc


def test_every_ci_job_declares_timeout(workflow: dict) -> None:
    jobs = workflow.get("jobs")
    assert jobs, "ci.yml defines no jobs"
    missing = [
        job_id
        for job_id, job in jobs.items()
        if not isinstance(job.get("timeout-minutes"), int) or job["timeout-minutes"] <= 0
    ]
    assert not missing, (
        f"jobs missing a positive integer timeout-minutes: {missing} — "
        "a hang would run until GitHub's 6h default, past every §23.3 cap"
    )


def test_ci_timeouts_respect_class_caps(workflow: dict) -> None:
    jobs = workflow.get("jobs") or {}
    over = {}
    for job_id, job in jobs.items():
        declared = job.get("timeout-minutes")
        if not isinstance(declared, int):
            continue  # covered by the declaration test
        cap = _cap_minutes(job_id)
        if declared > cap:
            over[job_id] = f"{declared}min declared > {cap}min cap"
    assert not over, f"jobs over their §23.3 timeout budget: {over}"


def test_workflow_itself_cancels_superseded_runs(workflow: dict) -> None:
    """Concurrency cancellation is part of the hang budget: a stale run
    must not hold a slot past its timeout."""
    concurrency = workflow.get("concurrency") or {}
    assert concurrency.get("cancel-in-progress") is True
