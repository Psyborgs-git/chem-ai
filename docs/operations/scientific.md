# Runbook — scientific workflows (plans, executions, measurements, closeout, science adapters)

Audience: lab operators, scientific reviewers, researchers.
Prerequisites: `installation.md` complete; capabilities needed per step
are listed — grants are managed in `admin.md`.

**Honesty contract:** every artifact below can carry fixture-only data.
A `supported_success` closure means the software gate passed — it is
*never* a scientific validation claim (`scientificStatus` stays
`not_validated` until real authorized data + review exist).

## 1. Experiment plans (immutable) — `/lab` → plans

- **Create:** `labPlansPlanCreateMutation` — the plan's `method` is an
  explicit requirements text; unknown equipment/methods are a stated
  blocker, never matched to an invented device catalog (U05).
- **Review/approve:** `labPlansPlanSubmitMutation` →
  `labPlansPlanReviewMutation` — requires `approve_experiment`;
  agents are excluded by the capability ceiling
  (`effective_grants` strips approval capabilities for agent
  principals — adversarially tested in CS-1101).
- **Packet export:** `labPlansPacketExportMutation` → JSON packet
  labelled MANUAL with approval provenance. No PDF/print pipeline.
- **Evidence:** `docs/execution/tickets/CS-0501.md`, e2e
  `at-0501.spec.ts`.

## 2. Executions, samples, measurements — `/lab` → results

- `labResultsExecutionOpenMutation` → `labResultsSampleAddMutation`
  → `labResultsBatchAddMutation` → `labResultsMeasurementRecordMutation`
  → `labResultsExecutionCloseMutation`. Executions are **manual
  records** — there is no instrument-control endpoint; the MANUAL
  EXECUTION label is visible on the page.
- **Measurement review:** `labResultsMeasurementReviewMutation`
  requires `review_measurement` (human; agent/viewer get FORBIDDEN —
  security-tested).
- **Corrections:** `labResultsMeasurementAmendMutation` creates an
  immutable *amendment* — the original value is never edited in place;
  the amendment chain is visible with reason+value. Applicability is
  set via `labResultsMeasurementApplicabilityMutation`.
- **Unit safety:** conversions run against an explicit whitelist;
  unlisted units return `inconclusive` — mass↔volume requires a
  density path; absolute-temperature conversion is deliberately
  excluded. No silent conversion ever happens.
- **Evidence:** `docs/execution/tickets/CS-0502.md`, e2e
  `at-0502.spec.ts`.

## 3. Task closeout (evaluator)

- Task tab **closeout** → `tasksCloseoutTransitionMutation` to
  `awaiting_review` → human `tasksCloseoutCloseMutation`.
- The stored packet is **evaluator-derived** — a client-supplied
  packet is accepted for compat but never becomes the bound record.
- Gate order (§12.2): contract frozen + non-empty required metrics +
  hard constraints evaluated (`metric`, `ingredient_absent`; unknown
  kinds → `not_evaluated` → block) + reviewed applicable measurements
  → `supported_success` eligible. Anything unproven refuses honestly.
- **Evidence:** `docs/execution/tickets/CS-0503.md`, e2e
  `at-0503.spec.ts`, journey evidence `docs/execution/pilot/journeys.md`.

## 4. Optimization campaigns — task tab `optimization`

- Server-side profile gate: API must run with
  `STUDIO_PROFILE_OPTIMIZATION=1`; the pinned BayBE image
  `chem-studio-baybe:0.15.0-v1` must exist (`model-ops.md` §2).
  Without either, `recommend` fails `ENGINE_UNAVAILABLE` — closed,
  honest.
- Create campaign via `optimizationCreateCampaignMutation` with the
  campaign **`spec` object only** (see
  `fixtures/synthetic/optimization-campaign.json` — pass its `spec`
  sub-object, not the file envelope). Spec `target` must match a
  frozen contract metric on id+unit+method+`numeric`.
- Independent constraint checks re-verify every proposal (CS-0603):
  a constraint the engine dropped is rejected by review, never
  carried silently.
- **Evidence:** `docs/execution/tickets/CS-0603.md`; smoke evidence
  `engine_smoke_passed` — fixture-only, not scientific validation.

## 5. Science adapters (profile-gated, isolated containers)

| Lane | Profile flag | Image (build in `model-ops.md`) | Status |
|---|---|---|---|
| RDKit descriptors | engines extra / container | `chem-studio-rdkit:2026.3.6` | live (container); `descriptor` evidence class only |
| Quantum (QCEngine/xtb templates) | `STUDIO_PROFILE_QUANTUM=1` | `chem-studio-qcengine:0.51.0-v1` | `available_tested` for xtb template; missing parameters → typed `blocked` |
| Materials/thermo (UNIFAC-LLE screen) | `STUDIO_PROFILE_MATERIALS=1` | `chem-studio-materials:0.6.1-v1` | fixture_only synthetic screen; task-justified |
| Analytical ingest (jcamp-dx/csv-xy) | core | `workers/chemistry` analytical service | fixture; scoped similarity, never identity claims |
| Molecular design (REINVENT) | `STUDIO_PROFILE_DESIGN=1` | `chem-studio-reinvent:4.8-v1` | adapter verified; heavy image — engine_smoke evidence |
| Retrosynthesis (AiZynthFinder) | `STUDIO_PROFILE_SYNTHESIS=1` | `chem-studio-aizynthfinder:4.4.1-v1` | adapter verified; needs ≥8 GiB container envelope |

- All adapters run under the §13.3 isolation profile (`--network
  none`, read-only rootfs, non-root, bounded resources) and report
  typed JSON `{code,message}` failures. Missing image →
  `ENGINE_UNAVAILABLE`, never a faked result.
- Analytical/reference-analysis UI: task tab **reference analysis**
  (`referenceAnalysisIngestMutation` + `referenceAnalysisCompareMutation`)
  — a functional/spectral match says nothing about composition or
  identity; the UI asserts this negatively (journey B).

## 6. What this lane will NOT do

- No recipe/identity inference from a functional match (§11.3).
- No equipment control — executions are human records.
- No scientific-success auto-close — a human reviewer closes, and the
  closure packet is bound to its contract revision permanently.
- Unknown material identity/parameters block the calculation — nothing
  fabricates force-field or structure inputs (§28).

## Failure symptoms

| Symptom | Cause | Recovery |
|---|---|---|
| `ENGINE_UNAVAILABLE` | image absent or profile flag off | `model-ops.md` §2 build; restart API with flag |
| closure blocked `not_evaluated` | unknown check kind / missing measurements | review measurements first; don't weaken the contract to pass |
| plan rejected at review | capability missing | `approve_experiment` grant — `admin.md` §2 |
| amendment rejected | concurrent review / applicability | reload — amendments are append-only |

## Evidence location

`docs/execution/tickets/CS-0501…CS-0504.md`, `CS-0404.md`,
`CS-0603.md`, `CS-0701…CS-0703.md`, `CS-0903.md`.
