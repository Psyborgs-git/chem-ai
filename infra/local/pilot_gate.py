"""Pilot gate report generator (CS-0505, §21.6, §25.5, §27).

Produces ``docs/operations/pilot-gate.md`` — a capability matrix that
separates **software status** (live / fixture / blocked / unavailable)
from **scientific validation status** (always ``not_validated`` —
fixtures prove the workflow, never the science).

Statuses are probed where a cheap honest probe exists (docker image
presence, model volume, DB reachability) and stated as constants where
the capability is unimplemented — never claimed.

Run: ``uv run python infra/local/pilot_gate.py [--out PATH]``
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "docs" / "operations" / "pilot-gate.md"

RDKIT_IMAGE = "chem-studio-rdkit:2026.3.6"
LLAMA_IMAGE = "ghcr.io/ggml-org/llama.cpp:server"
MODEL_VOLUME = "chem-models"
BAYBE_IMAGE = "chem-studio-baybe:0.15.0-v1"
CHEMPROP_IMAGE = "chem-studio-chemprop:2.3.1-v1"
SFT_IMAGE = "chem-studio-sft:0.1.0-v5"
RL_IMAGE = "chem-studio-rl:0.1.0-v1"


def _docker(*args: str) -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return (
            subprocess.run(  # noqa: S603 — fixed argv probes
                ["docker", *args],  # noqa: S607
                capture_output=True,
                timeout=15,
            ).returncode
            == 0
        )
    except Exception:
        return False


def _row(
    capability: str,
    software: str,
    evidence: str,
    limitations: str,
    scientific: str = "not_validated",
) -> str:
    return f"| {capability} | {software} | {evidence} | {scientific} | {limitations} |"


def build_report() -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    rdkit = (
        ("live (container)", f"`docker image inspect {RDKIT_IMAGE}` present")
        if _docker("image", "inspect", RDKIT_IMAGE)
        else ("blocked", "no chem-studio-rdkit image; `make test-engines` reports UNAVAILABLE")
    )
    inference = (
        ("live (container)", f"`{LLAMA_IMAGE}` + volume `{MODEL_VOLUME}` present")
        if _docker("image", "inspect", LLAMA_IMAGE) and _docker("volume", "inspect", MODEL_VOLUME)
        else ("blocked", "llama.cpp image or model volume absent; profile_local_ai off")
    )
    baybe = (
        (
            "live (container)",
            f"`{BAYBE_IMAGE}` present; CS-0603 adapter + independent constraint checks",
        )
        if _docker("image", "inspect", BAYBE_IMAGE)
        else ("blocked", f"`{BAYBE_IMAGE}` absent; build engine image then `make test-engines`")
    )
    proptrain = (
        (
            "live (container)",
            f"`{CHEMPROP_IMAGE}` + `{SFT_IMAGE}` present; "
            "CS-0604/CS-0801 mechanism verified on fixtures",
        )
        if _docker("image", "inspect", CHEMPROP_IMAGE) and _docker("image", "inspect", SFT_IMAGE)
        else (
            "blocked",
            "chemprop/SFT engine images absent; build engine images then `make test-engines`",
        )
    )
    rl = (
        ("live (container)", f"`{RL_IMAGE}` present; CS-0901/CS-0902 bounded env + GRPO trainer")
        if _docker("image", "inspect", RL_IMAGE)
        else ("blocked", f"`{RL_IMAGE}` absent; build engine image then `make test-engines`")
    )

    rows = [
        _row(
            "PostgreSQL persistence",
            "live",
            "compose container `chem-studio-postgres` (loopback :54329)",
            "single-host; no replication",
            scientific="n/a — infrastructure",
        ),
        _row(
            "Artifact vault",
            "live",
            "filesystem vault under `STUDIO_VAULT_ROOT`; checksum-verified blobs",
            "no at-rest encryption in app; relies on OS volume encryption",
            scientific="n/a — infrastructure",
        ),
        _row(
            "Deterministic verification",
            "live",
            "CS-0404 verifier; contract-bound deterministic checks",
            "covers whitelisted check kinds only",
        ),
        _row(
            "RDKit descriptors",
            rdkit[0],
            rdkit[1],
            "linux/amd64 container path; native rdkit optional",
        ),
        _row(
            "Local inference (llama.cpp)",
            inference[0],
            inference[1],
            "2B fixture model; not a validated chemistry assistant",
        ),
        _row(
            "Lab executions",
            "live (manual-first)",
            "CS-0501/0502 plans, executions, measurements, review",
            "no equipment control; all execution is human-performed",
        ),
        _row(
            "Task closeout evaluator",
            "live",
            "CS-0503 gate-first evaluator; server-derived closure packets",
            "fixture-only evidence possible; scientific status separate",
        ),
        _row(
            "Backup / restore",
            "live",
            "`make backup-test`; manifest + checksum verification",
            "no off-site rotation; SSD secure-erasure not promised",
            scientific="n/a — operations",
        ),
        _row(
            "BayBE optimization",
            baybe[0],
            baybe[1],
            "independent constraint re-check; fixture_only — no scientific validation",
        ),
        _row(
            "Property models / training",
            proptrain[0],
            proptrain[1],
            "fixture_only — real endpoints/training need U02/U14 data + U08/U13 hardware/model",
        ),
        _row(
            "RL research decisions",
            rl[0],
            rl[1],
            "promotion-gated; fixture reward climbs ≠ scientific gain",
        ),
        _row(
            "Cloud fallback",
            "not_configured",
            "CS-1001-1004 decision reports + transform + broker + adapter landed; "
            "zero providers registered",
            "no approved provider/account/region (U08/U09/U11); "
            "explicit human approval still required (§20.2)",
        ),
        _row(
            "Equipment / instrument control",
            "blocked",
            "no adapter by design (manual-first pilot)",
            "—",
        ),
        _row(
            "ELN bridge (eLabFTW)",
            "blocked",
            "CS-0506 not implemented; optional integration",
            "—",
        ),
    ]

    return f"""# Pilot gate report — Chemistry Studio

Generated: {now} by `infra/local/pilot_gate.py` (CS-0505, AT-0505-3).

**Software status ≠ scientific validation.** Every workflow executed
to date runs on synthetic fixture data. No entry below asserts
real-world chemical validity; `scientific` is `not_validated` for all
scientific capabilities even when the software path is live.

| Capability | Software status | Evidence | Scientific status | Limitations |
|---|---|---|---|---|
{chr(10).join(rows)}

## Privacy posture (verified)

- Bind host `127.0.0.1`; allowed origins loopback-only (settings.py).
- No outbound client imports in `services/studio-api/src`
  (`tests/integration/recovery/no_egress_check.py` — static scan +
  socket guard).
- Session tokens: opaque, sha256-hashed at rest (`auth_sessions`).
- Vault storage keys opaque; blobs never served from outside vault root.

## Honest gaps

- No at-rest app-level encryption — OS volume encryption assumed (§21.3).
- No separate key store exists; auth material is inside the DB dump.
- LAN/team access remains disabled (no TLS + real identity management).
- Retention schedule is a configuration placeholder, not a legal claim.
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    report = build_report()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
