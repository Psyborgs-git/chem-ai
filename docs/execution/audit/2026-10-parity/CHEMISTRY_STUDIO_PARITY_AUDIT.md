# Chemistry Studio — source audit and implementation continuation

**Repository:** `Psyborgs-git/chem-ai`  
**Audited pushed branch:** `main`  
**Audited commit:** `11fc69350e603898b7cb26c1989e5da09baf710a`  
**Most recent merged change inspected:** PR #22 / CS-1201  
**Document version:** 1.0 — read-only audit; no implementation changes made.

## 1. Verdict and limits of this review

The implementation has recognizable foundations for the approved standalone, local-first Chemistry Studio. However, the inspected code does **not** justify declaring the complete plan or the intended operator experience finished. There are concrete contract/evaluation defects and missing user-facing workflows, not just missing hardware, datasets, and scientific thresholds.

This is a **source-level, targeted parity review**. The reviewer read the provided screenshots, selected current repository implementation files, the original handoff, PR metadata, and the current CI workflow/run metadata. The full authenticated Devin conversation and its uncommitted workspace were not accessible. The application and its tests were not rerun by this reviewer: a container clone attempt failed because GitHub DNS resolution was unavailable. Findings identified as static are not represented as runtime reproductions. The executing agent must reproduce them at its actual HEAD and preserve any later fixes.

GitHub reports successful CI for the audited main commit, run `37523007726`. The inspected workflow does not run the Playwright suite or a production frontend build. The PR's claimed local test counts are author-reported evidence, not independent runtime verification by this audit. [S17, S19]

No real formulations, commercial product dataset, production model, hardware installation, or scientist validation was inspected. This report neither certifies scientific performance nor establishes a data leak. Simulation, training, full authorization, and external-export implementations were not exhaustively audited.

## 2. Authoritative scope and preservation rules

The original handoff remains canonical. This document is a corrective continuation, not a replacement product plan. Add a linked continuation section to the existing execution records; do not restart the original 52-ticket implementation.

Preserve the user's locked decisions:

- Standalone chemistry application; improve, match-reference, and discover modes; project/task/session hierarchy; versioned success contracts and scoped evidence.
- Historical successful and failed formulations, recipes, and product documents; unknown purchased-product recipes remain unknown.
- Native laboratory records; human experiment approval, manual execution and measurement upload. U16 / CS-0506 live eLabFTW integration stays intentionally deferred and nonblocking.
- Workflow first, distinct retrieval/property learning/SFT/RL capabilities, independent evaluation, no automatic promotion from a rising reward.
- Local-first execution, hardware-aware capabilities, and cloud disabled without the approved local-infeasibility/privacy/payload/budget checks. Do not buy hardware, download an unapproved model, provision a provider, or upload proprietary data to unblock this work.
- Preserve correct schema identities, immutable history, approvals, artifact vault, queue, worker isolation, and permission checks. Reuse application services and the existing Relay environment.

Preserve the useful parts of PR #22: ModelsPanel mounting, typed query errors, the stale-list corrections, and contract row-locking. Removing broken links avoided dead navigation, but it did not deliver the Materials & Products and Settings capabilities required by the original plan. Complete those capabilities; do not restore dead links or repeat fixes already landed. [S01, S02, S16]

Later approved design artifacts may exist outside the original package. Discover any actual canonical design map/Figma references available in the agent workspace. Do not invent links, claim pixel parity, or use this audit to authorize an unrelated redesign.

## 3. Executive parity map

| Area | What the inspected implementation supports | Remaining gap / evidence limit |
|---|---|---|
| Three task modes | Mode selection and mode-specific input fields exist. [S03] | Baseline/reference inputs are raw IDs; normal registry selection and editing flows are incomplete. |
| Task/session organization | Task workspace, sessions, context manifests, questions and summaries exist. [S10, S13] | The mounted research surface is a viewer, not a complete conversational input/execution flow. |
| Immutable research records | Task contract draft/freeze and closure services exist. [S05] | UI payload does not match evaluator input; current editor does not load saved contracts. |
| Native laboratory loop | Execution, sample, measurement review/applicability/amendment services exist. [S08] | Evaluation evidence is not selected by the exact candidate/contract; correction flow needs an end-to-end regression. |
| Scientific conclusions | Per-metric evaluator, hard gates, closeout reports exist. [S07] | Unknown composition can pass an absence gate; favorable readings can satisfy `single`; hard-gate evidence is incompletely tracked. |
| Learning and engines | Repository documents fixture/mechanism status and live-input blocks. [S20] | Scientific utility is not established; this review does not verify all engine/training integrations. |
| Operator experience | Real routes, panels, form mutations and run monitoring exist. [S02, S14] | Login/project creation, meaningful candidate editing, and core navigation are incomplete. |
| Release confidence | Latest main CI run is successful. | Browser journeys and production frontend build are absent from the inspected CI workflow. [S17] |

## 4. Corrective work packages

The IDs below are new continuation IDs, not claims that existing tickets were implemented incorrectly in their entirety. Map them into the existing execution register without overwriting original acceptance evidence. P0 blocks trusting the relevant real-data conclusions; P1 blocks calling the operator-facing pilot complete.

### PAR-01 — Canonical success-contract schema and editable round trip

**Priority:** P0. **Depends on:** baseline reconciliation only.  
**Observed files:** S04, S05, S06, S07. **Original requirements:** handoff §§5–8, 11.1, 12.3, 22.

**Static finding.** `ContractEditor` saves `payload.requiredMetrics`, with nested `target: {value, unit}`. `contract_draft_create` forwards the supplied JSON unchanged; `draft_contract` stores it. The evaluator enumerates `contract.payload.get("metrics", [])`. The editor also initializes a blank viscosity target on mount rather than loading the saved contract. Its primary controls do not provide the complete method/conditions/aggregation/replication contract or a freeze/history workflow.

**Implementation requirements.**

1. Establish one versioned contract DTO/schema shared by domain validation, GraphQL payload handling, the editor, fixtures and evaluation. Reuse the intended contract in the original pack; do not create a second incompatible vocabulary merely to patch this symptom.
2. Validate incoming drafts and freeze requests server-side. A draft can preserve explicit unknown fields. A missing metric/condition must not be converted into a scientifically meaningful default. Freeze/activation/next-action gates should require only what that action needs, as the original plan states.
3. Hydrate the current draft or frozen revision; display the revision identity, status, unit/basis, and editable or read-only state. Support human-readable metric name, operator/tolerance, target, method/version, conditions, required evidence and declared aggregation/replication where applicable.
4. Implement save, reload/resume, freeze/review, history, and conflict handling. Mark all edits dirty; prevent double-submission; retain unsaved input after a failed save. Do not lose changes on tab/route navigation silently.
5. Inspect already-persisted `requiredMetrics` payloads. Add a reviewed migration or explicit legacy read/repair path. Never rewrite signed or frozen history in place; ambiguous payloads require review or a successor revision. Preserve content hashes and old evidence packets.
6. Keep the row-locking introduced by PR #22. Distinguish actual transient database failures from validation errors; do not label every failed write successful or automatically retry ambiguous side effects.

**Required regression:** create a contract through the actual UI, save, reload, freeze via the UI, evaluate the same revision, and assert the exact metric/operator/unit/target reaches the evaluator. Do not seed a different contract JSON through an API helper to substitute for the action under test. Assert incompatible/unknown draft fields cannot silently become an assessable success contract.

### PAR-02 — Evaluation binds exact candidates, contracts and applicable evidence

**Priority:** P0. **Depends on:** PAR-01 contract identity.  
**Observed files:** S07, S08. **Original requirements:** §§6, 7, 11, 12.3, 14.

**Static finding.** `_task_measurements` selects accepted/applicable records by workspace, metric name and task association. It does not constrain them to the candidate revision named in the packet or the current contract revision/evaluation cycle. `_bound_candidate` separately chooses an accepted candidate by highest revision number. The evaluator discards method/conditions when passing rows to `assess_metric`. Consequently, unrelated candidate results can be pooled and attributed to a separately chosen candidate.

**Implementation requirements.**

1. Introduce or reuse an explicit evaluation request/record containing task, selected candidate revision, contract revision, evaluation cycle, evaluator version and evidence selection manifest. These must be authoritative IDs, not loose JSON names.
2. Resolve the experiment plan, actual execution, batch/sample, formulation/process revision and measurement lineage. Evidence must identify what was actually tested. Historical imports without sufficient linkage stay research evidence but cannot substantiate a specific candidate by assumption.
3. Check method/version, units, basis, substrate, preparation/application/test conditions, evidence class, quality review, and required replication before comparison. Record an actionable exclusion reason for each otherwise relevant result that is not applicable.
4. Allow legitimate reuse of historical evidence only through an explicit reviewed applicability mapping to the intended candidate/contract; do not blindly filter all old evidence out or blindly accept it into a new contract.
5. Report each candidate separately. Do not choose the successful candidate by revision number. Where comparisons require multiple candidates, represent them explicitly rather than synthesizing a single winner from their best metrics.
6. Bind closeout and approval to the exact report and evidence manifest the reviewer saw. A contract/candidate/evidence change invalidates the corresponding pending approval. Historical signed packets remain immutable.
7. Validate supplied baseline/reference IDs as authorized existing entities before using them for calculations. Blank draft inputs can remain unresolved; strings such as `baseline-rev-1` must not count as a real baseline.

**Required regression:** candidate A passes metric X and fails Y; candidate B fails X and passes Y. Neither may become supported-success through pooled observations. A measurement for the wrong method/substrate/contract must not satisfy a target solely because its metric name matches. Accepting a new candidate must not relabel an old evaluation packet.

### PAR-03 — Unknown hard gates fail safely; capture every supporting dependency

**Priority:** P0. **Depends on:** PAR-02 binding.  
**Observed file:** S07. **Original requirements:** §§12.1–12.3, 14, 17.

**Static finding.** The `ingredient_absent` branch initializes `present=False` and returns `pass` when there is no bound candidate, no formulation, or no usable ingredient list. Separately, report-level `evidenceIds` are collected only from ordinary metrics, even though metric-based hard gates can have their own evidence. Reassessment reads the packet list and checks missing/superseded/rejected measurements, not all applicability/dependency changes.

**Implementation requirements.**

1. An absence check requires a valid target identity, an applicable candidate representation, and sufficient reviewed composition coverage for the precise claim. Unknown or missing composition yields `not_evaluated`/insufficient evidence, not `pass`. Distinguish declared-ingredient absence from analytically established absence; do not upgrade a recipe check into a toxicology/compliance certificate.
2. Cover missing candidates, invalid entity links, empty/partial formulations, reference products with unknown recipes, ingredient aliases and unresolved supplier identities. Continue to show these candidates for research with the relevant block.
3. Include hard-gate evidence and dependencies in the immutable evaluation/closeout manifest: measurement versions, applicability decisions, material identities, composition coverage, methods, contract and candidate versions, and relevant source approvals.
4. Changes/revocation in any supporting dependency trigger reassessment of current conclusions and invalidate pending approvals. Preserve the historical packet unchanged. A change in `applicable` must be considered even when the measurement's integrity status remains accepted.
5. Guard the close command server-side; hiding a success button is insufficient. Do not introduce a blanket safety override.

**Required regression:** no composition never passes the absence gate; known excluded ingredient fails; supported absence passes only its explicitly bounded claim. A gate-only measurement amendment/revocation or applicability withdrawal causes reassessment even when every ordinary performance metric remains unchanged.

### PAR-04 — No favorable-reading selection; verify corrected measurement lineage

**Priority:** P0. **Depends on:** PAR-02. **Shared ownership:** same controller as PAR-03.  
**Observed files:** S07, S08. **Original requirements:** §§6.3, 12.3, 14.2, 17.

**Static finding.** Missing aggregation defaults to `fixture-single-value`. Both it and `single` use `any(compare(...))`, allowing one passing reading to outweigh conflicting accepted readings. `amend` writes a `MeasurementAmendment` and supersedes the original Measurement; the inspected evaluator reads accepted Measurement rows only. The correction path therefore needs tracing through any remaining hooks before its full behavior is asserted.

**Implementation requirements.**

1. For live evaluations require an explicit scientifically reviewed aggregation rule. An unspecified rule is unresolved, not permission to choose the best value.
2. For a single-observation rule, require one explicitly designated applicable observation/independent unit. Multiple conflicting readings must not be silently reduced with `any`. Approved policies for mean/min/max or other aggregation are explicit and versioned; this audit does not choose a scientific threshold or statistical rule for the user.
3. Distinguish technical repeats, timepoints, samples and independently prepared batches. Do not overweight the batch with more instrument readings or count aliases/copies as independent preparations.
4. Trace amendments through service, DB hooks, query, UI and dataset construction. First add a failing integration test if there is a gap. A correction must yield a reviewable immutable successor/effective version whose reviewed value is used exactly once; never both old and corrected values, and never the old value after supersession.
5. Maintain raw integrity acceptance separately from versioned contract applicability. Preserve correction reason, source, author and approval history. Invalidate affected evaluation and training lineage when evidence changes.
6. Verify outcome labels cannot make an unmeasured/unsupported experiment into training ground truth. Where a reviewer records a supported failure beyond the automatic evaluator, require the appropriate evidence and rationale; otherwise preserve it as inconclusive/stopped or an explicitly unverified report.

**Required regressions:** two conflicting readings cannot pass `single` merely because one passes; unspecified live aggregation is inconclusive; repeated readings do not inflate independent batches; a reviewed correction changes the effective result and flags an old signed packet without rewriting it. Any existing correct amendment hook must be reused, not duplicated.

### PAR-05 — Truthful data provenance versus scientific validation readiness

**Priority:** P0 before real-data conclusions. **Depends on:** PAR-02–04.  
**Observed files:** S07, S15, S20. **Original requirements:** §§9, 12.1, 17–20.

**Static finding.** The task evaluator/closeout packet hardcodes `fixtureOnly=True`; the UI always displays a fixture-only badge. These are honest for the current synthetic demonstrations but are not a complete live-data provenance model. Clearing that constant alone would be equally wrong.

Implement explicit provenance for synthetic fixtures, historical reports, reviewed laboratory observations, predictions, mixed evidence, and unknown sources. Keep evidence origin separate from engine applicability, method validation and independent scientific validation. A real upload does not establish a validated model or automatically fulfill U14. Prevent fixture data entering live training/acceptance by accident; preserve existing synthetic tests as synthetic. Unknown rights continue to block training/export according to policy.

**Required regression:** adding a real-origin record does not relabel fixture history or set scientific validation to true. Mixed evidence stays visibly mixed and policy-controlled. Readiness lists expose the actual missing scientific input without presenting it as an engineering success.

### PAR-06 — Fresh-operator entry and ordinary account/project workflow

**Priority:** P1. **Can begin independently after baseline/contract ownership is stable.**  
**Observed files:** S02, S03, S06, S20; operation-doc search shows developer-console login instructions.

The mounted application provides setup/signed-out status messages rather than a normal sign-in surface. ProjectsPage lists projects without a creation control. Complete usable loopback sign-in/logout/session-expiry recovery and project create/select/edit flows using existing auth and project services. Keep secure owner bootstrap separate from public sign-up: either a secure local first-run flow or an explicit administrative bootstrap followed by normal UI login. Do not introduce cloud identity, public registration or LAN deployment before U07 is resolved.

Do not store passwords/session secrets in browser persistence, URLs or logs. Keep authorization server-side. Invalidate identity-scoped Relay state on sign-out/identity changes. Provide concrete setup help and errors; normal work must not require DevTools fetch calls or hand-written GraphQL.

**Required regression:** from a fresh test installation, after the explicitly supported owner bootstrap, use the UI to sign in, create a project, create tasks in each mode, sign out and sign back in. Domain actions being tested cannot be pre-created by API helpers.

### PAR-07 — Materials, products, formulations and reference matching are real workflows

**Priority:** P1. **Depends on:** PAR-01 and existing material/identity contracts.  
**Observed files:** S02, S03, S09. **Original requirements:** §§5–6, 11.2–11.4, 22.

The candidate UI creates a kind/hypothesis draft and displays JSON. Task creation asks for baseline/reference UUIDs. Required Materials & Products and Settings links were removed because their pages did not exist. Restore capability by building real surfaces, not by adding labels back.

1. Reuse existing material/product/formulation/reference services, registered mutations and reusable atoms/molecules. Discover actual code before extending it.
2. Provide authorized searchable identity, supplier/grade, formulation-family/revision, and reference-product pickers; retain technical IDs in details rather than requiring them as normal user input.
3. Provide a structured formulation editor with authoritative decimal quantities, units, as-supplied/active basis, composition constraints, process version, parent revision and provenance. Never normalize percentages or mass/volume silently.
4. Provide candidate draft/edit/diff/propose/review/accept/reject flows. Each accepted change creates the appropriate immutable revision. Distinguish research acceptance from permission for physical execution.
5. Support reference documentation and analytical observations without inventing a recipe. Functional, analytical, and combined match objectives remain distinct.
6. Complete task-to-approved experiment-to-result navigation using native Lab records. Preserve manual approval/execution and unknown equipment/method gates.
7. Restore Materials & Products navigation only when real views exist. Build the required local workspace/capability/settings surface using existing backend controls; unavailable team/provider/instrument capabilities remain explicitly disabled with reasons.

**Required regression:** a user imports/reviews or creates an allowed synthetic baseline, selects it by name, proposes a structured successor, reviews an ingredient/process diff, and links the exact accepted revision to a manual experiment. A purchased-product reference can be selected with composition unknown. No normal step requires a UUID copied from SQL.

### PAR-08 — Real research composer and recoverable streams

**Priority:** P1. **Depends on:** stable session/message/action contracts; integrate candidate actions after PAR-07.  
**Observed files:** S10–S12, S14. **Original requirements:** §§8.4, 10, 11.1, 13, 22.4.

The mounted ResearchPanel starts/ends sessions and records questions; SessionStream displays messages but does not provide a composer or invoke a model turn. This is a UI integration gap, not proof that the underlying inference worker is missing.

Wire a real task/session composer into the existing authorized local inference/tool gateway. Persist the user message and requested turn transactionally; record durable messages, structured tool proposals/results and citations. Use budgets, idempotency, cancellation and execution-time permission checks. The assistant cannot approve experiments/measurements/exports/model releases or silently alter a frozen contract. Accept/reject actions call the same versioned services as the UI. Render source links, concise observable rationale and tool state; do not require hidden reasoning traces.

Show installed/model-unavailable/restricted states honestly and preserve manual work when a model is unavailable. Do not download an arbitrary base model or use an external API as a hidden fallback.

Stream recovery also needs attention: SessionStream fetches one initial snapshot and on snapshot failure only sets `live=false`; it does not retry. Its onOpen callback changes the badge without reconciling a snapshot, despite the stream module's comment. Implement real retry/error/expired/forbidden states, snapshot+cursor recovery after retention gaps, message deduplication/order, and revocation-aware clearing. Preserve the working RunsPanel onOpen refetch behavior.

**Required regressions:** send a message through the UI to a controlled synthetic test provider, observe the persisted assistant/tool response, reconnect/reload without duplication, start another session retaining task context, cancel an in-flight turn, recover an initial snapshot failure, and revoke source access. An unavailable real model gives a truthful actionable state, not generated placeholder research.

### PAR-09 — Task navigation, recoverability and Relay consistency

**Priority:** P1. **Depends on:** completed core workflow surfaces.  
**Observed files:** S02, S13, S14. **Original requirements:** §22 and original design map.

Replace the flat thirteen-section task treatment with the approved primary task organization (Overview, Research, Candidates, Experiments, Evidence, Decisions), retaining advanced learning/analysis/run capabilities through progressive disclosure and clear links. Map existing panels rather than deleting them. Keep objective, selected contract, evidence gaps and next authorized action visible. Provide stable route/query state so refresh/back/deep links preserve context. Add relevant recent tasks/pending decisions rather than a decorative dashboard.

Use documented Relay fragment/refetch/pagination patterns and canonical Node identities. Preserve current working cache corrections; no second server-state cache. Complete pageInfo-driven pagination, mutation updates and error handling in affected lists. Discover actual schema support before changing hooks. Each editable screen needs honest dirty/saving/conflict/read-only/error/retry states. A local API outage must not produce a false saved-offline claim.

**Required regressions:** deep links/back/refresh, more than one page of candidates/evidence, source-revocation refresh, a conflicting contract edit, API outage during save, small-laptop layout and keyboard-only completion. No new visual redesign or invented Figma reference is authorized.

### PAR-10 — Acceptance coverage, bounded CI and evidence-based closeout

**Priority:** P1 release gate; start CI scaffolding early, finish after dependent fixes.  
**Observed files:** S16–S19. **Original requirements:** §§25–27 and original acceptance register.

The current regression test asserts Materials & Products and Settings are absent, and API-seeds the project/task/contract for UI tests. Those tests can pass while required workflows are missing and the real contract editor sends a different schema. Preserve useful isolated tests but do not use them as end-to-end proof.

Add bounded CI jobs for the real production frontend build and Playwright journeys against a disposable database. Use synthetic fixtures only; isolate auth/workspaces per suite, avoid order-dependent owner setup and shared mutable datasets. Retain least privilege, concurrency cancellation, explicit per-job/process timeouts, and safe artifact collection. Optional engine/model jobs may be explicitly blocked; report unavailable checks separately, never as passing scientific validation.

Add three browser-first journeys:

- **Improve:** UI project, accepted baseline selection, real contract editing/freezing, candidate revision, approved manual plan, recorded/reviewed measurement, comparison/closeout.
- **Match:** reference with unknown recipe, scoped functional/analytical targets, evidence review and candidate comparison; no claim of recovered composition from functional similarity.
- **Discover:** task target definition, bounded research/proposal, eligible candidate selection and manual experimental feedback; missing method/model remains visibly unresolved.

Helpers may bootstrap accounts or attach known fixture bytes. They must not perform the very UI action the test claims to verify. Add adversarial evaluation cases from PAR-01–05; report nonassessable/inconclusive states as expected, not coerced successes.

## 5. Execution ownership, sequencing and rollback

First inspect the actual repository HEAD, dirty worktree, instructions, current PRs and prior tests. Reconcile findings against newer/uncommitted work before editing. The audit commit is a comparison baseline, not an instruction to reset to it.

The controller exclusively owns shared contract DTOs, schema/GraphQL generation, database migrations, evaluation/measurement lineage policy, dependency locks and CI integration. PAR-02–05 modify overlapping scientific logic and must not be assigned to independent agents editing the same files. Suggested sequence:

1. Baseline and failing regression tests; confirm privacy boundary; scaffold missing CI without weakening current tests.
2. PAR-01 canonical contract and reviewed legacy handling.
3. PAR-02 candidate/evidence binding, then PAR-03 hard gates and PAR-04 aggregation/corrections.
4. PAR-05 provenance/readiness; do not turn synthetic status into validated science.
5. PAR-06 entry workflow and PAR-07 registries; these can be separate workers only across already-stable service/schema boundaries.
6. PAR-08 composer/recovery; PAR-09 navigation integration; full PAR-10 acceptance and release evidence.

New schemas should be additive where possible. Before a migration, test against a disposable copy containing old draft/frozen contracts, signed packets, amendments and unknown references. Never resolve missing provenance by fabricating it. Back up and rehearse restore. Keep the old serving model and rollback pointer until a separately approved promotion; this continuation does not authorize model replacement.

## 6. What remains unknown, deferred or not independently verified

The visible Devin screenshot lists U02 data details, U03 exact pilot targets, U04 people/reviewer assignments, U05 available lab methods, U06 capacity/cost, U07 deployment topology, U08 hardware, U09 budget, U10 dates, U11 provider, U12 data rights, U13 base model, U14 scientific thresholds, U15 retention/keys. Preserve their exact current register meanings. U01 is reported resolved greenfield; U16 remains deferred ELN. Do not mark these inputs resolved merely because deterministic code is implemented.

These missing inputs may block real research acceptance, production deployment, or external execution. They do **not** block repairing an inconsistent payload, making absence gates fail safely, binding evidence, completing ordinary UI actions, or adding synthetic regression coverage. No invented user count, cloud account, budget, lab threshold or model choice is supplied by this audit.

The repo metadata currently reports **public visibility**. This is a deployment/privacy fact, not evidence of a leak. Check tracked files, artifacts, logs, fixture data and secret handling before real-data onboarding. Keep sensitive data in the private vault and approved storage, not Git/CI screenshots/caches. Do not change visibility or erase history without explicit permission.

## 7. Verification and required final report

Commands already present in the inspected repository include:

```text
make lint
make typecheck
make contracts-check
make test-unit
make test-integration
make test-security
make test-e2e
make test-engines
make backup-test
pnpm --filter studio-web build
```

Discover environment/setup prerequisites before running these. Core/API tests, UI tests, engine smoke tests and scientific validation are different evidence levels. `make verify-core` alone covers lint/contracts/unit in the inspected Makefile, not the entire release. Do not silently skip tests for missing dependencies and report success.

For every PAR item, return: requirement and original handoff anchor; static finding reproduced or disproved; exact changed files; migration/compatibility treatment; test names and commands; actual pass/fail/skip/blocked outcomes; UI screenshots or traces for affected journeys; and residual unknowns. Include base/HEAD/branch/PR state and the exact next blocked decision.

Use clear coverage states: implemented + tested, implemented but untested, missing, blocked by external input, intentionally deferred. Do not reduce this to a percentage or “all phases done.” No merge, deployment, public release, paid cloud job, repository-visibility change or proprietary upload is authorized by this document.

## 8. Source index

References below are pinned to the audited commit. They support source observations, not claims of runtime verification. Some large files were read in the relevant ranges rather than audited exhaustively.

- [S01] [Original implementation handoff](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/docs/chemistry-studio/CHEMISTRY_STUDIO_HANDOFF.md) — `docs/chemistry-studio/CHEMISTRY_STUDIO_HANDOFF.md`.
- [S02] [Application routes, setup state, project list](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/apps/studio-web/src/routes/AppRoutes.tsx) — `apps/studio-web/src/routes/AppRoutes.tsx`.
- [S03] [Task creation and mode input fields](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/apps/studio-web/src/features/tasks/TaskCreateForm.tsx) — `apps/studio-web/src/features/tasks/TaskCreateForm.tsx`.
- [S04] [Success-contract editor](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/apps/studio-web/src/features/tasks/ContractEditor.tsx) — `apps/studio-web/src/features/tasks/ContractEditor.tsx`.
- [S05] [Task service: drafting, freezing, closure](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/services/studio-api/src/studio/domain/tasks/service.py) — `services/studio-api/src/studio/domain/tasks/service.py`.
- [S06] [GraphQL contract mutation and read paths](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/services/studio-api/src/studio/api/graphql/schema.py) — `services/studio-api/src/studio/api/graphql/schema.py`.
- [S07] [Task metric evaluation, candidate selection, closeout, hard gates](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/services/studio-api/src/studio/domain/tasks/evaluation.py) — `services/studio-api/src/studio/domain/tasks/evaluation.py`.
- [S08] [Measurements, applicability, amendment service](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/services/studio-api/src/studio/domain/lab/measurements.py) — `services/studio-api/src/studio/domain/lab/measurements.py`.
- [S09] [Candidate proposal and JSON comparison surface](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/apps/studio-web/src/features/candidates/CandidatePanel.tsx) — `apps/studio-web/src/features/candidates/CandidatePanel.tsx`.
- [S10] [Research sessions and open questions surface](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/apps/studio-web/src/features/research/ResearchPanel.tsx) — `apps/studio-web/src/features/research/ResearchPanel.tsx`.
- [S11] [Session message snapshot and stream consumer](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/apps/studio-web/src/features/research/SessionStream.tsx) — `apps/studio-web/src/features/research/SessionStream.tsx`.
- [S12] [SSE client](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/apps/studio-web/src/features/research/stream.ts) — `apps/studio-web/src/features/research/stream.ts`.
- [S13] [Task workspace navigation](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/apps/studio-web/src/features/tasks/TaskWorkspace.tsx) — `apps/studio-web/src/features/tasks/TaskWorkspace.tsx`.
- [S14] [Run monitoring and cancellation UI](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/apps/studio-web/src/features/runs/RunsPanel.tsx) — `apps/studio-web/src/features/runs/RunsPanel.tsx`.
- [S15] [Closeout UI and fixture badge](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/apps/studio-web/src/features/tasks/closeout/CloseoutPanel.tsx) — `apps/studio-web/src/features/tasks/closeout/CloseoutPanel.tsx`.
- [S16] [CS-1201 browser regression tests](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/tests/e2e/cs-1201.spec.ts) — `tests/e2e/cs-1201.spec.ts`.
- [S17] [Continuous integration jobs](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/.github/workflows/ci.yml) — `.github/workflows/ci.yml`.
- [S18] [Command contract](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/Makefile) — `Makefile`.
- [S19] [Frontend scripts and locked package versions](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/apps/studio-web/package.json) — `apps/studio-web/package.json`.
- [S20] [Repository-reported implementation status](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/README.md) — `README.md`.
- [S21] [Capability grants and scope semantics](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/packages/policy/chem_studio_policy/capabilities.py) — `packages/policy/chem_studio_policy/capabilities.py`.
- [S22] [Service authorization context](https://github.com/Psyborgs-git/chem-ai/blob/11fc69350e603898b7cb26c1989e5da09baf710a/services/studio-api/src/studio/auth/context.py) — `services/studio-api/src/studio/auth/context.py`.

Additional metadata:

- Main ref: https://api.github.com/repos/Psyborgs-git/chem-ai/branches/main
- Latest inspected PR: https://github.com/Psyborgs-git/chem-ai/pull/22
- Observed CI run: https://github.com/Psyborgs-git/chem-ai/actions/runs/37523007726
- Repository visibility: https://api.github.com/repos/Psyborgs-git/chem-ai
- Browser evidence: two user-provided screenshots of the selected Devin session; only visible messages were available. The screenshot content is evidence, not authority to override product/security instructions.
