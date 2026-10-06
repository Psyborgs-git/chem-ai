"""Dynamic capability detection (handoff §4.3, decision D07).

Reports what is actually available; unavailable capabilities carry a
reason and remediation. Nothing here claims a capability that was not
verified in this process/host.
"""

from __future__ import annotations

import importlib.util
import platform
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
        from workers.chemistry.quantum.runtime import IMAGE as QUANTUM_IMAGE
        from workers.chemistry.quantum.runtime import available, capability

        ok = available()
        probe = capability() if ok else None
        detail = QUANTUM_IMAGE
        if probe:
            states = {name: state["state"] for name, state in (probe.get("programs") or {}).items()}
            detail = f"{QUANTUM_IMAGE}; programs: {states}"
        profiles["quantum"] = {
            "status": "available" if ok else "unavailable",
            "detail": detail
            if ok
            else "pinned QCEngine worker image unavailable; "
            "build workers/chemistry/quantum/Dockerfile",
        }
    else:
        profiles["quantum"] = {"status": "disabled", "detail": "profile off"}

    if settings.profile_materials:
        from workers.chemistry.materials.runtime import IMAGE as MATERIALS_IMAGE
        from workers.chemistry.materials.runtime import available, capability

        ok = available()
        probe = capability() if ok else None
        detail = MATERIALS_IMAGE
        if probe:
            methods = {name: m["state"] for name, m in (probe.get("methods") or {}).items()}
            detail = f"{MATERIALS_IMAGE}; methods: {methods}"
        profiles["materials"] = {
            "status": "available" if ok else "unavailable",
            "detail": detail
            if ok
            else "pinned thermo worker image unavailable; "
            "build workers/chemistry/materials/Dockerfile",
        }
    else:
        profiles["materials"] = {"status": "disabled", "detail": "profile off"}

    if settings.profile_training:
        try:
            from workers.training.sft.runtime import available as sft_available

            ok = sft_available()
        except Exception:
            ok = False
        profiles["training"] = {
            "status": "available" if ok else "unavailable",
            "detail": "isolated sft worker image live"
            if ok
            else "pinned sft worker image unavailable; build workers/training/sft/Dockerfile",
        }
    else:
        profiles["training"] = {"status": "disabled", "detail": "profile off"}

    if settings.profile_design:
        from workers.chemistry.design.runtime import IMAGE as DESIGN_IMAGE
        from workers.chemistry.design.runtime import available, capability

        ok = available()
        probe = capability() if ok else None
        detail = DESIGN_IMAGE
        if probe:
            methods = {name: m["state"] for name, m in (probe.get("methods") or {}).items()}
            detail = f"{DESIGN_IMAGE}; methods: {methods}"
        profiles["design"] = {
            "status": "available" if ok else "unavailable",
            "detail": detail
            if ok
            else "pinned reinvent worker image unavailable; "
            "build workers/chemistry/design/Dockerfile",
        }
    else:
        profiles["design"] = {"status": "disabled", "detail": "profile off"}

    if settings.profile_synthesis:
        from workers.chemistry.synthesis.runtime import IMAGE as SYNTHESIS_IMAGE
        from workers.chemistry.synthesis.runtime import available, capability

        ok = available()
        probe = capability() if ok else None
        detail = SYNTHESIS_IMAGE
        if probe:
            methods = {name: m["state"] for name, m in (probe.get("methods") or {}).items()}
            detail = f"{SYNTHESIS_IMAGE}; methods: {methods}"
        profiles["synthesis"] = {
            "status": "available" if ok else "unavailable",
            "detail": detail
            if ok
            else "pinned aizynthfinder worker image unavailable; "
            "build workers/chemistry/synthesis/Dockerfile",
        }
    else:
        profiles["synthesis"] = {"status": "disabled", "detail": "profile off"}

    # The adapter's own probe is authoritative: native import OR the
    # chem-studio-rdkit container image (CS-0404) — whichever is real.
    try:
        from engine_adapter_rdkit import RDKitAdapter

        _rdkit = RDKitAdapter().capability()
        engines: dict[str, dict[str, Any]] = {
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

    # QCEngine adapter: per-program §16.1 labels probed inside the
    # pinned image — never claimed available when it is not.
    try:
        from workers.chemistry.quantum.runtime import capability as _qc_probe

        _qc = _qc_probe()
        if _qc is None:
            engines["qcengine"] = {
                "status": "unavailable",
                "version": None,
                "detail": "pinned QCEngine worker image not installed on this host",
            }
        else:
            worst = "available"
            parts = []
            for name, p in sorted((_qc.get("programs") or {}).items()):
                parts.append(f"{name}={p['state']}")
                if p["state"] != "available_tested":
                    worst = "degraded"
            engines["qcengine"] = {
                "status": worst,
                "version": _qc.get("qcengine_version"),
                "detail": f"qcengine-adapter/v1; {', '.join(parts)}",
            }
    except ImportError:
        engines["qcengine"] = {
            "status": "unavailable",
            "version": None,
            "detail": "engine adapter package not importable",
        }

    # thermo adapter: §16.1 state probed inside the pinned image. When
    # enabled, the card carries the method record's benchmark, domain,
    # and limits verbatim — real state, never implied coverage.
    try:
        from workers.chemistry.materials.runtime import capability as _mt_probe

        _mt = _mt_probe()
        if _mt is None:
            engines["materials"] = {
                "status": "unavailable",
                "version": None,
                "detail": "pinned thermo worker image not installed on this host",
            }
        else:
            worst = "available"
            parts = []
            method_cards: dict[str, Any] = {}
            for name, m in sorted((_mt.get("methods") or {}).items()):
                parts.append(f"{name}={m['state']}")
                if m["state"] != "available_tested":
                    worst = "degraded"
                method_cards[name] = {
                    "endpoint": m.get("endpoint"),
                    "domain": m.get("domain"),
                    "benchmark": m.get("benchmark"),
                    "limitations": m.get("limitations") or [],
                }
            engines["materials"] = {
                "status": worst,
                "version": _mt.get("engine_version"),
                "detail": f"{_mt.get('adapter_version')}; {', '.join(parts)}",
                "methods": method_cards,
            }
    except ImportError:
        engines["materials"] = {
            "status": "unavailable",
            "version": None,
            "detail": "engine adapter package not importable",
        }

    # reinvent adapter (CS-0903): §16.1 state probed inside the pinned
    # image, with the method record's domain/benchmark/limits and the
    # licensed-asset registry carried verbatim.
    try:
        from workers.chemistry.design.runtime import capability as _rv_probe

        _rv = _rv_probe()
        if _rv is None:
            engines["reinvent"] = {
                "status": "unavailable",
                "version": None,
                "detail": "pinned reinvent worker image not installed on this host",
            }
        else:
            worst = "available"
            parts = []
            rv_cards: dict[str, Any] = {}
            for name, m in sorted((_rv.get("methods") or {}).items()):
                parts.append(f"{name}={m['state']}")
                if m["state"] != "available_tested":
                    worst = "degraded"
                rv_cards[name] = {
                    "endpoint": m.get("endpoint"),
                    "domain": m.get("domain"),
                    "benchmark": m.get("benchmark"),
                    "limitations": m.get("limitations") or [],
                    "assets": m.get("assets") or {},
                }
            engines["reinvent"] = {
                "status": worst,
                "version": _rv.get("engine_version"),
                "detail": f"{_rv.get('adapter_version')}; {', '.join(parts)}",
                "methods": rv_cards,
            }
    except ImportError:
        engines["reinvent"] = {
            "status": "unavailable",
            "version": None,
            "detail": "engine adapter package not importable",
        }

    # aizynthfinder adapter (CS-0903): same honest-state pattern —
    # proposed routes are never execution authority.
    try:
        from workers.chemistry.synthesis.runtime import capability as _az_probe

        _az = _az_probe()
        if _az is None:
            engines["aizynthfinder"] = {
                "status": "unavailable",
                "version": None,
                "detail": "pinned aizynthfinder worker image not installed on this host",
            }
        else:
            worst = "available"
            parts = []
            az_cards: dict[str, Any] = {}
            for name, m in sorted((_az.get("methods") or {}).items()):
                parts.append(f"{name}={m['state']}")
                if m["state"] != "available_tested":
                    worst = "degraded"
                az_cards[name] = {
                    "endpoint": m.get("endpoint"),
                    "domain": m.get("domain"),
                    "benchmark": m.get("benchmark"),
                    "limitations": m.get("limitations") or [],
                    "assets": m.get("assets") or {},
                }
            engines["aizynthfinder"] = {
                "status": worst,
                "version": _az.get("engine_version"),
                "detail": f"{_az.get('adapter_version')}; {', '.join(parts)}",
                "methods": az_cards,
            }
    except ImportError:
        engines["aizynthfinder"] = {
            "status": "unavailable",
            "version": None,
            "detail": "engine adapter package not importable",
        }

    # Analytics adapter (CS-0703): in-process stdlib numerics — the
    # honest capability is which export formats it parses; scientific
    # validation is never claimed (§16.1).
    try:
        from engine_adapter_analytics import AnalyticsAdapter

        _an = AnalyticsAdapter().capability()
        engines["analytics"] = {
            "status": "available",
            "version": _an["adapter_version"],
            "detail": "formats: "
            + ", ".join(sorted(_an["formats"]))
            + "; scientific_status=not_validated",
        }
    except ImportError:
        engines["analytics"] = {
            "status": "unavailable",
            "version": None,
            "detail": "engine adapter package not importable",
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
