"""Scoped similarity algorithms (§16.5, AT-0703-2).

A similarity value is meaningless without its algorithm, version,
relevant range and interpretation limit — so all four are part of the
returned record. Nothing here produces, or may be read as, composition
or identity evidence.
"""

from __future__ import annotations

import math

from .contracts import (
    SIMILARITY_LIMITS,
    SIMILARITY_VERSIONS,
    AnalyticsFailure,
    ScopedSimilarity,
)


def scoped_similarity(
    va: tuple[float, ...],
    vb: tuple[float, ...],
    *,
    algorithm: str,
    x_unit: str,
    range_min: float,
    range_max: float,
) -> ScopedSimilarity:
    if algorithm not in SIMILARITY_VERSIONS:
        raise AnalyticsFailure(
            "ANALYTICS_UNSUPPORTED_INPUT", f"unknown similarity algorithm '{algorithm}'"
        )
    if len(va) != len(vb) or len(va) < 2:
        raise AnalyticsFailure(
            "ANALYTICS_MALFORMED_INPUT", "aligned vectors must share length >= 2"
        )
    if algorithm == "cosine":
        value = _cosine(va, vb)
    else:
        value = _pearson(va, vb)
    return ScopedSimilarity(
        algorithm=algorithm,
        algorithm_version=SIMILARITY_VERSIONS[algorithm],
        value=value,
        scope={
            "x_unit": x_unit,
            "range_min": range_min,
            "range_max": range_max,
            "aligned_points": len(va),
        },
        interpretation_limits=SIMILARITY_LIMITS,
    )


def _cosine(va: tuple[float, ...], vb: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(va, vb, strict=True))
    na = math.sqrt(sum(x * x for x in va))
    nb = math.sqrt(sum(y * y for y in vb))
    if na == 0.0 or nb == 0.0:
        raise AnalyticsFailure(
            "ANALYTICS_DEGENERATE_TRANSFORM",
            "cosine similarity on a zero-norm vector is undefined",
        )
    return dot / (na * nb)


def _pearson(va: tuple[float, ...], vb: tuple[float, ...]) -> float:
    n = len(va)
    ma = sum(va) / n
    mb = sum(vb) / n
    da = [x - ma for x in va]
    db = [y - mb for y in vb]
    num = sum(x * y for x, y in zip(da, db, strict=True))
    den = math.sqrt(sum(x * x for x in da) * sum(y * y for y in db))
    if den == 0.0:
        raise AnalyticsFailure(
            "ANALYTICS_DEGENERATE_TRANSFORM",
            "pearson correlation on a constant vector is undefined",
        )
    return num / den
