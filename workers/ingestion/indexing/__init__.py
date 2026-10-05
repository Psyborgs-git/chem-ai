"""Source-chunk indexing (§10, CS-0303)."""

from workers.ingestion.indexing.chunker import ChunkDraft, chunk_records

__all__ = ["ChunkDraft", "chunk_records"]
