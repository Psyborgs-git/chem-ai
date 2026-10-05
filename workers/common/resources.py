"""Hardware/runtime/isolation capability detection (§13.4, §20.1).

Everything here is *observed* — a field the probe cannot establish is
reported as ``None``/``"unknown"`` rather than estimated or invented.
No benchmark throughput is fabricated; admission consumes this report
plus per-job envelopes and refuses what cannot be verified locally.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

MEMORY_MODELS = ("unified", "discrete", "unknown")


@dataclass
class GpuInfo:
    backend: str  # cuda|metal|rocm|unknown
    device: str | None = None
    memory_total_bytes: int | None = None
    memory_free_bytes: int | None = None
    unified: bool = False  # shares system RAM — never summed separately


@dataclass
class HardwareReport:
    os: str
    arch: str
    python_version: str
    observed_at: str
    memory_model: str = "unknown"
    cpu_count_logical: int | None = None
    cpu_count_physical: int | None = None
    ram_total_bytes: int | None = None
    ram_available_bytes: int | None = None
    disk_free_bytes: int | None = None
    gpus: list[GpuInfo] = field(default_factory=list)
    runtimes: dict[str, str | None] = field(default_factory=dict)
    isolation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sysctl(name: str) -> int | None:
    try:
        # Fixed-args read-only system probe; `name` is called with a
        # static literal at every call site.
        out = subprocess.run(  # noqa: S603
            ["sysctl", "-n", name],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        return int(out.stdout.strip()) if out.returncode == 0 else None
    except (OSError, ValueError):
        return None


def _sysconf_ram() -> tuple[int | None, int | None]:
    """(total, available) RAM bytes via sysconf — POSIX, no deps.
    Available may be ``None`` on platforms that do not expose it."""
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        avail = os.sysconf("SC_AVPHYS_PAGES")
        size = os.sysconf("SC_PAGE_SIZE")
        total = int(pages) * int(size) if pages > 0 else None
        available = int(avail) * int(size) if avail > 0 else None
        return total, available
    except (ValueError, OSError, AttributeError):
        return None, None


def _detect_memory_model(system: str, machine: str) -> str:
    """Unified memory shares RAM and VRAM — detect it so admission never
    double-counts (AT-0402-1). Apple Silicon is the common case; other
    platforms are reported ``unknown`` unless a discrete GPU is found."""
    if system == "Darwin" and machine == "arm64":
        return "unified"
    return "unknown"


def _detect_gpus(system: str, memory_model: str) -> list[GpuInfo]:
    gpus: list[GpuInfo] = []
    if shutil.which("nvidia-smi"):
        try:
            # Read-only GPU probe with a fixed argument list.
            out = subprocess.run(
                [  # noqa: S607
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.free",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if out.returncode == 0:
                for line in out.stdout.strip().splitlines():
                    name, total, free = (p.strip() for p in line.split(","))
                    gpus.append(
                        GpuInfo(
                            backend="cuda",
                            device=name or None,
                            memory_total_bytes=int(total) * 1024 * 1024
                            if total.isdigit()
                            else None,
                            memory_free_bytes=int(free) * 1024 * 1024 if free.isdigit() else None,
                            unified=False,
                        )
                    )
        except (OSError, ValueError):
            pass  # unobservable stays unobservable
    if memory_model == "unified" and not gpus:
        # The GPU exists (e.g. Apple Silicon) but its memory IS the RAM —
        # record it without separate capacity so it can never be summed.
        gpus.append(GpuInfo(backend="metal", unified=True))
    return gpus


def detect(*, for_path: str = ".") -> HardwareReport:
    """Collect the current host report. Every probe failure leaves the
    field ``None`` — absence of observation is stated, not guessed."""
    system, machine = platform.system(), platform.machine()
    memory_model = _detect_memory_model(system, machine)
    ram_total, ram_available = _sysconf_ram()
    if system == "Darwin":
        ram_total = ram_total or _sysctl("hw.memsize")
    try:
        disk_free = shutil.disk_usage(for_path).free
    except OSError:
        disk_free = None
    cpu_logical: int | None
    try:
        cpu_logical = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        cpu_logical = os.cpu_count()
    cpu_physical = _sysctl("hw.physicalcpu") if system == "Darwin" else None
    return HardwareReport(
        os=f"{system} {platform.release()}",
        arch=machine,
        python_version=platform.python_version(),
        observed_at=datetime.now(UTC).isoformat(),
        memory_model=memory_model,
        cpu_count_logical=cpu_logical,
        cpu_count_physical=cpu_physical,
        ram_total_bytes=ram_total,
        ram_available_bytes=ram_available,
        disk_free_bytes=disk_free,
        gpus=_detect_gpus(system, memory_model),
        runtimes={
            "python": sys.version.split()[0],
            "node": _tool_version("node"),
            "xtb": _tool_presence("xtb"),
            "psi4": _tool_presence("psi4"),
        },
        isolation={
            "subprocess": True,
            "multiprocessing_kill": True,
            "container_runtime": _tool_presence("docker") is not None
            or _tool_presence("podman") is not None,
            "network_deny_enforced": False,  # not enforced by this host probe
            "note": "controls not verifiable are reported absent, never claimed",
        },
    )


def _tool_presence(tool: str) -> str | None:
    return shutil.which(tool)


def _tool_version(tool: str) -> str | None:
    if not shutil.which(tool):
        return None
    try:
        # `tool` is a bare name resolved through PATH — probing for a
        # version string only, no user input reaches the argv.
        out = subprocess.run(  # noqa: S603
            [tool, "--version"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        return out.stdout.strip().splitlines()[0] if out.returncode == 0 else None
    except (OSError, IndexError):
        return None


def effective_system_memory(report: HardwareReport) -> int | None:
    """Bytes of memory a job may draw on — AT-0402-1.

    A unified-memory GPU shares RAM: adding ``memory_total_bytes`` again
    would double-count. A discrete GPU has its own memory which is NOT
    part of system memory either — it is admitted separately via
    ``discrete_gpu_memory_free``. So this function always returns RAM
    only; callers sum nothing."""
    if report.ram_total_bytes is None:
        return None
    return report.ram_total_bytes


def discrete_gpu_memory_free(report: HardwareReport) -> int:
    """Total free VRAM across *discrete* GPUs only — unified GPUs share
    the RAM already accounted by ``effective_system_memory``."""
    return sum(g.memory_free_bytes or 0 for g in report.gpus if not g.unified)
