"""CS-1101 security regression — transport, scope, worker & egress
boundaries (AT-1101-1).

Beyond hostile payloads: loopback origin/host spoofing at the
middleware, cross-scope id traversal (relay GlobalIDs, raw uuids,
run ids, cursors), SQL/GraphQL injection through every user string,
vault path escape at the storage layer, the parser/executor worker
boundary, audit redaction, session-token edges, and a whole-repo
egress scan covering ``workers/`` + ``infra/`` — not just the API
package the older check scanned.
"""

from __future__ import annotations

import base64
import json
import re
import uuid
from pathlib import Path
from typing import ClassVar

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.testclient import TestClient
from workers.common.executor import (
    ExecLimits,
    ExecResult,
    IsolationProfile,
    SubprocessBackend,
    _write_inputs,
)
from workers.ingestion.limits import IngestionLimits
from workers.ingestion.runner import run_parse

from studio.api.app import create_app
from studio.api.deps import SESSION_COOKIE
from studio.audit.log import record as audit_record
from studio.auth.context import load_context
from studio.auth.sessions import issue_session
from studio.auth.setup import create_owner
from studio.config.settings import Settings
from studio.domain.evidence.vault import Vault
from studio.domain.runs.execution import AttemptExecutor
from studio.domain.runs.queue import RunService
from studio.errors import DomainError
from studio.persistence.models import (
    Principal,
    PrincipalCapability,
    Project,
    Workspace,
)

pytestmark = pytest.mark.security

HEADERS = {"origin": "http://127.0.0.1:8787", "host": "127.0.0.1:8787"}
ROOT = Path(__file__).resolve().parents[4]


# ----------------------------------------------------------------- helpers


@pytest.fixture()
def app(db_url: str, tmp_path: Path) -> FastAPI:
    return create_app(Settings(database_url=db_url, vault_root=tmp_path))


@pytest.fixture()
def authed(app: FastAPI) -> TestClient:
    client = TestClient(app)
    resp = client.post(
        "/api/auth/setup",
        json={
            "login": "owner",
            "display_name": "Owner",
            "password": "correct horse battery staple",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    return client


def _graphql(client: TestClient, query: str, variables: dict | None = None):
    return client.post(
        "/graphql",
        json={"query": query, "variables": variables or {}},
        headers=HEADERS,
    )


def _other_workspace_client(app: FastAPI, session: Session, slug: str = "other-ws") -> TestClient:
    """An authenticated client for a DIFFERENT workspace — probes for
    cross-scope existence leaks."""
    ws_b = Workspace(slug=slug, display_name="Other")
    session.add(ws_b)
    session.flush()
    owner_b = create_owner(session, ws_b, "owner-b", "OB", "long-password-123")
    issued = issue_session(session, ws_b.id, owner_b, 3600)
    session.commit()
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE, issued.token)
    return client


def _researcher_ctx(session: Session):
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    p = Principal(workspace_id=ws.id, kind="user", login="r", display_name="r")
    session.add(p)
    session.flush()
    for cap in sorted(capabilities_for_role("researcher")):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=p.id, capability=cap))
    session.flush()
    return load_context(session, ws.id, p.id)


# ------------------------------------------------------- origin/host spoof


class TestOriginHostSpoofing:
    """AT-1101-1: the loopback middleware rejects every origin/host
    disguise — suffix domains, case tricks, forwarded headers, GET
    mutations."""

    @pytest.mark.parametrize(
        "host",
        [
            "127.0.0.1.evil.com",  # suffix domain
            "127.0.0.1.",  # trailing-dot DNS equivalent
            "0.0.0.0:8787",  # wildcard addr is not loopback
            "evil.com",  # plain foreign
            "localhost.evil.com",  # suffix on the other loopback name
        ],
    )
    def test_disguised_hosts_rejected(self, app: FastAPI, host: str) -> None:
        client = TestClient(app)
        resp = client.get("/api/auth/setup-needed", headers={"host": host})
        assert resp.status_code == 403

    @pytest.mark.parametrize(
        "origin",
        [
            "https://127.0.0.1:8787",  # scheme confusion
            "http://127.0.0.1:8787.evil.com",  # suffix domain
            "http://127.0.0.1:8787/",  # trailing slash is NOT the origin
            "http://127.0.0.1:8787@evil.com",  # userinfo trick
            "HTTP://127.0.0.1:8787",  # case — origins are case-sensitive
        ],
    )
    def test_disguised_origins_rejected(self, app: FastAPI, session: Session, origin: str) -> None:
        client = TestClient(app)
        resp = client.post(
            "/graphql",
            json={
                "query": 'mutation { projectCreate(input: {slug: "x", '
                'name: "x"}) { project { id } errors { code } } }'
            },
            headers={"origin": origin, "host": "127.0.0.1:8787"},
        )
        assert resp.status_code == 403
        assert session.execute(select(Project)).all() == []

    def test_forwarded_headers_do_not_bypass(self, app: FastAPI) -> None:
        """X-Forwarded-* are never consulted — only the real Host."""
        client = TestClient(app)
        resp = client.get(
            "/api/auth/setup-needed",
            headers={
                "host": "evil.com",
                "x-forwarded-host": "127.0.0.1:8787",
                "x-forwarded-for": "127.0.0.1",
                "x-real-ip": "127.0.0.1",
            },
        )
        assert resp.status_code == 403

    def test_ipv6_loopback_host_allowed(self, app: FastAPI) -> None:
        client = TestClient(app)
        resp = client.get("/api/auth/setup-needed", headers={"host": "[::1]:8787"})
        assert resp.status_code == 200

    def test_null_origin_treated_as_absent(self, app: FastAPI) -> None:
        """Sandboxed frames send Origin: null — allowed for commands
        because the SameSite=strict session cookie never rides a
        cross-site request anyway."""
        client = TestClient(app)
        resp = client.post(
            "/graphql",
            json={"query": "{ viewer { id } }"},
            headers={"origin": "null", "host": "127.0.0.1:8787"},
        )
        assert resp.status_code != 403  # middleware passes; auth still applies

    def test_mutation_via_get_never_executes(
        self, app: FastAPI, authed: TestClient, session: Session
    ) -> None:
        """A mutation smuggled into a GET (the CSRF-shaped request a
        browser CAN send cross-site) must never execute."""
        resp = authed.get(
            "/graphql",
            params={
                "query": 'mutation { projectCreate(input: {slug: "csrf", '
                'name: "csrf"}) { project { id } errors { code } } }'
            },
            headers=HEADERS,
        )
        assert session.execute(select(Project)).all() == []
        assert resp.status_code != 200 or resp.json().get("errors")


# ----------------------------------------------------- cross-scope ids


class TestCrossScopeTraversal:
    """AT-1101-1: foreign ids — relay GlobalIDs, raw uuids, run ids,
    cursors — return uniform nulls, never existence leaks."""

    def _project_gid(self, authed: TestClient) -> str:
        resp = _graphql(
            authed,
            'mutation { projectCreate(input: {slug: "p1", name: "P1"}) '
            "{ project { id } errors { code message } } }",
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["data"]["projectCreate"]["project"]["id"]

    def test_foreign_node_id_returns_null(
        self, app: FastAPI, authed: TestClient, session: Session
    ) -> None:
        gid = self._project_gid(authed)
        other = _other_workspace_client(app, session)
        resp = _graphql(other, f'{{ node(id: "{gid}") {{ id }} }}')
        assert resp.status_code == 200
        assert resp.json()["data"]["node"] is None
        # no error text distinguishing foreign from nonexistent
        assert not resp.json().get("errors")

    def test_globalid_type_confusion_returns_null(self, authed: TestClient) -> None:
        """A project uuid repackaged as Run:… resolves nothing — the
        type tag is part of the scope, not decoration."""
        gid = self._project_gid(authed)
        raw = base64.urlsafe_b64decode(gid).decode()
        _, raw_id = raw.split(":", 1)
        confused = base64.urlsafe_b64encode(f"Run:{raw_id}".encode()).decode()
        resp = _graphql(authed, f'{{ node(id: "{confused}") {{ id }} }}')
        assert resp.status_code == 200
        assert resp.json()["data"]["node"] is None

    def test_malformed_globalids_never_crash(self, authed: TestClient) -> None:
        for bad in [
            "AAAA",  # valid b64, no colon
            base64.urlsafe_b64encode(b"Project:not-a-uuid").decode(),
            base64.urlsafe_b64encode(b":").decode(),
        ]:
            resp = _graphql(authed, f'{{ node(id: "{bad}") {{ id }} }}')
            assert resp.status_code in (200, 400)
            body = resp.json()
            assert "Traceback" not in resp.text
            if resp.status_code == 200:
                assert body.get("data", {}).get("node") is None or body.get("errors")

    def test_cursor_reuse_across_workspace_rejected(
        self, app: FastAPI, authed: TestClient, session: Session
    ) -> None:
        """A cursor minted in workspace A is bound to its scope — reuse
        in B is a typed error or empty page, never foreign rows."""
        self._project_gid(authed)
        page1 = _graphql(
            authed, "{ projects(first: 1) { edges { cursor } pageInfo { endCursor } } }"
        )
        cursor = page1.json()["data"]["projects"]["edges"][0]["cursor"]

        other = _other_workspace_client(app, session)
        resp = _graphql(
            other, f'{{ projects(first: 1, after: "{cursor}") {{ edges {{ cursor }} }} }}'
        )
        body = resp.json()
        assert body.get("errors") or body["data"]["projects"]["edges"] == []

    def test_malformed_cursor_is_validation_not_500(self, authed: TestClient) -> None:
        resp = _graphql(authed, '{ projects(first: 1, after: "garbage") { edges { cursor } } }')
        assert resp.status_code in (200, 400)
        body = resp.json()
        assert "errors" in body
        assert "Traceback" not in resp.text and "Internal" not in resp.text

    def test_foreign_artifact_uuid_uniform_denial(
        self, app: FastAPI, authed: TestClient, session: Session
    ) -> None:
        """revocation_impact takes a raw uuid — a foreign/absent
        artifact id resolves to the same typed not-found, no oracle."""
        other = _other_workspace_client(app, session)
        resp = _graphql(other, f'{{ revocationImpact(artifactId: "{uuid.uuid4()}") }}')
        body = resp.json()
        assert resp.status_code == 200
        assert body.get("errors"), "foreign artifact id must not resolve to a report"
        assert "Traceback" not in resp.text


# ------------------------------------------------------------ injection


class TestInjection:
    """AT-1101-1: every user string is a parameter — never SQL, never
    a second query, never an evaluated expression."""

    def test_sql_in_slug_is_literal_or_rejected(self, authed: TestClient, session: Session) -> None:
        payload = "x'; DROP TABLE projects;--"
        resp = _graphql(
            authed,
            "mutation($slug: String!, $name: String!) { projectCreate(input: "
            "{slug: $slug, name: $name}) { project { slug } errors { code } } }",
            {"slug": payload, "name": "harmless"},
        )
        assert resp.status_code == 200
        alive = _graphql(authed, "{ projects(first: 5) { edges { node { slug } } } }")
        assert alive.status_code == 200
        for r in session.execute(select(Project)).scalars().all():
            assert r.slug == payload  # stored, never executed

    def test_sql_in_login_denied(self, authed: TestClient) -> None:
        for payload in ["' OR '1'='1", "owner' --", 'admin"; --']:
            resp = authed.post(
                "/api/auth/login",
                json={"login": payload, "password": "whatever"},
                headers=HEADERS,
            )
            assert resp.status_code in (401, 403)
            assert "studio_session" not in resp.cookies

    def test_oversize_page_rejected(self, authed: TestClient) -> None:
        resp = _graphql(authed, "{ projects(first: 100000) { edges { cursor } } }")
        body = resp.json()
        assert resp.status_code == 200
        assert body.get("errors")

    def test_graphql_string_injection_is_data(self, authed: TestClient) -> None:
        payload = 'a"; mutation { workspace { id } } b"'
        resp = _graphql(
            authed,
            'mutation($n: String!) { projectCreate(input: {slug: "inj", '
            "name: $n}) { project { name } errors { code } } }",
            {"n": payload},
        )
        assert resp.status_code == 200
        # The payload is a string literal — never re-parsed as a query.


# -------------------------------------------------------- vault boundary


class TestVaultContainment:
    """AT-1101-1: storage keys are opaque — traversal in any encoding
    dies at the vault, never reaches the filesystem."""

    @pytest.mark.parametrize(
        "key",
        [
            "../escape",
            "..\\escape",
            "a/../../b",
            "a\\..\\..\\b",
            "/etc/passwd",
            "\\etc\\passwd",
            "..",
            ".",
            "",
            "a\x00b",
        ],
    )
    def test_storage_key_never_escapes(self, tmp_path: Path, key: str) -> None:
        vault = Vault(tmp_path)
        with pytest.raises(DomainError):
            vault.open_blob(uuid.uuid4(), key)
        with pytest.raises(DomainError):
            vault.blob_path(uuid.uuid4(), key)

    @pytest.mark.parametrize("key", ["C:\\Windows\\system.ini", "C:/Windows/system.ini"])
    def test_absolute_like_key_stays_inside_root(self, tmp_path: Path, key: str) -> None:
        """Drive-letter paths are inert relative names on the loopback
        deployment — still confined under the vault root either way."""
        vault = Vault(tmp_path)
        try:
            path = vault.blob_path(uuid.uuid4(), key)
        except DomainError:
            return  # refusing is also correct
        assert path.is_relative_to(vault.root)

    def test_blob_confined_per_workspace(self, tmp_path: Path) -> None:
        """A blob written under ws A is unreachable as ws B — the
        workspace id is part of the storage path."""
        import hashlib

        ws_a, ws_b = uuid.uuid4(), uuid.uuid4()
        aid = uuid.uuid4()
        vault = Vault(tmp_path)
        staging = vault.begin_staging(ws_a, aid)
        vault.append_bytes(staging, b"secret bytes")
        key, _ = vault.commit(ws_a, aid, hashlib.sha256(b"secret bytes").hexdigest())
        # same key, foreign workspace → not found, never cross-read
        with pytest.raises(DomainError):
            vault.open_blob(ws_b, key)


# -------------------------------------------------------- worker boundary


class _HostileBackend:
    """Executor backend that reports hostile stderr — drives the real
    AttemptExecutor sanitization path end to end."""

    profile = IsolationProfile(backend="probe", enforced={"argv_only_no_shell": True})

    def run(self, argv, *, inputs, limits, cancel=None):
        return ExecResult(
            exit_code=3,
            timed_out=False,
            cancelled=False,
            wall_seconds=0.01,
            stdout="not json",
            stderr="x\x1b[31m\x00\nreal line",
            truncated=False,
            profile=self.profile,
        )


class _NoShellEnforcementBackend:
    """A backend that cannot enforce argv-only execution — the run
    must fail profile_unavailable rather than execute unprotected."""

    profile = IsolationProfile(backend="shellish", enforced={})

    def run(self, argv, *, inputs, limits, cancel=None):
        raise AssertionError("backend.run must never be called")


class TestWorkerBoundary:
    """AT-1101-1: the parser subprocess and the run executor are
    containment boundaries — a payload is data, never control."""

    def test_parser_findings_carry_no_host_paths(self) -> None:
        """A crashing parser reports a bounded typed finding — no
        absolute paths or env values leak through the report."""
        data = b"%PDF-1.4\n" + b"\xff" * 64  # pypdf rejects
        report = run_parse(data, "x.pdf", limits=IngestionLimits(), isolate=True)
        blob = " ".join(f["code"] + f.get("detail", "") for f in report.findings)
        blob += " ".join(r.original_text for r in report.records)
        assert not re.search(r"/home/|/tmp/|C:\\|Traceback", blob)

    def test_executor_input_names_are_basenames(self, tmp_path: Path) -> None:
        """inputs keys are file names, never paths."""
        for bad in ("../escape.sh", "sub/dir/x", "..", "."):
            with pytest.raises(ValueError):
                _write_inputs(str(tmp_path), {bad: b"x"})

    def test_executor_env_is_scrubbed(self, tmp_path: Path) -> None:
        """The subprocess profile runs argv-only with a minimal env —
        no inherited credentials, HOME/TMPDIR confined to scratch."""
        import os

        os.environ["CS1101_SENTINEL"] = "must-not-leak"
        try:
            backend = SubprocessBackend(scratch_root=str(tmp_path))
            result = backend.run(
                [
                    "python3",
                    "-c",
                    "import os,json;print(json.dumps(sorted(os.environ)))",
                ],
                inputs={},
                limits=ExecLimits(wall_seconds=15),
            )
        finally:
            del os.environ["CS1101_SENTINEL"]
        env = json.loads(result.stdout.strip().splitlines()[-1])
        assert "CS1101_SENTINEL" not in env
        assert not any("DATABASE" in e or "TOKEN" in e or "SECRET" in e for e in env)
        assert result.profile.enforced["argv_only_no_shell"] is True
        assert result.profile.enforced["env_scrubbed"] is True

    def test_executor_shell_metachars_are_argv_literals(self, tmp_path: Path) -> None:
        """argv is exec'd directly — '; $( ) | >' are bytes to the
        program, never shell syntax."""
        backend = SubprocessBackend(scratch_root=str(tmp_path))
        marker = tmp_path / "pwned-cs1101"
        result = backend.run(
            [
                "python3",
                "-c",
                "import sys,json;print(json.dumps(sys.argv))",
                f"; touch {marker}",
                "$(id)",
                "| cat",
            ],
            inputs={},
            limits=ExecLimits(wall_seconds=15),
        )
        argv_seen = json.loads(result.stdout.strip().splitlines()[-1])
        assert argv_seen[1:] == [f"; touch {marker}", "$(id)", "| cat"]
        assert not marker.exists()

    def test_stderr_tail_is_sanitized_in_run_error(self, session: Session) -> None:
        """Attacker-controlled stderr (ANSI escapes, NUL bytes) reaches
        the stored run error scrubbed to printable text — the executor
        message is never a terminal-injection vector."""
        ctx = _researcher_ctx(session)
        svc = RunService(session, ctx)
        run = svc.request(kind="simulation", request={"probe": True})
        attempt = svc.enqueue(run.id)
        ex = AttemptExecutor(session, ctx, _HostileBackend())
        run = ex.execute(run_id=run.id, attempt_id=attempt.id, argv=["noop"])
        assert run.status == "failed"
        message = run.error["message"]
        assert "\x1b" not in message and "\x00" not in message
        assert "real line" in message

    def test_backend_without_argv_contract_refused(self, session: Session) -> None:
        """A backend that can't enforce argv-only execution → the run
        fails 'profile_unavailable', never executes unprotected."""
        ctx = _researcher_ctx(session)
        svc = RunService(session, ctx)
        run = svc.request(kind="simulation", request={"probe": True})
        attempt = svc.enqueue(run.id)
        ex = AttemptExecutor(session, ctx, _NoShellEnforcementBackend())
        run = ex.execute(run_id=run.id, attempt_id=attempt.id, argv=["noop"])
        assert run.status == "failed"
        assert run.error["code"] == "profile_unavailable"


# --------------------------------------------------------- audit/log


class TestAuditRedaction:
    """AT-1101-1: the audit log is minimal by contract — sensitive keys
    die at ANY depth, NUL bytes never reach the jsonb column."""

    def test_nested_sensitive_keys_dropped(self, session: Session) -> None:
        ctx = _researcher_ctx(session)
        ev = audit_record(
            session,
            ctx,
            action="test.nested",
            target_type="probe",
            detail={
                "keep": "visible",
                "envelope": {"token": "sk-leak", "also_ok": 1},
                "items": [{"password": "pw"}, "plain"],
            },
        )
        blob = str(ev.detail)
        assert "sk-leak" not in blob
        assert "pw" not in blob
        assert ev.detail["keep"] == "visible"
        assert ev.detail["envelope"] == {"also_ok": 1}
        assert ev.detail["items"][0] == {}

    def test_nul_in_detail_scrubbed_not_crashed(self, session: Session) -> None:
        ctx = _researcher_ctx(session)
        ev = audit_record(
            session,
            ctx,
            action="test.nul",
            target_type="probe",
            detail={"note": "a\x00b"},
        )
        assert ev.detail["note"] == "ab"


# ------------------------------------------------------------ sessions


class TestSessionEdges:
    """AT-1101-1: forged, expired and revoked tokens are uniform 401s —
    the token hash lookup is an oracle for nothing."""

    def test_forged_token_rejected(self, authed: TestClient) -> None:
        client = TestClient(authed.app)
        client.cookies.set(SESSION_COOKIE, "forged-" + "a" * 40)
        resp = client.post("/graphql", json={"query": "{ viewer { id } }"}, headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json().get("errors")

    def test_expired_session_rejected(
        self, app: FastAPI, authed: TestClient, session: Session
    ) -> None:
        ws = session.execute(select(Workspace)).scalar_one()
        owner = (
            session.execute(select(Principal).where(Principal.workspace_id == ws.id))
            .scalars()
            .first()
        )
        issued = issue_session(session, ws.id, owner, -1)  # already expired
        session.commit()
        client = TestClient(app)
        client.cookies.set(SESSION_COOKIE, issued.token)
        resp = client.post("/graphql", json={"query": "{ viewer { id } }"}, headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json().get("errors")

    def test_revoked_session_rejected(
        self, app: FastAPI, authed: TestClient, session: Session
    ) -> None:
        resp = authed.post("/api/auth/logout", headers=HEADERS)
        assert resp.status_code == 200
        # The same cookie is dead — a fresh client carrying it gets nothing.
        stale = TestClient(app)
        for name, value in authed.cookies.items():
            stale.cookies.set(name, value)
        resp = stale.post("/graphql", json={"query": "{ viewer { id } }"}, headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json().get("errors")


# ------------------------------------------------------------- egress


class TestEgressWholeRepo:
    """AT-1101-1: the no-egress contract covers EVERY runtime tree, not
    just services/studio-api/src. The single reviewed exception is the
    inference worker's loopback urllib client."""

    OUTBOUND_MODULES = (
        "httpx",
        "requests",
        "urllib.request",
        "http.client",
        "aiohttp",
        "smtplib",
        "ftplib",
    )
    # Loopback-bound urllib client to the local llama.cpp container —
    # reviewed, documented, hardcoded 127.0.0.1 base_url.
    ALLOWED: ClassVar[set[str]] = {"workers/inference/runtime.py"}
    IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([\w.]+)")

    @pytest.mark.parametrize("tree", ["services/studio-api/src", "workers", "infra"])
    def test_no_outbound_client_imports(self, tree: str) -> None:
        offenders: list[str] = []
        for path in sorted((ROOT / tree).rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            for i, line in enumerate(path.read_text().splitlines(), 1):
                m = self.IMPORT_RE.match(line)
                if m and any(
                    m.group(1) == mod or m.group(1).startswith(mod + ".")
                    for mod in self.OUTBOUND_MODULES
                ):
                    if rel in self.ALLOWED:
                        continue
                    offenders.append(f"{rel}:{i}: {m.group(1)}")
        assert offenders == []

    def test_inference_client_is_loopback_bound(self) -> None:
        """The one network client must keep its hardcoded loopback
        base — if a future change parameterizes it, this fails."""
        src = (ROOT / "workers/inference/runtime.py").read_text()
        assert 'f"http://127.0.0.1:{host_port}"' in src
        # base_url must never come from the environment or settings
        assert re.search(r"base_url\s*=\s*(os\.environ|settings)", src) is None
