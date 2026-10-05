# Chemistry Studio
## Canonical implementation plan and engineering handoff

**Document version:** 1.0.0  
**Prepared:** 5 October 2026  
**Status:** Implementation specification; no application implementation or scientific validation is claimed.  
**Audience:** The implementation controller, coding agents, scientific reviewer, and product owner.  
**Canonical source:** This Markdown file plus the versioned contracts and planning registers in this package. The Word document is a reading copy.  
**Working product name:** Chemistry Studio; naming/branding is not a blocking decision.

> Build a standalone, local-first chemistry research application. Projects contain scoped research tasks; tasks contain persistent sessions, immutable candidates, evidence, calculations, laboratory experiments, and versioned success criteria. Support improving formulations, matching reference products, and discovering new formulations/materials/molecules. Use existing scientific engines. Make the workflow useful before fine-tuning; enable each subsequent learning capability only after its evidence and evaluation gates pass.

# 1. Authority, operating rules, and how to use this package

## 1.1 Order of authority

The user's explicit decisions in this conversation are authoritative. `planning/decisions.json` records them separately from engineering defaults and unresolved inputs. This handoff translates them into implementation requirements. `contracts/domain.schema.json` specifies initial interchange shapes; domain invariants below add requirements that JSON Schema alone cannot enforce. `planning/workplan.json` gives the dependency graph, ownership, implementation steps, and acceptance references. `planning/acceptance-tests.json` specifies required behaviors. `planning/design-map.json` connects screens, components, permissions, data, and tests.

When these artifacts disagree, do not select the easier interpretation. Record the conflict, preserve the stronger privacy/scientific-integrity constraint, and update all affected canonical artifacts through a reviewed change. A schema example is never permission to bypass an invariant. An engineering default may be changed with an architecture decision record (ADR); a locked product decision may not be silently changed. New code must not overwrite correct existing work if a repository already exists.

The first executable delivered with this package, `scripts/validate_pack.py`, checks specification consistency. It does not execute a chemistry engine, train a model, validate a formulation, or establish application readiness. Application test commands defined later are implementation obligations, not claims that those commands already exist.

## 1.2 Mandatory startup behavior for the implementation agent

1. Inspect the current directory, repository, branch, commit, uncommitted files, instructions, dependency locks, and available runtime. Do not invent a repository or claim to have inspected one from this conversation; none was provided.
2. Read this handoff, the kickoff, decisions, unknowns, contracts, workplan, acceptance tests, integration catalog, and design map before changing shared contracts.
3. Create `docs/execution/baseline.md`, `analysis.md`, `plan.md`, `tech-specs.md`, and `tasks.md`. Record current reality: existing, preserve, modify, new, blocked, and deferred.
4. Run existing tests before edits. If there is no repository, record a greenfield baseline rather than fabricating a passing test suite. Work only in an authorized writable directory.
5. Verify chosen dependency versions against official documentation and licenses; create lockfiles and `docs/dependencies.lock.md`. Do not copy APIs from memory, including examples in older documentation pages.
6. Implement the first unblocked ticket in dependency order. Do not spend the entire work session producing another plan. Continue around non-blocking unknowns using synthetic fixtures.
7. For every completed ticket, record changed files, migrations, exact test commands, results, evidence paths, limitations, and the commit identifier when available.

## 1.3 Completion language

Use `not_started`, `in_progress`, `blocked`, `implemented_unverified`, `verified`, and `deferred` in the implementation ledger. A ticket is `verified` only when its required software tests ran successfully. Separately record scientific capability as `not_configured`, `fixture_only`, `engine_smoke_passed`, `domain_benchmarked`, or `experimentally_supported`. Never collapse these into one green status.

A missing GPU, laboratory, model license, cloud account, or chemical dataset does not block core application engineering. It does block the corresponding real execution claim. Synthetic tests can verify control flow; they cannot establish chemistry accuracy. Record unavailable tests as blocked, never as passed or silently skipped.

# 2. Locked product decisions and explicit non-goals

## 2.1 Locked decisions

**D01 — Standalone focus.** Chemistry Studio is a chemistry-only product, not a plugin inside a general AI studio. Internal adapters are implementation modules, not a marketplace or a broad agent platform.

**D02 — Three modes.** Every research task uses one of `improve`, `match_reference`, or `discover`. All three must be available in the first useful pilot. Molecule-specific generation can be capability-gated without hiding the discovery task mode.

**D03 — Task-based pilot.** The pilot is a portfolio of bounded tasks, not one permanently selected product. Each task has an objective, versions of its success contract, evidence, and review outcomes. Sessions are subordinate to tasks and do not replace them.

**D04 — Historical learning.** Ingest authorized successful formulations, failures, recipes, product documentation, and purchased-product documents. A purchased product may have no known recipe. Unknown composition must remain unknown.

**D05 — Workflow first.** Deliver research, candidate management, verification, experiment recording, and evaluation before requiring local assistant fine-tuning or RL. Make data lineage and training eligibility part of the first schema.

**D06 — Human-controlled lab.** Initially, experiments are manually approved and performed; results are manually uploaded/imported. No autonomous instrument execution, chemical purchasing, or physical dispensing.

**D07 — Local-first and hardware-aware.** No equipment has been purchased. Detect capabilities at runtime. Do not assume a specific OS, GPU vendor, VRAM amount, cloud provider, or budget.

**D08 — Cloud fallback only.** A cloud job is an exception after local execution is shown infeasible for the approved job/configuration. Minimize and review exported information. Pseudonymization does not automatically make a recipe safe to export. Every actual transfer needs authorization; this document is not blanket consent.

**D09 — Honest unknowns.** Unspecified facts remain explicit unknowns. They block only actions that genuinely require them.

**D10 — Evidence-based upgrades.** A trained model must improve independent evaluation relative to a matched baseline before promotion. Training reward alone is not a release gate.

## 2.2 First useful pilot scope

The pilot includes a local application shell; task creation and resumption; all three modes; versioned metrics; ingredient/formulation/reference registries; source ingestion and review; provenance-aware retrieval; candidate revisions; a deterministic verifier; approved low-risk tool execution; human experiment review; measurement import; comparisons; task closeout; and export of a reproducible research packet. A local model is an optional capability during bootstrap, not a dependency for deterministic recordkeeping.

The complete roadmap additionally includes BayBE experiment selection, learned property models, targeted quantum calculations, analytical integrations, local assistant fine-tuning, independent evaluation, controlled research-agent RL, appropriate small-molecule generation, protected cloud fallback, and production hardening. These are not discarded simply because they are later than the pilot.

## 2.3 Non-goals and prohibited substitutions

Do not build a quantum solver, molecular-dynamics engine, general training framework, molecule parser, or electronic laboratory notebook replacement where an adapter suffices. Do not claim a universal chemical verifier. Do not make a chat transcript the database. Do not claim all polymers can be represented by one SMILES string. Do not claim that property matching recovers a commercial recipe, that a retrosynthesis suggestion is a validated synthesis, or that a restriction-list lookup proves safety/compliance.

No multi-customer SaaS billing, app marketplace, native mobile app, public data sharing, federated learning, encrypted-domain training promise, autonomous synthesis robot, or general-purpose agent builder is required. LAN/team access and a native desktop wrapper are optional later deployment profiles, not reasons to delay the loopback application. No production integrations or paid service purchases are authorized by the handoff.

# 3. Unknowns and how engineering continues safely

`planning/unknowns.json` is the authoritative unresolved-input register. At minimum retain: actual repository; dataset size and formats; historical measurement quality; pilot subjects and thresholds; lab personnel and qualifications; available methods/equipment; experiment capacity/turnaround; user count and role assignments; OS/hardware; infrastructure and experiment budgets; delivery dates; cloud provider/region/account; licenses and data rights; retention policy; and independent scientific acceptance criteria.

A task may be created with unknown metrics or a missing baseline, but must display `exploratory` and cannot close as scientifically successful. A purchased-product reference may be recorded without composition, but calculations needing composition are blocked. A model-training configuration may be prepared without hardware, but scheduling remains unavailable until a capability report exists. A provider-neutral cloud interface may be implemented without an account, but its live adapter must be disabled and labeled unverified.

Do not guess test thresholds from an LLM. Do not invent laboratory availability from the user's acceptance of manual workflows. Do not assume permission to train on supplier documentation merely because it was uploaded. During implementation, use clearly marked synthetic data with no real supplier identities or operational chemical recipes.

# 4. Reference architecture and technology decisions

## 4.1 Recommended deployable shape

Use a **modular Python backend with a React web client**, a local PostgreSQL database, a private artifact vault, and separate workers for ingestion, inference, optimization, simulation, and training. The default UI is served on loopback in the browser. Standalone means product independence, not a requirement to implement an Electron or native wrapper immediately.

```text
Local browser
  -> authenticated same-origin API
      -> domain services and authorization
      -> PostgreSQL: canonical records, events, job references
      -> artifact vault: source documents, spectra, datasets, models
      -> transactional outbox
          -> existing job queue
              -> isolated local workers
              -> approved cloud job broker (disabled by default)

Research agent -> typed tool gateway -> the same domain services
External sources -> explicit egress broker -> quarantine -> evidence review
Physical laboratory -> human-approved plan -> manual results -> quality review
```

This is not a microservices program. Keep one domain codebase, one migration authority, one canonical authorization implementation, and one user-facing server-state cache. Worker environments may differ because scientific dependencies conflict; that does not justify duplicating business logic.

## 4.2 Engineering defaults, not new user commitments

**Backend:** Python; FastAPI as the ASGI host; Strawberry GraphQL for the application API; Pydantic for DTO validation; SQLAlchemy and Alembic for persistence. Choose a tested Python version supported by the selected science dependencies, not the newest interpreter automatically.

**Frontend:** React, TypeScript, Vite, Relay, and CSS variables/CSS modules. A single Relay environment owns remote entity state. A small local store may own transient panel state, unsaved input, and selected tabs; it must not become another server cache. Follow Relay's Node and connection requirements [S03, S04].

**Persistence:** PostgreSQL for records, access scopes, outbox, and job references. Use PostgreSQL full-text search first. A locally generated vector index can be added behind the same retrieval interface if it improves the evaluated retrieval task. Do not require a separate vector service to launch.

**Queue:** Reuse Procrastinate for PostgreSQL-backed scheduling, locks, and retries [S05]. Add Chemistry Studio's authorization, resource-admission, subprocess supervision, and scientific execution records around it. Queue state is transport state; `Run` is the authoritative product record. Never duplicate the queue implementation in custom polling code.

**Artifact storage:** Private local filesystem behind an `ArtifactStore` interface, not inside the Git repository or public web root. Begin with filesystem storage and a streaming API. Object storage is a later adapter, subject to the same export policy.

**Model runtime:** Provider-neutral local adapter with a capability handshake. Evaluate llama.cpp as an initial local inference runtime [S21]. Pin model/license/checksum/tokenizer/chat template and test actual tool/structured-output behavior. Do not assume any local runtime supports every fine-tuned adapter without conversion and verification.

**Testing:** pytest for backend/domain/integration tests; property-based tests for units, composition and state invariants; TypeScript typecheck and component tests; Playwright for end-to-end journeys. Pin exact dependencies after bootstrap. No heavy simulation or real training in the default PR CI.

## 4.3 Runtime profiles

`core` runs the application, DB, ingestion, search, and manual workflows. `local_ai` additionally starts a compatible local model worker. `optimization` enables BayBE/property workers. `quantum` installs approved xTB/Psi4 environments. `training` adds the selected PyTorch/PEFT/TRL environment. Profiles are separately installable; the core service must not import GPU libraries at startup.

Linux x86-64 is the proposed CI reference environment, not a declared user OS. On macOS or Windows, verify each binary's availability and isolation support. A scientific worker may run in a compatible local VM/container when supported. Unsupported profiles report why they are unavailable; they never silently route to a hosted service.

## 4.4 Repository layout to create or map onto existing code

```text
apps/studio-web/src/
  app/ routes/ relay/ features/ components/ styles/
services/studio-api/src/studio/
  api/graphql/ api/transfers/ auth/ config/
  domain/{projects,tasks,materials,candidates,evidence,lab,runs,learning}/
  application/ persistence/ audit/ events/
workers/
  ingestion/ inference/ optimization/ chemistry/ training/
packages/contracts/                 # canonical schemas + generated types
packages/engine-adapters/           # no user-facing state
packages/policy/                    # policy interfaces; backend authority
migrations/                        # one controller owns ordering
infra/local/ infra/ci/ infra/cloud/ # cloud disabled initially
fixtures/synthetic/                 # no proprietary examples
tests/                             # layered automated test suites
  unit/ integration/ engines/ security/ eval/ e2e/
docs/
  architecture/ design/ execution/ operations/ science/ dependencies/
```

In an existing monorepo, preserve per-application isolation; do not import unrelated application business modules. Record a path mapping in `docs/execution/repo-map.md` before parallel work.

# 5. Canonical domain model

## 5.1 Identity, versions, and ownership

Use immutable UUID identifiers internally and globally unique opaque Node IDs at the GraphQL boundary. The Node ID must remain stable across queries, lists, refreshes, and mutations. Encoding is not authorization. A revision is its own Node, not a mutable object reusing its parent's ID.

Every scoped record carries `workspace_id`; project-owned records also carry `project_id`. Cross-scope references are checked in the service layer and constrained with composite foreign keys where practical. Principal identity comes from the authenticated request/worker context, never from an arbitrary client-provided owner field. UTC timestamps are stored; UI formatting follows a user setting. Scientific durations use explicit units, not timezone arithmetic.

Mutable drafts use integer optimistic concurrency (`expected_version`). Accepted records are append-only; corrections create superseding records. Mutable metadata changes still create audit events. Hash canonical payloads with a versioned serialization rule; include schema version. Use hashes for integrity/cache identity, not as a claim of privacy.

## 5.2 Entities and minimum required fields

**Workspace:** name; data root; security profile; default local-only egress policy; owner principal; retention configuration status. First release may contain one workspace, but still enforce scope.

**Project:** product family/application, description, authorized members, scoped knowledge collections, task list. Do not hardcode textile as the only domain.

**ResearchTask:** project; mode; target entity kind; title; objective; current contract revision; workflow state; responsible reviewer; linked baselines/references; active budget; decisions; unresolved questions. Mode changes after candidates exist create a new linked task or explicit migration reviewed by the owner; they must not reinterpret history silently.

**SuccessContractRevision:** task; revision; status; baseline/reference revisions; metrics; hard constraints; required evidence; review rules; budget; scope; unresolved fields; approval record. Historical evaluations always retain their contract ID.

**ResearchSession:** task; purpose; starting task snapshot; messages; authorized tool calls; evidence citations; proposal patches; summary; ending snapshot. Sessions can fork an approach but cannot fork ownership or bypass task constraints.

**DecisionRecord:** task; proposition; alternatives; supporting and opposing evidence; reviewer; decision; reason; supersedes pointer. A model-proposed decision is not accepted until an authorized user acts.

**MaterialIdentity:** identity kind (`defined_molecule`, `polymer`, `commercial_mixture`, `substance_class`, `unknown`); identifiers and their sources; structure if known; supplier/product aliases; confidentiality; evidence status. Preserve uncertainty and ambiguous identity candidates. A registry match is a proposal until reviewed.

**MaterialGrade / MaterialLot:** material; supplier grade; purity or active content with basis; specifications; lot; dates when known; certificates/documents. Do not collapse two commercial grades into one merely because a molecule identifier matches.

**Product / ReferenceProductRevision:** name/alias; supplier; product category; documentation; composition knowledge (`known`, `partial`, `unknown`); claimed properties; measured properties via evidence links; sample/lot references. No fabricated ingredient list is permitted for unknown purchased products.

**FormulationRevision:** formulation family; parent revision; ingredient lines; amount basis; total basis; preparation/process revision; substrate/application context; author/source; completeness; validation findings. Formula and process must be versioned together for reproducibility while remaining distinct objects.

**ProcessRevision:** ordered steps; input/output material references; recorded conditions; equipment requirements; source; unknown conditions; approval status. Store historical procedures faithfully. New actionable procedures require scientific/safety review before lab release.

**CandidateRevision:** task; entity kind (`formulation`, `molecule`, `material`); referenced entity revision; parent/branch; hypothesis; proposed differences; linked contract; evidence; eligibility. Candidate rankings and measurements do not mutate its content.

**Artifact:** private storage key; media type; bytes; checksum; original name stored privately; source; classification; rights; parser version; access scope; retention. Artifact URLs are not public paths.

**SourceDocumentRevision / SourceChunk:** original artifact; page/section/line/table locator; extraction method; extraction uncertainty; text; chunking version; rights and ACL. Keep original and normalized text; a chunk is not independent scientific evidence if all chunks share one source.

**Claim / EvidenceLink:** scoped statement; evidence type; source locator or run/measurement ID; conditions; support/contradiction/uncertain relation; review; temporal applicability. Store conflicting evidence rather than replacing it with the most convenient source.

**Run:** kind; immutable input manifest; engine/model/tool versions; resource request; policy decision; job reference; state; attempt records; outputs; failure category; timing; provenance. One run can have retry attempts, never overwritten logs pretending the first run succeeded.

**ExperimentPlanRevision:** task; candidate and process revisions; success contract; sample plan; metric/test methods; allowed deviations; required reviewer(s); hazard review; budget; immutable approval digest.

**Sample / ExperimentExecution:** planned and actual material lots; sample label; operator; planned/actual process; start/end; deviations; raw files; completion/abort reason. Separate preparation batches from aliquots and repeated measurements.

**Measurement:** sample/execution; metric; value or censored/ordinal/category representation; units; method/version; conditions; uncertainty/replicate semantics; quality status; raw source; reviewer; correction pointer. Raw measurements are immutable after review.

**DatasetSnapshot:** versioned inclusion query; explicit record IDs and hashes; use rights; purpose; labels; exclusions; split manifest; transformation hashes; confidentiality; approval. A live SQL query is not a reproducible dataset snapshot.

**ModelArtifact / ModelRelease:** model kind; base model; tokenizer; adapter; weights and format; training snapshot; configuration; environment; metrics; calibration; applicability; license; confidentiality; deployment status; rollback target. Training completion and release approval are separate.

**ExportRequest:** exact source artifacts; transformed payload; local-feasibility report; proposed provider/region; sensitivity assessment; recipient configuration; budget; approval; expiry; transfer receipt; deletion evidence. A single boolean `cloud_enabled` must not authorize arbitrary future exports.

## 5.3 SQL implementation requirements

Use normalized tables for identity, revisions, ownership, measurement references, approvals, runs, and datasets. JSONB is appropriate for versioned scientific payloads, method-specific settings, and conditions; it is not an excuse to put the entire application into one JSON table.

Use `NUMERIC` for stored decimal quantities and cost amounts. Reject NaN/infinity. Avoid PostgreSQL enum migrations for rapidly changing scientific vocabulary; use constrained text/reference tables with versioned registries. Use explicit enum-like constraints for stable workflow states. Index scoped lists on `(workspace_id, project_id, created_at, id)` and foreign-key lookup paths. Avoid unrestricted full-table JSON scans in core routes.

Implement `unique(entity_id, revision_number)`, `unique(workspace_id, idempotency_key, operation_name)`, and foreign keys that make an accepted record's referenced revisions non-deletable. Deletion of sensitive artifacts uses a separate lifecycle; tombstone metadata may remain, but retrieval and training must respect revocation. A deleted underlying source causes dependent claims to show unavailable evidence; it must not leave an apparently valid clickable citation.

# 6. Scientific values, units, composition, and missingness

## 6.1 Quantity contract

Represent a finite numeric value as a decimal string plus unit, dimensional category, basis/context, and original input. Scientific computation may convert to floats at an adapter boundary; record conversion and numerical tolerance. The authoritative stored value is not the browser's floating-point display.

Use a vetted units library; maintain a whitelist of supported unit IDs and conversions. Application validation must distinguish absolute temperatures from temperature differences, mass fraction from mass percent, active-solids basis from as-supplied basis, and formulation amount from application dosage. A concentration without basis is incomplete. Currency requires currency code and dated price source; never compare undisclosed different currencies as one cost scale.

No conversion between mass and volume without a relevant density, its units, conditions, source, and applicability. No automatic conversion between mole and mass fractions for unknown-composition mixtures. A result in mPa·s is not comparable to one in Pa·s until converted; viscosity comparisons also require compatible measurement conditions.

## 6.2 Formulation invariants

The pilot's optimizer-supported formulation representation is a reviewed **as-supplied mass-fraction basis**, with values between 0 and 1 and declared total 1. Other historical bases can be imported faithfully, but require a reviewed transform before using that optimizer representation. This is an adapter constraint, not a restriction on what products the studio can record.

Never silently normalize totals. An incomplete draft can sum below or above its stated total and display validation errors. A completed revision must pass its declared-basis rules within an explicitly versioned numerical tolerance. An intentional unknown remainder is represented by an unknown component and uncertainty; it does not authorize simulation or manufacturing. Duplicate ingredient lines require reconciliation or a documented reason, not silent summing.

Process order remains significant. Ingredient-list order may be canonicalized for deduplication where it is chemically order-independent, but process steps cannot be sorted alphabetically. Exact duplicate detection and near-duplicate grouping are separate operations. Preserve salts, stereochemistry, charges, polymer descriptors, lot/grade, substrate, and processing conditions when they affect interpretation.

## 6.3 Measurement value types

Support `numeric`, `interval`, `below_detection`, `above_quantification`, `ordinal`, `categorical`, and `missing`. Missing values require a reason, such as `not_measured`, `instrument_failure`, `sample_lost`, or `unknown`. A censored result is not zero; an ordinal rating is not an interval-scale number merely because its labels are digits. Default regression training excludes unsupported value types with a report; specialized modeling can be added later with explicit handling.

Preserve repeat types: same-sample repeated reading, independently prepared batch, independent operator/lab, and timepoint. Three readings of one aliquot are not three independent formulation successes. Aggregation is a derived result with an explicit method and retained underlying observations.

## 6.4 Historical failure taxonomy

Record `performance_miss`, `instability_observed`, `process_failure`, `safety_stop`, `instrument_failure`, `cancelled`, `sample_lost`, `incomplete`, or `unknown`. Only outcomes supported by applicable measurements may train the corresponding performance target. Instrument failures can train operational reliability models, but must not become negative chemistry labels. Mixed historical datasets must retain supplier claims, simulations, and lab measurements as different evidence classes.

# 7. State machines and transaction rules

## 7.1 Task states

`draft -> active -> awaiting_review -> closed`; `active <-> paused`; `draft/active/paused -> cancelled`. A task may return from `awaiting_review` to `active` with a review reason. Closing stores a closure decision (`supported_success`, `supported_failure`, `inconclusive`, or `stopped`) separately from workflow state. Only an authorized human reviewer can close. `supported_success` requires a frozen contract, all hard gates, applicable reviewed measurements for every required metric, and the contract's replication/review requirements. No agent tool can directly set success.

Reopening a closed task creates a reopen decision, retains the old closure packet, and creates a new evaluation cycle. Editing thresholds creates a new contract revision; old results remain attached to the old contract and are not retrospectively reclassified without a new recorded evaluation.

## 7.2 Candidate and evidence states

A candidate content revision is `draft -> submitted -> accepted_for_research` or `rejected`; accepted content is immutable. Scientific eligibility is separate (`not_assessed`, `eligible_for_computation`, `needs_review`, `blocked`, `eligible_for_approved_experiment`). No badge should suggest eligibility means laboratory proof.

A source extraction is `quarantined -> parsed -> needs_review -> accepted` or `rejected`. Accepted scientific evidence can be `superseded` or `revoked`; dependent retrieval results and new training snapshots must honor that state. A measurement is `uploaded -> quality_review -> accepted` or `rejected`; corrections create a new measurement record referencing the original.

## 7.3 Run states

`requested -> awaiting_approval -> queued -> running -> succeeded/failed/timed_out/cancelled`. `requested -> blocked` is valid for unsupported engines or insufficient inputs. `queued/running -> cancel_requested` must be visible until execution actually stops. A worker lost mid-run becomes `interrupted`; reconciliation may retry as a new attempt only under policy. A cancellation acknowledgment from the API is not proof that all child processes stopped.

State changes use database transactions and compare-and-swap rules. A late successful subprocess exit cannot overwrite a terminal canceled run. Persist output artifacts before publishing `succeeded`, and verify checksums/readability. Missing output, parser failure, nonconvergence, and rejected applicability each have explicit error/result states; process exit code zero alone is not scientific success.

## 7.4 Approval binding and idempotency

An approval binds principal, action, exact revision IDs, canonical input digest, contract revision, method/policy versions, permitted resource/financial envelope, expiry, and any recipient configuration. Changing any bound content invalidates approval. Do not bind merely to a mutable task ID.

Mutating API commands accept `idempotency_key` and, where applicable, `expected_version`. Persist the command outcome in the same transaction as domain changes and outbox events. Repeating the same key and payload returns the original result; repeating it with different payload fails. Retries must not create duplicate candidates, experiment executions, imports, training jobs, cloud transfers, or approvals.

The transactional outbox delivers at least once; consumers deduplicate using event/command IDs. Do not promise exactly-once delivery. Design side effects to be idempotent and reconcile external job IDs before retrying submission.

# 8. API contracts, Relay, events, and error behavior

## 8.1 Application API surface

Use GraphQL for application records and mutations. Use authenticated streaming HTTP endpoints only for artifact upload/download and run-event streams; these are deliberate transport exceptions, not a second CRUD API. Expose health/readiness separately with no sensitive payload. Generate the GraphQL schema from backend definitions and commit an exported schema for frontend code generation and breaking-change checks.

Required root queries include `viewer`, `workspace`, `projects`, `researchTask`, `node(id)`, `nodes(ids)`, `searchEvidence`, `engineCapabilities`, `hardwareCapabilities`, `pendingApprovals`, `modelReleases`, and `exportRequests`. Every growing collection is a cursor connection. Page size defaults to a bounded value and has a hard maximum. Sort using stable keyset ordering with an ID tie-breaker; tie cursors to scope/filter/order and reject mismatched cursor reuse.

Required mutation groups:

- Projects/tasks: create, draft update, create/approve contract revision, start/pause/resume, request closure, approve closure, reopen.
- Materials/candidates: create identities, propose alias matches, accept identity matches, create formulation/process revisions, create candidate revisions, accept/reject proposed patches.
- Evidence: initiate upload, finish upload, review extraction, link source, accept/revoke evidence, review contradictions.
- Sessions: create/resume session, append user message, request agent turn, cancel turn, accept/reject structured proposal, save reviewed summary.
- Runs: request, approve where required, cancel, retry, acknowledge failure, inspect capabilities. No generic `executeShell` or arbitrary Python endpoint.
- Lab: draft plan, submit for review, approve/reject plan, register sample/execution, record deviations, upload measurements, accept/reject/correct measurements.
- Learning: propose/freeze dataset, validate splits, prepare training run, approve/start/cancel, evaluate, promote/rollback model.
- Privacy: create export proposal, inspect transformed payload, approve/reject/revoke, launch transfer only within approval, reconcile deletion/retention evidence.

Each command maps to one application service with authorization, revision validation, domain invariants, transaction, outbox, and typed return value. Resolvers do not implement chemistry or business rules inline.

## 8.2 Relay acceptance requirements

Implement `Node { id: ID! }`, root refetching, canonical global IDs, and connections with `edges`, `node`, `cursor`, and `pageInfo` [S03]. Add `nodes` where useful but do not replace standard edges. Use batch-loading scoped to the request to avoid N+1 queries and cross-user cached authorization mistakes.

Components declare fragments near the consuming component. Use Relay query, fragment, mutation, refetchable-fragment, and pagination hooks. Only `apps/studio-web/src/relay/network.ts` handles GraphQL transport. Do not introduce component-level GraphQL fetch calls, manual mirrored entity arrays, React Query alongside Relay for the same entities, or a second Relay environment per screen.

After a mutation, update or refetch the correct connection using returned canonical IDs. New revisions have new IDs; views can show both revisions without cache collisions. A run event may trigger a Relay store update or refetch; it must not create a parallel job-state cache with different truth. Clear scoped cache on logout/workspace changes; do not persist sensitive Relay data to browser storage by default.

## 8.3 Mutation result shape and domain errors

Return a typed result with entity/result payload, `clientMutationId` when used, and a list of `DomainError { code, message, fieldPath, retryable, safeDetails }`. The server never returns raw private paths, credentials, tool stdout, or a SQL stack trace to an unauthorized client.

Implement at least these codes: `UNAUTHENTICATED`, `FORBIDDEN`, `NOT_FOUND`, `REVISION_CONFLICT`, `IDEMPOTENCY_MISMATCH`, `INVALID_UNIT`, `UNKNOWN_BASIS`, `COMPOSITION_TOTAL_INVALID`, `MISSING_IDENTITY`, `METHOD_INCOMPATIBLE`, `METRIC_NOT_DEFINED`, `EVIDENCE_INSUFFICIENT`, `QUALITY_REVIEW_REQUIRED`, `SAFETY_REVIEW_REQUIRED`, `APPROVAL_STALE`, `APPROVAL_EXPIRED`, `ENGINE_UNAVAILABLE`, `ENGINE_UNSUPPORTED_INPUT`, `NONCONVERGED`, `RESOURCE_UNAVAILABLE`, `LOCAL_INFEASIBLE`, `EXPORT_NOT_APPROVED`, `EXPORT_DIGEST_MISMATCH`, `DATA_RIGHTS_UNKNOWN`, `EVAL_CONTAMINATION`, `MODEL_NOT_PROMOTABLE`, and `RUN_ALREADY_TERMINAL`.

Errors should identify the corrective action without exposing secrets. For example: 'This value needs a concentration basis before comparison' is preferable to 'invalid payload'. A retryable flag never bypasses approval or generates an automatic cloud submission.

## 8.4 Events and streaming

The initial event envelope includes schema version, event ID, scope, aggregate ID/type, aggregate version, timestamp, actor type, correlation ID, causation ID, payload classification, and payload. Store only necessary metadata in queue messages; workers retrieve authorized payloads by ID.

Stream session/run progress with bounded buffers and sequence IDs. Reconnect resumes after the last acknowledged event where retained; otherwise return a snapshot plus a new cursor. Handle duplicate/out-of-order events. Distinguish partial assistant text, a valid final message, a proposed action, an approval request, and a completed action. A stream token saying 'saved' cannot substitute for a committed database operation.

# 9. Ingestion, source review, and the historical-data pipeline

## 9.1 Supported initial formats and ingestion transaction

Support text PDFs, DOCX, CSV, XLSX, Markdown/plain text, JSON, and common image attachments as data sources. Parsing must not execute macros, spreadsheet formulas, embedded scripts, or file hyperlinks. Use existing maintained parsers in a quarantine worker. Scanned documents require a separately enabled local OCR path and review; do not silently claim high extraction confidence.

The pipeline is: upload to quarantine; compute checksum; inspect declared and detected type; enforce size/decompression/page limits; scan/parse with timeout and no network; retain original; extract locators; propose structured records; show a review diff; accept authorized fields; create indexed evidence. Upload completion does not imply extraction acceptance.

For spreadsheets, preserve workbook, sheet, cell/range and units. Treat formulas as untrusted source expressions; read cached values where available, and mark missing/stale cached results rather than evaluating arbitrary expressions. Preserve merged/header context. Detect decimal separators, percentages, locale dates, and unit/basis ambiguity. Never quietly turn a cell labeled '5%' into mass fraction `5`.

## 9.2 Import review experience

The review screen places the source beside proposed records, shows unresolved identities, conflicting values, low-confidence fields, and duplicates, and supports accept/reject per field or row. Extracted amounts are not production formulations until accepted. Display the source locator for each extracted value. A model-suggested unit or ingredient identity is visibly distinct from text actually present in the document.

Imports are idempotent by artifact checksum plus parser/transformation version and scope. Reimporting a newer document creates a source revision; it does not silently overwrite an accepted historical recipe. Aliases require review, especially when a trade name maps to multiple suppliers/grades. Retain user corrections as reviewed extraction examples, not automatic scientific ground truth for unrelated products.

## 9.3 Data quality report

For each import batch, report records received, parsed, quarantined, accepted, rejected, duplicates, ambiguous identities, missing units, unknown concentration bases, incomplete process context, unlinked measurements, missing raw files, rights unknown, and training exclusions. Show a coverage matrix by product family, metric, method, and evidence type. Do not show a single inflated 'data quality score'.

Historical failures and successes are both imported. Normalize outcome categories only after preserving original labels and source text. Record whether an outcome was measured, informally observed, supplier-reported, or inferred. No example becomes an RL reward merely because the word 'successful' appears in a document.

## 9.4 Rights, classification, and permitted uses

Each source has separate decisions for internal retrieval, structured extraction, model training, cloud export, and redistribution. Unknown rights default to internal quarantine/review, not broad permission. The studio must allow recording the existence of a restricted source without indexing its content for all users.

Classify raw documents, structured recipes, embeddings, retrieval summaries, spectra, datasets, checkpoints, adapters, and logs. Derived artifacts inherit at least the maximum source sensitivity unless an authorized review records a justified change. A renamed file or a random product alias does not lower sensitivity automatically.

# 10. Persistent research memory and evidence-backed assistance

## 10.1 Memory layers

Maintain structured task state, reviewed decisions, an evidence graph, session messages, and generated summaries as separate layers. Structured task state is authoritative. Summaries are derived navigation aids with source IDs, creation model/version, coverage, and staleness markers. Never reconstruct the only copy of an experiment outcome from a summary.

On session start, compile a task context manifest containing the current contract, selected candidate revisions, relevant reviewed evidence, open questions, accepted/rejected approaches, active approvals and runs, and user-accessible history. Enforce a token budget by selecting and summarizing material, not by truncating scientific units or silently dropping constraints. Always preserve hard constraints and unresolved safety/identity warnings.

Retrieval is scoped by workspace/project/rights/quality status and evaluation policy. Return chunk IDs and precise source locators. Search lexical text first; add locally generated embeddings only with an evaluated benefit. Cache retrieval using query, scope, principal permissions, source-index version, and policy version; invalidate on access revocation or evidence supersession.

## 10.2 Agent turn and tool policy

A turn has a finite budget for tokens, wall time, tool calls, and compute. The model can research, ask for missing scientific inputs, propose candidate patches, request calculations, and draft experiment plans. It cannot directly approve a lab plan, accept measurements, lower sensitivity, export data, promote a model, or close a task as successful.

Use typed tools with JSON Schema inputs and outputs. Tool names should describe domain operations, such as `search_evidence`, `read_candidate_revision`, `validate_formulation`, `request_calculation`, `propose_candidate_patch`, `draft_experiment_plan`, and `summarize_task_evidence`. Tools call the same application services as the UI. No unrestricted shell, arbitrary code execution, raw SQL, or recursive agent spawning in the runtime product.

Optional MCP access is allowed only through a registered tool adapter with the same scope, schema, budgets, and approval enforcement. Discovered tools are not automatically authorized. No broad MCP marketplace or dynamic third-party code execution is required for the pilot. Keep tool metadata and capabilities cached and versioned; do not repeatedly fetch unchanged definitions.

## 10.3 Evidence and prompt-injection defenses

Treat uploaded text, research pages, patents, tool outputs, and retrieved passages as untrusted data. Instructions embedded in them cannot change tool permissions, export policy, success criteria, or system behavior. Present citations as references to source content, never executable instructions.

The assistant should distinguish sourced statements, derived calculations, hypotheses, and unknowns. A supported citation must point to accepted accessible evidence and compatible conditions. A citation existence check does not establish scientific entailment; use deterministic locator checks plus explicit model/human review where needed. Contradictory evidence remains visible.

The research agent stores observable inputs, outputs, structured proposals, tool calls/results, and concise reviewed rationale. Do not require hidden chain-of-thought extraction or treat a long private reasoning trace as scientific evidence. When a tool fails or evidence is absent, the response must say so instead of inventing a result.

# 11. End-to-end behavior for the three task modes

## 11.1 Shared task creation and resumption

The user chooses a mode, names the task, selects a project/product family, and attaches or searches available material. The system proposes a success contract with unknowns highlighted. The user can save a draft immediately; activation requires only the fields necessary for the intended next action. Deterministic tools explain missing requirements before scheduling.

The task workspace contains an overview, research sessions, candidates, experiments, evidence, and decisions. These are views of one task, not independent applications. The persistent header shows current objective/contract revision, required metrics, evidence coverage, blocking items, and the next authorized action.

A new session resumes from a task snapshot, not an empty chat. Changes proposed by the assistant are displayed as structured diffs. Accepting a patch creates a new revision; rejecting it records the reason without changing the current candidate. Concurrent edits trigger conflict resolution. Old sessions remain linked to the context that existed at their start.

## 11.2 Improve an existing formulation

Require an identified baseline formulation revision before calculating improvements. The baseline may come from an accepted historical record or a newly reviewed import. Retrieve baseline performance with methods/conditions; unknown baseline metrics remain unknown. Specify what may vary and what must be preserved: ingredients, composition ranges, grades, process windows, substrate, cost basis, and fixed properties.

The workflow is baseline -> success contract -> evidence review -> proposed candidate changes -> deterministic validation -> optional applicable predictions -> human selection -> approved experiment -> measurement quality review -> comparison to baseline -> next experiment or closeout.

Report per-metric deltas only on compatible evidence. A lower predicted cost does not establish improved wash durability. Do not compare a candidate prediction to a measured baseline without clearly identifying their different evidence classes. Record which baseline lot and method were used in any actual comparison.

## 11.3 Match a reference product

Start from a reference-product revision and explicit matching scope: `functional`, `analytical`, or `functional_and_analytical`. Exact composition recovery is a distinct research hypothesis, never the default interpretation of a matched performance result.

The product may have documentation and samples but no recipe. Keep supplier claims separate from measured reference properties. Create a target measurement fingerprint using approved methods. Analytical files can be linked even before advanced spectral processing is installed; their presence alone is not an interpreted result.

Propose candidate formulations or materials with stated hypotheses. Compare functional endpoints and analytical endpoints separately with specified tolerances and conditions. A task can conclude 'functional targets met under the tested conditions; composition not established'. It cannot conclude 'same molecule/recipe' from a matching marketing sheet or a single similar spectrum.

Maintain source ownership/rights and review constraints before using proprietary reference documents for training/export. No patent freedom-to-operate or legal clearance claim is generated automatically; the interface can record a human/legal review as external evidence.

## 11.4 Discover something new

The user selects target kind: formulation, material, or molecule. If uncertain, preserve `unknown` in the task draft and help scope the target without manufacturing a molecular representation. Set measurable objectives and constraints, then search historical internal evidence and approved public sources.

For formulations, discovery can begin with approved ingredients and processes; it does not require de novo molecular RL. For materials, preserve polymer/distribution or other descriptors and gate calculations to supported representations. For molecules, first validate structures and allowed scope; optionally use an approved REINVENT/AiZynthFinder adapter in the later milestone [S11, S12].

Novelty is evaluated relative to a declared corpus/search date and matching rule. 'Not found in this corpus' is not global novelty or patentability. A candidate is still useful when it matches targets without being novel; record the distinction rather than rewarding unsupported novelty claims.

# 12. Verification service: policy, evidence, and scientific applicability

## 12.1 Four independent axes

Every claim/result has: evidence type (`source_report`, `descriptor`, `physics_prediction`, `learned_prediction`, `lab_measurement`, `replication`); execution status; applicability (`supported`, `out_of_domain`, `unknown`); and acceptance (`meets`, `misses`, `inconclusive`, `not_evaluated`). Quality review and safety eligibility are additional gates. Never introduce `verified: true` as a universal shortcut.

A valid RDKit structure establishes a structural check, not synthesis feasibility or safety [S01]. A quantum calculation's output is a physics-model result. A property predictor's confidence needs calibration and applicability evidence. A lab measurement supports only its recorded sample, method, conditions, and scope. Independent replication is a specific experimental relationship, not another name for rerunning the same script.

## 12.2 Gate evaluation order

Authorize access; validate schema/identity/units; verify input completeness; enforce permitted task scope and hard exclusions; check engine/method applicability; check review and approval requirements; check resources and budgets; execute; validate execution/convergence/output; evaluate evidence quality; evaluate contract metrics. Each stage can return multiple actionable findings.

Safety, identity, licensing, and data-rights gates are not reward terms that can be offset by better performance. Ineligible candidates can remain visible for research with a block reason; they cannot progress to prohibited execution. Any human override must be a documented policy-authorized exception to a specific reviewable gate; no blanket safety bypass switch exists.

## 12.3 Success evaluator algorithm

Load the frozen contract, candidate revision, and permitted evidence snapshot. For every required metric, find accepted results with compatible method, units, substrate, conditions, evidence class, and repeat requirements. Convert units only through a recorded allowed transform. Apply the declared operator/tolerance and aggregation procedure. Missing, censored-unsupported, incompatible, or insufficiently replicated results are `inconclusive`, not passed.

Evaluate all hard constraints independently. Return a per-metric table, eligibility findings, evidence IDs, unknowns, and a suggested closure decision. A human reviewer approves the closure packet. A later corrected measurement or revoked source marks the prior conclusion as needing reassessment; it must not silently rewrite the signed historical packet.

## 12.4 Method and applicability registry

Each method definition records engine/template version, supported inputs, element/charge/state constraints where relevant, force-field/parameter requirements, environment limits, output meanings and units, failure conditions, approved benchmark set, and known limitations. Missing parameters must return `ENGINE_UNSUPPORTED_INPUT` rather than guessed substitutes.

For emulsions/coatings, do not equate molecular descriptors or equilibrium miscibility with storage stability, adhesion, durability, or processability. The studio's design must require an explicit, scientifically reviewed link between a proxy and the task endpoint before using it for decision support. Retain the lab endpoint even when a surrogate is useful.

# 13. Jobs, engine adapters, isolation, and cancellation

## 13.1 Engine adapter contract

Every adapter implements capability discovery, input validation, resource estimation, execution submission, status reconciliation, cancellation, and structured result parsing. The contract includes engine ID/version, adapter version, input/output schema versions, supported methods, installation health, license status, reproducibility metadata, and required isolation profile.

Use `RunRequest` and `ToolResult` schemas rather than passing human paragraphs to a command line. The gateway selects an allowlisted calculation template; user/model fields fill validated parameters only. Never concatenate input into a shell command. An adapter unable to honor its requested timeout, cancellation, or network restrictions must report unavailable for that profile.

## 13.2 Reuse boundary

RDKit covers structure parsing/sanitization/descriptors [S01, S02]. QCEngine provides execution standardization through QCSchema and connects to supported engines [S06]. xTB and Psi4 provide targeted quantum capabilities [S07, S08]. Procrastinate supplies queue primitives [S05]. We own the policy, input manifests, job accounting, permission checks, result semantics, and UI. We do not rewrite the scientific engines.

Optional AiiDA integration may become appropriate for complex computational workflows [S17]. Introduce it behind a `WorkflowExecutor` interface with one owner for scientific job orchestration. Do not let AiiDA and the application queue independently retry the same underlying calculation. Keep the application Run as the user-visible record, linked to the external workflow ID.

## 13.3 Isolation profile

Run scientific binaries and model loaders as restricted subprocesses/containers with allowlisted mounted inputs, a writable per-run scratch directory, no host home directory, no container-runtime socket, no unnecessary credentials, and network denied by default. Set explicit CPU/thread, memory, disk, output-size, process-count, and wall-time limits. Validate archive extraction paths and reject symlink escapes.

A virtual environment solves dependencies, not security isolation. The worker records the actual isolation profile and capabilities. On platforms where a control cannot be enforced, do not claim it is active. Restricted/public synthetic workloads may have a documented reduced-isolation development profile; proprietary or untrusted code execution requiring stronger controls remains blocked.

Do not install arbitrary user-supplied packages or load untrusted serialized Python objects in the API process. Model artifacts are untrusted inputs until checksum, origin, license, format, and compatibility checks pass. Prefer non-executable weight formats; when an upstream format requires an unsafe loader, isolate it and require explicit review rather than silently trusting it.

## 13.4 Scheduling and resource enforcement

Detect CPU count, available memory, GPU devices/backends and free memory where measurable, disk space, installed runtimes, and concurrency. Unified memory must not be double-counted as separate RAM plus VRAM. Resource estimates include a confidence/status, not a guaranteed exact number.

Reserve resources transactionally before start. Default to one heavy job per constrained resource group until benchmarks justify concurrency. Leave a configurable reserve for the OS/API/inference. Small metadata requests remain responsive while heavy jobs run. Queued jobs carry budget caps and expiries; stale approvals are rechecked at execution, not just enqueue time.

A resource watchdog can cancel a run that exceeds its envelope. Bounded retries apply only to classified transient infrastructure errors; invalid structures, failed scientific convergence, unsupported methods, and policy denials are not blindly retried. A new numerical method or relaxed convergence threshold is a new reviewed run, not an invisible retry.

## 13.5 Cancellation and recovery acceptance

Cancel the entire process tree; after a grace period use the platform's supported hard termination. Verify resource release and record final child-process status. A worker crash/restart reconciles persisted Runs and external IDs. Partial artifacts are retained as incomplete/restricted or cleaned according to policy, never promoted as full results.

Content-addressed cache keys include canonical input, chemical/context representation, engine/model/method/parameter versions, precision, seed where applicable, adapter version, and policy applicability version. Cache access is scoped. Changing a temperature, lot-dependent descriptor, force field, or formula basis must not hit an old incompatible result. Deterministic cache tests and permission-revocation tests are mandatory.

# 14. Laboratory loop and measurement acceptance

## 14.1 Manual-first workflow

The studio drafts an experiment plan referencing immutable candidate, process, contract, and method revisions. The scientific reviewer sees the full diff, unknown inputs, documented hazard considerations, resource needs, sample plan, and acceptance criteria. Approval binds these exact inputs. Changing ingredients, concentrations, preparation steps, conditions, or required methods invalidates the release approval.

After approval, export a clearly marked experiment packet for a qualified human operator. The system does not start equipment. The operator records actual materials/lots, sample IDs, deviations, timestamps, and observations. The application can record historical experiments that lack preapproval, but must mark them as historical imports and require evidence-quality review; it must not fabricate retrospective approval.

## 14.2 Sample and measurement semantics

Allow one plan to produce multiple independent preparation batches, multiple samples/aliquots, and multiple readings/timepoints. Each measurement belongs to a sample/execution and a method revision. Record planned versus actual conditions. Deviations can make a measurement inapplicable to the original contract while still scientifically useful; preserve it with that distinction.

A reviewer can accept raw result integrity yet reject applicability to a target. Store raw files and normalized values with a processing pipeline version. Measurements can be corrected only through an amendment with reason and source. Dependent comparisons, training snapshots, and model cards must surface superseded evidence.

## 14.3 ELN integration without dual truth

Use the native studio entities for its task/candidate/approval/measurement workflow. If eLabFTW is connected, use its existing API for linked experiment records and attachments [S16]. The initial optional adapter is explicit one-way export plus read/import of selected results, not silent bidirectional synchronization.

Document ownership: the studio owns task contracts/candidate revisions and its approval decision; the ELN may own the laboratory narrative/raw record. External IDs, record versions, checksum, last-sync time, and conflicts are stored. A conflict requires review. Disconnecting the ELN must not delete imported evidence or pretend unavailable live data is current.

## 14.4 Replication and scale-up

A replication plan states what is repeated, by whom, on which lot/batch, under which method, and the acceptance rule. The required replication count/independence is a scientific input left unknown, not hardcoded from this plan. A test dataset with arbitrary count three is a fixture, not a scientific policy.

Do not infer manufacturing readiness from a small lab batch. Scale-up, long-term storage, environmental/worker exposure, application-specific standards, and commercial claims require their own scope and reviewed evidence. The first product release supports recording these tasks; it does not certify them.

# 15. BayBE and property-model integration

## 15.1 Campaign definition

Use BayBE for approved parameter-space experiment planning [S09]. A campaign version pins task/contract, parameter definitions, discrete ingredients or continuous variables, constraints, target transformations, observed measurements, pending experiments, random seed, recommender configuration, and software version.

The adapter must validate parameter/constraint compatibility before suggesting points. BayBE's documented constraints have scope limitations; in particular its current documentation does not support arbitrary hybrid constraints across mixed discrete and continuous parameters [S09]. Record the tested installed version. Reject unsupported mappings or use a reviewed reparameterization/finite enumeration; never drop a constraint to make the library run.

## 15.2 Proposal algorithm and invariants

Build features only from the frozen campaign data allowed for that purpose. Convert the approved representation into BayBE inputs. Request a bounded batch. Independently validate every returned candidate against the studio's domain and hard constraints. Deduplicate against existing/pending suggestions with an explicit scientific identity rule. Record acquisition/recommender information and uncertainty where available; do not invent it when a recommender lacks it.

Pending experiments are not observations with value zero. Failed or cancelled jobs are not performance labels. If the candidate space is exhausted or feasible suggestions cannot be found, return an explanatory status. No unsupervised loops generate thousands of physical plans. Human review selects which suggestions become approved experiments.

Cold-start campaigns can use an appropriate existing random/space-filling design under the same constraints. Record which baseline was used. Optimizer results do not prove superiority over a simple baseline; evaluate retrospective replay carefully and then prospectively compare experiment usefulness under a documented budget.

## 15.3 Property models

Begin with simple regression/classification baselines suitable for the available data and value types. Molecular predictors are a different representation from formula/process models. Chemprop can support molecular-property training/prediction and uncertainty tools [S10], but it is not automatically a pretrained predictor for the user's coating. Choose features and architecture after inspecting the data.

Retain material identities, grade/active-content, composition basis, process/substrate, and method context. Split related formulations together. Fit encoders, imputers, scalers, feature selection, and calibration on the appropriate training/calibration partition only. Do not leak held-out measurements into feature engineering or fit preprocessing on the full dataset.

Every predictor publishes target/method scope, training coverage, missing-value policy, calibration report, applicability assessment, and limitations. Insufficient data yields `not_ready`, not synthetic confidence. Out-of-domain predictions may be displayed for exploratory review with explicit limitations, but cannot masquerade as validated candidate ranking.

# 16. Targeted chemistry and analytical integrations

## 16.1 Integration priorities and capability labels

Install RDKit and the deterministic formulation verifier in the pilot. Implement the BayBE adapter after the experiment/measurement foundation. Add QCEngine with xTB/Psi4 only for defined molecular questions with supported representations [S06–S08]. The application must expose each adapter's actual state: available/tested, installed/unverified, not installed, license unavailable, unsupported platform, insufficient inputs, or disabled by policy.

Do not bundle every engine into the first installer. A 'run simulation' button without method selection/applicability and a tested backend is prohibited. Engine smoke tests use benign public structures or upstream reference examples; output tolerances are method/version-specific, not invented target-product acceptance thresholds.

## 16.2 Quantum adapter recipe

Accept a supported explicit molecular representation, required charge/spin state, geometry provenance, method/template, solvent/context where applicable, and resource envelope. Validate units and atom ordering. Construct the selected version's QCSchema input and persist it before execution. Execute the supported engine under the worker isolation profile, parse structured output, preserve raw output, and classify convergence/quality.

Test structure/charge errors, missing binaries, unsupported methods, malformed output, timeout, cancellation, memory exhaustion, and a completed reference calculation. A successful reference calculation demonstrates installation/integration, not the appropriateness of the method for a proprietary material. Scientists approve method applicability separately.

## 16.3 Materials and thermodynamics

`thermo` supplies thermodynamic/phase-equilibrium models [S18]; LAMMPS supplies molecular/materials dynamics capabilities [S19]. Their adapters are optional, task-driven work packages. Before enabling one, specify which measured endpoint or proxy it supports, its required parameters, valid domain, computational budget, and benchmark against relevant data.

Do not substitute guessed force fields, missing binary parameters, or a generic molecule for an unknown polymer distribution. Missing information produces a blocked capability. Equilibrium calculations do not directly establish kinetic emulsion stability. Model assumptions, boundary conditions, ensemble, sampling/convergence, and calibration are part of the result manifest.

Commercial implementations such as COSMO-RS may be evaluated later through the same adapter boundary; no license is selected or purchased here. Machine-learned potentials are optional future adapters, not universal scientific truth. Changing the engine requires a new method applicability record and tests, not merely a configuration label.

## 16.4 Molecular design and synthesis planning

REINVENT 4 is a candidate reusable engine for small-molecule generation/optimization [S11]. AiZynthFinder provides retrosynthetic search [S12]. Both are later capabilities with separate code/model/data license checks. Their outputs remain candidates or proposed routes. A route reaching stock precursors is not evidence of practical yield, selectivity, safety, or scale-up.

Route scoring and candidate generation must respect allowed scope and the same safety/review gates. No generated route is automatically released as an executable lab protocol. Task novelty claims remain bounded to specified sources and searches. Validate known-invalid structures and unsupported input kinds; reject polymer/formulation input where only a defined molecule is supported.

## 16.5 Analytical workflow

Initially store raw spectra and instrument exports with method/calibration/sample metadata and reviewed derived values. Later add dedicated processing adapters for selected instruments/formats. Keep processing separate from interpretation and identity claims. Use validated library/vendor methods rather than training a universal spectrum interpreter from tiny proprietary data.

Reference comparison must account for method, sample preparation, preprocessing and alignment. A similarity score requires its algorithm, version, relevant range, and interpretation limit. Do not collapse multiple analytical methods into one opaque percentage or imply a single spectrum establishes complete composition. Existing analytical libraries can be evaluated in the corresponding ticket; they are not claimed installed or benchmarked by this handoff.

# 17. Training architecture from the first database migration

## 17.1 Four different learning products

The evidence vault and retrieval index expose knowledge without changing model weights. Property models learn specified input/outcome relationships. Assistant fine-tuning teaches bounded behaviors, representations, and tool use. RL optimizes an agent policy against an explicitly defined environment/reward. These use separate datasets, evaluations, release names, and permissions.

Do not train a foundation model from scratch as the default. Select a suitable licensed local base model through measured capability/hardware tests. An assistant adapter is not a replacement for continually updated task evidence. A property model cannot be called a chemistry reasoning model merely because it predicts one endpoint well.

## 17.2 Dataset construction algorithm

1. Select purpose and scope: retrieval/extraction correction, property prediction, supervised assistant examples, preference pairs, or RL training tasks.
2. Resolve source and derived-record lineage. Include only records whose rights, consent/classification, quality, and applicability permit that purpose.
3. Create a point-in-time snapshot of IDs, revisions, hashes, source classes, targets, contexts, transformations, exclusions, and unresolved issues.
4. Build grouping keys connecting related formula revisions, shared preparation batches, repeated measurements, near-duplicates, and task/session-derived examples. Use connected components where several relationships link records.
5. Assign train/development/calibration/final-evaluation partitions under a declared policy. No formula sibling or repeated reading may cross a split merely because it has a new row ID. Keep an untouched final evaluation set; do not repeatedly optimize against it.
6. Generate examples using reviewed outputs and authorized source inputs. Detect duplicates, contradictions, missing units, rejected data, and leaked outcome labels. Record manual exclusions.
7. Validate the full manifest; obtain training approval; freeze all artifact hashes. Changes create a new snapshot and require reevaluation of affected approvals.

No minimum sample count is invented here. The data-readiness report must state whether learning/evaluation is meaningful for each task family, including uncertainty due to small samples. Synthetic data can test the pipeline but cannot substitute for actual validation.

## 17.3 Supervised examples and preference pairs

Use examples such as: evidence-backed answers; correct extraction with source locators; identifying a missing concentration basis; selecting an appropriate registered tool; interpreting nonconvergence; refusing to label an unmeasured endpoint as proven; producing a valid candidate diff; and asking for the minimum necessary scientific clarification.

Store the user/task context, allowed evidence manifest, input messages, observable tool calls/results, reviewed final response, label provenance, rights, and split group. Do not store required hidden reasoning traces. Mask loss on input context when appropriate for the selected trainer; verify the actual version's formatting and role handling. Training must not simply teach the model to reproduce confidential recipes indiscriminately.

Preference pairs need a reason and reviewed criterion. A high-performing formulation does not automatically make every preceding research action good. A failed experiment does not automatically make the entire research trajectory bad: useful information gathering can be valuable. Do not derive simplistic pair labels solely from final performance.

## 17.4 Local assistant fine-tuning

Use PEFT/LoRA as an initial candidate parameter-efficient method, subject to runtime compatibility [S13]. Reuse an established trainer; isolate its environment. Persist base/tokenizer hashes, adapter configuration, preprocessing, seeds, exact dependencies, optimizer/scheduler, batch/accumulation settings, sequence length, precision, checkpoint policy, and approved resource envelope.

First execute a tiny synthetic smoke job that proves actual weight updates, checkpoint save/load, cancellation, and resume. Then run a real approved dataset only when available. Show loss and progress as training telemetry, not chemistry validation. Ensure evaluation uses the fine-tuned artifact actually produced, not a mistakenly cached base model.

Quantization, gradient accumulation, checkpointing, CPU offload, or smaller context can be attempted only where supported and documented. Record any change to task/model/sequence constraints; do not silently turn an approved training run into a different model to make a memory estimate fit. Preserve the local infeasibility report if no compatible configuration is acceptable.

## 17.5 Training-run lifecycle and registry

States: draft -> dataset_validated -> awaiting_approval -> queued -> running -> completed -> evaluating -> candidate_release -> promoted/rejected. Failed/cancelled/blocked are explicit alternatives. `completed` means the optimizer ran and outputs exist, not that the model is deployable.

Register all artifacts as confidential unless justified otherwise. Store adapter-base compatibility and conversion steps. A serving-format conversion is a derived artifact that needs its own checksum and parity evaluation. Unsafe model loaders are isolated. Existing sessions pin the model release they began with; new sessions use the current approved release. Promotion is atomic with rollback to a known-good release.

Deleting or revoking a training source does not guarantee the model has forgotten it. Mark affected model lineage, suspend reuse/promotion where policy requires, and require a reviewed retraining/remediation decision. Document backup and retention effects honestly. No unlearning guarantee is made.

# 18. Evaluation, calibration, and model promotion

## 18.1 Evaluation registry

Define a versioned evaluation suite with tasks, allowed context, hidden target/answers, tools, tool versions, resource budget, scoring, review rules, and acceptance thresholds. The suite is separate from the optimizer's reward. Record dataset lineage and contamination checks. Only an evaluation service principal can access hidden labels; neither the agent under test nor its retrieval tools can query them.

Related record grouping covers raw documents, extracted tables, summaries, embeddings, session transcripts, candidate revisions, experiment results, reports, and models trained on held-out labels. Do not merely remove one answer column from a CSV. An evaluation task's legitimate reference targets remain allowed when explicitly part of the test input; separate them from withheld candidate outcomes.

A model trained on an evaluation outcome can leak through a prediction tool. Evaluation therefore pins an allowed model/tool registry whose training lineage respects the split. Separate development evaluation for tuning from a final release evaluation; after extensive use, retire or replenish the final set under a new version rather than continuing to claim it is unseen.

## 18.2 Baselines and comparisons

Compare the proposed assistant against the unmodified base model with the same retrieval snapshot, tool access, prompts, token/compute budget, and allowed context. Where testing retrieval or tool improvements, use explicit ablation groups rather than attributing every gain to fine-tuning. Property models compare against appropriate simple baselines and previously released models on the same examples.

Measure schema validity; correct tool choice; source support and citation accuracy; unit/basis handling; appropriate abstention; constraint compliance; duplicate/unnecessary actions; and supported task completion. Measure both answerable and insufficient-evidence tasks so 'always refuse' cannot win. Report denominator, missing/invalid results, uncertainty and subgroup coverage, not just an average.

For numerical prediction report suitable error/ranking metrics and calibrated uncertainty for the endpoint. Chemprop provides calibration/evaluation facilities where applicable [S10]. Calibration is fitted on its own permitted partition; report coverage and interval width under the tested data assumptions, not unconditional certainty for out-of-domain chemistry.

## 18.3 Experimental usefulness and scientific gates

Retrospective replay is a useful software/research test but is vulnerable to selection effects and incomplete historical coverage. Treat it as preliminary. Prospective campaigns should compare against a documented baseline under comparable budgets and explicit acceptance rules, with a scientific reviewer defining statistical/design details.

Do not invent required accuracy, percentage gain, sample count, or maximum error. Store unknown thresholds as promotion blockers. A model can be enabled for a limited experimental role only through a documented approval with scope and limitations; it cannot receive a blanket 'better chemistry model' label.

## 18.4 Promotion algorithm

Validate dataset rights and hashes; confirm no contamination findings; verify model-load/conversion tests; compare the matched baseline; verify mandatory safety/privacy regression tests have no new failures; inspect endpoint/subgroup metrics; require a scientific review where scientific performance is claimed; record remaining limitations; obtain release approval; atomically update the release pointer.

Rollback restores the serving pointer and compatible runtime configuration, not old scientific data or schema. The previous model remains available if its rights/lineage are still valid. Canary sessions and error monitoring can trigger a rollback request, but cannot overwrite audit history. Training runs never self-approve promotion.

# 19. Controlled RL for research decisions

## 19.1 Preconditions

Do not start RL until the deterministic workflow, approved tools, stable datasets, baseline evaluations, and measured verifiers exist. The initial RL environment is computational/replay-based; it does not run physical experiments autonomously. Laboratory evidence can later inform supervised/property updates and reviewed rewards without putting live lab equipment inside an unattended policy loop.

TRL provides existing GRPO and custom reward infrastructure [S14]. Choose a supported algorithm according to the validated task/reward structure; GRPO is an available option, not an unconditional architectural requirement. Check actual trainer/environment interfaces for the pinned version before implementation.

## 19.2 Environment contract

`reset(task_id, seed, evidence_snapshot, policy)` returns permitted observations and constraints. `step(action)` validates the typed tool action, checks budgets/permissions, executes an approved tool or replay lookup, and returns an observable result, cost, status, and reward components. `terminate(reason)` records the final outcome. Enforce maximum steps, wall time, tokens, calls, and compute independently of the model.

The policy never sees hidden labels, reward-only metadata, credentials, or evaluator tool outputs unavailable at inference time. Tool errors are observations, not high-reward shortcuts. Replay outputs must be identified as replay, and unmatched actions fail explicitly instead of inventing an oracle answer.

## 19.3 Reward design

Keep eligibility gates outside the performance trade-off. Within eligible episodes, define versioned measurable components for task correctness, supported evidence, valid tool execution, calibrated uncertainty/appropriate abstention, and resource efficiency. Do not use novelty, verbosity, citations-count, or the model's own confidence as truth.

No single property predictor is sufficient to prove discovery value. Prevent reward hacking through duplicate action loops, repeated cheap validity calls, fabricated citation IDs, manipulating units/baselines, ignoring difficult metrics, always abstaining, or selecting an easier task mid-episode. Hold task/contract and reward versions fixed within a run. Test adversarial policies that intentionally exploit each shortcut.

The reward service runs separately from the policy and writes component-level records with provenance. A model-based judge can assist review, but cannot be the only arbiter for facts that have deterministic/lab evidence. The held-out promotion suite is not callable as a training reward endpoint.

## 19.4 RL acceptance and release

A smoke test proves a short actual optimization run, meaningful parameter/checkpoint change, reproducibility metadata, cancellation/resume, and reward trace persistence. A scientific improvement claim additionally requires independent evaluation and, where relevant, prospective lab evidence. Rising reward with flat or worse independent performance is a failed promotion.

Preserve the last good supervised release. Bound expensive rollout concurrency under the same scheduler. A missing local GPU can block actual RL execution without blocking environment/contracts/unit tests. Cloud fallback still requires the specific local-infeasibility and export approvals below.

# 20. Local compute admission and cloud fallback

## 20.1 Capability report and feasibility decision

The hardware report includes OS/architecture, memory model, available RAM, GPU backend/device/free memory when observable, disk, runtime versions, available engine installations, isolation features, and timestamp. It contains no invented benchmark throughput. A job feasibility report lists requested operation, model/data/sequence sizes, estimated resources and uncertainty, compatible local configurations, test/estimation evidence, and why the selected approved configuration fits or fails.

Do not run a reckless full-scale job merely to prove an out-of-memory failure. A conservative tested estimator, bounded probe, or compatibility check may establish local infeasibility. 'Cloud is faster' or 'there are cheaper cloud credits' does not meet the user rule by itself. A cost/time preference is not silently reinterpreted as physical impossibility.

Try supported local alternatives within the approved task: smaller batches, accumulation, supported precision, or offload. Material changes to model/task quality need approval. Without an acceptable local configuration, propose an export review; do not submit automatically.

## 20.2 Cloud authorization boundary

The default egress policy denies proprietary outbound data. Source-data rights, export eligibility, provider/region approval, budget, local-feasibility evidence, and exact payload review are separate checks. A cloud credential's existence is not approval. No provider is selected in this handoff; implement a provider-neutral broker and keep live submission disabled until configured.

An approved export manifest binds source/derived hashes, transformation version, payload fields, redaction report, classification, recipient/account/region, container/runtime digest, permitted job, limits, retention/deletion expectations, expiry, and approver. Approval must be revalidated immediately before transfer. Retries are allowed only within the same manifest, recipient, expiry, and budget.

## 20.3 Abstraction is not a confidentiality guarantee

NIST distinguishes disclosure-risk management from superficial masking [S15]. In this application, names can be replaced while the valuable ratios, structures, process windows, and outcomes remain exposed. Conversely, removing all chemical meaning may prevent the intended learning. Describe this trade-off in the export UI; never label a dataset safe merely because product IDs were changed.

The transformation pipeline is explicit: select minimum records/fields; remove direct identifiers; replace aliases with a local-only mapping where useful; strip metadata; review free text, tables, paths, spectra and derived features; test residual disclosure; preview exact payload; decide whether the remaining information is acceptable for the selected execution environment. A scanner can flag risk; it cannot certify that all trade secrets are removed.

Encryption in transit/at rest does not hide plaintext from a normal training process. Confidential-computing environments may provide protection during computation [S22], but hardware/backend/attestation coverage and residual risks must be verified for the actual job. Do not claim tokenization, embeddings, split learning, or unspecified encryption enables secret training automatically. Differential privacy or specialized cryptographic training is research scope, not a shipped promise.

## 20.4 Confidential execution adapter, if approved

The implementation must verify the exact approved environment identity/attestation before releasing decryption keys where the chosen provider supports that mechanism. Pin code/container/model dependencies; restrict network and operator access; disable content logging/third-party telemetry; use ephemeral credentials; enforce private artifacts and short-lived access; reconcile job termination and storage deletion; import outputs as confidential/untrusted until checked.

Attestation failure or unavailable approved GPU coverage fails closed. Record what the provider can still observe, such as metadata, job timing, payload size, or network endpoints. Do not claim secrecy against a compromised guest application or all side channels. A live provider remains `not_configured` until tested with synthetic payloads and reviewed by the owner.

## 20.5 Export revocation and downstream artifacts

Before transfer, revocation blocks the job. During transfer/run, request cancellation, revoke credentials/keys where possible, stop subsequent steps, and reconcile what was already received or persisted. Revocation cannot truthfully promise that already exposed information was never seen. Record actual deletion receipts and unresolved retention limits.

Model weights/adapters/checkpoints/logs are sensitive derived data. Training data extraction has been demonstrated in language models [S20]; therefore treating only the uploaded CSV as confidential is insufficient. The source key/alias map remains local, but it is not the sole sensitive asset. Return and validate artifacts locally; never publish them to a model hub by default.

# 21. Security, safety, and operational privacy

## 21.1 Principal and permission model

Define capabilities rather than relying on role names alone: `read_project`, `edit_task`, `manage_sources`, `propose_candidate`, `request_compute`, `review_science`, `approve_experiment`, `review_measurement`, `manage_models`, `approve_model`, `review_export`, `approve_export`, and `administer_workspace`. The agent principal gets only narrowly scoped read/propose/request capabilities; it never inherits owner approval privileges.

Proposed roles are owner, researcher/formulator, scientific reviewer, lab operator, data steward, and viewer. Actual user assignments are unknown. In a single-user deployment the same human can hold multiple capabilities, but the audit must not misrepresent that as independent two-person review. Cloud/safety approval remains an explicit human action even for an owner.

Server authorization applies at every resolver/service, artifact endpoint, search result, Node refetch, run replay, and background job. PostgreSQL row-security policies can add defense in depth; table owners and bypass-capable roles need careful handling [S23]. Use a restricted runtime DB role, separate migration credentials, and tests proving cross-scope denial. RLS does not replace application checks or protect artifacts outside the database.

## 21.2 Loopback and team access

Binding to localhost alone is not an authentication strategy. Use authenticated sessions, explicit allowed hosts/origins, same-origin requests, secure session handling, CSRF protections appropriate to the transport, and rejection of cross-origin commands. Protect upload/download and event endpoints identically. Do not expose the model server or database port publicly by default.

A local one-time setup flow creates the owner credential/session without a hardcoded password. Secrets live outside source control. LAN/team access stays disabled until TLS, real identity management, roles, session expiry/revocation, and deployment checks are configured. No browser localStorage copy of credentials, full recipes, or checkpoints.

## 21.3 Data at rest and threat model

Protect the data root, DB volume, scratch, local model cache, and backups. Use OS/full-volume encryption as a prerequisite for the intended sensitive deployment and established encryption/key-management libraries for encrypted artifacts where implemented. Keys must not sit next to ciphertext in world-readable files. Record which controls are configured, tested, unavailable, or unknown.

Do not claim protection against an attacker already controlling the unlocked OS account or live process memory. A hash chain can make audit edits detectable under a defined key/anchor model, but is not magically tamper-proof against an administrator controlling all storage and keys. Audit access, export, approval, policy changes, model promotion, and sensitive downloads with minimal payload.

## 21.4 External research and content handling

Any outbound research query can disclose chemistry information. The egress broker must inspect/authorize queries containing proprietary formulations, structures, document excerpts, or product identifiers. Public-source lookup does not override local-first confidentiality. Cache permitted public responses with source/date/rights; offline use remains possible after import.

Sandbox document parsing, disable active content, sanitize displayed HTML/Markdown, and reject SSRF/local-file URL requests. Never allow a source document to tell the agent to upload the vault or change its tools. External service outages return explicit unavailable results; the assistant may use existing local evidence without pretending the fetch succeeded.

## 21.5 Scientific safety scope

The platform supports legitimate industrial research. New experimental protocols require a qualified reviewer and documented safety/equipment constraints. The system must identify when it lacks identity, hazard, exposure, or method information. Restriction databases can support screening but not definitive safety certification; EPA CompTox is an example evidence source with experimental and predicted information [S24].

Do not implement optimization workflows targeted at chemical weapons, illegal harmful chemical production, or bypassing safety controls. These limits are system policy, not tradeable reward penalties. Store permitted-scope and hazard-review decisions separately from performance ranking. Actual chemical procedures in the user's historical vault must not appear in public fixtures or CI logs.

## 21.6 Retention, revocation, and backups

Retention periods are unknown; supply configuration and explicit policy placeholders, not a made-up legal schedule. Test backup/restore of DB, artifacts, keys, approvals, model manifests, and schema versions. Backup encryption/key recovery must be verified before claiming recovery readiness. Restore tests must check source/derived references and not just whether PostgreSQL starts.

Deleting a source revokes retrieval and future training eligibility, invalidates caches, and identifies affected derived artifacts. Physical deletion and backup expiry are tracked separately. Never promise secure erasure of SSD/cloud backups beyond verified controls. Export reports should state whether raw sensitive content is included, and require approval when crossing a trust boundary.

# 22. UX, screens, and atomic component architecture

## 22.1 Navigation and interaction principles

Use persistent navigation for Projects, Materials & Products, Evidence, Lab, Models & Learning, and Settings. Jobs/approvals are accessible globally without crowding the task workspace. The default landing view emphasizes recent tasks and pending decisions, not a wall of unrelated KPI cards. Research chat is one task surface, not the entire application.

Within a task, use Overview, Research, Candidates, Experiments, Evidence, and Decisions. Keep the success contract and active blockers accessible. Advanced scientific configuration is progressively disclosed but not hidden from review. Every action states whether it saves a draft, proposes a change, queues computation, requests approval, or records a measurement.

## 22.2 Required screen families

Create the routes and stable IDs in `planning/design-map.json`: project/task home; project detail; task wizard/contract editor; task overview; research session; candidate editor; candidate comparison; reference-product detail; material detail; evidence viewer; import review; experiment-plan review; execution/sample capture; measurement-quality review; job/run detail; capability/compute settings; dataset builder; training-run detail; evaluation report; model registry; cloud-export review; workspace/access settings; and task closeout packet.

No Figma file was supplied or created in this work. `figma_node_id` is null and design status is logical-specification-only. Do not invent Figma links, claim pixel parity, or block functional work on a nonexistent design. Validate the design map before code; any later Figma design must map to these stable IDs or a reviewed migration.

## 22.3 Reusable components

Atoms include Button, IconButton, TextField, DecimalField, UnitSelect, Badge, EvidenceTypeLabel, StatusIndicator, Tooltip, Checkbox, and FocusRing. Molecules include QuantityInput, SourceCitation, MetricTargetEditor, ConstraintRow, IngredientLine, IdentityPicker, ApprovalSummary, ResourceBudget, and InlineFinding. Organisms include ContractEditor, FormulationEditor, EvidencePanel, CandidateDiff, MetricComparisonTable, ExperimentReview, MeasurementGrid, RunTimeline, DatasetSplitReview, and ExportPayloadReview.

Keep dimension/basis validation in domain services and mirror safe feedback in UI, not duplicated divergent rules. Evidence badges must be distinct from completion badges. Quantity controls show unit/basis alongside the value. A dash means unknown with an accessible reason, not numeric zero. Show uncertainty and conditions where a result is displayed, not only in a hidden modal.

## 22.4 Screen states and recoverability

Every data screen implements loading, empty, populated, partial, error/retry, forbidden, and unavailable-capability states. Editable screens add unsaved, saving, saved, conflict, and read-only revision states. Approval screens add stale, expired, revoked, and insufficient-permission states. Runs show queued, blocked, running, cancel requested, interrupted, failed, completed, and output unavailable.

Internet-offline operation must still work against local data/services. If the local API is down, never display 'saved offline' without a real durable save. Keep unsaved input in memory, warn before navigation, and offer an explicitly user-controlled local draft export when permitted. A later encrypted offline-draft store is optional; no browser database should silently become a second canonical source. Approvals and exports cannot be queued offline as though already authorized.

## 22.5 Responsive, accessible, and reviewable

Support desktop and smaller laptop layouts first; tablet/mobile layouts allow navigation, reading, and approvals with deliberate confirmations. Wide scientific tables can scroll horizontally with sticky identity/unit columns and a stacked detail mode. Do not shrink tables into illegibility or drop conditions on small screens.

Use keyboard navigation, visible focus, semantic headings/tables, labeled fields, screen-reader status messages, sufficient contrast, reduced-motion support, and non-color indicators. Light/dark themes share semantic tokens and component states. UI validation includes keyboard-only contract editing, source navigation, candidate diff acceptance, and export rejection. Brand colors remain an engineering default, not a scientific status vocabulary.

# 23. Performance, observability, and cost limits

## 23.1 Performance budgets are proposed engineering targets

Because hardware and dataset scale are unknown, benchmark before publishing performance claims. Proposed initial targets on a recorded reference machine are: ordinary local indexed record reads p95 under 500 ms excluding model/simulation time; mutation acknowledgment p95 under 1 second before asynchronous work; UI controls remaining responsive during a heavy job; and visible progress/heartbeat for long-running work. These are targets to test, not guaranteed user-machine throughput.

Record benchmark machine, dataset/fixture size, concurrency, cold/warm state, and measured results. Do not compare benchmarks run on different hardware as an improvement without qualification. Add larger synthetic fixture profiles and test keyset pagination, artifact streaming, search, import backpressure, and worker contention.

## 23.2 Observability

Use structured logs with correlation/run/task IDs and redacted payloads. Default metrics: API latency/errors, queue wait, resource admissions/denials, run durations/failures/timeouts, parser errors, invalid outputs, cache hit rates, approval waits, data-quality exclusions, and model evaluation outcomes. Do not log full prompts, formulas, spectra, or documents into a generic external monitoring service.

Maintain a private diagnostic bundle exporter with a preview and redaction. Observability is local by default. Telemetry transmission requires explicit configuration/consent and must pass egress policy. A failure report needs enough method/version metadata to debug without automatically including proprietary input.

## 23.3 Budget enforcement

Task budgets distinguish compute, cloud money, experimental spend, and model tokens. Unknown budget means no authorization to spend external money. Estimates are not actuals; retain both. Budget checks occur at reservation and execution, with actual reconciliation. Exceeding a cap blocks new work or requests approval; it does not silently downgrade scientific requirements.

Every CI job has an explicit timeout. Suggested defaults: static/schema checks 10 minutes, core unit/integration jobs 20 minutes, browser tests 20 minutes, and heavy optional jobs a separately approved cap. Cancel superseded PR runs where safe; use narrow permissions; do not put proprietary fixtures or model weights in shared/public CI caches. Nightly expensive training is disabled by default.

# 24. Build phases, gates, and safe parallelism

## 24.1 Phase sequence

**P00 — Baseline and dependency decisions.** Audit or initialize the authorized repository; validate the pack; map files; establish official-version/license records; run existing checks; prepare synthetic fixtures and CI timeouts. Gate: reproducible core bootstrap plan with no invented runtime claims.

**P01 — Contracts, persistence, and security foundation.** Implement domain schemas, migrations, IDs/Relay skeleton, scope authorization, artifact storage, events/idempotency, and decision/unknown registers. Gate: unauthorized access, cross-scope reference, stale revision, and duplicate-command tests pass.

**P02 — Tasks, materials, and UI foundation.** Implement task hierarchy, versioned success contracts, material/reference/formulation/process revisions, deterministic quantity/composition rules, and atomic UI. Gate: all three task modes exist; unknown purchased composition is preserved; revisions cannot be silently overwritten.

**P03 — Ingestion and evidence.** Implement quarantine, parsing, review, citations, rights, retrieval, task memory and source revocation. Gate: import-to-reviewed-evidence journey works with locators and no raw source becoming an accepted recipe automatically.

**P04 — Runs, local AI, and core tools.** Implement queue integration, capability/resource gates, sandbox/cancel/recovery, RDKit, local model adapter and structured proposals. Gate: real benign RDKit smoke test plus denial/failure/recovery tests; local assistant integration is tested or explicitly blocked without preventing manual workflow.

**P05 — Lab and pilot closeout.** Implement approvals, samples, measurements, comparison, contract evaluation, closeout, and three complete task journeys. Gate: first useful pilot demonstrated on synthetic fixtures, clearly distinguished from scientific validation; backup restore and local privacy gates pass.

**P06 — Optimization and property learning.** Implement dataset preparation/splits, BayBE adapter, baseline predictors, calibrated evaluation and pending-experiment handling. Gate: actual constrained recommendation, no dropped constraints, data leakage tests, and baseline reports.

**P07 — Targeted science adapters.** Implement tested QCEngine/xTB/Psi4 integration; add optional thermodynamics/materials/analytical adapters only where a reviewed task justifies them. Gate: reference calculation and failure tests plus explicit applicability/benchmark status.

**P08 — Local assistant fine-tuning.** Implement approved dataset builder, trainer adapter, real tiny smoke training, registry, held-out evaluation, promotion and rollback. Gate: actual checkpoint update/load/evaluation; no improvement claim without a passing independent report.

**P09 — Research RL and molecular design.** Implement bounded environment/reward tests, trainer integration, and optional small-molecule/retrosynthesis adapters. Gate: anti-reward-hacking suite, isolated evaluation, actual approved smoke execution where hardware permits.

**P10 — Protected cloud fallback.** Implement local-feasibility reports, payload transforms/review, exact approvals, provider-neutral broker, cancellation/deletion receipts, and one provider only after approval. Gate: no outbound proprietary bytes before all checks; synthetic live test required for actual provider availability.

**P11 — Release hardening.** Complete access/security review, recovery, migration tests, performance measurements, UI accessibility, user/admin/scientific runbooks, license inventory, and acceptance evidence. Gate: release matrix states precisely what is implemented, tested, blocked, scientifically supported, or deferred.

The workplan supplies granular tickets. Later optional science/provider tickets may remain blocked while core releases proceed; they remain visible roadmap obligations. Do not declare the complete platform done because P05 is usable.

## 24.2 Controller-owned changes

One controller owns migrations, shared schemas, stable IDs, authorization policy, route registry, cross-worker contracts, design-map changes, dependency locks, and release gates. A worker proposing shared changes submits a contract patch to the controller. Two agents must not independently change the same database migration sequence or independently invent the same entity.

## 24.3 Safe parallel work

After P01 shared contracts are frozen, materials/task services and atomic UI may proceed in separate owned directories. During P03, parsers and evidence UI may proceed from the same accepted DTOs. During P04, engine adapter tests and run UI may proceed after Run contracts stabilize. Later, property-model evaluation and approved physics adapters can proceed independently of assistant training.

Start with at most three concurrent implementation workers unless the actual environment supports more safely. This is a planning limit, not a claim that subagents are available. If no delegation tool exists, execute sequentially. Workers must report scope, commit/diff, tests, dependencies, and blockers; a controller integrates and runs the combined suite.

Do not parallelize schema-changing work with dependent UI/code generation until the contract patch lands. Do not parallelize multiple GPU-heavy tasks on an unmeasured machine. Do not let cloud integration bypass the privacy workstream to 'unblock training'.

## 24.4 Branch and review strategy

Use small dependency-aligned commits/PRs, not one uncontrolled rewrite. Protect existing user changes; never force-push or discard work. Each PR includes scope, relevant requirement/ticket IDs, migration impact, before/after behavior, acceptance evidence, disabled/blocked capabilities, security implications, and rollback approach.

Keep a single task ledger. A ticket marked complete by an agent is reconciled against actual diff/runtime/tests by the controller. Generated files are reproducible and checked for drift. Documentation-only completion is insufficient for implementation tickets.

# 25. Test strategy and concrete acceptance journeys

## 25.1 Required test tiers

Contract tests validate JSON/GraphQL schemas and generated types. Unit/property tests enforce units, composition, revisions, gates, state machines, and scoring. Integration tests use a real disposable PostgreSQL database and artifact directory, with migrations applied. Engine tests include real benign calculations separately from fixtures. Browser tests exercise actual backend routes. Security tests attempt cross-scope access and forbidden egress. Evaluation tests cover split/label/retrieval/model-tool leakage.

The test catalog in `planning/acceptance-tests.json` is the required behavior inventory. Add test implementation paths and real evidence as code is delivered. Test IDs are stable. New discovered failure cases extend the catalog; do not delete failing requirements to make CI green.

## 25.2 Pilot journey A — improve

Import a synthetic historical formula and baseline measurement; review both; create an improve task and frozen test contract; start a research session; propose/accept a revision; reject invalid mass totals; run structural/eligibility checks; draft/approve an experiment; record sample and synthetic measurements; quality-review; compare under the same method; close with a human-approved result; open a second session and verify persistent history. Change the contract and prove the original conclusion is not rewritten.

## 25.3 Pilot journey B — match

Create a purchased reference with unknown composition and supplier claims; attach a sample measurement; select functional matching; propose a synthetic alternative; show analytical matching as not measured; accept applicable results; close with functional scope only. Assert that no recipe is inferred, no structure-required engine is called with a fabricated molecule, and no exact-identity claim appears.

## 25.4 Pilot journey C — discover

Create a discover-formulation task with approved synthetic ingredient identities and constraints; use manual proposals first and the real optimizer after P06; retain competing hypotheses; perform a bounded recommendation request; approve a selected candidate for a synthetic experiment; record failure with cause; update the campaign only with valid measurements; choose a subsequent candidate; show novelty scope as internal-corpus-only unless external evidence exists.

## 25.5 Reliability and privacy journeys

Interrupt an upload and retry without duplicate artifacts. Kill a worker during a run and reconcile safely. Cancel a subprocess tree and verify resource release. Revoke a source while a session has cached retrieval and confirm no new exposure. Submit a malicious document asking to export recipes and confirm denial. Change an approved experiment revision and confirm stale approval. Attempt an export after its digest/recipient changes and confirm no outbound bytes. Exhaust local resources and confirm no automatic cloud transfer.

## 25.6 Learning journeys

Build a dataset containing duplicate revisions, instrument failures, supplier claims, and missing values; inspect exclusions and grouping. Inject a held-out answer into an indexed summary and prove the evaluation tool blocks it. Run a tiny actual fine-tune on synthetic examples, load the resulting artifact, run the baseline comparison, reject a worse model, promote a qualified test release under explicit fixture thresholds, and roll back. Fixture thresholds must be labeled non-scientific.

Run a bounded RL test policy that tries repeated cheap validity actions, unsupported confidence, unit manipulation, and always-abstain. Assert those strategies cannot pass the independent release suite. Keep physical experiments outside the live RL step function.

# 26. Commands, migrations, delivery, and operations

## 26.1 Implementation command interface

The repository must implement documented commands with equivalent cross-platform scripts where Make is unavailable: `make bootstrap`, `make dev`, `make migrate`, `make seed-demo`, `make lint`, `make typecheck`, `make contracts-check`, `make test-unit`, `make test-integration`, `make test-security`, `make test-e2e`, `make test-engines`, `make eval-smoke`, `make train-smoke`, `make backup-test`, and `make verify-core`.

`make verify-core` runs deterministic checks without requiring a GPU, paid API, real lab, or internet once dependencies are installed. `test-engines`, `train-smoke`, and live cloud tests state prerequisites and report unavailable capabilities explicitly. No command may print success when its checks were skipped. Bootstrap does not automatically download large models, accept licenses, or upload telemetry.

The package's own command is `python scripts/validate_pack.py` from the package root after installing `jsonschema` in an isolated environment. Its output is specification-validation evidence only. It has no network or application side effects.

## 26.2 Migration sequence and rollback

Create migrations in dependency order: principals/workspaces/projects; core task/contracts/revisions; artifacts/evidence/rights; events/idempotency/queue integration; materials/formulations; runs/approvals; lab/measurements; datasets/models/evaluations; exports/privacy. The implementation may combine initial empty-schema migrations but must preserve referential ordering and test populated upgrades.

Use expand/migrate/contract changes for populated installations. Backfill with resumable idempotent jobs and checkpoints. Never mutate accepted historical revisions in place merely to match a new schema; add a transformation record or compatible read adapter. Verify backup/restore before destructive changes. Application rollback must not assume destructive DB downgrade is safe; prefer compatible roll-forward migration and restore procedures.

## 26.3 Operational runbooks

Deliver installation/profile setup; owner/access management; import review; task/contract editing; experiment approval; measurement correction; engine installation and benchmark; model import/training/promotion/rollback; cloud export review; job cancellation/recovery; backup/restore; incident response; source revocation and derived-artifact handling; and dependency updates.

Every runbook states prerequisites, exact commands or UI path, expected output, failure symptoms, recovery, privacy concerns, and evidence location. Include how to run entirely without a local model. The application must remain useful for records/manual research when the model is unavailable.

# 27. Definition of done and release evidence

A software feature is done when its code and migrations exist; its permissions and error paths are enforced server-side; relevant tests ran; UI states are usable; contracts/types/design map agree; logs are redacted; documentation explains operation/recovery; and a reviewer can reproduce its evidence. A fixture-only implementation is not a live integration.

The first pilot release requires all P00–P05 gates, three end-to-end modes, deterministic verification, local persistence/restore, source provenance, human lab approvals, and honest capability labels. Real chemical usefulness requires actual authorized data and scientific review not present in this package. Training and cloud features remain unavailable until their later gates pass.

The full roadmap release matrix must list each engine, parser, local model/runtime, optimizer, training method, evaluation suite, and cloud adapter with version, platform, evidence status, limitations, and blocked input. 'All phases implemented' is not an acceptable final report without this matrix.

Required evidence package: baseline commit; final commit; dependency locks; migration results; test commands/results; screenshots for each required journey/state; engine reference-run manifests; model smoke/evaluation manifests where executed; security/egress checks; restore evidence; performance benchmark machine/results; known issues; unresolved inputs; and next unblocked ticket. Do not include proprietary payloads in a public PR evidence bundle.

# 28. Risks, contingencies, and stop conditions

**Poor historical data:** prioritize review/normalization and manual workflows; report coverage. Do not train until target-specific readiness passes.

**Unavailable scientists/lab:** deliver computational workflow but keep physical validation/closure claims blocked. Do not invent measurements to demonstrate improvement.

**Incompatible hardware:** keep core operational; use supported local profiles; record infeasibility. Cloud remains an approved exception, not default.

**Unsupported formulation constraint:** reject/reparameterize through review; do not drop the constraint in BayBE or generate an invalid recipe.

**Unknown material identity/parameters:** preserve records and hypotheses; block calculations requiring missing data. Never fabricate force-field or structure inputs.

**Reward/model exploitation:** stop promotion, retain baseline, inspect component rewards, add adversarial tests, and revise the training environment without touching the final evaluation answers.

**Privacy/export uncertainty:** block transfer, preserve local job preparation, and document the missing protection/approval. Token aliases do not resolve this risk by themselves.

**Upstream API/license drift:** pin tested versions, isolate adapters, read official docs, and record compatibility changes. Do not replace a maintained engine with a homemade solver because integration is inconvenient.

**Conflicting concurrent edits:** reject stale writes and show a diff. Never silently prefer the AI's revision or the most recent timestamp.

**Missing credentials or budget:** complete provider-neutral/synthetic tests; mark live capability blocked; continue other unblocked tickets. Do not spend money or create external infrastructure without approval.

# 29. Specification artifacts and change process

`contracts/domain.schema.json` contains initial strict JSON interchange definitions. These are bounded first-release DTOs, not the entire eventual SQL/GraphQL schema. Fields and invariants described in the handoff but not represented in an interchange fixture still require implementation. Extend schemas through versioned migrations before using new fields. Never remove required constraints just to accept malformed examples.

`planning/design-map.json` is the canonical logical UI map. `planning/workplan.json` is the implementation DAG. `planning/acceptance-tests.json` is the behavioral test inventory. `planning/integrations.json` records reusable engines, phases, prerequisites, limits, and official sources. `planning/sources.json` records reference provenance and verification caveats. Fixtures use synthetic labels, never executable production recipes.

Changes require a version increment where appropriate, a changelog entry, updated schema/tests/mappings, and a passing package validation. During implementation, add actual code/test/Figma links only when they exist. Keep unknowns explicit rather than filling them with plausible guesses. The implementation agent should preserve this handoff in place and update execution state, not create a competing handoff on every pass.

# 30. Official sources and verification notes

The sources below support the identified upstream capabilities and cautionary facts. The architecture, requirement IDs, workflows, gates, and implementation priorities are proposed system design, not claims that an upstream library implements them for us. Sources were checked during preparation; some documentation routes display development or older example versions. Pin and retest actual installed versions at implementation time. No complete environment compatibility or commercial license audit has been executed here.

**[S01] RDKit: Getting Started in Python.** https://www.rdkit.org/docs/GettingStartedInPython.html  
Parsing, sanitization, and molecular operations; not proof of synthesis, safety, or application performance.

**[S02] RDKit overview.** https://www.rdkit.org/docs/Overview.html  
Core cheminformatics capabilities; verify installed build and license.

**[S03] Relay GraphQL server specification.** https://relay.dev/docs/guides/graphql-server-specification/  
Canonical object IDs, Node refetching and cursor connections.

**[S04] Strawberry Relay guide.** https://strawberry.rocks/docs/guides/relay  
Backend Relay integration; use version-specific API documentation.

**[S05] Procrastinate documentation.** https://procrastinate.readthedocs.io/en/stable/  
PostgreSQL-backed queue, retries and locks; resource policy remains application responsibility.

**[S06] QCEngine program executor documentation.** https://molssi.github.io/QCEngine/dev/  
The accessible route contains older/development examples. Capability reference only; pin and verify current packages/harnesses before implementation. Alternative QCArchive documentation route could not be fetched during preparation.

**[S07] xTB user guide.** https://xtb-docs.readthedocs.io/en/latest/  
Semiempirical quantum methods and interfaces. Some page news is old; do not infer latest release from it.

**[S08] Psi4 official site.** https://psicode.org/  
Quantum chemistry capabilities and license overview; benchmark selected method and build.

**[S09] BayBE constraints.** https://emdgroup.github.io/baybe/latest/components/constraints.html  
Version-sensitive constraint support and limitations. latest is a development documentation route; verify chosen stable version before coding.

**[S10] Chemprop prediction, uncertainty and calibration.** https://chemprop.readthedocs.io/en/main/tutorial/cli/predict.html  
Prediction and uncertainty tooling; proprietary endpoint models require relevant data and validation.

**[S11] REINVENT 4 official repository.** https://github.com/MolecularAI/REINVENT4  
Small-molecule design/optimization tool; code, pretrained models and data require separate review.

**[S12] AiZynthFinder documentation.** https://molecularai.github.io/aizynthfinder/  
Retrosynthetic planning, not experimental synthesis verification.

**[S13] Hugging Face PEFT LoRA documentation.** https://huggingface.co/docs/peft/main/en/conceptual_guides/lora  
Parameter-efficient adaptation; main may differ from a released package.

**[S14] Hugging Face TRL GRPO trainer.** https://huggingface.co/docs/trl/en/grpo_trainer  
Existing trainer/reward infrastructure; application environment and evaluation remain custom.

**[S15] NIST SP 800-188.** https://csrc.nist.gov/pubs/sp/800/188/final  
De-identification risk/governance reference. Its original scope is datasets/privacy, not a guarantee of chemical trade-secret protection.

**[S16] eLabFTW API documentation.** https://doc.elabftw.net/docs/usage/api/  
Existing ELN API integration; no live user ELN inspected.

**[S17] AiiDA documentation.** https://aiida.readthedocs.io/projects/aiida-core/en/stable/  
Scientific workflow/provenance infrastructure; optional, not an additional default scheduler.

**[S18] thermo documentation.** https://thermo.readthedocs.io/  
Thermodynamic/phase-equilibrium models; supported parameters and validity matter.

**[S19] LAMMPS overview.** https://docs.lammps.org/Intro_overview.html  
Molecular/materials dynamics engine; correct parameterization required.

**[S20] Carlini et al.: Extracting Training Data from Large Language Models.** https://arxiv.org/abs/2012.07805  
Primary research demonstrating extraction risk; not a claim every checkpoint necessarily leaks every record.

**[S21] llama.cpp official repository.** https://github.com/ggml-org/llama.cpp  
Local inference runtime candidate; actual model/tool/adapter compatibility requires testing.

**[S22] Google Cloud Confidential VM overview.** https://docs.cloud.google.com/confidential-computing/confidential-vm/docs/confidential-vm-overview  
Example of confidential-computing capabilities, not a selected provider or approved architecture.

**[S23] PostgreSQL row security.** https://www.postgresql.org/docs/current/ddl-rowsecurity.html  
RLS behavior and role caveats; pin documentation to deployed major version.

**[S24] EPA CompTox resource hub.** https://www.epa.gov/comptox-tools/comptox-chemicals-dashboard-resource-hub  
Chemical evidence source with measured/predicted information; not safety certification.

**[S25] Open Reaction Database documentation.** https://docs.open-reaction-database.org/en/latest/  
Reaction data/schema resource, not a universal formulation database.

