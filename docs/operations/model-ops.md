# Engine and model operations

Optional engines and model runtimes are separate from core records. Missing
software, unavailable hardware, or unconfigured profiles must report unavailable
rather than substitute fixture output. The [private learning workspace](learning-workspace.md)
and the older task-scoped registry are distinct systems.

## Choose the correct lane

| Capability | Setup and boundary |
|---|---|
| Native SMILES properties | `engines` extra with native RDKit, or its pinned descriptor image |
| Private assistant/property training | Isolated MLX, Transformers, Chemprop, or REINVENT interpreter and owner-private jobs |
| Private local-model preview/activation | Saved private asset/candidate; human activation tied to matched held-out evaluation |
| Older task optimization/science adapters | Explicit server profile flags, pinned image, typed input, and isolation profile |
| Older task model registry/SFT/RL | Versioned vault artifacts, compatibility validation, evaluation and human promotion gate |
| Configured inference endpoint | Provider connection, secure key storage, model protocol, and consent; not an engine image |

Use [providers](inference-providers.md) for HTTP inference and
[polymer simulation](polymer-simulation.md) for native RadonPy/LAMMPS setup.
Installing a library does not enable every UI action or profile automatically.

## Optional profiles and isolation

The core dependency environment contains no GPU/model/science engine imports.
Use declared `uv` extras only when needed, retaining all required extras during
synchronization. Older science lanes additionally use explicit
`STUDIO_PROFILE_LOCAL_AI`, `STUDIO_PROFILE_OPTIMIZATION`,
`STUDIO_PROFILE_QUANTUM`, `STUDIO_PROFILE_MATERIALS`,
`STUDIO_PROFILE_TRAINING`, `STUDIO_PROFILE_DESIGN`, or
`STUDIO_PROFILE_SYNTHESIS` flags as applicable. Restart the API after changing
flags. Private learning dispatch is separately available by default and probes
its optional backend interpreters.

The `restricted` container profile uses network denial, read-only root filesystem,
non-root execution, bounded resources, and process-group termination. The
`development-reduced` subprocess profile does not enforce network denial and
must not satisfy a contract that requires it. Native private learning and
simulation workers scrub credentials but do not claim the container's OS-level
network boundary.

## Build pinned adapter images

Run from the repository root. These builds can download public dependencies and
require compatible Docker/platform resources; they are not core onboarding.
Consult the owning Dockerfile and requirement lock for the current image contract.

| Lane | Build command |
|---|---|
| RDKit | `docker buildx build --platform linux/amd64 -t chem-studio-rdkit:2026.3.6 infra/images/rdkit` |
| BayBE | `docker build -f workers/optimization/Dockerfile -t chem-studio-baybe:0.15.0-v1 .` |
| QCEngine/xtb | `docker build -f workers/chemistry/quantum/Dockerfile -t chem-studio-qcengine:0.51.0-v1 .` |
| Materials/thermo | `docker build -f workers/chemistry/materials/Dockerfile -t chem-studio-materials:0.6.1-v1 .` |
| REINVENT | `docker build -f workers/chemistry/design/Dockerfile -t chem-studio-reinvent:4.8-v1 .` |
| AiZynthFinder | `docker build -f workers/chemistry/synthesis/Dockerfile -t chem-studio-aizynthfinder:4.4.1-v1 .` |
| Chemprop adapter | `docker build -f workers/optimization/property_models/chemprop/Dockerfile -t chem-studio-chemprop:2.3.1-v1 .` |
| Registry loader | `docker build -f workers/inference/model_loading/Dockerfile -t chem-studio-model-load:0.1.0 .` |
| Older SFT trainer | `docker build -f workers/training/sft/Dockerfile -t chem-studio-sft:0.1.0-v5 .` |
| Older RL trainer | `docker build -f workers/training/rl/trainer/Dockerfile -t chem-studio-rl:0.1.0-v1 .` |

AiZynthFinder's stock/model payload needs a substantial memory envelope; historical
checks needed about 8 GiB. Exit 137 is a real resource failure, not an inference
result. Image tags and model/license requirements must match the adapter's
allowlist; do not silently point a pinned adapter at a different solver version.

`make test-engines` checks the RDKit prerequisite, then runs the engine suites.
Review per-lane outcomes and missing dependencies; passing descriptor tests does
not qualify every optional engine. Older llama.cpp serving additionally needs
its configured image/model volume and checksum-approved local GGUF asset; no
core bootstrap model download is implied.

## Older registry and promotion

The Model registry and older task learning controls register releases with
artifact/adapter/training lineage. Validation loads a release in the pinned
loader rather than importing arbitrary weights into the API process. Serving
pointer changes are atomic, and session model pins retain their selected release
until explicitly rebound. Inspect base/tokenizer compatibility before promotion.

Training flows use frozen datasets and grouped splits, declared configurations,
resource admission, and human approval where required. Cancellation preserves
incomplete checkpoint state; an incomplete run is not a usable successful
training result. RL uses a closed action/tool catalog and hard budgets without
an automatic cloud fallback.

Independent evaluation, matched baselines, and applicable scientific gates are
separate from training reward. A reward increase alone cannot approve promotion.
The human release/activation action must be authorized for the exact candidate;
an agent cannot grant itself this authority.

## Current private model operations

Use **Local learning** for custom imports, model catalog downloads, preflight,
training, evaluation, cancellation, and resumption. Use a model preview or explicit
agent-run selection to inspect a candidate without changing the active binding.
[Learning documentation](learning-workspace.md) describes supported data kinds,
protocols, limits, and backend behavior.

Models downloaded into the active vault are included in a full vault backup.
Imported existing model directories remain at their registered external paths;
copy those separately. Remote worker-local model mappings and files also need
separate recovery. A restored DB does not make a missing external model loadable.

`make eval-smoke` executes a fixture-only evaluation. `make train-smoke` is an
older prerequisite/harness gate and may report blocked; it is not the current
private-learning acceptance workflow. Native training and engine execution
establish software behavior, not scientific qualification of predictions.
