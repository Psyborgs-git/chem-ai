"""Format parsers (§9.1). Every parser is a pure bytes → records
function: no filesystem, no network, no evaluation of anything the
document contains — formulas are *source text*, never executed."""

from __future__ import annotations

import csv as csv_mod
import io
import json as json_mod
import re
from collections.abc import Callable
from typing import Any

from workers.ingestion.limits import IngestionLimits
from workers.ingestion.types import (
    PARSER_VERSION,
    ExtractedRecord,
    ParseReport,
    QuarantineError,
)

PARSER_NAMES = {
    "csv": "csv-stdlib",
    "json": "json-stdlib",
    "text": "text-stdlib",
    "markdown": "markdown-stdlib",
    "xlsx": "openpyxl",
    "docx": "python-docx",
    "pdf": "pypdf",
}

_PERCENT_RE = re.compile(r"%\s*$")
_DECIMAL_COMMA_RE = re.compile(r"^-?\d+,\d+$")
_UNIT_HINT_RE = re.compile(
    r"\b(kg|g|mg|mL|L|mol|mmol|Pa\.?s|MPa|%|wt%|mol%|degC|°C|ppm)\b", re.IGNORECASE
)


def _numeric(text: str) -> bool:
    try:
        float(text.replace(",", "."))
        return True
    except ValueError:
        return False


# ------------------------------------------------------------------
# text-family parsers


def parse_csv(data: bytes, limits: IngestionLimits) -> ParseReport:
    text = data.decode("utf-8-sig", errors="replace")
    rows = list(csv_mod.reader(io.StringIO(text)))
    records: list[ExtractedRecord] = []
    header = rows[0] if rows else []
    for r, row in enumerate(rows[1:], start=1):
        for c, cell in enumerate(row):
            raw = cell.strip()
            if not raw:
                continue
            flags: list[str] = []
            if _PERCENT_RE.search(raw):
                # '5%' is a literal string — never mass_fraction 5
                flags.append("percent_literal_ambiguous")
            if _DECIMAL_COMMA_RE.match(raw):
                flags.append("decimal_separator_ambiguous")
            if _numeric(raw) and not _UNIT_HINT_RE.search(header[c] if c < len(header) else ""):
                flags.append("unit_unresolved")
            records.append(
                ExtractedRecord(
                    kind="cell",
                    locator={
                        "row": r,
                        "col": c,
                        "header": header[c] if c < len(header) else None,
                    },
                    original_text=raw,
                    value={"text": raw},
                    flags=flags,
                    confidence=0.6,
                )
            )
    return ParseReport(
        parser_name=PARSER_NAMES["csv"],
        parser_version=PARSER_VERSION,
        detected_type="csv",
        records=records,
    )


def parse_json(data: bytes, limits: IngestionLimits) -> ParseReport:
    try:
        doc = json_mod.loads(data.decode("utf-8"))
    except (json_mod.JSONDecodeError, UnicodeDecodeError) as exc:
        raise QuarantineError("MALFORMED", f"JSON not parseable: {exc}") from exc
    records: list[ExtractedRecord] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        else:
            raw = json_mod.dumps(node)
            flags: list[str] = []
            if isinstance(node, str) and _PERCENT_RE.search(node.strip()):
                flags.append("percent_literal_ambiguous")
            if isinstance(node, (int, float)):
                flags.append("unit_unresolved")
            records.append(
                ExtractedRecord(
                    kind="field",
                    locator={"jsonpath": path or "$"},
                    original_text=raw,
                    value={"json": node},
                    flags=flags,
                    confidence=0.7,
                )
            )

    walk(doc, "")
    return ParseReport(
        parser_name=PARSER_NAMES["json"],
        parser_version=PARSER_VERSION,
        detected_type="json",
        records=records,
    )


def parse_text(data: bytes, limits: IngestionLimits) -> ParseReport:
    text = data.decode("utf-8", errors="replace")
    records = [
        ExtractedRecord(
            kind="line",
            locator={"line": i + 1},
            original_text=line,
            value={"text": line},
            confidence=0.8,
        )
        for i, line in enumerate(text.splitlines())
        if line.strip()
    ]
    return ParseReport(
        parser_name=PARSER_NAMES["text"],
        parser_version=PARSER_VERSION,
        detected_type="text",
        records=records,
    )


# ------------------------------------------------------------------
# office formats


def parse_xlsx(data: bytes, limits: IngestionLimits) -> ParseReport:
    """Workbook cells with sheet/cell locators (§9.1).

    - formulas are *untrusted expressions*: read the cached result
      where present; a formula with no cache is flagged
      ``missing_cached_value`` and never evaluated (AT-0301-1).
    - percent-formatted cells keep their literal text + flag —
      '5%' never becomes mass fraction 5.
    - merged ranges are recorded on each member's locator.
    """
    from openpyxl import load_workbook

    cached = load_workbook(io.BytesIO(data), data_only=True, read_only=False)
    formulas = load_workbook(io.BytesIO(data), data_only=False, read_only=False)
    records: list[ExtractedRecord] = []
    findings: list[dict[str, str]] = []
    cell_count = 0
    for sheet_name in formulas.sheetnames:
        fsheet = formulas[sheet_name]
        csheet = cached[sheet_name]
        merged = [str(r) for r in fsheet.merged_cells.ranges]
        for row in fsheet.iter_rows():
            for cell in row:
                if cell.value is None:
                    continue
                cell_count += 1
                if cell_count > limits.max_cells:
                    findings.append({"code": "CELL_LIMIT", "detail": "stopped at max_cells"})
                    return ParseReport(
                        parser_name=PARSER_NAMES["xlsx"],
                        parser_version=PARSER_VERSION,
                        detected_type="xlsx",
                        records=records,
                        findings=findings,
                    )
                locator: dict[str, Any] = {
                    "sheet": sheet_name,
                    "cell": cell.coordinate,
                }
                if merged:
                    locator["merged_ranges"] = merged
                flags: list[str] = []
                original = cell.value
                value: dict[str, Any] | None = None
                if cell.data_type == "f" or (
                    isinstance(original, str) and original.startswith("=")
                ):
                    cached_val = csheet[cell.coordinate].value
                    if cached_val is None:
                        # no trustworthy cache — the formula is text only
                        flags.append("missing_cached_value")
                        flags.append("untrusted_formula")
                    else:
                        value = {"cached": cached_val}
                        flags.append("cached_formula_result")
                elif isinstance(original, float) or isinstance(original, int):
                    value = {"number": original}
                    fmt = cell.number_format or ""
                    if "%" in fmt:
                        flags.append("percent_format_ambiguous")
                    if not _UNIT_HINT_RE.search(fmt):
                        flags.append("unit_unresolved")
                else:
                    value = {"text": str(original)}
                    if isinstance(original, str) and _PERCENT_RE.search(original.strip()):
                        flags.append("percent_literal_ambiguous")
                if cell.data_type == "d" or (cell.is_date if hasattr(cell, "is_date") else False):
                    flags.append("locale_date_ambiguous")
                records.append(
                    ExtractedRecord(
                        kind="cell",
                        locator=locator,
                        original_text=str(original),
                        value=value,
                        flags=flags,
                        confidence=0.7 if "missing_cached_value" not in flags else 0.3,
                    )
                )
    return ParseReport(
        parser_name=PARSER_NAMES["xlsx"],
        parser_version=PARSER_VERSION,
        detected_type="xlsx",
        records=records,
        findings=findings,
    )


def parse_docx(data: bytes, limits: IngestionLimits) -> ParseReport:
    from docx import Document

    doc = Document(io.BytesIO(data))
    records: list[ExtractedRecord] = []
    for i, para in enumerate(doc.paragraphs):
        if not para.text.strip():
            continue
        records.append(
            ExtractedRecord(
                kind="line",
                locator={
                    "paragraph": i,
                    "style": para.style.name if para.style is not None else None,
                },
                original_text=para.text,
                value={"text": para.text},
                confidence=0.8,
            )
        )
    for t_i, table in enumerate(doc.tables):
        for r_i, row in enumerate(table.rows):
            for c_i, cell in enumerate(row.cells):
                text = cell.text.strip()
                if not text:
                    continue
                records.append(
                    ExtractedRecord(
                        kind="cell",
                        locator={"table": t_i, "row": r_i, "col": c_i},
                        original_text=text,
                        value={"text": text},
                        confidence=0.7,
                    )
                )
    return ParseReport(
        parser_name=PARSER_NAMES["docx"],
        parser_version=PARSER_VERSION,
        detected_type="docx",
        records=records,
    )


def parse_pdf(data: bytes, limits: IngestionLimits) -> ParseReport:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if len(reader.pages) > limits.max_pages:
        raise QuarantineError(
            "PAGE_LIMIT",
            f"{len(reader.pages)} pages exceeds the {limits.max_pages} limit",
        )
    records: list[ExtractedRecord] = []
    findings: list[dict[str, str]] = []
    any_text = False
    for i, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if text:
            any_text = True
            records.append(
                ExtractedRecord(
                    kind="line",
                    locator={"page": i + 1},
                    original_text=text[:4000],
                    value={"text": text[:4000]},
                    confidence=0.7,
                )
            )
        else:
            findings.append(
                {
                    "code": "NO_TEXT_LAYER",
                    "detail": f"page {i + 1} has no extractable text — "
                    "scanned content requires a separately enabled OCR "
                    "path and review",
                }
            )
    if not any_text:
        findings.append(
            {
                "code": "REQUIRES_OCR_REVIEW",
                "detail": "no text layer — do not claim extraction confidence for scanned pages",
            }
        )
    return ParseReport(
        parser_name=PARSER_NAMES["pdf"],
        parser_version=PARSER_VERSION,
        detected_type="pdf",
        records=records,
        findings=findings,
    )


PARSERS: dict[str, Callable[[bytes, IngestionLimits], ParseReport]] = {
    "csv": parse_csv,
    "json": parse_json,
    "text": parse_text,
    "markdown": parse_text,
    "xlsx": parse_xlsx,
    "docx": parse_docx,
    "pdf": parse_pdf,
}
