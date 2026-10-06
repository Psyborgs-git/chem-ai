# Pilot gate report — Chemistry Studio

Generated: 2026-10-05 10:41 UTC by `infra/local/pilot_gate.py` (CS-0505, AT-0505-3).

**Software status ≠ scientific validation.** Every workflow executed
to date runs on synthetic fixture data. No entry below asserts
real-world chemical validity; `scientific` is `not_validated` for all
scientific capabilities even when the software path is live.

| Capability | Software status | Evidence | Scientific status | Limitations |
|---|---|---|---|---|
| PostgreSQL persistence | live | compose container `chem-studio-postgres` (loopback :54329) | n/a — infrastructure | single-host; no replication |
| Artifact vault | live | filesystem vault under `STUDIO_VAULT_ROOT`; checksum-verified blobs | n/a — infrastructure | no at-rest encryption in app; relies on OS volume encryption |
| Deterministic verification | live | CS-0404 verifier; contract-bound deterministic checks | not_validated | covers whitelisted check kinds only |
| RDKit descriptors | live (container) | `docker image inspect chem-studio-rdkit:2026.3.6` present | not_validated | linux/amd64 container path; native rdkit optional |
| Local inference (llama.cpp) | live (container) | `ghcr.io/ggml-org/llama.cpp:server` + volume `chem-models` present | not_validated | 2B fixture model; not a validated chemistry assistant |
| Lab executions | live (manual-first) | CS-0501/0502 plans, executions, measurements, review | not_validated | no equipment control; all execution is human-performed |
| Task closeout evaluator | live | CS-0503 gate-first evaluator; server-derived closure packets | not_validated | fixture-only evidence possible; scientific status separate |
| Backup / restore | live | `make backup-test`; manifest + checksum verification | n/a — operations | no off-site rotation; SSD secure-erasure not promised |
| BayBE optimization | blocked | not implemented (P06, dependency-gated) | not_validated | — |
| Property models / training | blocked | not implemented (P06+, U08/U13) | not_validated | — |
| RL research decisions | blocked | not implemented (§19 preconditions unmet) | not_validated | — |
| Cloud fallback | blocked | no cloud adapter; explicit human approval required (§20.2) | not_validated | — |
| Equipment / instrument control | blocked | no adapter by design (manual-first pilot) | not_validated | — |
| ELN bridge (eLabFTW) | fixture | CS-0506 adapter verified vs fixtures (export + review-gated import); connector off by default | not_validated | live sync deferred (U16 decision); no instance/credentials provisioned |

## Privacy posture (verified)

- Bind host `127.0.0.1`; allowed origins loopback-only (settings.py).
- No outbound client imports in `services/studio-api/src`
  (`tests/integration/recovery/no_egress_check.py` — static scan +
  socket guard).
- Session tokens: opaque, sha256-hashed at rest (`auth_sessions`).
- Vault storage keys opaque; blobs never served from outside vault root.

## Honest gaps

- No at-rest app-level encryption — OS volume encryption assumed (§21.3).
- No separate key store exists; auth material is inside the DB dump.
- LAN/team access remains disabled (no TLS + real identity management).
- Retention schedule is a configuration placeholder, not a legal claim.
