# Operations runbooks — index

Each runbook states prerequisites, exact commands or UI paths, expected
output, failure symptoms, recovery, privacy concerns, and evidence
location (handoff §26.3). Commands marked **not_configured** depend on
prerequisites that do not exist yet — they document the activation path,
not a claim of current capability.

| Runbook | Covers |
|---|---|
| `installation.md` | install, profiles, db, API+web bring-up, first sign-in, verification battery, running without a local model |
| `user.md` | sign-in, projects/tasks, contracts, candidates, import review, research sessions, evidence/quality, runs |
| `scientific.md` | experiment plans/approvals, executions, measurements + corrections, closeout evaluator, optimization + science adapters |
| `admin.md` | owner/access management, jobs/cancellation, incident response, dependency updates, observability |
| `model-ops.md` | engine image install/benchmark, model registry, SFT/RL training, evaluation + promotion gate |
| `privacy.md` | export review + egress broker, source revocation cascade, retention posture |
| `backup-restore.md` | backup, verify, restore, automated checks (CS-0505) |
| `recovery.md` | upgrades, interrupted migrations/backfills, fresh-machine restore, retention inventory (CS-1102) |
| `cloud-security.md` | confidential-cloud adapter posture + activation prerequisites (CS-1004, not_configured) |
| `pilot-gate.md` | generated capability matrix (regenerate via `infra/local/pilot_gate.py`) |

Release-level state: `docs/execution/release/release-matrix.md` +
`docs/execution/release/unknowns-register.md`.
