"""Quarantine limits (§9.1): size, decompression, members, pages,
cells, and a hard parse timeout. Exceeding any of them is a typed
denial, never a crash or a hang."""

from dataclasses import dataclass


@dataclass(frozen=True)
class IngestionLimits:
    max_input_bytes: int = 128 * 1024 * 1024
    max_decompressed_bytes: int = 256 * 1024 * 1024
    max_zip_members: int = 5_000
    max_compression_ratio: int = 200
    max_pages: int = 500
    max_cells: int = 500_000
    parse_timeout_s: float = 60.0


DEFAULT_LIMITS = IngestionLimits()
