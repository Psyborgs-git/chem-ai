# Agent chat and session history

The agent uses a conversation-first layout with a visible New chat action,
searchable history and a compact composer. A wider chat workspace gives research
answers room to read; the companion sidebar remains available beside app work.

Visible session navigation and compact activity controls follow the patterns in
[VS Code's session interface](https://code.visualstudio.com/docs/agents/run/sessions/manage-sessions).
Searching titles and visible message text follows
[ChatGPT's history search](https://help.openai.com/en/articles/10056348-how-do-i-search-my-chat-history-in-chatgpt).
These are interaction references; Chemistry Studio keeps its own visual tokens.

## Shared controls

The implementation uses the official shadcn `radix-nova` registry components:
buttons, grouped model selectors, inputs, dialogs, tabs, switches, checkboxes,
menus, tooltips and the sidebar-width slider. Tailwind tokens map to Studio's
existing light and dark themes. Portals stay above the companion sidebar,
inactive tab panels remain hidden, and reduced-motion preferences are respected.
The same controls cover local learning, notebooks, the research library and
provider configuration. Decorative animation is unnecessary for these workflows.

## Conversation behavior

- New chat is explicit. Opening an existing session restores its transcript and
  model binding without starting another run.
- The header names the current conversation. Model selection identifies an
  actual configured provider/model; a new chat does not silently select an
  unavailable local runtime or promote a fine-tuned candidate.
- User and assistant messages have distinct readable treatments. Long prompts
  have an expandable preview, preserving the complete stored message.
- A turn's tool calls/results form one collapsed activity group. Technical
  request/response details remain available inside it.
- The composer separates writing, sending and stopping. Settings and automation
  controls stay outside the main conversation flow.
- Scrolling to an older answer is respected while new activity arrives.
- Unsent New chat and contextual Ask drafts use separate in-memory slots. Moving
  between them restores each draft; owner changes and sign-out clear them.

## Durable history and privacy

`GET /api/agent-workspace/threads` accepts `q`, `offset` and `limit`. Search covers
only the current owner's thread titles and visible user/assistant messages.
Tool payloads, system/status messages and other owners' data are excluded from
search previews. Literal percent/underscore/backslash characters are escaped.

Results include title, dates, visible-message count, bounded last-message
preview and latest run status. `nextOffset` makes older sessions discoverable.
Thread messages use a scoped `before` cursor and stable timestamp/ID order, with
the newest page returned chronologically and earlier pages available explicitly.
Overlapping pages retain earlier messages already loaded in the current view.
When background work advances beyond that window and the newest page no longer
overlaps, the view resets to the coherent server page and its earlier cursor so
intervening history remains reachable.

Only a selected thread ID is persisted in browser preferences, under the server's
owner/workspace scope. Transcript content is not cached there. A missing/foreign
selection returns to history; a temporary network error does not erase it.
History selection never starts or resumes model inference automatically.
