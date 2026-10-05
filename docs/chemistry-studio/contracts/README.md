# Contracts and invariant coverage

`domain.schema.json` contains strict **initial interchange DTOs**, not a complete relational schema, API schema, scientific ontology, or authorization system. The implementation must expand these contracts using handoff sections 5–10 and 17–20, preserving compatibility through explicit versioning.

Every object rejects unknown properties. Stored numbers use finite decimal strings. Nulls are permitted only where absence is deliberately represented. A draft is not automatically execution-ready just because its JSON is structurally valid.

The authoritative implementation additionally checks workspace permissions; reference existence and revision identity; content-hash approvals; optimistic concurrency; units, basis and scientific applicability; state-machine transitions; immutable history; data rights; result quality; dataset leakage; resource and export policies. These cannot be proven by validating an isolated JSON object.

The included validator adds selected checks for completed fixture composition totals, frozen required metrics, failed-run acceptance, approved export prerequisites, and dataset split membership. The composition tolerance `0.000001` is explicitly **a software-fixture tolerance**, not a chosen product standard or permission to normalize real formulations. Production tolerances and test methods must be versioned and reviewed.

Fixture UUID references represent external objects in an eventual database. The files are interchange examples, not a complete foreign-key-consistent seed dataset. Build a separate coherent demo dataset that creates the referenced entities and their approvals in an isolated test workspace. It must remain visibly synthetic.

The following contracts are delivered:

- Scientific interchange: `Quantity`, `Metric`, `HardConstraint`, `SuccessContract`, `IngredientLine`, `FormulationRevision`, `ReferenceProduct`, `CandidateRevision`, `MeasuredValue`, `Measurement`, `ToolResult`, `ExportManifest`, `TrainingRun`, `DatasetSnapshot`.
- Execution graph: `workplan.schema.json`.
- Logical UX map: `design-map.schema.json`.
- Acceptance test register: `acceptance-tests.schema.json`.

Do not conflate a schema's valid `approved` state with an actual signed authorization; only application checks against a trusted, current approval record can establish that. Similarly, `fixture_only: false` is not evidence that a value was measured.
