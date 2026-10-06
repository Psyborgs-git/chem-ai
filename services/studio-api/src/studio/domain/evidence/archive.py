"""Archive member safety (AT-0103-1, §9.1, §21.4).

Archives are containers of untrusted names. Any traversal component,
absolute path, link member or device node rejects the whole upload
*before* bytes enter the vault — the staged file is discarded, nothing
is extracted.
"""

from __future__ import annotations

import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from studio.errors import DomainError, ErrorCode

# Declared media types that are treated as archives. Detection by
# content (magic bytes) supplements this in the service layer.
ZIP_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
TAR_TYPES = {"application/x-tar"}
TAR_GZ_TYPES = {"application/gzip", "application/x-gtar", "application/x-tgz"}
ARCHIVE_TYPES = ZIP_TYPES | TAR_TYPES | TAR_GZ_TYPES


@dataclass(frozen=True)
class ArchiveLimits:
    max_members: int = 10_000
    max_decompressed_bytes: int = 2 * 1024 * 1024 * 1024
    max_compression_ratio: float = 100.0


def unsafe_member_reason(name: str) -> str | None:
    """Why one member name is unsafe, or None if it is inert."""
    if not name or "\x00" in name:
        return "empty or NUL-containing member name"
    stripped = name.rstrip("/")  # trailing dir marker is legal
    if not stripped:
        return "empty member name"
    # Backslash is a path separator on Windows — normalize before the
    # segment checks so 'a\..\b' is caught like 'a/../b' (CS-1101).
    normalized = stripped.replace("\\", "/")
    if normalized.startswith("/"):
        return "absolute path member"
    win = PureWindowsPath(stripped)
    if win.is_absolute() or (len(stripped) >= 2 and stripped[1] == ":"):
        return "absolute/drive-letter member"
    parts = normalized.split("/")
    if ".." in parts:
        return "parent-directory traversal member"
    if any(part in ("", ".") for part in parts):
        return "empty/dot path segment"
    return None


def _reject(reason: str) -> DomainError:
    return DomainError(
        ErrorCode.VALIDATION,
        f"unsafe archive: {reason}; the payload stays outside the vault",
    )


def check_zip(path: Path, limits: ArchiveLimits) -> None:
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise _reject("declared zip is not readable") from exc
    with zf:
        infos = zf.infolist()
        if len(infos) > limits.max_members:
            raise _reject(f"more than {limits.max_members} members")
        total = 0
        for info in infos:
            if reason := unsafe_member_reason(info.filename):
                raise _reject(f"{reason}: member rejected")
            # Unix-mode symlink entries store S_IFLNK in external_attr.
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise _reject("symlink member")
            if info.is_dir():
                continue
            total += info.file_size
            if total > limits.max_decompressed_bytes:
                raise _reject("decompressed size over limit")
            if info.compress_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > limits.max_compression_ratio:
                    raise _reject("implausible compression ratio")


def check_tar(path: Path, limits: ArchiveLimits) -> None:
    try:
        tf = tarfile.open(path)
    except (tarfile.TarError, OSError) as exc:
        raise _reject("declared tar is not readable") from exc
    with tf:
        members = tf.getmembers()
        if len(members) > limits.max_members:
            raise _reject(f"more than {limits.max_members} members")
        total = 0
        for m in members:
            if reason := unsafe_member_reason(m.name):
                raise _reject(f"{reason}: member rejected")
            if m.issym() or m.islnk():
                raise _reject("link member")
            if m.isdev() or m.isfifo():
                raise _reject("device/FIFO member")
            if not (m.isfile() or m.isdir()):
                raise _reject("non-regular member type")
            if m.isfile():
                total += m.size
                if total > limits.max_decompressed_bytes:
                    raise _reject("decompressed size over limit")


def check_archive(path: Path, media_type: str, limits: ArchiveLimits) -> None:
    """Validate a staged archive before it may enter the vault."""
    if media_type in ZIP_TYPES or zipfile.is_zipfile(path):
        check_zip(path, limits)
    elif media_type in TAR_TYPES | TAR_GZ_TYPES or tarfile.is_tarfile(path):
        check_tar(path, limits)
    # Non-archives need no member checks.
