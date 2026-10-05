"""Pinned analytical-data processing adapter; stdlib-only, no science dependencies."""

from .adapter import AnalyticsAdapter
from .contracts import (
    ADAPTER_VERSION,
    UNDECLARED_UNIT,
    AnalyticalMethod,
    AnalyticsFailure,
    CompareSpec,
    IngestSpec,
    ScopedSimilarity,
    SpectrumTrace,
    TransformStep,
)

__all__ = [
    "ADAPTER_VERSION",
    "UNDECLARED_UNIT",
    "AnalyticalMethod",
    "AnalyticsAdapter",
    "AnalyticsFailure",
    "CompareSpec",
    "IngestSpec",
    "ScopedSimilarity",
    "SpectrumTrace",
    "TransformStep",
]
