"""Value objects shared across the quarantine boundary — everything
here must be picklable (the runner crosses a subprocess)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PARSER_VERSION = "ingestion-1.0.0"

# Record kinds — what the parser proposed, not what was accepted.
RECORD_KINDS = frozenset({"cell", "row", "field", "line", "table", "document_meta"})


class QuarantineError(Exception):
    """Inspection refused the payload before parsing — a typed denial,
    not a parse failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ExtractedRecord:
    """One proposed extraction — a *candidate* record, not an accepted
    value (§9.2). Locators + original text are mandatory; flags carry
    every ambiguity the parser noticed."""

    kind: str
    locator: dict[str, Any]
    original_text: str
    value: dict[str, Any] | None = None
    flags: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class ParseReport:
    parser_name: str
    parser_version: str
    detected_type: str
    records: list[ExtractedRecord] = field(default_factory=list)
    # batch-level findings: active content, limits hit, ocr needed…
    findings: list[dict[str, str]] = field(default_factory=list)
    timed_out: bool = False
