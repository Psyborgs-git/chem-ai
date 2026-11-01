# Private learning workspace

The learning workspace uses owner-scoped datasets, model assets and durable jobs.
It is enabled by default. Optional runtimes report their actual dependency and
hardware availability; the API does not substitute fixture training when a
runtime is unavailable.

## Local Apple Silicon

```sh
uv run python -m venv .runtime/learning-mlx
.runtime/learning-mlx/bin/pip install -r workers/training/mlx/requirements.lock
```

The API discovers this environment for MLX and catalog downloads. An installed
deployment can set `STUDIO_MLX_PYTHON` and `STUDIO_TRAINING_PYTHON` to explicit
interpreter paths. The API environment stays free of optional MLX/torch imports.
Metal must be accessible to the application process. A sandbox or headless
session that cannot access Metal reports the MLX runtime unavailable.

The API also discovers isolated environments at `.runtime/learning-science`
for Chemprop, `.runtime/learning-transformers` for Transformers/PEFT/TRL, and
`.runtime/learning-reinvent` for REINVENT. The installed science environment is
used automatically when no interpreter override is set. Deployments can select
interpreters with `STUDIO_CHEMPROP_PYTHON`, `STUDIO_TRANSFORMERS_PYTHON`, or
`STUDIO_REINVENT_PYTHON`. Each environment needs its corresponding runtime
dependencies; a GPU worker needs a compatible GPU-enabled torch installation.
A backend-specific override takes precedence over `STUDIO_TRAINING_PYTHON`,
which in turn takes precedence over automatic discovery. No environment is
installed by selecting a model or starting a job.

The catalog includes Qwen3 0.6B in MLX 4-bit and Transformers formats, plus Qwen3
4B Instruct 2507 in MLX 4-bit for substantive local assistant adaptation. Selecting a
catalog model creates an explicit download job. Existing local safetensors model
directories can also be registered. Training loads local assets with remote code
disabled and model-hub offline flags. Native execution scrubs credentials from
the worker environment; it does not claim OS-enforced network isolation.
Catalog revisions are pinned to immutable Hugging Face commits. Downloads verify
weight SHA-256 values and retain a manifest of repository, revision, license and
every file's hash. Remote workers use the same pinned download path. Optional
runtime interpreters receive first-party source paths without the API environment's
site-packages, so installed MLX and Chemprop versions remain isolated.

## Datasets and jobs

Use `/api/learning-workspace` with the existing authenticated session:

- `POST /datasets/import` accepts UTF-8 content, format, field mapping, source
  provenance, data kind and training rights. `POST /datasets/upload` accepts a
  multipart file and JSON `metadata`. CSV, JSONL, SMI and SDF are supported, up to
  20 MiB and 50,000 rows.
- `POST /datasets/from-notebook` accepts `pageIds` and `name`. Current authored
  revisions become prompt/response examples; recipes and formula fields are
  included. Notebook training opt-outs apply to exports and existing jobs.
- `POST /datasets/{id}/freeze` creates immutable identity/scaffold/document
  grouping and train/development/final partitions. At least three independent
  groups are needed for held-out partitions. Related examples never cross the
  boundary. Rejected rows and duplicate counts stay visible.
- `POST /datasets/from-source` imports externally computed CSV/JSONL values
  directly from an owner-retained source's original bytes. It requires declared
  training rights, verifies the retained checksum, preserves selected metadata
  columns and property/unit/method/condition context, and records source lineage.
  Caller-supplied replacement content is never used. This is the agent's route
  for published computational datasets; generated labels cannot use this route.
- `POST /jobs/preflight` accepts the same kind/dataset/model/config payload as
  job creation and returns ordered compatibility, rights, held-out partition,
  runtime/device and disk checks with resolved parameters. `GET /jobs/preflight`
  checks defaults. Job creation uses these checks too; unresolved checks produce
  a blocked job. Research-workflow jobs and catalog downloads retain a 5 GiB
  free-space reserve in addition to the estimated allocation.
- `POST /jobs` accepts `datasetId`, optional `modelId`, `kind`, and bounded
  `config`. Supported kinds are assistant SFT, DPO, GRPO, Chemprop regression or
  binary classification (`propertyTask`),
  molecular transfer learning, molecular RL, held-out evaluation and prediction.
  `GET /jobs/{id}` returns persisted progress and checkpoint metadata.
- `POST /jobs/{id}/cancel` stops a process group; `/resume` requeues stopped jobs.
  Transformers resumes optimizer checkpoints. MLX resumes adapter weights as a
  **warm start**, with fresh optimizer state. Worker lease expiry leaves an
  interrupted job that can be resumed.

Assistant data uses `prompt`/`response`; preference data uses
`prompt`/`chosen`/`rejected`; GRPO uses `prompt`/`expected` and an exact-match
reward. Molecular property training uses `smiles`/`target` with declared
method/unit context. Classification requires 0/1 labels with both classes in
training and reports held-out accuracy and AUROC when both held-out classes
exist. Structure-only input supplies no invented property labels.
Molecular RL supports declared QED, molecular-weight or logP objectives using a
licensed local REINVENT prior. These scoring objectives do not establish
experimental properties, biological activity or safety.

Research extraction and structure checks validate provenance/schema/structure;
they do not turn a paper claim or synthetic example into an experimental
measurement. Data kinds remain explicit in job lineage.
Assistant JSONL also supports complete `messages` and `tools`, including matched
assistant tool calls and tool results. Tool protocol is checked on import;
identical user conversations stay in the same partition. Molecular data preserves
polymer repeat-unit SMILES (including connection wildcards), UUID metadata and
declared conditions. Each property fit uses one property/unit/method/condition
context, rather than silently combining unlike measurements.

## Self-hosted worker protocol

The authenticated worker protocol is implemented, but the stock Studio server
is loopback-only. The supported local test below connects on the same machine.
A different host needs a separately designed secure HTTPS deployment and
reachable authenticated service; changing a URL or origin allowlist alone does
not provide supported LAN/remote hosting.

Install the repository and desired training/Chemprop/REINVENT dependencies in
the worker environment. A worker initiates its API connections; the server does
not need inbound access to the worker machine.

```sh
python -m workers.training.workspace_worker \
  --api http://127.0.0.1:8787 \
  --backends transformers,chemprop \
  --work-dir /private/training
```

Set `STUDIO_WORKER_TOKEN` to an existing user's session token through the worker
host's secret management. It is never printed or passed to trainer processes.
Create jobs with `config.executionTarget="remote"`. Leases, heartbeat,
cancellation, checkpoint download and artifact upload are authenticated and
restricted to that user. Remote connections require HTTPS; loopback HTTP is
accepted for local testing.

Catalog assets download on the worker. Imported assets require an explicit
`--model MODEL_ID=/local/model/path` mapping. The server never sends its local
model paths. ZIP members are bounded and cannot escape the job output directory;
artifact/checkpoint transfers are limited to 256 MiB. Worker loss expires the
lease after two minutes. Resume reuses the uploaded checkpoint files.

## Evaluation and use

Completed training registers an owner-private candidate. `/models/{id}/preview`
uses saved weights; `/models/{id}/chat` accepts complete chat messages and a typed
tool catalog. Native tool calls are limited to that supplied catalog and are
validated again by the agent runtime. An explicit model selection can preview a
candidate in an agent run without changing the owner's active binding.

An `evaluate` job runs the base and candidate on the same held-out final prompts
without supplying their expected answers to either model. It records exact-match
metrics and the real responses in an owner-only downloadable artifact. This
evaluation is software evidence, not scientific validation of chemistry claims.
Each base/candidate is loaded once per evaluation pass. Optional per-row
`evaluation` contracts check JSON fields, allowed/required citation IDs, numeric
values and units, expected tool calls and forbidden phrases. Citation-ID checks
do not establish that a source entails a generated claim.

Property evaluation predicts only labelled final rows and reports MAE/RMSE or
classification metrics against a mean/majority baseline fitted from training
labels. Saved models retain a Morgan-fingerprint applicability manifest, and
predictions report nearest-training structural coverage. The threshold is an
uncalibrated coverage flag, rather than an uncertainty interval or a measure of
fabric hand, drape or performance.

`POST /models/{id}/activate` requires `approved: true` and `evaluationJobId` from a
completed matched held-out evaluation for that exact model. The human user's
private active binding changes atomically. This remains separate from the older
pico fixture registry and does not bypass its base/tokenizer compatibility
rules. The agent cannot call the human activation action as a tool.

Historical synthetic smoke artifacts under `.runtime/learning-smoke/` demonstrate
the tested training mechanism. Check current preflight, dependencies, hardware,
and job outcomes on the machine being operated; those artifacts do not establish
model quality or scientific qualification.

## Files and recovery

Private datasets/model/job metadata live in PostgreSQL. Catalog model downloads,
local job outputs, adapters, checkpoints, and previews normally live inside the
active vault's workspace/learning/owner tree and are included in a full vault
backup. Imported model paths may point outside that tree. Worker-host files and
explicit model mappings are also external. Preserve those separately and retain
the exact base/model revisions needed to resume or load adapters.

Quiesce running jobs before a database/vault snapshot. A restored database alone
does not recover external model directories or optional Python environments.
See [configuration](configuration.md), [backup and restore](backup-restore.md),
and [recovery](recovery.md).
