# Private learning workspace

The learning workspace uses owner-scoped datasets, model assets and durable jobs.
It is enabled by default. Optional runtimes report their actual dependency and
hardware availability; the API does not substitute fixture training when a
runtime is unavailable.

## Local Apple Silicon

```sh
python3.12 -m venv .runtime/learning-mlx
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

The catalog includes Qwen3 0.6B in MLX 4-bit and Transformers formats. Selecting a
catalog model creates an explicit download job. Existing local safetensors model
directories can also be registered. Training loads local assets with remote code
disabled and model-hub offline flags. Native execution scrubs credentials from
the worker environment; it does not claim OS-enforced network isolation.

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

## Self-hosted GPU workers

Install the repository and the desired optional training/Chemprop/REINVENT
dependencies on the worker host. A worker opens outbound connections only; the
Studio server does not need access to the worker machine.

```sh
python -m workers.training.workspace_worker \
  --api https://studio.example \
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

`POST /models/{id}/activate` requires `approved: true` and `evaluationJobId` from a
completed matched held-out evaluation for that exact model. The human user's
private active binding changes atomically. This remains separate from the older
pico fixture registry and does not bypass its base/tokenizer compatibility
rules. The agent cannot call the human activation action as a tool.

The two-step local synthetic smoke is recorded under `.runtime/learning-smoke/`.
It proves real LoRA updates, persisted checkpoints and reloadable inference, not
model quality or a scientifically validated chemistry model.
