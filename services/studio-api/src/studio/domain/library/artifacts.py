"""Retain cited workspace artifacts as owner-private research sources.

Copies preserve their originating ACL, per-use rights and revision lineage.
The copy's existence never authorizes a use refused by the current source.
"""

from __future__ import annotations

import copy
import hashlib
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext
from studio.config.settings import Settings
from studio.domain.evidence.archive import ArchiveLimits
from studio.domain.evidence.service import ArtifactService
from studio.domain.evidence.vault import Vault
from studio.domain.library.research import MAX_DOWNLOAD_BYTES, Download
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import Artifact


def authorize_retained_artifact(
    db: Session,
    ctx: ServiceContext,
    citation: dict[str, Any],
    *,
    provider_bound: bool = False,
    _seen: set[uuid.UUID] | None = None,
) -> Artifact | None:
    """Recheck originating source when a retained copy is read or retrieved."""
    value = citation.get("artifactId")
    if not value:
        return None
    try:
        artifact_id = uuid.UUID(str(value))
    except ValueError:
        raise not_found("retained artifact") from None
    row = db.scalar(
        select(Artifact).where(
            Artifact.id == artifact_id,
            Artifact.workspace_id == ctx.workspace_id,
            Artifact.upload_state == "committed",
            Artifact.review_state.not_in(["revoked", "rejected", "superseded"]),
        )
    )
    if row is None or not ctx.has("read_project", row.access_scope):
        raise not_found("retained artifact")
    rights, retention = row.rights or {}, row.retention or {}
    if (
        rights.get("retrieval") == "denied"
        or retention.get("local_copy") == "denied"
        or retention.get("allow_local_copy") is False
    ):
        raise DomainError(
            ErrorCode.FORBIDDEN, "current source policy does not allow a retained copy"
        )
    if provider_bound and rights.get("export") != "allowed":
        raise DomainError(
            ErrorCode.FORBIDDEN, "current source rights do not allow provider transfer"
        )
    expected_checksum = citation.get("artifactChecksum")
    if expected_checksum and expected_checksum != row.checksum_sha256:
        raise DomainError(ErrorCode.CONFLICT, "retained artifact checksum changed")
    visited = _seen if _seen is not None else set()
    if row.id in visited:
        return row
    if len(visited) >= 100:
        raise DomainError(ErrorCode.FORBIDDEN, "artifact lineage is too large to verify")
    visited.add(row.id)
    for source_id in row.source_artifact_ids or []:
        authorize_retained_artifact(
            db, ctx, {"artifactId": str(source_id)}, provider_bound=provider_bound, _seen=visited
        )
    return row


def archive_artifact(
    db: Session, ctx: ServiceContext, settings: Settings, artifact_id: uuid.UUID | str
) -> dict[str, Any]:
    from studio.domain.library.service import LibraryService

    try:
        artifact_id = uuid.UUID(str(artifact_id))
    except ValueError:
        raise DomainError(ErrorCode.VALIDATION, "artifactId must be a UUID") from None
    row = authorize_retained_artifact(db, ctx, {"artifactId": str(artifact_id)})
    if row is None:
        raise not_found("artifact")
    service = ArtifactService(
        db,
        Vault(settings.vault_root),
        max_bytes=settings.artifact_max_bytes,
        archive_limits=ArchiveLimits(
            max_members=settings.artifact_max_archive_members,
            max_decompressed_bytes=settings.artifact_max_decompressed_bytes,
            max_compression_ratio=float(settings.artifact_max_compression_ratio),
        ),
    )
    row, stream = service.open_download(ctx, artifact_id)
    with stream:
        body = stream.read(MAX_DOWNLOAD_BYTES + 1)
    if len(body) > MAX_DOWNLOAD_BYTES:
        raise DomainError(
            ErrorCode.VALIDATION,
            (
                "cited artifact exceeds the 24 MiB research-copy limit; "
                "the original remains in its protected vault"
            ),
        )
    checksum = hashlib.sha256(body).hexdigest()
    if not row.checksum_sha256 or checksum != row.checksum_sha256:
        raise DomainError(
            ErrorCode.CONFLICT, "artifact checksum did not match its protected original"
        )
    citation = {
        "artifactId": str(row.id),
        "artifactRevision": row.version,
        "artifactChecksum": checksum,
        "rights": copy.deepcopy(row.rights or {}),
        "retention": copy.deepcopy(row.retention or {}),
        "sourceArtifactIds": copy.deepcopy(row.source_artifact_ids or []),
        "sourceKind": "workspace_artifact",
    }
    return LibraryService(db, ctx, vault_root=settings.vault_root).archive_download(
        Download(url=f"artifact:{row.id}", media_type=row.media_type, body=body),
        title=row.original_name,
        citation=citation,
        original_name=row.original_name,
        url_hash=hashlib.sha256(f"artifact:{row.id}:{checksum}".encode()).hexdigest(),
        requested_url=f"artifact:{row.id}",
    )


def archive_cited_artifacts(
    db: Session, ctx: ServiceContext, settings: Settings, artifact_ids: list[str]
) -> dict[str, Any]:
    """Bounded archive hook for sources whose snippets were actually returned."""
    unique = list(dict.fromkeys(artifact_ids))
    archived, omissions = [], []
    for artifact_id in unique[:20]:
        try:
            with db.begin_nested():
                result = archive_artifact(db, ctx, settings, artifact_id)
            archived.append(
                {
                    "artifactId": artifact_id,
                    "sourceId": result["id"],
                    "archiveStatus": result.get("archiveStatus"),
                }
            )
        except DomainError as exc:
            omissions.append({"artifactId": artifact_id, "reason": exc.message})
        except OSError:
            omissions.append(
                {
                    "artifactId": artifact_id,
                    "reason": (
                        "Research copy could not be saved; "
                        "the original remains in its protected vault."
                    ),
                }
            )
    if len(unique) > 20:
        omissions.append({"reason": "Research-copy batch limited to 20 cited artifacts"})
    return {"sources": archived, "omissions": omissions}
