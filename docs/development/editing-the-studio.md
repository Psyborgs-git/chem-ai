# Editing and extending the Studio frontend

The frontend is React/TypeScript with React Router, Relay, Vite and feature-owned UI. Small interaction changes should use the existing components, transport and state patterns so scientific records remain correctly scoped, saved and reviewed.

## Find the owning feature

`apps/studio-web/src/routes/AppRoutes.tsx` owns authentication gating, the shell and top-level routes. `src/components/layout/StudioLayout.tsx` owns workspace destination metadata and shared page/surface primitives. `src/features/tasks/navigation.ts` owns task groups/subviews and URL construction.

Feature directories own their forms, GraphQL operations, CSS and tests. For example, task contracts live under `features/tasks`, notebook editing under `features/notebooks`, providers under `features/providers`, and private learning under `features/learning/LocalLearningPage.tsx`.

Trace the rendered control and its transport before editing prose or behavior. Existing implementation comments and old operation runbooks can describe historical behavior; use current component and service code to confirm a control actually exists.

## Add a route or navigation destination

Add a feature component, lazily import it alongside other feature surfaces in AppRoutes, and register its path inside the authenticated shell unless it is an explicitly approved entry surface. Use the existing loading/error boundary behavior.

For a top-level destination, add it to the appropriate primary/secondary metadata list. The workspace finder and header location derive from the combined destination list. Add an appropriate `StudioIcon` path rather than accepting the generic fallback icon.

For task tools, extend the typed task group/subview metadata and group body together. Preserve the URL pattern `/tasks/:taskId/:group?view=...`. Do not reintroduce hidden local-only tab state that breaks reload/back/deep links. A conditional tool should reflect an actual task object/capability and provide an honest empty/unavailable state.

Update navigation tests when destination counts or labels change, and test direct route entry as well as clicking from the home screen.

## Change a GraphQL-backed feature

Feature queries and mutations live in adjacent `operations.ts` files or component-local `graphql` templates. The compiler reads `packages/contracts/schema.graphql` and writes `src/__generated__/`.

1. If the backend schema changes, implement/export it using [Backend and contracts](backend-and-contracts.md).
2. Edit the feature's operation and requested fields.
3. Run `pnpm relay` and inspect generated changes.
4. Update typed component props/rendering and mutation result handling.
5. Run focused feature tests, typecheck and production build.

Do not hand-edit generated Relay artifacts. Use the returned node/global ID types rather than guessing an entity kind from an opaque string. Resolve server domain errors from the mutation's typed errors; a transport success with domain errors is not a saved record.

## Use the private REST transport

Private workspace features use `workspaceRequest` from `src/relay/network.ts` and helpers in `features/workspace/useWorkspace.ts`. These centralize authenticated relative requests, error handling and owner/session invalidation.

For example, a synthetic note update follows the existing optimistic-revision contract:

```ts
const saved = await workspaceRequest<NotebookPage>(
  `/api/library/pages/${page.id}`,
  {
    method: "PATCH",
    body: JSON.stringify({
      title: "Synthetic solvent-screen notes",
      content: { markdown: "Example only; no measured result." },
      citations: [],
      expectedRevision: page.revision,
    }),
  },
);
```

Use the actual feature's types and fields. Do not add direct cross-origin fetches, browser-stored provider keys or a second authentication client. Multipart uploads use `FormData` and let the browser supply its multipart boundary.

## Preserve save and conflict behavior

Scientific editors show explicit draft/save/review states. Notebook editing adds serialized autosave, generation tracking, owner-scoped session draft recovery and optimistic revision checks. Adopt the pattern appropriate to the feature rather than displaying Saved optimistically before confirmation.

During a save, keep user input stable. If new edits arrive while the request is in flight, the earlier response must not mark the newer text saved. Preserve recoverable drafts on failures/conflicts and show a deliberate recovery path. Disable duplicate submission while pending; keep an idempotency key stable across an uncertain unchanged request.

After confirmed mutations, update normalized returned nodes or deliberately refetch affected connections. A remount alone can replay a stale Relay result; inspect the feature's fetch policy and key. Scope local drafts/history to their owner and clear them on sign-out.

## Keep approvals and privacy visible

Controls may hide unavailable actions, but the backend remains authoritative. Show actual typed capability/validation/conflict errors. Agent proposals must retain human review controls and source provenance. Never turn an accept/review action into an automatic side effect of saving a form.

Notebook Markdown is untrusted. Its renderer disables raw HTML and makes remote images inert links. Do not weaken it to support handbook navigation. Help uses its own wrapper with bundled articles, local search, internal links and heading anchors.

Private notebook AI/training access, provider disclosure and source export rights must remain distinct UI choices. A selected provider or reachable models endpoint is not completion/tool verification or scientific validation.

## Use existing visual and accessibility primitives

Start with tokens and shared atoms/layouts rather than adding a parallel color/spacing system. The app has shared Button, TextField, DecimalField, UnitSelect, InlineFinding, quantity and structured-row controls, plus Radix-based UI components.

Give every form input a visible label and every icon-only control an accessible name. Maintain keyboard submit, Escape/back behavior, focus restoration, pending announcements and readable errors. Respect reduced-motion and light/dark styles. Keep dense technical records behind intentional details while leaving scientific meaning and blockers visible.

For quantities, preserve decimal strings, explicit zero and unknown values; do not coerce a missing value into zero or silently normalize a formulation. See [Materials and candidates](../usage/materials-and-candidates.md).

## Verify the user-visible outcome

Run focused Vitest tests around the meaningful interaction, then the shared checks in [Testing and documentation](testing-and-docs.md). Verify at least the normal action, failed save, unavailable/forbidden state and direct deep link when relevant. For revision edits, test a stale writer and confirmed reload. Update the current handbook with the actual labels and save behavior you shipped.
