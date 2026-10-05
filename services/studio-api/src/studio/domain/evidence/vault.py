"""Filesystem vault mechanics (CS-0103, §5.2, §21.3).

Layout::

    <root>/blobs/<workspace>/<checksum[:2]>/<checksum>/<artifact-id>
    <root>/.staging/<workspace>/<artifact-id>.part

- Storage keys are opaque and workspace-relative; nothing outside the
  vault root is ever served to a client.
- Commit is an atomic ``os.replace`` after fsync — a crash mid-upload
  can only leave a staging file, never a half blob.
- ``resolve_inside`` is the single containment gate: any path that
  escapes the vault raises instead of resolving.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from studio.errors import DomainError, ErrorCode

_CHUNK = 1024 * 1024
STAGING_DIR = ".staging"
BLOB_DIR = "blobs"


def sha256_file(path: Path) -> tuple[str, int]:
    """Streaming digest; returns (hex, byte_count)."""
    h = hashlib.sha256()
    n = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


class Vault:
    """One private artifact vault rooted at an absolute path."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()

    @property
    def root(self) -> Path:
        return self._root

    # ------------------------------------------------------ containment

    def resolve_inside(self, rel: str | Path) -> Path:
        """Resolve a vault-relative path, refusing escapes (AT-0103-3)."""
        p = (self._root / rel).resolve()
        if p != self._root and self._root not in p.parents:
            raise DomainError(ErrorCode.VALIDATION, "path escapes vault root")
        return p

    def _check_key(self, storage_key: str) -> None:
        if (
            not storage_key
            or storage_key.startswith(("/", "\\"))
            or "\x00" in storage_key
            or any(part in ("", ".", "..") for part in storage_key.split("/"))
        ):
            raise DomainError(ErrorCode.VALIDATION, "invalid storage key")

    # --------------------------------------------------------- paths

    def staging_path(self, workspace_id: uuid.UUID, artifact_id: uuid.UUID) -> Path:
        return self.resolve_inside(Path(STAGING_DIR) / str(workspace_id) / f"{artifact_id}.part")

    def blob_path(self, workspace_id: uuid.UUID, storage_key: str) -> Path:
        self._check_key(storage_key)
        return self.resolve_inside(Path(BLOB_DIR) / str(workspace_id) / storage_key)

    @staticmethod
    def storage_key_for(checksum: str, artifact_id: uuid.UUID) -> str:
        """Content-addressed, artifact-unique key (dedup stays possible
        via the checksum directory; ownership stays exclusive)."""
        return f"{checksum[:2]}/{checksum}/{artifact_id}"

    # -------------------------------------------------------- lifecycle

    def begin_staging(self, workspace_id: uuid.UUID, artifact_id: uuid.UUID) -> Path:
        path = self.staging_path(workspace_id, artifact_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def append_bytes(self, staging: Path, data: bytes) -> None:
        with staging.open("ab") as f:
            f.write(data)

    def staging_size(self, staging: Path) -> int:
        return staging.stat().st_size if staging.exists() else 0

    def commit(
        self, workspace_id: uuid.UUID, artifact_id: uuid.UUID, checksum: str
    ) -> tuple[str, int]:
        """Atomically move staging → content-addressed blob.

        Returns (storage_key, byte_size). If a blob for this artifact
        already exists the retried commit replaces it only with identical
        bytes — the checksum is identical by definition.
        """
        staging = self.staging_path(workspace_id, artifact_id)
        actual, size = sha256_file(staging)
        if actual != checksum:
            raise DomainError(
                ErrorCode.VALIDATION,
                "uploaded bytes do not match the recorded checksum",
            )
        key = self.storage_key_for(actual, artifact_id)
        dest = self.blob_path(workspace_id, key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # fsync staging before the atomic rename so a crash cannot leave
        # a committed-but-empty blob.
        with staging.open("rb") as f:
            os.fsync(f.fileno())
        os.replace(staging, dest)
        dir_fd = os.open(dest.parent, os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        return key, size

    def open_blob(self, workspace_id: uuid.UUID, storage_key: str) -> BinaryIO:
        self._check_key(storage_key)
        path = self.blob_path(workspace_id, storage_key)
        if not path.is_file():
            raise DomainError(ErrorCode.NOT_FOUND, "artifact content unavailable")
        return path.open("rb")

    def blob_exists(self, workspace_id: uuid.UUID, storage_key: str) -> bool:
        self._check_key(storage_key)
        return self.blob_path(workspace_id, storage_key).is_file()

    # --------------------------------------------------------- cleanup

    def discard_staging(self, workspace_id: uuid.UUID, artifact_id: uuid.UUID) -> None:
        staging = self.staging_path(workspace_id, artifact_id)
        staging.unlink(missing_ok=True)

    def remove_blob(self, workspace_id: uuid.UUID, storage_key: str) -> None:
        self.blob_path(workspace_id, storage_key).unlink(missing_ok=True)

    def stale_staging(self, ttl_seconds: int) -> Iterator[Path]:
        """Yield staging files older than TTL for staged cleanup.

        Committed blobs are never listed — cleanup cannot orphan
        committed records.
        """
        root = self._root / STAGING_DIR
        if not root.is_dir():
            return
        cutoff = time.time() - ttl_seconds
        for path in root.rglob("*.part"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                yield path

    def iter_blobs(self, workspace_id: uuid.UUID) -> Iterator[Path]:
        ws_root = self._root / BLOB_DIR / str(workspace_id)
        if not ws_root.is_dir():
            return
        yield from ws_root.rglob("*")

    def verify_blob(self, workspace_id: uuid.UUID, storage_key: str) -> bool:
        """Re-hash a committed blob; used by restore/verification paths."""
        try:
            path = self.blob_path(workspace_id, storage_key)
        except DomainError:
            return False
        if not path.is_file():
            return False
        digest, _ = sha256_file(path)
        # The checksum is embedded in the key: <aa>/<sha256>/<id>.
        parts = storage_key.split("/")
        return len(parts) == 3 and digest == parts[1]

    def delete_workspace_tree(self, workspace_id: uuid.UUID) -> None:
        """Full workspace purge — retention lifecycle only, never called
        from request paths."""
        for sub in (BLOB_DIR, STAGING_DIR):
            shutil.rmtree(self._root / sub / str(workspace_id), ignore_errors=True)
