"""Disposable-database fixtures for integration tests (CS-0101+).

Each session spins up a throwaway PostgreSQL container; each test gets a
fresh schema via alembic upgrade head on a per-test database.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.community.postgres import PostgresContainer

MIGRATIONS = os.path.join(os.path.dirname(__file__), "..", "migrations", "alembic.ini")


@pytest.fixture(scope="session")
def pg_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16.10-alpine") as pg:
        yield pg


def _alembic_cfg(url: str) -> Config:
    cfg = Config(MIGRATIONS)
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture()
def db_url(pg_container: PostgresContainer) -> Iterator[str]:
    """A fresh, migrated database for one test."""
    admin_url = pg_container.get_connection_url(driver="psycopg")
    dbname = f"t_{uuid.uuid4().hex[:12]}"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    try:
        base = admin_url.rsplit("/", 1)[0]
        url = f"{base}/{dbname}"
        command.upgrade(_alembic_cfg(url), "head")
        yield url
    finally:
        admin_engine.dispose()
        drop = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with drop.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :d AND pid <> pg_backend_pid()"
                ),
                {"d": dbname},
            )
            conn.execute(text(f'DROP DATABASE "{dbname}"'))
        drop.dispose()


@pytest.fixture()
def session(db_url: str) -> Iterator[Session]:
    engine = create_engine(db_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    s = factory()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()
