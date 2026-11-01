# Projects and research tasks

Projects group related research. A task binds a question to versioned success criteria, candidate revisions, experiments, sources and a reviewed decision. Use this workflow when you need a traceable scientific record rather than a private freeform note.

Read [Chemistry basics](chemistry-basics.md) for the question, hypothesis, baseline and success-criteria distinctions, or begin with [A guided first research exercise](guided-first-research.md).

## Create a project and task

1. Open **Projects** and select **New project**.
2. Enter **project name**. Description and a custom **project slug** are optional; the app generates the slug when you leave it blank.
3. Select **Create project**, then open the project and choose **New research task**.
4. Enter **task title**. It becomes the starting research goal unless you provide **Research goal (optional)**.
5. Select a mode, provide the context you have, and choose **Create task**.

You can also start a research task from Home. **Organize in a project** is optional there; the default is **Research inbox - organize automatically**. A draft can preserve missing scientific context as unresolved input.

| UI mode | Stored mode | Context |
| --- | --- | --- |
| **Explore** | `discover` | Choose molecule, material, formulation or Not sure yet |
| **Improve** | `improve` | An accepted baseline formulation revision and the variation scope |
| **Match** | `match_reference` | A reference product and performance, analytical, or combined matching scope |

**Not sure yet** preserves an unknown target. A Match task does not recover a reference product's undisclosed composition. See [Materials and candidates](materials-and-candidates.md).

## Navigate a task

The workspace header shows the question, workflow status, selected criteria revision, relevant evidence gaps and a suggested next action. **Start task** moves a draft into active research when the backend permits it. **Resume task** is available for a paused task.

| Section | Contents |
| --- | --- |
| **Overview** | Readable success criteria and intentional criteria editing |
| **Research** | Task-bound research sessions, questions and provider turns |
| **Candidates** | Hypotheses, exact scientific revisions, comparisons and review |
| **Experiments** | Plans, Calculations and Results |
| **Sources** | Claims and Source quality |
| **Review** | Review & decide, Report and Decision history |
| **Tools** | Run history, Datasets, Training, Models, Evaluations, Optimization and Reference analysis |

Task navigation is recorded in `/tasks/:taskId/:group?view=...`. Refresh, back and direct links restore the section. Optimization and Reference analysis depend on the task having those objects. Their visibility does not install an engine.

## Define success criteria

From **Overview**, choose **Define success criteria** or **Edit criteria**. Record explicit metrics, target values, comparison operators, units, methods, conditions, required evidence classes, hard constraints and unknowns as appropriate to the task. Preserve intentional zero values and mark dimensionless quantities explicitly.

Select **save draft**. Confirm the save indicator and resolve field errors before continuing. Select **freeze contract** only after the saved draft represents the criteria you intend to evaluate. The freeze button is unavailable while edits remain unsaved or no saved draft exists.

Freezing binds a revision for evaluation. Later changes create a new revision; they do not rewrite the old frozen record. The editor exposes earlier revisions for read-only inspection. The current task header and Overview summary refresh after a confirmed criteria save or freeze.

Unsaved criteria edits survive section changes during the current app session through a per-task pending form store. The browser warns before closing a dirty page. This is not a durable server save or a general guarantee of recovery after closing the browser. See [Notebooks and editing](notebooks-and-editing.md) for the stronger notebook-specific recovery behavior.

## Build evidence against the exact revision

Propose and review a candidate, then create an experiment plan bound to that candidate revision and the agreed contract revision. Record actual execution, samples, batches and measurements. Review measurement applicability instead of assuming every number is suitable for every criterion.

Local calculations can support exploration while criteria remain draft. A molecular descriptor is a computed result, not a substitute for an applicable reviewed laboratory measurement. See [Experiments and evidence](experiments-and-evidence.md).

## Research sessions and private conversations

The task's **Research** panel is part of the task workflow. Starting a session assembles task decisions, outcomes and evidence into a manifest. Record open questions; unresolved blocking questions remain visible. End a session to make its durable history available to later task sessions.

The header's app-wide **Agent** is a separate owner-private conversation system with its own history, policies, tools and scheduled work. Opening a task does not publish that private conversation into task history. See [Agent and providers](agent-and-providers.md).

## Review and close a task

Open **Review → Review & decide**. The evaluator shows the frozen criteria, metric and hard-gate results, candidate-specific findings and evidence gaps. Transition the task to `awaiting_review` when appropriate, then make the human closure decision.

For multiple accepted candidates, select the exact candidate the decision binds. Choose the outcome, add reviewer rationale where needed, and select **I confirm this closure as the human reviewer** before submitting the decision.

`supported_success` is available only when its backend evidence gates pass. A frozen contract, required metrics, evaluated hard constraints and applicable reviewed measurements matter; missing or unsupported checks block success. The evaluator suggests an outcome. It does not close the task on its own.

**Report** is a derived view of hypotheses, evidence, measurements, unknowns and limitations. **Decision history** preserves prior bound packets. A later source revocation or superseded measurement can mark a decision as needing reassessment without rewriting the signed decision record.

## Resolve common problems

| Symptom | Next action |
| --- | --- |
| Unresolved baseline, variation scope or reference | Supply real context in the relevant workflow; keep the uncertainty explicit until then |
| Freeze unavailable | Save the draft and resolve its validation findings |
| Revision conflict | Preserve edits, reload the current revision, and create a deliberate new revision |
| Closed or cancelled task rejects a calculation/edit | Inspect its stored history; use an authorized new task or revision workflow |
| Success is blocked | Review the specific metric, hard constraint, evidence status or applicability finding |
| Capability error | Ask the administrator to check the actual permission; changing UI state does not grant authority |
