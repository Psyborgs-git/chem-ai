"""Quarantined ingestion worker (§9, CS-0301).

Parsers run behind a subprocess boundary with hard limits — they
receive bytes only, never paths or network, and they never execute
macros, formulas, scripts, or hyperlinks.
"""

from workers.ingestion.runner import run_parse
from workers.ingestion.types import (
    ExtractedRecord,
    ParseReport,
    QuarantineError,
)

__all__ = ["ExtractedRecord", "ParseReport", "QuarantineError", "run_parse"]
