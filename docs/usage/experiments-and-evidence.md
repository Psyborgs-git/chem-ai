# Experiments, measurements and evidence

Chemistry Studio records manual laboratory work and the evidence used in a reviewed task decision. It does not control instruments or operate laboratory equipment. An experiment plan, an execution record, a measurement and an evidence claim are separate records.

The evidence, control and uncertainty examples in [Chemistry basics](chemistry-basics.md) explain why those records remain distinct. The [guided first exercise](guided-first-research.md) provides an app-only starting point.

## Draft an experiment plan

Open a task's **Experiments → Plans**. The global **Lab** surface also exposes lab work. Select **Candidate to test** and **Agreed success criteria** using their exact accepted/frozen revisions.

Record **Test method**, a plan title if useful, **batch count**, acceptance criteria, hazard notes and resource needs. State requirements for unknown equipment or methods explicitly. The app does not select invented instruments or fill in an undisclosed method.

Save/create the draft plan and inspect blockers. Submit it for review. An authorized human with `approve_experiment` can approve or reject it with rationale. Agent principals cannot grant themselves this approval.

An approved plan can export an execution packet. The packet is labeled **MANUAL EXECUTION - qualified operator required; the system does not start equipment** and retains approval provenance. It is a JSON packet, not an automatic instrument job or a PDF print workflow.

## Record actual execution

Use **Experiments → Results** or the Lab results surface. Open the execution against the intended plan, then add samples and batches. Record what actually happened, including:

- Actual materials and amounts, process and conditions.
- Deviations from the approved plan.
- Observations and the operator's actual source information.

The guided **Actual process**, **Materials used**, **Deviations** and **observations** fields support ordinary capture. **Use exact actuals payload** exposes the JSON form for integrations or cases the structured rows cannot express. Select **record actuals** only after the form reflects the real execution.

**import historical record** captures a historical source and notes. It is not a newly performed experiment. Keep source provenance and the original date/method distinctions clear. Close the execution when its actual record is complete.

## Record and review measurements

Select the correct execution/sample/batch, metric, value, unit, method, conditions and source. Record failure states as failures. An instrument failure does not become a numeric zero or a passing result.

A human with `review_measurement` reviews measurements. Set applicability to the candidate/criterion deliberately. Reviewed status, applicable status and matching method/conditions serve different purposes.

For an incorrect recorded value, create an amendment and record its reason. The original measurement remains immutable; the amendment chain shows the correction. If a measurement is no longer appropriate, update its applicability through the supported action rather than editing history.

The comparison form accepts **Comparison metric name**, **Comparison comparator**, **Comparison bound** and **Comparison unit**. Use explicit dimensionless units when appropriate. **Use exact comparison metric** exposes the structured metric for advanced cases.

## Keep units and methods meaningful

The comparison layer permits explicit unit conversions from a whitelist. Unknown conversions produce an inconclusive result. Mass-to-volume needs an appropriate density path. Absolute-temperature conversion is deliberately outside this lane's automatic conversion rules.

Equivalent-looking numbers from different methods, temperatures or sample definitions are not automatically comparable. Preserve the actual recorded conditions. A calculated descriptor, published extracted claim or simulation value does not become a reviewed experimental measurement by being entered into the same workspace.

## Review imported evidence

Open **More → Imports**. **Import a stored source** expects the artifact identifier of a source already committed to the local vault. This evidence-extraction surface does not use the private Downloads file picker.

An integration first uses the staged artifact upload API: create upload, send bytes to its returned upload URL, finish the upload, then submit the resulting artifact ID. Artifact commit checks checksums and content boundaries. See [Backend and contracts](../development/backend-and-contracts.md) for integration rules.

Quarantined extraction produces proposed records and per-record findings. Ambiguous units or fields remain provisional. OCR-required pages report review needs. Archive, embedded and active-content findings are not silently ignored.

An authorized source steward accepts/rejects extracted records and can promote accepted records to evidence claims. Claim review requires human scientific review. Artifact rights default to unknown; classify rights explicitly before retrieval/export/training uses that require permission.

## Link claims and inspect source quality

Open **More → Evidence** or task **Sources → Claims** to inspect claims, provenance and locators, link them into the scientific workflow, and review them with the required capability. Claim links preserve the source behind the assertion.

**Sources → Source quality** and `/evidence/quality` show extraction/quality findings and source revocation impact. Some evidence panels are workspace-wide even when opened from a task; inspect the displayed binding before treating an item as task-specific evidence.

Revoking a source invalidates its future use and marks affected derived decisions/context for reassessment. Revocation is different from deleting the original bytes and does not rewrite signed decision packets. See [Privacy](../operations/privacy.md).

## Decide the outcome

Open **Review → Review & decide**. The evaluator reads the bound frozen contract, applicable reviewed measurements and hard constraints. `supported_success` requires its evidence gates to pass. Unknown constraint kinds remain `not_evaluated` and block success; missing data stays missing.

For multiple accepted candidates, bind the decision to the specific candidate. The backend derives the closure packet from current authoritative data. Client-supplied prose cannot manufacture an eligible closure. A human confirms and records the final decision; agents cannot close their own scientific work.

See [Projects and tasks](projects-and-tasks.md) for report/history and [Scientific operations](../operations/scientific.md) for the underlying scientific service lanes.
