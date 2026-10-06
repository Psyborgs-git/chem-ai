# Release matrix — Chemistry Studio pilot release (CS-1104)

**Release state: verified pilot + hardening — not a finished
scientific platform.** All workflows run on synthetic fixture data;
`scientificStatus` is `not_validated` everywhere. Live compute,
training-at-scale, ELN, and cloud egress lanes are implemented as
mechanism-only or remain blocked by their named unknowns
(`unknowns-register.md`).

Evidence rule (AT-1104-1): every row traces to a merged commit/PR plus
a ticket evidence doc (`docs/execution/tickets/CS-*.md`) whose
"Acceptance"/"验证命令与结果" sections record executed commands, exit
codes, and test names. AT verdicts are the ticket's recorded verdicts;
where a doc's AT evidence is thin this matrix says so.

## 1. Component matrix (handoff §27)

| Component | Version / image | Platform | Evidence status | Limitations | Blocked input |
|---|---|---|---|---|---|
| PostgreSQL persistence | 16.10-alpine container (dev) | loopback :54329 | **live** — `make migrate` → head; populated-upgrade test (AT-1102-1) | single-host, no replication | — |
| Artifact vault | filesystem, content-addressed | `STUDIO_VAULT_ROOT` | **live** — checksum-verified blobs, containment-tested | no app-level at-rest encryption (OS volume encryption assumed) | — |
| Queue | Procrastinate primitives, in-process runner | — | **live** (defer/job-id/reconcile semantics) | production Psycopg connector + daemon worker not installed | — |
| RDKit engine | `chem-studio-rdkit:2026.3.6` | linux/amd64 container | **live** — real descriptor runs, `--network none` | `descriptor` evidence class only; native wheel absent on some hosts | image must be built locally |
| llama.cpp runtime | `ghcr.io/ggml-org/llama.cpp:server` + `gemma-2b-it` (sha256-pinned) | container + `chem-models` volume | **live** — handshake + turns verified | 2B fixture model ≠ chemistry assistant; container egress not denied | U13 (model/license choice) |
| Parsers (doc/pdf/xlsx/csv/jcamp-dx/csv-xy) | repo workers | subprocess quarantine | **live** — hostile-input suite green | text-layer only; OCR flagged not faked; heuristic injection flags | — |
| BayBE optimizer | `chem-studio-baybe:0.15.0-v1` | container | **engine_smoke_passed**, fixture_only | independent constraint re-check; no scientific validation | profile flag + image |
| Chemprop property models | `chem-studio-chemprop:2.3.1-v1` | container | **fixture_only**; not_ready for real endpoints | requires endpoint data + validation | U02/U14 |
| QCEngine/xtb | `chem-studio-qcengine:0.51.0-v1` | container | **available_tested** (xtb template) | approved-template subset; missing parameters → blocked | U05-class inputs |
| Materials (thermo/UNIFAC-LLE) | `chem-studio-materials:0.6.1-v1` | container | **fixture_only** synthetic screen | task-justified scope only | — |
| Analytical adapter | repo service (`workers/chemistry` analytical) | service-level | **fixture** | scoped similarity; no identity claims | — |
| REINVENT design | `chem-studio-reinvent:4.8-v1` | container | **adapter verified**, synthetic | heavy image; design ≠ synthesis proof | — |
| AiZynthFinder | `chem-studio-aizynthfinder:4.4.1-v1` | container | **adapter verified**, synthetic | ≥8 GiB envelope; retrosynthesis ≠ verified route | — |
| SFT trainer | `chem-studio-sft:0.1.0-v5` | container | **mechanism live** on fixture corpus | real training needs hardware/model (U08/U13) | U08, U13 |
| RL trainer | `chem-studio-rl:0.1.0-v1` | container | **mechanism live** — real optimizer steps, checkpoint round-trip, budget stop | reward climb on pico backbone ≠ scientific gain | U08 |
| Evaluation + promotion gate | repo services (CS-0803) | service-level | **live** — hidden labels double-gated, matched baseline required | thresholds synthetic until U14 | U14 |
| Export broker | `infra/cloud/broker` | in-process | **mechanism live** — permit gate, receipts, revoke stops transfer | zero providers registered | U11 |
| Confidential cloud adapter | `infra/cloud/providers` | in-process double | **not_configured** — attestation gate verified against double only | no approved provider/account/region | U08, U09, U11 |
| ELN bridge (eLabFTW) | — | — | **blocked** — CS-0506 not implemented | optional integration | U16 |

## 2. Per-ticket verification matrix (definition-of-done, §27)

`landed` = merge commit / PR on `main`. ATs: verdicts recorded in the
ticket evidence doc — all green unless noted. Capability label = the
ticket's own honest status, condensed.

| Ticket | Phase | Landed | Evidence doc | ATs | Capability status |
|---|---|---|---|---|---|
| CS-0001 | P00 | 713fb88 (initial import) | CS-0001.md | AT-0001-1/2/3 ✔ (audit) | baseline audit; fixture: 20/20 spec fixtures; all lanes blocked (expected) |
| CS-0002 | P00 | 713fb88 | CS-0002.md | AT-0002-1/2/3 ✔ | live: health/capability endpoints; blocked: optional profiles/engines then |
| CS-0003 | P00 | 713fb88 | CS-0003.md | AT-0003-1/2/3 ✔ | live: Makefile contract + CI policy + contracts; fixture: 21 synthetic fixtures |
| CS-0101 | P01 | 713fb88 | CS-0101.md | AT-0101-1/2/3 ✔ | live: persistence + revision invariants in Postgres |
| CS-0102 | P01 | 713fb88 | CS-0102.md | AT-0102-1/2/3 ✔ | live: sessions/capabilities/loopback; blocked: LAN/team (U07), DB-level RLS later |
| CS-0103 | P01 | 713fb88 | CS-0103.md | AT-0103-1/2/3 ✔ | live: vault + authz on every transfer; gap: no at-rest encryption |
| CS-0104 | P01 | 713fb88 | CS-0104.md | AT-0104-1/2/3 ✔ | live: GraphQL/Relay foundation, keyset cursors |
| CS-0105 | P01 | 713fb88 | CS-0105.md | AT-0105-1/2/3 ✔ | live: idempotent commands, approvals, outbox |
| CS-0201 | P02 | 713fb88 | CS-0201.md | AT-0201-1/2/3 ✔ | live: §7.1 state machine + contract freeze/supersede; evidence gate human-only |
| CS-0202 | P02 | 713fb88 | CS-0202.md | AT-0202-1/2/3 ✔ | live: exact-decimal quantities, unit whitelist |
| CS-0203 | P02 | 713fb88 | CS-0203.md | AT-0203-1/2/3 ✔ | live: materials/grades/lots/reference registry |
| CS-0204 | P02 | 713fb88 | CS-0204.md | AT-0204-1/2/3 ✔ | live: formulation families/revisions/candidates |
| CS-0205 | P02 | 713fb88 | CS-0205.md | AT-0205-1/2/3 ✔ | live: token system + design map contract test + e2e harness |
| CS-0206 | P02 | 713fb88 | CS-0206.md | AT-0206-1/2/3 ✔ | live: task workspace UI (browse/create/contract/candidates) |
| CS-0301 | P03 | 713fb88 | CS-0301.md | AT-0301-1/2/3 ✔ | live: quarantined parsing; OCR/active-content flagged not faked |
| CS-0302 | P03 | 713fb88 | CS-0302.md | AT-0302-1/2/3 ✔ | live: record review (steward) → claim promotion (reviewer) |
| CS-0303 | P03 | 713fb88 | CS-0303.md | AT-0303-1/2/3 ✔ | live: scoped lexical retrieval; no embeddings/cloud |
| CS-0304 | P03 | 713fb88 | CS-0304.md | AT-0304-1/2/3 ✔ | live: durable task memory, session manifests |
| CS-0305 | P03 | 713fb88 | CS-0305.md | AT-0305-1/2/3 ✔ | live: revocation cascade + quality report; dataset/model fields empty then (registry landed CS-0802) |
| CS-0401 | P04 | 713fb88 | CS-0401.md | AT-0401-1/2/3 ✔ | live: queue + authoritative runs; in-process runner; no background scheduler |
| CS-0402 | P04 | 713fb88 | CS-0402.md | AT-0402-1/2/3 ✔ | live: admission/budgets; typed `blocked` with missing dims |
| CS-0403 | P04 | 713fb88 | CS-0403.md | AT-0403-1/2/3 ✔ | live: isolated execution + cancel + run cache; subprocess can't deny network (R1) |
| CS-0404 | P04 | 713fb88 | CS-0404.md | AT-0404-1/2/3 ✔ | live: real RDKit container; deterministic verifier produces decision *input* |
| CS-0405 | P04 | 713fb88 | CS-0405.md | AT-0405-1/2/3 ✔ | live: llama.cpp container + pinned GGUF; degrades to `model_unavailable` honestly |
| CS-0406 | P04 | 713fb88 | CS-0406.md | AT-0406-1/2/3 ✔ | live: message-level SSE streams (not token-level); outbox-authoritative |
| CS-0501 | P05 | 713fb88 | CS-0501.md | AT-0501-1/2/3 + cap gate ✔ | live: immutable plans + approval packets; U04/U05 open |
| CS-0502 | P05 | 713fb88 | CS-0502.md | AT-0502-1/2/3 + cap gate ✔ | live: manual executions, immutable measurements/amendments |
| CS-0503 | P05 | 713fb88 | CS-0503.md | AT-0503-1/2/3 ✔ | live: gate-first evaluator; server-derived closure packets |
| CS-0504 | P05 | 713fb88 | CS-0504.md | AT-0504-1/2/3 ✔ (browser journeys) | live: 3 pilot journeys on real backend+PG+prod build, all fixture |
| CS-0505 | P05 | 998c56a (P05 closeout) | CS-0505.md | AT-0505-1/2/3 ✔ | live: backup/restore + egress check + generated pilot gate; no backup encryption |
| **CS-0506** | P05 | — | none | AT-0506-* not run | **blocked — U16** (no ELN instance/credentials/ownership; optional integration; never started) |
| CS-0601 | P06 | 998c56a | CS-0601.md | AT-0601-1/2/3 ✔ | live: dataset snapshots + eligibility; fixture manifests `not_validated` |
| CS-0602 | P06 | 998c56a | CS-0602.md | AT-0602-1/2/3 ✔ | live: group-aware leakage-safe splits + baseline eval; fixture |
| CS-0603 | P06 | PR #1 (71bc161) | CS-0603.md | AT-0603-1/2/3 ✔ | engine_smoke_passed / fixture_only: BayBE container + independent constraint checks |
| CS-0604 | P06 | PR #2 (962b8b8) | CS-0604.md | AT-0604-1/2/3 ✔ | fixture_only / not_ready: property models + calibration + applicability |
| CS-0701 | P07 | PR #3 (1410c15) | CS-0701.md | AT-0701-1/2/3 ✔ | xtb `available_tested`; polymer/missing params → typed blocked; quantum profile |
| CS-0702 | P07 | PR #5 (dc0dbe1) | CS-0702.md | AT-0702-1/2/3 ✔ | fixture_only synthetic UNIFAC-LLE screen; task-justified (optional adapter) |
| CS-0703 | P07 | PR #4 (7537a67) | CS-0703.md | AT-0703-1/2/3 ✔ | fixture: jcamp-dx/csv-xy ingest + scoped similarity + reference-analysis UI |
| CS-0801 | P08 | PR #6 (60d3bf4) | CS-0801.md | AT-0801-1/2/3 ✔ | live mechanism: SFT dataset builder + isolated trainer lifecycle; fixture corpus |
| CS-0802 | P08 | PR #7 (1f9f66d) | CS-0802.md | AT-0802-1/2/3 ✔ | live: model registry, isolated load, atomic serving pointer, rollback |
| CS-0803 | P08 | PR #8 (a9b90f6) | CS-0803.md | AT-0803-1/2/3 ✔ | live: hidden-label eval + matched-baseline promotion gate, human release |
| CS-0901 | P09 | PR #9 (336c8b6) | CS-0901.md | AT-0901-1/2/3 ✔ | live (worker layer): typed tools, replay provenance, hard budgets, gate-eligible rewards |
| CS-0902 | P09 | PR #11 (2cb5ff2) | CS-0902.md | AT-0902-1/2/3 ✔ | live: RL trainer image, optimizer steps, checkpoint/cancel/resume; fixture_only data |
| CS-0903 | P09 | PR #10 (5f3afa9) | CS-0903.md | AT-0903-1/2/3 ✔ | adapters verified: REINVENT + AiZynthFinder; synthetic; heavy images gated |
| CS-1001 | P10 | PR #12 (5df0b1a) | CS-1001.md | AT-1001-1/2/3 ✔ | live: infeasibility + fallback decision reports; export stays not_configured |
| CS-1002 | P10 | PR #15 (85484da) | CS-1002.md | AT-1002-1/2/3 ✔ | live mechanism: minimal transformed payload + disclosure review; no live egress |
| CS-1003 | P10 | PR #18 (50142ba) | CS-1003.md | AT-1003-1/2/3 ✔ | live broker mechanics vs in-process double; PROVIDERS empty → not_configured |
| CS-1004 | P10 | PR #16 (2581dbb) | CS-1004.md | AT-1004-1/2/3 ✔ | adapter skeleton verified vs double; **not_configured** (U08/U09/U11) |
| CS-1101 | P11 | PR #17 (d778c3a) | CS-1101.md | AT-1101-1/2/3 ✔ (93 attack tests green; 8 defects fixed) | verified: residual threats R1–R12 disclosed |
| CS-1102 | P11 | PR #14 (3b6b882) | CS-1102.md | AT-1102-1/2/3 ✔ (4/4 integration) | verified: populated upgrade, kill-safe migration, fresh restore, retention inventory |
| CS-1103 | P11 | PR #13 (31b97f3) | CS-1103.md | AT-1103-1/2/3 ✔ | measured: benchmark vs §23.1 PASS; a11y e2e green; CI timeout caps |
| CS-1104 | P11 | this PR | CS-1104.md | AT-1104-1/2/3 — see doc | this matrix + runbooks + fresh-operator repro |

Merge-order note: PR numbers ≠ merge order — several branches were
stacked and landed in dependency order. Actual merge sequence:
`#1 #2 #3 #5 #4 #6 #7 #8 #9 #10 #11 #12 #13 #15 #18 #14 #16 #17`
(e.g. CS-0702 #5 landed before CS-0703 #4; CS-1003 #18 landed before
CS-1102 #14 — CS-1101 #17's review baseline covered CS-1003's infra
layer while its domain layer landed last).

## 3. Aggregate verification evidence (current head)

| Suite | Command | Scale |
|---|---|---|
| unit+contracts+lint | `make verify-core` | deterministic, no GPU/net/lab |
| backend tests | `pytest services/studio-api/tests tests -m 'not engine'` | 1,055 collected, 61 engine-marked deselected |
| web unit | `pnpm --filter studio-web test` | 18 tests / 8 files |
| e2e browser | `make test-e2e` | 24 journeys across 11 specs; fresh-DB run currently 21 pass / 3 fail — see known issues |
| security | `make test-security` | adversarial suite (CS-1101) |
| performance | `pytest tests/performance/` | measured report `docs/execution/benchmarks/CS-1103-report.md` — all §23.1 targets PASS |
| recovery | `make backup-test` + `recovery_check.py` | 12-check integrity validation |

## 4. Known issues / thin evidence (honest)

- **Early-phase tickets (CS-0001…CS-0504, CS-0505/0601/0602)** landed in
  two squash commits (713fb88, 998c56a) without per-ticket PRs — VCS was
  initialized mid-flight (CS-0001 records greenfield). Their evidence
  docs are detailed; the per-ticket PR trail a release auditor would
  want does not exist for them.
- **`make seed-demo` is blocked** — the synthetic demo loader was never
  written; data entry is via UI/GraphQL. Documented, not papered over.
- **RLS at the database layer** is a defense-in-depth item; scope
  enforcement is service-layer today (CS-0102 limitation).
- **Import runs on the request path** — large imports stall the single
  uvicorn loop for the parse duration (CS-1103 finding 2).
- **Backups carry revoked bytes** by design; no purge policy exists
  (recovery.md §4).
- **`make test-e2e` spec-ordering defect (found in CS-1104 repro, reported
  not fixed):** `tests/e2e/at-1103.spec.ts` signs in as `e2e-1103-owner`,
  but every earlier spec uses `e2e-owner` and `/api/auth/setup` refuses a
  second owner — on a fresh `studio_e2e` DB the full suite fails all 3
  at-1103 specs at login. `at-1103` passes standalone
  (`playwright test at-1103`); core journeys (at-0504 et al.) pass in the
  full run. Fix = align the helper to `e2e-owner` — a test change
  deliberately left out of this docs-only ticket.
- **`infra/local/pilot_gate.py` reason strings are stale:** the
  regenerated `docs/operations/pilot-gate.md` still says `not implemented
  (P06…)` for BayBE/training/RL rows when those capabilities exist but
  their environment prerequisites (engine images, `profile_*` flags,
  hardware) are absent. Status detection is honest; the reason text is
  not. Flagged, not edited — the report is generated output.
- Residual security risks R1–R12: see
  `docs/execution/security/cs1101-residual-threat-register.md`.
- Benchmark machine/results: `docs/execution/benchmarks/cs1103-latest.json`.

## 5. Unresolved inputs and next unblocked work

- All U-codes: `unknowns-register.md`.
- **Next unblocked ticket:** none — CS-1104 is the final planned ticket.
  Continuation requires resolving unknowns (U16 eLabFTW; U08/U13
  hardware/model; U11 provider approval; U02/U03/U14 real data and
  thresholds) before new capability claims.
