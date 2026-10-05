"""Artifact application service (CS-0103, §8.1, §9.1).

Every operation runs inside a ``ServiceContext``; authorization is
checked here, not in the route. Upload protocol:

    initiate  → artifact row (upload_state='receiving') + staging file
    PUT bytes → appended to staging, size-capped mid-stream
    finish    → checksum verify → archive safety → atomic commit
    abort     → discard staging

``finish`` is idempotent: retrying a completed upload returns the same
committed artifact instead of duplicating bytes (AT-0103-2).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from chem_studio_policy.capabilities import CAP_MANAGE_SOURCES, CAP_READ_PROJECT
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext
from studio.domain.evidence.archive import ArchiveLimits, check_archive
from studio.domain.evidence.vault import Vault, sha256_file
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import Artifact

PENDING_KEY_PREFIX = "pending/"


class ArtifactService:
    def __init__(
        self,
        db: Session,
        vault: Vault,
        *,
        max_bytes: int,
        archive_limits: ArchiveLimits,
    ) -> None:
        self.db = db
        self.vault = vault
        self.max_bytes = max_bytes
        self.archive_limits = archive_limits

    # ------------------------------------------------------- lookups

    def get(self, ctx: ServiceContext, artifact_id: uuid.UUID) -> Artifact:
        row = self.db.execute(
            select(Artifact).where(
                Artifact.id == artifact_id,
                Artifact.workspace_id == ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            # Uniform not-found: no existence leak across scopes.
            raise not_found("artifact")
        return row

    # ------------------------------------------------------- upload

    def initiate(
        self,
        ctx: ServiceContext,
        *,
        original_name: str,
        media_type: str,
        declared_size: int | None,
        declared_checksum: str | None,
        access_scope: uuid.UUID | None = None,
    ) -> Artifact:
        ctx.require(CAP_MANAGE_SOURCES, access_scope)
        if not original_name.strip():
            raise DomainError(ErrorCode.VALIDATION, "original name required")
        if declared_size is not None and declared_size > self.max_bytes:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"declared size exceeds the {self.max_bytes}-byte limit",
            )
        if declared_checksum is not None and len(declared_checksum) != 64:
            raise DomainError(ErrorCode.VALIDATION, "checksum must be sha256 hex")
        artifact = Artifact(
            workspace_id=ctx.workspace_id,
            storage_key="",  # replaced below with the pending key
            media_type=media_type,
            original_name=original_name,
            declared_checksum=declared_checksum,
            access_scope=access_scope,
            created_by=ctx.principal_id,
        )
        self.db.add(artifact)
        self.db.flush()
        artifact.storage_key = f"{PENDING_KEY_PREFIX}{artifact.id}"
        self.db.flush()
        self.vault.begin_staging(ctx.workspace_id, artifact.id)
        return artifact

    def staging_path(self, ctx: ServiceContext, artifact_id: uuid.UUID) -> Path:
        """Path the transport layer appends to. Keeps vault layout out of
        the route while still streaming to disk (not memory)."""
        artifact = self.get(ctx, artifact_id)
        if artifact.upload_state != "receiving":
            raise DomainError(ErrorCode.CONFLICT, f"upload is {artifact.upload_state}")
        return self.vault.staging_path(ctx.workspace_id, artifact.id)

    def check_size_budget(self, current: int, incoming: int) -> None:
        if current + incoming > self.max_bytes:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"upload exceeds the {self.max_bytes}-byte limit",
            )

    def finish(
        self,
        ctx: ServiceContext,
        artifact_id: uuid.UUID,
        *,
        checksum: str | None = None,
    ) -> Artifact:
        ctx.require(CAP_MANAGE_SOURCES)
        artifact = self.get(ctx, artifact_id)

        if artifact.upload_state == "committed":
            # AT-0103-2: retried completion returns the same artifact.
            expected = checksum or artifact.declared_checksum
            if expected and expected != artifact.checksum_sha256:
                raise DomainError(
                    ErrorCode.CONFLICT,
                    "committed checksum differs from the retried one",
                )
            return artifact
        if artifact.upload_state != "receiving":
            raise DomainError(ErrorCode.CONFLICT, f"upload is {artifact.upload_state}")

        staging = self.vault.staging_path(ctx.workspace_id, artifact.id)
        if not staging.exists():
            raise DomainError(ErrorCode.VALIDATION, "no bytes uploaded")
        actual, size = sha256_file(staging)
        expected = checksum or artifact.declared_checksum
        if expected and expected != actual:
            self.vault.discard_staging(ctx.workspace_id, artifact.id)
            artifact.upload_state = "aborted"
            self.db.flush()
            raise DomainError(
                ErrorCode.VALIDATION,
                "uploaded bytes do not match the declared checksum",
            )
        if size == 0:
            raise DomainError(ErrorCode.VALIDATION, "no bytes uploaded")

        # Archive member safety happens in staging — an unsafe payload
        # is rejected before a single byte enters the vault (AT-0103-1).
        try:
            check_archive(staging, artifact.media_type, self.archive_limits)
        except DomainError:
            self.vault.discard_staging(ctx.workspace_id, artifact.id)
            artifact.upload_state = "aborted"
            artifact.review_state = "rejected"
            self.db.flush()
            raise

        key, byte_size = self.vault.commit(ctx.workspace_id, artifact.id, actual)
        artifact.storage_key = key
        artifact.checksum_sha256 = actual
        artifact.byte_size = byte_size
        artifact.upload_state = "committed"
        artifact.committed_at = datetime.now(UTC)
        self.db.flush()
        return artifact

    def abort(self, ctx: ServiceContext, artifact_id: uuid.UUID) -> Artifact:
        ctx.require(CAP_MANAGE_SOURCES)
        artifact = self.get(ctx, artifact_id)
        if artifact.upload_state == "receiving":
            artifact.upload_state = "aborted"
            self.vault.discard_staging(ctx.workspace_id, artifact.id)
            self.db.flush()
        return artifact

    # ----------------------------------------------------- download

    def open_download(
        self, ctx: ServiceContext, artifact_id: uuid.UUID
    ) -> tuple[Artifact, BinaryIO]:
        """Authorized byte stream. No filesystem path crosses the
        boundary — the caller gets (record, fileobj) only (AT-0103-3)."""
        artifact = self.get(ctx, artifact_id)
        ctx.require(CAP_READ_PROJECT, artifact.access_scope)
        if artifact.upload_state != "committed":
            # Quarantined/aborted bytes are not downloadable content.
            raise not_found("artifact content")
        blob = self.vault.open_blob(ctx.workspace_id, artifact.storage_key)
        return artifact, blob
