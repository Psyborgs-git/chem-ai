"""CS-0402 unit tests — capability report honesty + envelope bounds.

AT-0402-1  unified-memory report → RAM/VRAM never double-counted
"""

from __future__ import annotations

import pytest
from workers.common.resources import (
    GpuInfo,
    HardwareReport,
    discrete_gpu_memory_free,
    effective_system_memory,
)

from studio.domain.runs.admission import MAX_WALL_SECONDS, validate_envelope
from studio.errors import DomainError

GB = 1024**3


def _report(**kw) -> HardwareReport:
    base = dict(
        os="Darwin 23.0",
        arch="arm64",
        python_version="3.12.0",
        observed_at="2025-01-01T00:00:00+00:00",
    )
    return HardwareReport(**{**base, **kw})


# AT-0402-1 -----------------------------------------------------------


def test_unified_memory_not_double_counted() -> None:
    """Apple-Silicon-style report: the GPU's memory IS the RAM — it must
    never be added on top."""
    r = _report(
        memory_model="unified",
        ram_total_bytes=64 * GB,
        gpus=[GpuInfo(backend="metal", unified=True, memory_total_bytes=64 * GB)],
    )
    assert effective_system_memory(r) == 64 * GB  # not 128
    assert discrete_gpu_memory_free(r) == 0


def test_discrete_gpu_is_separate_not_summed() -> None:
    """A discrete GPU's VRAM is tracked independently — it is neither
    added to system RAM nor lost."""
    r = _report(
        memory_model="discrete",
        ram_total_bytes=64 * GB,
        gpus=[
            GpuInfo(
                backend="cuda",
                device="RTX",
                memory_total_bytes=24 * GB,
                memory_free_bytes=20 * GB,
                unified=False,
            )
        ],
    )
    assert effective_system_memory(r) == 64 * GB
    assert discrete_gpu_memory_free(r) == 20 * GB


def test_unobserved_fields_stay_unknown() -> None:
    """A field the probe cannot establish is None/'unknown' — never a
    fabricated number."""
    r = _report()  # nothing observed
    assert r.memory_model == "unknown"
    assert r.ram_total_bytes is None
    assert effective_system_memory(r) is None
    assert discrete_gpu_memory_free(r) == 0


# Envelope bounds ------------------------------------------------------


@pytest.mark.parametrize(
    "env",
    [
        {"memory_bytes": -1},
        {"cpu_cores": 1.5},
        {"memory_bytes": "8Gi"},
        {"wall_seconds": 0},
        {"wall_seconds": MAX_WALL_SECONDS + 1},
        {"gpu_devices": True},
    ],
)
def test_envelope_rejects_unbounded_or_typed_wrong(env) -> None:
    with pytest.raises(DomainError):
        validate_envelope(env)


def test_envelope_defaults() -> None:
    env = validate_envelope({"memory_bytes": 1 * GB})
    assert env["cpu_cores"] == 0
    assert env["wall_seconds"] == 3600
