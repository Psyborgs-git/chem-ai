# Research inference providers

## Private Agent sidebar

The app-wide Agent sidebar has owner-private conversations and durable runs.
Its workspace API is `/api/agent-workspace`; the older task Research panel
continues to use the GraphQL turn flow described below. Both use the existing
configured provider connection and Keychain credential store.

One provider can have several enabled model entries, each assigned planner,
researcher, extractor, or reviewer roles. Assigning a role moves that assignment
from another model on the same provider. Discovery lists models returned by the
endpoint; it does not silently enable them or assert tool compatibility.
Consultations can use another enabled model on an authorized provider.

Private learned models use `localModelId` and an owner-authorized local
inference subprocess. Selecting a candidate for a run does not change an
owner's active model or create a workspace provider. The existing llama.cpp
runtime remains the fallback when neither kind of model is selected.

Remote private-data disclosure is saved per owner, provider destination, and
provider revision. A changed destination or revision requires a new disclosure
decision. Originating workspace artifact export restrictions remain enforced
for every HTTP provider, including loopback endpoints that might forward
requests. Direct local model execution can use authorized private content
without transferring it to an HTTP provider.

Runs checkpoint after each model/tool step, expose persisted tool events to
polling clients, and use bounded worker leases for crash recovery. Closing the
sidebar or browser leaves the backend run intact. The backend process must
remain running; stopping it suspends work until restart and lease recovery.
Cancellation preserves completed notes, retained sources and training job
checkpoints. Training jobs have their own cancellation controls; cancelling an
agent run stops further agent steps.

Autopilot is off initially. Balanced defaults are four hours per owner per UTC
day, 100 fetched documents per day, one concurrent training/evaluation job,
and zero paid-provider spend. Owners can edit these limits. Paid autopilot
requires configured model token prices; the worker reserves the next request's
maximum estimated cost before sending it. Unreported usage retains that
conservative charge. Scheduled goals persist on private threads, default to a
24-hour cadence when enabled, and queue fresh runs using current memory.
Turning autopilot off prevents scheduling and stops active autopilot runs at
their next checkpoint.

Notes, recipes, formulae, source copies and sourced research memory use the
private Library. Notebook AI/training opt-outs and current source rights are
checked again at use. Edits and deletions invalidate checkpointed context.
Evidence snippets actually returned by tools retain their referenced source
artifacts in private research copies, up to 20 per operation. Original bytes,
readable text when permitted, citation metadata, SHA-256 and per-use rights are
preserved. Restricted or oversized copies report omissions without changing
the protected original. Revocation applies to retained copies too.

`GET /api/agent-workspace/tools` exposes the typed tool catalog. It covers
private notes and memory, scholarly/web resource discovery and retention,
custom datasets, local model assets and training/evaluation jobs, real SMILES
calculations, and workbench project/task/material/formulation/lab operations.
Scientific approvals, model activation/promotion, credential settings and
arbitrary shell or GraphQL execution are outside this catalog.

The Providers screen saves workspace-scoped OpenAI or OpenAI-compatible
configurations using Chat Completions or Responses. Set the endpoint's API base
URL (usually ending in `/v1`), exact model identifier, API style, declared tool
support, and enabled state. No protocol or cloud-provider fallback is selected
automatically. Each child model can inherit the provider's API style or select
its own, allowing both protocols under one connection and credential.

Human users with `administer_workspace` can create, edit, test and delete
providers. Authorized workspace readers see enabled, nonsecret metadata.
Research turns additionally require task editing permission. A provider is
chosen explicitly for each turn; an agent or service principal cannot grant
itself permission to send task data to a configured endpoint.

## Credentials and uncertain retries

API keys are write-only and stored in the macOS login Keychain through
Security.framework. They are never artifact blobs, database columns, browser
storage, process arguments, environment variables, audit payloads, or returned
GraphQL fields. There is no plaintext fallback on unsupported platforms or a
locked/unavailable Keychain. Local providers can be configured without a key.
Keys must be 8–8192 printable ASCII characters, without whitespace or controls.

An empty key edit retains the saved key. Removal is explicit. Changing any
normalized endpoint URL or provider kind while keeping a saved key is rejected;
replace or remove the key before changing its destination.

Save retries use the actor and `clientMutationId`. The database stores a digest
of nonsecret settings and whether a key was supplied, with opaque references.
It stores no key-derived verifier. A keyed retry uses a constant-time comparison
against the still-active Keychain item. If the provider changed in the meantime,
reload before retrying. A retry with different settings or a different key is
rejected.

PostgreSQL and Keychain cannot share a transaction. Opaque credential intents
are committed before key creation. Failed metadata writes compensate by
deleting the new item; failed cleanup remains a durable retired intent. If the
screen reports pending cleanup, unlock Keychain and choose **Retry key cleanup**.
Unlocking alone does not run deletion. An explicit retry also cleans pending
intents older than one hour left by an interrupted process. It never deletes an
active provider credential.

## What leaves the app

Choosing a provider is separate from enabling its configuration. Each send needs
explicit consent tied to that provider's current revision. A stale selection is
rejected before any network request. Each turn snapshots the chosen model,
endpoint and credential reference and records nonsecret provider provenance in
its session messages and idempotency result.

The selected endpoint receives the current task UUID, title and mode, the
question, bounded previous user messages (at most 12 messages and 12,000
characters), the available function schemas, and results of tools invoked in
this turn. Previous assistant replies, old tool outputs, cancellation messages
and errors are omitted. Sources are retrieved afresh so changed permissions do
not silently carry forward through prior model paraphrases.

For every configured provider, including a loopback endpoint that might forward
requests, evidence search only sends hits whose current artifact and source
chunk both explicitly allow export. Revoked or unpermitted hits are withheld
with an omission count; their text and identifiers are not sent. This does not
grant or change source/export permissions or the separate export broker policy.
Manually typed questions and prior user messages are part of the disclosed
conversation context.

Tools use the existing capability checks and a task-bound closed catalog.
Unknown tools, malformed arguments and cross-task identifiers return recorded
errors. Approval, export, promotion and task closure are outside this catalog.
Results and past conversation are untrusted data, never model instructions.
Provider-declared tool support is also enforced if an unexpected model response
tries to invoke tools while support is disabled.

## Connection test and transport

**Test connection** performs `GET /models` against the saved configuration. It
sends no task context or completion prompt. A successful response means the
endpoint responded; it does not prove that a key was checked, that generation
works, or that function calling is compatible. The result distinguishes a listed
model from an unverified model. Invalid model-list responses fail the probe.

Non-loopback endpoints require HTTPS. Credentials in URLs, query strings,
fragments, nonpublic resolved addresses and path traversal are rejected.
Explicit loopback HTTP is supported. Validated DNS addresses are pinned for the
actual socket while TLS verifies the original hostname. Redirects are never
followed and environment proxies are not used. Response size, socket lifetime,
turn duration, token estimates and tool attempts are bounded. Upstream errors
discard response bodies and headers; known credential echoes are redacted from
successful response values before they can become messages or tool arguments.

The local llama.cpp path remains available when no provider is selected. It
keeps its previous current-question context behavior and does not silently
route to a configured remote provider.

## Verification

- Private workspace ownership, model roles, scheduling, restart checkpoints,
  private local inference plumbing and source revocation replay:
  `services/studio-api/tests/integration/test_agent_workspace.py`.
- Retained source bytes, checksum reuse, Downloads rights metadata and live
  revocation: `services/studio-api/tests/integration/test_retained_artifact_archive.py`.
- Provider lifecycle, scoped access, credential-safe idempotency and cleanup:
  `services/studio-api/tests/integration/test_inference_providers.py`.
- Actual local HTTP, function calls, durable messages and GraphQL consent:
  `services/studio-api/tests/integration/test_inference_provider_http.py` and
  `test_agent_provider_graphql.py`.
- Tool validation/task scope and source permission checks:
  `services/studio-api/tests/unit/test_agent_tool_registry.py` and provider HTTP
  integration tests.
- Unsupported secure storage:
  `services/studio-api/tests/unit/test_inference_secret_store.py`.

Responses requests set `store: false` and include encrypted reasoning state.
Function calls and results retain their correlated call IDs across tool loops
and private checkpoints. Only opaque encrypted reasoning items are retained;
plaintext reasoning and reasoning summaries do not enter UI messages or logs.
Changes to source permissions, provider revisions or effective model protocol
discard the prior checkpoint context before another outbound model call.

The transport follows the [official OpenAI function calling guide](https://developers.openai.com/api/docs/guides/function-calling)
and [Responses migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses).
Local mock providers verify protocol and application behavior; they are not
evidence of any hosted model's scientific accuracy or account access.
