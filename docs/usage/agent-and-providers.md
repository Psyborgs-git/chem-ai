# Agent and AI providers

The header's **Agent** opens owner-private conversations that can use research, notebook, dataset and calculation tools. The task's **Research** panel is a separate task-bound session workflow. Both can use configured provider connections, but their conversation history and disclosure controls differ.

## Connect a provider

Open **More → Providers** at `/settings/providers`. A human with `administer_workspace` can select **Add provider**, edit a connection, **Test connection**, or remove it. Other authorized readers can inspect nonsecret connection metadata.

Configure the provider kind, API base URL, exact model identifier, **Chat Completions** or **Responses** protocol, declared tool support and enabled state. The API base commonly ends in `/v1`; use the endpoint's actual API base rather than a marketing or chat webpage. Non-loopback destinations require HTTPS. Explicit loopback HTTP supports a local gateway.

API keys are write-only and stored in the macOS login Keychain. The app does not return a key to the browser. Leaving the key blank while editing keeps the existing key; removal is explicit. Changing a keyed destination requires replacing or removing the key first. Unsupported or locked secure storage reports an error instead of storing plaintext.

**Test connection** requests the endpoint's models list. A reachable status confirms that check only. It does not verify generation, paid account access, the selected model's scientific accuracy, or tool calling. No research context is sent by the connection test.

If removal reports pending secure-key cleanup, unlock the login Keychain and select **Retry key cleanup**. Unlocking by itself does not perform cleanup. See [Inference providers](../operations/inference-providers.md) for exact credential and transport behavior.

## Configure models and prices

The Providers page also manages enabled models for each connection. One connection may expose several models with separate availability, protocol, declared tool support, role assignments and token prices. A model can inherit the connection's protocol or choose its own.

Roles include planner, researcher, extractor and reviewer. Assigning a role transfers that assignment from another model on the same provider. A model discovered from the endpoint is not automatically enabled or proven tool-compatible.

Enter token prices before using paid autopilot. This requirement applies to HTTP gateways on loopback too, because a local gateway may forward charged requests. Enter explicit zero prices for a free gateway. Pricing controls accounting; private-content permission controls disclosure.

## Start and revisit a conversation

1. Open **Agent** from the header.
2. Choose an enabled provider/model, a ready private MLX/Transformers model, or the running local runtime.
3. Enter your question and select **Send**. Enter sends; Shift-Enter inserts a newline.
4. Inspect grouped tool activity, results, errors and model identities in the transcript.

**New chat** starts a separate conversation. **History** shows saved chats grouped by time; **Search chats** searches titles and visible messages in your owner's workspace. **Load older chats** and earlier-message controls expose paginated history. Reopening a conversation does not resume charged work on its own.

Unsent message drafts are kept per conversation in the current UI session. Only the selected conversation identifier is persisted locally, scoped to its owner. Sign-out clears identity-scoped UI state.

**Stop** requests that an active run stop after its current checkpoint. The interface distinguishes a stop request from a completed stop. **Resume** is offered for resumable states. Closing the sidebar or browser does not cancel a backend-owned run. The backend process and an awake computer are still required.

## Ask for help using the app

Ask questions such as **How do I save a notebook?** or **Explain a formulation with a simple analogy**. The task and app-wide agents have two read-only documentation tools:

- `search_studio_docs` finds relevant handbook sections.
- `read_studio_doc` reads a section and can continue through longer articles.

The tools read the same manuals as **Help & documentation**. They return article titles, relevant text and links; they do not inspect private research or check the current state of an installation. The agent should cite those links and use separate live-state tools when answering questions about your saved work or a running job.

Selecting a documentation link in chat opens that article inside the Studio and closes the chat panel so it remains readable on a narrow screen. Your saved conversation is still in History. **New to chemistry? Start here** opens the [chemistry basics guide](chemistry-basics.md) without needing a model. Follow the [guided first exercise](guided-first-research.md) for app-only practice.

For a useful teaching answer, name the term you do not know and ask for a familiar analogy, its limits, and one next step in the app. Documentation examples describe software use; they are not laboratory instructions or a guarantee that a generated chemical claim is correct.

## Decide what a provider may receive

Before a private notebook, library item or related context is sent to an external provider, authorize that specific provider under **Agent → Settings**. Permission is bound to the destination and provider revision; changing it requires a renewed decision. Source rights remain enforced even after you allow private disclosure.

The selected model receives your question, the authorized context assembled for the workflow, available tool schemas, and results of tools it invokes. Text you type into the conversation can itself disclose private information. Direct local learned-model execution avoids transferring that context to an HTTP provider.

Notebook **Allow my agent to use this notebook**, notebook training permission, provider disclosure, artifact export rights and scientific approval are different controls. Recheck all relevant controls when a source is withheld. See [Notebooks and editing](notebooks-and-editing.md) and [Privacy](../operations/privacy.md).

## Use task Research deliberately

Within a task, open **Research**, start a session, ask questions and record blocking/open questions. End the session when finished. Later sessions rebuild the task manifest from current decisions, outcomes and evidence.

The task GraphQL turn flow requires explicit send consent for the chosen provider's current revision. Its bounded context includes the task identity/title/mode, the question, recent user messages, tool schemas and currently authorized tool results. Prior assistant replies and old tool outputs are not silently replayed as trusted evidence. Current source permissions are checked again.

Do not confuse private app-wide chat history with shared task session history. A private note or model preview is not automatically a shared task decision.

## Enable bounded autopilot

Autopilot starts off. Under **Agent → Settings**, save limits, then select **Autopilot** in the conversation's mode selector. The balanced defaults are four hours per owner per UTC day, 100 fetched documents per day, one concurrent training/evaluation job and zero paid-provider spend.

Paid autopilot needs a positive saved budget and explicit model token prices. The worker reserves a conservative maximum request cost before sending. Limits apply across owner runs and retries, not independently to every reopened chat. A missing usage report retains the conservative charge.

Use **Continue research over time** to save a research goal and interval. Enabled schedules create fresh bounded runs from current memory; the default cadence is 24 hours. Turning autopilot off prevents future scheduling and stops active autopilot runs at their next checkpoint.

## Continue work after closing the app

On macOS, **Background service → Enable background service** installs an optional LaunchAgent. It can keep the backend working after quitting the desktop UI while the Mac remains awake. Disable it through the same setting. The equivalent commands are documented in [Agentic research](../operations/agentic-research.md).

Without that service, quitting a native app that owns its backend stops that backend. A separately owned matching backend is not stopped by the app. Browser/sidebar closure alone does not stop a backend process.

Agent cancellation stops further agent steps. A training or simulation job already created has its own Stop/cancel control and durable state; inspect that job rather than assuming the agent's stop button cancelled all child work.

## Review the agent's authority

The tool catalog supports research discovery, retained sources, private notes and memory, datasets, learning jobs, real calculations, workbench records and lab drafts. The agent cannot approve its own scientific claims, approve experiment/measurement review, close a task as the human reviewer, activate/promote a model, configure credentials, publish private work or run arbitrary shell/GraphQL commands.

Read a generated conclusion against its cited source and method. A tool result establishes the recorded software behavior within its scope; it does not establish chemical safety, experimental performance or source entailment.
