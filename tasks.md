# Tasks — live ticket board

Mirror of `docs/chemistry-studio/planning/workplan.json` execution
state. Canonical DAG = workplan.json; this file records session state.

## Current ticket

CS-0002 — Pin compatible dependencies and profiles.

## Queue (next unblocked)

1. CS-0003 → CI, fixtures, Makefile command contract
2. CS-0101 → persistence/revision foundation (migrations + tests)
3. CS-0102 → auth/capabilities/loopback security
4. CS-0103 → artifact vault (needs 0101+0102)
5. CS-0104 → GraphQL Node/Relay foundation (needs 0101+0102)
6. CS-0105 → commands/approvals/outbox (needs 0101+0102)
7. CS-0202 → quantities/basis/missingness (needs 0101)
8. CS-0201 → project/task/contract lifecycle (needs 0104+0105)
9. CS-0203 → materials registry (needs 0202+0104)
10. CS-0204 → formulation/process/candidate revisions (0201+0202+0203)
11. CS-0205 → atomic UI + design map (0104+0202)
12. CS-0206 → task workspace UI (0201+0204+0205)
13. CS-0301 → ingestion quarantine (0103+0203)
14. CS-0302 → extraction review/provenance (0301+0205+0105)
15. CS-0303 → scoped retrieval + source rights (0302+0102)
16. CS-0304 → task memory/session snapshots (0201+0303)
17. CS-0305 → evidence revocation + data-quality report (0302+0303+0304)

## Done

- CS-0001 baseline — see `docs/execution/tickets/CS-0001.md`

## Blocked (unknown-gated; do not start live portions)

- CS-0405 (U08 hardware/U13 model), CS-0501 (U04 reviewers/U05 lab
  methods — implement recordkeeping, block release), CS-0604
  (U02/U14), CS-0701 (U08), CS-0702/0703 optional (U03/U05/U14),
  CS-0801/0803 (U08/U13/U14), CS-0902/0903 (U08/U13/U14), CS-1004
  optional (U08/U09/U11), CS-0506 optional (U16).

Per D09, blocked items gate only their dependent live action; all
deterministic/synthetic engineering proceeds.
