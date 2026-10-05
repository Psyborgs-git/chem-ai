"""Deterministic record → chunk indexing (§10).

Chunks carry the *exact* source locator and both the original and
normalized text — a chunk is evidence about where text came from,
never a rewrite that loses it. `chunking_version` is part of index
identity: rechunking under a new version creates new chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

CHUNKING_VERSION = "chunk-v1"
MAX_CHARS = 4_000

_WS_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase + whitespace-collapse — lexical retrieval normalizes
    for matching while ``original_text`` stays verbatim."""
    return _WS_RE.sub(" ", text).strip().lower()


@dataclass
class ChunkDraft:
    chunk_index: int
    record_index: int  # position in the input record list
    locator: dict[str, Any]
    original_text: str
    normalized_text: str


def chunk_records(records: list[dict[str, Any]]) -> list[ChunkDraft]:
    """One chunk per extracted record (records are already
    locator-scoped); oversized text is split with a slice marker so
    the locator still resolves to its source region."""
    out: list[ChunkDraft] = []
    idx = 0
    for rec_pos, rec in enumerate(records):
        text = rec.get("original_text") or ""
        locator = dict(rec.get("locator") or {})
        if not text.strip():
            continue
        if len(text) <= MAX_CHARS:
            out.append(
                ChunkDraft(
                    chunk_index=idx,
                    record_index=rec_pos,
                    locator=locator,
                    original_text=text,
                    normalized_text=normalize(text),
                )
            )
            idx += 1
            continue
        for start in range(0, len(text), MAX_CHARS):
            piece = text[start : start + MAX_CHARS]
            loc = {**locator, "slice": f"{start}:{start + len(piece)}"}
            out.append(
                ChunkDraft(
                    chunk_index=idx,
                    record_index=rec_pos,
                    locator=loc,
                    original_text=piece,
                    normalized_text=normalize(piece),
                )
            )
            idx += 1
    return out
