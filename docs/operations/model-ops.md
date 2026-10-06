# Runbook — engine installation/benchmark and model operations

Audience: owner / `manage_models` holder. Everything here is optional —
the core pilot works without any of it (`installation.md` §9). Every
lane fails closed and reports `ENGINE_UNAVAILABLE`/`unavailable` rather
than faking capability when its prerequisites are absent (AT-1104-2).

## 1. How engines run (§13.3)

Container profile `restricted.json` (`infra/local/worker-profiles/`):
`--network none`, read-only rootfs, non-root, bounded resources,
process-tree kill. The subprocess profile `development-reduced.json`
does **not** deny network egress and says so — runs requiring network
denial are blocked by policy, never run unprotected (residual R1).

## 2. Engine images — build and smoke

| Lane | Image | Build (verified commands) | Size |
|---|---|---|---|
| RDKit descriptors | `chem-studio-rdkit:2026.3.6` | `docker buildx build --platform linux/amd64 -t chem-studio-rdkit:2026.3.6 infra/images/rdkit` | — |
| Local inference | `ghcr.io/ggml-org/llama.cpp:server` + volume `chem-models` + pinned `gemma-2b-it` GGUF (sha256-verified, copied from a local store — **no automatic downloads**, U13) | `docker pull ghcr.io/ggml-org/llama.cpp:server` | — |
| BayBE optimization | `chem-studio-baybe:0.15.0-v1` | `docker build -f workers/optimization/Dockerfile -t chem-studio-baybe:0.15.0-v1 .` | ~1.76 GB |
| QCEngine/xtb | `chem-studio-qcengine:0.51.0-v1` | `docker build -f workers/chemistry/quantum/Dockerfile -t chem-studio-qcengine:0.51.0-v1 .` | — |
| Materials (thermo/UNIFAC) | `chem-studio-materials:0.6.1-v1` | `docker build -f workers/chemistry/materials/Dockerfile -t chem-studio-materials:0.6.1-v1 .` | — |
| Molecular design (REINVENT) | `chem-studio-reinvent:4.8-v1` | `docker build -f workers/chemistry/design/Dockerfile -t chem-studio-reinvent:4.8-v1 .` | — |
| Retrosynthesis (AiZynthFinder) | `chem-studio-aizynthfinder:4.4.1-v1` | `docker build -f workers/chemistry/synthesis/Dockerfile -t chem-studio-aizynthfinder:4.4.1-v1 .` | ≥8 GiB container envelope — stock+ONNX OOMs at 4 GiB (exit 137) |
| Chemprop property models | `chem-studio-chemprop:2.3.1-v1` | `docker build -f workers/optimization/property_models/chemprop/Dockerfile -t chem-studio-chemprop:2.3.1-v1 .` | ~2.25 GB |
| Model loader (registry) | `chem-studio-model-load:0.1.0` | `docker build -f workers/inference/model_loading/Dockerfile -t chem-studio-model-load:0.1.0 .` | — |
| SFT trainer | `chem-studio-sft:0.1.0-v5` | `docker build -f workers/training/sft/Dockerfile -t chem-studio-sft:0.1.0-v5 .` | — |
| RL trainer | `chem-studio-rl:0.1.0-v1` | `docker build -f workers/training/rl/trainer/Dockerfile -t chem-studio-rl:0.1.0-v1 .` | — |

- **Verify:** `make test-engines` — exits 2 with `UNAVAILABLE:` + the
  exact build command when images are absent (honest by design).
  With images present it runs `pytest -m engine` against the real
  containers.
- AiZynthFinder note: figshare model downloads use the canonical CDN
  (`ndownloader.figshare.com/files/<id>` — `figshare.com/ndownloader`
  is AWS-WAF challenged and returns 0 bytes). rdkit-based images need
  `libxrender1 libxext6` on slim bases.
- Restart the API with the matching `STUDIO_PROFILE_*` flags
  (`installation.md` §4) — profile off ⇒ commands fail closed.

## 3. Model registry (CS-0802)

- Task tab **models**: `learningModelReleaseRegisterMutation` registers
  a release (adapter + artifact lineage); `…ValidateMutation` runs the
  isolated load in `chem-studio-model-load` (load happens in the pinned
  container, never in the API process);
  `…PromoteMutation`/`…ApproveMutation`/`…RollbackMutation` manage the
  serving pointer — atomic pointer flip, session pins
  (`learningSessionModelBindMutation`) keep existing sessions on their
  release until rebound.
- Releases flow `registered → validated → promoted` (superseded on
  rollback); `serving_chain` integrity is part of `recovery_check`.

## 4. Training (CS-0801 SFT, CS-0901/0902 RL)

- Tab **datasets** (`learningDataset*`) → snapshot +
  leakage-safe splits (group keys `formula:`/`batch:`/`dedup:`/`doc:`/
  `sample:`); tab **training** (`learningTrainingRun*`) → create →
  submit (human approval; agent principals cannot approve) → queue →
  execute → transition. Checkpoint save/reload round-trips are
  identity-verified; cancel produces `incomplete_run` (usable=false),
  never a failed-pretending-success.
- RL: typed-action environment, closed tool catalog, replay provenance,
  hard budgets — budget exhaustion stops work as `budget_exhausted`;
  there is **no** cloud fallback path (`test_no_cloud_fallback_path`).
  Reward promotion routes through the CS-0803 gate — training reward
  rising without independent eval gain → promotion REJECTED.
- `make train-smoke` / `make eval-smoke`: BLOCKED without the training
  extra + hardware (U08/U13); fixture evidence is `fixture_only`
  `not_validated` always.

## 5. Evaluation and promotion gate (CS-0803)

- Tab **evaluations** (`learningEvaluation*`): suite create → freeze →
  hidden labels (double gate: `read_eval_labels` capability +
  `kind=service` principal — forged grants stripped at context load)
  → run. Promotion requires the matched baseline + scientific gates;
  final release is human (`approve_model`).

## Failure symptoms

| Symptom | Cause | Recovery |
|---|---|---|
| `ENGINE_UNAVAILABLE` | image absent | build per §2 table; tests skip honestly rather than pass falsely |
| `profile_unavailable` typed fail | backend missing a required contract control | use the container profile (subprocess can't deny network) |
| exit 137 mid-run | container memory envelope | AiZynthFinder needs ~8 GiB; raise `--memory` |
| promotion rejected despite reward gain | independent eval flat/regressed | intended gate — inspect component rewards, never bypass |

## Privacy concerns

- Model artifacts and checkpoints live in the vault; exports route only
  through the approved broker (`privacy.md`).
- A 2B fixture model is not a validated chemistry assistant — treat
  every turn as fixture output.

## Evidence location

`docs/execution/tickets/CS-0404.md`, `CS-0405.md`, `CS-0603.md`,
`CS-0604.md`, `CS-0701…CS-0703.md`, `CS-0801…CS-0803.md`,
`CS-0901…CS-0903.md`.
