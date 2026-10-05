"""CS-0305 security tests — revocation closes cached exposure.

AT-0305-1  source cached, then revoked → new search returns nothing
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import load_context
from studio.domain.evidence.archive import ArchiveLimits
from studio.domain.evidence.imports import ImportService
from studio.domain.evidence.retrieval import RetrievalService
from studio.domain.evidence.revocation import RevocationService
from studio.domain.evidence.service import ArtifactService
from studio.domain.evidence.vault import Vault
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Principal,
    PrincipalCapability,
    RetrievalCache,
    Workspace,
)

pytestmark = pytest.mark.security


@pytest.fixture()
def env(session: Session, tmp_path: Path):
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    steward_p = Principal(workspace_id=ws.id, kind="user", login="ds", display_name="ds")
    session.add(steward_p)
    session.flush()
    for cap in sorted(capabilities_for_role("data_steward")):
        session.add(
            PrincipalCapability(workspace_id=ws.id, principal_id=steward_p.id, capability=cap)
        )
    agent_p = Principal(workspace_id=ws.id, kind="agent", login="bot", display_name="b")
    session.add(agent_p)
    session.flush()
    for cap in sorted(capabilities_for_role("agent")):
        session.add(
            PrincipalCapability(workspace_id=ws.id, principal_id=agent_p.id, capability=cap)
        )
    session.flush()
    vault = Vault(tmp_path)
    return {
        "ws": ws,
        "steward": load_context(session, ws.id, steward_p.id),
        "agent": load_context(session, ws.id, agent_p.id),
        "artifacts": ArtifactService(
            session, vault, max_bytes=64 * 1024 * 1024, archive_limits=ArchiveLimits()
        ),
        "importer": ImportService(session, vault, isolate=False),
        "retrieval": RetrievalService(session),
        "revocations": RevocationService(session, load_context(session, ws.id, steward_p.id)),
        "session": session,
    }


def _index(env: dict) -> uuid.UUID:
    ctx = env["steward"]
    data = b"component,amount\nresin_A,12\ncure_agent,3\n"
    artifact = env["artifacts"].initiate(
        ctx,
        original_name="recipe.csv",
        media_type="text/csv",
        declared_size=len(data),
        declared_checksum=None,
    )
    env["artifacts"].staging_path(ctx, artifact.id).write_bytes(data)
    artifact = env["artifacts"].finish(ctx, artifact.id)
    batch, _ = env["importer"].import_artifact(ctx, artifact.id)
    env["retrieval"].index_batch(ctx, batch.id)
    return artifact.id


class TestRevokedSourceNeverServed:
    """AT-0305-1: a cached+manifested search result is unreachable after
    revocation — the index version inside every cache key changes."""

    def test_cache_cannot_serve_revoked_source(self, env: dict) -> None:
        ctx = env["steward"]
        artifact_id = _index(env)
        hits1, _ = env["retrieval"].search(ctx, "resin_A")
        assert len(hits1) == 1
        # cache row exists for this exact scope/query/policy tuple
        assert env["session"].execute(select(RetrievalCache)).scalars().all()

        env["revocations"].revoke(ctx, artifact_id, reason="rights withdrawn")

        hits2, manifest2 = env["retrieval"].search(ctx, "resin_A")
        assert hits2 == []
        assert manifest2.chunk_ids == []
        # a different scope/principal can't reach it either
        hits3, _ = env["retrieval"].search(env["agent"], "resin_A")
        assert hits3 == []

    def test_agent_cannot_revoke(self, env: dict) -> None:
        artifact_id = _index(env)
        with pytest.raises(DomainError) as exc:
            RevocationService(env["session"], env["agent"]).revoke(
                env["agent"], artifact_id, reason="trying"
            )
        assert exc.value.code == ErrorCode.FORBIDDEN
