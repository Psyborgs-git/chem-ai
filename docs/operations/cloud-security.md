# Confidential cloud execution — security posture (CS-1004)

Status: **not_configured** — no provider, account, region, or security
model is owner-approved (U08/U09/U11 open). The
`infra/cloud/providers/cloud_providers` adapter skeleton is implemented
and exercised only against an in-process `ConfidentialDouble` with
synthetic approved payloads. Nothing in this document asserts live
capability.

## What the adapter does

The adapter sits between the CS-1003 egress broker and a confidential
backend. Every approved byte traverses the broker's permit gate; the
adapter adds the confidential-execution lifecycle behind it:

1. **Attestation gate (fails closed, AT-1004-1).** Before any key
   release or payload handoff the adapter fetches the provider's
   attestation document and verifies it against the
   `ApprovedEnvironment` — identity (provider/account/region/
   environment), TEE measurement, pinned image/model digests, firmware,
   GPU confidential coverage, network isolation, operator access,
   telemetry/content-logging disabled, ephemeral-credential and
   private-artifact support, signature integrity, expiry windows. Every
   check is independent and reported; any single failure refuses —
   including *absent* evidence (e.g. a provider that does not report
   GPU coverage fails closed rather than passing).
2. **Ephemeral key release.** Only after a verified attestation, and
   re-verified inline on every release — a caller-supplied verdict is
   never trusted. Tickets are ephemeral and TTL-capped by the approved
   `max_access_ttl_seconds`.
3. **Confidential job lifecycle.** Submit / status / cancel / delete
   delegate to the backend; the broker still records attempts, lineage,
   and callback convergence. Job termination and storage deletion are
   reconciled via a post-delete storage probe (`retained_bytes`), never
   assumed clean.
4. **Output import.** Artifacts import marked `confidential` +
   `trusted=false` + `validated=false` — the domain layer marks them
   usable only after validation against the approved manifest.
   Non-private or over-TTL artifacts are refused at import.
5. **Provenance gate.** A synthetic-only environment refuses
   `approved_real` payloads — the honest state of this deployment.

## Provider-observable surface

Even in a correctly attested environment the provider can still
observe:

- **Job metadata** — job id, job kind, job reference, classification.
- **Timing** — submission time, run duration, callback sequence,
  cancellation and deletion times.
- **Payload and artifact sizes** — bytes in, artifact count and bytes
  out (sizes leak shape even when content is protected).
- **Network endpoints** — the endpoints the environment dials for
  artifact/storage access.
- **Key-release requests** — frequency and scope of ephemeral key
  requests.

The adapter records this surface per job (`ProviderObservation`) so the
audit trail states plainly what was visible. Content secrecy is **not**
claimed against a compromised guest or all side channels.

## Residual risks

- **Metadata/timing/size leakage** (above) persists inside any TEE;
  mitigate by coarsening job shapes, batching, and padding only if a
  threat model later requires it.
- **Attestation freshness** — the skeleton verifies each submission,
  but a long-running job can outlive its initial attestation; live
  activation must decide re-attestation cadence.
- **Provider-side compromise** — a compromised host operator or guest
  image outside the measured boundary is out of scope of the
  attestation checks; the measurement pin is only as strong as the
  pinned image.
- **Key-release trust** — the model assumes the provider's key-release
  machinery only issues to the attested environment; verify the real
  KMS/enclave binding during provider evaluation.
- **Side channels** — speculative/physical side channels are not
  covered by this skeleton; do not claim them closed.
- **Synthetic coverage gap** — all evidence is from the in-process
  double. Real-provider behavior (attestation formats, GPU reporting,
  retention semantics) must be verified per-provider before approval.

## What live activation requires

1. Owner approval (`approve_export`) binding a concrete
   `provider/account/region/environment` — closes U08, U09, U11.
2. A `ConfidentialBackend` implementation (`kind="live"`) over the
   provider's real TEE attestation + key-release machinery, with
   verification of its actual attestation/key-release/GPU/network/
   retention behavior (implementation-order step 2 — evidence, not
   docs).
3. `cloud_providers.register(spec, approval, backend)` — registration
   refuses missing/expired/wrong-capability/wrong-subject approvals —
   then the adapter added to `cloud_broker.providers.PROVIDERS` under
   the approved provider name. The broker path remains the only egress.
4. The `ApprovedEnvironment` spec filled with the provider's *verified*
   attestation values (measurement, image/model digests, GPU coverage,
   network/operator posture, TTL caps) — never assumed.

Until then `confidential_capability()` reports `not_configured` and the
surface is inert.
