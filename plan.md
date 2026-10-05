# Plan — Chemistry Studio execution

This is a progress tracker against `docs/chemistry-studio/planning/
workplan.json` (the canonical DAG), not a competing plan. Status values:
`done` (evidence recorded), `in_progress`, `blocked:<U##>`, `pending`.

## P00 — Baseline and dependency decisions

| Ticket | Title | Status | Evidence |
|---|---|---|---|
| CS-0001 | Inspect baseline and map repository | done | `docs/execution/tickets/CS-0001.md` |
| CS-0002 | Pin compatible dependencies and profiles | in_progress | `docs/execution/tickets/CS-0002.md` |
| CS-0003 | Create CI, fixtures and command contract | pending | |

## P01 — Contracts, persistence and security

| Ticket | Title | Status |
|---|---|---|
| CS-0101 | Canonical persistence and revision foundation | pending |
| CS-0102 | Principal capabilities and loopback security | pending |
| CS-0103 | Private artifact vault | pending |
| CS-0104 | GraphQL Node and Relay foundation | pending |
| CS-0105 | Commands, approvals base and outbox | pending |

## P02+

All later tickets `pending`; dependency order per `workplan.json`.
Blocked-capability notes (from the DAG): CS-0405 on U08/U13;
CS-0501 on U04/U05; CS-0604 on U02/U14; CS-0701 on U08; CS-0702
(optional) on U03/U05/U14; CS-0703 (optional) on U05; CS-0801/0902 on
U08/U13(/U14); CS-0803/0903 on U14/U13; CS-1004 (optional) on
U08/U09/U11; CS-0506 (optional) on U16.

## Sequencing notes

- Phase order P00 → P11 per workplan; first useful release = through
  P05. Optional integrations only after their dependencies and
  unknown-gates resolve.
- Controller-owned surfaces (migrations, contracts, global IDs,
  authorization, dependency locks, CI) are edited in this session only —
  no parallel workers assumed (environment has no delegation; work runs
  sequentially per kickoff §6).
