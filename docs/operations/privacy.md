# Privacy, disclosure, and retention

The Studio is a local-first application, but optional features can make network
requests. Local storage, a loopback URL, and a configured provider do not imply
the same disclosure policy. Review the selected workflow and source rights.

## Private and shared records

Projects/tasks, approved scientific records, and their capability-scoped evidence
are separate from owner-private notebooks, source copies, memory, conversations,
private datasets/models/jobs, and simulations. A project link does not publish a
private notebook, and workspace administration does not widen private author
scope. Notebook AI/training opt-outs and current source permissions are checked
again when content is used.

Source text, tool results, and model output are untrusted research material.
A citation or successful execution does not establish scientific truth. Human
scientific approvals and model activation remain separate decisions.

## Network paths and consent

| Path | What to review |
|---|---|
| Configured HTTP inference provider | Destination, provider revision, selected model/protocol, disclosure consent, and source export rights |
| Direct local model subprocess | Authorized private context and local runtime/files; no HTTP provider transfer is needed |
| Scholarly/chemical/web search | Search terms reach the configured public services or trusted SearXNG instance |
| Source retrieval | Selected public URL is fetched and may expose access metadata to its host |
| Catalog model download | Explicit pinned model repository/revision and license; download uses network access |
| Self-hosted learning worker | Explicit remote execution target and owner-authorized data/model/checkpoint transfers |
| Older cloud science export broker | Separate reviewed payload/recipient/approval manifest; no live science provider is configured by default |

An inference provider, including a loopback endpoint that can forward elsewhere,
requires the applicable consent and rights. Private Agent consent is stored per
owner/destination/revision; task Research turns use explicit revision-bound
consent. A changed destination requires a new decision. Provider connection
testing fetches model metadata and sends no research completion prompt.
See [provider details](inference-providers.md) for exactly what task turns send
and how current source restrictions withhold content.

Keyed providers store secrets in macOS Keychain. There is no plaintext fallback
when secure storage is unavailable. Database/vault backups do not include those
keys. Local training workers receive scrubbed environments; native subprocess
execution does not claim OS-enforced network denial. Restricted container
profiles provide a different, stronger execution boundary.

## Reviewed cloud science export

The older science-compute export workflow creates a feasibility report, prepares
a transformed payload manifest, obtains human disclosure approval, and gates
broker transfer with exact bound recipient/environment/bytes/expiry checks.
A proposal is not a transfer. Revocation stops further transfer but cannot
retract bytes already exposed; cancellation/deletion reconciliation records
what a provider still retains.

The confidential-cloud adapter has only synthetic double-backed verification
and no configured live backend. This status does **not** mean configured
research inference cannot make an authorized outbound request. The provider
connection mechanism and the older science broker are separate. See
[cloud posture](cloud-security.md).

## Revocation and source impact

Revoking a shared source artifact preserves its row/tombstone and records an
impact report. Retrieval excludes its chunks; extracted records are rejected,
claims are superseded, and derived lineage requires review. Historical exposure
records remain. Current rights also govern retained private copies.

Revocation is per artifact: uploading identical bytes as a new artifact is not
an automatic global revocation. Existing trained weights are not unlearned by
revoking a source, forgetting memory, or disabling notebook training. Review
impacted datasets/model use separately.

## Retention and deletion

There is no configured universal age-based retention window or secure erasure
policy. Revocation preserves original bytes and history, so later backups can
still contain revoked sources. Notebook trash/restoration, source deletion,
memory forgetting, grant/session revocation, and model/job lifecycle actions
have their own record-specific semantics.

Human-review Downloads and exported citation files can outlive the protected
source record. External model directories, worker-host outputs, backups, and
copies made outside the Studio require their own retention handling. Removing
a UI item does not securely erase all those copies or undo previous disclosure.

The application does not provide general at-rest application encryption,
cryptographic audit tamper-proofing, or guaranteed SSD/cloud erasure. Protect
the trusted machine and backup storage accordingly. [Backup and restore](backup-restore.md)
explains coverage and [configuration](configuration.md) lists state stores.

## Verify the boundary you changed

Use security tests for shared capabilities and private ownership; provider tests
for consent/transport/redaction; library tests for rights/revocation; worker tests
for artifact and credential boundaries. The older core `no_egress_check.py` and
generated pilot report cover a narrower historical core posture and are not
proof that today's optional research/learning paths cannot use the network.

Do not disable source gates or widen Vite filesystem access to repair research
or documentation issues. Use [troubleshooting](troubleshooting.md) and inspect the
specific denied operation.
