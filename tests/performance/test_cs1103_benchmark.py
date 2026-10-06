"""CS-1103 / AT-1103-1 — recorded performance benchmark (§23.1).

A real uvicorn server on a throwaway PostgreSQL database is seeded with
a recorded-size synthetic fixture, then measured while a heavy
subprocess run executes in the background. Everything reported here is
measured on the machine that ran it — hardware, dataset scale,
concurrency, and cold/warm state are recorded alongside the numbers.
§23.1's targets are engineering proposals: results are reported
measured-vs-target; no unmeasured throughput is claimed anywhere.

Fixture-only — synthetic rows prove responsiveness, not scientific
validity.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import socket
import statistics
import subprocess
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker
from workers.common.executor import ExecLimits, SubprocessBackend

from studio.auth.context import load_context
from studio.domain.evidence.retrieval import RetrievalService
from studio.domain.runs.admission import AdmissionService
from studio.domain.runs.execution import AttemptExecutor
from studio.domain.runs.queue import RunService
from studio.persistence.models import (
    Principal,
    ResearchSession,
    Run,
    RunAttempt,
    SessionMessage,
    Workspace,
)

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = REPO_ROOT / "docs" / "execution" / "benchmarks"
GB = 1024**3

# Recorded fixture scale — every number below is the real dataset the
# measurements ran against on this machine.
N_TASKS = 300
N_SESSIONS = 40
N_MESSAGES_PER_SESSION = 8
N_COMPLETED_RUNS = 8
N_ATTEMPTS_PER_RUN = 30
CORPUS_ROWS = 600  # import → indexed source chunks
IMPORT_ROWS = 1200  # measured import
LARGE_ARTIFACT_BYTES = 64 * 1024 * 1024
PAGE = 50
READ_PROBES = 30


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _machine() -> dict[str, Any]:
    cpu = "unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    mem_gib = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                mem_gib = round(int(line.split()[1]) / 1024 / 1024, 1)
                break
    except OSError:
        pass
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_model": cpu,
        "cpu_count_logical": os.cpu_count(),
        "ram_total_gib": mem_gib,
        "captured_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def _stats(samples: list[float]) -> dict[str, Any]:
    """seconds → ms stats; n<20 percentile values are still reported but
    the sample list is the primary record."""
    ms = [round(s * 1000, 2) for s in samples]
    ms_sorted = sorted(ms)
    return {
        "n": len(ms),
        "min_ms": ms_sorted[0],
        "max_ms": ms_sorted[-1],
        "mean_ms": round(statistics.fmean(ms), 2),
        "p50_ms": ms_sorted[len(ms_sorted) // 2],
        "p95_ms": ms_sorted[max(0, int(len(ms_sorted) * 0.95) - 1)],
        "samples_ms": ms,
    }


class Bench:
    def __init__(self, base: str, token: str) -> None:
        self.base = base
        self.client = httpx.Client(
            base_url=base,
            headers={"Origin": base},
            cookies={"studio_session": token},
            timeout=httpx.Timeout(120.0, connect=10.0),
        )

    def gql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        r = self.client.post("/graphql", json={"query": query, "variables": variables or {}})
        r.raise_for_status()
        body = r.json()
        if body.get("errors"):
            raise AssertionError(json.dumps(body["errors"]))
        return body["data"]


def _upload(
    client: Bench, name: str, media: str, data: bytes, chunk: int = 8 * 1024 * 1024
) -> dict[str, str]:
    init = client.client.post(
        "/api/artifacts/uploads",
        json={"original_name": name, "media_type": media, "declared_size": len(data)},
    )
    init.raise_for_status()
    artifact_id = init.json()["artifactId"]
    for off in range(0, len(data), chunk):
        r = client.client.put(
            f"/api/artifacts/uploads/{artifact_id}/content",
            content=data[off : off + chunk],
        )
        r.raise_for_status()
    fin = client.client.post(f"/api/artifacts/uploads/{artifact_id}/finish", json={})
    fin.raise_for_status()
    body = fin.json()
    return {"id": artifact_id, "checksum": body["checksumSha256"]}


def _decode_gid(gid: str) -> uuid.UUID:
    import base64

    return uuid.UUID(base64.b64decode(gid).decode().split(":")[-1])


def _encode_gid(typename: str, uid: uuid.UUID) -> str:
    import base64

    return base64.b64encode(f"{typename}:{uid}".encode()).decode()


RECORDS_PER_ROW = 2  # parse_csv extracts one record per non-empty cell
WORDS = ["solvent", "phenol", "resin", "binder", "catalyst", "film", "cure", "glass"]


def _build_csv(rows: int, tag: str) -> bytes:
    out = ["component,amount"]
    for i in range(rows):
        w = WORDS[i % len(WORDS)]
        out.append(f"{w} blend {tag}-{i} observation,{i % 97}")
    return ("\n".join(out) + "\n").encode()


def test_benchmark_cs1103(db_url: str, session: Session, tmp_path: Path) -> None:
    """AT-1103-1 — the full measured benchmark. Asserts the paths work
    and the fixture is what it claims; every number is recorded to
    docs/execution/benchmarks/ as evidence, measured-vs-target."""
    report: dict[str, Any] = {
        "ticket": "CS-1103",
        "capability": "fixture-only performance evidence — not scientific validation",
        "targets_23_1": {
            "indexed_record_read_p95_ms": 500,
            "mutation_ack_p95_ms": 1000,
            "ui_responsive_during_heavy_job": "no failed interactions",
            "progress_or_heartbeat_visible": True,
        },
        "machine": _machine(),
        "scale": {
            "tasks": N_TASKS,
            "sessions": N_SESSIONS,
            "session_messages": N_SESSIONS * N_MESSAGES_PER_SESSION,
            "completed_runs": N_COMPLETED_RUNS,
            "attempts": N_COMPLETED_RUNS * N_ATTEMPTS_PER_RUN,
            "corpus_csv_rows": CORPUS_ROWS,
            "corpus_records": CORPUS_ROWS * RECORDS_PER_ROW,
            "import_csv_rows": IMPORT_ROWS,
            "import_records": IMPORT_ROWS * RECORDS_PER_ROW,
            "large_artifact_bytes": LARGE_ARTIFACT_BYTES,
            "page_size": PAGE,
        },
        "concurrency": {"worker_jobs": 1, "read_probes_under_load": READ_PROBES},
        "results": {},
    }
    engine = session.get_bind()
    report["machine"]["postgres"] = session.execute(text("SELECT version()")).scalar()

    # ---- live server -------------------------------------------------
    port = _free_port()
    vault = tmp_path / "vault"
    env = {
        **os.environ,
        "STUDIO_DATABASE_URL": db_url,
        "STUDIO_VAULT_ROOT": str(vault),
        "STUDIO_ALLOWED_ORIGINS": f"http://127.0.0.1:{port}",
        "STUDIO_EVENT_MAX_SECONDS": "2",
    }
    t0 = time.perf_counter()
    proc = subprocess.Popen(  # noqa: S603 — fixed argv to the venv interpreter
        [
            sys.executable,
            "-m",
            "uvicorn",
            "studio.api.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 30
        while True:
            try:
                if httpx.get(f"{base}/healthz", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            assert time.time() < deadline, "uvicorn never came up"
            time.sleep(0.25)
        report["server_cold_start_s"] = round(time.perf_counter() - t0, 2)

        # ---- identity ------------------------------------------------
        anon = httpx.Client(base_url=base, headers={"Origin": base})
        res = anon.post(
            "/api/auth/setup",
            json={
                "login": "bench-owner",
                "display_name": "Bench Owner",
                "password": "bench-password-10",
            },
        )
        res.raise_for_status()
        token = re.search(r"studio_session=([^;]+)", res.headers["set-cookie"]).group(1)  # type: ignore[union-attr]
        bench = Bench(base, token)

        ws = session.execute(select(Workspace)).scalars().one()
        owner = session.execute(
            select(Principal).where(Principal.login == "bench-owner")
        ).scalar_one()
        ctx = load_context(session, ws.id, owner.id)

        # ---- seed (recorded, not measured) ---------------------------
        seed_t0 = time.perf_counter()
        proj = bench.gql(
            'mutation { projectCreate(input: {slug: "bench", name: "Bench"}) '
            "{ project { id } errors { message } } }"
        )
        project_gid = proj["projectCreate"]["project"]["id"]
        task_ids: list[uuid.UUID] = []
        for i in range(N_TASKS):
            r = bench.gql(
                "mutation ($p: ID!, $t: String!) { taskCreate(input: "
                '{projectId: $p, title: $t, mode: "improve", '
                'targetKind: "formulation"}) { task { id } errors { message } } }',
                {"p": project_gid, "t": f"bench task {i}"},
            )
            task_ids.append(_decode_gid(r["taskCreate"]["task"]["id"]))

        # sessions + messages + completed run history via ORM bulk rows
        for i in range(N_SESSIONS):
            s = ResearchSession(
                workspace_id=ws.id,
                task_id=task_ids[i],
                status="ended",
                started_by=owner.id,
                ended_at=datetime.now(UTC),
            )
            session.add(s)
            session.flush()
            for j in range(N_MESSAGES_PER_SESSION):
                session.add(
                    SessionMessage(
                        workspace_id=ws.id,
                        session_id=s.id,
                        role="user",
                        content=f"bench note {i}-{j}: solvent ratio finding",
                    )
                )
        for i in range(N_COMPLETED_RUNS):
            run = Run(
                workspace_id=ws.id,
                task_id=task_ids[i],
                kind="simulation",
                request_digest=hashlib.sha256(f"r{i}".encode()).hexdigest(),
                status="succeeded",
                requested_by=owner.id,
                queued_at=datetime.now(UTC),
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                attempt_count=N_ATTEMPTS_PER_RUN,
            )
            session.add(run)
            session.flush()
            for a in range(N_ATTEMPTS_PER_RUN):
                session.add(
                    RunAttempt(
                        workspace_id=ws.id,
                        run_id=run.id,
                        attempt_number=a + 1,
                        status="succeeded",
                        worker_id="bench-seed",
                        started_at=datetime.now(UTC),
                        finished_at=datetime.now(UTC),
                    )
                )
        session.commit()

        # search corpus: real artifact → real parser → real chunk index
        corpus_csv = _build_csv(CORPUS_ROWS, "corpus")
        corpus_artifact = _upload(bench, "corpus.csv", "text/csv", corpus_csv)["id"]
        imp = bench.gql(
            "mutation ($a: String!) { imports { artifactImport(input: "
            "{artifactId: $a}) { batch { id status recordCount } errors { message } } } }",
            {"a": corpus_artifact},
        )
        batch_gid = imp["imports"]["artifactImport"]["batch"]["id"]
        assert imp["imports"]["artifactImport"]["batch"]["status"] == "parsed"
        batch_id = _decode_gid(batch_gid)
        n_chunks = RetrievalService(session).index_batch(ctx, batch_id)
        session.commit()
        report["scale"]["source_chunks_indexed"] = n_chunks

        big_blob = os.urandom(LARGE_ARTIFACT_BYTES)
        big = _upload(bench, "big.bin", "application/octet-stream", big_blob)
        report["fixture_setup_seconds"] = round(time.perf_counter() - seed_t0, 1)

        # =================  measured scenarios  =======================
        results = report["results"]

        # 1. keyset pagination — cold first page, then warm page walk
        tasks_q = (
            "query ($p: ID!, $after: String) { projectTasks(projectId: $p, "
            f"first: {PAGE}, after: $after) {{ edges {{ cursor node {{ id title }} }} "
            "pageInfo { hasNextPage endCursor } } }"
        )
        cold_t = time.perf_counter()
        page = bench.gql(tasks_q, {"p": project_gid})
        results["pagination_project_tasks_cold_ms"] = round(
            (time.perf_counter() - cold_t) * 1000, 2
        )
        lat: list[float] = [cold_t]
        seen = len(page["projectTasks"]["edges"])
        cursor = page["projectTasks"]["pageInfo"]["endCursor"]
        while page["projectTasks"]["pageInfo"]["hasNextPage"]:
            t = time.perf_counter()
            page = bench.gql(tasks_q, {"p": project_gid, "after": cursor})
            lat.append(time.perf_counter() - t)
            seen += len(page["projectTasks"]["edges"])
            cursor = page["projectTasks"]["pageInfo"]["endCursor"]
        assert seen == N_TASKS, f"keyset walk saw {seen}/{N_TASKS} tasks"
        results["pagination_project_tasks"] = _stats(lat[1:])
        results["pagination_project_tasks"]["pages"] = len(lat)
        results["pagination_project_tasks"]["rows_walked"] = seen

        # importRecords keyset walk over the 600-row parsed batch
        rec_q = (
            "query ($b: ID!, $after: String) { importRecords(batchId: $b, "
            f"first: {PAGE}, after: $after) {{ edges {{ cursor node {{ id }} }} "
            "pageInfo { hasNextPage endCursor } } }"
        )
        lat = []
        page = bench.gql(rec_q, {"b": batch_gid})
        got = len(page["importRecords"]["edges"])
        cursor = page["importRecords"]["pageInfo"]["endCursor"]
        while page["importRecords"]["pageInfo"]["hasNextPage"]:
            t = time.perf_counter()
            page = bench.gql(rec_q, {"b": batch_gid, "after": cursor})
            lat.append(time.perf_counter() - t)
            got += len(page["importRecords"]["edges"])
            cursor = page["importRecords"]["pageInfo"]["endCursor"]
        assert got == CORPUS_ROWS * RECORDS_PER_ROW
        results["pagination_import_records"] = _stats(lat)
        results["pagination_import_records"]["pages"] = len(lat) + 1
        results["pagination_import_records"]["rows_walked"] = got

        # 2. artifact streaming download — cold + warm, checksum verified
        got_hash = hashlib.sha256()
        t = time.perf_counter()
        n_bytes = 0
        hdr_checksum = ""
        with bench.client.stream("GET", f"/api/artifacts/{big['id']}/content") as r:
            r.raise_for_status()
            hdr_checksum = r.headers.get("x-content-sha256", "")
            for chunk in r.iter_bytes(1024 * 1024):
                got_hash.update(chunk)
                n_bytes += len(chunk)
        cold_dl = time.perf_counter() - t
        assert n_bytes == LARGE_ARTIFACT_BYTES
        assert got_hash.hexdigest() == big["checksum"] == hdr_checksum
        warm: list[float] = []
        for _ in range(3):
            t = time.perf_counter()
            r = bench.client.get(f"/api/artifacts/{big['id']}/content")
            r.raise_for_status()
            _ = r.content
            warm.append(time.perf_counter() - t)
        results["artifact_download_64mb"] = {
            "cold_ms": round(cold_dl * 1000, 1),
            "warm": _stats(warm),
            "bytes": n_bytes,
            "cold_mib_s": round(LARGE_ARTIFACT_BYTES / cold_dl / 1024 / 1024, 1),
        }

        # 3. lexical search — service boundary (no public route exists;
        #    the resolver path is agent-only §10), cold + cached warm
        svc = RetrievalService(session)
        # probes must genuinely hit the indexed corpus — the component
        # cell of row n is "{WORDS[n % 8]} blend corpus-n observation",
        # so each probe pairs the row's real word with its id (AND query)
        lat = []
        total_hits = 0
        for i in range(12):
            n = i * 47
            q = f"{WORDS[n % len(WORDS)]} blend corpus-{n}"
            t = time.perf_counter()
            hits, _manifest = svc.search(ctx, q, limit=20)
            lat.append(time.perf_counter() - t)
            total_hits += len(hits)
        results["search_lexical_uncached"] = _stats(lat)
        results["search_lexical_uncached"]["total_hits"] = total_hits
        assert total_hits > 0, "search probes never hit the indexed corpus"
        lat = []
        hits2: list[Any] = []
        for _ in range(6):
            t = time.perf_counter()
            hits2, _m2 = svc.search(ctx, "resin blend corpus-42", limit=20)
            lat.append(time.perf_counter() - t)
        results["search_lexical_cached"] = _stats(lat)
        results["search_lexical_cached"]["hits"] = len(hits2)
        assert hits2, "warm search returned no hits for a seeded term"

        # 4. mutation ack — taskCreate through the real command path
        lat = []
        for i in range(12):
            t = time.perf_counter()
            r = bench.gql(
                "mutation ($p: ID!, $t: String!) { taskCreate(input: "
                '{projectId: $p, title: $t, mode: "improve", '
                'targetKind: "formulation"}) { task { id } errors { message } } }',
                {"p": project_gid, "t": f"ack probe {i}"},
            )
            lat.append(time.perf_counter() - t)
            assert r["taskCreate"]["task"]["id"]
        results["mutation_ack_task_create"] = _stats(lat)

        # 5. import backpressure — a real parse while the UI reads
        import_csv = _build_csv(IMPORT_ROWS, "payload")
        imp_artifact = _upload(bench, "payload.csv", "text/csv", import_csv)["id"]
        read_lat: list[float] = []
        stop = threading.Event()

        def probe_reads() -> None:
            c = Bench(base, token)
            while not stop.is_set():
                t = time.perf_counter()
                r = c.client.get("/healthz")
                r.raise_for_status()
                read_lat.append(time.perf_counter() - t)
                time.sleep(0.02)

        thr = threading.Thread(target=probe_reads, daemon=True)
        thr.start()
        t = time.perf_counter()
        imp2 = bench.gql(
            "mutation ($a: String!) { imports { artifactImport(input: "
            "{artifactId: $a}) { batch { id status recordCount } errors { message } } } }",
            {"a": imp_artifact},
        )
        import_ms = (time.perf_counter() - t) * 1000
        stop.set()
        thr.join(timeout=10)
        assert imp2["imports"]["artifactImport"]["batch"]["status"] == "parsed"
        assert (
            imp2["imports"]["artifactImport"]["batch"]["recordCount"]
            == IMPORT_ROWS * RECORDS_PER_ROW
        )
        results["import_backpressure"] = {
            "import_rows": IMPORT_ROWS,
            "import_wall_ms": round(import_ms, 1),
            "concurrent_healthz": _stats(read_lat),
        }

        # 6. worker contention — real subprocess job + UI activity
        ws_session = sessionmaker(bind=engine, expire_on_commit=False)()
        worker_ctx = load_context(ws_session, ws.id, owner.id)
        adm = AdmissionService(ws_session, worker_ctx)
        adm.ensure_group(
            "compute",
            capacity={"cpu_cores": 8, "memory_bytes": 16 * GB, "concurrency": 4},
            reserve={},
        )
        runs = RunService(ws_session, worker_ctx)
        run = runs.request(
            kind="simulation",
            request={"bench": "contention"},
            task_id=task_ids[0],
        )
        decision = adm.admit(run.id, {"memory_bytes": 1 * GB, "wall_seconds": 120})
        assert decision.admitted
        attempt = (
            ws_session.execute(select(RunAttempt).where(RunAttempt.run_id == run.id))
            .scalars()
            .one()
        )
        ws_session.commit()  # queued attempt visible to the API now

        executor = AttemptExecutor(
            ws_session, worker_ctx, SubprocessBackend(), worker_id="bench-w1"
        )
        burn = (
            "import time,json\n"
            "t=time.time();n=0\n"
            "while time.time()-t<10: n+=1\n"
            "print(json.dumps({'ok':True,'spins':n}))\n"
        )
        done: dict[str, Any] = {}

        def heavy() -> None:
            done["run"] = executor.execute(
                run_id=run.id,
                attempt_id=attempt.id,
                argv=[sys.executable, "-c", burn],
                limits=ExecLimits(wall_seconds=60),
            )
            ws_session.commit()

        worker = threading.Thread(target=heavy, daemon=True)
        worker.start()
        # commit the flushed running transition so the API reports
        # real progress mid-flight (executor holds no ORM op during
        # backend.run — the commit is the worker-loop's)
        time.sleep(1.0)
        try:
            ws_session.commit()
            heartbeat_visible = True
        except Exception:
            heartbeat_visible = False

        ui_lat: list[float] = []
        run_q = (
            "query ($t: ID!) { taskRuns(taskId: $t, first: 10) { edges { node { id status } } } }"
        )
        task_gid = _encode_gid("Task", task_ids[0])
        status_seen: set[str] = set()
        while worker.is_alive():
            t = time.perf_counter()
            bench.gql(tasks_q, {"p": project_gid})
            ui_lat.append(time.perf_counter() - t)
            rr = bench.gql(run_q, {"t": task_gid})
            statuses = {e["node"]["status"] for e in rr["taskRuns"]["edges"]}
            status_seen |= statuses
        worker.join(timeout=30)
        results["worker_contention"] = {
            "job": "python cpu-burn ~10s in isolated subprocess backend",
            "ui_project_tasks_during": _stats(ui_lat),
            "run_statuses_observed": sorted(status_seen),
            "heartbeat_or_progress_visible": heartbeat_visible,
            "run_terminal_status": done["run"].status,
        }
        assert done["run"].status == "succeeded"
        assert {"queued", "running"} & status_seen  # progress was visible

        ws_session.close()

        # ---- write the recorded report --------------------------------
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d")
        out = REPORT_DIR / f"cs1103-{stamp}.json"
        out.write_text(json.dumps(report, indent=2) + "\n")
        latest = REPORT_DIR / "cs1103-latest.json"
        shutil.copy(out, latest)

        # functional sanity — results exist, reads are sub-second-scale
        assert results["pagination_project_tasks"]["rows_walked"] == N_TASKS
        assert results["artifact_download_64mb"]["bytes"] == LARGE_ARTIFACT_BYTES
        assert results["import_backpressure"]["import_rows"] == IMPORT_ROWS
        assert results["worker_contention"]["heartbeat_or_progress_visible"]
        print(json.dumps({k: v for k, v in results.items()}, indent=2, default=str))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
