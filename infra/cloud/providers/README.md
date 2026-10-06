# `infra/cloud/providers` — confidential execution adapter (CS-1004)

The provider-neutral adapter that lets approved payloads execute in an
owner-approved confidential cloud environment — without ever moving
egress off the CS-1003 broker.

## Honest state

U08/U09/U11 are open: no provider, account, or security model is
owner-approved. `confidential_capability()` therefore reports
`not_configured`; `cloud_providers.register` refuses to bind an adapter
without a valid `approve_export` approval. The synthetic tests exercise
the real code path against `ConfidentialDouble` — an in-process backend
that honestly labels itself `kind="synthetic"` and can mint attestation
documents it gets right or wrong.

## Layers

```
TransferOrder ──> EgressBroker (approval binding + permit + gate)
                     │  provider.submit(...)
                     ▼
        ConfidentialExecutionAdapter (implements CloudProvider)
                     │  attest → verify (fail closed) → release_key
                     ▼
             ConfidentialBackend (protocol)
                     │
            ┌────────┴─────────┐
     ConfidentialDouble   (a real provider SDK backend — none approved yet)
```

- `types.py` — `ApprovedEnvironment`, `AttestationDocument`,
  `AttestationVerdict`, `KeyRelease*`, `ConfidentialJobSpec`,
  `ImportedArtifact(s)`, `ProviderObservation`, `StorageVerification`.
- `attestation.py` — `verify_attestation`, all-or-nothing checks over
  identity/measurement/pinned digests/GPU coverage/network/operator/
  telemetry/ephemeral/private-artifact claims. Fails closed.
- `adapter.py` — `ConfidentialExecutionAdapter`: attestation → ephemeral
  key release → confidential submit → callbacks → cancel → delete →
  storage probe → confidential/untrusted output import; records the
  provider-observable surface per job.
- `backend.py` — the `ConfidentialBackend` protocol a real provider
  implements.
- `double.py` — `ConfidentialDouble` in-process backend for tests.
- `registry.py` — approval-bound registration + `confidential_capability`.

## What live activation would require

1. Owner approval (`approve_export`) binding a concrete
   `provider/account/region/environment` — closes U08/U09/U11.
2. A `ConfidentialBackend` implementation over the provider's real TEE
   attestation + key-release machinery (`kind="live"`).
3. `cloud_providers.register(spec=..., approval=..., backend=...)`, then
   the adapter added to `cloud_broker.providers.PROVIDERS` under the
   approved provider name — broker path stays the only egress.

See `docs/operations/cloud-security.md` for the provider-observable
surface and residual risks.
