"""Engine/session factories (sync SQLAlchemy 2 + psycopg v3)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def make_engine(url: str, *, echo: bool = False, pool_size: int = 5) -> Engine:
    engine = create_engine(url, echo=echo, pool_size=pool_size, pool_pre_ping=True)

    @event.listens_for(engine, "connect")
    def _set_session_params(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        # Defense in depth: no trustable search_path beyond public, UTC.
        cur = dbapi_conn.cursor()
        cur.execute("SET search_path = public")
        cur.execute("SET TimeZone = 'UTC'")
        cur.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Commit-or-rollback scope for service-layer unit of work."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
