"""Versioned, deliberately narrow analytical-data contracts (CS-0703).

Scope (§16.5): store raw instrument exports with method/calibration/
sample metadata and reviewed derived values; process them with named,
versioned transforms; compare with a *scoped* similarity that carries
its algorithm, version, relevant range and interpretation limit on the
result. Nothing here interprets composition — a similarity value is
never recipe or molecular identity.

Selected instrument export formats (the only ones this adapter reads):

- ``jcamp-dx``   JCAMP-DX ASCII (##XYDATA / ##XYPOINTS / ##DATA TABLE /
                 ##PEAK TABLE in AFFN `(X..Y)` or `(X++(Y..Y))` form) —
                 the vendor-neutral exchange format for IR/UV-Vis/Raman
                 benchtop instruments. Compressed DIFDUP/SQUEEZED forms
                 are rejected explicitly, never guessed.
- ``csv-xy``     generic two-column delimiter-separated exports
                 (comma/semicolon/tab) emitted by instrument software —
                 the universal fallback export.

Anything else is ``unsupported`` at ingest: the raw bytes stay stored,
no interpretation is produced (AT-0703-3).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ADAPTER_VERSION: Literal["analytics-adapter/v1"] = "analytics-adapter/v1"
SCHEMA_VERSION: Literal["1"] = "1"

# ------------------------------------------------------------------
# Support matrices — explicit and closed. A format/transform/algorithm
# not listed here does not exist for this adapter.
# ------------------------------------------------------------------

SUPPORTED_FORMATS: dict[str, str] = {
    "jcamp-dx": "jcampdx-reader/v1",
    "csv-xy": "csvxy-reader/v1",
}

# Analytical methods this adapter distinguishes. Comparison is only
# meaningful inside one method — the service enforces it, the label is
# recorded on the series so a spectrum can never silently drift across
# methods.
ANALYTICAL_METHODS = ("infrared", "uv_vis", "raman", "nmr_1h")
AnalyticalMethod = Literal["infrared", "uv_vis", "raman", "nmr_1h"]

# Each transform kind has exactly one implementation version. The
# version is pinned here and copied onto every result record — a later
# v2 ships beside v1, never replaces its meaning.
TRANSFORM_KINDS = ("baseline_offset", "minmax_normalize", "moving_average")
TRANSFORM_VERSIONS: dict[str, str] = {
    "baseline_offset": "baseline-offset/v1",
    "minmax_normalize": "minmax-normalize/v1",
    "moving_average": "moving-average/v1",
}
ALIGNMENT_KINDS = ("resample_linear",)
ALIGNMENT_VERSIONS: dict[str, str] = {"resample_linear": "resample-linear/v1"}
SIMILARITY_ALGORITHMS = ("cosine", "pearson")
SIMILARITY_VERSIONS: dict[str, str] = {
    "cosine": "cosine-similarity/v1",
    "pearson": "pearson-correlation/v1",
}

MAX_POINTS = 1_000_000
MIN_ALIGNED_POINTS = 8
MAX_RESAMPLE_POINTS = 65_536
MAX_WINDOW = 101

# Marker unit for unitless exports (csv-xy): the operator's declared
# units in the ingest spec replace it before anything is persisted or
# compared. A trace that still carries it can never have been reviewed.
UNDECLARED_UNIT = "undeclared"

# Interpretation limits that ALWAYS travel with a similarity value
# (§16.5). They are part of the result, not a UI footnote.
SIMILARITY_LIMITS = (
    "similarity is scoped to the aligned x range and the selected algorithm only",
    "a matching similarity value is not evidence of identical "
    "composition, recipe, or molecular identity",
    "a single spectrum cannot establish complete composition; "
    "independent analytical methods and functional evidence remain "
    "separate",
    "preprocessing and alignment choices change the value; the exact "
    "transform record is required to reproduce it",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AnalyticsFailure(Exception):
    """Typed adapter failure — the service maps codes onto run/record
    states; raw {code, message} only, never a traceback."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ------------------------------------------------------------------
# Request shapes
# ------------------------------------------------------------------


class InstrumentContext(StrictModel):
    """Instrument/method metadata — recorded, never defaulted."""

    vendor: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=200)
    resolution: str | None = Field(default=None, max_length=120)
    medium: str | None = Field(default=None, max_length=200)


class CalibrationContext(StrictModel):
    """Calibration state at measurement time (§16.5)."""

    reference: str | None = Field(default=None, max_length=200)
    performed_at: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=500)


class SampleContext(StrictModel):
    """What the spectrum was measured on — lineage, not inference."""

    sample_id: str | None = Field(default=None, max_length=64)
    label: str = Field(min_length=1, max_length=200)
    preparation: str | None = Field(default=None, max_length=500)


class TransformStep(StrictModel):
    """One named preprocessing step. The version is NOT caller input —
    it is pinned by the adapter and recorded on the result."""

    kind: Literal["baseline_offset", "minmax_normalize", "moving_average"]
    parameters: dict[str, int | float | str | bool] = Field(default_factory=dict, max_length=4)


class AlignmentSpec(StrictModel):
    kind: Literal["resample_linear"] = "resample_linear"
    points: int = Field(default=2048, ge=MIN_ALIGNED_POINTS, le=MAX_RESAMPLE_POINTS, strict=True)


class SimilaritySpec(StrictModel):
    """The requested comparison. ``range_min/max`` bound the x axis in
    the trace's own unit; omitted bounds fall back to the exact overlap
    of the two aligned traces — still recorded on the result."""

    algorithm: Literal["cosine", "pearson"]
    range_min: float | None = None
    range_max: float | None = None

    @model_validator(mode="after")
    def ordered_range(self) -> SimilaritySpec:
        if (
            self.range_min is not None
            and self.range_max is not None
            and not self.range_min < self.range_max
        ):
            raise ValueError("range_min must be below range_max")
        return self


class IngestSpec(StrictModel):
    """Declared ingest: method + context + optional preprocessing that
    is applied to the parsed trace before it is persisted as the derived
    processed artifact. Declared units are required operator metadata
    (§16.5): csv-xy exports carry no units so they supply them; a
    format-native unit (JCAMP) must agree with the declared one —
    mismatch is a conflict error, never a silent override."""

    schema_version: Literal["1"] = "1"
    method: AnalyticalMethod
    label: str | None = Field(default=None, max_length=200)
    x_unit: str = Field(min_length=1, max_length=60)
    y_unit: str = Field(min_length=1, max_length=60)
    instrument: InstrumentContext = Field(default_factory=InstrumentContext)
    calibration: CalibrationContext | None = None
    sample: SampleContext
    preprocessing: list[TransformStep] = Field(default_factory=list, max_length=8)

    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()


class CompareSpec(StrictModel):
    """One scoped comparison of two already-processed series."""

    schema_version: Literal["1"] = "1"
    preprocessing: list[TransformStep] = Field(default_factory=list, max_length=8)
    alignment: AlignmentSpec = Field(default_factory=AlignmentSpec)
    similarity: SimilaritySpec

    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()


# ------------------------------------------------------------------
# Result shapes
# ------------------------------------------------------------------


class SpectrumTrace(StrictModel):
    """A parsed x/y trace — always ordered ascending in x. Units may be
    the literal ``undeclared`` only for a unitless export that has not
    yet been given the operator's declared units (csv-xy ingest)."""

    x: tuple[float, ...] = Field(min_length=2, max_length=MAX_POINTS)
    y: tuple[float, ...] = Field(min_length=2, max_length=MAX_POINTS)
    x_unit: str = Field(min_length=1, max_length=60)
    y_unit: str = Field(min_length=1, max_length=60)

    @model_validator(mode="after")
    def consistent(self) -> SpectrumTrace:
        if len(self.x) != len(self.y):
            raise ValueError("x and y must have equal length")
        return self


class TransformRecord(StrictModel):
    """What the adapter actually applied — persisted on the result."""

    kind: str
    version: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ScopedSimilarity(StrictModel):
    """A similarity value with its full scope attached (§16.5, AT-0703-2)."""

    algorithm: str
    algorithm_version: str
    value: float
    scope: dict[str, Any]  # {x_unit, range_min, range_max, aligned_points}
    interpretation_limits: tuple[str, ...] = SIMILARITY_LIMITS
    adapter_version: str = ADAPTER_VERSION
    scientific_status: Literal["not_composition_evidence"] = "not_composition_evidence"
