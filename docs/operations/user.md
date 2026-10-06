# Runbook — daily user workflows (records, tasks, research sessions)

Audience: signed-in workspace members on the loopback deployment.
Prerequisites: `installation.md` §2–§7 done — API on `127.0.0.1:8787`,
web on `http://127.0.0.1:5173`, owner session cookie set.

Every screen below was exercised by executed e2e journeys
(`tests/e2e/at-*.spec.ts`; pilot journeys in
`docs/execution/pilot/journeys.md`). GraphQL mutation names are given
for scripting; the UI drives the same mutations.

## 1. Sign in / sign out

- **UI path:** open `http://127.0.0.1:5173` — if "Not signed in",
  run the devtools-console `fetch("/api/auth/login", …)` call from
  `installation.md` §7 and reload. "Signed in as <name>" appears on
  the home page once the cookie is set.
- **API:** `POST /api/auth/login` `{login, password}` → `studio_session`
  cookie. `POST /api/auth/logout` revokes the session row server-side.
- **Failure:** wrong credentials return a domain error, no detail
  oracle; expired sessions (12 h TTL default) simply 401 — log in again.

## 2. Projects and tasks

- `/projects` → create a project (`projectCreate`), open it.
- `/projects/:id` → create a task (`taskCreate`): mode
  `improve` | `match_reference` | `discover`; `targetKind`
  `formulation|material|molecule|unknown` — `unknown` stays unknown,
  it is never silently inferred.
- `/tasks/:taskId` workspace tabs: overview · candidates · contract ·
  research · runs · datasets · models · training · evaluations ·
  optimization · closeout · decisions · report · reference analysis.
- Task states follow §7.1: `draft → active → awaiting_review →
  closed` (closure is human-only, `tasksCloseout*` mutations).

## 3. Success contract

- Tab **contract** → draft metrics/hard constraints
  (`contractDraftCreate` / `tasksContractDraftMutation`), then
  **freeze** (`contractFreeze`). Frozen revisions are immutable —
  a tighter target is a new revision (`B`) that supersedes, never
  rewrites, the signed record (verified in pilot journey A step 4).
- A contract naming required metrics gates `supported_success` —
  without applicable reviewed measurements the evaluator refuses
  (CS-0201 evidence gate; no path fakes past it).

## 4. Candidates and revisions

- Tab **candidates** → propose (`candidatesProposeMutation` →
  submit → human review → eligibility). Formula/process revisions use
  `tasksContract`/candidate revision surfaces; patches go
  propose → human review. Exact ingredient-set dedup reports
  duplicates — near-duplicate grouping is a separate, honest
  operation, not a fuzzy guess.

## 5. Import review (evidence intake)

- **UI:** `/imports` — upload creates an artifact in the private
  vault (content-addressed, checksum-verified), then
  `importsArtifactImportMutation` runs the quarantined parse.
- **What you see:** parsed records with per-record flags —
  ambiguous units/fields are marked and stay `provisional`;
  OCR-needed pages report `REQUIRES_OCR_REVIEW`, never a fabricated
  extraction; archive/embedded/active-content threats are quarantine
  findings, not silent drops (CS-0301/CS-1101).
- **Review:** `importsRecordReviewMutation` (steward-level
  `manage_sources`) accepts/rejects records;
  `importsRecordPromoteMutation` promotes accepted records to evidence
  claims — claim review is `review_science`, human-only.
- **Rights:** artifact `rights` default `unknown` — unknown-rights
  content stays out of retrieval/eval corpora until classified
  (`exportSetClassificationMutation` on the artifact; §9.4).

## 6. Research sessions and decisions

- Tab **research** → `researchSessionStartMutation` starts a session
  whose manifest assembles prior decisions, outcomes, and evidence;
  `researchQuestionRaiseMutation` records open questions;
  `researchSessionEndMutation` ends it — history then appears in the
  *next* session's manifest (verified in journey A step 5).
- Tab **decisions** lists closure packets bound to their contract
  revision; tab **report** compiles the task report (hypotheses,
  measurements, unknowns, limitations). Reports are derived views —
  authoritative state lives in the domain records.

## 7. Evidence and quality

- `/evidence` — claims, provenance, locators.
- `/evidence/quality` — the computed-at-read data-quality report and
  source revocation (`qualitySourceRevokeMutation`, admin-side —
  see `privacy.md` §3).
- Search is lexical-only by design; there is no embedding or cloud
  call anywhere in the retrieval path.

## 8. Runs and compute

- Tab **runs** → `runsRequestMutation` asks for compute; admission
  either queues the attempt or returns a typed `blocked` with the
  missing dimensions listed (group capacity, observed dims —
  CS-0402). `runsRequestCancelMutation` requests cancellation;
  termination is *confirmed* separately — the API never claims
  children stopped on acknowledgment (§7.3).
- `/compute` shows capability/admission state; `/compute/fallback/:runId`
  shows the infeasibility/fallback decision report (CS-1001).

## Failure symptoms → first checks

| Symptom | Likely cause | Check |
|---|---|---|
| "Not signed in" persists | cookie expired / wrong origin | cookie is scoped to the origin you logged in on; re-login on `:5173` |
| Mutation returns typed `FORBIDDEN`/`CAPABILITY` error | principal lacks the capability | `admin.md` §2 — grant check |
| Import shows quarantine findings | hostile/unsupported content | expected; review findings, source stays quarantined |
| `REVISION_CONFLICT` | stale write | reload; the diff view shows both sides — never silently overwritten |
| Optimization tab disabled | profile/engine missing | `model-ops.md` §2; `STUDIO_PROFILE_OPTIMIZATION=1` + image |

## Privacy concerns

- Everything you upload lands in the local vault; nothing egresses
  (verified `no_egress_check`). Revocation semantics live in
  `privacy.md` — revoke ≠ delete.
- Reports/decisions persist verbatim — do not enter secrets you would
  not want in a backup.

## Evidence location

`docs/execution/tickets/CS-0201…CS-0504.md` (tasks, contracts,
imports, sessions, journeys); `docs/execution/pilot/journeys.md`.
