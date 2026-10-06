# Unknowns register — release state (CS-1104)

Source of truth: `docs/chemistry-studio/planning/unknowns.json`
(U01–U16). Status reflects main @ `d778c3a` + this ticket. An unknown
marked **open** blocks the listed surface — the codepath exists where
noted and reports `blocked`/`not_configured` honestly (AT-1104-2);
nothing waits silently.

| ID | Question | Status | What's implemented meanwhile | Still blocking |
|---|---|---|---|---|
| U01 | Existing repository/directory | **resolved** | Greenfield confirmed (CS-0001 baseline); repo built from scratch | — |
| U02 | Dataset size, formats, quality | **open** | Quarantined parsers + review workflow (CS-0301/0302); perf measured on synthetic scale (CS-1103) | real import perf, training readiness |
| U03 | Pilot tasks/products and targets | **open** | Contract machinery with exploratory bounds (CS-0201) | scientific acceptance thresholds |
| U04 | Scientists/reviewers, role assignments | **open** | Capability-based approvals; agent ceiling enforced (CS-0501/1101) | experimental release sign-off |
| U05 | Lab equipment, available methods | **open** | Manual-first executions; method as explicit requirement text (CS-0501/0502) | executable protocols, endpoint validation |
| U06 | Experiment capacity/cost/turnaround | **open** | — | campaign planning, physical execution |
| U07 | User count / team deployment | **open** | Single-workspace loopback; service-layer principal provisioning (admin.md) | LAN/team rollout (TLS + identity) |
| U08 | OS/CPU/GPU/RAM/disk for production | **open** | Dev box recorded (CS-1103 benchmark environment); capability detector + hardware probe (CS-1001) | production runtime + training scale |
| U09 | Infrastructure/cloud budgets | **open** | External spend disabled; admission budgets exist (CS-0402) | paid job authorization |
| U10 | Delivery milestones/dates | **open** | Dependency-gated plan executed to completion | calendar commitments |
| U11 | Cloud provider/region/account/security model | **open** | Provider-neutral broker + confidential adapter skeleton verified vs double (CS-1003/1004) | live cloud execution — `confidential_capability() = not_configured` |
| U12 | Data rights, permitted training/export uses | **open** | `rights=unknown` stays out of corpora; disclosure review exists (CS-0303/1002) | dataset freeze, exports of real data |
| U13 | Base model/license/runtime compatibility | **open** | llama.cpp + sha256-pinned 2B GGUF proven the mechanics (CS-0405) | fine-tuning/serving a chosen model |
| U14 | Scientific evaluation/replication thresholds | **open** | Gate machinery + synthetic thresholds (CS-0602/0803) | model promotion for real science |
| U15 | Retention/recovery/key-management policy | **open** | Tested backup/restore + 12-check integrity + retention inventory (CS-0505/1102) | production retention schedule, key store |
| U16 | Optional ELN (eLabFTW) instance/credentials/ownership | **decided — deferred** | CS-0506 implemented at fixture level (export + selective import, version/hash review gates); core lab workflow is native | live sync — needs explicit instance + credentials + separate ownership/sync-direction decision |

## Optional/live integrations — honest state

| Integration | Status | Note |
|---|---|---|
| eLabFTW ELN | **fixture / live not_configured (U16 decided-deferred)** | CS-0506 adapter + `docs/operations/eln.md`; connector off by default, no instance/credentials provisioned |
| Confidential cloud provider | **not_configured (U08/U09/U11)** | CS-1004 adapter skeleton + attestation gate verified against in-process double; `cloud-security.md` §"live activation" lists the required owner approval + real `ConfidentialBackend` |
| Live model training at scale | **blocked (U08/U13)** | mechanism verified on fixture corpus; no hardware/model selection |
| Instrument control | **blocked by design** | manual-first pilot; no adapter exists or is claimed |
| Team/LAN deployment | **blocked (U07)** | loopback-only cookies + origin policy; needs TLS + identity design |

None of the above block the verified core: records, review, tasks,
contracts, lab workflow, retrieval, closeout, backup/restore, and the
synthetic pilot journeys are all live (see `release-matrix.md` §1–2).
