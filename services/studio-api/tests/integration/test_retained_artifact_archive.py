"""Retained research copies preserve owner, original bytes and current rights."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from chem_studio_policy.capabilities import Grant, capabilities_for_role
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext
from studio.config.settings import Settings
from studio.domain.evidence.archive import ArchiveLimits
from studio.domain.evidence.service import ArtifactService
from studio.domain.evidence.vault import Vault
from studio.domain.library.artifacts import archive_artifact, authorize_retained_artifact
from studio.domain.library.service import LibraryService
from studio.errors import DomainError
from studio.persistence.models import Principal, Workspace

pytestmark = pytest.mark.integration


def test_artifact_copy_preserves_bytes_rights_and_live_revocation(
    session: Session, tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("STUDIO_RESEARCH_DOWNLOADS_ROOT", str(tmp_path / "downloads"))
    settings = Settings(vault_root=tmp_path / "vault")
    workspace = Workspace(slug="retained-artifacts", display_name="Retained sources")
    session.add(workspace)
    session.flush()
    principal = Principal(
        workspace_id=workspace.id, kind="user", login="reader", display_name="Reader"
    )
    session.add(principal)
    session.flush()
    ctx = ServiceContext(
        session=session,
        workspace_id=workspace.id,
        principal_id=principal.id,
        principal_kind="user",
        grants=frozenset(Grant(capability) for capability in capabilities_for_role("owner")),
    )
    vault = Vault(settings.vault_root)
    artifacts = ArtifactService(
        session, vault, max_bytes=1024 * 1024, archive_limits=ArchiveLimits()
    )
    body = b"Measured ethanol property record, with original units."
    artifact = artifacts.initiate(
        ctx,
        original_name="original-paper.txt",
        media_type="text/plain",
        declared_size=len(body),
        declared_checksum=None,
    )
    vault.append_bytes(vault.staging_path(workspace.id, artifact.id), body)
    artifact = artifacts.finish(ctx, artifact.id)
    artifact.review_state = "accepted"
    artifact.rights = {
        "retrieval": "allowed",
        "extraction": "allowed",
        "export": "denied",
        "training": "denied",
        "redistribution": "denied",
    }
    session.flush()
    copied = archive_artifact(session, ctx, settings, artifact.id)
    duplicate = archive_artifact(session, ctx, settings, artifact.id)
    assert copied["id"] == duplicate["id"]
    library = LibraryService(session, ctx, vault_root=settings.vault_root)
    original_path, _, _ = library.source_file(copied["id"], "original")
    assert original_path.read_bytes() == body
    copies = list((tmp_path / "downloads").rglob("metadata.json"))
    assert len(copies) == 1
    metadata = json.loads(copies[0].read_text())
    assert metadata["citation"]["artifactId"] == str(artifact.id)
    assert metadata["rights"]["export"] == "denied"
    with pytest.raises(DomainError):
        authorize_retained_artifact(session, ctx, copied["citation"], provider_bound=True)
    artifact.review_state = "revoked"
    session.flush()
    with pytest.raises(DomainError):
        library.get_source(copied["id"])
