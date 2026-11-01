# Chemistry Studio interaction and visual design specification

## Product job and measurable goals

A researcher arrives with a molecule, a research question, or an experiment
record. The app should make that work immediately available and retain its
context without requiring knowledge of the underlying database.

| Journey | Observed previous UI | Required new behavior |
|---|---|---|
| Calculate an existing task's molecule from Home | Two navigation activations, one structure field, then submit | One structure field and one submit directly on Home; save context automatically |
| Start a project | Name and technical slug required | Name required; generate editable slug; description optional |
| Start research | Administrative mode dropdown and several unrelated inputs | Three illustrated intent choices; show only inputs relevant to the selected intent |
| Create a plan | Eight controls shown together | Known revisions selected by name when unambiguous; method primary; optional details disclosed |
| Record a numeric measurement | Seven controls, including internal metric ID | Reading, unit, and named metric; reuse visible editable plan context; never prefill a reading |
| Resume work | Navigate through project/task lists | Recent work links and a workspace finder lead directly to the selected record |

Counts describe this app's inspected baseline, not a measured user-study outcome.
The separate approval actions required for scientific review remain intact.

## Research and how it changes the interface

- [NN/g progressive disclosure](https://www.nngroup.com/articles/progressive-disclosure/): put frequent actions first; disclose secondary controls. Closely related fields stay together, rather than being split into unnecessary pages.
- [NN/g usability heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/): recognize named records instead of recalling IDs; show system state, clear recovery, and user control. Apply to named metric selectors, visible run progress, retained drafts, and explicit cancel/change actions.
- [GOV.UK question pages](https://design-system.service.gov.uk/patterns/question-pages/): each form has a specific task, asks necessary questions, and reuses earlier answers. Apply to research intent and contextual experiment forms.
- [GOV.UK check answers](https://design-system.service.gov.uk/patterns/check-answers/): consequential actions show a readable answer summary and an explicit final action. Apply to plan review and closeout without merging human approval into record creation.
- [W3C labels](https://www.w3.org/WAI/tutorials/forms/labels/) and [instructions](https://www.w3.org/WAI/tutorials/forms/instructions/): visible persistent labels, units, and field guidance; placeholder text is supplementary.
- [GOV.UK error summary](https://design-system.service.gov.uk/components/error-summary/): explain what needs fixing, keep entered values, and associate feedback with the input.
- [W3C multi-page forms](https://www.w3.org/WAI/tutorials/forms/multi-page/): complex work uses logical stages and visible progress, while optional stages are skippable. Simple calculations remain on one screen.

## Information architecture and action hierarchy

Home is a working launch surface, with a direct molecular calculator,
illustrated entry points for research and lab work, recent work, and reviews
that actually require attention. It contains no decorative metric dashboard.

The shell groups destinations into work, reference library, and tools.
A keyboard-accessible finder searches actual projects and recent research.
Persistent account/theme controls are compact; the main content is reserved
for the user's task. Every primary control uses an action verb.

A task has a compact project breadcrumb, title, state, and goal. A visual
workflow identifies its current stage and the next authorized action.
Primary sections use user-facing labels: Overview, Research, Candidates,
Experiments, Sources, and Review. Advanced capabilities live in a Tools
disclosure. Existing deep links remain valid. IDs, hashes, and raw manifests
are inspectable in details and do not lead the page.

One primary action dominates each local decision. Secondary actions use
quieter styling. Changing context must not silently clear or rebind data.

## Concrete visual system

- Use the existing semantic light/dark palette, with navy text, blue primary
  actions, and teal accents. Evidence classes and workflow status keep
  separate colors and explicit text labels.
- Use a consistent illustrated scientific vocabulary: molecular bonds,
  sample vessels, paired formulations, and source documents. Illustrations
  identify the action; their adjacent labels provide the accessible meaning.
- Draw native vector artwork with consistent stroke, corner, and shape rules.
  Do not use unrelated stock illustrations or fake numerical charts.
- Actual calculation results display the molecule's RDKit-generated 2D
  drawing. Older results without a drawing show their exact structure text,
  not an unrelated example picture.
- A result leads with the drawing, formula, weight, and relevant counts.
  Full descriptors follow; provenance and execution details remain available
  without overwhelming the answer.
- Use a clear type hierarchy, compact operational headers, intentional
  spacing, filled action surfaces, and visible hover/focus/selected states.
  Empty states explain one useful action and use relevant artwork.
- At narrow widths, content becomes one column, actions remain reachable,
  tables scroll inside their regions, and identity columns stay visible.
  Respect reduced motion and maintain keyboard operation.

### Implementation values

| Foundation | Value |
|---|---|
| Light canvas / primary surface | `#f5f7fa` / `#ffffff` |
| Navigation / primary action / illustration accent | `#14283e` / `#245bce` / `#268b7b` |
| Typography | System sans; 14px body; 12px labels; 26–36px page titles; monospace for structure strings and technical identifiers |
| Spacing | 4, 8, 12, 16, 24 and 32px base steps |
| Corners | 8px controls, 12px records, 16px entry cards |
| Shell | 232px sidebar, 64px header, 1280px maximum content |
| Action targets | Main actions at least 44px high; compact desktop utilities 36px; mobile controls 44px |
| Layout changes | Sidebar becomes a drawer below 768px; Home launchpad stacks below 1150px; intent cards stack below 420px |
| Modal creation | Native modal dialog, Escape/backdrop/Close exits, focus containment and return, input focus on open |

Dark mode uses the same semantic token names with explicit contrast-aware
surfaces. Decorative artwork is hidden from assistive technology; persistent
text labels carry the action meaning.

## Interaction and data rules

- Quick calculation creates only organizational metadata automatically.
  It never invents a result, a lab measurement, an approval, or scientific
  eligibility. The same retry key resolves to the same task/run.
- Use existing selected project context when requested; otherwise label
  automatic organization as Quick calculations before submission.
- Keep the result inline, so calculating another structure does not require
  leaving the current screen. Opening the full saved record is optional.
- Use defaults for ordinary metadata only when visible and editable.
  Scientific readings, evidence, hazards, and approval rationales are explicit.
- Auto-select a revision only when exactly one authoritative eligible record
  exists. An explicit clear is respected. Named metric choices retain exact IDs
  internally and show their bounds and units beside the reading.
- Show progress during work, retain values on failure, and provide actionable
  recovery. Technical error codes are secondary to a plain-language message.
- Cancellation is a request until the worker confirms it. Unavailable
  capabilities explain why and do not simulate success.

## Acceptance checks

Verify the direct Home calculation with an installed engine and persisted
reload; repeat with invalid input and a simulated uncertain response.
Verify project creation without a slug, research intent-dependent fields,
direct task start, named lab metric selection, and explicit clearing.
Inspect actual populated and empty views at desktop and 390px widths.
Check the finder, disclosures, keyboard focus, dark theme, and reduced motion.
Record screenshots and action counts. Automated checks establish these
behaviors; ease of use still requires observation with representative users.

## Lab workflow measurements

The local browser check used the clearly labeled Synthetic UI audit task at
1440px and 390px. It had one accepted candidate, one frozen agreement and an
existing approved plan with a prepared sample. These are control counts and
behavior checks, not a user study or a completed physical experiment.

| Primary form | Before | After | Visible context carried forward |
|---|---:|---:|---|
| New experiment plan | 8 controls | 1 control: Test method | The sole eligible candidate and frozen agreement appear as named, changeable summaries. Name, sampling and notes are optional disclosures. |
| Numeric reading for a known plan/sample | 7 controls | 3 controls: criterion, actual value, unit | The plan method and the bound frozen metric/unit are visible; repeat details and advanced types are secondary. |

With one eligible candidate and agreement, creating a draft plan needs one
entered method and one save activation. With a known plan and sole metric,
recording a numeric reading needs one entered value and one record activation
after opening the form; the value always starts blank. Users can change the
method, criterion, unit and repeat classification explicitly.

For the reference task-to-first-reading sequence, the source-derived minimum
falls from 12 to 10 action activations and from 8 to 4 typed values for an
attributed reading. This sequence includes planning, submission, human approval,
opening the execution record, adding the actual batch/sample, and recording the
reading. It excludes prerequisite candidate/contract creation, searches,
scrolling, optional changes and measurement acceptance. That complete sequence
was not executed during the read-only measurement.

Live checks confirmed that an explicit candidate or metric clear stays clear,
an intentional zero is supported, the known method/unit remain editable, and
the actual value is never prefilled. The 390px page remained 390px wide with no
browser errors. No plan or reading was submitted by this measurement. Evidence:
`.runtime/evidence/ux-lab-measurements.json`, `ux-plan-desktop.png`,
`ux-measurement-desktop.png` and `ux-measurement-mobile.png`.

## Workbench and creation behavior

The task header keeps the project, title, goal, state and next action visible.
Start or Resume invokes the existing transition to active in one activation;
it does not approve a plan or close a task. The previous ready-task path was
Review → Closeout → Start (three activations). Review now opens closeout in one
activation instead of two. These are inspected and tested action counts.

The illustrated Scope → Candidates → Test & calculate → Review path reflects
actual recorded criteria, candidate revisions, plans and task state. A
checkmark describes a recorded checkpoint, not scientific success. The
Overview shows real metric targets, units and conditions; editing starts from
one explicit control. Technical task details remain expandable.

Project creation requires one name instead of a name and a slug. Research
creation uses illustrated Explore, Improve and Match choices. Explore visibly
defaults to Molecule and can be changed. The title becomes the initial goal
unless a detailed goal is supplied. Baseline and reference inputs appear for
the relevant intent. Tasks remain drafts after creation. Optional project
organization defaults to the explicitly labeled Research inbox; choosing a
project overrides it. No scientific observations are generated by creation.

The Home result keeps the real molecular drawing, formula, molecular weight,
and donor/acceptor count inline. Full property tables and provenance are one
optional link away. Changing the structure or its project clears the old
answer so it cannot be mistaken for the new input's result.
