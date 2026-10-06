"""Quarantine runner — the parse executes in a spawned subprocess
with a hard timeout (§9.1). The child receives bytes only: no
filesystem paths, no network, no session. A timeout is a hard kill,
not a cancelled thread."""

from __future__ import annotations

import multiprocessing as mp
import queue as queue_mod
import time
from typing import Any

from workers.ingestion.limits import DEFAULT_LIMITS, IngestionLimits
from workers.ingestion.parsers import PARSERS
from workers.ingestion.quarantine import inspect
from workers.ingestion.types import (
    PARSER_VERSION,
    ParseReport,
    QuarantineError,
)


def _child(data: bytes, detected: str, limits: IngestionLimits, out: Any) -> None:
    """Entry point for the quarantine subprocess — module-level and
    picklable by construction."""
    try:
        parser = PARSERS.get(detected)
        if parser is None:
            raise QuarantineError("UNSUPPORTED_TYPE", f"no parser for '{detected}'")
        out.put(("ok", parser(data, limits)))
    except QuarantineError as exc:
        out.put(("quarantine", exc.code, exc.message))
    except Exception as exc:  # parser crash — typed, never swallowed
        out.put(("error", type(exc).__name__, str(exc)))


def run_parse(
    data: bytes,
    filename: str,
    *,
    limits: IngestionLimits = DEFAULT_LIMITS,
    isolate: bool = True,
) -> ParseReport:
    """Inspect → parse in a quarantined subprocess with timeout.

    ``isolate=False`` is for fast unit paths; the application always
    crosses the subprocess boundary.
    """
    detected = inspect(data, filename, limits)
    if not isolate:
        return _parse_inline(data, detected, limits)
    ctx = mp.get_context("spawn")  # fresh interpreter — no inherited state
    out: mp.Queue[tuple[Any, ...]] = ctx.Queue()
    proc = ctx.Process(target=_child, args=(data, detected, limits, out), daemon=True)
    proc.start()
    # Drain the result queue while the child runs. A ParseReport larger
    # than the OS pipe buffer can only be delivered while the parent is
    # reading — joining first deadlocks the child on its feeder flush and
    # surfaces as a false PARSE_TIMEOUT (CS-1103 measurement).
    deadline = time.monotonic() + limits.parse_timeout_s
    payload_item: tuple[Any, ...] | None = None
    while proc.is_alive() and time.monotonic() < deadline:
        try:
            payload_item = out.get(timeout=0.1)
        except queue_mod.Empty:
            proc.join(timeout=0.05)
    if payload_item is None and proc.is_alive():
        proc.kill()
        proc.join(timeout=5)
        return ParseReport(
            parser_name="quarantine",
            parser_version=PARSER_VERSION,
            detected_type=detected,
            timed_out=True,
            findings=[
                {
                    "code": "PARSE_TIMEOUT",
                    "detail": f"parse exceeded {limits.parse_timeout_s}s — process killed",
                }
            ],
        )
    proc.join(timeout=5)
    if payload_item is None:
        # The child's queue feeder can outlive process exit by a tick —
        # a clean put() may still be in the pipe. Drain once more on a
        # short grace before treating a payload-less exit as a crash.
        try:
            payload_item = out.get(timeout=5)
        except queue_mod.Empty:
            pass
    if payload_item is None:
        return ParseReport(
            parser_name="quarantine",
            parser_version=PARSER_VERSION,
            detected_type=detected,
            timed_out=False,
            findings=[
                {
                    "code": "WORKER_CRASH",
                    "detail": f"worker exited ({proc.exitcode}) without a result",
                }
            ],
        )
    status, *payload = payload_item
    if status == "ok":
        report = payload[0]
        if not isinstance(report, ParseReport):  # pragma: no cover
            raise QuarantineError("WORKER_PROTOCOL", "unexpected worker payload")
        return report
    if status == "quarantine":
        raise QuarantineError(payload[0], payload[1])
    return ParseReport(
        parser_name="quarantine",
        parser_version=PARSER_VERSION,
        detected_type=detected,
        findings=[
            {
                "code": "PARSER_ERROR",
                "detail": f"{payload[0]}: {payload[1]}",
            }
        ],
    )


def _parse_inline(data: bytes, detected: str, limits: IngestionLimits) -> ParseReport:
    parser = PARSERS.get(detected)
    if parser is None:
        raise QuarantineError("UNSUPPORTED_TYPE", f"no parser for '{detected}'")
    return parser(data, limits)
