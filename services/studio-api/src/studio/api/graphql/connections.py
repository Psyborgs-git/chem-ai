"""Bounded keyset connections (§8.1/§8.2, AT-0104-2).

Every growing collection paginates over a stable ``(created_at, id)``
ordering with the ID as tie-breaker — tied timestamps cannot produce
duplicates or gaps. Page size is bounded; cursors are bound to the
issuing scope/filter/order (see ``ids.py``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

import strawberry
from sqlalchemy import Select, tuple_
from sqlalchemy.orm import Session

from studio.api.graphql.ids import decode_cursor, encode_cursor
from studio.errors import DomainError, ErrorCode

DEFAULT_PAGE = 20
MAX_PAGE = 50

RowT = TypeVar("RowT")


@strawberry.type
class PageInfo:
    has_next_page: bool
    has_previous_page: bool
    start_cursor: str | None
    end_cursor: str | None


@dataclass
class PageArgs:
    first: int
    after: tuple[datetime, uuid.UUID] | None


def page_args(first: int | None, after: str | None, *, kind: str, sig: str) -> PageArgs:
    """Validate + decode pagination arguments. Backward pagination is
    not implemented — it is rejected, never silently mishandled."""
    size = DEFAULT_PAGE if first is None else first
    if size < 1 or size > MAX_PAGE:
        raise DomainError(
            ErrorCode.VALIDATION,
            f"page size must be between 1 and {MAX_PAGE}",
            field_path="first",
        )
    key = decode_cursor(after, kind=kind, sig=sig) if after else None
    return PageArgs(first=size, after=key)


def reject_backward(before: str | None, last: int | None) -> None:
    if before is not None or last is not None:
        raise DomainError(
            ErrorCode.VALIDATION,
            "backward pagination is not supported; paginate forward",
            field_path="before" if before is not None else "last",
        )


def keyset_page(
    db: Session,
    stmt: Select[Any],
    ts_col: Any,
    id_col: Any,
    args: PageArgs,
    *,
    kind: str,
    sig: str,
) -> tuple[list[RowT], list[str], PageInfo]:
    """Run one bounded keyset query ordered (created_at DESC, id DESC).

    Fetches ``first + 1`` rows to compute ``hasNextPage`` without a
    COUNT query. Returns (rows, per-row cursors, pageInfo).
    """
    ordered = stmt.order_by(ts_col.desc(), id_col.desc())
    if args.after is not None:
        ordered = ordered.where(tuple_(ts_col, id_col) < args.after)
    rows = list(db.execute(ordered.limit(args.first + 1)).scalars().all())
    has_next = len(rows) > args.first
    page = rows[: args.first]
    cursors = [encode_cursor(kind, sig, (r.created_at, r.id)) for r in page]
    info = PageInfo(
        has_next_page=has_next,
        has_previous_page=args.after is not None,
        start_cursor=cursors[0] if cursors else None,
        end_cursor=cursors[-1] if cursors else None,
    )
    return page, cursors, info
