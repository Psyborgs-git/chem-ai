# Materials and candidate editing

Use **More → Materials & Products** for material identities, commercial grades, reference products and formulation families. Use a task's **Candidates** section to propose and review an exact scientific revision against that task's criteria.

For molecule/material/formulation distinctions and percent/basis arithmetic, start with [Chemistry basics](chemistry-basics.md). Use the [glossary](chemistry-glossary.md) when a scientific field is unfamiliar.

## Choose the right record

| Record | Meaning |
| --- | --- |
| Material identity | A defined molecule, polymer, commercial mixture, substance class or explicitly unknown material |
| Material grade | A supplier/grade-specific material description tied to an identity |
| Reference product | A product used as a comparison target, with known, partial or unknown composition |
| Formulation family | A named family of formulation revisions and related process revisions |
| Candidate | A task-bound hypothesis pointing to an exact scientific entity revision |

Unknown identity or composition stays unknown. A familiar trade name, a functional match or a similar spectrum does not authorize filling in a structure or proprietary recipe.

## Create or review identities and grades

Open the **material identities** section to search or create an identity. Select the actual kind and record identifiers and structure information you have. Structure review and evidence status remain visible. **mark structure reviewed** is a deliberate review action; it does not generate missing chemical evidence.

Under **material grades**, associate the grade with the correct identity and supplier context. Record quantity, active-content and basis information explicitly. A commercial mixture may be partly described while its full composition remains unresolved.

Use a picker to select an existing record instead of copying an identifier from a visually similar item. The UI may show readable names while GraphQL uses typed global IDs; integrations must pass the required identifier type.

## Describe a reference product

Under **reference products**, create the product record and a reference revision containing actual known facts. Record confidentiality and composition knowledge truthfully. Save the draft, review its data, then freeze the reference revision when appropriate.

For unknown or partial composition, preserve the available functional/analytical evidence without claiming recipe recovery. A Match task can compare performance or analytical profile against that reference while keeping composition unknown.

## Edit a formulation revision

Open **formulation families**, create or select a family, and open its structured revision editor. A revision can descend from a parent revision. **copy parent contents** copies the parent's available ingredient/totals fields into your new form; inspect the result and enter the intended context before saving.

For each ingredient:

1. Select the material identity when known, or preserve the explicit ingredient name if unresolved.
2. Enter the numeric amount as recorded and choose its unit.
3. For fraction/percentage units, choose the basis explicitly.
4. Record the ingredient's role when known.

Under **totals**, choose **amount basis**. Record **declared total** and any justified **tolerance**. Select **draft - may be incomplete** while information is missing. **complete - declared total enforced** asks the acceptance workflow to verify the declared total and related validation rules. The editor does not silently normalize ingredient values to force a total.

Record substrate/application context and author source. Select **save formulation draft** and read the saved revision/status plus validation findings. Saving an incomplete draft is different from accepting a scientifically complete recipe. A malformed numeric quantity, incompatible basis or missing requirement remains visible.

To change an accepted or historical recipe, derive a new revision instead of changing the original. **diff vs parent** compares it with its parent. **accept revision** is a separate authorized action after inspecting the stored contents and findings. A parent relationship identifies lineage; it is not approval of the new revision.

## Record a process revision

Within the formulation family, choose **new process revision**. Enter each **step action** and its optional notes. **add step** and **remove step** adjust the ordered procedure. Step order is part of the scientific content and changes its signature.

Select **save process draft**, confirm **process draft saved**, and inspect the stored process revision. **accept process revision** is a separate review action. A recipe and its procedure are independent revision bindings; use the actual intended pair in a candidate or experiment rather than assuming the newest process belongs to an older recipe.

## Propose a task candidate

Open the task's **Candidates** section. Choose the actual entity/revision and enter the hypothesis/context requested by the proposal form. **Propose candidate (creates a draft revision)** persists a candidate in draft state. Proposals start with unassessed eligibility.

Inspect the candidate contents and, when available, its revision diff. The same exact ingredient set can be reported as a duplicate. Near-duplicate grouping is a separate operation; it is not proof that two recipes are interchangeable.

Select **submit for review**. A human reviewer can then choose **accept for research** or **reject** when authorized. Acceptance permits research on that candidate; it is not a claim that the task succeeded or that the material is safe to make or use.

An accepted candidate can be selected under **Experiments → Plans**. Bind the experiment to the exact accepted candidate revision and agreed frozen contract. Later candidate changes require their own revision and review.

## Review proposed patches

Candidate/formulation changes proposed by an agent remain proposals. Inspect the diff and provenance, then approve or reject through the human review surface. Do not treat the model's explanation as a review decision. Unknown identity, incompatible quantity basis and incomplete processing details remain blockers until resolved with actual information.

## Handle save and review errors

| Finding | What to do |
| --- | --- |
| Invalid quantity or basis | Correct the value/unit/basis using the actual source; keep unknowns explicit |
| Declared total mismatch | Reconcile ingredients or the justified total/tolerance; do not force normalization |
| Missing identity or structure | Add verified identity information or use a workflow that permits unresolved inputs |
| Stale revision/conflict | Preserve edits, load the current record and create a deliberate new revision |
| Forbidden review | Ask an authorized human reviewer; proposing a revision does not confer approval rights |
| Candidate no longer applicable | Review its exact task/contract/revision binding before planning experiments |

Continue with [Experiments and evidence](experiments-and-evidence.md) or [Projects and tasks](projects-and-tasks.md).
