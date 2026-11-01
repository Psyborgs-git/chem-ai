# GraphQL mutation reference

[Transport, IDs, pagination and errors](graphql-overview.md). Declarations below are generated from the committed SDL, including nested mutation namespaces. Look up argument and response structures in the [type catalog](graphql-types.md).

## analytical.compare

Compare analytical records using compatible methods, transforms and scope.

```graphql
compare(input: AnalyticalCompareInput!): AnalyticalResult!
```

Analytical ingest/compare preserve source lineage, method/unit compatibility and quality state. Unsupported or invalid formats fail explicitly; analysis is not an instrument-control interface.

Return contract: [AnalyticalResult](graphql-types.md#analyticalresult).

Argument contracts: [AnalyticalCompareInput](graphql-types.md#analyticalcompareinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `FORBIDDEN` | only humans can run a comparison |
| `IDEMPOTENCY_MISMATCH` | creation key reused with a different comparison |
| `VALIDATION` | bounded idempotency key required |
| `VALIDATION` | spec must be an object |

Exact state, permission and validation rules: [AnalyticalMutation.compare](graphql-contracts.md#analyticalmutationcompare), [AnalyticsService.compare](graphql-contracts.md#analyticsservicecompare).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:6689`.

## analytical.ingest

Ingest analytical data into a provenance-preserving typed record.

```graphql
ingest(input: AnalyticalIngestInput!): AnalyticalResult!
```

Analytical ingest/compare preserve source lineage, method/unit compatibility and quality state. Unsupported or invalid formats fail explicitly; analysis is not an instrument-control interface.

Return contract: [AnalyticalResult](graphql-types.md#analyticalresult).

Argument contracts: [AnalyticalIngestInput](graphql-types.md#analyticalingestinput).

**Capability checks declared in these contracts:** `edit_task`, `manage_sources`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `FORBIDDEN` | only humans can ingest analytical data |
| `IDEMPOTENCY_MISMATCH` | creation key reused with a different ingest |
| `VALIDATION` | bounded idempotency key required |
| `VALIDATION` | malformed artifact id |
| `VALIDATION` | spec must be an object |

Exact state, permission and validation rules: [AnalyticalMutation.ingest](graphql-contracts.md#analyticalmutationingest), [AnalyticsService.ingest](graphql-contracts.md#analyticsserviceingest).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:6654`.

## candidates.create

Propose a candidate hypothesis and bind its entity/evidence revisions.

```graphql
create(input: CandidateCreateInput!): CandidateRevisionResult!
```

Candidate and patch services enforce task access, version checks and explicit submit/review decisions. Model suggestions do not create human approvals. Read the input/result types for required decision fields.

Return contract: [CandidateRevisionResult](graphql-types.md#candidaterevisionresult).

Argument contracts: [CandidateCreateInput](graphql-types.md#candidatecreateinput).

**Capability checks declared in these contracts:** `propose_candidate`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `NOT_FOUND` | task |
| `VALIDATION` | parent candidate belongs to a different task |

Exact state, permission and validation rules: [CandidatesMutation.create](graphql-contracts.md#candidatesmutationcreate), [CandidateService.create_candidate](graphql-contracts.md#candidateservicecreate_candidate).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4554`.

## candidates.patchPropose

Propose a bounded revision patch without applying it as an approval.

```graphql
patchPropose(input: CandidatePatchProposeInput!): CandidatePatchResult!
```

Candidate and patch services enforce task access, version checks and explicit submit/review decisions. Model suggestions do not create human approvals. Read the input/result types for required decision fields.

Return contract: [CandidatePatchResult](graphql-types.md#candidatepatchresult).

Argument contracts: [CandidatePatchProposeInput](graphql-types.md#candidatepatchproposeinput).

**Capability checks declared in these contracts:** `propose_candidate`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | patch must not be empty |

Exact state, permission and validation rules: [CandidatesMutation.patch_propose](graphql-contracts.md#candidatesmutationpatch_propose), [CandidateService.propose_patch](graphql-contracts.md#candidateservicepropose_patch).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4648`.

## candidates.patchReview

Review a proposed patch and apply only its authorized accepted changes.

```graphql
patchReview(input: CandidatePatchReviewInput!): CandidatePatchResult!
```

Candidate and patch services enforce task access, version checks and explicit submit/review decisions. Model suggestions do not create human approvals. Read the input/result types for required decision fields.

Return contract: [CandidatePatchResult](graphql-types.md#candidatepatchresult).

Argument contracts: [CandidatePatchReviewInput](graphql-types.md#candidatepatchreviewinput).

**Capability checks declared in these contracts:** `review_science`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | a rejection reason is required |

Exact state, permission and validation rules: [CandidatesMutation.patch_review](graphql-contracts.md#candidatesmutationpatch_review), [CandidateService.review_patch](graphql-contracts.md#candidateservicereview_patch).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4692`.

## candidates.review

Accept or reject a submitted candidate through human review.

```graphql
review(input: CandidateReviewInput!): CandidateRevisionResult!
```

Candidate and patch services enforce task access, version checks and explicit submit/review decisions. Model suggestions do not create human approvals. Read the input/result types for required decision fields.

Return contract: [CandidateRevisionResult](graphql-types.md#candidaterevisionresult).

Argument contracts: [CandidateReviewInput](graphql-types.md#candidatereviewinput).

**Capability checks declared in these contracts:** `review_science`. Ownership and delegated checks also apply.

Exact state, permission and validation rules: [CandidatesMutation.review](graphql-contracts.md#candidatesmutationreview), [CandidateService.review_candidate](graphql-contracts.md#candidateservicereview_candidate).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4626`.

## candidates.submit

Submit a draft candidate for scientific review.

```graphql
submit(input: CandidateSubmitInput!): CandidateRevisionResult!
```

Candidate and patch services enforce task access, version checks and explicit submit/review decisions. Model suggestions do not create human approvals. Read the input/result types for required decision fields.

Return contract: [CandidateRevisionResult](graphql-types.md#candidaterevisionresult).

Argument contracts: [CandidateSubmitInput](graphql-types.md#candidatesubmitinput).

**Capability checks declared in these contracts:** `propose_candidate`. Ownership and delegated checks also apply.

Exact state, permission and validation rules: [CandidatesMutation.submit](graphql-contracts.md#candidatesmutationsubmit), [CandidateService.submit_candidate](graphql-contracts.md#candidateservicesubmit_candidate).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4604`.

## contractDraftCreate

Create a new editable success-contract revision for a task.

```graphql
contractDraftCreate(input: ContractDraftCreateInput!): ContractRevisionResult!
```

Requires edit_task in the task project. Canonical contract validation runs before write; a draft can retain explicit unknown top-level fields for review. Task-row locking serializes concurrent max+1 revision allocation. The payload is hashed and status starts draft; no missing scientific threshold is invented.

Return contract: [ContractRevisionResult](graphql-types.md#contractrevisionresult).

Argument contracts: [ContractDraftCreateInput](graphql-types.md#contractdraftcreateinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

Exact state, permission and validation rules: [TaskService.draft_contract](graphql-contracts.md#taskservicedraft_contract), [validate_draft_payload](graphql-contracts.md#validate_draft_payload).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2912`.

## contractFreeze

Bind a complete reviewed draft as the task’s current success contract.

```graphql
contractFreeze(input: ContractFreezeInput!): ContractRevisionResult!
```

Requires edit_task in the task project. revisionId must reference an accessible draft; a frozen/superseded revision cannot be frozen again. Canonical freeze validation rejects unresolved unknowns, unknown vocabulary and incomplete metric bounds. Under task-row lock the prior frozen contract is superseded, the chosen revision becomes frozen, and task version/current-contract pointer advance. Optional idempotencyKey binds the freeze retry to its payload.

Return contract: [ContractRevisionResult](graphql-types.md#contractrevisionresult).

Argument contracts: [ContractFreezeInput](graphql-types.md#contractfreezeinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `NOT_FOUND` | contract revision |

Exact state, permission and validation rules: [TaskService.freeze_contract](graphql-contracts.md#taskservicefreeze_contract), [validate_freeze_payload](graphql-contracts.md#validate_freeze_payload).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2977`.

## evidence.claimCreate

Create an evidence claim with explicit source/record provenance.

```graphql
claimCreate(input: ClaimCreateInput!): EvidenceClaimResult!
```

Claim creation, review and linking require valid source/record provenance, task access and review capability where applicable. Evidence type and quality are preserved; computation is not relabeled as laboratory measurement.

Return contract: [EvidenceClaimResult](graphql-types.md#evidenceclaimresult).

Argument contracts: [ClaimCreateInput](graphql-types.md#claimcreateinput).

**Capability checks declared in these contracts:** `manage_sources`. Ownership and delegated checks also apply.

Exact state, permission and validation rules: [EvidenceMutation.claim_create](graphql-contracts.md#evidencemutationclaim_create), [ClaimService.create_claim](graphql-contracts.md#claimservicecreate_claim).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4910`.

## evidence.claimLink

Link a claim as supporting or contradicting a scoped research entity.

```graphql
claimLink(input: ClaimLinkInput!): ClaimLinkResult!
```

Claim creation, review and linking require valid source/record provenance, task access and review capability where applicable. Evidence type and quality are preserved; computation is not relabeled as laboratory measurement.

Return contract: [ClaimLinkResult](graphql-types.md#claimlinkresult).

Argument contracts: [ClaimLinkInput](graphql-types.md#claimlinkinput).

**Capability checks declared in these contracts:** `review_science`. Ownership and delegated checks also apply.

Exact state, permission and validation rules: [EvidenceMutation.claim_link](graphql-contracts.md#evidencemutationclaim_link), [ClaimService.link](graphql-contracts.md#claimservicelink).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4983`.

## evidence.claimReview

Record the scientific quality/review decision on an evidence claim.

```graphql
claimReview(input: ClaimReviewInput!): EvidenceClaimResult!
```

Claim creation, review and linking require valid source/record provenance, task access and review capability where applicable. Evidence type and quality are preserved; computation is not relabeled as laboratory measurement.

Return contract: [EvidenceClaimResult](graphql-types.md#evidenceclaimresult).

Argument contracts: [ClaimReviewInput](graphql-types.md#claimreviewinput).

**Capability checks declared in these contracts:** `review_science`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `FORBIDDEN` | evidence review requires a human principal |
| `VALIDATION` | decision must be accepted\|rejected |

Exact state, permission and validation rules: [EvidenceMutation.claim_review](graphql-contracts.md#evidencemutationclaim_review), [ClaimService.review](graphql-contracts.md#claimservicereview).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4950`.

## exports.decide

Approve or reject a prepared export using its reviewed digest and recipient scope.

```graphql
decide(input: ExportDecideInput!): ExportReviewResult!
```

Export preparation and decisions enforce source rights/provenance, classification, exact digest/recipient/scope and explicit human approval. Stale or absent approvals block egress; there is no automatic cloud fallback.

Return contract: [ExportReviewResult](graphql-types.md#exportreviewresult).

Argument contracts: [ExportDecideInput](graphql-types.md#exportdecideinput).

**Capability checks declared in these contracts:** `review_export`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | decision must be approved\|rejected |

Exact state, permission and validation rules: [ExportsMutation.decide](graphql-contracts.md#exportsmutationdecide), [TransformService.payload](graphql-contracts.md#transformservicepayload), [TransformService.decide](graphql-contracts.md#transformservicedecide), [TransformService.review_view](graphql-contracts.md#transformservicereview_view).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5370`.

## exports.prepare

Prepare an exact export manifest for policy and human review.

```graphql
prepare(input: ExportPrepareInput!): ExportReviewResult!
```

Export preparation and decisions enforce source rights/provenance, classification, exact digest/recipient/scope and explicit human approval. Stale or absent approvals block egress; there is no automatic cloud fallback.

Return contract: [ExportReviewResult](graphql-types.md#exportreviewresult).

Argument contracts: [ExportPrepareInput](graphql-types.md#exportprepareinput).

**Capability checks declared in these contracts:** `review_export`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | snapshot is not frozen |
| `CONFLICT` | snapshot source drift — refreeze before export |
| `VALIDATION` | snapshot task does not match the proposed run's task |

Exact state, permission and validation rules: [ExportsMutation.prepare](graphql-contracts.md#exportsmutationprepare), [TransformService.prepare](graphql-contracts.md#transformserviceprepare), [TransformService.review_view](graphql-contracts.md#transformservicereview_view).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5337`.

## exports.setClassification

Set reviewed data classification used by export eligibility policy.

```graphql
setClassification(input: ExportSetClassificationInput!): ExportReviewResult!
```

Export preparation and decisions enforce source rights/provenance, classification, exact digest/recipient/scope and explicit human approval. Stale or absent approvals block egress; there is no automatic cloud fallback.

Return contract: [ExportReviewResult](graphql-types.md#exportreviewresult).

Argument contracts: [ExportSetClassificationInput](graphql-types.md#exportsetclassificationinput).

**Capability checks declared in these contracts:** `review_export`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | a reviewed classification change requires a rationale |

Exact state, permission and validation rules: [ExportsMutation.set_classification](graphql-contracts.md#exportsmutationset_classification), [TransformService.set_classification](graphql-contracts.md#transformserviceset_classification), [TransformService.review_view](graphql-contracts.md#transformservicereview_view).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5397`.

## formulations.familyCreate

Create the family that groups related formulation revisions.

```graphql
familyCreate(input: FormulationFamilyCreateInput!): FormulationFamilyResult!
```

Formulation/process drafts are versioned and validated for identities, units, quantities and composition totals. Accepting a revision freezes the reviewed state; expected revisions and idempotency are checked where declared.

Return contract: [FormulationFamilyResult](graphql-types.md#formulationfamilyresult).

Argument contracts: [FormulationFamilyCreateInput](graphql-types.md#formulationfamilycreateinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | name is required |

Exact state, permission and validation rules: [FormulationsMutation.family_create](graphql-contracts.md#formulationsmutationfamily_create), [FormulationService.create_family](graphql-contracts.md#formulationservicecreate_family).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4337`.

## formulations.processAccept

Accept a reviewed process revision without mutating prior revisions.

```graphql
processAccept(input: ProcessRevisionIdInput!): ProcessRevisionResult!
```

Formulation/process drafts are versioned and validated for identities, units, quantities and composition totals. Accepting a revision freezes the reviewed state; expected revisions and idempotency are checked where declared.

Return contract: [ProcessRevisionResult](graphql-types.md#processrevisionresult).

Argument contracts: [ProcessRevisionIdInput](graphql-types.md#processrevisionidinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `NOT_FOUND` | process revision |

Exact state, permission and validation rules: [FormulationsMutation.process_accept](graphql-contracts.md#formulationsmutationprocess_accept), [FormulationService.accept_process_revision](graphql-contracts.md#formulationserviceaccept_process_revision).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4512`.

## formulations.processDraft

Draft a process revision linked to its research context.

```graphql
processDraft(input: ProcessRevisionDraftInput!): ProcessRevisionResult!
```

Formulation/process drafts are versioned and validated for identities, units, quantities and composition totals. Accepting a revision freezes the reviewed state; expected revisions and idempotency are checked where declared.

Return contract: [ProcessRevisionResult](graphql-types.md#processrevisionresult).

Argument contracts: [ProcessRevisionDraftInput](graphql-types.md#processrevisiondraftinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | a process revision needs at least one step |
| `VALIDATION` | payload must be an object |

Exact state, permission and validation rules: [FormulationsMutation.process_draft](graphql-contracts.md#formulationsmutationprocess_draft), [FormulationService.draft_process_revision](graphql-contracts.md#formulationservicedraft_process_revision).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4468`.

## formulations.revisionAccept

Accept a validated formulation revision as an immutable reviewed state.

```graphql
revisionAccept(input: FormulationRevisionIdInput!): FormulationRevisionResult!
```

Formulation/process drafts are versioned and validated for identities, units, quantities and composition totals. Accepting a revision freezes the reviewed state; expected revisions and idempotency are checked where declared.

Return contract: [FormulationRevisionResult](graphql-types.md#formulationrevisionresult).

Argument contracts: [FormulationRevisionIdInput](graphql-types.md#formulationrevisionidinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | a complete revision needs at least one ingredient |
| `VALIDATION` | declaredTotal is required for a complete revision |
| `VALIDATION` | only a complete revision can be accepted |

Exact state, permission and validation rules: [FormulationsMutation.revision_accept](graphql-contracts.md#formulationsmutationrevision_accept), [FormulationService.accept_revision](graphql-contracts.md#formulationserviceaccept_revision).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4430`.

## formulations.revisionDraft

Draft a formulation revision with explicit identities, amounts and basis.

```graphql
revisionDraft(input: FormulationRevisionDraftInput!): FormulationRevisionResult!
```

Formulation/process drafts are versioned and validated for identities, units, quantities and composition totals. Accepting a revision freezes the reviewed state; expected revisions and idempotency are checked where declared.

Return contract: [FormulationRevisionResult](graphql-types.md#formulationrevisionresult).

Argument contracts: [FormulationRevisionDraftInput](graphql-types.md#formulationrevisiondraftinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | parent revision belongs to a different family |
| `VALIDATION` | payload must be an object |

Exact state, permission and validation rules: [FormulationsMutation.revision_draft](graphql-contracts.md#formulationsmutationrevision_draft), [FormulationService.draft_revision](graphql-contracts.md#formulationservicedraft_revision).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4372`.

## imports.artifactImport

Start quarantine/extraction for an accessible uploaded artifact.

```graphql
artifactImport(input: ImportArtifactInput!): ImportBatchResult!
```

Imports remain quarantined until reviewed and promoted. Source revocation propagates invalidation to derived evidence/context. Artifact import IDs must be accessible; record review is a separate action.

Return contract: [ImportBatchResult](graphql-types.md#importbatchresult).

Argument contracts: [ImportArtifactInput](graphql-types.md#importartifactinput).

**Capability checks declared in these contracts:** `manage_sources`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | artifact is revoked — a revoked source cannot re-enter the pipeline |
| `CONFLICT` | no vault configured for byte reads |
| `FORBIDDEN` | extraction right is denied for this artifact |
| `NOT_FOUND` | artifact |
| `VALIDATION` | malformed artifact id |

Exact state, permission and validation rules: [ImportsMutation.artifact_import](graphql-contracts.md#importsmutationartifact_import), [ImportService.import_artifact](graphql-contracts.md#importserviceimport_artifact).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4774`.

## imports.recordPromote

Promote a reviewed extracted record while preserving source lineage.

```graphql
recordPromote(input: PromoteRecordInput!): EvidenceClaimResult!
```

Imports remain quarantined until reviewed and promoted. Source revocation propagates invalidation to derived evidence/context. Artifact import IDs must be accessible; record review is a separate action.

Return contract: [EvidenceClaimResult](graphql-types.md#evidenceclaimresult).

Argument contracts: [PromoteRecordInput](graphql-types.md#promoterecordinput).

**Capability checks declared in these contracts:** `manage_sources`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | a rejected record cannot be promoted |

Exact state, permission and validation rules: [ImportsMutation.record_promote](graphql-contracts.md#importsmutationrecord_promote), [ClaimService.promote_record](graphql-contracts.md#claimservicepromote_record).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4860`.

## imports.recordReview

Review an extracted record before it can be promoted as evidence.

```graphql
recordReview(input: ReviewRecordInput!): ExtractedRecordResult!
```

Imports remain quarantined until reviewed and promoted. Source revocation propagates invalidation to derived evidence/context. Artifact import IDs must be accessible; record review is a separate action.

Return contract: [ExtractedRecordResult](graphql-types.md#extractedrecordresult).

Argument contracts: [ReviewRecordInput](graphql-types.md#reviewrecordinput).

**Capability checks declared in these contracts:** `manage_sources`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `FORBIDDEN` | import review requires a human principal |
| `VALIDATION` | decision must be accepted\|rejected |

Exact state, permission and validation rules: [ImportsMutation.record_review](graphql-contracts.md#importsmutationrecord_review), [ImportService.review_record](graphql-contracts.md#importservicereview_record).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4823`.

## imports.sourceRevoke

Revoke source use and invalidate downstream claims/context consistently.

```graphql
sourceRevoke(input: SourceRevokeInput!): SourceRevokeResult!
```

Imports remain quarantined until reviewed and promoted. Source revocation propagates invalidation to derived evidence/context. Artifact import IDs must be accessible; record review is a separate action.

Return contract: [SourceRevokeResult](graphql-types.md#sourcerevokeresult).

Argument contracts: [SourceRevokeInput](graphql-types.md#sourcerevokeinput).

**Capability checks declared in these contracts:** `manage_sources`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | artifact already has a revocation record |
| `CONFLICT` | artifact is already revoked |
| `FORBIDDEN` | source revocation requires a human principal |
| `VALIDATION` | a revocation reason is required |
| `VALIDATION` | malformed artifact id |

Exact state, permission and validation rules: [ImportsMutation.source_revoke](graphql-contracts.md#importsmutationsource_revoke), [RevocationService.revoke](graphql-contracts.md#revocationservicerevoke).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4728`.

## lab.measurements.actualsRecord

Record what was actually done in an existing lab execution.

```graphql
actualsRecord(input: ActualsRecordInput!): ExecutionResult!
```

Experiment plans and measurement commands enforce lab/reviewer capabilities, approved plan versions, execution state, units, quality and source provenance. Corrections append history rather than overwriting the scientific record; approval cannot be delegated to agent principals.

Return contract: [ExecutionResult](graphql-types.md#executionresult).

Argument contracts: [ActualsRecordInput](graphql-types.md#actualsrecordinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | execution is closed |

Exact state, permission and validation rules: [LabMeasurementsMutation.actuals_record](graphql-contracts.md#labmeasurementsmutationactuals_record), [LabMeasurementService.record_actuals](graphql-contracts.md#labmeasurementservicerecord_actuals).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:6220`.

## lab.measurements.batchAdd

Add a batch record to its accessible lab execution.

```graphql
batchAdd(input: BatchAddInput!): BatchResult!
```

Experiment plans and measurement commands enforce lab/reviewer capabilities, approved plan versions, execution state, units, quality and source provenance. Corrections append history rather than overwriting the scientific record; approval cannot be delegated to agent principals.

Return contract: [BatchResult](graphql-types.md#batchresult).

Argument contracts: [BatchAddInput](graphql-types.md#batchaddinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | execution is closed |
| `VALIDATION` | batch label required |

Exact state, permission and validation rules: [LabMeasurementsMutation.batch_add](graphql-contracts.md#labmeasurementsmutationbatch_add), [LabMeasurementService.add_batch](graphql-contracts.md#labmeasurementserviceadd_batch).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:6246`.

## lab.measurements.executionClose

Close a lab execution while retaining its samples and recorded actuals.

```graphql
executionClose(input: ExecutionCloseInput!): ExecutionResult!
```

Experiment plans and measurement commands enforce lab/reviewer capabilities, approved plan versions, execution state, units, quality and source provenance. Corrections append history rather than overwriting the scientific record; approval cannot be delegated to agent principals.

Return contract: [ExecutionResult](graphql-types.md#executionresult).

Argument contracts: [ExecutionCloseInput](graphql-types.md#executioncloseinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | execution is already closed |
| `VALIDATION` | status must be completed\|stopped |

Exact state, permission and validation rules: [LabMeasurementsMutation.execution_close](graphql-contracts.md#labmeasurementsmutationexecution_close), [LabMeasurementService.close_execution](graphql-contracts.md#labmeasurementserviceclose_execution).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:6197`.

## lab.measurements.executionHistoricalImport

Import a historical execution with explicit provenance and quality state.

```graphql
executionHistoricalImport(input: ExecutionHistoricalInput!): ExecutionResult!
```

Experiment plans and measurement commands enforce lab/reviewer capabilities, approved plan versions, execution state, units, quality and source provenance. Corrections append history rather than overwriting the scientific record; approval cannot be delegated to agent principals.

Return contract: [ExecutionResult](graphql-types.md#executionresult).

Argument contracts: [ExecutionHistoricalInput](graphql-types.md#executionhistoricalinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

Exact state, permission and validation rules: [LabMeasurementsMutation.execution_historical_import](graphql-contracts.md#labmeasurementsmutationexecution_historical_import), [LabMeasurementService.import_historical](graphql-contracts.md#labmeasurementserviceimport_historical).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:6171`.

## lab.measurements.executionOpen

Open a lab execution against the required approved plan.

```graphql
executionOpen(input: ExecutionOpenInput!): ExecutionResult!
```

Experiment plans and measurement commands enforce lab/reviewer capabilities, approved plan versions, execution state, units, quality and source provenance. Corrections append history rather than overwriting the scientific record; approval cannot be delegated to agent principals.

Return contract: [ExecutionResult](graphql-types.md#executionresult).

Argument contracts: [ExecutionOpenInput](graphql-types.md#executionopeninput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | only an approved plan can be executed |

Exact state, permission and validation rules: [LabMeasurementsMutation.execution_open](graphql-contracts.md#labmeasurementsmutationexecution_open), [LabMeasurementService.open_execution](graphql-contracts.md#labmeasurementserviceopen_execution).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:6150`.

## lab.measurements.measurementAmend

Append a measurement correction while preserving the original record.

```graphql
measurementAmend(input: MeasurementAmendInput!): MeasurementResult!
```

Experiment plans and measurement commands enforce lab/reviewer capabilities, approved plan versions, execution state, units, quality and source provenance. Corrections append history rather than overwriting the scientific record; approval cannot be delegated to agent principals.

Return contract: [MeasurementResult](graphql-types.md#measurementresult).

Argument contracts: [MeasurementAmendInput](graphql-types.md#measurementamendinput).

**Capability checks declared in these contracts:** `review_measurement`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | only an accepted measurement can be amended |
| `VALIDATION` | amendment reason required |

Exact state, permission and validation rules: [LabMeasurementsMutation.measurement_amend](graphql-contracts.md#labmeasurementsmutationmeasurement_amend), [LabMeasurementService.amend](graphql-contracts.md#labmeasurementserviceamend).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:6481`.

## lab.measurements.measurementApplicability

Set a measurement’s reviewed applicability flag and explanatory note.

```graphql
measurementApplicability(input: MeasurementApplicabilityInput!): MeasurementResult!
```

Experiment plans and measurement commands enforce lab/reviewer capabilities, approved plan versions, execution state, units, quality and source provenance. Corrections append history rather than overwriting the scientific record; approval cannot be delegated to agent principals.

Return contract: [MeasurementResult](graphql-types.md#measurementresult).

Argument contracts: [MeasurementApplicabilityInput](graphql-types.md#measurementapplicabilityinput).

**Capability checks declared in these contracts:** `review_measurement`. Ownership and delegated checks also apply.

Exact state, permission and validation rules: [LabMeasurementsMutation.measurement_applicability](graphql-contracts.md#labmeasurementsmutationmeasurement_applicability), [LabMeasurementService.set_applicability](graphql-contracts.md#labmeasurementserviceset_applicability).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:6386`.

## lab.measurements.measurementMapApplicability

Map measurement applicability with explicit method/metric compatibility.

```graphql
measurementMapApplicability(input: MeasurementApplicabilityMapInput!): ApplicabilityMapResult!
```

Experiment plans and measurement commands enforce lab/reviewer capabilities, approved plan versions, execution state, units, quality and source provenance. Corrections append history rather than overwriting the scientific record; approval cannot be delegated to agent principals.

Return contract: [ApplicabilityMapResult](graphql-types.md#applicabilitymapresult).

Argument contracts: [MeasurementApplicabilityMapInput](graphql-types.md#measurementapplicabilitymapinput).

**Capability checks declared in these contracts:** `review_measurement`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `NOT_FOUND` | applicability mapping |
| `NOT_FOUND` | candidate revision not found |
| `NOT_FOUND` | contract revision not found |
| `VALIDATION` | applicability mapping requires a rationale |

Exact state, permission and validation rules: [LabMeasurementsMutation.measurement_map_applicability](graphql-contracts.md#labmeasurementsmutationmeasurement_map_applicability), [LabMeasurementService.withdraw_applicability](graphql-contracts.md#labmeasurementservicewithdraw_applicability), [LabMeasurementService.record_applicability](graphql-contracts.md#labmeasurementservicerecord_applicability).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:6417`.

## lab.measurements.measurementRecord

Record a typed measurement value, method, repeat type and conditions.

```graphql
measurementRecord(input: MeasurementRecordInput!): MeasurementResult!
```

Experiment plans and measurement commands enforce lab/reviewer capabilities, approved plan versions, execution state, units, quality and source provenance. Corrections append history rather than overwriting the scientific record; approval cannot be delegated to agent principals.

Return contract: [MeasurementResult](graphql-types.md#measurementresult).

Argument contracts: [MeasurementRecordInput](graphql-types.md#measurementrecordinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | execution is closed |
| `VALIDATION` | method is required |

Exact state, permission and validation rules: [LabMeasurementsMutation.measurement_record](graphql-contracts.md#labmeasurementsmutationmeasurement_record), [LabMeasurementService.record_measurement](graphql-contracts.md#labmeasurementservicerecord_measurement).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:6317`.

## lab.measurements.measurementReview

Review measurement quality before using it in scientific conclusions.

```graphql
measurementReview(input: MeasurementReviewInput!): MeasurementResult!
```

Experiment plans and measurement commands enforce lab/reviewer capabilities, approved plan versions, execution state, units, quality and source provenance. Corrections append history rather than overwriting the scientific record; approval cannot be delegated to agent principals.

Return contract: [MeasurementResult](graphql-types.md#measurementresult).

Argument contracts: [MeasurementReviewInput](graphql-types.md#measurementreviewinput).

**Capability checks declared in these contracts:** `review_measurement`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | decision must be accepted\|rejected |

Exact state, permission and validation rules: [LabMeasurementsMutation.measurement_review](graphql-contracts.md#labmeasurementsmutationmeasurement_review), [LabMeasurementService.review](graphql-contracts.md#labmeasurementservicereview).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:6355`.

## lab.measurements.sampleAdd

Add a sample with its batch and execution lineage.

```graphql
sampleAdd(input: SampleAddInput!): SampleResult!
```

Experiment plans and measurement commands enforce lab/reviewer capabilities, approved plan versions, execution state, units, quality and source provenance. Corrections append history rather than overwriting the scientific record; approval cannot be delegated to agent principals.

Return contract: [SampleResult](graphql-types.md#sampleresult).

Argument contracts: [SampleAddInput](graphql-types.md#sampleaddinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | sample label required |

Exact state, permission and validation rules: [LabMeasurementsMutation.sample_add](graphql-contracts.md#labmeasurementsmutationsample_add), [LabMeasurementService.add_sample](graphql-contracts.md#labmeasurementserviceadd_sample).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:6281`.

## lab.packetExport

Create the reviewed experiment packet rather than executing an instrument.

```graphql
packetExport(input: PlanIdInput!): PacketResult!
```

Experiment plans and measurement commands enforce lab/reviewer capabilities, approved plan versions, execution state, units, quality and source provenance. Corrections append history rather than overwriting the scientific record; approval cannot be delegated to agent principals.

Return contract: [PacketResult](graphql-types.md#packetresult).

Argument contracts: [PlanIdInput](graphql-types.md#planidinput).

**Capability checks declared in these contracts:** `read_project`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | only an approved plan can produce a packet |

Exact state, permission and validation rules: [LabMutation.packet_export](graphql-contracts.md#labmutationpacket_export), [LabPlanService.export_packet](graphql-contracts.md#labplanserviceexport_packet).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5940`.

## lab.planCreate

Draft an experiment plan linked to the task and candidate.

```graphql
planCreate(input: PlanCreateInput!): PlanResult!
```

Experiment plans and measurement commands enforce lab/reviewer capabilities, approved plan versions, execution state, units, quality and source provenance. Corrections append history rather than overwriting the scientific record; approval cannot be delegated to agent principals.

Return contract: [PlanResult](graphql-types.md#planresult).

Argument contracts: [PlanCreateInput](graphql-types.md#plancreateinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | payload must be an object |
| `VALIDATION` | title is required |

Exact state, permission and validation rules: [LabMutation.plan_create](graphql-contracts.md#labmutationplan_create), [LabPlanService.create](graphql-contracts.md#labplanservicecreate).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5799`.

## lab.planReview

Approve or reject the submitted experiment plan and reviewed scope.

```graphql
planReview(input: PlanReviewInput!): PlanResult!
```

Experiment plans and measurement commands enforce lab/reviewer capabilities, approved plan versions, execution state, units, quality and source provenance. Corrections append history rather than overwriting the scientific record; approval cannot be delegated to agent principals.

Return contract: [PlanResult](graphql-types.md#planresult).

Argument contracts: [PlanReviewInput](graphql-types.md#planreviewinput).

**Capability checks declared in these contracts:** `approve_experiment`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | only a submitted plan can be reviewed |
| `CONFLICT` | plan has unresolved blockers |
| `VALIDATION` | decision must be approved\|rejected |

Exact state, permission and validation rules: [LabMutation.plan_review](graphql-contracts.md#labmutationplan_review), [LabPlanService.review](graphql-contracts.md#labplanservicereview).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5902`.

## lab.planSubmit

Submit an experiment plan for explicit human approval.

```graphql
planSubmit(input: PlanIdInput!): PlanResult!
```

Experiment plans and measurement commands enforce lab/reviewer capabilities, approved plan versions, execution state, units, quality and source provenance. Corrections append history rather than overwriting the scientific record; approval cannot be delegated to agent principals.

Return contract: [PlanResult](graphql-types.md#planresult).

Argument contracts: [PlanIdInput](graphql-types.md#planidinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | only a draft can be submitted |

Exact state, permission and validation rules: [LabMutation.plan_submit](graphql-contracts.md#labmutationplan_submit), [LabPlanService.submit](graphql-contracts.md#labplanservicesubmit).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5870`.

## lab.planUpdate

Revise a draft plan using the expected version.

```graphql
planUpdate(input: PlanUpdateInput!): PlanResult!
```

Experiment plans and measurement commands enforce lab/reviewer capabilities, approved plan versions, execution state, units, quality and source provenance. Corrections append history rather than overwriting the scientific record; approval cannot be delegated to agent principals.

Return contract: [PlanResult](graphql-types.md#planresult).

Argument contracts: [PlanUpdateInput](graphql-types.md#planupdateinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | payload must be an object |

Exact state, permission and validation rules: [LabMutation.plan_update](graphql-contracts.md#labmutationplan_update), [LabPlanService.update](graphql-contracts.md#labplanserviceupdate).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5836`.

## learning.evaluationRunStart

Start the evaluation run against its frozen suite and candidate model.

```graphql
evaluationRunStart(input: EvaluationRunStartInput!): EvaluationRunResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [EvaluationRunResult](graphql-types.md#evaluationrunresult).

Argument contracts: [EvaluationRunStartInput](graphql-types.md#evaluationrunstartinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | suite definition drifted from its frozen digest — re-freeze a new version |
| `CONFLICT` | suite must be frozen before a run |
| `ENGINE_UNAVAILABLE` | no evaluation runtime installed — the matched comparison cannot fabricate scores |

Exact state, permission and validation rules: [LearningMutation.evaluation_run_start](graphql-contracts.md#learningmutationevaluation_run_start), [EvaluationService.start_run](graphql-contracts.md#evaluationservicestart_run).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3813`.

## learning.evaluationSuiteCreate

Create an independently tracked evaluation suite specification.

```graphql
evaluationSuiteCreate(input: EvaluationSuiteCreateInput!): EvaluationSuiteResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [EvaluationSuiteResult](graphql-types.md#evaluationsuiteresult).

Argument contracts: [EvaluationSuiteCreateInput](graphql-types.md#evaluationsuitecreateinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | kind must be development\|final |

Exact state, permission and validation rules: [LearningMutation.evaluation_suite_create](graphql-contracts.md#learningmutationevaluation_suite_create), [EvaluationService.create_suite](graphql-contracts.md#evaluationservicecreate_suite).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3716`.

## learning.evaluationSuiteFreeze

Freeze evaluation data and its independent baseline/scope.

```graphql
evaluationSuiteFreeze(input: EvaluationSuiteIdInput!): EvaluationSuiteResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [EvaluationSuiteResult](graphql-types.md#evaluationsuiteresult).

Argument contracts: [EvaluationSuiteIdInput](graphql-types.md#evaluationsuiteidinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | suite is already frozen |
| `VALIDATION` | every task needs a hidden label before freeze |

Exact state, permission and validation rules: [LearningMutation.evaluation_suite_freeze](graphql-contracts.md#learningmutationevaluation_suite_freeze), [EvaluationService.freeze](graphql-contracts.md#evaluationservicefreeze).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3789`.

## learning.evaluationSuiteLabels

Attach hidden target labels to a draft evaluation suite using manage_models.

```graphql
evaluationSuiteLabels(input: EvaluationSuiteLabelsInput!): EvaluationSuiteResult!
```

Write path: requires manage_models and a draft suite; labels attach as hidden evaluation targets. This mutation does not read hidden targets. Hidden-label reads are separately restricted to service principals with read_eval_labels. Existing suite/frozen-state, task cardinality and target shape checks apply.

Return contract: [EvaluationSuiteResult](graphql-types.md#evaluationsuiteresult).

Argument contracts: [EvaluationSuiteLabelsInput](graphql-types.md#evaluationsuitelabelsinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | labels attach only to a draft suite |

Exact state, permission and validation rules: [LearningMutation.evaluation_suite_labels](graphql-contracts.md#learningmutationevaluation_suite_labels), [EvaluationService.set_labels](graphql-contracts.md#evaluationserviceset_labels).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3758`.

## learning.modelReleaseApprove

Record human approval for a reviewed model release.

```graphql
modelReleaseApprove(input: ModelReleaseApproveInput!): ModelReleaseResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [ModelReleaseResult](graphql-types.md#modelreleaseresult).

Argument contracts: [ModelReleaseApproveInput](graphql-types.md#modelreleaseapproveinput).

**Capability checks declared in these contracts:** `read_project`. Ownership and delegated checks also apply.

Exact state, permission and validation rules: [LearningMutation.model_release_approve](graphql-contracts.md#learningmutationmodel_release_approve), [ModelRegistryService.approve](graphql-contracts.md#modelregistryserviceapprove), [ModelRegistryService.get](graphql-contracts.md#modelregistryserviceget).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3624`.

## learning.modelReleaseConvert

Convert a model through the supported lineage-recorded conversion path.

```graphql
modelReleaseConvert(input: ModelReleaseConvertInput!): ModelReleaseResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [ModelReleaseResult](graphql-types.md#modelreleaseresult).

Argument contracts: [ModelReleaseConvertInput](graphql-types.md#modelreleaseconvertinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `MODEL_INCOMPATIBLE` | conversion parity failed — derived artifact does not match the registered pair |

Exact state, permission and validation rules: [LearningMutation.model_release_convert](graphql-contracts.md#learningmutationmodel_release_convert), [ModelRegistryService.convert](graphql-contracts.md#modelregistryserviceconvert).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3608`.

## learning.modelReleasePromote

Promote a validated approved model release using its guarded serving pointer.

```graphql
modelReleasePromote(input: ModelReleaseIdInput!): ModelReleaseResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [ModelReleaseResult](graphql-types.md#modelreleaseresult).

Argument contracts: [ModelReleaseIdInput](graphql-types.md#modelreleaseidinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `MODEL_INCOMPATIBLE` | fresh compatibility validation failed — refusing to serve |

Exact state, permission and validation rules: [LearningMutation.model_release_promote](graphql-contracts.md#learningmutationmodel_release_promote), [ModelRegistryService.promote](graphql-contracts.md#modelregistryservicepromote).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3642`.

## learning.modelReleaseRegister

Register a model release with artifact and training lineage.

```graphql
modelReleaseRegister(input: ModelReleaseRegisterInput!): ModelReleaseResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [ModelReleaseResult](graphql-types.md#modelreleaseresult).

Argument contracts: [ModelReleaseRegisterInput](graphql-types.md#modelreleaseregisterinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | training result lacks recorded base/tokenizer/adapter digests — compatibility binding cannot be established |
| `CONFLICT` | training run has no persisted adapter/result — cannot register |
| `NOT_FOUND` | training run |

Exact state, permission and validation rules: [LearningMutation.model_release_register](graphql-contracts.md#learningmutationmodel_release_register), [ModelRegistryService.register](graphql-contracts.md#modelregistryserviceregister).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3572`.

## learning.modelReleaseRollback

Restore a prior permitted serving release without rewriting model history.

```graphql
modelReleaseRollback(input: ModelReleaseRollbackInput!): ModelReleaseResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [ModelReleaseResult](graphql-types.md#modelreleaseresult).

Argument contracts: [ModelReleaseRollbackInput](graphql-types.md#modelreleaserollbackinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | no known-good release to roll back to |
| `MODEL_INCOMPATIBLE` | rollback target no longer validates — pick another release |

Exact state, permission and validation rules: [LearningMutation.model_release_rollback](graphql-contracts.md#learningmutationmodel_release_rollback), [ModelRegistryService.rollback](graphql-contracts.md#modelregistryservicerollback).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3659`.

## learning.modelReleaseValidate

Validate/load a registered model in the isolated loader runtime.

```graphql
modelReleaseValidate(input: ModelReleaseIdInput!): ModelReleaseResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [ModelReleaseResult](graphql-types.md#modelreleaseresult).

Argument contracts: [ModelReleaseIdInput](graphql-types.md#modelreleaseidinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

Exact state, permission and validation rules: [LearningMutation.model_release_validate](graphql-contracts.md#learningmutationmodel_release_validate), [ModelRegistryService.validate_release](graphql-contracts.md#modelregistryservicevalidate_release).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3594`.

## learning.promotionApprove

Record the required human approval for a promotion decision.

```graphql
promotionApprove(input: PromotionApproveInput!): PromotionDecisionResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [PromotionDecisionResult](graphql-types.md#promotiondecisionresult).

Argument contracts: [PromotionApproveInput](graphql-types.md#promotionapproveinput).

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | no promotion decision on record — run promotion_decide first |

Exact state, permission and validation rules: [LearningMutation.promotion_approve](graphql-contracts.md#learningmutationpromotion_approve), [PromotionService.approve_scope](graphql-contracts.md#promotionserviceapprove_scope).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3872`.

## learning.promotionDecide

Compute a promotion decision from independent evaluation and scientific gates.

```graphql
promotionDecide(input: PromotionDecideInput!): PromotionDecisionResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [PromotionDecisionResult](graphql-types.md#promotiondecisionresult).

Argument contracts: [PromotionDecideInput](graphql-types.md#promotiondecideinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

Exact state, permission and validation rules: [LearningMutation.promotion_decide](graphql-contracts.md#learningmutationpromotion_decide), [PromotionService.decide](graphql-contracts.md#promotionservicedecide).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3847`.

## learning.promotionPromote

Apply an approved passing promotion decision to the serving release.

```graphql
promotionPromote(input: PromotionPromoteInput!): PromotionDecisionResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [PromotionDecisionResult](graphql-types.md#promotiondecisionresult).

Argument contracts: [PromotionPromoteInput](graphql-types.md#promotionpromoteinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `MODEL_NOT_PROMOTABLE` | promotion blocked by the evaluation gate |

Exact state, permission and validation rules: [LearningMutation.promotion_promote](graphql-contracts.md#learningmutationpromotion_promote), [PromotionService.promote](graphql-contracts.md#promotionservicepromote).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3903`.

## learning.sessionModelBind

Bind a research session to its compatible pinned or serving model release.

```graphql
sessionModelBind(input: SessionModelBindInput!): SessionBindResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [SessionBindResult](graphql-types.md#sessionbindresult).

Argument contracts: [SessionModelBindInput](graphql-types.md#sessionmodelbindinput).

**Capability checks declared in these contracts:** `read_project`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | no model release is being served for this session |
| `MODEL_INCOMPATIBLE` | serving compatibility validation failed |
| `NOT_FOUND` | session |

Exact state, permission and validation rules: [LearningMutation.session_model_bind](graphql-contracts.md#learningmutationsession_model_bind), [ModelRegistryService.bind_session](graphql-contracts.md#modelregistryservicebind_session).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3679`.

## learning.snapshotBuild

Build a lineage-bound dataset snapshot from permitted evidence.

```graphql
snapshotBuild(input: DatasetSnapshotBuildInput!): DatasetSnapshotResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [DatasetSnapshotResult](graphql-types.md#datasetsnapshotresult).

Argument contracts: [DatasetSnapshotBuildInput](graphql-types.md#datasetsnapshotbuildinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

Exact state, permission and validation rules: [LearningMutation.snapshot_build](graphql-contracts.md#learningmutationsnapshot_build), [DatasetService.build](graphql-contracts.md#datasetservicebuild).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3318`.

## learning.snapshotFreeze

Freeze the snapshot and leakage-safe training/evaluation partitions.

```graphql
snapshotFreeze(input: DatasetSnapshotIdInput!): DatasetSnapshotResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [DatasetSnapshotResult](graphql-types.md#datasetsnapshotresult).

Argument contracts: [DatasetSnapshotIdInput](graphql-types.md#datasetsnapshotidinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | snapshot already frozen |
| `DATA_RIGHTS_UNKNOWN` | training rights unresolved for included records |
| `PROVENANCE_UNKNOWN` | evidence origin unresolved for included records — rebuild the snapshot so provenance is derived and labeled |

Exact state, permission and validation rules: [LearningMutation.snapshot_freeze](graphql-contracts.md#learningmutationsnapshot_freeze), [DatasetService.freeze](graphql-contracts.md#datasetservicefreeze).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3344`.

## learning.snapshotPrepareRun

Validate a frozen snapshot and prepare its run-readiness report.

```graphql
snapshotPrepareRun(input: DatasetSnapshotIdInput!): DatasetPrepareResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [DatasetPrepareResult](graphql-types.md#datasetprepareresult).

Argument contracts: [DatasetSnapshotIdInput](graphql-types.md#datasetsnapshotidinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | snapshot is not frozen |

Exact state, permission and validation rules: [LearningMutation.snapshot_prepare_run](graphql-contracts.md#learningmutationsnapshot_prepare_run), [DatasetService.prepare_run](graphql-contracts.md#datasetserviceprepare_run).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3366`.

## learning.trainingRunApprove

Approve a training run against its exact reviewed configuration.

```graphql
trainingRunApprove(input: TrainingRunApproveInput!): TrainingRunResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [TrainingRunResult](graphql-types.md#trainingrunresult).

Argument contracts: [TrainingRunApproveInput](graphql-types.md#trainingrunapproveinput).

Exact state, permission and validation rules: [LearningMutation.training_run_approve](graphql-contracts.md#learningmutationtraining_run_approve), [TrainingRunService.approve](graphql-contracts.md#trainingrunserviceapprove).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3464`.

## learning.trainingRunCancel

Request cancellation without treating an incomplete checkpoint as usable success.

```graphql
trainingRunCancel(input: TrainingRunIdInput!): TrainingRunResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [TrainingRunResult](graphql-types.md#trainingrunresult).

Argument contracts: [TrainingRunIdInput](graphql-types.md#trainingrunidinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

Exact state, permission and validation rules: [LearningMutation.training_run_cancel](graphql-contracts.md#learningmutationtraining_run_cancel), [TrainingRunService.cancel](graphql-contracts.md#trainingrunservicecancel).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3509`.

## learning.trainingRunCreate

Create a versioned supervised-training run specification.

```graphql
trainingRunCreate(input: TrainingRunCreateInput!): TrainingRunResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [TrainingRunResult](graphql-types.md#trainingrunresult).

Argument contracts: [TrainingRunCreateInput](graphql-types.md#trainingruncreateinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `NOT_FOUND` | dataset snapshot |
| `NOT_FOUND` | task |

Exact state, permission and validation rules: [LearningMutation.training_run_create](graphql-contracts.md#learningmutationtraining_run_create), [TrainingRunService.create](graphql-contracts.md#trainingrunservicecreate).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3428`.

## learning.trainingRunExecute

Execute an admitted training attempt in its supported isolated runtime.

```graphql
trainingRunExecute(input: TrainingRunExecuteInput!): TrainingRunResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [TrainingRunResult](graphql-types.md#trainingrunresult).

Argument contracts: [TrainingRunExecuteInput](graphql-types.md#trainingrunexecuteinput).

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | training run has no execution run attached |
| `ENGINE_UNAVAILABLE` | training profile is disabled (STUDIO_PROFILE_TRAINING=0) |
| `NOT_FOUND` | dataset artifact missing |

Exact state, permission and validation rules: [LearningMutation.training_run_execute](graphql-contracts.md#learningmutationtraining_run_execute), [TrainingRunService.execute](graphql-contracts.md#trainingrunserviceexecute).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3494`.

## learning.trainingRunQueue

Queue an approved training run after admission checks.

```graphql
trainingRunQueue(input: TrainingRunIdInput!): TrainingRunResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [TrainingRunResult](graphql-types.md#trainingrunresult).

Argument contracts: [TrainingRunIdInput](graphql-types.md#trainingrunidinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `ENGINE_UNAVAILABLE` | training profile is disabled (STUDIO_PROFILE_TRAINING=0) |

Exact state, permission and validation rules: [LearningMutation.training_run_queue](graphql-contracts.md#learningmutationtraining_run_queue), [TrainingRunService.queue](graphql-contracts.md#trainingrunservicequeue).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3480`.

## learning.trainingRunResume

Resume a compatible interrupted supervised-training attempt.

```graphql
trainingRunResume(input: TrainingRunIdInput!): TrainingRunResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [TrainingRunResult](graphql-types.md#trainingrunresult).

Argument contracts: [TrainingRunIdInput](graphql-types.md#trainingrunidinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | no checkpoint to resume from — nothing was persisted |

Exact state, permission and validation rules: [LearningMutation.training_run_resume](graphql-contracts.md#learningmutationtraining_run_resume), [TrainingRunService.resume](graphql-contracts.md#trainingrunserviceresume).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3523`.

## learning.trainingRunSubmit

Submit the training request for explicit human approval.

```graphql
trainingRunSubmit(input: TrainingRunIdInput!): TrainingRunResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [TrainingRunResult](graphql-types.md#trainingrunresult).

Argument contracts: [TrainingRunIdInput](graphql-types.md#trainingrunidinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

Exact state, permission and validation rules: [LearningMutation.training_run_submit](graphql-contracts.md#learningmutationtraining_run_submit), [TrainingRunService.submit](graphql-contracts.md#trainingrunservicesubmit).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3450`.

## learning.trainingRunTransition

Apply a supported training lifecycle transition with state/version checks.

```graphql
trainingRunTransition(input: TrainingRunTransitionInput!): TrainingRunResult!
```

Legacy dataset/training/model/evaluation operations enforce frozen dataset splits and lineage, explicit approvals, isolated runtime availability and independent promotion gates. Hidden evaluation labels require both the label capability and service principal kind. Reward increase alone does not qualify a model for promotion.

Return contract: [TrainingRunResult](graphql-types.md#trainingrunresult).

Argument contracts: [TrainingRunTransitionInput](graphql-types.md#trainingruntransitioninput).

**Capability checks declared in these contracts:** `review_science`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `MODEL_NOT_PROMOTABLE` | promotion requires the model registry's approved serving pointer |

Exact state, permission and validation rules: [LearningMutation.training_run_transition](graphql-contracts.md#learningmutationtraining_run_transition), [TrainingRunService.transition](graphql-contracts.md#trainingrunservicetransition).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3537`.

## materials.gradeCreate

Register a material grade under its known identity.

```graphql
gradeCreate(input: MaterialGradeCreateInput!): MaterialGradeResult!
```

Material identity/grade/reference-product services validate read/edit capabilities, structures, matching decisions and immutable revisions. Human review is required by the relevant review command; identifiers must resolve in this workspace.

Return contract: [MaterialGradeResult](graphql-types.md#materialgraderesult).

Argument contracts: [MaterialGradeCreateInput](graphql-types.md#materialgradecreateinput).

**Capability checks declared in these contracts:** `manage_sources`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | supplier and grade_name are required |

Exact state, permission and validation rules: [MaterialsMutation.grade_create](graphql-contracts.md#materialsmutationgrade_create), [MaterialService.create_grade](graphql-contracts.md#materialservicecreate_grade).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4117`.

## materials.gradeReconcile

Reconcile a grade against a reviewed material identity.

```graphql
gradeReconcile(input: MaterialGradeReconcileInput!): MaterialGradeResult!
```

Material identity/grade/reference-product services validate read/edit capabilities, structures, matching decisions and immutable revisions. Human review is required by the relevant review command; identifiers must resolve in this workspace.

Return contract: [MaterialGradeResult](graphql-types.md#materialgraderesult).

Argument contracts: [MaterialGradeReconcileInput](graphql-types.md#materialgradereconcileinput).

**Capability checks declared in these contracts:** `review_science`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `FORBIDDEN` | grade reconciliation (human review required) |
| `VALIDATION` | reconciliation requires a reason |

Exact state, permission and validation rules: [MaterialsMutation.grade_reconcile](graphql-contracts.md#materialsmutationgrade_reconcile), [MaterialService.reconcile_grades](graphql-contracts.md#materialservicereconcile_grades).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4169`.

## materials.identityCreate

Create a material identity with explicit structure/identity provenance.

```graphql
identityCreate(input: MaterialIdentityCreateInput!): MaterialIdentityResult!
```

Material identity/grade/reference-product services validate read/edit capabilities, structures, matching decisions and immutable revisions. Human review is required by the relevant review command; identifiers must resolve in this workspace.

Return contract: [MaterialIdentityResult](graphql-types.md#materialidentityresult).

Argument contracts: [MaterialIdentityCreateInput](graphql-types.md#materialidentitycreateinput).

**Capability checks declared in these contracts:** `manage_sources`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | each identifier needs a scheme and a value |
| `VALIDATION` | name is required |

Exact state, permission and validation rules: [MaterialsMutation.identity_create](graphql-contracts.md#materialsmutationidentity_create), [MaterialService.create_identity](graphql-contracts.md#materialservicecreate_identity).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:3946`.

## materials.matchPropose

Propose an identity match for later human review.

```graphql
matchPropose(input: MaterialMatchProposeInput!): MaterialIdentityResult!
```

Material identity/grade/reference-product services validate read/edit capabilities, structures, matching decisions and immutable revisions. Human review is required by the relevant review command; identifiers must resolve in this workspace.

Return contract: [MaterialIdentityResult](graphql-types.md#materialidentityresult).

Argument contracts: [MaterialMatchProposeInput](graphql-types.md#materialmatchproposeinput).

**Capability checks declared in these contracts:** `manage_sources`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | an identity cannot match itself |

Exact state, permission and validation rules: [MaterialsMutation.match_propose](graphql-contracts.md#materialsmutationmatch_propose), [MaterialService.propose_match](graphql-contracts.md#materialservicepropose_match).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4036`.

## materials.matchReview

Accept or reject a material-identity match proposal.

```graphql
matchReview(input: MaterialMatchReviewInput!): MaterialIdentityResult!
```

Material identity/grade/reference-product services validate read/edit capabilities, structures, matching decisions and immutable revisions. Human review is required by the relevant review command; identifiers must resolve in this workspace.

Return contract: [MaterialIdentityResult](graphql-types.md#materialidentityresult).

Argument contracts: [MaterialMatchReviewInput](graphql-types.md#materialmatchreviewinput).

**Capability checks declared in these contracts:** `review_science`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `FORBIDDEN` | identity-match review (human review required) |
| `NOT_FOUND` | identity match |
| `VALIDATION` | decision must be accepted or rejected |

Exact state, permission and validation rules: [MaterialsMutation.match_review](graphql-contracts.md#materialsmutationmatch_review), [MaterialService.review_match](graphql-contracts.md#materialservicereview_match).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4080`.

## materials.referenceProductCreate

Create a reference product record without inventing an unknown recipe.

```graphql
referenceProductCreate(input: ReferenceProductCreateInput!): ReferenceProductResult!
```

Material identity/grade/reference-product services validate read/edit capabilities, structures, matching decisions and immutable revisions. Human review is required by the relevant review command; identifiers must resolve in this workspace.

Return contract: [ReferenceProductResult](graphql-types.md#referenceproductresult).

Argument contracts: [ReferenceProductCreateInput](graphql-types.md#referenceproductcreateinput).

**Capability checks declared in these contracts:** `manage_sources`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | name is required |

Exact state, permission and validation rules: [MaterialsMutation.reference_product_create](graphql-contracts.md#materialsmutationreference_product_create), [MaterialService.create_reference_product](graphql-contracts.md#materialservicecreate_reference_product).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4207`.

## materials.referenceRevisionDraft

Draft a versioned reference-product specification.

```graphql
referenceRevisionDraft(input: ReferenceRevisionDraftInput!): ReferenceRevisionResult!
```

Material identity/grade/reference-product services validate read/edit capabilities, structures, matching decisions and immutable revisions. Human review is required by the relevant review command; identifiers must resolve in this workspace.

Return contract: [ReferenceRevisionResult](graphql-types.md#referencerevisionresult).

Argument contracts: [ReferenceRevisionDraftInput](graphql-types.md#referencerevisiondraftinput).

**Capability checks declared in these contracts:** `manage_sources`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | compositionKnowledge is 'unknown' — an ingredient list cannot be recorded; leave composition empty |

Exact state, permission and validation rules: [MaterialsMutation.reference_revision_draft](graphql-contracts.md#materialsmutationreference_revision_draft), [MaterialService.draft_reference_revision](graphql-contracts.md#materialservicedraft_reference_revision).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4256`.

## materials.referenceRevisionFreeze

Freeze a reviewed reference-product revision for reproducible matching.

```graphql
referenceRevisionFreeze(input: ReferenceRevisionFreezeInput!): ReferenceRevisionResult!
```

Material identity/grade/reference-product services validate read/edit capabilities, structures, matching decisions and immutable revisions. Human review is required by the relevant review command; identifiers must resolve in this workspace.

Return contract: [ReferenceRevisionResult](graphql-types.md#referencerevisionresult).

Argument contracts: [ReferenceRevisionFreezeInput](graphql-types.md#referencerevisionfreezeinput).

**Capability checks declared in these contracts:** `manage_sources`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `NOT_FOUND` | reference product revision |

Exact state, permission and validation rules: [MaterialsMutation.reference_revision_freeze](graphql-contracts.md#materialsmutationreference_revision_freeze), [MaterialService.freeze_reference_revision](graphql-contracts.md#materialservicefreeze_reference_revision).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4294`.

## materials.structureReview

Record a review of a proposed material structure.

```graphql
structureReview(input: MaterialStructureReviewInput!): MaterialIdentityResult!
```

Material identity/grade/reference-product services validate read/edit capabilities, structures, matching decisions and immutable revisions. Human review is required by the relevant review command; identifiers must resolve in this workspace.

Return contract: [MaterialIdentityResult](graphql-types.md#materialidentityresult).

Argument contracts: [MaterialStructureReviewInput](graphql-types.md#materialstructurereviewinput).

**Capability checks declared in these contracts:** `review_science`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `FORBIDDEN` | structure review (human review required) |
| `MISSING_IDENTITY` | no structure to review |

Exact state, permission and validation rules: [MaterialsMutation.structure_review](graphql-contracts.md#materialsmutationstructure_review), [MaterialService.review_structure](graphql-contracts.md#materialservicereview_structure).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:4001`.

## notebookCreate

Create an owner-private notebook through the GraphQL alias.

```graphql
notebookCreate(title: String!, folderId: ID = null): JSON!
```

Accepts title and optional folderId; title is validated by CreateNotebook and ownership is checked by LibraryService. Returns the notebook JSON descriptor. This ID is a private notebook identifier as documented by the alias, not a legacy Relay task ID.

Return contract: [JSON](graphql-types.md#json).

Additional JSON semantics: [contracts-library](contracts-library.md), [contracts-agent](contracts-agent.md), [contracts-learning](contracts-learning.md).

Exact state, permission and validation rules: [CreateNotebook](graphql-contracts.md#createnotebook), [LibraryService.create_notebook](graphql-contracts.md#libraryservicecreate_notebook).

Resolver source: `services/studio-api/src/studio/api/graphql/workspace.py:141`.

## notebookPageCreate

Add a structured page with optional citations to a private notebook.

```graphql
notebookPageCreate(input: JSON!): JSON!
```

input is validated as CreatePage: notebookId and title are required; kind/content/citations follow their declared shared library contracts. Unknown keys are rejected and notebook/source ownership is rechecked before the page is committed.

Return contract: [JSON](graphql-types.md#json).

Argument contracts: [JSON](graphql-types.md#json).

Additional JSON semantics: [contracts-library](contracts-library.md), [contracts-agent](contracts-agent.md), [contracts-learning](contracts-learning.md).

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | unsupported notebook page kind |

Exact state, permission and validation rules: [CreatePage](graphql-contracts.md#createpage), [PageContent](graphql-contracts.md#pagecontent), [LibraryService.create_page](graphql-contracts.md#libraryservicecreate_page).

Resolver source: `services/studio-api/src/studio/api/graphql/workspace.py:154`.

## notebookPageUpdate

Save a new revision of an owner-private notebook page.

```graphql
notebookPageUpdate(id: ID!, input: JSON!): JSON!
```

id is the private page ID. input validates as UpdatePage and requires expectedRevision; a stale revision conflicts instead of overwriting another edit. Content/citations are revalidated, revision history retained, and derivative context invalidated as required.

Return contract: [JSON](graphql-types.md#json).

Argument contracts: [JSON](graphql-types.md#json).

Additional JSON semantics: [contracts-library](contracts-library.md), [contracts-agent](contracts-agent.md), [contracts-learning](contracts-learning.md).

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `REVISION_CONFLICT` | notebook page |

Exact state, permission and validation rules: [UpdatePage](graphql-contracts.md#updatepage), [LibraryService.update_page](graphql-contracts.md#libraryserviceupdate_page).

Resolver source: `services/studio-api/src/studio/api/graphql/workspace.py:163`.

## optimization.command

Apply a supported optimization campaign command using its pinned engine/state.

```graphql
command(input: OptimizationCommandInput!): OptimizationResult!
```

Optimization campaign commands require compatible task constraints, accessible/frozen observations, the enabled profile and a usable maintained engine. Synthetic mechanism checks do not establish scientific efficacy.

Return contract: [OptimizationResult](graphql-types.md#optimizationresult).

Argument contracts: [OptimizationCommandInput](graphql-types.md#optimizationcommandinput).

**Capability checks declared in these contracts:** `manage_models`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `ENGINE_UNAVAILABLE` | optimization profile is disabled |
| `FORBIDDEN` | only humans can record campaign lifecycle decisions |
| `IDEMPOTENCY_MISMATCH` | command key reused with changed parameters |
| `REVISION_CONFLICT` | campaign revision changed; reload before retrying |
| `VALIDATION` | idempotency envelope exceeded |

Exact state, permission and validation rules: [OptimizationMutation.command](graphql-contracts.md#optimizationmutationcommand), [OptimizationService.command](graphql-contracts.md#optimizationservicecommand).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:6580`.

## optimization.create

Create a constrained optimization campaign with explicit observations and objectives.

```graphql
create(input: OptimizationCreateInput!): OptimizationResult!
```

Optimization campaign commands require compatible task constraints, accessible/frozen observations, the enabled profile and a usable maintained engine. Synthetic mechanism checks do not establish scientific efficacy.

Return contract: [OptimizationResult](graphql-types.md#optimizationresult).

Argument contracts: [OptimizationCreateInput](graphql-types.md#optimizationcreateinput).

**Capability checks declared in these contracts:** `manage_models`, `review_science`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | campaign creation requires an active task |
| `CONFLICT` | optimization requires a frozen task success contract |
| `ENGINE_UNSUPPORTED_INPUT` | contract-level hard constraints need a reviewed mapping; none were dropped |
| `ENGINE_UNSUPPORTED_INPUT` | match transformation conflicts with frozen metric thresholds |
| `ENGINE_UNSUPPORTED_INPUT` | target direction lacks a reviewed contract mapping |
| `ENGINE_UNSUPPORTED_INPUT` | unsupported campaign parameters/targets/constraints; nothing was dropped |
| `FORBIDDEN` | only humans can freeze a campaign definition |
| `IDEMPOTENCY_MISMATCH` | creation key reused with a different definition |
| `NOT_FOUND` | task |
| `VALIDATION` | bounded idempotency key required |
| `VALIDATION` | definition must be an object |
| `VALIDATION` | target metric, unit and method must match the pinned contract |

Exact state, permission and validation rules: [OptimizationMutation.create](graphql-contracts.md#optimizationmutationcreate), [OptimizationService.create](graphql-contracts.md#optimizationservicecreate).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:6556`.

## privateAgentRunStart

Queue a tool-using turn on an owned private agent thread.

```graphql
privateAgentRunStart(threadId: ID!, input: JSON!): JSON!
```

Requires kind=user. threadId is the private UUID; JSON input supplies message, model/provider selection, role and optional workflow/autopilot flags. Configuration, remote-context consent, model availability and bounded automation policy are rechecked before a queued run is committed.

Return contract: [JSON](graphql-types.md#json).

Argument contracts: [JSON](graphql-types.md#json).

Additional JSON semantics: [contracts-library](contracts-library.md), [contracts-agent](contracts-agent.md), [contracts-learning](contracts-learning.md).

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | a run is already active in this thread |
| `CONFLICT` | provider is disabled |
| `FORBIDDEN` | Workflow belongs to a different conversation |
| `FORBIDDEN` | Workflow provider changed; create a new reviewed workflow |
| `FORBIDDEN` | enable bounded autopilot in Agent settings first |
| `NOT_FOUND` | private local model |
| `VALIDATION` | invalid agent role |
| `VALIDATION` | message must contain 1-32000 characters |
| `VALIDATION` | select a provider model or private local model |
| `VALIDATION` | select an enabled provider model |
| `VALIDATION` | this model backend cannot run the research agent |

Exact state, permission and validation rules: [AgentWorkspaceService.create_run](graphql-contracts.md#agentworkspaceservicecreate_run).

Resolver source: `services/studio-api/src/studio/api/graphql/workspace.py:181`.

## privateAgentThreadCreate

Create a private agent thread, optionally bound to a task/notebook.

```graphql
privateAgentThreadCreate(input: JSON!): JSON!
```

Requires kind=user through AgentWorkspaceService. JSON input accepts title, optional taskId and notebookId. Bound resources are access/owner checked. Returns the thread descriptor; metadata and messages remain private to the owner.

Return contract: [JSON](graphql-types.md#json).

Argument contracts: [JSON](graphql-types.md#json).

Additional JSON semantics: [contracts-library](contracts-library.md), [contracts-agent](contracts-agent.md), [contracts-learning](contracts-learning.md).

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `FORBIDDEN` | AI access is disabled for this notebook |
| `NOT_FOUND` | private notebook |
| `NOT_FOUND` | task |

Exact state, permission and validation rules: [AgentWorkspaceService.create_thread](graphql-contracts.md#agentworkspaceservicecreate_thread).

Resolver source: `services/studio-api/src/studio/api/graphql/workspace.py:172`.

## privateLearningDatasetImport

Validate and retain a custom private dataset through GraphQL.

```graphql
privateLearningDatasetImport(input: JSON!): JSON!
```

JSON input supplies name, dataKind, rights, format and content plus optional mapping/provenance metadata. The same bounded parser, ownership and source-rights checks as REST apply. Returns a dataset descriptor and at most 200 preview rows; it does not silently declare training rights.

Return contract: [JSON](graphql-types.md#json).

Argument contracts: [JSON](graphql-types.md#json).

Additional JSON semantics: [contracts-library](contracts-library.md), [contracts-agent](contracts-agent.md), [contracts-learning](contracts-learning.md).

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `ENGINE_UNAVAILABLE` | Install RDKit to validate molecular datasets |
| `VALIDATION` | Source provenance must be bounded JSON metadata |
| `VALIDATION` | Unknown dataKind |
| `VALIDATION` | Unknown training rights |

Exact state, permission and validation rules: [LearningWorkspaceService.import_dataset](graphql-contracts.md#learningworkspaceserviceimport_dataset), [validate_import](graphql-contracts.md#validate_import).

Resolver source: `services/studio-api/src/studio/api/graphql/workspace.py:192`.

## privateLearningJobStart

Validate and persist a private learning job through GraphQL.

```graphql
privateLearningJobStart(input: JSON!): JSON!
```

JSON input follows the learning job request: kind, datasetId, optional modelId and bounded config. Dataset must be frozen and authorized. Backend/device/kind compatibility and storage/runtime preflight determine queued versus blocked state. The result retains scientificStatus=not_validated.

Return contract: [JSON](graphql-types.md#json).

Argument contracts: [JSON](graphql-types.md#json).

Additional JSON semantics: [contracts-library](contracts-library.md), [contracts-agent](contracts-agent.md), [contracts-learning](contracts-learning.md).

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `DATA_RIGHTS_UNKNOWN` | Declare the base model's license before training |
| `ENGINE_UNSUPPORTED_INPUT` | GRPO currently supports a grounded exact_match reward |
| `ENGINE_UNSUPPORTED_INPUT` | MLX training uses Metal; choose auto or mps |
| `MODEL_INCOMPATIBLE` | Dataset conditions differ from the trained property model |
| `VALIDATION` | Assistant final rows need prompts and reference answers |
| `VALIDATION` | Binary classification requires 0/1 labels and both classes in the train partition |
| `VALIDATION` | Evaluation requires compatible labelled final rows |
| `VALIDATION` | Freeze the validated dataset before starting a job |
| `VALIDATION` | Molecular RL reward must be qed, molecular_weight or logp |
| `VALIDATION` | Molecular transfer supports at most 1000 epochs |
| `VALIDATION` | One property model requires consistent temperature, pressure and process conditions |
| `VALIDATION` | Property jobs support at most 20,000 train rows and 512-character SMILES |
| `VALIDATION` | Property name must be an identifier of at most 96 characters |
| `VALIDATION` | Property training supports 1-300 epochs |
| `VALIDATION` | Select a local model for this job |
| `VALIDATION` | Unknown learning job kind |
| `VALIDATION` | config must be a JSON object |
| `VALIDATION` | device must be auto, cpu, cuda or mps |
| `VALIDATION` | executionTarget must be local or remote |
| `VALIDATION` | propertyTask must be regression or classification |

Exact state, permission and validation rules: [LearningWorkspaceService.create_job](graphql-contracts.md#learningworkspaceservicecreate_job), [LearningWorkspaceService._prepare_job](graphql-contracts.md#learningworkspaceservice_prepare_job).

Resolver source: `services/studio-api/src/studio/api/graphql/workspace.py:200`.

## projectCreate

Create a project that scopes research tasks and materials.

```graphql
projectCreate(input: ProjectCreateInput!): ProjectResult!
```

Requires edit_task. slug and name must be nonempty after trimming. Creates an audited project/outbox event. Optional idempotencyKey deduplicates the same payload; a changed payload under that key fails. Returns ProjectResult, including typed errors.

Return contract: [ProjectResult](graphql-types.md#projectresult).

Argument contracts: [ProjectCreateInput](graphql-types.md#projectcreateinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | name is required |
| `VALIDATION` | slug is required |

Exact state, permission and validation rules: [ProjectService.create](graphql-contracts.md#projectservicecreate).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2641`.

## providers.cleanupCredentials

Retry deletion of orphaned provider credential references.

```graphql
cleanupCredentials: InferenceCredentialCleanupResult!
```

Provider administration uses the manage/admin gate and write-only credential storage. Save/test/delete may contact the configured endpoint or update credential state; stale provider revisions and invalid endpoint styles are rejected. Keys are never returned.

Return contract: [InferenceCredentialCleanupResult](graphql-types.md#inferencecredentialcleanupresult).

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | credential cleanup could not be completed; retry after unlocking Keychain |

Exact state, permission and validation rules: [ProviderMutation.cleanup_credentials](graphql-contracts.md#providermutationcleanup_credentials), [ProviderService.cleanup_credentials](graphql-contracts.md#providerservicecleanup_credentials).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:855`.

## providers.delete

Delete a provider connection after checking its expected revision.

```graphql
delete(input: InferenceProviderDeleteInput!): InferenceProviderDeleteResult!
```

Provider administration uses the manage/admin gate and write-only credential storage. Save/test/delete may contact the configured endpoint or update credential state; stale provider revisions and invalid endpoint styles are rejected. Keys are never returned.

Return contract: [InferenceProviderDeleteResult](graphql-types.md#inferenceproviderdeleteresult).

Argument contracts: [InferenceProviderDeleteInput](graphql-types.md#inferenceproviderdeleteinput).

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | provider could not be removed; reload and retry |

Exact state, permission and validation rules: [ProviderMutation.delete](graphql-contracts.md#providermutationdelete), [ProviderService.delete](graphql-contracts.md#providerservicedelete).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:915`.

## providers.save

Create or revise a provider connection using a write-only credential.

```graphql
save(input: InferenceProviderSaveInput!): InferenceProviderResult!
```

Provider administration uses the manage/admin gate and write-only credential storage. Save/test/delete may contact the configured endpoint or update credential state; stale provider revisions and invalid endpoint styles are rejected. Keys are never returned.

Return contract: [InferenceProviderResult](graphql-types.md#inferenceproviderresult).

Argument contracts: [InferenceProviderSaveInput](graphql-types.md#inferenceprovidersaveinput).

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | provider settings could not be committed; reload and retry |
| `CONFLICT` | saved provider changed; reload before retrying |
| `IDEMPOTENCY_MISMATCH` | clientMutationId was already used with different settings |
| `IDEMPOTENCY_MISMATCH` | clientMutationId was used with a different API key |
| `VALIDATION` | API key must be 8-8192 characters without whitespace or controls |
| `VALIDATION` | changing a keyed provider destination requires replacing or removing its API key |
| `VALIDATION` | clientMutationId is too long |
| `VALIDATION` | provider name and model must be nonempty and bounded |
| `VALIDATION` | replace or clear the API key, not both |
| `VALIDATION` | supported providers use Chat Completions or Responses |

Exact state, permission and validation rules: [ProviderMutation.save](graphql-contracts.md#providermutationsave), [ProviderService.save](graphql-contracts.md#providerservicesave).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:873`.

## providers.test

Probe a saved provider and persist its connection-test state.

```graphql
test(input: InferenceProviderTestInput!): InferenceProviderTestResult!
```

Provider administration uses the manage/admin gate and write-only credential storage. Save/test/delete may contact the configured endpoint or update credential state; stale provider revisions and invalid endpoint styles are rejected. Keys are never returned.

Return contract: [InferenceProviderTestResult](graphql-types.md#inferenceprovidertestresult).

Argument contracts: [InferenceProviderTestInput](graphql-types.md#inferenceprovidertestinput).

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | provider probe could not be recorded; retry |

Exact state, permission and validation rules: [ProviderMutation.test](graphql-contracts.md#providermutationtest), [ProviderService.test](graphql-contracts.md#providerservicetest).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:946`.

## research.messagePost

Append a human message to an accessible research session.

```graphql
messagePost(input: MessagePostInput!): SessionMessageResult!
```

Task-scoped research sessions/messages/questions/summaries use capability checks and persisted outbox events. Turn requests are bounded and cancelable; remote provider disclosure and engine availability are evaluated before execution.

Return contract: [SessionMessageResult](graphql-types.md#sessionmessageresult).

Argument contracts: [MessagePostInput](graphql-types.md#messagepostinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | cannot post to an ended session |
| `VALIDATION` | message content must not be empty |

Exact state, permission and validation rules: [ResearchMutation.message_post](graphql-contracts.md#researchmutationmessage_post), [TaskMemoryService.post_message](graphql-contracts.md#taskmemoryservicepost_message).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5497`.

## research.questionRaise

Record an unresolved research question rather than inventing an answer.

```graphql
questionRaise(input: QuestionRaiseInput!): TaskQuestionResult!
```

Task-scoped research sessions/messages/questions/summaries use capability checks and persisted outbox events. Turn requests are bounded and cancelable; remote provider disclosure and engine availability are evaluated before execution.

Return contract: [TaskQuestionResult](graphql-types.md#taskquestionresult).

Argument contracts: [QuestionRaiseInput](graphql-types.md#questionraiseinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | question must not be empty |

Exact state, permission and validation rules: [ResearchMutation.question_raise](graphql-contracts.md#researchmutationquestion_raise), [TaskMemoryService.raise_question](graphql-contracts.md#taskmemoryserviceraise_question).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5638`.

## research.questionResolve

Resolve a recorded question with its provided answer/provenance.

```graphql
questionResolve(input: QuestionResolveInput!): TaskQuestionResult!
```

Task-scoped research sessions/messages/questions/summaries use capability checks and persisted outbox events. Turn requests are bounded and cancelable; remote provider disclosure and engine availability are evaluated before execution.

Return contract: [TaskQuestionResult](graphql-types.md#taskquestionresult).

Argument contracts: [QuestionResolveInput](graphql-types.md#questionresolveinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `NOT_FOUND` | task question |
| `VALIDATION` | a resolution is required |

Exact state, permission and validation rules: [ResearchMutation.question_resolve](graphql-contracts.md#researchmutationquestion_resolve), [TaskMemoryService.resolve_question](graphql-contracts.md#taskmemoryserviceresolve_question).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5675`.

## research.sessionEnd

End a research session while retaining its conversation history.

```graphql
sessionEnd(input: SessionEndInput!): ResearchSessionResult!
```

Task-scoped research sessions/messages/questions/summaries use capability checks and persisted outbox events. Turn requests are bounded and cancelable; remote provider disclosure and engine availability are evaluated before execution.

Return contract: [ResearchSessionResult](graphql-types.md#researchsessionresult).

Argument contracts: [SessionEndInput](graphql-types.md#sessionendinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

Exact state, permission and validation rules: [ResearchMutation.session_end](graphql-contracts.md#researchmutationsession_end), [TaskMemoryService.end_session](graphql-contracts.md#taskmemoryserviceend_session).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5465`.

## research.sessionStart

Open a task research session with its model/context provenance.

```graphql
sessionStart(input: SessionStartInput!): ResearchSessionResult!
```

Task-scoped research sessions/messages/questions/summaries use capability checks and persisted outbox events. Turn requests are bounded and cancelable; remote provider disclosure and engine availability are evaluated before execution.

Return contract: [ResearchSessionResult](graphql-types.md#researchsessionresult).

Argument contracts: [SessionStartInput](graphql-types.md#sessionstartinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | token budget must be positive |

Exact state, permission and validation rules: [ResearchMutation.session_start](graphql-contracts.md#researchmutationsession_start), [TaskMemoryService.start_session](graphql-contracts.md#taskmemoryservicestart_session).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5427`.

## research.summaryCreate

Persist a sourced research summary for later task context.

```graphql
summaryCreate(input: SummaryCreateInput!): TaskSummaryResult!
```

Task-scoped research sessions/messages/questions/summaries use capability checks and persisted outbox events. Turn requests are bounded and cancelable; remote provider disclosure and engine availability are evaluated before execution.

Return contract: [TaskSummaryResult](graphql-types.md#tasksummaryresult).

Argument contracts: [SummaryCreateInput](graphql-types.md#summarycreateinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | generator (model/version or 'deterministic') is required |
| `VALIDATION` | summary body must not be empty |

Exact state, permission and validation rules: [ResearchMutation.summary_create](graphql-contracts.md#researchmutationsummary_create), [TaskMemoryService.create_summary](graphql-contracts.md#taskmemoryservicecreate_summary).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5711`.

## research.turnCancel

Request cancellation of an assistant turn.

```graphql
turnCancel(input: TurnCancelInput!): TurnCancelResult!
```

Task-scoped research sessions/messages/questions/summaries use capability checks and persisted outbox events. Turn requests are bounded and cancelable; remote provider disclosure and engine availability are evaluated before execution.

Return contract: [TurnCancelResult](graphql-types.md#turncancelresult).

Argument contracts: [TurnCancelInput](graphql-types.md#turncancelinput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | cannot post to an ended session |
| `VALIDATION` | message content must not be empty |

Exact state, permission and validation rules: [ResearchMutation.turn_cancel](graphql-contracts.md#researchmutationturn_cancel), [TaskMemoryService.post_message](graphql-contracts.md#taskmemoryservicepost_message).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5597`.

## research.turnRequest

Request one bounded assistant turn with explicit provider/private-context consent.

```graphql
turnRequest(input: TurnRequestInput!): TurnRequestResult!
```

Task-scoped research sessions/messages/questions/summaries use capability checks and persisted outbox events. Turn requests are bounded and cancelable; remote provider disclosure and engine availability are evaluated before execution.

Return contract: [TurnRequestResult](graphql-types.md#turnrequestresult).

Argument contracts: [TurnRequestInput](graphql-types.md#turnrequestinput).

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `CONFLICT` | research turn could not be committed; retry with the same turn id |

Exact state, permission and validation rules: [ResearchMutation.turn_request](graphql-contracts.md#researchmutationturn_request).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5541`.

## runs.describeStructure

Run molecular descriptors for a structure within an existing task.

```graphql
describeStructure(input: DescribeStructureInput!): RunResult!
```

Run commands enforce task access, admission, resource/profile availability and structure validation. Cancellation is a request until execution termination is recorded. Fallback does not bypass privacy/export approval or make an unavailable engine available. Resolver-declared capability checks: `CAP_REQUEST_COMPUTE`.

Return contract: [RunResult](graphql-types.md#runresult).

Argument contracts: [DescribeStructureInput](graphql-types.md#describestructureinput).

**Capability checks declared in these contracts:** `request_compute`. Ownership and delegated checks also apply.

Exact state, permission and validation rules: [RunsMutation.describe_structure](graphql-contracts.md#runsmutationdescribe_structure).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5129`.

## runs.quickDescribeStructure

Create a quick research task and run local molecular descriptors from SMILES.

```graphql
quickDescribeStructure(input: QuickDescribeStructureInput!): RunResult!
```

Run commands enforce task access, admission, resource/profile availability and structure validation. Cancellation is a request until execution termination is recorded. Fallback does not bypass privacy/export approval or make an unavailable engine available. Resolver-declared capability checks: `CAP_REQUEST_COMPUTE`.

Return contract: [RunResult](graphql-types.md#runresult).

Argument contracts: [QuickDescribeStructureInput](graphql-types.md#quickdescribestructureinput).

**Capability checks declared in these contracts:** `request_compute`. Ownership and delegated checks also apply.

Exact state, permission and validation rules: [RunsMutation.quick_describe_structure](graphql-contracts.md#runsmutationquick_describe_structure).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5096`.

## runs.request

Request a typed compute run after capability, resource and profile admission.

```graphql
request(input: RunRequestInput!): RunResult!
```

Run commands enforce task access, admission, resource/profile availability and structure validation. Cancellation is a request until execution termination is recorded. Fallback does not bypass privacy/export approval or make an unavailable engine available.

Return contract: [RunResult](graphql-types.md#runresult).

Argument contracts: [RunRequestInput](graphql-types.md#runrequestinput).

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `NOT_FOUND` | task |
| `VALIDATION` | request must be an object |

Exact state, permission and validation rules: [RunsMutation.request](graphql-contracts.md#runsmutationrequest), [RunService.request](graphql-contracts.md#runservicerequest).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5161`.

## runs.requestCancel

Persist a run cancellation request for worker reconciliation.

```graphql
requestCancel(input: RunCancelInput!): RunResult!
```

Run commands enforce task access, admission, resource/profile availability and structure validation. Cancellation is a request until execution termination is recorded. Fallback does not bypass privacy/export approval or make an unavailable engine available.

Return contract: [RunResult](graphql-types.md#runresult).

Argument contracts: [RunCancelInput](graphql-types.md#runcancelinput).

Exact state, permission and validation rules: [RunsMutation.request_cancel](graphql-contracts.md#runsmutationrequest_cancel), [RunService.request_cancel](graphql-contracts.md#runservicerequest_cancel).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5203`.

## runs.requestFallback

Request an explicit policy-checked fallback route after local infeasibility.

```graphql
requestFallback(input: RunFallbackInput!): FallbackResult!
```

Run commands enforce task access, admission, resource/profile availability and structure validation. Cancellation is a request until execution termination is recorded. Fallback does not bypass privacy/export approval or make an unavailable engine available.

Return contract: [FallbackResult](graphql-types.md#fallbackresult).

Argument contracts: [RunFallbackInput](graphql-types.md#runfallbackinput).

**Capability checks declared in these contracts:** `request_compute`. Ownership and delegated checks also apply.

Exact state, permission and validation rules: [RunsMutation.request_fallback](graphql-contracts.md#runsmutationrequest_fallback), [FeasibilityService.request_fallback](graphql-contracts.md#feasibilityservicerequest_fallback), [FeasibilityService.fallback_view](graphql-contracts.md#feasibilityservicefallback_view).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:5235`.

## taskClose

Close a task with a human scientific review decision.

```graphql
taskClose(input: TaskCloseInput!): TaskResult!
```

Requires principal kind=user and review_science; task must be awaiting_review. closureDecision must be a supported closure. Multiple accepted candidates require candidateRevisionId. The service builds a bound closeout packet: supported_success must pass frozen-contract evidence gates; supported_failure must pass its failure gate. Closure increments task version and preserves contract/evaluation-cycle provenance.

Return contract: [TaskResult](graphql-types.md#taskresult).

Argument contracts: [TaskCloseInput](graphql-types.md#taskcloseinput).

**Capability checks declared in these contracts:** `review_science`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `FORBIDDEN` | task closure (human review required) |
| `VALIDATION` | multiple accepted candidates — close requires an explicit candidateRevisionId binding the report the reviewer saw |
| `VALIDATION` | task must be awaiting_review to close |

Exact state, permission and validation rules: [TaskService.close](graphql-contracts.md#taskserviceclose).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2813`.

## taskCreate

Create a research task in a selected project or the research inbox.

```graphql
taskCreate(input: TaskCreateInput!): TaskCreateResult!
```

Requires read_project and edit_task in the selected project scope. If projectId is absent, the service reuses/creates the research inbox. title, mode and mode-specific inputs are validated; unsupported or incomplete science intent is not filled with invented defaults. Optional idempotencyKey makes retries payload-bound. Resolver-declared capability checks: `CAP_EDIT_TASK`, `CAP_READ_PROJECT`.

Return contract: [TaskCreateResult](graphql-types.md#taskcreateresult).

Argument contracts: [TaskCreateInput](graphql-types.md#taskcreateinput).

**Capability checks declared in these contracts:** `edit_task`, `read_project`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | title is required |

Exact state, permission and validation rules: [TaskService.create](graphql-contracts.md#taskservicecreate), [ProjectService.research_inbox](graphql-contracts.md#projectserviceresearch_inbox).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2684`.

## taskReopen

Reopen a closed task while preserving its prior closure packet.

```graphql
taskReopen(input: TaskReopenInput!): TaskResult!
```

Requires edit_task in the task project. Only closed tasks can reopen and reason must be nonempty. New state is active; closure decision is cleared and evaluation cycle increments. Prior contract/closure/evaluation provenance is retained, rather than rewriting the old review.

Return contract: [TaskResult](graphql-types.md#taskresult).

Argument contracts: [TaskReopenInput](graphql-types.md#taskreopeninput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `VALIDATION` | only a closed task can be reopened |
| `VALIDATION` | reopening requires a reason |

Exact state, permission and validation rules: [TaskService.reopen](graphql-contracts.md#taskservicereopen).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2870`.

## taskTransition

Move a task through a permitted workflow transition.

```graphql
taskTransition(input: TaskTransitionInput!): TaskResult!
```

Requires edit_task in the task project. Supply expectedVersion to detect stale state. toState must be permitted from the current state; closed is rejected here because closure needs taskClose. Returning awaiting_review to active requires a review reason. The version increments and a decision/outbox event is recorded.

Return contract: [TaskResult](graphql-types.md#taskresult).

Argument contracts: [TaskTransitionInput](graphql-types.md#tasktransitioninput).

**Capability checks declared in these contracts:** `edit_task`. Ownership and delegated checks also apply.

**Literal rejection reasons declared in these contracts:** dynamic messages and delegated failures are specified by the full excerpts.

| Code | Rejected condition / record |
| --- | --- |
| `REVISION_CONFLICT` | task |
| `VALIDATION` | closing requires the taskClose command with a closure decision |
| `VALIDATION` | returning to active requires a review reason |

Exact state, permission and validation rules: [TaskService.transition](graphql-contracts.md#taskservicetransition).

Resolver source: `services/studio-api/src/studio/api/graphql/schema.py:2761`.
