# Scientific workflow operations

Researchers, lab operators, and scientific reviewers use task contracts,
versioned candidates, approved plans, manual results, and evaluator-derived
closeout. Follow [experiments and evidence](../usage/experiments-and-evidence.md)
for the screen-by-screen workflow. This guide explains operational gates and
how to diagnose blocked scientific actions.

A supported software closeout or successfully executed calculation is not an
automatic scientific validation claim. Inspect data provenance, method, units,
uncertainty, source rights, and real review evidence.

## Contracts and candidate revisions

Choose a task mode and target kind, record baseline/reference requirements, and
freeze a complete success contract before approval-dependent work. Required
metrics need explicit identity, unit, method, and acceptance criteria. Unknown
inputs remain unresolved; a functional match cannot infer a reference recipe
or material identity.

Candidate edits create revisions. Approvals bind exact revisions/digests; when
inputs change, rereview the current version instead of reusing an older approval.
Registry materials/products and task candidates have distinct identities and
lineage. See [materials and candidates](../usage/materials-and-candidates.md).

## Experiment plans and manual execution

Create a task-bound plan with explicit method and requirements, submit it, and
obtain review from an authorized human with `approve_experiment`. Agents cannot
approve experiments. An approved manual packet retains its provenance; the
application's packet export is JSON rather than a delivered PDF/print system.

Open an execution against the selected plan, add samples/batches, record the
actual observations, and close the execution. These are manual laboratory
records. No instrument-control API or invented equipment catalog exists.
Unspecified equipment/method details remain a blocker for real execution.

Measurements preserve original values, units, conditions, sample lineage, and
review state. Human measurement review uses `review_measurement`. Correct an
observation by adding an amendment with a reason; do not replace historical
values. Applicability decisions are separate from whether the measurement was
recorded or reviewed.

## Unit handling and closeout

Conversions use an explicit whitelist. Missing/unsupported conversions produce
inconclusive checks. Mass/volume conversion requires a valid density path;
absolute-temperature conversion is not silently inferred.

At closeout, move the task to review and inspect the server-derived evaluation
packet. Supported success requires its frozen contract, required metrics,
evaluated hard constraints, and applicable reviewed measurement evidence.
Unknown check kinds remain `not_evaluated` and block success. A client-supplied
packet cannot override the evaluator's bound record. Human review finalizes the
closure against the exact contract revision.

When closeout is blocked, resolve the reported scientific/evidence gap. Do not
weaken the contract solely to manufacture a passing result.

## Calculations and optional adapters

| Lane | Prerequisites and interpretation |
|---|---|
| SMILES descriptors | Native RDKit or pinned descriptor image; computed structural descriptors, not a laboratory measurement |
| Optimization | Explicit optimization profile and BayBE image; campaign target must match a frozen metric's ID/unit/method/type |
| Quantum | Quantum profile and pinned QCEngine/xtb image; missing parameters block execution |
| Materials/thermo | Materials profile and pinned thermo image; constrained screening with declared assumptions |
| Analytical ingest/comparison | Supported JCAMP-DX or CSV-XY records; similarity is scoped and does not establish composition or identity |
| Molecular design/retrosynthesis | Explicit profile and pinned REINVENT/AiZynthFinder runtime/model assets; proposals require independent review |
| Polymer atomistic pilot | Separate RadonPy/LAMMPS environment, explicit repeat/end caps, and bounded protocol; output remains computational |

See [engine operations](model-ops.md) for image builds and isolation, and
[polymer simulations](polymer-simulation.md) for pilot eligibility and resumption.
Input/engine failures must produce typed blocked/failed states rather than
invented parameters or successful-looking outputs.

Optimization campaign input is its `spec` object, not an entire fixture-file
envelope. Independent checks review engine proposals against the frozen
constraints. A recommendation is not an approved experiment.

## Operational checks

Confirm the capability, exact task/revision, profile, runtime/image version,
resource budget, and persisted engine error before retrying. Closed/cancelled
tasks retain results but reject new calculations. Local calculation execution
is bounded and idempotent; a retry with changed inputs needs a new intended
operation rather than an identifier collision.

Science adapter fixtures and native pilot evidence are historical execution
records under `docs/execution` and `docs/research`. They must not be relabeled as
qualified material properties or physical laboratory outcomes. The generated
[interface reference](../reference/README.md) identifies current operation names
and inputs without duplicating the complete schema here.
