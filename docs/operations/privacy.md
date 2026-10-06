# Runbook — privacy: export review, source revocation, retention

Audience: owner / `review_export` + `approve_export` holders.
Current posture: **no live cloud provider is configured** (U08/U09/U11
open — `docs/operations/cloud-security.md`); every egress byte in the
verified evidence went through the in-process double only.

## 1. Cloud export review (CS-1001→CS-1004)

Pipeline, all gated:

1. **Infeasibility report** — a run that cannot proceed locally gets a
   `RunFeasibilityReport` (`/compute/fallback/:runId`,
   `fallbackRequestMutation`). It names the missing dimensions —
   it is a report, never an action.
2. **Export proposal** — `exportPrepareMutation` produces an
   `ExportProposal` bound by digest (`bound_inputs`/`bound_digest`);
   the minimal transformed payload (CS-1002) carries a manifest of
   exactly what leaves, reviewed per-field.
3. **Disclosure review** — `/privacy/exports/:proposalId`
   (`exportDecideMutation`): reviewer sees the payload manifest;
   `approve_export` approval binds `provider/account/region/
   environment`, recipient, bytes, expiry — exact-equality checked at
   the gate, not similarity.
4. **Broker execution** (CS-1003): one-shot permits — denied ⇒ the
   provider sees zero bytes; revoke mid-transfer stops further
   transfer while already-sent bytes stay honestly recorded as
   `exposed`; callbacks converge idempotently; cancel/reconcile/
   delete record what the provider still holds.
5. **Confidential environment** (CS-1004): attestation gate fails
   closed on any absent check; `confidential_capability()` reports
   `not_configured` until owner approval + a live `ConfidentialBackend`
   exist — today it does not.

```bash
# verify: provider registry is empty without configuration (executed —
# prints `providers: [] (none configured)`)
uv run python - <<'PY'
import sys
sys.path.insert(0, "infra/cloud/broker")
from cloud_broker.providers import PROVIDERS
print("providers:", list(PROVIDERS) if PROVIDERS else "[] (none configured)")
PY
```

## 2. Source revocation and derived artifacts (CS-0305/CS-1101)

`qualitySourceRevokeMutation` (data-steward level) on a source
artifact triggers the verified cascade:

- source row stays, `review_state='revoked'`; `source_revocations`
  tombstone rows record the impact report;
- chunks leave the retrieval index (index-version bump + fetch-layer
  status filter — revoked content can't be served from cache);
- extracted records → `rejected` (`source_revoked`); proposed/accepted
  claims → `superseded` (still queryable, with provenance);
- derived artifacts → `retention.lineage_review='required'` — suspended
  visibly, not silently deleted;
- historical exposure (`exposedManifestIds`/`exposedPrincipalIds`) is
  **recorded, not erased**.

Honest limits: revocation is per-artifact — re-uploaded identical bytes
are a new artifact and need fresh review (residual R6);
dataset/model-release impact fields are honestly empty where no
registry rows exist (R7).

## 3. Retention posture (CS-1102, recovery.md §4)

There are **no retention-window policies configured** — nothing ages
out on a timer; "deletion" surfaces are soft marks everywhere:

| Surface | Delete does | Backups retain |
|---|---|---|
| artifact revoke | mark + tombstones; index/cache exclusion | everything incl. blob bytes |
| grant/session/principal | `revoked_at`/`disabled_at` | full history |
| workspace purge | `delete_workspace_tree` exists, never wired to requests | n/a |
| vault blob | `remove_blob` primitive, no request-path callers | blobs are never deleted by the app |

Implication: revoke ≠ delete — plan backups accordingly; a real purge
policy needs `recovery_check` extended to expect-absent semantics.

## 4. Periodic privacy verification

```bash
uv run python tests/integration/recovery/no_egress_check.py   # AT-0505-2
uv run python infra/local/pilot_gate.py                        # AT-0505-3
make test-security                                             # CS-1101 suite
```

- `no_egress_check`: static scan of app src + socket guard — expected
  `no_egress_check: OK`. (Whole-repo egress scan incl. `workers/` +
  `infra/` is in `test_cs1101_loaders.py::TestEgressWholeRepo`.)
- `pilot_gate.py` regenerates `docs/operations/pilot-gate.md`.

## Failure symptoms

| Symptom | Cause | Recovery |
|---|---|---|
| proposal exists but transfer never runs | approval absent/expired/mismatched | re-review; permit gate is exact-match, fail-closed |
| revoked content still in a fresh backup | by design — tombstone + bytes retained | document retention expectation; no purge exists |
| `confidential_capability() = not_configured` | no approved provider | expected until §1.5 prerequisites land |

## Evidence location

`docs/execution/tickets/CS-0305.md`, `CS-0505.md`,
`CS-1001…CS-1004.md`, `CS-1101.md`, `CS-1102.md`;
`docs/operations/cloud-security.md`, `backup-restore.md`,
`recovery.md`; residual register
`docs/execution/security/cs1101-residual-threat-register.md`.
