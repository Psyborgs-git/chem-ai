"""CS-0303 security tests — scoped retrieval + source rights.

AT-0303-1  hidden eval answers + derived chunks excluded in eval context
AT-0303-2  principals lacking source permission never see its chunks
AT-0303-3  lexical retrieval works; no embedding/cloud request occurs
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext, load_context
from studio.domain.evidence.archive import ArchiveLimits
from studio.domain.evidence.imports import ImportService
from studio.domain.evidence.retrieval import POLICY_VERSION, RetrievalService
from studio.domain.evidence.service import ArtifactService
from studio.domain.evidence.vault import Vault
from studio.persistence.models import (
    ImportBatch,
    Principal,
    PrincipalCapability,
    RetrievalManifest,
    Workspace,
)

pytestmark = pytest.mark.security


def _principal(session: Session, ws: Workspace, kind: str, role: str, login: str) -> Principal:
    p = Principal(workspace_id=ws.id, kind=kind, login=login, display_name=login)
    session.add(p)
    session.flush()
    for cap in sorted(capabilities_for_role(role)):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=p.id, capability=cap))
    session.flush()
    return p


@pytest.fixture()
def setup(session: Session, tmp_path: Path):
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    steward = _principal(session, ws, "user", "data_steward", "ds")
    agent = _principal(session, ws, "agent", "agent", "bot")
    vault = Vault(tmp_path)
    artifacts = ArtifactService(
        session, vault, max_bytes=64 * 1024 * 1024, archive_limits=ArchiveLimits()
    )
    importer = ImportService(session, vault, isolate=False)
    retrieval = RetrievalService(session)
    return {
        "ws": ws,
        "steward": load_context(session, ws.id, steward.id),
        "agent": load_context(session, ws.id, agent.id),
        "artifacts": artifacts,
        "importer": importer,
        "retrieval": retrieval,
        "session": session,
    }


def _indexed(
    s: dict,
    ctx: ServiceContext,
    text: str,
    *,
    name: str = "doc.csv",
    rights: dict | None = None,
    access_scope: uuid.UUID | None = None,
    retention: dict | None = None,
) -> str:
    data = text.encode()
    artifact = s["artifacts"].initiate(
        ctx,
        original_name=name,
        media_type="text/csv",
        declared_size=len(data),
        declared_checksum=None,
        access_scope=access_scope,
    )
    s["artifacts"].staging_path(ctx, artifact.id).write_bytes(data)
    artifact = s["artifacts"].finish(ctx, artifact.id)
    if rights:
        artifact.rights = {**artifact.rights, **rights}
    if retention:
        artifact.retention = {**(artifact.retention or {}), **retention}
    s["session"].flush()
    batch, _ = s["importer"].import_artifact(ctx, artifact.id)
    return str(batch.id)


class TestEvalContextExclusion:
    """AT-0303-1."""

    def test_hidden_eval_chunks_excluded_in_eval_context(self, setup: dict) -> None:
        s = setup
        ctx = s["steward"]
        batch_id = _indexed(
            s,
            ctx,
            "component,amount\nsecret_target,42\npublic_note,7\n",
            retention={"eval_restricted": True},
        )
        n = s["retrieval"].index_batch(ctx, uuid.UUID(batch_id))
        assert n > 0

        general, _ = s["retrieval"].search(ctx, "secret_target")
        assert len(general) > 0  # indexed and retrievable normally

        restricted, manifest = s["retrieval"].search(ctx, "secret_target", eval_context=True)
        assert restricted == []  # hidden in eval context
        assert manifest.eval_context is True
        assert manifest.chunk_ids == []


class TestScopedAclFiltering:
    """AT-0303-2."""

    def test_principal_without_scope_sees_nothing_scoped(self, setup: dict) -> None:
        s = setup
        ctx = s["steward"]
        restricted_scope = uuid.uuid4()
        other_scope = uuid.uuid4()
        batch_id = _indexed(
            s,
            ctx,
            "component,amount\nclassified_recipe,99\n",
            access_scope=restricted_scope,
        )
        s["retrieval"].index_batch(ctx, uuid.UUID(batch_id))

        # steward (workspace-wide read) sees it
        hits, _ = s["retrieval"].search(ctx, "classified_recipe")
        assert len(hits) == 1

        # a principal scoped to a *different* scope does not — filtered
        # before exposure even though FTS matched the text
        ws = s["ws"]
        session = s["session"]
        p = Principal(workspace_id=ws.id, kind="user", login="scoped", display_name="scoped")
        session.add(p)
        session.flush()
        session.add(
            PrincipalCapability(
                workspace_id=ws.id,
                principal_id=p.id,
                capability="read_project",
                scope_ref=other_scope,
            )
        )
        session.flush()
        scoped_ctx = load_context(session, ws.id, p.id)
        filtered, manifest2 = s["retrieval"].search(scoped_ctx, "classified_recipe")
        assert filtered == []
        assert manifest2.chunk_ids == []

    def test_retrieval_denied_source_is_recorded_not_indexed(self, setup: dict) -> None:
        s = setup
        ctx = s["steward"]
        batch_id = _indexed(
            s,
            ctx,
            "component,amount\nrestricted,5\n",
            rights={"retrieval": "denied"},
        )
        n = s["retrieval"].index_batch(ctx, uuid.UUID(batch_id))
        assert n == 0  # existence recorded, content not indexed
        hits, _ = s["retrieval"].search(ctx, "restricted")
        assert hits == []


class TestLexicalBaseline:
    """AT-0303-3."""

    def test_lexical_search_manifest_and_cache(self, setup: dict) -> None:
        s = setup
        ctx = s["steward"]
        batch_id = _indexed(s, ctx, "component,amount\nwater,50\nsolvent,40\n")
        s["retrieval"].index_batch(ctx, uuid.UUID(batch_id))

        hits, manifest = s["retrieval"].search(ctx, "water")
        assert len(hits) == 1
        assert manifest.query_kind == "lexical"  # no embedding path
        assert manifest.policy_version == POLICY_VERSION
        assert manifest.principal_id == ctx.principal_id
        assert (
            hits[0].locator.get("header") in ("amount", "component")
            or hits[0].locator.get("row") is not None
        )
        # second search is a manifest-recorded cache hit
        _hits2, manifest2 = s["retrieval"].search(ctx, "water")
        assert manifest2.cached is True
        assert manifest2.chunk_ids == manifest.chunk_ids

    def test_revocation_removes_chunks_and_invalidates(self, setup: dict) -> None:
        s = setup
        ctx = s["steward"]
        batch_id = _indexed(s, ctx, "component,amount\nrevocable,9\n")
        s["retrieval"].index_batch(ctx, uuid.UUID(batch_id))
        batch = s["session"].get(ImportBatch, uuid.UUID(batch_id))
        hits, _ = s["retrieval"].search(ctx, "revocable")
        assert len(hits) == 1

        n = s["retrieval"].revoke_artifact(ctx, batch.artifact_id)
        assert n == 2  # both cells of the revoked source leave the index
        hits2, _ = s["retrieval"].search(ctx, "revocable")
        assert hits2 == []  # revoked content can never be served

        manifests = s["session"].query(RetrievalManifest).all()
        assert len(manifests) >= 2  # every search left a manifest
