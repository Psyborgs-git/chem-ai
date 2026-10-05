"""Unit tests — vault mechanics & archive member safety (no DB)."""

from __future__ import annotations

import io
import os
import tarfile
import time
import uuid
import zipfile
from pathlib import Path

import pytest

from studio.domain.evidence.archive import (
    ArchiveLimits,
    check_archive,
    unsafe_member_reason,
)
from studio.domain.evidence.vault import Vault, sha256_file
from studio.errors import DomainError, ErrorCode

WS = uuid.uuid4()
AID = uuid.uuid4()


def _tar_bytes(members: list[tuple[tarfile.TarInfo, bytes | None]]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for info, data in members:
            if data is None:
                tf.addfile(info)
            else:
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _zip_bytes(members: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            zf.writestr(name, data)
    return buf.getvalue()


class TestMemberNames:
    @pytest.mark.parametrize(
        "name",
        ["../evil.txt", "a/../../b", "/etc/passwd", "C:/win/x", "a//b", "a/./b", "\x00bad"],
    )
    def test_unsafe_names(self, name: str) -> None:
        assert unsafe_member_reason(name) is not None

    @pytest.mark.parametrize(
        "name",
        ["docs/readme.md", "dir/", "a.tar.gz", "深 ファイル.csv", "file name.txt"],
    )
    def test_safe_names(self, name: str) -> None:
        assert unsafe_member_reason(name) is None


class TestArchiveChecks:
    def test_traversal_tar_rejected(self, tmp_path: Path) -> None:
        info = tarfile.TarInfo("../evil.txt")
        payload = _tar_bytes([(info, b"x")])
        f = tmp_path / "a.tar"
        f.write_bytes(payload)
        with pytest.raises(DomainError) as exc:
            check_archive(f, "application/x-tar", ArchiveLimits())
        assert exc.value.code == ErrorCode.VALIDATION

    def test_symlink_tar_rejected(self, tmp_path: Path) -> None:
        info = tarfile.TarInfo("link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        f = tmp_path / "a.tar"
        f.write_bytes(_tar_bytes([(info, None)]))
        with pytest.raises(DomainError):
            check_archive(f, "application/x-tar", ArchiveLimits())

    def test_traversal_zip_rejected(self, tmp_path: Path) -> None:
        f = tmp_path / "a.zip"
        f.write_bytes(_zip_bytes([("../../etc/evil", b"x")]))
        with pytest.raises(DomainError):
            check_archive(f, "application/zip", ArchiveLimits())

    def test_symlink_zip_rejected(self, tmp_path: Path) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zi = zipfile.ZipInfo("link")
            zi.create_system = 3  # unix
            zi.external_attr = 0o120777 << 16  # S_IFLNK
            zf.writestr(zi, "/etc/passwd")
        f = tmp_path / "a.zip"
        f.write_bytes(buf.getvalue())
        with pytest.raises(DomainError):
            check_archive(f, "application/zip", ArchiveLimits())

    def test_clean_zip_accepted(self, tmp_path: Path) -> None:
        f = tmp_path / "a.zip"
        f.write_bytes(_zip_bytes([("dir/", b""), ("dir/a.txt", b"hello")]))
        check_archive(f, "application/zip", ArchiveLimits())

    def test_renamed_archive_still_checked(self, tmp_path: Path) -> None:
        # Declared text/plain but content is a zip → detection by magic.
        f = tmp_path / "notes.txt"
        f.write_bytes(_zip_bytes([("../x", b"boom")]))
        with pytest.raises(DomainError):
            check_archive(f, "text/plain", ArchiveLimits())

    def test_plain_text_is_not_an_archive(self, tmp_path: Path) -> None:
        f = tmp_path / "a.txt"
        f.write_bytes(b"just text")
        check_archive(f, "text/plain", ArchiveLimits())

    def test_member_count_limit(self, tmp_path: Path) -> None:
        f = tmp_path / "a.zip"
        f.write_bytes(_zip_bytes([(f"f{i}.txt", b"x") for i in range(20)]))
        with pytest.raises(DomainError):
            check_archive(f, "application/zip", ArchiveLimits(max_members=10))


class TestVault:
    def test_resolve_inside_blocks_escape(self, tmp_path: Path) -> None:
        v = Vault(tmp_path)
        with pytest.raises(DomainError):
            v.resolve_inside("../outside")
        with pytest.raises(DomainError):
            v.resolve_inside("/etc/passwd")

    def test_bad_storage_keys_rejected(self, tmp_path: Path) -> None:
        v = Vault(tmp_path)
        for key in ("", "/abs", "..", "a/../b", "a//b"):
            with pytest.raises(DomainError):
                v.blob_path(WS, key)

    def test_commit_roundtrip_and_verify(self, tmp_path: Path) -> None:
        v = Vault(tmp_path)
        staging = v.begin_staging(WS, AID)
        v.append_bytes(staging, b"hello vault")
        digest, size = sha256_file(staging)
        key, committed = v.commit(WS, AID, digest)
        assert committed == size == 11
        assert not staging.exists()
        with v.open_blob(WS, key) as f:
            assert f.read() == b"hello vault"
        assert v.verify_blob(WS, key)
        assert not v.verify_blob(WS, f"00/{'0' * 64}/{AID}")

    def test_stale_staging_lists_only_old_parts(self, tmp_path: Path) -> None:
        v = Vault(tmp_path)
        fresh = v.begin_staging(WS, uuid.uuid4())
        old = v.begin_staging(WS, uuid.uuid4())
        old.write_bytes(b"x")
        past = time.time() - 90000
        os.utime(old, (past, past))
        fresh.write_bytes(b"x")
        stale = list(v.stale_staging(ttl_seconds=3600))
        assert old in stale and fresh not in stale

    def test_blob_never_in_stale_staging(self, tmp_path: Path) -> None:
        v = Vault(tmp_path)
        staging = v.begin_staging(WS, AID)
        v.append_bytes(staging, b"data")
        digest, _ = sha256_file(staging)
        v.commit(WS, AID, digest)
        assert list(v.stale_staging(ttl_seconds=0)) == []
