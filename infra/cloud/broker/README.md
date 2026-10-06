# infra/cloud/broker — the single egress path (CS-1003)

`cloud_broker` is the provider-neutral broker for approved exports
(handoff §20.2, §20.5). It is deliberately small and DB-free: the
studio domain layer (`studio.domain.learning.exports.broker`) resolves
manifests, revalidates approvals and persists lineage; this package
owns the bytes boundary.

- **Binding** — `EgressBroker.transfer` requires the attempted
  transfer's digest to equal the approved `ApprovedBinding` digest and
  the approval digest (payload, provider, account, region,
  environment, limits, expiry — exact equality, never similarity).
- **Single egress** — `EgressGate.emit` is the only route to a
  provider; it re-checks digest, recipient, limits and expiry right at
  the boundary and marks permits single-use. A denied attempt emits
  **zero** proprietary bytes.
- **Honest lifecycle** — `dry_run` (full validation, no contact),
  `cancel`, `reconcile`, `delete` produce real receipts; revoke via
  `revoke_binding` blocks later attempts and `cancel` records
  already-transferred bytes as exposed — never "unseen".
- **Untrusted returns** — callbacks are folded into one lineage
  idempotently (duplicates dropped, reordered events converge,
  artifacts deduped). Returned checkpoints/logs/weights stay
  confidential **and** untrusted until the domain layer validates them
  locally; nothing here publishes to a model hub.

## Providers

`PROVIDERS` is empty by design — production providers report
`not_configured`. The only working implementation is
`ProviderDouble`, an in-process double exercising the real contract
end to end in tests and local runs.
