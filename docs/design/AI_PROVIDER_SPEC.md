# AI providers and agent workflow verification

## Intent and safety boundary

A researcher can configure an OpenAI-compatible endpoint and choose it for a
research turn. Provider selection is explicit. An unavailable model does not
create a simulated reply, and the existing local model and manual workflow
remain available. Adding a provider does not authorize automatic network calls
from unrelated workflows or change scientific approval and export controls.

Before a provider turn, the interface identifies the endpoint and explains that
the current question, task context, up to 12 recent user messages, and relevant
current-turn tool results may be transmitted, and that the provider may charge
for usage. Prior assistant responses are omitted because source export rights
may have changed since they were generated. Retrieved source chunks are included
only when both the artifact and chunk have export permission. Actual transmission requires the
researcher's selection and confirmation. A connection check communicates with
that endpoint only when the user requests it and reports the exact scope of the
check; reachability is not a measurement of scientific or tool-use accuracy.

API keys are write-only in the interface and never returned in provider
queries. Existing keys are retained when an edited form leaves the new-key
field blank. Provider errors must not echo keys or raw authorization headers.
On this Mac, the system Keychain holds credentials; the application database
stores only configuration and an opaque reference. If the secure credential
store is unavailable, the app reports that fact instead of quietly writing a
plaintext credential to the database, log or web bundle.

## Tool and result contract

The model can request only the registered, schema-described agent tools.
Every request is validated, budgeted and executed through the existing
workspace authorization and domain services. A tool call and its result remain
visible in the session. Invalid arguments, unknown tools, denial, timeouts and
provider failures are recorded honestly, and an agent-generated statement is
not itself measured evidence or approval. Long prior messages can be truncated; prior tool results and whole files are
not automatically attached. A tool response is untrusted data,
not an instruction that changes the tool catalog or authorization.

OpenAI-compatible implementations vary. The integration targets the configured
protocol and reports unsupported provider behavior rather than assuming every
endpoint or model implements every optional feature. Tool execution precision
can be established against known fixtures; scientific accuracy and tool choice
of an arbitrary third-party model require evaluation with that model and data.

## Verification matrix

- Create, edit, select, disable and remove configurations; blank key retains the
  existing key, and invalid/unauthorized requests do not expose or replace it.
- Verify endpoint validation, same-origin/redirect handling and error redaction.
- Use a deterministic local OpenAI-compatible server to verify request shape,
  exact tool names and arguments, multi-call results, and final message handling.
- Exercise unknown tools, malformed JSON and arguments, schema/UUID failures,
  workspace denial, tool failures, budgets and provider/network errors.
- Verify explicit remote consent and absence of calls when no provider is chosen.
- Confirm native app navigation and settings after rebuilding the macOS bundle.

No production API key or paid remote model is required for deterministic tests.

## Protocol reference

The Chat Completions integration follows the documented function-call/message
contract, then validates every requested function against the application's
own schemas. Provider implementations may differ in optional request fields.
See [OpenAI's function-calling guide](https://developers.openai.com/api/docs/guides/function-calling)
and [Chat API reference](https://platform.openai.com/docs/api-reference/chat/create).
