"""Pre-parse inspection (§9.1): declared vs detected type, size and
decompression bounds, and active-content denial — all before any
parser touches the payload."""

from __future__ import annotations

import zipfile
from io import BytesIO

from workers.ingestion.limits import IngestionLimits
from workers.ingestion.types import QuarantineError

# Zip container signatures — a payload starting with any of these is
# inspected as an archive even when its filename/mime claims text.
# PK\x03\x04 local file header · PK\x05\x06 empty-archive EOCD ·
# PK\x06\x06 zip64 EOCD · PK\x01\x02 central-directory entry.
ZIP_MAGICS = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x06\x06", b"PK\x01\x02")

ZIP_MEMBERS_KIND = {
    "xl/workbook.xml": "xlsx",
    "word/document.xml": "docx",
}

# Member names (basename) whose presence means active content we will
# not parse — flag and refuse rather than strip and silently continue.
ACTIVE_CONTENT_MEMBERS = ("vbaproject.bin", "macrosheet", "activex")


def detect_type(data: bytes, filename: str = "") -> str:
    """Sniff the payload — magic bytes first, zip members for the
    office formats, then text fallbacks by filename/content."""
    if data.startswith(b"%PDF"):
        return "pdf"
    if any(data.startswith(m) for m in ZIP_MAGICS):
        try:
            with zipfile.ZipFile(BytesIO(data)) as zf:
                names = set(zf.namelist())
            for marker, kind in ZIP_MEMBERS_KIND.items():
                if marker in names:
                    return kind
        except zipfile.BadZipFile:
            return "zip"
        return "zip"
    head = data[:64].lstrip()
    if head[:1] in (b"{", b"["):
        return "json"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "csv":
        return "csv"
    if ext in ("md", "markdown"):
        return "markdown"
    if b"\x00" in data[:4096]:
        # NUL can never persist to a text column — it marks binary.
        return "binary"
    try:
        data[:4096].decode("utf-8")
        return "text"
    except UnicodeDecodeError:
        return "binary"


def inspect(data: bytes, filename: str, limits: IngestionLimits) -> str:
    """Refuse unsafe payloads; return the detected type otherwise.

    - input size limit
    - zip decompression bound (members, total bytes, ratio)
    - active content (vbaProject, macro sheets) — denied outright
    """
    if len(data) > limits.max_input_bytes:
        raise QuarantineError(
            "INPUT_TOO_LARGE",
            f"{len(data)} bytes exceeds the {limits.max_input_bytes}-byte limit",
        )
    detected = detect_type(data, filename)
    if detected in ("xlsx", "docx", "zip"):
        try:
            zf = zipfile.ZipFile(BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise QuarantineError("CORRUPT_ARCHIVE", "zip payload unreadable") from exc
        with zf:
            infos = zf.infolist()
            if len(infos) > limits.max_zip_members:
                raise QuarantineError(
                    "TOO_MANY_MEMBERS",
                    f"{len(infos)} members exceeds the {limits.max_zip_members} limit",
                )
            total = 0
            for i in infos:
                total += i.file_size
                if i.file_size > limits.max_decompressed_bytes:
                    raise QuarantineError(
                        "DECOMPRESSION_LIMIT",
                        f"member {i.filename} decompresses past the limit",
                    )
                if i.compress_size and i.file_size / i.compress_size > (
                    limits.max_compression_ratio
                ):
                    raise QuarantineError(
                        "DECOMPRESSION_RATIO",
                        f"member {i.filename} exceeds the compression-ratio bound",
                    )
            if total > limits.max_decompressed_bytes:
                raise QuarantineError(
                    "DECOMPRESSION_LIMIT",
                    f"{total} decompressed bytes exceeds the limit",
                )
            names = zf.namelist()
            # Scan every path segment, not only the basename — XLM macro
            # sheets live at 'xl/macrosheets/…' where the marker is the
            # directory, not the member name (CS-1101).
            active = [
                n
                for n in names
                if any(
                    marker in segment
                    for segment in n.lower().replace("\\", "/").split("/")
                    for marker in ACTIVE_CONTENT_MEMBERS
                )
            ]
            if active:
                raise QuarantineError(
                    "ACTIVE_CONTENT_DENIED",
                    f"active content present: {sorted(active)} — parsing "
                    "macros/active content is refused",
                )
    if detected == "pdf":
        # JavaScript / launch actions are denied on inspection.
        head = data[: 4 * 1024 * 1024]
        if b"/JavaScript" in head or b"/JS" in head or b"/Launch" in head:
            raise QuarantineError(
                "ACTIVE_CONTENT_DENIED",
                "PDF contains JavaScript or launch actions — refused",
            )
    return detected
