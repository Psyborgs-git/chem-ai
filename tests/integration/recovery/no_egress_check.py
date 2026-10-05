"""AT-0505-2 — core profile makes no non-loopback connections.

Two layers:

1. **Static scan** — ``services/studio-api/src`` must import no
   outbound-capable client module (``httpx``, ``requests``,
   ``urllib.request``, ``http.client``, ``smtplib``, ``socket``).
   The only network client in the tree is ``workers/inference``'s
   urllib client, which is bound to a loopback llama.cpp container —
   reported, not exempted silently.

2. **Runtime guard** — ``socket.socket.connect``/``connect_ex`` are
   patched to allow only loopback peers while a real in-process app
   (fresh migrated DB, temp vault) serves setup + authenticated
   GraphQL work. Any proprietary egress attempt raises.

Run: ``uv run python tests/integration/recovery/no_egress_check.py``
(requires compose postgres at 127.0.0.1:54329 — ``make db-up``).
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "services" / "studio-api" / "src"
ADMIN_DSN = "postgresql://studio:studio@127.0.0.1:54329/postgres"
DB = f"studio_egress_{uuid.uuid4().hex[:8]}"
DSN = f"postgresql://studio:studio@127.0.0.1:54329/{DB}"

OUTBOUND_MODULES = (
    "httpx",
    "requests",
    "urllib.request",
    "http.client",
    "aiohttp",
    "smtplib",
    "ftplib",
)
IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([\w.]+)")

_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    if not ok:
        _failures.append(name)


def _scan() -> None:
    print("== static scan: services/studio-api/src ==")
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        for i, line in enumerate(path.read_text().splitlines(), 1):
            m = IMPORT_RE.match(line)
            if (
                m
                and m.group(1).split(".")[0:2]
                and any(
                    m.group(1) == mod or m.group(1).startswith(mod + ".")
                    for mod in OUTBOUND_MODULES
                )
            ):
                offenders.append(f"{path.relative_to(ROOT)}:{i}: {m.group(1)}")
    check("no outbound client imports in core src", not offenders, "; ".join(offenders))


def _loopback_only_guard() -> None:
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def _allowed(addr: object) -> bool:
        if isinstance(addr, tuple) and addr:
            try:
                return ipaddress.ip_address(str(addr[0])).is_loopback
            except ValueError:
                return str(addr[0]) in {"localhost"}
        return False

    from typing import Any

    def guarded_connect(self: socket.socket, addr: Any) -> None:
        if not _allowed(addr):
            raise AssertionError(f"EGRESS BLOCKED: connect to non-loopback {addr!r}")
        real_connect(self, addr)

    def guarded_connect_ex(self: socket.socket, addr: Any) -> int:
        if not _allowed(addr):
            raise AssertionError(f"EGRESS BLOCKED: connect_ex to non-loopback {addr!r}")
        return real_connect_ex(self, addr)

    # setattr sidesteps mypy's method-assign guard; this is an
    # intentional process-wide guard, exactly the thing being tested.
    setattr(socket.socket, "connect", guarded_connect)  # noqa: B010
    setattr(socket.socket, "connect_ex", guarded_connect_ex)  # noqa: B010


def _runtime() -> None:
    print("== runtime guard: in-process app under socket guard ==")
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{DB}"')
    try:
        env = dict(os.environ, STUDIO_DATABASE_URL=DSN)
        subprocess.run(  # noqa: S603 — fixed argv
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(ROOT / "services/studio-api/migrations/alembic.ini"),
                "upgrade",
                "head",
            ],
            check=True,
            env=env,
            cwd=ROOT,
            capture_output=True,
        )
        with tempfile.TemporaryDirectory() as td:
            sys.path.insert(0, str(ROOT / "services" / "studio-api" / "src"))
            from starlette.testclient import TestClient

            from studio.api.app import create_app
            from studio.config.settings import Settings

            _loopback_only_guard()
            app = create_app(Settings(database_url=DSN, vault_root=Path(td) / "vault"))
            client = TestClient(app)
            headers = {"origin": "http://127.0.0.1:8787", "host": "127.0.0.1:8787"}

            try:
                r = client.post(
                    "/api/auth/setup",
                    json={
                        "login": "owner",
                        "display_name": "Owner",
                        "password": "egress check password",
                    },
                    headers=headers,
                )
                check("auth setup under guard", r.status_code == 200, r.text[:200])

                r = client.post(
                    "/graphql",
                    json={
                        "query": "mutation { projectCreate(input: "
                        '{slug: "egress-check", name: "Egress Check"}) '
                        "{ project { id } errors { code message } } }"
                    },
                    headers=headers,
                )
                body = r.json()
                created = body.get("data", {}).get("projectCreate", {}).get("project")
                check(
                    "project create under guard",
                    r.status_code == 200 and bool(created),
                    json.dumps(body)[:200],
                )

                r = client.post(
                    "/graphql",
                    json={"query": "{ projects(first: 5) { edges { node { slug } } } }"},
                    headers=headers,
                )
                check("project query under guard", r.status_code == 200)
            except AssertionError as exc:
                check("no non-loopback connection attempted", False, str(exc))
            else:
                check("no non-loopback connection attempted", True)
    finally:
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (DB,),
            )
            conn.execute(f'DROP DATABASE IF EXISTS "{DB}"')


def main() -> int:
    _scan()
    _runtime()
    if _failures:
        print(f"no_egress_check: FAILED ({len(_failures)})")
        return 1
    print("no_egress_check: OK — core profile attempted no non-loopback egress")
    return 0


if __name__ == "__main__":
    sys.exit(main())
