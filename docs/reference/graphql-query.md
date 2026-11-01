# GraphQL query reference

[Transport, IDs, pagination and errors](graphql-overview.md). Declarations below are generated from the committed SDL, including nested mutation namespaces. Look up argument and response structures in the [type catalog](graphql-types.md).

## canManageInferenceProviders

Check whether the signed-in principal is a human workspace administrator.

```graphql
canManageInferenceProviders: Boolean!
```

Requires authentication. Returns true only for a human user with administer_workspace. A signed-in agent/service or insufficiently privileged user gets false; a missing/expired session produces an authentication error.

Return contract: [Boolean](graphql-types.md#boolean).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1320`.

## claimLinks

Read supporting/contradicting links for an accessible evidence claim.

```graphql
claimLinks(claimId: ID!): [ClaimLink!]!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [ClaimLink](graphql-types.md#claimlink).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2601`.

## computeResources

Read observed hardware/resources and admitted compute-group utilization.

```graphql
computeResources: JSON!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_REQUEST_COMPUTE`.

Return contract: [JSON](graphql-types.md#json).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2438`.

## dataQualityReport

Read evidence/import quality findings for the requested accessible scope.

```graphql
dataQualityReport(batchId: ID = null): JSON!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [JSON](graphql-types.md#json).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2357`.

## datasetSnapshotDrift

Check source or contract drift affecting a frozen dataset snapshot.

```graphql
datasetSnapshotDrift(snapshotId: ID!): JSON!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [JSON](graphql-types.md#json).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2159`.

## datasetSnapshots

Read legacy dataset snapshots and their frozen provenance/split state.

```graphql
datasetSnapshots(taskId: ID = null): [DatasetSnapshotInfo!]!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [DatasetSnapshotInfo](graphql-types.md#datasetsnapshotinfo).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2150`.

## engineCapabilities

Inspect installed/enabled engine profiles and their reported availability.

```graphql
engineCapabilities: ProfileCapabilities!
```

This capability resolver does not request a signed-in service context; loopback Host/Origin transport restrictions still apply. It reports software/hardware availability, not scientific validation. Missing optional engines are represented explicitly rather than replaced by fabricated success.

Return contract: [ProfileCapabilities](graphql-types.md#profilecapabilities).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2411`.

## evaluationRun

Read an accessible independent evaluation run and its report.

```graphql
evaluationRun(evaluationRunId: ID!): EvaluationRunInfo
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [EvaluationRunInfo](graphql-types.md#evaluationruninfo).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2283`.

## evaluationRuns

Page evaluation runs and their recorded results/status.

```graphql
evaluationRuns(modelReleaseId: ID = null, evaluationSuiteId: ID = null): [EvaluationRunInfo!]!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [EvaluationRunInfo](graphql-types.md#evaluationruninfo).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2258`.

## evaluationSuite

Read one evaluation suite’s permitted public specification.

```graphql
evaluationSuite(evaluationSuiteId: ID!): EvaluationSuiteInfo
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [EvaluationSuiteInfo](graphql-types.md#evaluationsuiteinfo).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2246`.

## evaluationSuites

Page independent evaluation-suite specifications and their freeze state.

```graphql
evaluationSuites(taskId: ID = null): [EvaluationSuiteInfo!]!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [EvaluationSuiteInfo](graphql-types.md#evaluationsuiteinfo).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2235`.

## evidenceClaims

Page evidence claims retaining source class, quality and provenance.

```graphql
evidenceClaims(kind: String = null, status: String = null, first: Int = null, after: String = null, last: Int = null, before: String = null): EvidenceClaimConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [EvidenceClaimConnection](graphql-types.md#evidenceclaimconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2557`.

## exportReview

Read an export review manifest and its current approval/classification state.

```graphql
exportReview(proposalId: ID!): JSON!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [JSON](graphql-types.md#json).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2475`.

## formulationFamilies

Page the formulation families grouping related revisions.

```graphql
formulationFamilies(search: String = null, first: Int = null, after: String = null, last: Int = null, before: String = null): FormulationFamilyConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [FormulationFamilyConnection](graphql-types.md#formulationfamilyconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1761`.

## formulationRevisions

Read formulation revisions and their quantities, basis and review state.

```graphql
formulationRevisions(familyId: ID = null, search: String = null, first: Int = null, after: String = null, last: Int = null, before: String = null): FormulationRevisionConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [FormulationRevisionConnection](graphql-types.md#formulationrevisionconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1796`.

## hardwareCapabilities

Read the detected operating system, architecture and GPU summary.

```graphql
hardwareCapabilities: HardwareCapabilities!
```

This capability resolver does not request a signed-in service context; loopback Host/Origin transport restrictions still apply. It reports software/hardware availability, not scientific validation. Missing optional engines are represented explicitly rather than replaced by fabricated success.

Return contract: [HardwareCapabilities](graphql-types.md#hardwarecapabilities).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2432`.

## importBatches

Page quarantined ingestion batches and their review state.

```graphql
importBatches(first: Int = null, after: String = null, last: Int = null, before: String = null): ImportBatchConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [ImportBatchConnection](graphql-types.md#importbatchconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2488`.

## importRecords

Page extracted records within a permitted import/review scope.

```graphql
importRecords(batchId: ID!, first: Int = null, after: String = null, last: Int = null, before: String = null): ExtractedRecordConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [ExtractedRecordConnection](graphql-types.md#extractedrecordconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2520`.

## inferenceCredentialCleanupPending

Check whether a human administrator has pending provider credential cleanup.

```graphql
inferenceCredentialCleanupPending: Boolean!
```

Requires authentication. Returns cleanup status only when ProviderService.can_manage is true (human user with administer_workspace); returns false for a signed-in nonadministrator. Credential material is never returned.

Return contract: [Boolean](graphql-types.md#boolean).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1306`.

## inferenceProviders

List provider connections and their nonsecret configuration/test state.

```graphql
inferenceProviders: [InferenceProvider!]!
```

Requires read_project through ProviderService.list. Returns nonsecret provider configuration, availability and revision/test state. Provider credentials remain write-only; administration actions have their separate human administer_workspace gate.

Return contract: [InferenceProvider](graphql-types.md#inferenceprovider).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1312`.

## materialGrades

Page material-grade records within the requested accessible scope.

```graphql
materialGrades(materialId: ID = null, search: String = null, first: Int = null, after: String = null, last: Int = null, before: String = null): MaterialGradeConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [MaterialGradeConnection](graphql-types.md#materialgradeconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1626`.

## materialIdentities

Page scoped material identities with source/structure provenance.

```graphql
materialIdentities(search: String = null, first: Int = null, after: String = null, last: Int = null, before: String = null): MaterialIdentityConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [MaterialIdentityConnection](graphql-types.md#materialidentityconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1582`.

## measurementContractCheck

Check a measurement against the requested frozen-contract compatibility rules.

```graphql
measurementContractCheck(measurementId: ID!, metric: JSON!): JSON!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [JSON](graphql-types.md#json).

Argument contracts: [JSON](graphql-types.md#json).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2086`.

## modelRelease

Read a model release with its artifact and training lineage.

```graphql
modelRelease(modelReleaseId: ID!): ModelReleaseInfo
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [ModelReleaseInfo](graphql-types.md#modelreleaseinfo).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2204`.

## modelReleases

Page registered model releases and their validation/approval state.

```graphql
modelReleases(taskId: ID = null): [ModelReleaseInfo!]!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [ModelReleaseInfo](graphql-types.md#modelreleaseinfo).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2194`.

## node

Resolve one canonical Relay node ID within authorized workspace scope.

```graphql
node(
  """The ID of the object."""
  id: ID!
): Node
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [Node](graphql-types.md#node).

## nodes

Resolve multiple canonical Relay IDs without revealing inaccessible records.

```graphql
nodes(ids: [ID!]!): [Node]!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [Node](graphql-types.md#node).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1327`.

## planExecutions

Read lab executions linked to an accessible experiment plan.

```graphql
planExecutions(planId: ID!): [LabExecution!]!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [LabExecution](graphql-types.md#labexecution).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2036`.

## privateAgent

Read owner-private agent workspace data using its JSON alias.

```graphql
privateAgent: PrivateAgentInfo!
```

Private owner-scoped JSON alias. The corresponding private REST service enforces ownership, structured body validation and any consent/approval gate. Exact JSON construction/validation is in the linked service contract articles; the JSON scalar does not waive these checks.

Return contract: [PrivateAgentInfo](graphql-types.md#privateagentinfo).

Additional JSON semantics: [contracts-library](contracts-library.md), [contracts-agent](contracts-agent.md), [contracts-learning](contracts-learning.md).

Resolver source: `services/studio-api/src/studio/api/graphql/workspace.py:109`.

## privateAgentRun

Read the owner’s private agent run and bounded progress/messages.

```graphql
privateAgentRun(id: ID!): JSON!
```

Private owner-scoped JSON alias. The corresponding private REST service enforces ownership, structured body validation and any consent/approval gate. Exact JSON construction/validation is in the linked service contract articles; the JSON scalar does not waive these checks.

Return contract: [JSON](graphql-types.md#json).

Additional JSON semantics: [contracts-library](contracts-library.md), [contracts-agent](contracts-agent.md), [contracts-learning](contracts-learning.md).

Resolver source: `services/studio-api/src/studio/api/graphql/workspace.py:121`.

## privateLearning

Read private datasets, models and learning jobs through the GraphQL alias.

```graphql
privateLearning: PrivateLearningInfo!
```

Private owner-scoped JSON alias. The corresponding private REST service enforces ownership, structured body validation and any consent/approval gate. Exact JSON construction/validation is in the linked service contract articles; the JSON scalar does not waive these checks.

Return contract: [PrivateLearningInfo](graphql-types.md#privatelearninginfo).

Additional JSON semantics: [contracts-library](contracts-library.md), [contracts-agent](contracts-agent.md), [contracts-learning](contracts-learning.md).

Resolver source: `services/studio-api/src/studio/api/graphql/workspace.py:128`.

## privateLibrary

Read the authenticated owner’s private folders, notebooks, pages, sources and memory.

```graphql
privateLibrary: PrivateLibraryInfo!
```

Private owner-scoped JSON alias. The corresponding private REST service enforces ownership, structured body validation and any consent/approval gate. Exact JSON construction/validation is in the linked service contract articles; the JSON scalar does not waive these checks.

Return contract: [PrivateLibraryInfo](graphql-types.md#privatelibraryinfo).

Additional JSON semantics: [contracts-library](contracts-library.md), [contracts-agent](contracts-agent.md), [contracts-learning](contracts-learning.md).

Resolver source: `services/studio-api/src/studio/api/graphql/workspace.py:77`.

## processRevisions

Read process revisions and their retained lineage/review state.

```graphql
processRevisions(familyId: ID!, first: Int = null, after: String = null, last: Int = null, before: String = null): ProcessRevisionConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [ProcessRevisionConnection](graphql-types.md#processrevisionconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1874`.

## projectTasks

Page tasks belonging to an accessible project.

```graphql
projectTasks(projectId: ID!, first: Int = null, after: String = null, last: Int = null, before: String = null): TaskConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [TaskConnection](graphql-types.md#taskconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1383`.

## projects

Page accessible projects using bounded keyset pagination.

```graphql
projects(first: Int = null, after: String = null, last: Int = null, before: String = null): ProjectConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [ProjectConnection](graphql-types.md#projectconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1351`.

## promotionDecision

Read the recorded evaluation-based model-promotion verdict.

```graphql
promotionDecision(modelReleaseId: ID!): PromotionDecisionInfo
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [PromotionDecisionInfo](graphql-types.md#promotiondecisioninfo).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2295`.

## referenceProductRevisions

Read versioned reference-product specifications.

```graphql
referenceProductRevisions(productId: ID!, first: Int = null, after: String = null, last: Int = null, before: String = null): ReferenceRevisionConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [ReferenceRevisionConnection](graphql-types.md#referencerevisionconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1723`.

## referenceProducts

Page reference-product identities without inventing missing recipe information.

```graphql
referenceProducts(search: String = null, first: Int = null, after: String = null, last: Int = null, before: String = null): ReferenceProductConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [ReferenceProductConnection](graphql-types.md#referenceproductconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1678`.

## replicationSummary

Summarize recorded measurement replication without fabricating absent repeats.

```graphql
replicationSummary(executionId: ID!): JSON!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [JSON](graphql-types.md#json).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2080`.

## researchTask

Read one accessible research task with its current workflow/contract state.

```graphql
researchTask(id: ID!): Task
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [Task](graphql-types.md#task).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1910`.

## revocationImpact

Preview the records and descendants affected by source revocation.

```graphql
revocationImpact(artifactId: String!): JSON!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [JSON](graphql-types.md#json).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2372`.

## runFallback

Read a run’s explicit feasibility/fallback proposal and policy state.

```graphql
runFallback(runId: ID!): JSON!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [JSON](graphql-types.md#json).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2464`.

## servingPointer

Read the current guarded serving-release pointer.

```graphql
servingPointer: ServingPointerInfo
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [ServingPointerInfo](graphql-types.md#servingpointerinfo).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2216`.

## sessionMessages

Page persisted research-session messages with sequence/provenance.

```graphql
sessionMessages(sessionId: ID!, first: Int = null, after: String = null, last: Int = null, before: String = null): SessionMessageConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [SessionMessageConnection](graphql-types.md#sessionmessageconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2306`.

## sessionModelPins

Read the release pins preserving model identity for research sessions.

```graphql
sessionModelPins(taskId: ID = null): [SessionModelPinInfo!]!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [SessionModelPinInfo](graphql-types.md#sessionmodelpininfo).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2224`.

## sourceRevocations

Read the append-only source-revocation history.

```graphql
sourceRevocations(artifactId: String = null): JSON!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [JSON](graphql-types.md#json).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2385`.

## taskCandidateRevisions

Read candidate hypotheses and their bound research revisions.

```graphql
taskCandidateRevisions(taskId: ID!, first: Int = null, after: String = null, last: Int = null, before: String = null): CandidateConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [CandidateConnection](graphql-types.md#candidateconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1538`.

## taskCloseoutPacket

Read the evaluator-bound closeout packet for the chosen candidate/context.

```graphql
taskCloseoutPacket(taskId: ID!, candidateRevisionId: ID = null): JSON!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [JSON](graphql-types.md#json).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2118`.

## taskContractRevisions

Read versioned success-contract drafts and frozen/superseded contracts.

```graphql
taskContractRevisions(taskId: ID!, first: Int = null, after: String = null, last: Int = null, before: String = null): ContractConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [ContractConnection](graphql-types.md#contractconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1496`.

## taskDecisions

Read recorded task lifecycle, closure and review decisions.

```graphql
taskDecisions(taskId: ID!, first: Int = null, after: String = null, last: Int = null, before: String = null): DecisionConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [DecisionConnection](graphql-types.md#decisionconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1460`.

## taskEvaluation

Evaluate candidate evidence against the task’s bound success contract.

```graphql
taskEvaluation(taskId: ID!, candidateRevisionId: ID = null): JSON!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [JSON](graphql-types.md#json).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2098`.

## taskExecutions

Read lab executions linked to the accessible research task.

```graphql
taskExecutions(taskId: ID!): [LabExecution!]!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [LabExecution](graphql-types.md#labexecution).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2056`.

## taskPlans

Page experiment plans linked to the task and candidate revisions.

```graphql
taskPlans(taskId: ID!, first: Int = null, after: String = null, last: Int = null, before: String = null): ExperimentPlanConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [ExperimentPlanConnection](graphql-types.md#experimentplanconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1999`.

## taskQuestions

Read recorded unresolved or answered research questions for a task.

```graphql
taskQuestions(taskId: ID!): [TaskQuestion!]!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [TaskQuestion](graphql-types.md#taskquestion).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2343`.

## taskReassessmentStatus

Check whether changed evidence/contracts require task reassessment.

```graphql
taskReassessmentStatus(taskId: ID!): JSON!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [JSON](graphql-types.md#json).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2138`.

## taskReport

Read the sourced task report and its explicit scientific evidence limitations.

```graphql
taskReport(taskId: ID!): JSON!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [JSON](graphql-types.md#json).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2144`.

## taskRuns

Page compute runs requested within an accessible task.

```graphql
taskRuns(taskId: ID!, first: Int = null, after: String = null, last: Int = null, before: String = null): RunConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [RunConnection](graphql-types.md#runconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1963`.

## taskSessions

Page a task’s research sessions and their model/context bindings.

```graphql
taskSessions(taskId: ID!, first: Int = null, after: String = null, last: Int = null, before: String = null): ResearchSessionConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [ResearchSessionConnection](graphql-types.md#researchsessionconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1926`.

## taskSummaries

Read sourced summaries retained for task context.

```graphql
taskSummaries(taskId: ID!): [TaskSummary!]!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [TaskSummary](graphql-types.md#tasksummary).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2350`.

## tasks

Page accessible research tasks with their supported filters.

```graphql
tasks(workflowState: String = null, first: Int = null, after: String = null, last: Int = null, before: String = null): TaskConnection!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules. Resolver-declared capability checks: `CAP_READ_PROJECT`.

Return contract: [TaskConnection](graphql-types.md#taskconnection).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1423`.

## trainingRun

Read one accessible legacy supervised-training run and its attempt linkage.

```graphql
trainingRun(trainingRunId: ID!): TrainingRunInfo
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [TrainingRunInfo](graphql-types.md#trainingruninfo).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2180`.

## trainingRuns

Page legacy supervised-training specifications and execution state.

```graphql
trainingRuns(taskId: ID = null): [TrainingRunInfo!]!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [TrainingRunInfo](graphql-types.md#trainingruninfo).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2165`.

## viewer

Read the currently authenticated principal’s public profile fields.

```graphql
viewer: User!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [User](graphql-types.md#user).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1333`.

## workspace

Read the current authenticated workspace identity.

```graphql
workspace: Workspace!
```

Requires the signed-in service context except where the field explicitly supplies setup/capability information. IDs are canonical Relay IDs scoped to this workspace; responses and nested selections are defined in the linked type catalog. Domain services enforce their own capability, ownership, revision and state rules.

Return contract: [Workspace](graphql-types.md#workspace).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:1342`.
