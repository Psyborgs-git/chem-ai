"""Analytics processing adapter facade (CS-0703, §16.5).

Pure stdlib — parsing, versioning and scoped comparison all run in
process. Isolation is unnecessary at this complexity; a heavier
signal-processing engine would belong behind the isolated-runner
pattern instead.

The adapter never interprets composition. ``compare`` enforces the
only cross-checks it can honestly enforce — same method, same x unit —
and returns a value whose scope is part of the record.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from . import formats, similarity, transforms
from .contracts import (
    ADAPTER_VERSION,
    ALIGNMENT_VERSIONS,
    ANALYTICAL_METHODS,
    SIMILARITY_VERSIONS,
    SUPPORTED_FORMATS,
    TRANSFORM_VERSIONS,
    UNDECLARED_UNIT,
    AnalyticsFailure,
    CompareSpec,
    ScopedSimilarity,
    SpectrumTrace,
    TransformRecord,
    TransformStep,
)
from .formats import ParsedExport


class ComparisonResult(NamedTuple):
    similarity: ScopedSimilarity
    transform: dict[str, Any]


class AnalyticsAdapter:
    """The only call surface for analytical processing."""

    def capability(self) -> dict[str, Any]:
        """Report the real state of this adapter (§16.1 labels)."""
        return {
            "adapter_version": ADAPTER_VERSION,
            "formats": {
                name: {"state": "available_tested", "parser_version": version}
                for name, version in SUPPORTED_FORMATS.items()
            },
            "methods": list(ANALYTICAL_METHODS),
            "transforms": dict(TRANSFORM_VERSIONS),
            "alignment": dict(ALIGNMENT_VERSIONS),
            "similarity": dict(SIMILARITY_VERSIONS),
            "scientific_status": "not_validated",
        }

    def detect(self, data: bytes, *, filename: str | None = None) -> str | None:
        """Content-sniff the export format. ``None`` = unsupported: the
        caller stores the raw bytes and marks interpretation unsupported
        (AT-0703-3) — no guessing, no fallback parser."""
        return formats.sniff_format(data, filename)

    def parse(self, data: bytes, *, format: str) -> ParsedExport:
        """Parse one export with the pinned reader for that format."""
        return formats.parse(data, format)

    def process(
        self, trace: SpectrumTrace, steps: list[TransformStep]
    ) -> tuple[SpectrumTrace, list[TransformRecord]]:
        """Apply declared ingest preprocessing, recording what ran."""
        return transforms.apply_preprocessing(trace, steps)

    def compare(
        self,
        trace_a: SpectrumTrace,
        trace_b: SpectrumTrace,
        *,
        method_a: str,
        method_b: str,
        spec: CompareSpec,
    ) -> ComparisonResult:
        """One scoped comparison. Cross-method and cross-unit pairs are
        refused — a number produced across them would be meaningless
        (§16.5)."""
        if method_a != method_b:
            raise AnalyticsFailure(
                "ANALYTICS_METHOD_MISMATCH",
                f"cannot compare '{method_a}' with '{method_b}' — analytical "
                "methods are compared separately, never merged",
            )
        if trace_a.x_unit.lower() != trace_b.x_unit.lower():
            raise AnalyticsFailure(
                "ANALYTICS_UNIT_MISMATCH",
                f"x units differ ({trace_a.x_unit!r} vs {trace_b.x_unit!r}); "
                "no silent unit conversion is performed",
            )
        if trace_a.x_unit == UNDECLARED_UNIT or trace_a.y_unit == UNDECLARED_UNIT:
            raise AnalyticsFailure(
                "ANALYTICS_UNIT_MISMATCH",
                "traces carry undeclared units — declared units must be "
                "recorded at ingest before any comparison",
            )
        a, rec_a = transforms.apply_preprocessing(trace_a, spec.preprocessing)
        b, rec_b = transforms.apply_preprocessing(trace_b, spec.preprocessing)
        grid, va, vb, align_record = transforms.align(a, b, spec.alignment)
        grid, va, vb = transforms.crop_to_range(
            grid,
            va,
            vb,
            range_min=spec.similarity.range_min,
            range_max=spec.similarity.range_max,
        )
        scoped = similarity.scoped_similarity(
            va,
            vb,
            algorithm=spec.similarity.algorithm,
            x_unit=a.x_unit,
            range_min=grid[0],
            range_max=grid[-1],
        )
        return ComparisonResult(
            similarity=scoped,
            transform={
                "preprocessing": {
                    "left": [r.model_dump(mode="json") for r in rec_a],
                    "right": [r.model_dump(mode="json") for r in rec_b],
                },
                "alignment": align_record.model_dump(mode="json"),
            },
        )
