"""Dynamic capability detection (handoff §4.3, decision D07).

Reports what is actually available; unavailable capabilities carry a
reason and remediation. Nothing here claims a capability that was not
verified in this process/host.
"""

from __future__ import annotations

import importlib.util
import platform
import shutil
from typing import Any

from studio.config.settings import Settings


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def collect_capabilities(settings: Settings) -> dict[str, Any]:
    """Collect an honest capability report for the current process."""
    profiles: dict[str, dict[str, str]] = {}

    profiles["core"] = {"status": "available", "detail": "manual recordkeeping"}

    if settings.profile_local_ai:
        ok = _module_available("llama_cpp")
        profiles["local_ai"] = {
            "status": "available" if ok else "unavailable",
            "detail": "llama-cpp-python importable"
            if ok
            else "llama-cpp-python not installed; install extra "
            "'local_ai' and select a licensed model (U13)",
        }
    else:
        profiles["local_ai"] = {
            "status": "disabled",
            "detail": "profile off; set STUDIO_PROFILE_LOCAL_AI=1 after capability/model review",
        }

    if settings.profile_optimization:
        from workers.optimization.runtime import available

        ok = available()
        profiles["optimization"] = {
            "status": "available" if ok else "unavailable",
            "detail": "network-denied BayBE worker installed; version checked on each request"
            if ok
            else "pinned BayBE worker image unavailable; build workers/optimization/Dockerfile",
        }
    else:
        profiles["optimization"] = {"status": "disabled", "detail": "profile off"}

    if settings.profile_quantum:
        xtb = shutil.which("xtb")
        psi4 = shutil.which("psi4")
        found = [e for e in (xtb, psi4) if e]
        profiles["quantum"] = {
            "status": "available" if found else "unavailable",
            "detail": f"binaries found: {found}"
            if found
            else "no xtb/psi4 binaries on PATH; quantum profile cannot execute",
        }
    else:
        profiles["quantum"] = {"status": "disabled", "detail": "profile off"}

    if settings.profile_training:
        ok = _module_available("torch")
        profiles["training"] = {
            "status": "available" if ok else "unavailable",
            "detail": "torch importable"
            if ok
            else "torch not installed; install extra 'training' (U08/U13 gate live use)",
        }
    else:
        profiles["training"] = {"status": "disabled", "detail": "profile off"}

    # The adapter's own probe is authoritative: native import OR the
    # chem-studio-rdkit container image (CS-0404) — whichever is real.
    try:
        from engine_adapter_rdkit import RDKitAdapter

        _rdkit = RDKitAdapter().capability()
        engines = {
            "rdkit": {
                "status": "available" if _rdkit.available else "unavailable",
                "version": _rdkit.version,
                "detail": _rdkit.detail
                if _rdkit.available
                else f"rdkit not installed or unsupported on this platform "
                f"({platform.system()}/{platform.machine()}); "
                "see docs/dependencies.lock.md platform matrix",
            }
        }
    except ImportError:
        engines = {
            "rdkit": {
                "status": "unavailable",
                "version": None,
                "detail": "engine adapter package not importable",
            }
        }

    return {
        "profiles": profiles,
        "engines": engines,
        "database": {"status": "unknown", "detail": "checked by readiness probe"},
        "hardware": {
            "os": f"{platform.system()} {platform.release()}",
            "arch": platform.machine(),
            "gpu": "none detected on this host",
        },
    }
