# GraphQL type catalog

Every declared scalar, enum, input and response object from `packages/contracts/schema.graphql`, plus the standard built-in scalars. `!` means non-null, `[T]` is a list, and defaults appear after `=`. JSON scalars use the linked endpoint/contract guides; they do not imply arbitrary values are accepted.

## ActualsRecordInput

```graphql
input ActualsRecordInput {
  executionId: ID!
  actual: JSON = null
  deviations: JSON = null
  observations: String = null
  clientMutationId: String = null
}
```

## AnalyticalCompareInput

```graphql
input AnalyticalCompareInput {
  taskId: ID!
  leftSeriesId: ID!
  rightSeriesId: ID!
  spec: JSON!
  idempotencyKey: String!
  clientMutationId: String = null
}
```

## AnalyticalComparisonInfo

```graphql
type AnalyticalComparisonInfo {
  id: ID!
  manifest: JSON!
}
```

## AnalyticalIngestInput

```graphql
input AnalyticalIngestInput {
  taskId: ID!
  rawArtifactId: String!
  spec: JSON!
  idempotencyKey: String!
  clientMutationId: String = null
}
```

## AnalyticalMutation

```graphql
type AnalyticalMutation {
  ingest(input: AnalyticalIngestInput!): AnalyticalResult!
  compare(input: AnalyticalCompareInput!): AnalyticalResult!
}
```

## AnalyticalResult

```graphql
type AnalyticalResult {
  task: Task
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## AnalyticalSeriesInfo

```graphql
type AnalyticalSeriesInfo {
  id: ID!
  label: String!
  method: String!
  interpretationState: String!
  manifest: JSON!
}
```

## ApplicabilityMapResult

```graphql
type ApplicabilityMapResult {
  mappingId: String
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## BatchAddInput

```graphql
input BatchAddInput {
  executionId: ID!
  label: String!
  payload: JSON = null
  clientMutationId: String = null
}
```

## BatchResult

```graphql
type BatchResult {
  batch: LabBatch
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## Boolean

```graphql
"""Boolean true or false."""
scalar Boolean
```

## CandidateConnection

```graphql
type CandidateConnection {
  edges: [CandidateEdge!]!
  pageInfo: PageInfo!
}
```

## CandidateCreateInput

```graphql
input CandidateCreateInput {
  taskId: ID!
  entityKind: String!
  entityRevisionId: String = null
  hypothesis: String = null
  proposedDifferences: JSON = null
  evidenceIds: JSON = null
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## CandidateEdge

```graphql
type CandidateEdge {
  cursor: String!
  node: CandidateRevision!
}
```

## CandidatePatchProposeInput

```graphql
input CandidatePatchProposeInput {
  candidateId: ID!
  patch: JSON!
  reason: String = null
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## CandidatePatchResult

```graphql
type CandidatePatchResult {
  patchId: String
  status: String
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## CandidatePatchReviewInput

```graphql
input CandidatePatchReviewInput {
  patchId: String!
  accept: Boolean!
  rejectionReason: String = null
  clientMutationId: String = null
}
```

## CandidateReviewInput

```graphql
input CandidateReviewInput {
  candidateId: ID!
  accept: Boolean!
  clientMutationId: String = null
}
```

## CandidateRevision

```graphql
type CandidateRevision implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  revision: Int!
  status: String!
  eligibility: String!
  entityKind: String!
  hypothesis: String
  payload: JSON!
  parentRevisionId: String
  entityRevisionId: String
  createdAt: DateTime!
}
```

## CandidateRevisionResult

```graphql
type CandidateRevisionResult {
  candidate: CandidateRevision
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## CandidateSubmitInput

```graphql
input CandidateSubmitInput {
  candidateId: ID!
  clientMutationId: String = null
}
```

## CandidatesMutation

```graphql
type CandidatesMutation {
  create(input: CandidateCreateInput!): CandidateRevisionResult!
  submit(input: CandidateSubmitInput!): CandidateRevisionResult!
  review(input: CandidateReviewInput!): CandidateRevisionResult!
  patchPropose(input: CandidatePatchProposeInput!): CandidatePatchResult!
  patchReview(input: CandidatePatchReviewInput!): CandidatePatchResult!
}
```

## CapabilityStatus

```graphql
type CapabilityStatus {
  status: String!
  detail: String!
}
```

## ClaimCreateInput

```graphql
input ClaimCreateInput {
  kind: String!
  subject: JSON!
  statement: JSON!
  locator: JSON = null
  originalText: String = null
  conditions: JSON = null
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## ClaimLink

```graphql
type ClaimLink {
  fromClaimId: String!
  toClaimId: String!
  relation: String!
  note: String
}
```

## ClaimLinkInput

```graphql
input ClaimLinkInput {
  fromClaimId: ID!
  toClaimId: ID!
  relation: String!
  note: String = null
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## ClaimLinkResult

```graphql
type ClaimLinkResult {
  link: ClaimLink
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## ClaimReviewInput

```graphql
input ClaimReviewInput {
  claimId: ID!
  decision: String!
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## ContextManifest

```graphql
type ContextManifest {
  id: String!
  compilerVersion: String!
  tokenBudget: Int!
  tokenEstimate: Int!
  overBudget: Boolean!
  items: JSON!
  omitted: JSON!
  warnings: JSON!
  createdAt: DateTime!
}
```

## ContractConnection

```graphql
type ContractConnection {
  edges: [ContractEdge!]!
  pageInfo: PageInfo!
}
```

## ContractDraftCreateInput

```graphql
input ContractDraftCreateInput {
  taskId: ID!
  payload: JSON!
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## ContractEdge

```graphql
type ContractEdge {
  cursor: String!
  node: ContractRevision!
}
```

## ContractFreezeInput

```graphql
input ContractFreezeInput {
  revisionId: ID!
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## ContractRevision

```graphql
type ContractRevision implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  revision: Int!
  status: String!
  contentHash: String!
  createdAt: DateTime!
  payload: JSON!
}
```

## ContractRevisionResult

```graphql
type ContractRevisionResult {
  contractRevision: ContractRevision
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## DatasetPrepareResult

```graphql
type DatasetPrepareResult {
  report: JSON
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## DatasetSnapshotBuildInput

```graphql
input DatasetSnapshotBuildInput {
  purpose: String!
  name: String!
  taskId: ID = null
  clientMutationId: String = null
}
```

## DatasetSnapshotIdInput

```graphql
input DatasetSnapshotIdInput {
  snapshotId: ID!
  clientMutationId: String = null
}
```

## DatasetSnapshotInfo

```graphql
type DatasetSnapshotInfo {
  id: ID!
  purpose: String!
  name: String!
  taskId: String
  state: String!
  digest: String!
  manifest: JSON!
  createdAt: DateTime!
  frozenAt: DateTime
}
```

## DatasetSnapshotResult

```graphql
type DatasetSnapshotResult {
  snapshot: DatasetSnapshotInfo
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## DateTime

```graphql
"""Date with time (isoformat)"""
scalar DateTime
```

## Decision

```graphql
type Decision implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  kind: String!
  payload: JSON!
  createdAt: DateTime!
  decidedBy: User
}
```

## DecisionConnection

```graphql
type DecisionConnection {
  edges: [DecisionEdge!]!
  pageInfo: PageInfo!
}
```

## DecisionEdge

```graphql
type DecisionEdge {
  cursor: String!
  node: Decision!
}
```

## DescribeStructureInput

```graphql
input DescribeStructureInput {
  taskId: ID!
  smiles: String!
  idempotencyKey: String!
  clientMutationId: String = null
}
```

## DomainErrorPayload

```graphql
type DomainErrorPayload {
  code: String!
  message: String!
  fieldPath: String
  retryable: Boolean!
  safeDetails: JSON!
}
```

## EvaluationRunInfo

```graphql
type EvaluationRunInfo {
  id: ID!
  suiteId: ID!
  suiteDigest: String!
  modelReleaseId: String!
  baselineReleaseId: String
  state: String!
  backend: JSON
  comparison: JSON
  contamination: JSON
  blockers: JSON
  capability: JSON
  error: JSON
  createdAt: DateTime!
}
```

## EvaluationRunResult

```graphql
type EvaluationRunResult {
  evaluationRun: EvaluationRunInfo
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## EvaluationRunStartInput

```graphql
input EvaluationRunStartInput {
  evaluationSuiteId: ID!
  modelReleaseId: ID!
  baselineReleaseId: ID = null
  clientMutationId: String = null
}
```

## EvaluationSuiteCreateInput

```graphql
input EvaluationSuiteCreateInput {
  name: String!
  kind: String!
  taskId: ID = null
  tasks: JSON = null
  thresholds: JSON = null
  budget: JSON = null
  scoring: JSON = null
  allowedContext: JSON = null
  reviewRules: JSON = null
  purpose: String = null
  clientMutationId: String = null
}
```

## EvaluationSuiteIdInput

```graphql
input EvaluationSuiteIdInput {
  evaluationSuiteId: ID!
  clientMutationId: String = null
}
```

## EvaluationSuiteInfo

```graphql
type EvaluationSuiteInfo {
  id: ID!
  taskId: String
  name: String!
  version: Int!
  purpose: String!
  kind: String!
  state: String!
  definition: JSON
  digest: String!
  capability: JSON
  createdAt: DateTime!
  updatedAt: DateTime
}
```

## EvaluationSuiteLabelsInput

```graphql
input EvaluationSuiteLabelsInput {
  evaluationSuiteId: ID!
  labels: JSON = null
  clientMutationId: String = null
}
```

## EvaluationSuiteResult

```graphql
type EvaluationSuiteResult {
  evaluationSuite: EvaluationSuiteInfo
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## EvidenceClaim

```graphql
type EvidenceClaim implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  kind: String!
  status: String!
  subject: JSON!
  statement: JSON!
  locator: JSON
  originalText: String
  conditions: JSON
  sourceRecordId: String
  reviewedAt: DateTime
  createdAt: DateTime!
}
```

## EvidenceClaimConnection

```graphql
type EvidenceClaimConnection {
  edges: [EvidenceClaimEdge!]!
  pageInfo: PageInfo!
}
```

## EvidenceClaimEdge

```graphql
type EvidenceClaimEdge {
  cursor: String!
  node: EvidenceClaim!
}
```

## EvidenceClaimResult

```graphql
type EvidenceClaimResult {
  claim: EvidenceClaim
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## EvidenceMutation

```graphql
type EvidenceMutation {
  claimCreate(input: ClaimCreateInput!): EvidenceClaimResult!
  claimReview(input: ClaimReviewInput!): EvidenceClaimResult!
  claimLink(input: ClaimLinkInput!): ClaimLinkResult!
}
```

## ExecutionCloseInput

```graphql
input ExecutionCloseInput {
  executionId: ID!
  status: String! = "completed"
  clientMutationId: String = null
}
```

## ExecutionHistoricalInput

```graphql
input ExecutionHistoricalInput {
  taskId: ID!
  payload: JSON!
  clientMutationId: String = null
}
```

## ExecutionOpenInput

```graphql
input ExecutionOpenInput {
  planId: ID!
  clientMutationId: String = null
}
```

## ExecutionResult

```graphql
type ExecutionResult {
  execution: LabExecution
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## ExperimentPlan

```graphql
type ExperimentPlan implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  taskId: String!
  title: String!
  status: String!
  contentDigest: String!
  blockers: JSON!
  payload: JSON!
  approvalId: String
  packet: JSON
  createdAt: DateTime!
}
```

## ExperimentPlanConnection

```graphql
type ExperimentPlanConnection {
  edges: [ExperimentPlanEdge!]!
  pageInfo: PageInfo!
}
```

## ExperimentPlanEdge

```graphql
type ExperimentPlanEdge {
  cursor: String!
  node: ExperimentPlan!
}
```

## ExportDecideInput

```graphql
input ExportDecideInput {
  payloadId: ID!
  decision: String!
  rationale: String = null
  ttlSeconds: Int = null
  clientMutationId: String = null
}
```

## ExportPrepareInput

```graphql
input ExportPrepareInput {
  proposalId: ID!
  snapshotId: ID!
  recipient: String = null
  account: String = null
  region: String = null
  expiresAt: String = null
  maxRecords: Int = null
  maxBytes: Int = null
  retentionExpectation: String = null
  deletionExpectation: String = null
  clientMutationId: String = null
}
```

## ExportReviewResult

```graphql
type ExportReviewResult {
  view: JSON
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## ExportSetClassificationInput

```graphql
input ExportSetClassificationInput {
  payloadId: ID!
  classification: String!
  rationale: String = null
  clientMutationId: String = null
}
```

## ExportsMutation

```graphql
type ExportsMutation {
  prepare(input: ExportPrepareInput!): ExportReviewResult!
  decide(input: ExportDecideInput!): ExportReviewResult!
  setClassification(input: ExportSetClassificationInput!): ExportReviewResult!
}
```

## ExtractedRecord

```graphql
type ExtractedRecord implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  batchId: String!
  kind: String!
  locator: JSON!
  originalText: String!
  payload: JSON
  flags: [String!]!
  confidence: Float!
  status: String!
  createdAt: DateTime!
}
```

## ExtractedRecordConnection

```graphql
type ExtractedRecordConnection {
  edges: [ExtractedRecordEdge!]!
  pageInfo: PageInfo!
}
```

## ExtractedRecordEdge

```graphql
type ExtractedRecordEdge {
  cursor: String!
  node: ExtractedRecord!
}
```

## ExtractedRecordResult

```graphql
type ExtractedRecordResult {
  record: ExtractedRecord
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## FallbackResult

```graphql
type FallbackResult {
  run: Run
  decision: String
  cloudAuthorized: Boolean!
  report: JSON
  proposal: JSON
  cloud: JSON
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## Float

```graphql
"""Finite double-precision number."""
scalar Float
```

## FormulationFamily

```graphql
type FormulationFamily implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  name: String!
  description: String
  createdAt: DateTime!
}
```

## FormulationFamilyConnection

```graphql
type FormulationFamilyConnection {
  edges: [FormulationFamilyEdge!]!
  pageInfo: PageInfo!
}
```

## FormulationFamilyCreateInput

```graphql
input FormulationFamilyCreateInput {
  name: String!
  description: String = null
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## FormulationFamilyEdge

```graphql
type FormulationFamilyEdge {
  cursor: String!
  node: FormulationFamily!
}
```

## FormulationFamilyResult

```graphql
type FormulationFamilyResult {
  family: FormulationFamily
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## FormulationRevision

```graphql
type FormulationRevision implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  familyId: String!
  revision: Int!
  status: String!
  payload: JSON!
  parentRevisionId: String
  contentHash: String!
  createdAt: DateTime!
  familyName: String
}
```

## FormulationRevisionConnection

```graphql
type FormulationRevisionConnection {
  edges: [FormulationRevisionEdge!]!
  pageInfo: PageInfo!
}
```

## FormulationRevisionDraftInput

```graphql
input FormulationRevisionDraftInput {
  familyId: ID!
  payload: JSON!
  parentRevisionId: ID = null
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## FormulationRevisionEdge

```graphql
type FormulationRevisionEdge {
  cursor: String!
  node: FormulationRevision!
}
```

## FormulationRevisionIdInput

```graphql
input FormulationRevisionIdInput {
  revisionId: ID!
  clientMutationId: String = null
}
```

## FormulationRevisionResult

```graphql
type FormulationRevisionResult {
  revision: FormulationRevision
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## FormulationsMutation

```graphql
type FormulationsMutation {
  familyCreate(input: FormulationFamilyCreateInput!): FormulationFamilyResult!
  revisionDraft(input: FormulationRevisionDraftInput!): FormulationRevisionResult!
  revisionAccept(input: FormulationRevisionIdInput!): FormulationRevisionResult!
  processDraft(input: ProcessRevisionDraftInput!): ProcessRevisionResult!
  processAccept(input: ProcessRevisionIdInput!): ProcessRevisionResult!
}
```

## HardwareCapabilities

```graphql
type HardwareCapabilities {
  os: String!
  arch: String!
  gpu: String!
}
```

## ID

```graphql
"""Opaque identifier serialized as a string; use the format required by the operation."""
scalar ID
```

## ImportArtifactInput

```graphql
input ImportArtifactInput {
  artifactId: String!
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## ImportBatch

```graphql
type ImportBatch implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  originalName: String!
  detectedType: String!
  parserName: String!
  parserVersion: String!
  sourceRevision: Int!
  status: String!
  recordCount: Int!
  findings: JSON!
  createdAt: DateTime!
}
```

## ImportBatchConnection

```graphql
type ImportBatchConnection {
  edges: [ImportBatchEdge!]!
  pageInfo: PageInfo!
}
```

## ImportBatchEdge

```graphql
type ImportBatchEdge {
  cursor: String!
  node: ImportBatch!
}
```

## ImportBatchResult

```graphql
type ImportBatchResult {
  batch: ImportBatch
  deduplicated: Boolean!
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## ImportsMutation

```graphql
type ImportsMutation {
  sourceRevoke(input: SourceRevokeInput!): SourceRevokeResult!
  artifactImport(input: ImportArtifactInput!): ImportBatchResult!
  recordReview(input: ReviewRecordInput!): ExtractedRecordResult!
  recordPromote(input: PromoteRecordInput!): EvidenceClaimResult!
}
```

## InferenceCredentialCleanupResult

```graphql
type InferenceCredentialCleanupResult {
  pending: Boolean!
  errors: [DomainErrorPayload!]!
}
```

## InferenceProvider

```graphql
type InferenceProvider {
  id: ID!
  revision: Int!
  name: String!
  kind: String!
  baseUrl: String!
  model: String!
  apiStyle: String!
  enabled: Boolean!
  supportsTools: Boolean!
  hasApiKey: Boolean!
  lastTestStatus: String!
  lastTestDetail: String
  lastTestAt: DateTime
  createdAt: DateTime!
  updatedAt: DateTime!
}
```

## InferenceProviderDeleteInput

```graphql
input InferenceProviderDeleteInput {
  id: ID!
  expectedRevision: Int!
  clientMutationId: String = null
}
```

## InferenceProviderDeleteResult

```graphql
type InferenceProviderDeleteResult {
  deleted: Boolean!
  credentialCleanupPending: Boolean!
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## InferenceProviderResult

```graphql
type InferenceProviderResult {
  provider: InferenceProvider
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## InferenceProviderSaveInput

```graphql
input InferenceProviderSaveInput {
  name: String!
  kind: String!
  baseUrl: String!
  model: String!
  apiStyle: String! = "chat_completions"
  enabled: Boolean! = false
  supportsTools: Boolean! = true
  id: ID = null
  expectedRevision: Int = null
  apiKey: String = null
  clearApiKey: Boolean! = false
  clientMutationId: String = null
}
```

## InferenceProviderTestInput

```graphql
input InferenceProviderTestInput {
  id: ID!
  clientMutationId: String = null
}
```

## InferenceProviderTestResult

```graphql
type InferenceProviderTestResult {
  provider: InferenceProvider
  status: String!
  detail: String!
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## Int

```graphql
"""Signed 32-bit integer."""
scalar Int
```

## JSON

```graphql
"""
The `JSON` scalar type represents JSON values as specified by [ECMA-404](https://ecma-international.org/wp-content/uploads/ECMA-404_2nd_edition_december_2017.pdf).
"""
scalar JSON @specifiedBy(url: "https://ecma-international.org/wp-content/uploads/ECMA-404_2nd_edition_december_2017.pdf")
```

## LabBatch

```graphql
type LabBatch implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  executionId: String!
  label: String!
  payload: JSON!
  createdAt: DateTime!
  samples: [LabSample!]!
}
```

## LabExecution

```graphql
type LabExecution implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  planId: String
  status: String!
  historical: Boolean!
  actual: JSON!
  deviations: JSON!
  observations: String
  closedAt: DateTime
  createdAt: DateTime!
  batches: [LabBatch!]!
}
```

## LabMeasurementsMutation

```graphql
type LabMeasurementsMutation {
  executionOpen(input: ExecutionOpenInput!): ExecutionResult!
  executionHistoricalImport(input: ExecutionHistoricalInput!): ExecutionResult!
  executionClose(input: ExecutionCloseInput!): ExecutionResult!
  actualsRecord(input: ActualsRecordInput!): ExecutionResult!
  batchAdd(input: BatchAddInput!): BatchResult!
  sampleAdd(input: SampleAddInput!): SampleResult!
  measurementRecord(input: MeasurementRecordInput!): MeasurementResult!
  measurementReview(input: MeasurementReviewInput!): MeasurementResult!
  measurementApplicability(input: MeasurementApplicabilityInput!): MeasurementResult!
  measurementMapApplicability(input: MeasurementApplicabilityMapInput!): ApplicabilityMapResult!
  measurementAmend(input: MeasurementAmendInput!): MeasurementResult!
}
```

## LabMutation

```graphql
type LabMutation {
  planCreate(input: PlanCreateInput!): PlanResult!
  planUpdate(input: PlanUpdateInput!): PlanResult!
  planSubmit(input: PlanIdInput!): PlanResult!
  planReview(input: PlanReviewInput!): PlanResult!
  packetExport(input: PlanIdInput!): PacketResult!
  measurements: LabMeasurementsMutation!
}
```

## LabSample

```graphql
type LabSample implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  batchId: String!
  label: String!
  kind: String!
  payload: JSON!
  createdAt: DateTime!
  measurements: [Measurement!]!
}
```

## LearningMutation

```graphql
type LearningMutation {
  snapshotBuild(input: DatasetSnapshotBuildInput!): DatasetSnapshotResult!
  snapshotFreeze(input: DatasetSnapshotIdInput!): DatasetSnapshotResult!
  snapshotPrepareRun(input: DatasetSnapshotIdInput!): DatasetPrepareResult!
  trainingRunCreate(input: TrainingRunCreateInput!): TrainingRunResult!
  trainingRunSubmit(input: TrainingRunIdInput!): TrainingRunResult!
  trainingRunApprove(input: TrainingRunApproveInput!): TrainingRunResult!
  trainingRunQueue(input: TrainingRunIdInput!): TrainingRunResult!
  trainingRunExecute(input: TrainingRunExecuteInput!): TrainingRunResult!
  trainingRunCancel(input: TrainingRunIdInput!): TrainingRunResult!
  trainingRunResume(input: TrainingRunIdInput!): TrainingRunResult!
  trainingRunTransition(input: TrainingRunTransitionInput!): TrainingRunResult!
  modelReleaseRegister(input: ModelReleaseRegisterInput!): ModelReleaseResult!
  modelReleaseValidate(input: ModelReleaseIdInput!): ModelReleaseResult!
  modelReleaseConvert(input: ModelReleaseConvertInput!): ModelReleaseResult!
  modelReleaseApprove(input: ModelReleaseApproveInput!): ModelReleaseResult!
  modelReleasePromote(input: ModelReleaseIdInput!): ModelReleaseResult!
  modelReleaseRollback(input: ModelReleaseRollbackInput!): ModelReleaseResult!
  sessionModelBind(input: SessionModelBindInput!): SessionBindResult!
  evaluationSuiteCreate(input: EvaluationSuiteCreateInput!): EvaluationSuiteResult!
  evaluationSuiteLabels(input: EvaluationSuiteLabelsInput!): EvaluationSuiteResult!
  evaluationSuiteFreeze(input: EvaluationSuiteIdInput!): EvaluationSuiteResult!
  evaluationRunStart(input: EvaluationRunStartInput!): EvaluationRunResult!
  promotionDecide(input: PromotionDecideInput!): PromotionDecisionResult!
  promotionApprove(input: PromotionApproveInput!): PromotionDecisionResult!
  promotionPromote(input: PromotionPromoteInput!): PromotionDecisionResult!
}
```

## MaterialGrade

```graphql
type MaterialGrade implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  supplier: String!
  gradeName: String!
  activeContent: JSON
  specifications: JSON!
  reconciledInto: ID
  createdAt: DateTime!
}
```

## MaterialGradeConnection

```graphql
type MaterialGradeConnection {
  edges: [MaterialGradeEdge!]!
  pageInfo: PageInfo!
}
```

## MaterialGradeCreateInput

```graphql
input MaterialGradeCreateInput {
  materialId: ID!
  supplier: String!
  gradeName: String!
  activeContent: JSON = null
  specifications: JSON = null
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## MaterialGradeEdge

```graphql
type MaterialGradeEdge {
  cursor: String!
  node: MaterialGrade!
}
```

## MaterialGradeReconcileInput

```graphql
input MaterialGradeReconcileInput {
  keepGradeId: ID!
  mergeGradeId: ID!
  reason: String!
  clientMutationId: String = null
}
```

## MaterialGradeResult

```graphql
type MaterialGradeResult {
  grade: MaterialGrade
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## MaterialIdentity

```graphql
type MaterialIdentity implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  kind: String!
  name: String!
  structureStatus: String!
  evidenceStatus: String!
  identifiers: JSON!
  aliases: JSON!
  createdAt: DateTime!
}
```

## MaterialIdentityConnection

```graphql
type MaterialIdentityConnection {
  edges: [MaterialIdentityEdge!]!
  pageInfo: PageInfo!
}
```

## MaterialIdentityCreateInput

```graphql
input MaterialIdentityCreateInput {
  kind: String!
  name: String!
  identifiers: JSON = null
  aliases: JSON = null
  structure: String = null
  structureFormat: String = null
  confidentiality: String! = "internal"
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## MaterialIdentityEdge

```graphql
type MaterialIdentityEdge {
  cursor: String!
  node: MaterialIdentity!
}
```

## MaterialIdentityResult

```graphql
type MaterialIdentityResult {
  identity: MaterialIdentity
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## MaterialMatchProposeInput

```graphql
input MaterialMatchProposeInput {
  sourceIdentityId: ID!
  candidateIdentityId: ID!
  confidence: String = null
  rationale: String = null
  proposedBy: String! = "user"
  clientMutationId: String = null
}
```

## MaterialMatchReviewInput

```graphql
input MaterialMatchReviewInput {
  matchId: ID!
  decision: String!
  rationale: String = null
  clientMutationId: String = null
}
```

## MaterialStructureReviewInput

```graphql
input MaterialStructureReviewInput {
  identityId: ID!
  clientMutationId: String = null
}
```

## MaterialsMutation

```graphql
type MaterialsMutation {
  identityCreate(input: MaterialIdentityCreateInput!): MaterialIdentityResult!
  structureReview(input: MaterialStructureReviewInput!): MaterialIdentityResult!
  matchPropose(input: MaterialMatchProposeInput!): MaterialIdentityResult!
  matchReview(input: MaterialMatchReviewInput!): MaterialIdentityResult!
  gradeCreate(input: MaterialGradeCreateInput!): MaterialGradeResult!
  gradeReconcile(input: MaterialGradeReconcileInput!): MaterialGradeResult!
  referenceProductCreate(input: ReferenceProductCreateInput!): ReferenceProductResult!
  referenceRevisionDraft(input: ReferenceRevisionDraftInput!): ReferenceRevisionResult!
  referenceRevisionFreeze(input: ReferenceRevisionFreezeInput!): ReferenceRevisionResult!
}
```

## Measurement

```graphql
type Measurement implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  sampleId: String!
  method: String!
  repeatType: String!
  metric: String
  valueType: String!
  value: JSON!
  conditions: JSON!
  applicable: Boolean!
  applicabilityNote: String
  status: String!
  reviewNote: String
  pipelineVersion: String
  supersededBy: String
  createdAt: DateTime!
  amendments: JSON!
  effectiveValue: JSON
}
```

## MeasurementAmendInput

```graphql
input MeasurementAmendInput {
  measurementId: ID!
  reason: String!
  value: JSON!
  source: String = null
  conditions: JSON = null
  clientMutationId: String = null
}
```

## MeasurementApplicabilityInput

```graphql
input MeasurementApplicabilityInput {
  measurementId: ID!
  applicable: Boolean!
  note: String = null
  clientMutationId: String = null
}
```

## MeasurementApplicabilityMapInput

```graphql
input MeasurementApplicabilityMapInput {
  measurementId: ID!
  candidateRevisionId: ID!
  contractRevisionId: ID = null
  applicable: Boolean! = true
  rationale: String! = ""
  withdraw: Boolean! = false
  clientMutationId: String = null
}
```

## MeasurementRecordInput

```graphql
input MeasurementRecordInput {
  sampleId: ID!
  method: String!
  repeatType: String!
  value: JSON!
  metric: String = null
  valueType: String = null
  conditions: JSON = null
  pipelineVersion: String = null
  clientMutationId: String = null
}
```

## MeasurementResult

```graphql
type MeasurementResult {
  measurement: Measurement
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## MeasurementReviewInput

```graphql
input MeasurementReviewInput {
  measurementId: ID!
  decision: String!
  note: String = null
  clientMutationId: String = null
}
```

## MessagePostInput

```graphql
input MessagePostInput {
  sessionId: ID!
  role: String!
  content: String!
  kind: String = null
  refs: JSON = null
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## ModelReleaseApproveInput

```graphql
input ModelReleaseApproveInput {
  modelReleaseId: ID!
  rationale: String = null
  clientMutationId: String = null
}
```

## ModelReleaseConvertInput

```graphql
input ModelReleaseConvertInput {
  modelReleaseId: ID!
  targetFormat: String = null
  clientMutationId: String = null
}
```

## ModelReleaseIdInput

```graphql
input ModelReleaseIdInput {
  modelReleaseId: ID!
  clientMutationId: String = null
}
```

## ModelReleaseInfo

```graphql
type ModelReleaseInfo {
  id: ID!
  taskId: String
  name: String!
  state: String!
  snapshotId: String!
  trainingRunId: String
  baseModelId: String!
  architecture: String!
  baseSha256: String!
  licenseId: String!
  tokenizerKind: String!
  tokenizerSha256: String!
  adapterSha256: String!
  adapterMethod: String!
  servingFormat: String!
  conversions: JSON
  validation: JSON
  capability: JSON
  provenance: JSON
  approvalId: String
  createdAt: DateTime!
  updatedAt: DateTime
}
```

## ModelReleaseRegisterInput

```graphql
input ModelReleaseRegisterInput {
  trainingRunId: ID!
  name: String!
  taskId: ID = null
  servingFormat: String = null
  clientMutationId: String = null
}
```

## ModelReleaseResult

```graphql
type ModelReleaseResult {
  modelRelease: ModelReleaseInfo
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## ModelReleaseRollbackInput

```graphql
input ModelReleaseRollbackInput {
  modelReleaseId: ID = null
  clientMutationId: String = null
}
```

## Node

```graphql
"""An object with a Globally Unique ID"""
interface Node {
  """The Globally Unique ID of this object"""
  id: ID!
}
```

## OptimizationCampaignInfo

```graphql
type OptimizationCampaignInfo {
  id: ID!
  revision: Int!
  manifest: JSON!
}
```

## OptimizationCommandInput

```graphql
input OptimizationCommandInput {
  campaignId: ID!
  expectedRevision: Int!
  idempotencyKey: String!
  operation: OptimizationOperation!
  batchSize: Int! = 1
  experimentId: String = null
  measurementId: ID = null
  snapshotId: ID = null
  reason: String = null
  clientMutationId: String = null
}
```

## OptimizationCreateInput

```graphql
input OptimizationCreateInput {
  taskId: ID!
  definition: JSON!
  idempotencyKey: String!
  clientMutationId: String = null
}
```

## OptimizationMutation

```graphql
type OptimizationMutation {
  create(input: OptimizationCreateInput!): OptimizationResult!
  command(input: OptimizationCommandInput!): OptimizationResult!
}
```

## OptimizationOperation

```graphql
enum OptimizationOperation {
  recommend
  observed
  cancelled
  failed
}
```

## OptimizationResult

```graphql
type OptimizationResult {
  task: Task
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## PacketResult

```graphql
type PacketResult {
  packet: JSON
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## PageInfo

```graphql
type PageInfo {
  hasNextPage: Boolean!
  hasPreviousPage: Boolean!
  startCursor: String
  endCursor: String
}
```

## PlanCreateInput

```graphql
input PlanCreateInput {
  taskId: ID!
  title: String!
  payload: JSON!
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## PlanIdInput

```graphql
input PlanIdInput {
  planId: ID!
  clientMutationId: String = null
}
```

## PlanResult

```graphql
type PlanResult {
  plan: ExperimentPlan
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## PlanReviewInput

```graphql
input PlanReviewInput {
  planId: ID!
  decision: String!
  rationale: String = null
  clientMutationId: String = null
}
```

## PlanUpdateInput

```graphql
input PlanUpdateInput {
  planId: ID!
  payload: JSON!
  clientMutationId: String = null
}
```

## PrivateAgentInfo

```graphql
type PrivateAgentInfo {
  threads: [JSON!]!
  providers: [JSON!]!
  policy: JSON!
}
```

## PrivateLearningInfo

```graphql
type PrivateLearningInfo {
  datasets: [JSON!]!
  models: [JSON!]!
  jobs: [JSON!]!
}
```

## PrivateLibraryInfo

```graphql
type PrivateLibraryInfo {
  folders: [JSON!]!
  notebooks: [PrivateNotebookInfo!]!
  pages: [PrivatePageInfo!]!
  memory: [JSON!]!
  downloads: [JSON!]!
}
```

## PrivateNotebookInfo

```graphql
type PrivateNotebookInfo {
  id: ID!
  title: String!
  folderId: ID
  revision: Int!
  aiEnabled: Boolean!
  trainingEnabled: Boolean!
}
```

## PrivatePageInfo

```graphql
type PrivatePageInfo {
  id: ID!
  notebookId: ID!
  title: String!
  kind: String!
  revision: Int!
  content: JSON!
  citations: [JSON!]!
}
```

## ProcessRevision

```graphql
type ProcessRevision implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  familyId: String!
  revision: Int!
  status: String!
  payload: JSON!
  contentHash: String!
  createdAt: DateTime!
}
```

## ProcessRevisionConnection

```graphql
type ProcessRevisionConnection {
  edges: [ProcessRevisionEdge!]!
  pageInfo: PageInfo!
}
```

## ProcessRevisionDraftInput

```graphql
input ProcessRevisionDraftInput {
  familyId: ID!
  payload: JSON!
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## ProcessRevisionEdge

```graphql
type ProcessRevisionEdge {
  cursor: String!
  node: ProcessRevision!
}
```

## ProcessRevisionIdInput

```graphql
input ProcessRevisionIdInput {
  revisionId: ID!
  clientMutationId: String = null
}
```

## ProcessRevisionResult

```graphql
type ProcessRevisionResult {
  revision: ProcessRevision
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## ProfileCapabilities

```graphql
type ProfileCapabilities {
  core: CapabilityStatus!
  localAi: CapabilityStatus!
  optimization: CapabilityStatus!
  quantum: CapabilityStatus!
  materials: CapabilityStatus!
  training: CapabilityStatus!
  design: CapabilityStatus!
  synthesis: CapabilityStatus!
  rdkit: CapabilityStatus!
}
```

## Project

```graphql
type Project implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  slug: String!
  name: String!
  status: String!
  description: String
  createdAt: DateTime!
}
```

## ProjectConnection

```graphql
type ProjectConnection {
  edges: [ProjectEdge!]!
  pageInfo: PageInfo!
}
```

## ProjectCreateInput

```graphql
input ProjectCreateInput {
  slug: String!
  name: String!
  description: String = null
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## ProjectEdge

```graphql
type ProjectEdge {
  cursor: String!
  node: Project!
}
```

## ProjectResult

```graphql
type ProjectResult {
  project: Project
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## PromoteRecordInput

```graphql
input PromoteRecordInput {
  recordId: ID!
  subject: JSON!
  statement: JSON!
  conditions: JSON = null
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## PromotionApproveInput

```graphql
input PromotionApproveInput {
  modelReleaseId: ID!
  scope: String!
  limitations: [String!] = null
  rationale: String = null
  clientMutationId: String = null
}
```

## PromotionDecideInput

```graphql
input PromotionDecideInput {
  modelReleaseId: ID!
  clientMutationId: String = null
}
```

## PromotionDecisionInfo

```graphql
type PromotionDecisionInfo {
  id: ID!
  modelReleaseId: String!
  evaluationRunId: String
  eligible: Boolean!
  blockers: JSON
  modelCard: JSON
  decisionDigest: String!
  approvalId: String
  createdAt: DateTime!
}
```

## PromotionDecisionResult

```graphql
type PromotionDecisionResult {
  promotionDecision: PromotionDecisionInfo
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## PromotionPromoteInput

```graphql
input PromotionPromoteInput {
  modelReleaseId: ID!
  scope: String!
  limitations: [String!] = null
  clientMutationId: String = null
}
```

## ProviderMutation

```graphql
type ProviderMutation {
  cleanupCredentials: InferenceCredentialCleanupResult!
  save(input: InferenceProviderSaveInput!): InferenceProviderResult!
  delete(input: InferenceProviderDeleteInput!): InferenceProviderDeleteResult!
  test(input: InferenceProviderTestInput!): InferenceProviderTestResult!
}
```

## QuestionRaiseInput

```graphql
input QuestionRaiseInput {
  taskId: ID!
  question: String!
  blocking: Boolean = null
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## QuestionResolveInput

```graphql
input QuestionResolveInput {
  questionId: ID!
  resolution: String!
  clientMutationId: String = null
}
```

## QuickDescribeStructureInput

```graphql
input QuickDescribeStructureInput {
  smiles: String!
  idempotencyKey: String!
  projectId: ID = null
  clientMutationId: String = null
}
```

## ReferenceProduct

```graphql
type ReferenceProduct implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  name: String!
  supplier: String
  category: String
  compositionKnowledge: String!
  aliases: JSON!
  createdAt: DateTime!
}
```

## ReferenceProductConnection

```graphql
type ReferenceProductConnection {
  edges: [ReferenceProductEdge!]!
  pageInfo: PageInfo!
}
```

## ReferenceProductCreateInput

```graphql
input ReferenceProductCreateInput {
  name: String!
  supplier: String = null
  category: String = null
  compositionKnowledge: String! = "unknown"
  aliases: JSON = null
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## ReferenceProductEdge

```graphql
type ReferenceProductEdge {
  cursor: String!
  node: ReferenceProduct!
}
```

## ReferenceProductResult

```graphql
type ReferenceProductResult {
  product: ReferenceProduct
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## ReferenceProductRevision

```graphql
type ReferenceProductRevision implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  productId: String!
  revision: Int!
  status: String!
  payload: JSON!
  contentHash: String!
  createdAt: DateTime!
}
```

## ReferenceRevisionConnection

```graphql
type ReferenceRevisionConnection {
  edges: [ReferenceRevisionEdge!]!
  pageInfo: PageInfo!
}
```

## ReferenceRevisionDraftInput

```graphql
input ReferenceRevisionDraftInput {
  productId: ID!
  payload: JSON!
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## ReferenceRevisionEdge

```graphql
type ReferenceRevisionEdge {
  cursor: String!
  node: ReferenceProductRevision!
}
```

## ReferenceRevisionFreezeInput

```graphql
input ReferenceRevisionFreezeInput {
  revisionId: ID!
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## ReferenceRevisionResult

```graphql
type ReferenceRevisionResult {
  revision: ReferenceProductRevision
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## ResearchMutation

```graphql
type ResearchMutation {
  sessionStart(input: SessionStartInput!): ResearchSessionResult!
  sessionEnd(input: SessionEndInput!): ResearchSessionResult!
  messagePost(input: MessagePostInput!): SessionMessageResult!
  turnRequest(input: TurnRequestInput!): TurnRequestResult!
  turnCancel(input: TurnCancelInput!): TurnCancelResult!
  questionRaise(input: QuestionRaiseInput!): TaskQuestionResult!
  questionResolve(input: QuestionResolveInput!): TaskQuestionResult!
  summaryCreate(input: SummaryCreateInput!): TaskSummaryResult!
}
```

## ResearchSession

```graphql
type ResearchSession implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  status: String!
  startContractRevisionId: String
  endSnapshot: JSON
  createdAt: DateTime!
  endedAt: DateTime
  startManifest: ContextManifest
}
```

## ResearchSessionConnection

```graphql
type ResearchSessionConnection {
  edges: [ResearchSessionEdge!]!
  pageInfo: PageInfo!
}
```

## ResearchSessionEdge

```graphql
type ResearchSessionEdge {
  cursor: String!
  node: ResearchSession!
}
```

## ResearchSessionResult

```graphql
type ResearchSessionResult {
  session: ResearchSession
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## ReviewRecordInput

```graphql
input ReviewRecordInput {
  recordId: ID!
  decision: String!
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## Run

```graphql
type Run implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  taskId: ID
  kind: String!
  status: String!
  attemptCount: Int!
  maxAttempts: Int!
  queuedAt: DateTime
  startedAt: DateTime
  finishedAt: DateTime
  cancelRequestedAt: DateTime
  deadlineAt: DateTime
  error: JSON
  resultSummary: JSON
  inputSummary: JSON
  attempts: [RunAttempt!]!
}
```

## RunAttempt

```graphql
type RunAttempt implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  status: String!
  queue: String!
  workerId: String
  attemptNumber: Int!
  enqueuedAt: DateTime!
  startedAt: DateTime
  finishedAt: DateTime
  error: JSON
}
```

## RunCancelInput

```graphql
input RunCancelInput {
  runId: ID!
  clientMutationId: String = null
}
```

## RunConnection

```graphql
type RunConnection {
  edges: [RunEdge!]!
  pageInfo: PageInfo!
}
```

## RunEdge

```graphql
type RunEdge {
  cursor: String!
  node: Run!
}
```

## RunFallbackInput

```graphql
input RunFallbackInput {
  runId: ID!
  clientMutationId: String = null
}
```

## RunRequestInput

```graphql
input RunRequestInput {
  taskId: ID!
  kind: String!
  request: JSON = null
  maxAttempts: Int = null
  requiresApproval: Boolean! = false
  clientMutationId: String = null
  idempotencyKey: String! = ""
}
```

## RunResult

```graphql
type RunResult {
  run: Run
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## RunsMutation

```graphql
type RunsMutation {
  quickDescribeStructure(input: QuickDescribeStructureInput!): RunResult!
  describeStructure(input: DescribeStructureInput!): RunResult!
  request(input: RunRequestInput!): RunResult!
  requestCancel(input: RunCancelInput!): RunResult!
  requestFallback(input: RunFallbackInput!): FallbackResult!
}
```

## SampleAddInput

```graphql
input SampleAddInput {
  batchId: ID!
  label: String!
  kind: String! = "aliquot"
  payload: JSON = null
  clientMutationId: String = null
}
```

## SampleResult

```graphql
type SampleResult {
  sample: LabSample
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## ServingPointerInfo

```graphql
type ServingPointerInfo {
  releaseId: ID
  revision: Int!
  reason: String!
  updatedAt: DateTime
}
```

## SessionBindResult

```graphql
type SessionBindResult {
  modelRelease: ModelReleaseInfo
  validation: JSON
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## SessionEndInput

```graphql
input SessionEndInput {
  sessionId: ID!
  clientMutationId: String = null
}
```

## SessionMessage

```graphql
type SessionMessage {
  id: String!
  role: String!
  kind: String!
  content: String!
  refs: JSON!
  createdAt: DateTime!
}
```

## SessionMessageConnection

```graphql
type SessionMessageConnection {
  edges: [SessionMessageEdge!]!
  pageInfo: PageInfo!
}
```

## SessionMessageEdge

```graphql
type SessionMessageEdge {
  cursor: String!
  node: SessionMessage!
}
```

## SessionMessageResult

```graphql
type SessionMessageResult {
  message: SessionMessage
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## SessionModelBindInput

```graphql
input SessionModelBindInput {
  sessionId: ID!
  clientMutationId: String = null
}
```

## SessionModelPinInfo

```graphql
type SessionModelPinInfo {
  sessionId: ID!
  releaseId: ID
  createdAt: DateTime!
}
```

## SessionStartInput

```graphql
input SessionStartInput {
  taskId: ID!
  tokenBudget: Int = null
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## SourceRevokeInput

```graphql
input SourceRevokeInput {
  artifactId: String!
  reason: String!
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## SourceRevokeResult

```graphql
type SourceRevokeResult {
  report: JSON
  revocationId: String
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## String

```graphql
"""UTF-8 text string."""
scalar String
```

## SummaryCreateInput

```graphql
input SummaryCreateInput {
  taskId: ID!
  body: String!
  sourceIds: [String!]!
  generator: String!
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## Task

```graphql
type Task implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  title: String!
  mode: String!
  workflowState: String!
  targetKind: String!
  objective: String
  closureDecision: String
  evaluationCycle: Int!
  unresolvedInputs: [String!]!
  createdAt: DateTime!
  optimizationCampaigns: [OptimizationCampaignInfo!]!
  analyticalSeries: [AnalyticalSeriesInfo!]!
  analyticalComparisons: [AnalyticalComparisonInfo!]!
  project: Project
  invalidInputs: [JSON!]!
}
```

## TaskCloseInput

```graphql
input TaskCloseInput {
  taskId: ID!
  closureDecision: String!
  packet: JSON = null
  candidateRevisionId: ID = null
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## TaskConnection

```graphql
type TaskConnection {
  edges: [TaskEdge!]!
  pageInfo: PageInfo!
}
```

## TaskCreateInput

```graphql
input TaskCreateInput {
  title: String!
  mode: String!
  projectId: ID = null
  objective: String = null
  targetKind: String = null
  modeInputs: JSON = null
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## TaskCreateResult

```graphql
type TaskCreateResult {
  task: Task
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## TaskEdge

```graphql
type TaskEdge {
  cursor: String!
  node: Task!
}
```

## TaskQuestion

```graphql
type TaskQuestion implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  question: String!
  blocking: Boolean!
  status: String!
  resolution: String
  createdAt: DateTime!
}
```

## TaskQuestionResult

```graphql
type TaskQuestionResult {
  question: TaskQuestion
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## TaskReopenInput

```graphql
input TaskReopenInput {
  taskId: ID!
  reason: String!
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## TaskResult

```graphql
type TaskResult {
  task: Task
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## TaskSummary

```graphql
type TaskSummary {
  id: String!
  body: String!
  sourceIds: JSON!
  coverage: JSON!
  generator: String!
  contractRevisionId: String
  stale: Boolean!
  createdAt: DateTime!
}
```

## TaskSummaryResult

```graphql
type TaskSummaryResult {
  summaryId: String
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## TaskTransitionInput

```graphql
input TaskTransitionInput {
  taskId: ID!
  toState: String!
  reason: String = null
  expectedVersion: Int = null
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## TrainingRunApproveInput

```graphql
input TrainingRunApproveInput {
  trainingRunId: ID!
  decision: String!
  rationale: String = null
  clientMutationId: String = null
}
```

## TrainingRunCreateInput

```graphql
input TrainingRunCreateInput {
  snapshotId: ID!
  name: String!
  taskId: ID = null
  spec: JSON = null
  clientMutationId: String = null
}
```

## TrainingRunExecuteInput

```graphql
input TrainingRunExecuteInput {
  trainingRunId: ID!
  attemptId: ID!
  clientMutationId: String = null
}
```

## TrainingRunIdInput

```graphql
input TrainingRunIdInput {
  trainingRunId: ID!
  clientMutationId: String = null
}
```

## TrainingRunInfo

```graphql
type TrainingRunInfo {
  id: ID!
  taskId: String
  name: String!
  state: String!
  snapshotId: String
  snapshotDigest: String
  spec: JSON!
  specDigest: String
  datasetDigest: String
  datasetManifest: JSON
  telemetry: JSON
  checkpoints: JSON
  resumeFrom: JSON
  provenance: JSON
  capability: JSON
  error: JSON
  runId: String
  attemptId: String
  approvalId: String
  createdAt: DateTime!
  updatedAt: DateTime
}
```

## TrainingRunResult

```graphql
type TrainingRunResult {
  trainingRun: TrainingRunInfo
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## TrainingRunTransitionInput

```graphql
input TrainingRunTransitionInput {
  trainingRunId: ID!
  toState: String!
  rationale: String = null
  clientMutationId: String = null
}
```

## TurnCancelInput

```graphql
input TurnCancelInput {
  sessionId: ID!
  turnId: String!
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## TurnCancelResult

```graphql
type TurnCancelResult {
  recorded: Boolean!
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## TurnRequestInput

```graphql
input TurnRequestInput {
  sessionId: ID!
  content: String!
  turnId: String!
  providerId: ID = null
  providerRevision: Int = null
  allowProviderDataTransfer: Boolean! = false
  idempotencyKey: String = null
  clientMutationId: String = null
}
```

## TurnRequestResult

```graphql
type TurnRequestResult {
  turnId: String
  finishedReason: String
  finalMessage: SessionMessage
  toolCalls: Int!
  detail: String
  errors: [DomainErrorPayload!]!
  clientMutationId: String
}
```

## User

```graphql
type User implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  displayName: String!
  kind: String!
}
```

## Workspace

```graphql
type Workspace implements Node {
  """The Globally Unique ID of this object"""
  id: ID!
  slug: String!
  displayName: String!
}
```

## Query

See the [complete query reference](graphql-query.md).

## Mutation

See the [complete mutation reference](graphql-mutation.md).
