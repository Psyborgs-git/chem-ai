# Agentic research and the private library

Use this guide for current operation. Historical verification is recorded in
`docs/operations/agentic-research-verification.md`; it does not establish the
current machine's provider, hardware, or scientific readiness.

Open **Agent** in the app header to start an owner-private conversation from any
screen. Select an existing provider and one of its models, a private local model,
or a running llama.cpp runtime. Existing provider credentials stay in the secure
credential store. **Providers → Models on each provider** manages additional
models, role assignments, availability, API protocol, and optional token prices.
Responses and Chat Completions can be selected independently per model under the
same connection. Stateless Responses tool loops preserve encrypted protocol state
inside owner-private checkpoints without displaying hidden reasoning.

The agent uses schema-described application tools for research, notebooks,
materials, tasks, calculations, evidence, datasets, learning jobs, and lab drafts.
Tool calls, results, errors, and model identities persist in the conversation.
The agent cannot approve its own scientific claims, publish private work, invent
lab observations, or approve an active-model replacement.

## Private notes and memory

**Notebooks** supports nested folders, Markdown, mathematical formulae, recipe
tables and steps, and validated SMILES previews. Pages autosave using optimistic
revisions; conflicting edits remain recoverable as separate drafts. History and
trash restoration preserve previous revisions. Citations can link retained
sources and source locations.

Notebooks are private to their author, including against workspace-wide
administrator read grants. Agent retrieval and local/self-hosted training are
enabled by default and can be disabled per notebook. Derived transcripts,
memory, datasets, and model outputs retain owner scope. Linking a private note
to a project does not publish it into shared task history.

**Research memory** records source-backed findings, decisions, and open questions.
The agent rebuilds its context from currently authorized sources. Edits,
deletion, AI opt-out, and source-right changes invalidate stale context. Forgetting
a memory prevents its future retrieval; it does not reverse earlier training.

Before an external model receives private context, allow that specific provider
in **Agent → Settings**. Permissions are bound to the provider destination and
revision. Current originating artifact rights still apply to retained copies,
citations, notebook-derived memory, and dataset tool results.

## Retained sources and Downloads

**Research library** discovers scholarly papers through OpenAlex/Crossref,
chemical records through PubChem, and web pages through the app-local SearXNG
service. Remote availability and rate limits are reported as actual failures.

Start the optional web-search service:

```sh
bash infra/local/research-search.sh start
```

It uses a pinned container image on loopback port 8088. Set
`STUDIO_SEARXNG_URL` to use another trusted SearXNG installation. Resource-fetch
URLs themselves cannot access loopback/private addresses or redirect into them.

**Downloads** retains originals, extracted text, citation metadata, and readable
review copies. It supports uploaded files and sources cited from existing
evidence artifacts. The default review folder is
`~/Downloads/Chemistry Studio/<workspace>/<owner>/`; `STUDIO_RESEARCH_DOWNLOADS_ROOT`
changes its root. The protected source copies remain under the artifact vault.
Use **Open in Finder**, **Open original**, or citation JSON/BibTeX exports for
human review.

Refreshing a URL keeps earlier source versions. Unavailable full text is not
represented as a downloaded paper. Files are never automatically evicted for
space; insufficient storage blocks new retention with a useful error.

## Persistent autopilot

Enable autopilot in **Agent → Settings**, save resource limits, then select
**Autopilot** on a conversation run. The balanced defaults are one concurrent
training job, four hours and 100 documents daily. Paid autopilot inference starts
only after a budget and token prices are configured. Owner totals apply across
runs, not independently to every retry.

For recurring work, save a research goal and interval under **Continue research
over time**. The worker creates a new bounded run when due, retrieves current
memory, and avoids duplicating already scheduled work. Disabling autopilot stops
future scheduled execution. Pause/stop preserves durable checkpoints.

The app backend owns workers independently of open browser tabs. On macOS,
**Background service → Enable background service** optionally installs a
LaunchAgent so work can continue after quitting the desktop UI while the Mac is
awake. It can be removed from the same control. Equivalent commands are:

```sh
bash infra/local/background.sh install
bash infra/local/background.sh status
bash infra/local/background.sh uninstall
```

The service waits for an existing foreground runtime to finish rather than
replacing it. It does not keep a sleeping or powered-off computer running.

## Local and self-hosted learning

**Local learning** imports custom data, validates rows, freezes grouped dataset
partitions, manages model assets, queues jobs, and shows recorded results.
Assistant adaptation, SMILES property prediction, and molecular generation use
separate data contracts and metrics. Machine validation is distinct from
scientific review; extracted, computed, and synthetic rows retain their origin.

See [learning-workspace.md](learning-workspace.md) for isolated Mac runtimes,
CUDA/self-hosted workers, algorithms, cancellation/resume, and inference-backed
evaluation. A candidate can be previewed or selected for a private agent run.
Changing the active private model requires human approval linked to a completed
independent evaluation for that exact candidate.

## Updating an existing installation

Back up first, apply the current migration head, rebuild the web or native app,
and restart its API process with the existing database and vault configuration:

```sh
.venv/bin/alembic -c services/studio-api/migrations/alembic.ini upgrade head
pnpm build:web
```

Provider rows migrate their previous model into an initial child model. Existing
tasks, shared research sessions, and the older reviewed model registry remain
available. New private GraphQL roots are `privateLibrary`, `privateAgent`, and
`privateLearning`; their operations call the same services as the authenticated
`/api/library`, `/api/agent-workspace`, and `/api/learning-workspace` interfaces.

## Maintenance and recovery

A conversation cancellation stops further agent steps; learning and simulation
jobs have their own cancellation controls. Check those jobs separately before
stopping the backend or taking a consistent snapshot. Review the
[stored-state inventory](configuration.md) and [backup procedure](backup-restore.md)
for protected originals, human-review Downloads, private checkpoints/models, and
provider keys. The background service must be deliberately stopped during
maintenance so it cannot restart a writer.
