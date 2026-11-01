# Research workbench and local-learning experiment

The workbench connects a private research-agent conversation, retained public
sources, notebooks, immutable datasets, local training and bounded polymer
simulations. This document describes the implemented workflow. The materials
campaign's actual model and simulation results are recorded separately; adding
a catalog model or queueing a run does not establish a successful fine-tune.

## Using the interface

**Local learning** opens on **Runs**, with persisted status, progress, loss and
validation events, measured results, artifacts and stop/resume controls. Existing
research campaigns show their linked resources, API cost and an **Open agent**
action. **Datasets** exposes accepted/rejected rows, duplicates and frozen
partitions. **Models** distinguishes downloadable bases, trained candidates and
assistant previews. **New run** guides task, dataset, compatible model,
parameters and readiness checks before queueing.

Source-backed property datasets carry their property, unit and method into the
form. These fields stay attached to the source context. Assistant previews use
ready MLX/Transformers models; molecular models use prediction jobs. Candidate
evaluation is separate from a human-approved active-model change.

The global agent keeps durable conversations with visible, searchable session
history, explicit New chat and a conversation layout with grouped tool activity.
History search matches titles and visible messages within the current owner's
workspace. Older sessions and messages have pagination; reopening history does
not resume a charged run. Only the selected session ID is stored locally, scoped
to its owner. Notebooks support recoverable
edits, recipe/formula/structure pages and source citations. Research library and
Downloads retain originals, text and citation metadata for review. Research
memory stores source-linked findings and open questions.
Native artifact downloads use `~/Downloads/Chemistry Studio/Artifacts/`, with
job-specific learning/simulation folders and collision-safe filenames. Directories
are private (`0700`) and downloaded files are private (`0600`). Research originals,
readable copies and citation metadata retain their existing source folders.

## Interfaces and data lineage

- `/api/research-workflows` creates and reads owner-private public-source
  campaigns, each with its own agent thread, notebook, limits and resource ledger.
  Campaign agents can access only linked workflow resources and allowed tools.
- `/api/learning-workspace/jobs/preflight` accepts the proposed job payload and
  checks data rights, compatible rows/model, held-out groups, runtime/device and
  storage. Creation repeats admission checks. Incompatible inputs are rejected;
  unavailable prerequisites leave a blocked job with its reason.
- `/api/learning-workspace/datasets/from-source` imports actual retained
  CSV/JSONL bytes, verifies their checksum and declared training rights, and
  preserves polymer UUIDs, repeat-unit SMILES, conditions and property context.
  Externally computed values remain distinct from measured observations.
- The agent's `merge_datasets` tool compiles 2–10 owned synthetic assistant
  shards, preserving multi-turn tool calls/results, evaluation contracts and
  document groups. It deduplicates rows and rechecks parent/source rights during
  future training. Generated examples do not become experimental labels.
- Catalog downloads pin an immutable Hugging Face revision and retain verified
  file hashes and licenses. The Qwen3 4B Instruct 2507 MLX 4-bit entry is a local
  assistant base; its availability alone does not mean it has been trained.
  Public campaigns accept only actual pinned catalog entries and cannot override
  their paths, backend or repository. An unknown catalog ID never falls back to
  importing an unrelated local model.
- Public workflows can save source-linked research memory using only their own
  linked source/page references. This does not grant access to unrelated memory,
  notebooks or projects, and current revision/access checks still apply.

Assistant evaluation compares base and adapter on final prompts without giving
either the target answer. Declared task checks cover JSON shape, citation IDs,
numeric values/units and tool calls. Property evaluation uses final labels and a
training-only baseline, with structural coverage flags. These checks do not
establish source entailment or experimental textile performance.
Raw output-format scores remain separate from semantic checks that remove only
an empty model protocol prefix. Nonempty reasoning text is never stripped to
make an invalid answer pass. Every MLX train/development sequence is tokenized
before optimization; overlong or empty-target examples fail clearly. Final
held-out examples never enter assistant training requests or loaders.

## Limits and physical meaning

Campaign defaults are four hours each for training and simulation and US$20 for
paid inference; the saved campaign specification is authoritative. Agents cannot
raise those limits. Admission reserves compute time, reconciles actual elapsed
time across retries, and serializes heavy work. Campaign learning/model downloads
preserve 5 GiB free storage in addition to the estimated allocation. Manual jobs
outside a campaign use their own job limits. Optional runtimes stay isolated and
workers receive a scrubbed credential environment.
HTTP providers require explicit token prices for autopilot, including localhost
gateways that may forward paid requests; use explicit zero prices for a free
gateway. Disclosure routing and paid usage accounting are separate decisions.

Polymer pilots run actual RadonPy/GAFF2/Gasteiger/LAMMPS calculations for bounded
amorphous cells at 300 K and 1 atm. A small two-seed PET positive control completed
real integration, cancellation and stage resumption checks. Its short trajectories
were numerically stable but unconverged and explicitly ineligible as training
labels. The separate 200-step Qwen4B campaign and property fits are described in
the [actual experiment report](research/mulberry-silk-pilot-2026-11-01.md).

Repeat-unit properties cannot determine yarn orientation, fiber cross-section,
weave, finishing, tactile hand or drape. The user clarified the textile reference
as mulberry (*Bombyx mori*) silk, prioritizing feel, drape and lustre. This requires
separate measured textile endpoints. See the
[learning runbook](operations/learning-workspace.md) and
[polymer simulation runbook](operations/polymer-simulation.md) for exact runtime,
protocol, convergence and artifact contracts.
