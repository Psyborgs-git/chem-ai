# Graphical app and UX redesign verification

This pass replaces the prior navigation-heavy working surface with a direct
Home calculator, illustrated intent choices, focused creation sheets, a
workspace finder, a compact research workbench and contextual lab forms.
The product rules and research references are in `docs/design/UX_SPEC.md`.

## Actual local experiment

The installed RDKit engine calculated ethanol from `CCO` through the Home
form, using one structure field and one submit activation. The actual output
was C2H6O, molecular weight 46.069 g/mol and hydrogen-bond donors/acceptors 1/1.
The browser displayed RDKit's persisted SVG molecular graph. Opening the full
result and reloading retained the same saved run and values. This was a
computational experiment; no physical laboratory experiment was performed.

Title-only Explore research creation filed a real draft in Research inbox,
then one header Start action activated it. Name-only project creation
produced a real project and retained it through reload.

## Visual and interaction inspection

Desktop 1440px and mobile 390px screenshots cover Home, research creation,
finder, projects, workbench, plans, inline calculation, saved result and dark
result views. All 18 captured page states had matching viewport and document
widths and no browser exceptions. Evidence is in the ignored local directory
`.runtime/evidence/ux-redesign/`, with measurements in `checks.json`.

The lab inspection also verified blank actual readings, supported zero,
editable carried method/unit, the exact plan-bound frozen metric, and explicit
clears that stay clear. Evidence is in
`.runtime/evidence/ux-lab-measurements.json`. Synthetic audit records are
visibly labeled; their values are not scientific evidence.

## Verification records

Fresh check logs for this pass are under `.runtime/evidence/`:

- `ux-unit-tests.log`: frontend component and interaction tests.
- `ux-contract-tests.log`: contract, schema and Relay-boundary checks.
- `ux-lint-types.log`: lint and strict Python/TypeScript checks.
- `ux-backend-workflows.log`: new quick-calculation/inbox backend tests.
- `browser-ux-tests.log`: complete browser regression suite.

Fresh results on 29 October 2026:

| Check | Result |
|---|---|
| Browser journeys | All 59 distinct journeys verified: 58 passed in the full run; the remaining Home label assertion was updated to the new review grouping and passed in a focused rerun. No application code changed for that final assertion repair. |
| Frontend tests | 101 passed across 25 files |
| New backend workflows | 14 passed |
| Actual RDKit / SVG engine | 7 passed |
| Contracts and design map | 29 passed; exported schema, contract mirrors and Relay boundaries clean |
| Private development paths | 3 passed |
| Strict typing and build | Python 232 files clean; TypeScript and production build passed |

The initial run caught a client rule that prevented incomplete draft plans
from being saved; this was corrected and the real browser plan journey passed.
Saved criteria now refresh the workbench, and saved Home calculations refresh
Recent research without a page reload. The final focused browser result is
in `browser-ux-home-rerun.log`.

No user study was performed. The action/control counts establish interaction
changes; they do not establish task-completion time or usability for every
researcher. Existing explicit scientific review and approval remain required.
