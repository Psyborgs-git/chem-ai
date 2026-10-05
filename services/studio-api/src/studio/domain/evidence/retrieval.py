"""Scoped, rights-aware lexical retrieval (§9.4, §10, CS-0303).

Lexical full-text search is the baseline — embeddings may join later
behind this same interface, only with an evaluated benefit (§10).
Every result passes through the same gate: workspace scope → source
rights → principal ACL → quality/eval context. A retrieval manifest
is recorded for every search; the cache key includes scope,
permissions, source-index version, and policy version, so revocation
or supersession can never serve stale exposure.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any, cast

from chem_studio_policy.capabilities import CAP_MANAGE_SOURCES, CAP_READ_PROJECT
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from workers.ingestion.indexing import chunk_records
from workers.ingestion.indexing.chunker import CHUNKING_VERSION

from studio.auth.context import ServiceContext
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import (
    Artifact,
    ImportBatch,
    RetrievalCache,
    RetrievalManifest,
    SourceChunk,
)

POLICY_VERSION = "retrieval-policy-1"


@dataclass
class SearchResult:
    chunk_id: str
    artifact_id: str
    locator: dict[str, Any]
    snippet: str
    score: float


class RetrievalService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------- indexing

    def index_batch(self, ctx: ServiceContext, batch_id: uuid.UUID) -> int:
        """Index a parsed batch's records as source chunks. An artifact
        whose retrieval right is denied is *recorded but not indexed*
        — its existence stays known without exposing content (§9.4)."""
        ctx.require(CAP_MANAGE_SOURCES)
        batch = self.db.execute(
            select(ImportBatch).where(
                ImportBatch.id == batch_id,
                ImportBatch.workspace_id == ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if batch is None:
            raise not_found("import batch")
        artifact = self.db.execute(
            select(Artifact).where(
                Artifact.id == batch.artifact_id,
                Artifact.workspace_id == ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if artifact is None:
            raise not_found("artifact")
        rights = artifact.rights or {}
        if rights.get("retrieval") == "denied":
            return 0
        # reindex under the same chunking version is idempotent
        existing = self.db.execute(
            select(func.count())
            .select_from(SourceChunk)
            .where(
                SourceChunk.workspace_id == ctx.workspace_id,
                SourceChunk.batch_id == batch.id,
                SourceChunk.chunking_version == CHUNKING_VERSION,
            )
        ).scalar_one()
        if existing:
            return 0
        from studio.persistence.models import ExtractedRecord

        rows = list(
            self.db.execute(
                select(ExtractedRecord).where(
                    ExtractedRecord.workspace_id == ctx.workspace_id,
                    ExtractedRecord.batch_id == batch.id,
                )
            ).scalars()
        )
        drafts = chunk_records(
            [{"original_text": r.original_text, "locator": r.locator} for r in rows]
        )
        eval_allowed = not (artifact.retention or {}).get("eval_restricted", False)
        for d in drafts:
            self.db.add(
                SourceChunk(
                    workspace_id=ctx.workspace_id,
                    artifact_id=artifact.id,
                    batch_id=batch.id,
                    record_id=rows[d.record_index].id,
                    chunk_index=d.chunk_index,
                    locator=d.locator,
                    original_text=d.original_text,
                    normalized_text=d.normalized_text,
                    extraction_method=batch.parser_name,
                    uncertainty=None,
                    chunking_version=CHUNKING_VERSION,
                    rights=rights,
                    acl_scope=artifact.access_scope,
                    eval_allowed=eval_allowed,
                )
            )
        self.db.flush()
        return len(drafts)

    # ------------------------------------------------------- search

    def _visible_scopes(self, ctx: ServiceContext) -> list[uuid.UUID] | None:
        """None = workspace-wide read grant; otherwise the explicit
        scope list the principal may read."""
        scopes: list[uuid.UUID] = []
        for g in ctx.grants:
            if g.capability != CAP_READ_PROJECT:
                continue
            if g.scope_ref is None:
                return None
            try:
                scopes.append(uuid.UUID(g.scope_ref))
            except ValueError:
                continue
        return scopes

    def _index_version(self, ctx: ServiceContext) -> str:
        count, latest = self.db.execute(
            select(func.count(), func.max(SourceChunk.updated_at)).where(
                SourceChunk.workspace_id == ctx.workspace_id,
                SourceChunk.status == "active",
            )
        ).one()
        return f"{count}:{latest.isoformat() if latest else 'none'}"

    def search(
        self,
        ctx: ServiceContext,
        query: str,
        *,
        eval_context: bool = False,
        limit: int = 20,
    ) -> tuple[list[SearchResult], RetrievalManifest]:
        """Lexical FTS through the rights/ACL/eval gate. Returns
        (results, manifest) — the manifest is always persisted."""
        # any read grant permits searching — scoped principals see only
        # their scopes (AT-0303-2); no grant at all → forbidden
        if not any(g.capability == CAP_READ_PROJECT for g in ctx.grants):
            raise DomainError(ErrorCode.FORBIDDEN, "capability 'read_project'")
        if not query.strip():
            raise DomainError(ErrorCode.VALIDATION, "query must not be empty")
        limit = max(1, min(limit, 50))
        scopes = self._visible_scopes(ctx)
        index_version = self._index_version(ctx)
        grants_hash = hashlib.sha256(
            "|".join(sorted(f"{g.capability}:{g.scope_ref}" for g in ctx.grants)).encode()
        ).hexdigest()[:16]
        cache_key = hashlib.sha256(
            f"{ctx.workspace_id}|{grants_hash}|{query}|{index_version}|"
            f"{POLICY_VERSION}|{eval_context}".encode()
        ).hexdigest()

        cached = self.db.execute(
            select(RetrievalCache).where(
                RetrievalCache.workspace_id == ctx.workspace_id,
                RetrievalCache.cache_key == cache_key,
            )
        ).scalar_one_or_none()
        if cached is not None:
            manifest = self._manifest(
                ctx,
                query,
                cache_key,
                index_version,
                eval_context,
                list(cached.chunk_ids),
                cached=True,
            )
            rows = self._fetch_chunks(ctx, [uuid.UUID(c) for c in cached.chunk_ids])
            return self._results(rows), manifest

        stmt = (
            select(
                SourceChunk,
                func.ts_rank(
                    func.to_tsvector("english", SourceChunk.normalized_text),
                    func.plainto_tsquery("english", query),
                ).label("rank"),
            )
            .where(
                SourceChunk.workspace_id == ctx.workspace_id,
                SourceChunk.status == "active",
                func.to_tsvector("english", SourceChunk.normalized_text).op("@@")(
                    func.plainto_tsquery("english", query)
                ),
            )
            .order_by(
                func.ts_rank(
                    func.to_tsvector("english", SourceChunk.normalized_text),
                    func.plainto_tsquery("english", query),
                ).desc()
            )
            .limit(limit * 4)  # ACL post-filter headroom
        )
        # rights gate: retrieval-denied chunks are invisible
        stmt = stmt.where(SourceChunk.rights["retrieval"].astext.is_distinct_from("denied"))
        if eval_context:
            # AT-0303-1: hidden eval answers and their derived chunks
            # are excluded from evaluation-context retrieval.
            stmt = stmt.where(SourceChunk.eval_allowed.is_(True))
        if scopes is not None:
            stmt = stmt.where(
                or_(
                    SourceChunk.acl_scope.is_(None),
                    SourceChunk.acl_scope.in_(scopes),
                )
            )
        query_rows = self.db.execute(stmt).all()
        # defense-in-depth: verify each row's scope in Python too —
        # an ACL bug must never leak a foreign chunk (AT-0303-2)
        results: list[tuple[SourceChunk, float]] = [
            (cast(SourceChunk, row[0]), float(cast(float, row[1])))
            for row in query_rows
            if cast(SourceChunk, row[0]).acl_scope is None
            or scopes is None
            or cast(SourceChunk, row[0]).acl_scope in scopes
        ][:limit]
        chunk_ids = [str(c.id) for c, _ in results]
        self.db.add(
            RetrievalCache(
                workspace_id=ctx.workspace_id,
                cache_key=cache_key,
                chunk_ids=chunk_ids,
            )
        )
        manifest = self._manifest(ctx, query, cache_key, index_version, eval_context, chunk_ids)
        return self._results([c for c, _ in results], [r for _, r in results]), manifest

    def _fetch_chunks(self, ctx: ServiceContext, ids: list[uuid.UUID]) -> list[SourceChunk]:
        if not ids:
            return []
        rows = self.db.execute(
            select(SourceChunk).where(
                SourceChunk.workspace_id == ctx.workspace_id,
                SourceChunk.id.in_(ids),
                SourceChunk.status == "active",
            )
        ).scalars()
        by_id = {str(r.id): r for r in rows}
        return [by_id[str(i)] for i in ids if str(i) in by_id]

    def _results(
        self,
        chunks: list[SourceChunk],
        scores: list[float] | None = None,
    ) -> list[SearchResult]:
        out = []
        for i, c in enumerate(chunks):
            out.append(
                SearchResult(
                    chunk_id=str(c.id),
                    artifact_id=str(c.artifact_id),
                    locator=c.locator,
                    snippet=c.original_text[:240],
                    score=scores[i] if scores else 0.0,
                )
            )
        return out

    def _manifest(
        self,
        ctx: ServiceContext,
        query: str,
        cache_key: str,
        index_version: str,
        eval_context: bool,
        chunk_ids: list[str],
        cached: bool = False,
    ) -> RetrievalManifest:
        manifest = RetrievalManifest(
            workspace_id=ctx.workspace_id,
            principal_id=ctx.principal_id,
            query=query,
            query_kind="lexical",
            cache_key=cache_key,
            source_index_version=index_version,
            policy_version=POLICY_VERSION,
            eval_context=eval_context,
            chunk_ids=chunk_ids,
            cached=cached,
        )
        self.db.add(manifest)
        self.db.flush()
        return manifest

    # ---------------------------------------------------- revocation

    def revoke_artifact(self, ctx: ServiceContext, artifact_id: uuid.UUID) -> int:
        """Source revocation (§9.4): all chunks from the artifact leave
        the index; the index version changes so caches can never serve
        the revoked content."""
        ctx.require(CAP_MANAGE_SOURCES)
        rows = self.db.execute(
            select(SourceChunk).where(
                SourceChunk.workspace_id == ctx.workspace_id,
                SourceChunk.artifact_id == artifact_id,
                SourceChunk.status == "active",
            )
        ).scalars()
        n = 0
        for c in rows:
            c.status = "revoked"
            n += 1
        self.db.flush()
        return n
