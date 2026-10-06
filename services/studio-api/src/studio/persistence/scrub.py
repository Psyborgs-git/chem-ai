"""Persisted-text hygiene (CS-1101).

Postgres ``text`` and ``jsonb`` columns refuse NUL (``\\x00``) bytes —
an untrusted document or payload carrying one would crash the INSERT
as a raw driver error instead of a typed denial. ``pg_clean`` strips
NUL bytes out of strings recursively (dicts/lists/scalars) at the
persistence boundary and reports whether anything was scrubbed, so the
record can carry an honest ``nul_scrubbed`` flag rather than silently
mutating.
"""

from __future__ import annotations

from typing import Any

NUL = "\x00"


def pg_clean(value: Any) -> tuple[Any, bool]:
    """Return (cleaned, scrubbed) — NUL bytes removed from every
    string inside the structure; ``scrubbed`` is True iff a byte was
    removed anywhere."""
    scrubbed = False

    def walk(v: Any) -> Any:
        nonlocal scrubbed
        if isinstance(v, str):
            if NUL in v:
                scrubbed = True
                return v.replace(NUL, "")
            return v
        if isinstance(v, dict):
            return {walk(k): walk(val) for k, val in v.items()}
        if isinstance(v, (list, tuple)):
            return type(v)(walk(x) for x in v)
        return v

    return walk(value), scrubbed
