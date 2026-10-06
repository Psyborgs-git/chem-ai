"""Shared fixtures/helpers for CS-1102 migration + recovery tests.

Each test gets disposable databases on one throwaway PostgreSQL
container (same image as the services suite). ``backup.py``'s pg-tool
fallback is pointed at this container via ``STUDIO_PGTOOL_CONTAINER``
so no compose service or host pg client version is required.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "services" / "studio-api" / "migrations" / "alembic.ini"
LEGACY_BASE_REV = "0012_evidence_revocation"

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def pg() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16.10-alpine") as container:
        yield container


@pytest.fixture()
def db_factory(pg: PostgresContainer) -> Iterator:
    """Create disposable databases on the session container."""
    admin_url = (
        f"postgresql://{pg.username}:{pg.password}@"
        f"{pg.get_container_host_ip()}:{pg.get_exposed_port(5432)}/test"
    )
    created: list[str] = []

    def make() -> str:
        name = f"m_{uuid.uuid4().hex[:12]}"
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{name}"')
        created.append(name)
        return f"{admin_url.rsplit('/', 1)[0]}/{name}"

    yield make

    with psycopg.connect(admin_url, autocommit=True) as conn:
        for name in created:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (name,),
            )
            conn.execute(f'DROP DATABASE IF EXISTS "{name}"')


def alembic_env(dsn: str, pg_container: PostgresContainer | None = None) -> dict[str, str]:
    env = dict(os.environ, STUDIO_DATABASE_URL=dsn)
    if pg_container is not None:
        env["STUDIO_PGTOOL_CONTAINER"] = str(pg_container.get_wrapped_container().id)
    return env


def alembic_upgrade(
    dsn: str,
    rev: str = "head",
    pg_container: PostgresContainer | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(  # noqa: S603 — fixed argv
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ALEMBIC_INI),
            "upgrade",
            rev,
        ],
        check=True,
        env=alembic_env(dsn, pg_container),
        cwd=ROOT,
        capture_output=True,
    )


def alembic_version(dsn: str) -> str:
    with psycopg.connect(dsn, autocommit=True) as conn:
        rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
    assert len(rows) == 1, f"expected 1 alembic_version row, got {rows}"
    return str(rows[0][0])


def alembic_repo_head() -> str:
    out = subprocess.run(  # noqa: S603 — fixed argv
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "heads"],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()
    head = out.splitlines()[-1].split(" ")[0].strip()
    assert head, f"no alembic head parsed from {out!r}"
    return head


def fetchall(dsn: str, sql: str, params: tuple[object, ...] = ()) -> list[tuple]:
    with psycopg.connect(dsn, autocommit=True) as conn:
        cur = conn.execute(sql, params)
        return cur.fetchall() if cur.description else []


def fetchval(dsn: str, sql: str, params: tuple[object, ...] = ()):
    rows = fetchall(dsn, sql, params)
    return rows[0][0] if rows else None


def table_exists(dsn: str, name: str) -> bool:
    return bool(
        fetchval(
            dsn,
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s)",
            (name,),
        )
    )
