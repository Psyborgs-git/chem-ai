# CS-1103 performance benchmark — measured vs §23.1 targets

**Capability label:** fixture-only performance evidence on synthetic data — not scientific validation.

Run `pytest tests/performance/test_cs1103_benchmark.py` reproduces the measurement and rewrites `cs1103-<date>.json` + `cs1103-latest.json` in this directory. All numbers below are real measurements on this machine, no projected throughput.

## Recorded environment

| | |
|---|---|
| Machine | Intel Xeon Platinum 8375C @ 2.90GHz, 8 logical cores, 31.3 GiB RAM, Linux 6.8.0-1061-aws x86_64 |
| Python / Postgres | CPython 3.12.14 / PostgreSQL 16.10 (testcontainers `postgres:16.10-alpine`, fresh `t_*` DB per run, alembic head) |
| Server | real `uvicorn studio.api.app:create_app --factory` subprocess on 127.0.0.1, real vault dir, real auth (owner account, session cookie) |
| Cold/warm | server cold start 1.38 s; fixture setup 4.7 s; download measured cold then 3 warm reads |

## Fixture scale (synthetic, deterministic)

300 tasks · 40 research sessions · 320 session messages · 8 completed runs with 240 attempts · 600-row CSV → 1,200 parsed records → 1,200 indexed source chunks · measured import 1,200 rows → 2,400 records · 64 MiB artifact · page size 50.

## Measured vs §23.1 targets

| §23.1 target | Measured | Result |
|---|---|---|
| indexed record reads p95 < 500 ms | keyset pagination `projectTasks` p95 **11.7 ms** (300 rows / 6 pages); `importRecords` p95 **18.0 ms** (1,200 rows / 24 pages); cold first page **11.6 ms** | PASS |
| mutation ack p95 < 1 s before async work | `taskCreate` through the real command path p95 **11.2 ms** (n=12) | PASS |
| UI responsive during heavy job | 470 `projectTasks` page reads issued while a CPU-burn subprocess run executed — p95 **13.4 ms**, max 73.1 ms, zero failed interactions | PASS |
| visible progress/heartbeat | run observed `running` → `succeeded` via `taskRuns` polling mid-execution (status transitions visible to the API while the worker ran) | PASS |

## Additional measured paths

| Path | Measurement |
|---|---|
| Artifact streaming | 64 MiB download cold **91.4 ms** (~700 MiB/s), warm p95 92.1 ms; `X-Content-SHA256` header matched the uploaded checksum |
| Lexical search (uncached) | p95 **10.9 ms**, 12/12 probes hit the indexed corpus |
| Lexical search (cached) | p95 **3.0 ms** via `RetrievalCache` |
| Import backpressure | 1,200-row CSV upload→parse→`parsed` batch in **600 ms** wall |

## Findings surfaced by the benchmark

1. **Quarantine runner deadlock (fixed in this change).** `workers/ingestion/runner.py::run_parse` called `proc.join(timeout)` *before* draining the result `mp.Queue`. A pickled `ParseReport` larger than the OS pipe buffer (~64 KiB — roughly a >400-row CSV) can only be delivered while the parent is reading, so the child never exited and every such import surfaced as a false `PARSE_TIMEOUT` quarantine after 60 s. Measured: 600 rows → timed_out=True, 0 records (before); 600 rows → 1,200 records in 0.2 s (after). Fix drains the queue while joining; `parse_timeout_s` kill semantics unchanged. Regression test: `test_large_report_crosses_the_pipe`.

2. **Import executes on the request path.** During the 600 ms import, the concurrent `/healthz` probe waited **595 ms** (n=1) — the synchronous parse+insert starves the single-uvicorn event loop for the import's duration. Within §23.1 tolerance (mutation ack < 1 s), but worth noting: at larger import sizes the whole API stalls, not just the requester. Candidate follow-up: move `artifactImport` execution to the run queue or a worker thread so healthz/reads stay live.

## Limits

- Single-machine, loopback HTTP — no network loss, no second client contention beyond the probes listed.
- FTS corpus is 1,200 single-cell chunks; embedding search is not implemented and not measured.
- The worker job is a CPU-bound subprocess burn (~10 s); memory/IO-heavy engine profiles are not part of this run.
