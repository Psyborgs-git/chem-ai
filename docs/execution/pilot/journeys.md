# Pilot journeys — execution evidence (CS-0504)

Three browser journeys run end-to-end against the real FastAPI backend
+ PostgreSQL (`studio_e2e` database, migrations applied) + production
Vite build. All data is **synthetic fixture** — these journeys prove
the software workflow, never scientific validity.

Spec mapping: §25.2/§25.3/§25.4 → AT-0504-1/2/3.

## Journey A — improve (`at-0504.spec.ts` journey 1)

1. `improve` task with `baselineRevisionId` + `variationScope` mode
   inputs → frozen contract (required metric `metric.synthetic-performance`,
   bound `>= 5 dimensionless`).
2. Candidate → plan draft → submit → human approve → manual execution
   open → batch → aliquot → measurement `7` attributed to the metric →
   measurement review `accepted`.
3. `active → awaiting_review` → human close `supported_success`.
   The stored closure packet is evaluator-derived (contract revision A,
   evidence ids, `fixtureOnly: true`,
   `scientificValidation: not_validated`).
4. **New contract revision B frozen** (tighter bound `>= 9`) —
   `taskDecisions` still shows the closure bound to **revision A**;
   the signed packet is not rewritten.
5. New research session → manifest items include the recorded
   `decision (closure)` — history persists into new context.
6. UI: `decisions` tab lists the closure with its bound contract
   revision and signed packet; `report` tab compiles the task report
   (hypotheses, measurements, unknowns, review scope, limitations).

## Journey B — match reference (`at-0504.spec.ts` journey 2)

1. `referenceProductCreate` with `compositionKnowledge: "unknown"` —
   a purchased reference, no recipe.
2. `match_reference` task with `matchScope: "functional"` → contract
   with a required functional metric **and** an optional analytical
   (`spectral similarity`) metric.
3. Functional measurement accepted → close `supported_success`.
4. Report shows the functional metric `met`, the optional analytical
   metric inconclusive (never measured), and the mode limitation
   *"functional match says nothing about composition or identity"*.
5. Asserted negatively: no "same molecule", "exact identity", or
   "recipe recovered" text appears anywhere on the report — exact
   composition recovery is a separate research hypothesis, never the
   default interpretation of a functional match (§11.3).

## Journey C — discover (`at-0504.spec.ts` journey 3)

1. `discover` task → frozen contract → plan → execution → measurement
   recorded (misses the bound).
2. Failure recorded honestly: `actualsRecord` with observations
   "emulsion broke — candidate failed at temperature" + deviation
   "phase separation observed at 40C"; execution closed `stopped`.
3. `sessionStart` → the next session's manifest contains an
   `experiment_outcome` item carrying the failure cause — permitted
   evidence and the failure inform the task instead of disappearing.
4. UI: research tab renders the manifest item (`data-kind=
   experiment_outcome`) with the observations text.

## What these journeys deliberately do NOT claim

- No recipe/identity inference from a functional match.
- No scientific validation — every packet is `fixtureOnly`.
- No equipment control — executions are manual records.
- Contract success under a superseded revision does not retroactively
  bless or rewrite an earlier signed closure.
