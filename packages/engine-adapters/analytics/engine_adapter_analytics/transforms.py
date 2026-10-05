"""Versioned preprocessing and alignment implementations (§16.5).

Every step is pure stdlib numerics, deterministic, and records its own
pinned version on the result. A transform kind has exactly one
implementation — changing behavior ships a new version, never a silent
edit.
"""

from __future__ import annotations

import math
from typing import Any

from .contracts import (
    ALIGNMENT_VERSIONS,
    MAX_WINDOW,
    MIN_ALIGNED_POINTS,
    TRANSFORM_VERSIONS,
    AlignmentSpec,
    AnalyticsFailure,
    SpectrumTrace,
    TransformRecord,
    TransformStep,
)


def apply_preprocessing(
    trace: SpectrumTrace, steps: list[TransformStep]
) -> tuple[SpectrumTrace, list[TransformRecord]]:
    """Apply declared preprocessing in order; the returned records are
    what was actually applied (kind + pinned version + parameters)."""
    out = trace
    records: list[TransformRecord] = []
    for step in steps:
        out, params = _apply_one(out, step)
        records.append(
            TransformRecord(
                kind=step.kind,
                version=TRANSFORM_VERSIONS[step.kind],
                parameters=params,
            )
        )
    return out, records


def _apply_one(trace: SpectrumTrace, step: TransformStep) -> tuple[SpectrumTrace, dict[str, Any]]:
    x, y = list(trace.x), list(trace.y)
    if step.kind == "baseline_offset":
        params = dict(step.parameters)
        offset = params.get("offset")
        if offset is None:
            offset = min(y)
        elif not isinstance(offset, (int, float)) or isinstance(offset, bool):
            raise AnalyticsFailure(
                "ANALYTICS_UNSUPPORTED_INPUT", "baseline_offset.offset must be numeric"
            )
        if not math.isfinite(float(offset)):
            raise AnalyticsFailure(
                "ANALYTICS_UNSUPPORTED_INPUT", "baseline_offset.offset is not finite"
            )
        unknown = set(params) - {"offset"}
        if unknown:
            raise AnalyticsFailure(
                "ANALYTICS_UNSUPPORTED_INPUT",
                f"baseline_offset got unknown parameters {sorted(unknown)} — "
                "nothing is ignored silently",
            )
        return (
            SpectrumTrace(
                x=tuple(x),
                y=tuple(v - float(offset) for v in y),
                x_unit=trace.x_unit,
                y_unit=trace.y_unit,
            ),
            {"offset": float(offset)},
        )
    if step.kind == "minmax_normalize":
        if step.parameters:
            raise AnalyticsFailure(
                "ANALYTICS_UNSUPPORTED_INPUT",
                "minmax_normalize takes no parameters",
            )
        lo, hi = min(y), max(y)
        span = hi - lo
        if span <= 0 or not math.isfinite(span):
            raise AnalyticsFailure(
                "ANALYTICS_DEGENERATE_TRANSFORM",
                "minmax_normalize on a constant or degenerate trace is undefined — "
                "no value is invented",
            )
        return (
            SpectrumTrace(
                x=tuple(x),
                y=tuple((v - lo) / span for v in y),
                x_unit=trace.x_unit,
                y_unit=trace.y_unit,
            ),
            {"min": lo, "span": span},
        )
    if step.kind == "moving_average":
        params = dict(step.parameters)
        window = params.get("window", 5)
        unknown = set(params) - {"window"}
        if unknown:
            raise AnalyticsFailure(
                "ANALYTICS_UNSUPPORTED_INPUT",
                f"moving_average got unknown parameters {sorted(unknown)}",
            )
        if (
            not isinstance(window, int)
            or isinstance(window, bool)
            or window < 3
            or window > MAX_WINDOW
            or window % 2 == 0
        ):
            raise AnalyticsFailure(
                "ANALYTICS_UNSUPPORTED_INPUT",
                f"moving_average.window must be an odd integer 3..{MAX_WINDOW}",
            )
        if window > len(y):
            raise AnalyticsFailure(
                "ANALYTICS_UNSUPPORTED_INPUT",
                f"window {window} exceeds trace length {len(y)}",
            )
        half = window // 2
        smoothed = [
            sum(y[max(0, i - half) : min(len(y), i + half + 1)])
            / len(y[max(0, i - half) : min(len(y), i + half + 1)])
            for i in range(len(y))
        ]
        return (
            SpectrumTrace(x=tuple(x), y=tuple(smoothed), x_unit=trace.x_unit, y_unit=trace.y_unit),
            {"window": window},
        )
    raise AnalyticsFailure(  # pragma: no cover - Literal guarantees this never fires
        "ANALYTICS_UNSUPPORTED_INPUT", f"unknown transform '{step.kind}'"
    )


def align(
    a: SpectrumTrace,
    b: SpectrumTrace,
    spec: AlignmentSpec,
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...], TransformRecord]:
    """Resample both traces onto one uniform grid over their shared x
    overlap. Traces that do not overlap cannot be compared — that is a
    typed failure, not an extrapolation."""
    lo = max(a.x[0], b.x[0])
    hi = min(a.x[-1], b.x[-1])
    if not lo < hi:
        raise AnalyticsFailure(
            "ANALYTICS_NO_OVERLAP",
            f"traces do not overlap in x ([{a.x[0]}..{a.x[-1]}] vs "
            f"[{b.x[0]}..{b.x[-1]}] {a.x_unit}) — no grid is fabricated",
        )
    n = spec.points
    step = (hi - lo) / (n - 1)
    grid = tuple(lo + i * step for i in range(n))
    va = _resample(a, grid)
    vb = _resample(b, grid)
    record = TransformRecord(
        kind="resample_linear",
        version=ALIGNMENT_VERSIONS["resample_linear"],
        parameters={"points": n, "range_min": lo, "range_max": hi, "x_unit": a.x_unit},
    )
    return grid, va, vb, record


def _resample(trace: SpectrumTrace, grid: tuple[float, ...]) -> tuple[float, ...]:
    """Piecewise-linear interpolation; every grid point lies inside the
    trace domain by construction."""
    x, y = trace.x, trace.y
    out: list[float] = []
    j = 0
    for gx in grid:
        while j < len(x) - 2 and x[j + 1] < gx:
            j += 1
        x0, x1 = x[j], x[j + 1]
        t = (gx - x0) / (x1 - x0)
        out.append(y[j] + t * (y[j + 1] - y[j]))
    return tuple(out)


def crop_to_range(
    grid: tuple[float, ...],
    va: tuple[float, ...],
    vb: tuple[float, ...],
    *,
    range_min: float | None,
    range_max: float | None,
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    """Apply the caller's similarity range; the effective bounds are
    always the recorded ones, never implied."""
    lo = grid[0] if range_min is None else max(range_min, grid[0])
    hi = grid[-1] if range_max is None else min(range_max, grid[-1])
    idx = [i for i, gx in enumerate(grid) if lo <= gx <= hi]
    if len(idx) < MIN_ALIGNED_POINTS:
        raise AnalyticsFailure(
            "ANALYTICS_NO_OVERLAP",
            f"similarity range [{lo}..{hi}] leaves {len(idx)} aligned points "
            f"(minimum {MIN_ALIGNED_POINTS})",
        )
    return (
        tuple(grid[i] for i in idx),
        tuple(va[i] for i in idx),
        tuple(vb[i] for i in idx),
    )
