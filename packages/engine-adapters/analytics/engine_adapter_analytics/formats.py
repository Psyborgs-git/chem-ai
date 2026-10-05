"""Selected instrument-export readers (CS-0703, §16.5).

Two real export formats, parsed with the standard library only:

- ``jcamp-dx``: ASCII JCAMP-DX AFFN tables (XYDATA/XYPOINTS/DATA TABLE/
  PEAK TABLE in `(X..Y)` or `(X++(Y..Y))` form). Compressed forms
  (DIFDUP/SQUEEZED digit-letter codes) are detected and rejected as
  ``ANALYTICS_UNSUPPORTED_ENCODING`` — never partially parsed.
- ``csv-xy``:   two-column delimiter-separated numeric exports
  (comma/semicolon/tab) with an optional preamble. The file carries no
  units — they are supplied by the caller's declared method metadata.

Detection is content sniffing; a file that matches neither grammar is
``unsupported`` upstream, not a parse attempt with guesses.
"""

from __future__ import annotations

import math
import re
from typing import Any, NamedTuple

from .contracts import (
    SUPPORTED_FORMATS,
    UNDECLARED_UNIT,
    AnalyticsFailure,
    SpectrumTrace,
)

# LDR: '##NAME=value'; canonical names may contain a space (PEAK TABLE,
# DATA TABLE), so the name is everything up to the first '='.
_JCAMP_LABEL = re.compile(r"^\s*##\s*(.+?)\s*=\s*(.*)$")
_JCAMP_DATA_CLASSES = ("XYDATA", "XYPOINTS", "PEAK TABLE", "DATA TABLE")
# AFFN compressed codes: DIFDUP (%+JKLMNOPQR or their lowercase), SQUEEZED
# (+ABC…/abc…), SQZ/PCS variants. Any alphabetic or % token inside a data
# block means the encoding is one we deliberately do not interpret.
_AFFN_COMPRESSED_TOKEN = re.compile(r"[%@A-Za-z]")
_DELIMITERS = (",", ";", "\t")
_MAX_ROWS = 1_000_000


class ParsedExport(NamedTuple):
    format: str
    parser_version: str
    trace: SpectrumTrace
    metadata: dict[str, Any]
    warnings: tuple[str, ...]


def sniff_format(data: bytes, filename: str | None = None) -> str | None:
    """Detect the export format from content; None = unsupported.

    A filename extension is only a hint for sniffing order — never the
    decision itself.
    """
    text = _decode(data)
    if text is not None:
        head = text[:4096]
        if "##" in head and any(
            f"##{dc}" in head.upper() or f"## {dc}" in head.upper() for dc in _JCAMP_DATA_CLASSES
        ):
            return "jcamp-dx"
        if _looks_like_csv_xy(text):
            return "csv-xy"
    # Binary exports (spc/spa/spc-g, vendor binaries) never decode —
    # they are unsupported, not guessed.
    if filename and filename.lower().endswith((".jdx", ".dx", ".jcamp")):
        return "jcamp-dx" if _JCAMP_LABEL.search((text or "")[:1024]) else None
    return None


def parse(data: bytes, format: str) -> ParsedExport:
    if format not in SUPPORTED_FORMATS:
        raise AnalyticsFailure("ANALYTICS_UNSUPPORTED_FORMAT", f"no reader for format '{format}'")
    text = _decode(data)
    if text is None:
        raise AnalyticsFailure("ANALYTICS_MALFORMED_INPUT", "export is not decodable text")
    if format == "jcamp-dx":
        return _parse_jcamp(text)
    return _parse_csv_xy(text)


def _decode(data: bytes) -> str | None:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return data.decode("latin-1")
        except UnicodeDecodeError:
            return None


# ------------------------------------------------------------------
# jcamp-dx
# ------------------------------------------------------------------


def _parse_jcamp(text: str) -> ParsedExport:
    headers: dict[str, str] = {}
    data_lines: list[str] = []
    data_class: str | None = None
    warnings: list[str] = []
    in_data = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        m = _JCAMP_LABEL.match(line)
        if m:
            label = m.group(1).upper().strip()
            value = m.group(2).strip()
            if label in _JCAMP_DATA_CLASSES:
                data_class = label
                in_data = True
                headers[label] = value
                continue
            headers[label] = value
            continue
        if line.lstrip().startswith("$$"):
            continue  # comment line
        if in_data:
            data_lines.append(line)
        else:
            # Non-label preamble before any ## — not a JCAMP file.
            raise AnalyticsFailure(
                "ANALYTICS_MALFORMED_INPUT",
                "content before the first JCAMP label is not a JCAMP-DX export",
            )
    if data_class is None or not data_lines:
        raise AnalyticsFailure(
            "ANALYTICS_MALFORMED_INPUT", "no JCAMP data table (##XYDATA/##XYPOINTS) found"
        )

    table_kind = headers[data_class].upper().replace(" ", "")
    x_factor = _jfloat(headers, "XFACTOR", default=1.0)
    y_factor = _jfloat(headers, "YFACTOR", default=1.0)
    xs: list[float] = []
    ys: list[float] = []
    if "(X++(Y..Y))" in table_kind:
        _read_xyplusplus(data_lines, headers, x_factor, y_factor, xs, ys)
    elif "(X..Y)" in table_kind or "(XY..XY)" in table_kind:
        _read_xy_pairs(data_lines, x_factor, y_factor, xs, ys)
    else:
        raise AnalyticsFailure(
            "ANALYTICS_UNSUPPORTED_ENCODING",
            f"JCAMP table form '{headers[data_class]}' is not an AFFN table "
            "(only (X..Y), (XY..XY) and (X++(Y..Y)) are supported)",
        )
    npoints = _jfloat(headers, "NPOINTS", default=float(len(xs)))
    if int(npoints) != len(xs):
        raise AnalyticsFailure(
            "ANALYTICS_MALFORMED_INPUT",
            f"NPOINTS declares {int(npoints)} points; parsed {len(xs)}",
        )
    x_unit = (headers.get("XUNITS") or "").strip()
    y_unit = (headers.get("YUNITS") or "").strip()
    if not x_unit:
        raise AnalyticsFailure("ANALYTICS_MALFORMED_INPUT", "JCAMP export declares no ##XUNITS")
    metadata = {
        "title": headers.get("TITLE"),
        "data_class": data_class,
        "table_kind": headers[data_class],
        "jcamp_labels": {
            k: v for k, v in headers.items() if k in ("JCAMP-DX", "DATA TYPE", "ORIGIN", "OWNER")
        },
    }
    trace = _finalize(xs, ys, x_unit, y_unit or "arbitrary", warnings)
    return ParsedExport(
        format="jcamp-dx",
        parser_version=SUPPORTED_FORMATS["jcamp-dx"],
        trace=trace,
        metadata=metadata,
        warnings=tuple(warnings),
    )


def _jfloat(headers: dict[str, str], key: str, *, default: float) -> float:
    raw = headers.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as e:
        raise AnalyticsFailure(
            "ANALYTICS_MALFORMED_INPUT", f"JCAMP header ##{key}='{raw}' is not numeric"
        ) from e


def _data_tokens(line: str) -> list[str]:
    tokens = line.split()
    for tok in tokens:
        if _AFFN_COMPRESSED_TOKEN.search(tok.lstrip("+-")):
            raise AnalyticsFailure(
                "ANALYTICS_UNSUPPORTED_ENCODING",
                f"compressed JCAMP token '{tok}' — DIFDUP/SQUEEZED encodings "
                "are rejected, not guessed",
            )
    return tokens


def _read_xy_pairs(
    lines: list[str], x_factor: float, y_factor: float, xs: list[float], ys: list[float]
) -> None:
    for line in lines:
        tokens = _data_tokens(line)
        if len(tokens) % 2 != 0:
            raise AnalyticsFailure(
                "ANALYTICS_MALFORMED_INPUT",
                "(X..Y) row has an odd token count — x/y pairing is ambiguous",
            )
        for i in range(0, len(tokens), 2):
            xs.append(_to_float(tokens[i]) * x_factor)
            ys.append(_to_float(tokens[i + 1]) * y_factor)


def _read_xyplusplus(
    lines: list[str],
    headers: dict[str, str],
    x_factor: float,
    y_factor: float,
    xs: list[float],
    ys: list[float],
) -> None:
    """`(X++(Y..Y))`: each row starts with the x of its first y value,
    subsequent y values advance by ##DELTAX (or a computed increment)."""
    deltax = headers.get("DELTAX")
    if deltax is not None:
        try:
            step = float(deltax)
        except ValueError as e:
            raise AnalyticsFailure(
                "ANALYTICS_MALFORMED_INPUT", f"##DELTAX='{deltax}' is not numeric"
            ) from e
    else:
        firstx = _jfloat(headers, "FIRSTX", default=0.0)
        lastx = _jfloat(headers, "LASTX", default=0.0)
        npoints = _jfloat(headers, "NPOINTS", default=0.0)
        if npoints <= 1:
            raise AnalyticsFailure(
                "ANALYTICS_MALFORMED_INPUT",
                "(X++(Y..Y)) without ##DELTAX needs ##FIRSTX/##LASTX/##NPOINTS",
            )
        step = (lastx - firstx) / (npoints - 1)
    if step == 0:
        raise AnalyticsFailure("ANALYTICS_MALFORMED_INPUT", "x increment is zero")
    for line in lines:
        tokens = _data_tokens(line)
        if len(tokens) < 2:
            raise AnalyticsFailure("ANALYTICS_MALFORMED_INPUT", "(X++(Y..Y)) row has no y values")
        x0 = _to_float(tokens[0])
        for i, tok in enumerate(tokens[1:]):
            xs.append((x0 + i * step) * x_factor)
            ys.append(_to_float(tok) * y_factor)


# ------------------------------------------------------------------
# csv-xy
# ------------------------------------------------------------------


def _looks_like_csv_xy(text: str) -> bool:
    """Two consecutive rows of 'number<delim>number' make it a candidate;
    real parse errors still surface inside _parse_csv_xy."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    numeric = 0
    for line in lines[:400]:
        for delim in _DELIMITERS:
            parts = line.split(delim)
            if len(parts) >= 2 and _is_number(parts[0]) and _is_number(parts[1]):
                numeric += 1
                break
        if numeric >= 2:
            return True
    return False


def _is_number(token: str) -> bool:
    try:
        float(token.strip())
    except ValueError:
        return False
    return math.isfinite(float(token.strip()))


def _to_float(token: str) -> float:
    try:
        value = float(token)
    except ValueError as e:
        raise AnalyticsFailure(
            "ANALYTICS_MALFORMED_INPUT", f"non-numeric data token '{token}'"
        ) from e
    if not math.isfinite(value):
        raise AnalyticsFailure("ANALYTICS_MALFORMED_INPUT", f"non-finite data token '{token}'")
    return value


def _parse_csv_xy(text: str) -> ParsedExport:
    preamble: list[str] = []
    xs: list[float] = []
    ys: list[float] = []
    delimiter: str | None = None
    started = False
    for line in text.splitlines():
        if not line.strip():
            if started:
                break  # trailing blank ends the table
            continue
        candidates = [d for d in _DELIMITERS if line.count(d) >= 1]
        row: list[str] | None = None
        for d in candidates:
            parts = [p.strip() for p in line.split(d)]
            if len(parts) >= 2 and _is_number(parts[0]) and _is_number(parts[1]):
                row = parts
                if delimiter is None:
                    delimiter = d
                elif d != delimiter:
                    continue
                break
        if row is None:
            if started:
                raise AnalyticsFailure(
                    "ANALYTICS_MALFORMED_INPUT",
                    f"non-numeric row inside the data block: '{line.strip()[:60]}'",
                )
            preamble.append(line.strip())
            continue
        if delimiter is None:
            raise AnalyticsFailure(  # pragma: no cover - delimiter is set with first row
                "ANALYTICS_MALFORMED_INPUT", "no consistent delimiter found"
            )
        if len(row) != 2:
            raise AnalyticsFailure(
                "ANALYTICS_MALFORMED_INPUT",
                "csv-xy requires exactly two columns (x, y); extra columns are "
                "not silently selected",
            )
        xs.append(_to_float(row[0]))
        ys.append(_to_float(row[1]))
        started = True
        if len(xs) > _MAX_ROWS:
            raise AnalyticsFailure("ANALYTICS_MALFORMED_INPUT", "too many rows")
    if len(xs) < 2:
        raise AnalyticsFailure(
            "ANALYTICS_MALFORMED_INPUT", "csv-xy found fewer than two numeric rows"
        )
    warnings: list[str] = []
    # csv-xy carries no unit metadata: both axes are UNDECLARED until
    # the operator's ingest spec declares them (never a guess).
    trace = _finalize(xs, ys, UNDECLARED_UNIT, UNDECLARED_UNIT, warnings)
    return ParsedExport(
        format="csv-xy",
        parser_version=SUPPORTED_FORMATS["csv-xy"],
        trace=trace,
        metadata={"delimiter": delimiter, "preamble": preamble},
        warnings=tuple(warnings),
    )


# ------------------------------------------------------------------
# shared trace validation
# ------------------------------------------------------------------


def _finalize(
    xs: list[float], ys: list[float], x_unit: str, y_unit: str, warnings: list[str]
) -> SpectrumTrace:
    """Sort ascending, validate monotonicity/finiteness — a trace the
    rest of the pipeline can rely on."""
    if len(xs) != len(ys):
        raise AnalyticsFailure("ANALYTICS_MALFORMED_INPUT", "x/y length mismatch")
    pairs = sorted(zip(xs, ys, strict=True), key=lambda p: p[0])
    sx = [p[0] for p in pairs]
    sy = [p[1] for p in pairs]
    if xs != sx:
        warnings.append("x order normalized to ascending")
    for i in range(1, len(sx)):
        if not sx[i] > sx[i - 1]:
            raise AnalyticsFailure(
                "ANALYTICS_MALFORMED_INPUT",
                f"duplicate x value at index {i} — the trace is degenerate",
            )
    for v in sy:
        if not math.isfinite(v):
            raise AnalyticsFailure("ANALYTICS_MALFORMED_INPUT", "y contains a non-finite value")
    return SpectrumTrace(x=tuple(sx), y=tuple(sy), x_unit=x_unit, y_unit=y_unit)
