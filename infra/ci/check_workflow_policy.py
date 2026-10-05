#!/usr/bin/env python3
"""CI policy check (AT-0003-1).

Verifies every job in .github/workflows/*.yml has a timeout and that no
step uploads repository content to external services (no artifact
upload of sources/models, no secrets in echo). Exits non-zero with the
violating job when the policy fails.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"

BANNED_USES = ("actions/upload-artifact", "actions/cache/save", "codecov")
BANNED_RUN_PATTERNS = tuple(
    re.compile(p)
    for p in (
        r"\bcurl\s+https?://",
        r"\bwget\s+https?://",
        r"\b(nc|netcat|ncat)\b",
        r"\bupload-artifact\b",
        r"\bsecrets\.",
    )
)


def check() -> list[str]:
    problems: list[str] = []
    files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    if not files:
        problems.append("no workflow files found")
    for wf in files:
        doc = yaml.safe_load(wf.read_text())
        jobs = doc.get("jobs") or {}
        if not jobs:
            problems.append(f"{wf.name}: no jobs")
        for job_name, job in jobs.items():
            if "timeout-minutes" not in job:
                problems.append(f"{wf.name}:{job_name}: missing timeout-minutes")
            for step in job.get("steps", []):
                uses = str(step.get("uses", ""))
                run = str(step.get("run", ""))
                for b in BANNED_USES:
                    if b in uses:
                        problems.append(f"{wf.name}:{job_name}: banned action {uses}")
                for pat in BANNED_RUN_PATTERNS:
                    if pat.search(run):
                        problems.append(
                            f"{wf.name}:{job_name}: suspicious run content ({pat.pattern!r})"
                        )
        perms = doc.get("permissions")
        if perms != {"contents": "read"}:
            problems.append(f"{wf.name}: permissions must be contents:read")
        conc = doc.get("concurrency") or {}
        if not conc.get("cancel-in-progress"):
            problems.append(f"{wf.name}: concurrency cancellation missing")
    return problems


def main() -> int:
    problems = check()
    if problems:
        print("CI POLICY FAIL:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("CI policy OK: every job bounded, least-privilege, no uploads")
    return 0


if __name__ == "__main__":
    sys.exit(main())
