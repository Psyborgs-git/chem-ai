# External ELN bridge (eLabFTW) — ownership and operation

**Status: optional integration, fixture-level only. Live sync is
deferred (U16 decision); no eLabFTW instance URL or credentials were
ever provisioned, configured, or called in this release.**

## 1. Ownership model (handoff §14.3)

Chemistry Studio is the **authoritative system** for its native records:
experiment plans, task contracts, candidate revisions, approvals,
samples, measurements, attachments, audit history. Nothing in this
release syncs those records bidirectionally.

The eLabFTW side — when an operator configures one — may own the
laboratory narrative: the dated, human-readable record of what was
physically done. The bridge's job is explicit *exchange*, not merging:

| Direction | Meaning | Guarantee |
|---|---|---|
| Export (Studio -> ELN) | Assemble + send a snapshot of a Studio record as an eLabFTW entity, carrying studio provenance in `metadata.extra_fields.studio_provenance` | Never updates a remote that drifted — it refuses into `review_required` first |
| Selective import (ELN -> Studio) | Read **one** explicitly selected linked entity and compare it to the recorded baseline (`modified_at` + content `sha256`) | Any drift routes to review; the agreed baseline and local snapshot are never overwritten |
| Bidirectional sync | — | **Does not exist by design.** No auto-sync, no background poller, no silent overwrite in either direction. |

## 2. Enabling (opt-in, off by default)

The adapter is `packages/engine-adapters/elabftw/engine_adapter_elabftw`.
It is not imported by the API, so missing config cannot break startup,
health checks, or any core workflow.

| Env var | Required | Meaning |
|---|---|---|
| `STUDIO_ELN_BASE_URL` | for connectivity | Instance URL, e.g. `https://eln.example.org` |
| `STUDIO_ELN_API_TOKEN` | for connectivity | eLabFTW API key; sent verbatim in the `Authorization` header. Never defaulted, logged, or rendered on any status surface. |
| `STUDIO_ELN_ENABLED` | for connectivity | Explicit enable switch. An endpoint+token without it stays `configured_disabled` and refuses every remote call (`ELN_DISABLED`). |
| `STUDIO_ELN_TIMEOUT_SECONDS` | optional | Per-request timeout (default 10) |
| `STUDIO_ELN_VERIFY_TLS` | optional | `0` disables certificate verification (default on) |

Config states reported by `ElabftwAdapter().capability()`:

- `not_configured` — no URL/token. No account is shown; nothing is
  provisioned or invented.
- `configured_disabled` — endpoint exists but `STUDIO_ELN_ENABLED` is
  off. Every remote operation is refused before any byte leaves.
- `enabled` — remote calls allowed. `connectivity` still reports
  `not_probed`: the capability surface never claims a "connected"
  account it has not verified.

## 3. Link records and conflict handling

Each bridge operation maintains an `ElnLink`: `local_ref` (the Studio
object), `entity_type`/`entity_id` (the eLabFTW record),
`remote_version` + `remote_sha256` (the agreed baseline), the imported
`snapshot`, and `state`:

- `synced` — remote matches the baseline.
- `review_required` — remote drifted. `link.review` records the
  baseline and observed version/hash plus the incoming record for a
  reviewer. Resolution is explicit:
  - `accept_remote` — re-reads the remote *now* and adopts exactly what
    is observed as the new baseline.
  - `keep_local` — keeps Studio's baseline. Does **not** suppress future
    drift detection: a later divergent import re-flags review.
- `stale` — the ELN was unreachable at the last check. The local
  snapshot (imported evidence) is kept and still verified on open;
  `link_status` reports `remote: "unavailable"` — no crash, and never a
  fabricated "connected" state.

A linked record opened while the ELN is down or disabled shows its
local evidence intact and the remote honestly marked
`unavailable`/`disabled`/`not_configured`.

## 4. What is NOT delivered

- No live eLabFTW call has ever been made. `HttpElnTransport` is real
  code (stdlib urllib, documented v2 API: `Authorization: <key>`,
  GET/POST/PATCH under `/api/v2/`), but it is exercised by **no test**
  and is labelled unverified.
- No Studio DB persistence for links yet — `export_state()` serializes
  the registry for a caller to persist; a domain-side storage ticket
  would own that.
- No connector UI exists in `apps/studio-web` (the nav's `/settings`
  target has no route — recorded gap). A future settings surface must
  render `capability()` verbatim.
- No attachments/uploads transfer, no webhooks, no bulk import.

## 5. Path to live (requires a separate decision)

Per the U16 decision, going live needs: (a) a real instance URL +
credentials provisioned by the owner into environment secrets, (b) an
explicit decision on record ownership, sync direction, and conflict
handling, (c) `STUDIO_ELN_ENABLED=1` set deliberately, and (d) live
verification against the real instance — fixture-green is not a live
claim.
