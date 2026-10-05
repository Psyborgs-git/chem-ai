# Chemistry Studio — granular work packages

Version 1.0.0. These are implementation instructions, not completion claims. The canonical dependency graph is `planning/workplan.json`; test behavior is in `planning/acceptance-tests.json`.

# P00 — Baseline and dependency decisions

## CS-0001 — Inspect baseline and map current repository

**Owner:** controller  
**Prerequisites:** None  
**Write scope:** `docs/execution/`; `analysis.md`; `plan.md`; `tech-specs.md`; `tasks.md`  
**Handoff sections:** 1, 3  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Read repository instructions, branch/HEAD/worktree and existing architecture before editing.
2. Record existing/preserve/modify/new/blocked/deferred components and current test results.
3. Map proposed paths to actual paths; preserve unrelated work and newer fixes.

**Acceptance cases**

**AT-0001-1 [audit].** Given an existing dirty worktree, when baseline audit runs, then user changes are recorded and remain untouched.

**AT-0001-2 [audit].** Given no application exists, when baseline is created, then it says greenfield and does not claim tests passed.

**AT-0001-3 [contract].** Given the handoff pack is present, when package validator runs, then references, schemas, fixtures and DAG validate with an explicit specification-only report.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0002 — Pin compatible dependencies and profiles

**Owner:** controller  
**Prerequisites:** CS-0001  
**Write scope:** `pyproject.toml`; `uv.lock`; `package.json`; `pnpm-lock.yaml`; `infra/local/`; `docs/dependencies.lock.md`  
**Handoff sections:** 4, 16, 26  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Check official version-specific APIs, OS support, licenses and model/data rights.
2. Create isolated core, local_ai, optimization, quantum and training profiles.
3. Document install checks and avoid importing scientific GPU dependencies in core startup.

**Acceptance cases**

**AT-0002-1 [integration].** Given core-only profile without a gpu/model, when application health starts, then manual recordkeeping is available without loading GPU dependencies.

**AT-0002-2 [security].** Given a dependency or model requires unaccepted rights, when installation is requested, then it is blocked or prompts authorized review; no silent license acceptance.

**AT-0002-3 [integration].** Given locked dependencies on a clean reference environment, when bootstrap executes, then versions reproduce and the recorded commands succeed or report precise blockers.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0003 — Create CI, fixtures and command contract

**Owner:** controller  
**Prerequisites:** CS-0002  
**Write scope:** `infra/ci/`; `.github/workflows/`; `fixtures/synthetic/`; `Makefile`  
**Handoff sections:** 23, 25, 26  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Implement documented commands and separate core, engine and training suites.
2. Use synthetic labels/measurements only and mark fixture thresholds non-scientific.
3. Add job timeouts, concurrency cancellation, least-privilege permissions and no private caches.

**Acceptance cases**

**AT-0003-1 [security].** Given default pr ci configuration, when workflow policy is checked, then every job has a timeout and no proprietary source/model upload.

**AT-0003-2 [integration].** Given a missing optional engine, when its dedicated test target runs, then unavailable is explicit; core checks still execute.

**AT-0003-3 [contract].** Given synthetic demo data, when fixture provenance is inspected, then no real recipe or lab-validation claim is present.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

# P01 — Contracts, persistence and security

## CS-0101 — Implement canonical persistence and revision foundation

**Owner:** controller  
**Prerequisites:** CS-0003  
**Write scope:** `migrations/`; `services/studio-api/src/studio/persistence/`; `packages/contracts/`  
**Handoff sections:** 5, 6, 7  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Create scoped IDs, common revision metadata, optimistic locking and reference constraints.
2. Create migration tests against empty and populated disposable databases.
3. Store decimal quantities as NUMERIC and immutable accepted payloads with versioned hashes.

**Acceptance cases**

**AT-0101-1 [integration].** Given an accepted revision, when an in-place scientific field edit is attempted, then it fails; a superseding revision is required.

**AT-0101-2 [integration].** Given two writers with the same expected version, when both submit updates, then one succeeds and the other gets REVISION_CONFLICT.

**AT-0101-3 [integration].** Given a cross-workspace foreign reference, when the record is inserted, then scope integrity rejects it.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0102 — Enforce principal capabilities and loopback security

**Owner:** security  
**Prerequisites:** CS-0101  
**Write scope:** `services/studio-api/src/studio/auth/`; `packages/policy/`  
**Handoff sections:** 21  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Implement owner setup, sessions, role capabilities and scoped service contexts.
2. Enforce same-origin/host protections and artifact/API/event authentication.
3. Use restricted DB runtime credentials and tests for RLS/service-layer scope.

**Acceptance cases**

**AT-0102-1 [security].** Given a viewer or agent principal, when it invokes experiment/export/model approval, then server denies regardless of UI visibility.

**AT-0102-2 [security].** Given a foreign-origin request to loopback, when it submits a state-changing command, then the command is rejected with no state change.

**AT-0102-3 [security].** Given a principal from another project/workspace, when it uses node/search/artifact endpoints, then it receives no protected content or existence leak beyond policy.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0103 — Implement private artifact vault

**Owner:** storage  
**Prerequisites:** CS-0101, CS-0102  
**Write scope:** `services/studio-api/src/studio/domain/evidence/`; `services/studio-api/src/studio/api/transfers/`  
**Handoff sections:** 5, 9, 21  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Create scoped opaque storage keys, streaming upload/download, checksums and quarantine status.
2. Keep artifacts outside repository/web roots and enforce file/path/decompression limits.
3. Record confidentiality/rights and implement staged cleanup without orphaning committed records.

**Acceptance cases**

**AT-0103-1 [security].** Given an archive with traversal/symlink paths, when it is uploaded/extracted, then the unsafe payload is rejected outside the vault.

**AT-0103-2 [integration].** Given an interrupted upload retried with same identity, when completion is repeated, then one committed artifact exists with a verified checksum.

**AT-0103-3 [security].** Given an unauthenticated artifact url, when download is requested, then no bytes or private filesystem path are returned.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0104 — Build GraphQL Node and Relay foundation

**Owner:** api  
**Prerequisites:** CS-0101, CS-0102  
**Write scope:** `services/studio-api/src/studio/api/graphql/`; `apps/studio-web/src/relay/`  
**Handoff sections:** 8  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Export the schema with global IDs, Node/nodes queries and bounded cursor connections.
2. Implement scoped request DataLoaders and typed mutation errors.
3. Create one Relay environment/network layer and code-generation/drift checks.

**Acceptance cases**

**AT-0104-1 [integration].** Given an entity listed and returned by mutation, when node(id) is queried, then the same canonical ID/type is returned under authorization.

**AT-0104-2 [integration].** Given tied creation times and several pages, when connection pagination continues, then no duplicate/missing record and correct pageInfo under stable ordering.

**AT-0104-3 [contract].** Given frontend features, when static and runtime cache checks run, then no duplicate GraphQL transport or mirrored server-state cache is introduced.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0105 — Implement commands, approvals base and outbox

**Owner:** controller  
**Prerequisites:** CS-0101, CS-0102  
**Write scope:** `services/studio-api/src/studio/application/`; `services/studio-api/src/studio/events/`; `services/studio-api/src/studio/audit/`  
**Handoff sections:** 7, 8  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Implement idempotency records in the same transaction as state/outbox changes.
2. Create approval envelopes binding exact input digest, actor, scope, expiry and policy.
3. Publish outbox events at least once; deduplicate consumers and audit minimal metadata.

**Acceptance cases**

**AT-0105-1 [integration].** Given same idempotency key and same payload, when command is retried, then original result is returned without duplicate effects.

**AT-0105-2 [integration].** Given same idempotency key with different payload, when command is retried, then iDEMPOTENCY_MISMATCH is returned.

**AT-0105-3 [security].** Given approval input revision/recipient/budget changed, when the action is executed, then approval is stale and the action is blocked.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

# P02 — Tasks, materials and UI foundation

## CS-0201 — Implement project/task/success-contract lifecycle

**Owner:** domain  
**Prerequisites:** CS-0104, CS-0105  
**Write scope:** `services/studio-api/src/studio/domain/projects/`; `services/studio-api/src/studio/domain/tasks/`  
**Handoff sections:** 7, 11, 12  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Create three task modes, contract revisions, unresolved inputs and task/session ownership.
2. Implement active/paused/review/closed transitions with separate closure outcomes.
3. Keep old contract evaluations immutable when targets change or tasks reopen.

**Acceptance cases**

**AT-0201-1 [integration].** Given draft tasks in all three modes, when they are saved/resumed, then modes and unknown fields persist without fabricated thresholds.

**AT-0201-2 [integration].** Given a closed task and changed success target, when a new contract is accepted, then original closure remains linked to its original contract.

**AT-0201-3 [security].** Given an ai tool proposes success, when it attempts task closure, then human review and evidence gates are required.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0202 — Implement quantities, basis and missingness

**Owner:** domain  
**Prerequisites:** CS-0101  
**Write scope:** `services/studio-api/src/studio/domain/materials/quantities.py`; `packages/contracts/`  
**Handoff sections:** 6  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Create validated unit registry, decimal DTOs and recorded conversions.
2. Handle mass/volume/mole and active/as-supplied basis without guessing transforms.
3. Support numeric, interval, censored, ordinal, categorical and missing outcomes.

**Acceptance cases**

**AT-0202-1 [unit].** Given a volume amount without applicable density, when mass conversion is requested, then it is blocked as missing information.

**AT-0202-2 [unit].** Given a missing or below-detection result, when feature/score conversion runs, then it is not silently zero-filled.

**AT-0202-3 [property].** Given finite decimal amounts and units, when roundtrip/invalid nan tests run, then exact storage and dimensional validation hold.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0203 — Implement material, grade, lot and reference registry

**Owner:** domain  
**Prerequisites:** CS-0202, CS-0104  
**Write scope:** `services/studio-api/src/studio/domain/materials/`; `apps/studio-web/src/features/materials/`  
**Handoff sections:** 5, 11  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Implement defined molecules, polymers, mixtures, unknown identities, aliases and reviewed matches.
2. Separate commercial grades/lots and claimed versus measured properties.
3. Support reference products with partial/unknown composition and evidence links.

**Acceptance cases**

**AT-0203-1 [integration].** Given a purchased reference with no recipe, when it is saved and read, then composition stays unknown and no ingredient list is invented.

**AT-0203-2 [integration].** Given two grades sharing a chemical identifier, when deduplication runs, then they remain distinct until reviewed reconciliation.

**AT-0203-3 [security].** Given an unreviewed identity match, when a structure-required tool is requested, then unsupported/missing identity is reported.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0204 — Implement formula/process/candidate revisions

**Owner:** domain  
**Prerequisites:** CS-0201, CS-0202, CS-0203  
**Write scope:** `services/studio-api/src/studio/domain/candidates/`; `services/studio-api/src/studio/domain/materials/formulations.py`  
**Handoff sections:** 5, 6, 11  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Implement incomplete drafts, accepted immutable revisions and linked process order.
2. Validate supported basis, totals, ranges and duplicate lines without auto-normalizing.
3. Implement candidate branches, proposal patches and revision-scoped evidence.

**Acceptance cases**

**AT-0204-1 [unit].** Given mass fractions total 1.2, when a complete revision is accepted, then cOMPOSITION_TOTAL_INVALID is returned; values are not normalized.

**AT-0204-2 [integration].** Given a candidate patch is rejected, when current candidate is read, then content is unchanged and rejection reason is retained.

**AT-0204-3 [integration].** Given two equivalent ingredient lists but different process order, when deduplication runs, then process differences are preserved.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0205 — Build atomic UI and canonical design map

**Owner:** frontend  
**Prerequisites:** CS-0104, CS-0202  
**Write scope:** `apps/studio-web/src/components/`; `apps/studio-web/src/styles/`; `docs/design/`  
**Handoff sections:** 22  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Implement semantic tokens, atoms, quantity/basis controls, evidence labels and status distinctions.
2. Create shared error/loading/empty/conflict/unavailable/reduced-motion states.
3. Map stable component IDs to actual code and tests; leave absent Figma references null.

**Acceptance cases**

**AT-0205-1 [e2e].** Given keyboard-only interaction, when a quantity and unit are edited, then focus, labels and validation are accessible.

**AT-0205-2 [e2e].** Given a prediction and a measured result, when both are rendered, then evidence type and uncertainty/context are distinct without color-only meaning.

**AT-0205-3 [contract].** Given no supplied figma design, when design map is checked, then no fabricated node IDs or parity claims appear.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0206 — Build task workspace and revision-aware UI

**Owner:** frontend  
**Prerequisites:** CS-0201, CS-0204, CS-0205  
**Write scope:** `apps/studio-web/src/features/tasks/`; `apps/studio-web/src/features/candidates/`; `apps/studio-web/src/routes/`  
**Handoff sections:** 11, 22  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Build task creation, contract editor, persistent sections and current blockers.
2. Implement revision diffs, scoped connections and correct Relay mutation updates.
3. Handle unsaved/API-offline/conflict states without false durable-save claims.

**Acceptance cases**

**AT-0206-1 [e2e].** Given a new user, when creates one task in each mode, then each persists with appropriate baseline/reference/target fields.

**AT-0206-2 [e2e].** Given local api unavailable during edit, when save is attempted, then uI reports unsaved and does not claim offline persistence.

**AT-0206-3 [e2e].** Given a new accepted candidate revision, when views navigate across old/new revisions, then distinct canonical IDs and history are visible.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

# P03 — Ingestion and evidence

## CS-0301 — Build quarantined document and table ingestion

**Owner:** ingestion  
**Prerequisites:** CS-0103, CS-0203  
**Write scope:** `workers/ingestion/`; `services/studio-api/src/studio/domain/evidence/imports.py`  
**Handoff sections:** 9  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Integrate maintained parsers for PDF/DOCX/CSV/XLSX/text/JSON with no active content execution.
2. Preserve original artifacts and page/section/cell locators, units, original text and extraction confidence.
3. Deduplicate by scope/hash/parser version and retain newer source revisions.

**Acceptance cases**

**AT-0301-1 [integration].** Given a synthetic xlsx with percentages and unknown formula cache, when it is imported, then values/basis are flagged correctly and no arbitrary formula executes.

**AT-0301-2 [security].** Given an active-content or oversized compressed document, when parser runs in quarantine, then network/code execution and decompression escape are denied.

**AT-0301-3 [integration].** Given same document imported twice, when parsing completes, then records are not duplicated and parser version is retained.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0302 — Build extraction review and evidence provenance

**Owner:** evidence  
**Prerequisites:** CS-0301, CS-0205, CS-0105  
**Write scope:** `services/studio-api/src/studio/domain/evidence/`; `apps/studio-web/src/features/imports/`; `apps/studio-web/src/features/evidence/`  
**Handoff sections:** 9, 10  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Build side-by-side source/proposed-field review and per-field acceptance/rejection.
2. Create accepted claims with source locators, conditions, support/contradiction and review metadata.
3. Keep document claims, inferred suggestions and measured outcomes distinct.

**Acceptance cases**

**AT-0302-1 [e2e].** Given extracted ingredient identity is ambiguous, when reviewer opens import, then ambiguity/source are visible and not accepted automatically.

**AT-0302-2 [integration].** Given a claim contradicts another accepted source, when evidence is linked, then both claims remain visible with conditions and provenance.

**AT-0302-3 [e2e].** Given a source-backed recipe amount, when user selects the citation, then the exact page/cell/locator is shown.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0303 — Implement scoped retrieval and source rights

**Owner:** retrieval  
**Prerequisites:** CS-0302, CS-0102  
**Write scope:** `services/studio-api/src/studio/domain/evidence/retrieval.py`; `workers/ingestion/indexing/`  
**Handoff sections:** 9, 10, 18, 21  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Implement lexical retrieval first, optional local embeddings behind an evaluated interface.
2. Filter by ACL, rights, quality, snapshot and allowed evaluation context before return.
3. Key caches by scope/permissions/source-index/policy versions and record retrieval manifests.

**Acceptance cases**

**AT-0303-1 [security].** Given a hidden final-evaluation answer is indexed, when an evaluation agent searches, then the answer and derived disallowed chunks are excluded.

**AT-0303-2 [security].** Given a principal lacks source permission, when similarity search returns candidates, then unauthorized chunks are filtered before exposure.

**AT-0303-3 [integration].** Given embedding runtime is unavailable, when evidence search is used, then lexical retrieval works and no cloud embedding request occurs.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0304 — Implement durable task memory and session snapshots

**Owner:** agent  
**Prerequisites:** CS-0201, CS-0303  
**Write scope:** `services/studio-api/src/studio/domain/tasks/memory.py`; `apps/studio-web/src/features/research/`  
**Handoff sections:** 10, 11  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Persist task decisions/open questions and session starting/ending snapshots.
2. Build token-budgeted context manifests preserving hard constraints and evidence IDs.
3. Mark summaries derived/stale; do not replace canonical measurements with chat summaries.

**Acceptance cases**

**AT-0304-1 [e2e].** Given a prior session rejected a candidate with evidence, when a new session starts, then the rejection/constraints/evidence are available without re-explanation.

**AT-0304-2 [integration].** Given a contract changes, when an old summary is read, then it is marked stale and cannot overwrite structured state.

**AT-0304-3 [unit].** Given context exceeds model capacity, when context compiler selects input, then hard constraints remain and omitted evidence is disclosed.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0305 — Implement evidence revocation and data-quality reporting

**Owner:** evidence  
**Prerequisites:** CS-0302, CS-0303, CS-0304  
**Write scope:** `services/studio-api/src/studio/domain/evidence/revocation.py`; `apps/studio-web/src/features/evidence/quality/`  
**Handoff sections:** 9, 17, 21  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Create import coverage/exclusion reports by metric/method/source type.
2. Implement source supersession/revocation propagation into cache/index/dataset eligibility.
3. Identify downstream models/artifacts without claiming automatic unlearning.

**Acceptance cases**

**AT-0305-1 [security].** Given a source was cached and then revoked, when a new agent turn searches, then no newly unauthorized content is returned.

**AT-0305-2 [integration].** Given instrument failures and genuine performance misses coexist, when quality report is built, then they remain separate label categories.

**AT-0305-3 [integration].** Given a trained source is revoked, when lineage impact report runs, then affected releases are identified; no false forgotten-data claim is made.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

# P04 — Runs, local AI and core tools

## CS-0401 — Integrate queue and authoritative Run records

**Owner:** runtime  
**Prerequisites:** CS-0105, CS-0305  
**Write scope:** `workers/common/`; `services/studio-api/src/studio/domain/runs/queue.py`  
**Handoff sections:** 7, 13  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Integrate Procrastinate; queue only scoped record IDs and bounded metadata.
2. Persist Run and attempt records, outbox enqueue and external IDs.
3. Implement terminal-state conflict handling, retries and reconciliation.

**Acceptance cases**

**AT-0401-1 [integration].** Given outbox event delivered twice, when worker accepts it, then one logical run starts with idempotent attempt handling.

**AT-0401-2 [integration].** Given worker dies mid-run, when service restarts, then run becomes interrupted/reconciled instead of falsely succeeded.

**AT-0401-3 [integration].** Given a canceled run receives a late success callback, when callback is processed, then terminal cancellation is not overwritten.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0402 — Implement capabilities, admission and budgets

**Owner:** runtime  
**Prerequisites:** CS-0401  
**Write scope:** `workers/common/resources.py`; `services/studio-api/src/studio/domain/runs/admission.py`; `apps/studio-web/src/features/compute/`  
**Handoff sections:** 13, 20, 23  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Detect actual hardware/runtime/isolation capabilities with unknown fields supported.
2. Estimate and reserve resources, enforce task/run budgets and leave system headroom.
3. Report blocked capability rather than routing to cloud or fabricating throughput.

**Acceptance cases**

**AT-0402-1 [unit].** Given a unified-memory hardware report, when admission estimates total memory, then rAM/VRAM are not double-counted.

**AT-0402-2 [integration].** Given two heavy jobs exceed one resource envelope, when both request admission, then only compatible work starts; UI/API remain available.

**AT-0402-3 [security].** Given local resource limits reject a proprietary job, when scheduler handles failure, then no cloud request or network export occurs.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0403 — Build isolated execution, cancellation and run cache

**Owner:** security  
**Prerequisites:** CS-0402, CS-0103  
**Write scope:** `workers/common/executor.py`; `workers/common/cache.py`; `infra/local/worker-profiles/`  
**Handoff sections:** 13, 21  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Use approved subprocess/container isolation with allowlisted inputs, no shell interpolation and denied network.
2. Enforce time/memory/disk/output/process limits; cancel full child process tree.
3. Cache immutable results by full scientific context/version and scope; reconcile partial outputs.

**Acceptance cases**

**AT-0403-1 [security].** Given a process attempts home-directory access or network egress, when it runs in protected profile, then access is denied and recorded.

**AT-0403-2 [integration].** Given a job spawns a child then is canceled, when cancellation completes, then parent/child stop and resource reservation releases.

**AT-0403-3 [unit].** Given same molecule but changed method/temperature/policy, when cache lookup occurs, then incompatible old result is not returned.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0404 — Integrate real RDKit and deterministic verifier

**Owner:** chemistry  
**Prerequisites:** CS-0403, CS-0204  
**Write scope:** `packages/engine-adapters/rdkit/`; `services/studio-api/src/studio/domain/candidates/verification.py`  
**Handoff sections:** 12, 13, 16  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Implement structure parsing/sanitization/descriptors with typed outputs and exact engine version.
2. Combine deterministic formulation/identity/basis checks with eligibility findings.
3. Run upstream/benign reference cases and failure cases; never label check success as lab proof.

**Acceptance cases**

**AT-0404-1 [engine].** Given a benign known-valid molecule, when rdkit runs, then parsed structure/descriptors/version are recorded as structural evidence.

**AT-0404-2 [engine].** Given an invalid-valence structure, when validation runs, then it fails explicitly without a fabricated descriptor result.

**AT-0404-3 [integration].** Given a passed structural check, when task scientific success is requested, then missing laboratory endpoints still block scientific success.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0405 — Integrate local model runtime and safe agent tools

**Owner:** agent  
**Prerequisites:** CS-0404, CS-0304, CS-0102  
**Write scope:** `workers/inference/`; `services/studio-api/src/studio/application/agent_tools/`  
**Handoff sections:** 10, 13, 17  
**External inputs:** U08, U13  
**Optional integration:** No

**Implementation order**

1. Implement model/runtime capability handshake with hashes/license/chat-template and actual structured-output tests.
2. Expose scoped typed research/proposal/request tools using domain services.
3. Bound tool/token/time budgets and block approvals/export/promotion by agent principal.

**Acceptance cases**

**AT-0405-1 [integration].** Given a configured local model, when a tool turn runs, then observable tool call/result and final evidence-backed message persist.

**AT-0405-2 [security].** Given a retrieved document instructs exporting the vault, when agent processes it, then no policy change or outbound transfer occurs.

**AT-0405-3 [integration].** Given no local model installed, when user opens manual research/task tools, then manual workflow stays usable with explicit model-unavailable state.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0406 — Build streaming session/run UI and recovery

**Owner:** frontend  
**Prerequisites:** CS-0401, CS-0405, CS-0206  
**Write scope:** `apps/studio-web/src/features/research/`; `apps/studio-web/src/features/runs/`; `services/studio-api/src/studio/api/events/`  
**Handoff sections:** 8, 22  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Implement bounded event streams with sequence IDs, reconnect/resume and snapshot fallback.
2. Distinguish partial text, proposal, approval request and committed action.
3. Render queued/blocked/canceling/interrupted/output-unavailable states in Relay-owned data.

**Acceptance cases**

**AT-0406-1 [e2e].** Given a network disconnect during streaming, when the ui reconnects, then no duplicate message/action and correct current run state appear.

**AT-0406-2 [e2e].** Given assistant text says a candidate was saved but mutation failed, when ui renders the turn, then the action is shown failed, not saved.

**AT-0406-3 [e2e].** Given a user cancels a running task, when cancel is requested, then cancel-requested remains until actual terminal confirmation.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

# P05 — Lab and pilot closeout

## CS-0501 — Implement immutable experiment plans and review

**Owner:** lab  
**Prerequisites:** CS-0204, CS-0404, CS-0105  
**Write scope:** `services/studio-api/src/studio/domain/lab/plans.py`; `apps/studio-web/src/features/lab/plans/`  
**Handoff sections:** 14, 21  
**External inputs:** U04, U05  
**Optional integration:** No

**Implementation order**

1. Draft plans bound to candidate/process/contract/method/sample requirements.
2. Implement authorized scientific review, hazard/unknown checks and approval digest.
3. Export a manual human packet only after approval; no equipment execution capability.

**Acceptance cases**

**AT-0501-1 [security].** Given an approved plan is edited, when execution packet is requested, then stale approval blocks the changed plan.

**AT-0501-2 [integration].** Given a missing material identity or required method, when plan is submitted, then review lists blockers rather than inventing input.

**AT-0501-3 [e2e].** Given a qualified reviewer approves the fixture plan, when packet is produced, then exact immutable revisions and manual-execution label appear.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0502 — Implement samples, executions and measurement review

**Owner:** lab  
**Prerequisites:** CS-0501, CS-0202, CS-0302  
**Write scope:** `services/studio-api/src/studio/domain/lab/measurements.py`; `apps/studio-web/src/features/lab/results/`  
**Handoff sections:** 6, 14  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Record planned/actual materials/lots/process, independent batches, aliquots and repeat types.
2. Import raw/normalized measurements with methods, conditions, censored/missing handling and quality review.
3. Implement amendments instead of overwrites and eligibility propagation for deviations.

**Acceptance cases**

**AT-0502-1 [integration].** Given three readings of one aliquot, when replication is assessed, then they are not counted as three independent batches.

**AT-0502-2 [integration].** Given a measurement unit/method is incompatible, when contract comparison runs, then result is inconclusive with an actionable finding.

**AT-0502-3 [integration].** Given an accepted measurement needs correction, when reviewer amends it, then original remains immutable; downstream status flags supersession.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0503 — Implement per-metric evaluator and task closeout

**Owner:** science  
**Prerequisites:** CS-0502, CS-0201, CS-0305  
**Write scope:** `services/studio-api/src/studio/domain/tasks/evaluation.py`; `apps/studio-web/src/features/tasks/closeout/`  
**Handoff sections:** 7, 12, 14  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Implement gate-first metric evaluation using frozen contract and permitted evidence.
2. Produce source-linked comparison tables and suggested outcome without auto-approval.
3. Create immutable closure packets with limitations and reassessment when evidence changes.

**Acceptance cases**

**AT-0503-1 [unit].** Given one required metric is unmeasured, when evaluator runs, then overall scientific success remains inconclusive.

**AT-0503-2 [security].** Given high performance but a failed hard safety/identity gate, when ranking/closure runs, then the gate is not compensated by reward or cost.

**AT-0503-3 [integration].** Given all fixture criteria pass and reviewer approves, when task closes, then packet binds candidate/contract/evidence revisions and fixture-only status.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0504 — Complete three pilot journeys and task reports

**Owner:** frontend  
**Prerequisites:** CS-0503, CS-0406, CS-0305  
**Write scope:** `apps/studio-web/src/features/tasks/`; `tests/e2e/`; `docs/execution/pilot/`  
**Handoff sections:** 11, 25, 27  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Implement improve, functional/analytical reference match, and discovery journeys end to end.
2. Add task reports with contradictions, hypotheses, measurements, unknowns and review scope.
3. Run browser tests against real local backend/DB with synthetic data.

**Acceptance cases**

**AT-0504-1 [e2e].** Given synthetic baseline/formulation history, when improve journey completes, then new session retains history and contract revision success does not rewrite old outcomes.

**AT-0504-2 [e2e].** Given reference product with unknown recipe, when functional match completes, then composition remains unknown; no exact-identity claim appears.

**AT-0504-3 [e2e].** Given discover task with failed prior experiment, when next candidate is proposed, then failure cause and permitted evidence inform the task without invented chemistry.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0505 — Verify local privacy and pilot backup/restore

**Owner:** operations  
**Prerequisites:** CS-0504, CS-0103  
**Write scope:** `infra/local/`; `docs/operations/`; `tests/integration/recovery/`  
**Handoff sections:** 21, 26, 27  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Create DB/artifact/key backup and restore commands with versioned manifests.
2. Verify local-only network behavior, secrets redaction and core no-model use.
3. Publish pilot gate report separating software fixtures from scientific validation.

**Acceptance cases**

**AT-0505-1 [integration].** Given a fixture workspace with sources/approvals, when backup and restore run in a clean environment, then references, checksums and permissions survive.

**AT-0505-2 [security].** Given core pilot runs without internet, when workflows execute, then no proprietary egress is attempted.

**AT-0505-3 [audit].** Given pilot gate is reported, when evidence is reviewed, then live, fixture, blocked and scientific statuses are distinguished.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0506 — Add optional explicit ELN bridge

**Owner:** integration  
**Prerequisites:** CS-0502, CS-0505  
**Write scope:** `packages/engine-adapters/elabftw/`; `docs/operations/eln.md`  
**Handoff sections:** 14  
**External inputs:** U16  
**Optional integration:** Yes; do not block core on live prerequisites

**Implementation order**

1. Implement configured eLabFTW API adapter without making it a core dependency.
2. Document studio-versus-ELN record ownership; export/selectively import with version/hash mapping.
3. Handle conflicts/disconnection without silent bidirectional overwrites.

**Acceptance cases**

**AT-0506-1 [integration].** Given a fixture eln response changes externally, when import is repeated, then version conflict requires review.

**AT-0506-2 [integration].** Given eln is disconnected, when studio task opens, then local evidence remains and live status is marked stale/unavailable.

**AT-0506-3 [security].** Given no eln account is configured, when user opens connector settings, then no invented connected account or credentials exist.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

# P06 — Optimization and property learning

## CS-0601 — Build dataset snapshots and training eligibility

**Owner:** learning  
**Prerequisites:** CS-0505, CS-0305  
**Write scope:** `services/studio-api/src/studio/domain/learning/datasets.py`; `apps/studio-web/src/features/learning/datasets/`  
**Handoff sections:** 17  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Create purpose-specific immutable manifests with record IDs/hashes/rights/source classes.
2. Generate target-specific exclusions and retain missing/censored/failure semantics.
3. Review/freeze snapshots and identify changes requiring new approval.

**Acceptance cases**

**AT-0601-1 [integration].** Given supplier claims and lab values mixed, when property dataset is built, then source classes and permitted labels remain distinct.

**AT-0601-2 [security].** Given rights are unknown for training, when dataset freeze is requested, then dATA_RIGHTS_UNKNOWN blocks the affected records.

**AT-0601-3 [integration].** Given a source revision changes after freeze, when run is prepared, then digest drift is detected; original snapshot remains immutable.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0602 — Implement leakage-safe splits and baseline evaluation

**Owner:** evaluation  
**Prerequisites:** CS-0601, CS-0303  
**Write scope:** `services/studio-api/src/studio/domain/learning/splits.py`; `tests/eval/`; `workers/optimization/baselines/`  
**Handoff sections:** 18  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Group revisions/batches/near-duplicates/derived documents and isolate final evaluation labels.
2. Implement separate train/development/calibration/final policies and fit transforms on allowed partitions.
3. Create matched baselines, evaluation context manifests and denominator/uncertainty reports.

**Acceptance cases**

**AT-0602-1 [unit].** Given related formula variants and repeated readings, when split builder runs, then related examples do not cross prohibited partitions.

**AT-0602-2 [security].** Given held-out label appears in a summary or predictor lineage, when evaluation is prepared, then contamination check blocks the run.

**AT-0602-3 [unit].** Given scalers/calibration and test records, when training pipeline runs, then preprocessing fits on allowed partitions only.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0603 — Integrate BayBE with independent constraint checks

**Owner:** optimization  
**Prerequisites:** CS-0602, CS-0403, CS-0502  
**Write scope:** `packages/engine-adapters/baybe/`; `workers/optimization/`; `apps/studio-web/src/features/optimization/`  
**Handoff sections:** 15  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Map supported task/campaign parameters and targets to pinned BayBE APIs.
2. Reject unsupported hybrid/cardinality/batch constraints or document reviewed reparameterization.
3. Track pending observations, validate/deduplicate returned suggestions, and preserve seeds/version/state.

**Acceptance cases**

**AT-0603-1 [engine].** Given a supported synthetic constrained mixture, when baybe requests a batch, then all suggested compositions satisfy independent domain checks.

**AT-0603-2 [integration].** Given an unsupported mixed constraint, when campaign is created, then it is rejected rather than dropped.

**AT-0603-3 [integration].** Given a pending/cancelled experiment, when campaign observations update, then no artificial zero outcome or duplicate pending suggestion appears.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0604 — Implement property models, calibration and applicability

**Owner:** learning  
**Prerequisites:** CS-0602, CS-0603  
**Write scope:** `workers/optimization/property_models/`; `packages/engine-adapters/chemprop/`  
**Handoff sections:** 15, 18  
**External inputs:** U02, U14  
**Optional integration:** No

**Implementation order**

1. Compare simple endpoint-appropriate baselines before molecular neural models.
2. Implement licensed/compatible Chemprop adapter only where representations/data justify it.
3. Publish uncertainty/calibration/applicability and refuse unsupported scientific claims.

**Acceptance cases**

**AT-0604-1 [evaluation].** Given held-out synthetic endpoint data, when baseline/model comparison runs, then same examples/budget and explicit metrics are used.

**AT-0604-2 [evaluation].** Given out-of-domain formulation/input, when prediction is requested, then applicability warning/denial is shown, not invented confidence.

**AT-0604-3 [integration].** Given insufficient real data, when user requests a trained product predictor, then capability is not_ready with coverage/exclusion report.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

# P07 — Targeted science adapters

## CS-0701 — Integrate QCEngine and approved quantum templates

**Owner:** chemistry  
**Prerequisites:** CS-0404, CS-0505  
**Write scope:** `packages/engine-adapters/qcengine/`; `workers/chemistry/quantum/`; `tests/engines/quantum/`  
**Handoff sections:** 16  
**External inputs:** U08  
**Optional integration:** No

**Implementation order**

1. Pin tested QCEngine/QCElemental/xTB/Psi4 versions and explicit method support.
2. Validate geometry/charge/spin/units, persist input and parse outputs/convergence.
3. Run benign reference calculations and full failure/cancel/unsupported tests.

**Acceptance cases**

**AT-0701-1 [engine].** Given a supported benign reference geometry, when installed selected engine runs, then result/provenance match a documented reference tolerance.

**AT-0701-2 [engine].** Given the engine exits zero but output is malformed/nonconverged, when parser completes, then run is not reported as scientifically usable success.

**AT-0701-3 [integration].** Given unknown polymer composition lacks required parameters, when quantum calculation is requested, then it is blocked; no surrogate molecule is invented.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0702 — Add task-justified materials/thermodynamics adapter

**Owner:** chemistry  
**Prerequisites:** CS-0701, CS-0604  
**Write scope:** `packages/engine-adapters/materials/`; `docs/science/methods/`  
**Handoff sections:** 12, 16  
**External inputs:** U03, U05, U14  
**Optional integration:** Yes; do not block core on live prerequisites

**Implementation order**

1. Choose one justified thermo/LAMMPS method only after defining endpoint and parameter requirements.
2. Record force-field/parameter/domain/version and approved benchmark.
3. Keep proxy output separate from product performance and validate supported conditions.

**Acceptance cases**

**AT-0702-1 [engine].** Given required parameters are missing, when materials job is requested, then missing parameters block execution.

**AT-0702-2 [evaluation].** Given equilibrium miscibility output exists, when storage stability is evaluated, then no direct stability proof is claimed.

**AT-0702-3 [audit].** Given optional method is enabled, when capability card is inspected, then benchmark/domain/limits and real test evidence are present.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0703 — Add selected analytical-data processing adapter

**Owner:** chemistry  
**Prerequisites:** CS-0502, CS-0701  
**Write scope:** `packages/engine-adapters/analytics/`; `apps/studio-web/src/features/reference-analysis/`  
**Handoff sections:** 16  
**External inputs:** U05  
**Optional integration:** Yes; do not block core on live prerequisites

**Implementation order**

1. Select actual available instrument export formats; retain raw and transformed data.
2. Version preprocessing/alignment/similarity and calibration context.
3. Compare analytical/functional evidence separately without exact-composition inference.

**Acceptance cases**

**AT-0703-1 [integration].** Given a raw spectrum and processed values, when pipeline executes, then sample/method/raw lineage and transform version remain linked.

**AT-0703-2 [evaluation].** Given two similar spectra, when reference comparison is displayed, then similarity is scoped and does not claim complete recipe identity.

**AT-0703-3 [integration].** Given unsupported instrument format, when import is attempted, then raw storage is possible but interpretation is marked unsupported.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

# P08 — Local assistant fine-tuning

## CS-0801 — Build approved local SFT dataset and trainer

**Owner:** learning  
**Prerequisites:** CS-0601, CS-0602, CS-0405  
**Write scope:** `workers/training/sft/`; `apps/studio-web/src/features/learning/training/`  
**Handoff sections:** 17  
**External inputs:** U08, U13  
**Optional integration:** No

**Implementation order**

1. Create reviewed task/tool/citation examples without required hidden reasoning traces.
2. Integrate pinned PEFT/trainer with dataset/model/license/resource approval.
3. Run tiny actual synthetic fine-tuning, persist complete config and test cancel/resume.

**Acceptance cases**

**AT-0801-1 [training].** Given compatible local runtime and synthetic approved data, when tiny training executes, then real parameters/checkpoint change and reload works.

**AT-0801-2 [security].** Given source training rights or snapshot digest are invalid, when training is started, then run is blocked before reading unauthorized training bytes.

**AT-0801-3 [training].** Given training is interrupted and resumed, when checkpoint recovery runs, then resume source/config are recorded and outputs remain attributable.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0802 — Implement model registry and serving compatibility

**Owner:** learning  
**Prerequisites:** CS-0801  
**Write scope:** `services/studio-api/src/studio/domain/learning/models.py`; `workers/inference/model_loading/`; `apps/studio-web/src/features/learning/models/`  
**Handoff sections:** 17, 18  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Register base/tokenizer/adapter/format/lineage and derived conversion artifacts.
2. Validate load/checksum/compatibility in isolated runtime and pin sessions to releases.
3. Implement atomic approved serving pointer and rollback without changing data.

**Acceptance cases**

**AT-0802-1 [integration].** Given an adapter is paired with the wrong base/tokenizer, when serving is requested, then compatibility validation rejects it.

**AT-0802-2 [integration].** Given a promoted model and old running session, when new session starts, then old session stays pinned; new uses approved release.

**AT-0802-3 [integration].** Given rollback is requested, when serving pointer changes, then known-good model restores without schema/data rollback.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0803 — Implement independent model evaluation and promotion gate

**Owner:** evaluation  
**Prerequisites:** CS-0802, CS-0604  
**Write scope:** `workers/training/evaluation/`; `services/studio-api/src/studio/domain/learning/promotion.py`; `apps/studio-web/src/features/learning/evaluations/`  
**Handoff sections:** 18  
**External inputs:** U14  
**Optional integration:** No

**Implementation order**

1. Run matched base-versus-adapted comparisons with frozen tools/evidence/budgets.
2. Check safety/privacy regressions, scientific thresholds and subgroup/uncertainty reports.
3. Require authorized human release decision and label unknown thresholds as blockers.

**Acceptance cases**

**AT-0803-1 [evaluation].** Given training loss improves but held-out performance worsens, when promotion is attempted, then promotion fails.

**AT-0803-2 [security].** Given agent tries accessing the evaluation labels, when its tools run, then hidden labels remain inaccessible.

**AT-0803-3 [evaluation].** Given real scientific acceptance thresholds unknown, when model card is reviewed, then no blanket improved-chemistry claim is permitted.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

# P09 — Research RL and molecular design

## CS-0901 — Build bounded research RL environment and rewards

**Owner:** rl  
**Prerequisites:** CS-0803, CS-0403  
**Write scope:** `workers/training/rl/environment/`; `workers/training/rl/rewards/`  
**Handoff sections:** 19  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Implement reset/step/terminate with approved typed tools, replay provenance and hard budgets.
2. Separate gate eligibility, component rewards and independent hidden evaluation.
3. Build deliberate adversarial reward-hacking policies and denied-action tests.

**Acceptance cases**

**AT-0901-1 [evaluation].** Given policy repeats cheap validity calls or always abstains, when reward suite runs, then it cannot pass intended task completion/evaluation.

**AT-0901-2 [security].** Given policy attempts a physical experiment or export, when environment step executes, then no physical execution or unauthorized egress occurs.

**AT-0901-3 [unit].** Given an unmatched replay action, when environment steps, then explicit unavailable result is returned, not invented oracle output.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0902 — Integrate actual RL trainer behind release gates

**Owner:** rl  
**Prerequisites:** CS-0901  
**Write scope:** `workers/training/rl/trainer/`; `tests/training/rl/`  
**Handoff sections:** 19  
**External inputs:** U08, U13, U14  
**Optional integration:** No

**Implementation order**

1. Verify pinned TRL/environment API and select an appropriate supported algorithm.
2. Run bounded synthetic actual training and preserve reward components/checkpoints/resources.
3. Compare against supervised baseline using untouched independent evaluation.

**Acceptance cases**

**AT-0902-1 [training].** Given compatible approved runtime, when tiny rl smoke executes, then actual optimizer/checkpoint update and cancel/resume evidence exist.

**AT-0902-2 [evaluation].** Given training reward rises without independent gain, when release gate evaluates, then promotion is rejected.

**AT-0902-3 [security].** Given gpu/compute envelope is exhausted, when rollouts request more capacity, then budget stops work without cloud fallback.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-0903 — Add approved molecular design and retrosynthesis adapters

**Owner:** chemistry  
**Prerequisites:** CS-0901, CS-0701  
**Write scope:** `packages/engine-adapters/reinvent/`; `packages/engine-adapters/aizynthfinder/`  
**Handoff sections:** 16, 19  
**External inputs:** U13  
**Optional integration:** Yes; do not block core on live prerequisites

**Implementation order**

1. Validate licenses, pretrained models and supported small-molecule input kinds.
2. Integrate candidate/route outputs with structural/gate/evidence checks.
3. Keep synthesis plans as hypotheses requiring human review; no automatic execution.

**Acceptance cases**

**AT-0903-1 [engine].** Given supported benign target and configured engine, when design/route search runs, then output is labeled proposed with version/stock/model provenance.

**AT-0903-2 [integration].** Given a formulation or unknown polymer is supplied, when small-molecule tool is requested, then unsupported input is rejected.

**AT-0903-3 [security].** Given a route reaches purchasable precursors, when agent requests lab execution, then independent plan approval is still required.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

# P10 — Protected cloud fallback

## CS-1001 — Implement local-infeasibility and fallback decision reports

**Owner:** runtime  
**Prerequisites:** CS-0803, CS-0402  
**Write scope:** `services/studio-api/src/studio/domain/runs/feasibility.py`; `apps/studio-web/src/features/compute/fallback/`  
**Handoff sections:** 20  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Evaluate compatible local configurations with bounded estimates/probes and declared uncertainty.
2. Record why approved local execution cannot proceed; do not equate slower with impossible.
3. Create an export proposal only, with no transfer or spending side effect.

**Acceptance cases**

**AT-1001-1 [unit].** Given local job is feasible but cloud would be faster, when fallback is requested, then policy does not authorize cloud automatically.

**AT-1001-2 [integration].** Given all approved compatible configurations fail feasibility, when user opens fallback, then evidence report exists and export remains unapproved.

**AT-1001-3 [security].** Given no cloud budget/account exists, when fallback processing runs, then no external job or spend occurs.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-1002 — Build minimal transformed payload and disclosure review

**Owner:** privacy  
**Prerequisites:** CS-1001, CS-0601, CS-0305  
**Write scope:** `services/studio-api/src/studio/domain/learning/exports/transform.py`; `apps/studio-web/src/features/privacy/export-review/`  
**Handoff sections:** 20, 21  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Select minimum permitted records/fields and version explicit transformations.
2. Keep alias mapping local while scanning remaining ratios/structures/free text/metadata/derived values.
3. Display exact payload and residual-risk report; preserve classification unless reviewed change.

**Acceptance cases**

**AT-1002-1 [security].** Given names are aliased but ratios/process remain, when export scanner/reviewer opens payload, then it is not labeled anonymous or safe automatically.

**AT-1002-2 [security].** Given a hidden sensitive field in metadata/free text, when transformation runs, then it is flagged or excluded and remains reviewable.

**AT-1002-3 [integration].** Given transformation version changes, when approval is reused, then digest mismatch invalidates the approval.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-1003 — Implement approved broker, revocation and receipts

**Owner:** privacy  
**Prerequisites:** CS-1002, CS-0105  
**Write scope:** `infra/cloud/broker/`; `services/studio-api/src/studio/domain/learning/exports/broker.py`  
**Handoff sections:** 20  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Bind approval to exact payload/provider/account/region/environment/limits/expiry.
2. Enforce outbound policy in one broker; support dry-run, cancel, reconcile and deletion receipts.
3. Treat returned checkpoints/logs as confidential and untrusted until locally validated.

**Acceptance cases**

**AT-1003-1 [security].** Given payload/recipient/expiry differs from approval, when transfer is attempted, then no outbound proprietary bytes are emitted.

**AT-1003-2 [security].** Given an export is revoked during execution, when broker cancels/reconciles, then already-transferred data is honestly recorded, not claimed unseen.

**AT-1003-3 [integration].** Given provider callback repeats, when receipt is processed, then one consistent external job/artifact lineage is recorded.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-1004 — Implement one owner-approved confidential cloud adapter

**Owner:** cloud  
**Prerequisites:** CS-1003  
**Write scope:** `infra/cloud/providers/`; `docs/operations/cloud-security.md`  
**Handoff sections:** 20  
**External inputs:** U08, U09, U11  
**Optional integration:** Yes; do not block core on live prerequisites

**Implementation order**

1. Obtain explicit provider/region/security approval before creating infrastructure.
2. Verify actual attestation/key-release/GPU/backend/network/retention behavior where applicable.
3. Run synthetic end-to-end submission/return/cancel/delete tests and document residual risks.

**Acceptance cases**

**AT-1004-1 [security].** Given attestation is missing/wrong for approved environment, when key release is requested, then release fails closed.

**AT-1004-2 [integration].** Given only synthetic approved data is used, when live provider smoke executes, then job receipts/artifacts/cancellation/deletion evidence are recorded.

**AT-1004-3 [audit].** Given no provider/account approval is supplied, when feature status is reported, then it remains not_configured, not falsely implemented-live.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

# P11 — Release hardening

## CS-1101 — Complete security and privacy regression review

**Owner:** security  
**Prerequisites:** CS-0505, CS-1003, CS-0803  
**Write scope:** `tests/security/`; `docs/execution/security/`  
**Handoff sections:** 21, 25, 27  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Test scopes, injection, loaders, loopback origin, artifact access, workers, logs and egress.
2. Test revocation impact across retrieval/datasets/models/backups and permissions.
3. Record residual threats and block release on critical control failures.

**Acceptance cases**

**AT-1101-1 [security].** Given malicious document and cross-scope ids, when attack suite runs, then policy/server deny unauthorized actions and exposure.

**AT-1101-2 [security].** Given sensitive source revoked while cached, when all affected surfaces are exercised, then revocation/lineage handling is consistent.

**AT-1101-3 [audit].** Given a required control is unavailable on platform, when release review runs, then unavailable protection is disclosed and relevant capability blocked.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-1102 — Verify upgrades, recovery and data lifecycle

**Owner:** operations  
**Prerequisites:** CS-0505, CS-1003, CS-0802  
**Write scope:** `tests/integration/migrations/`; `docs/operations/recovery.md`; `infra/local/`  
**Handoff sections:** 21, 26  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Test populated upgrades and expand/migrate/contract compatibility.
2. Exercise restore of DB/artifacts/keys/model pointers and resumable backfills.
3. Document retention/deletion limits and avoid destructive rollback assumptions.

**Acceptance cases**

**AT-1102-1 [integration].** Given populated previous schema with immutable evidence, when upgrade runs, then references, hashes and permissions remain valid.

**AT-1102-2 [integration].** Given migration/backfill interrupted, when operation resumes, then no duplicate or silently rewritten scientific record occurs.

**AT-1102-3 [integration].** Given a fresh machine restores backup, when integrity checks run, then required keys/artifacts/models and scopes are validated or exact missing items reported.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-1103 — Measure performance and finish responsive accessibility

**Owner:** frontend  
**Prerequisites:** CS-0504, CS-0603, CS-0803  
**Write scope:** `tests/e2e/`; `tests/performance/`; `apps/studio-web/src/`; `docs/execution/benchmarks/`  
**Handoff sections:** 22, 23  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Benchmark recorded synthetic dataset/machine with heavy worker contention.
2. Verify pagination/streaming/import backpressure and command budgets.
3. Exercise desktop/small-screen/themes/keyboard/reduced-motion states; fix shared components first.

**Acceptance cases**

**AT-1103-1 [performance].** Given recorded hardware and fixture scale, when heavy job runs with normal ui activity, then measured API/UI performance is reported against targets.

**AT-1103-2 [e2e].** Given keyboard and narrow viewport, when critical review journeys execute, then no inaccessible fields or hidden required conditions.

**AT-1103-3 [integration].** Given ci job hangs, when timeout policy applies, then job is terminated within its configured cap.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.

## CS-1104 — Assemble release matrix, runbooks and final handoff

**Owner:** controller  
**Prerequisites:** CS-1101, CS-1102, CS-1103, CS-0902, CS-0701  
**Write scope:** `docs/operations/`; `docs/execution/release/`; `README.md`  
**Handoff sections:** 26, 27, 28  
**External inputs:** None for synthetic implementation  
**Optional integration:** No

**Implementation order**

1. Produce installation/user/admin/scientific/model/privacy/recovery runbooks.
2. Reconcile every ticket with runtime/test evidence and capability status.
3. List outstanding unknowns and optional live integrations honestly; do not equate pilot with full scientific platform.

**Acceptance cases**

**AT-1104-1 [audit].** Given a claimed completed feature, when release reviewer follows evidence, then actual code/test/run artifacts support the claim.

**AT-1104-2 [audit].** Given optional lab/cloud/model prerequisite remains absent, when release matrix is produced, then it is marked blocked/unconfigured without stopping unrelated verified capabilities.

**AT-1104-3 [integration].** Given fresh authorized reference setup, when documented core workflow runs, then a new operator can reproduce the synthetic pilot without hidden steps.

**Completion evidence:** changed files; migration impact; exact commands and results; acceptance IDs with output; real/fixture/blocked capability status; limitations. Do not weaken shared policy or claim skipped execution passed.
