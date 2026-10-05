"""CS-0703 adapter tests — fixture-only, no scientific validation claim.

Every fixture spectrum is synthetic; pass/fail here is about format
handling, versioned transforms and scoped similarity records, never
about chemistry.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from engine_adapter_analytics import (
    UNDECLARED_UNIT,
    AnalyticsAdapter,
    AnalyticsFailure,
    CompareSpec,
    IngestSpec,
    SpectrumTrace,
    TransformStep,
)

FIXTURES = Path("fixtures/synthetic/analytics")
ADAPTER = AnalyticsAdapter()


def _jcamp_body(ys: list[int], *, npoints: int | None = None, kind: str = "(X++(Y..Y))") -> bytes:
    lines = [
        "##TITLE=synthetic unit test",
        "##JCAMP-DX=5.01",
        "##DATA TYPE=INFRARED SPECTRUM",
        "##XUNITS=1/CM",
        "##YUNITS=TRANSMITTANCE",
        "##XFACTOR=1.0",
        "##YFACTOR=0.01",
        "##FIRSTX=400.0",
        "##LASTX=440.0",
        f"##NPOINTS={npoints if npoints is not None else len(ys)}",
        "##DELTAX=10.0",
        f"##XYDATA={kind}",
    ]
    for i in range(0, len(ys), 4):
        chunk = ys[i : i + 4]
        lines.append(f"{400.0 + i * 10.0} " + " ".join(str(v) for v in chunk))
    lines.append("##END=")
    return ("\n".join(lines) + "\n").encode()


def _trace(xs: list[float], ys: list[float], x_unit: str = "1/CM") -> SpectrumTrace:
    return SpectrumTrace(x=tuple(xs), y=tuple(ys), x_unit=x_unit, y_unit="TRANSMITTANCE")


# ---------------------------------------------------------------- formats


def test_jcamp_xyplusplus_fixture_parses_with_factors() -> None:
    parsed = ADAPTER.parse((FIXTURES / "ir-film-a.dx").read_bytes(), format="jcamp-dx")
    assert parsed.parser_version == "jcampdx-reader/v1"
    assert len(parsed.trace.x) == 801
    assert parsed.trace.x[0] == pytest.approx(400.0)
    assert parsed.trace.x_unit == "1/CM"
    assert parsed.trace.y_unit == "TRANSMITTANCE"
    assert parsed.metadata["title"].startswith("Synthetic IR export A")


def test_jcamp_xy_pairs_and_npoints_checked() -> None:
    data = (
        b"##TITLE=pairs\n##XUNITS=NM\n##YUNITS=A\n##XYDATA=(X..Y)\n"
        b"200.0 0.1 210.0 0.2\n220.0 0.3\n##END=\n"
    )
    parsed = ADAPTER.parse(data, format="jcamp-dx")
    assert list(parsed.trace.x) == [200.0, 210.0, 220.0]
    with pytest.raises(AnalyticsFailure) as exc:
        ADAPTER.parse(_jcamp_body([10, 20, 30], npoints=9), format="jcamp-dx")
    assert exc.value.code == "ANALYTICS_MALFORMED_INPUT"


def test_jcamp_compressed_encoding_rejected_not_guessed() -> None:
    # SQUEEZED-style token inside a well-formed (X++(Y..Y)) table.
    data = _jcamp_body([10, 20, 30]).replace(b"400.0 10 20 30", b"400.0 10 A20")
    with pytest.raises(AnalyticsFailure) as exc:
        ADAPTER.parse(data, format="jcamp-dx")
    assert exc.value.code == "ANALYTICS_UNSUPPORTED_ENCODING"


def test_jcamp_requires_units_and_known_table_kind() -> None:
    with pytest.raises(AnalyticsFailure) as exc:
        ADAPTER.parse(b"##TITLE=x\n##XYDATA=(X..Y)\n1 2\n", format="jcamp-dx")
    assert exc.value.code == "ANALYTICS_MALFORMED_INPUT"
    data = _jcamp_body([10, 20]).replace(b"(X++(Y..Y))", b"(X<Y)")
    with pytest.raises(AnalyticsFailure) as exc:
        ADAPTER.parse(data, format="jcamp-dx")
    assert exc.value.code == "ANALYTICS_UNSUPPORTED_ENCODING"


def test_csv_xy_preamble_and_strict_two_columns() -> None:
    parsed = ADAPTER.parse((FIXTURES / "uv-sample-a.csv").read_bytes(), format="csv-xy")
    assert parsed.parser_version == "csvxy-reader/v1"
    assert parsed.trace.x_unit == UNDECLARED_UNIT
    assert len(parsed.trace.x) == 601
    assert parsed.metadata["preamble"][0].startswith("# export")
    with pytest.raises(AnalyticsFailure) as exc:
        ADAPTER.parse(b"a,b\n1,2\n3,x\n", format="csv-xy")
    assert exc.value.code == "ANALYTICS_MALFORMED_INPUT"
    with pytest.raises(AnalyticsFailure) as exc:
        ADAPTER.parse(b"1,2,3\n4,5,6\n", format="csv-xy")
    assert exc.value.code == "ANALYTICS_MALFORMED_INPUT"


def test_sniff_is_content_based_and_binary_is_unsupported() -> None:
    assert ADAPTER.detect(b"##TITLE=x\n##XYDATA=(X..Y)\n1 2\n") == "jcamp-dx"
    assert ADAPTER.detect(b"# header\n1.0,2.0\n3.0,4.0\n") == "csv-xy"
    assert ADAPTER.detect(b"\x00\x01\x02\xff" * 8, filename="vendor.spc") is None
    assert ADAPTER.detect(b"<html>nope</html>") is None


# ------------------------------------------------------------ transforms


def test_preprocessing_records_versions_and_degenerates_fail() -> None:
    trace = _trace([1, 2, 3, 4, 5], [10, 20, 30, 20, 10])
    out, records = ADAPTER.process(
        trace,
        [
            TransformStep(kind="baseline_offset", parameters={}),
            TransformStep(kind="minmax_normalize", parameters={}),
        ],
    )
    assert [r.version for r in records] == ["baseline-offset/v1", "minmax-normalize/v1"]
    assert min(out.y) == 0.0 and max(out.y) == 1.0
    assert records[0].parameters["offset"] == 10.0
    with pytest.raises(AnalyticsFailure) as exc:
        ADAPTER.process(
            _trace([1, 2, 3], [7, 7, 7]), [TransformStep(kind="minmax_normalize", parameters={})]
        )
    assert exc.value.code == "ANALYTICS_DEGENERATE_TRANSFORM"
    with pytest.raises(AnalyticsFailure) as exc:
        ADAPTER.process(trace, [TransformStep(kind="moving_average", parameters={"window": 4})])
    assert exc.value.code == "ANALYTICS_UNSUPPORTED_INPUT"


def test_moving_average_window_and_output() -> None:
    trace = _trace([1, 2, 3, 4, 5], [0, 0, 9, 0, 0])
    out, records = ADAPTER.process(
        trace, [TransformStep(kind="moving_average", parameters={"window": 3})]
    )
    assert records[0].version == "moving-average/v1"
    assert out.y == (0.0, 3.0, 3.0, 3.0, 0.0)


# ------------------------------------------------------------- compare


def _compare_spec(algorithm: str = "cosine", **kw: object) -> CompareSpec:
    sim = {"algorithm": algorithm}
    sim.update(kw)
    return CompareSpec.model_validate({"similarity": sim})


def test_scoped_similarity_carries_algorithm_range_limits() -> None:
    a = ADAPTER.parse((FIXTURES / "ir-film-a.dx").read_bytes(), format="jcamp-dx")
    b = ADAPTER.parse((FIXTURES / "ir-film-b.dx").read_bytes(), format="jcamp-dx")
    out = ADAPTER.compare(
        a.trace, b.trace, method_a="infrared", method_b="infrared", spec=_compare_spec()
    )
    s = out.similarity
    assert s.value == pytest.approx(0.996517, abs=1e-4)
    assert s.algorithm == "cosine" and s.algorithm_version == "cosine-similarity/v1"
    assert s.scope["x_unit"] == "1/CM"
    assert s.scope["range_min"] == pytest.approx(400.0)
    assert s.scope["aligned_points"] == 2048
    assert s.scientific_status == "not_composition_evidence"
    assert any(
        "not evidence of identical composition" in lim for lim in s.interpretation_limits
    )
    assert out.transform["alignment"]["version"] == "resample-linear/v1"


def test_compare_refuses_cross_method_cross_unit_undeclared() -> None:
    a = ADAPTER.parse((FIXTURES / "ir-film-a.dx").read_bytes(), format="jcamp-dx")
    b = ADAPTER.parse((FIXTURES / "ir-film-b.dx").read_bytes(), format="jcamp-dx")
    with pytest.raises(AnalyticsFailure) as exc:
        ADAPTER.compare(
            a.trace, b.trace, method_a="infrared", method_b="raman", spec=_compare_spec()
        )
    assert exc.value.code == "ANALYTICS_METHOD_MISMATCH"
    nm_trace = _trace(list(a.trace.x), list(a.trace.y), x_unit="NM")
    with pytest.raises(AnalyticsFailure) as exc:
        ADAPTER.compare(
            nm_trace, b.trace, method_a="infrared", method_b="infrared", spec=_compare_spec()
        )
    assert exc.value.code == "ANALYTICS_UNIT_MISMATCH"
    un = SpectrumTrace(x=a.trace.x, y=a.trace.y, x_unit=UNDECLARED_UNIT, y_unit=UNDECLARED_UNIT)
    with pytest.raises(AnalyticsFailure) as exc:
        ADAPTER.compare(un, b.trace, method_a="infrared", method_b="infrared", spec=_compare_spec())
    assert exc.value.code == "ANALYTICS_UNIT_MISMATCH"


def test_compare_no_overlap_and_range_recording() -> None:
    a = _trace([400, 500, 600], [1, 2, 1])
    b = _trace([700, 800, 900], [1, 2, 1])
    with pytest.raises(AnalyticsFailure) as exc:
        ADAPTER.compare(a, b, method_a="infrared", method_b="infrared", spec=_compare_spec())
    assert exc.value.code == "ANALYTICS_NO_OVERLAP"
    # A constant trace cannot be pearson-compared — recorded, not invented.
    c = _trace([400, 500, 600], [5, 5, 5])
    with pytest.raises(AnalyticsFailure) as exc:
        ADAPTER.compare(
            a,
            c,
            method_a="infrared",
            method_b="infrared",
            spec=_compare_spec(algorithm="pearson"),
        )
    assert exc.value.code == "ANALYTICS_DEGENERATE_TRANSFORM"


def test_pearson_anticorrelation_and_cosine_identity() -> None:
    a = _trace([float(i) for i in range(32)], [math.sin(i / 5) for i in range(32)])
    neg = _trace([float(i) for i in range(32)], [-math.sin(i / 5) for i in range(32)])
    out = ADAPTER.compare(
        a, neg, method_a="infrared", method_b="infrared", spec=_compare_spec("pearson")
    )
    assert out.similarity.value == pytest.approx(-1.0, abs=1e-6)
    same = ADAPTER.compare(a, a, method_a="infrared", method_b="infrared", spec=_compare_spec())
    assert same.similarity.value == pytest.approx(1.0, abs=1e-9)


# ------------------------------------------------------------- spec rules


def test_specs_are_strict_and_bounded() -> None:
    with pytest.raises(ValidationError):
        IngestSpec.model_validate(
            {"method": "mass_spec", "x_unit": "1/CM", "y_unit": "T", "sample": {"label": "x"}}
        )
    with pytest.raises(ValidationError):
        IngestSpec.model_validate(
            {
                "method": "infrared",
                "x_unit": "1/CM",
                "y_unit": "T",
                "sample": {"label": "x"},
                "bogus": True,
            }
        )
    with pytest.raises(ValidationError):
        CompareSpec.model_validate(
            {"similarity": {"algorithm": "cosine", "range_min": 9.0, "range_max": 1.0}}
        )
    spec = IngestSpec.model_validate(
        {
            "method": "infrared",
            "x_unit": "1/CM",
            "y_unit": "TRANSMITTANCE",
            "sample": {"label": "film A"},
        }
    )
    assert spec.digest() == spec.digest()  # deterministic, canonical
