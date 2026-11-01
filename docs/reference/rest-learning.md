# Local learning and worker API

Private datasets, model registration, preflight, training/evaluation jobs and authenticated self-hosted worker leases.

[Shared authentication, errors and transport](rest-overview.md). Examples use synthetic values; replace resource IDs with records from your workspace.

## GET /api/learning-workspace/capabilities

Inspect learning backends, devices, model catalog and supported jobs.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No body.

**Response:** Runtime/backend readiness, device availability, catalog and supported training/evaluation capabilities. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/learning-workspace/capabilities HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** Synthetic Linux host with none of the optional backend dependencies installed. This response reports unavailability honestly; it does not install anything or start training.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "enabled": true,
  "platform": "Linux",
  "architecture": "x86_64",
  "backends": [
    {
      "backend": "mlx",
      "available": false,
      "missing": [
        "mlx_lm",
        "mlx"
      ],
      "platformSupported": false,
      "deviceAvailable": true,
      "execution": "native_local_process",
      "installCommand": "python -m pip install \"mlx-lm[train]\""
    },
    {
      "backend": "transformers",
      "available": false,
      "missing": [
        "torch",
        "transformers",
        "peft",
        "trl",
        "datasets"
      ],
      "platformSupported": true,
      "deviceAvailable": true,
      "execution": "native_local_process",
      "installCommand": "python -m pip install torch transformers peft trl datasets accelerate"
    },
    {
      "backend": "chemprop",
      "available": false,
      "missing": [
        "torch",
        "chemprop",
        "rdkit",
        "pydantic"
      ],
      "platformSupported": true,
      "deviceAvailable": true,
      "execution": "native_local_process",
      "installCommand": "python -m pip install chemprop==2.3.1 rdkit pydantic"
    },
    {
      "backend": "reinvent",
      "available": false,
      "missing": [
        "reinvent",
        "torch",
        "rdkit"
      ],
      "platformSupported": true,
      "deviceAvailable": true,
      "execution": "native_local_process",
      "installCommand": "Install MolecularAI/REINVENT4 and register a licensed local prior"
    },
    {
      "backend": "download",
      "available": false,
      "missing": [
        "huggingface_hub"
      ],
      "platformSupported": true,
      "deviceAvailable": true,
      "execution": "native_local_process",
      "installCommand": "python -m pip install huggingface-hub"
    }
  ],
  "catalog": [
    {
      "id": "qwen3-0.6b-mlx",
      "name": "Qwen3 0.6B · MLX 4-bit",
      "repo": "mlx-community/Qwen3-0.6B-4bit",
      "revision": "73e3e38d981303bc594367cd910ea6eb48349da8",
      "backend": "mlx",
      "license": "apache-2.0",
      "sizeHint": "~0.5 GB",
      "estimatedBytes": 500000000,
      "tasks": [
        "sft",
        "evaluate"
      ]
    },
    {
      "id": "qwen3-0.6b",
      "name": "Qwen3 0.6B · Transformers",
      "repo": "Qwen/Qwen3-0.6B",
      "revision": "c1899de289a04d12100db370d81485cdf75e47ca",
      "backend": "transformers",
      "license": "apache-2.0",
      "sizeHint": "~1.3 GB",
      "estimatedBytes": 1300000000,
      "tasks": [
        "sft",
        "dpo",
        "grpo",
        "evaluate"
      ]
    },
    {
      "id": "qwen3-4b-instruct-mlx",
      "name": "Qwen3 4B Instruct 2507 · MLX 4-bit",
      "repo": "mlx-community/Qwen3-4B-Instruct-2507-4bit",
      "revision": "50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b",
      "backend": "mlx",
      "license": "apache-2.0",
      "sizeHint": "~2.28 GB",
      "estimatedBytes": 2278972236,
      "tasks": [
        "sft",
        "evaluate"
      ],
      "description": "Instruction and tool-use adaptation on Apple Silicon"
    }
  ],
  "privacy": "Datasets, jobs and trained models are private to their owner",
  "formats": [
    "csv",
    "jsonl",
    "smi",
    "sdf"
  ],
  "jobKinds": [
    "chemprop",
    "dpo",
    "evaluate",
    "grpo",
    "molecular_rl",
    "molecular_transfer",
    "predict",
    "sft"
  ],
  "taskParameters": {
    "sft": {
      "stepLabel": "Optimizer steps",
      "requires": [
        "messages or prompt/response",
        "assistant model"
      ]
    },
    "chemprop": {
      "stepLabel": "Epochs",
      "maxSteps": 300,
      "requires": [
        "SMILES and target",
        "property/unit/method"
      ]
    },
    "evaluate": {
      "stepLabel": "Held-out evaluation",
      "requires": [
        "trained candidate",
        "final partition"
      ]
    }
  },
  "limits": {
    "datasetBytes": 20971520,
    "datasetRows": 50000
  },
  "storage": {
    "available": true,
    "freeBytes": 21474836480,
    "requiredFreeBytes": 134217728
  },
  "hardwareProfiles": [
    {
      "id": "apple_silicon",
      "backend": "mlx",
      "kinds": [
        "sft",
        "evaluate"
      ]
    },
    {
      "id": "cpu_or_cuda",
      "backend": "transformers",
      "kinds": [
        "sft",
        "dpo",
        "grpo",
        "evaluate"
      ]
    }
  ]
}
```

**Failure response example:** The session cookie is omitted and no Bearer session token is supplied.

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "errors": [
    {
      "code": "UNAUTHENTICATED",
      "message": "session required",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [capabilities](contracts-learning.md#capabilities), [LearningWorkspaceService.catalog](contracts-learning.md#learningworkspaceservicecatalog).

Source: `services/studio-api/src/studio/api/learning_workspace.py:24` (`capabilities`).

## GET /api/learning-workspace/datasets

List private datasets.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No body; identifier is required for a single dataset.

**Response:** Dataset descriptor: id, name, state, dataKind, rights, report, source, digest, rowCount, partitions and createdAt; detail responses add at most 200 preview rows, previewTruncated and splits. See _dataset for conditional fields. Returned as an array. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/learning-workspace/datasets HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** This owner has no private datasets.

```http
HTTP/1.1 200 OK
Content-Type: application/json

[]
```

**Failure response example:** The session cookie is omitted and no Bearer session token is supplied.

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "errors": [
    {
      "code": "UNAUTHENTICATED",
      "message": "session required",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [datasets](contracts-learning.md#datasets), [LearningWorkspaceService.list_datasets](contracts-learning.md#learningworkspaceservicelist_datasets), [LearningWorkspaceService._dataset](contracts-learning.md#learningworkspaceservice_dataset).

Source: `services/studio-api/src/studio/api/learning_workspace.py:29` (`datasets`).

## GET /api/learning-workspace/datasets/{identifier}

Read one private dataset and its rows.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No body; identifier is required for a single dataset.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `identifier` (required) | path | `str` | `required` |

**Response:** Dataset descriptor: id, name, state, dataKind, rights, report, source, digest, rowCount, partitions and createdAt; detail responses add at most 200 preview rows, previewTruncated and splits. See _dataset for conditional fields. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/learning-workspace/datasets/00000000-0000-4000-8000-000000000011 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000011",
  "name": "Synthetic assistant examples",
  "state": "validated",
  "dataKind": "synthetic",
  "rights": "owned",
  "report": {
    "total": 3,
    "accepted": 3,
    "rejected": 0,
    "duplicates": 0,
    "rejections": [],
    "rowKinds": {
      "assistant": 3
    },
    "validation": "structure_and_schema",
    "scientificStatus": "not_validated"
  },
  "source": {
    "kind": "documentation_fixture"
  },
  "digest": "5b731741ec23484b524eed160bfa40600d5f7b2d8bf1f533ecb6e6764ba8a12f",
  "rowCount": 3,
  "partitions": {},
  "createdAt": "2026-11-02T00:00:00+00:00",
  "rows": [
    {
      "id": "row-1",
      "sourceRow": 1,
      "prompt": "First synthetic question",
      "response": "First synthetic answer",
      "documentId": "doc-a"
    },
    {
      "id": "row-2",
      "sourceRow": 2,
      "prompt": "Second synthetic question",
      "response": "Second synthetic answer",
      "documentId": "doc-b"
    },
    {
      "id": "row-3",
      "sourceRow": 3,
      "prompt": "Third synthetic question",
      "response": "Third synthetic answer",
      "documentId": "doc-c"
    }
  ],
  "previewTruncated": false,
  "splits": {}
}
```

**Failure response example:** The session cookie is omitted and no Bearer session token is supplied.

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "errors": [
    {
      "code": "UNAUTHENTICATED",
      "message": "session required",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [dataset](contracts-learning.md#dataset), [LearningWorkspaceService.get_dataset](contracts-learning.md#learningworkspaceserviceget_dataset), [LearningWorkspaceService._dataset](contracts-learning.md#learningworkspaceservice_dataset).

Source: `services/studio-api/src/studio/api/learning_workspace.py:70` (`dataset`).

## GET /api/learning-workspace/jobs

List private learning jobs.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No body.

**Response:** Job descriptor: id, name, kind, state, datasetId, modelId, config, result, events (latest 100), error, attempt, cancelRequested, createdAt, updatedAt and elapsedSeconds. Returned as an array. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/learning-workspace/jobs HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** No private learning jobs exist for this owner.

```http
HTTP/1.1 200 OK
Content-Type: application/json

[]
```

**Failure response example:** The session cookie is omitted and no Bearer session token is supplied.

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "errors": [
    {
      "code": "UNAUTHENTICATED",
      "message": "session required",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [jobs](contracts-learning.md#jobs), [LearningWorkspaceService.list_jobs](contracts-learning.md#learningworkspaceservicelist_jobs), [LearningWorkspaceService._job](contracts-learning.md#learningworkspaceservice_job).

Source: `services/studio-api/src/studio/api/learning_workspace.py:129` (`jobs`).

## GET /api/learning-workspace/jobs/preflight

Inspect training/evaluation readiness before queueing a job.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** Required datasetId query; kind defaults to sft and optional modelId. Uses default configuration.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `datasetId` (required) | query | `str` | `required` |
| `kind` (optional) | query | `str` | `'sft'` |
| `modelId` (optional) | query | `str \| None` | `None` |

**Response:** Readiness/preflight report: blockers/warnings, selected runtime/device, normalized configuration, storage estimates and compatibility checks. No training job is created. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/learning-workspace/jobs/preflight?datasetId=00000000-0000-4000-8000-000000000011&kind=sft&modelId=00000000-0000-4000-8000-000000000012 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** The frozen example dataset and ready Transformers model are selected; the optional local runtime and output storage are available. GET applies default local configuration, not the explicit remote POST configuration.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "ready": true,
  "checks": [
    {
      "id": "inputs",
      "status": "pass",
      "message": "Dataset rights, model compatibility and parameter validation passed"
    },
    {
      "id": "heldout",
      "status": "pass",
      "message": "Independent train and final groups are present"
    },
    {
      "id": "runtime",
      "status": "pass",
      "message": "Local runtime is available"
    },
    {
      "id": "device",
      "status": "pass",
      "message": "Selected auto device is available"
    },
    {
      "id": "model",
      "status": "pass",
      "message": "Model asset is ready"
    },
    {
      "id": "disk",
      "status": "pass",
      "message": "Output storage is available"
    },
    {
      "id": "data_origin",
      "status": "warn",
      "message": "Synthetic labels retain their data origin; training does not establish experimental properties"
    }
  ],
  "normalizedConfig": {
    "backend": "transformers",
    "maxSteps": 20,
    "batchSize": 1,
    "maxTokens": 256,
    "maxSeconds": 3600,
    "saveEvery": 10,
    "seed": 0,
    "rank": 8,
    "numGenerations": 2,
    "ensembleSize": 2,
    "hiddenDim": 64,
    "depth": 2,
    "learningRate": 1e-05
  },
  "estimated": {
    "available": true,
    "freeBytes": 21474836480,
    "requiredFreeBytes": 536870912
  },
  "dataset": {
    "id": "00000000-0000-4000-8000-000000000011",
    "state": "frozen",
    "trainingRows": 1,
    "developmentRows": 1,
    "finalRows": 1
  },
  "model": {
    "id": "00000000-0000-4000-8000-000000000012",
    "backend": "transformers",
    "state": "ready"
  }
}
```

**Failure response example:** The selected dataset has not been frozen; preflight returns ready=false rather than an HTTP error.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "ready": false,
  "checks": [
    {
      "id": "inputs",
      "status": "fail",
      "message": "Freeze the validated dataset before starting a job"
    }
  ],
  "normalizedConfig": {}
}
```

**Exact JSON rules and response serialization:** [default_job_preflight](contracts-learning.md#default_job_preflight), [LearningWorkspaceService.preflight_job](contracts-learning.md#learningworkspaceservicepreflight_job), [LearningWorkspaceService._prepare_job](contracts-learning.md#learningworkspaceservice_prepare_job).

Source: `services/studio-api/src/studio/api/learning_workspace.py:150` (`default_job_preflight`).

## GET /api/learning-workspace/jobs/{identifier}

Read one learning job.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** identifier path parameter; no body.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `identifier` (required) | path | `str` | `required` |

**Response:** Job descriptor: id, name, kind, state, datasetId, modelId, config, result, events (latest 100), error, attempt, cancelRequested, createdAt, updatedAt and elapsedSeconds. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/learning-workspace/jobs/00000000-0000-4000-8000-000000000013 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000013",
  "name": "Synthetic remote assistant adaptation",
  "kind": "sft",
  "state": "queued",
  "datasetId": "00000000-0000-4000-8000-000000000011",
  "modelId": "00000000-0000-4000-8000-000000000012",
  "config": {
    "executionTarget": "remote",
    "device": "cpu",
    "backend": "transformers",
    "maxSteps": 20,
    "batchSize": 1,
    "maxTokens": 256,
    "maxSeconds": 3600,
    "saveEvery": 10,
    "seed": 0,
    "rank": 8,
    "numGenerations": 2,
    "ensembleSize": 2,
    "hiddenDim": 64,
    "depth": 2,
    "learningRate": 1e-05
  },
  "result": {
    "datasetDigest": "30affb02e05a8dae705fce7afb61e567464794ef715f6358b056ee5ce91212cc",
    "dataKind": "synthetic",
    "scientificStatus": "not_validated",
    "storagePreflight": {
      "available": true,
      "freeBytes": 21474836480,
      "requiredFreeBytes": 134217728
    },
    "preflight": {
      "ready": true,
      "checks": [
        {
          "id": "inputs",
          "status": "pass",
          "message": "Dataset rights, model compatibility and parameter validation passed"
        },
        {
          "id": "heldout",
          "status": "pass",
          "message": "Independent train and final groups are present"
        },
        {
          "id": "runtime",
          "status": "pass",
          "message": "Self-hosted worker selected; a compatible worker must claim the job"
        },
        {
          "id": "model",
          "status": "pass",
          "message": "Model asset is ready"
        },
        {
          "id": "disk",
          "status": "pass",
          "message": "Output storage is available"
        },
        {
          "id": "data_origin",
          "status": "warn",
          "message": "Synthetic labels retain their data origin; training does not establish experimental properties"
        }
      ],
      "normalizedConfig": {
        "executionTarget": "remote",
        "device": "cpu",
        "backend": "transformers",
        "maxSteps": 20,
        "batchSize": 1,
        "maxTokens": 256,
        "maxSeconds": 3600,
        "saveEvery": 10,
        "seed": 0,
        "rank": 8,
        "numGenerations": 2,
        "ensembleSize": 2,
        "hiddenDim": 64,
        "depth": 2,
        "learningRate": 1e-05
      },
      "estimated": {
        "available": true,
        "freeBytes": 21474836480,
        "requiredFreeBytes": 134217728
      },
      "dataset": {
        "id": "00000000-0000-4000-8000-000000000011",
        "state": "frozen",
        "trainingRows": 1,
        "developmentRows": 1,
        "finalRows": 1
      },
      "model": {
        "id": "00000000-0000-4000-8000-000000000012",
        "backend": "transformers",
        "state": "ready"
      }
    }
  },
  "events": [],
  "error": null,
  "attempt": 0,
  "cancelRequested": false,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00",
  "elapsedSeconds": null
}
```

**Failure response example:** The session cookie is omitted and no Bearer session token is supplied.

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "errors": [
    {
      "code": "UNAUTHENTICATED",
      "message": "session required",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [job](contracts-learning.md#job), [LearningWorkspaceService.get_job](contracts-learning.md#learningworkspaceserviceget_job), [LearningWorkspaceService._job](contracts-learning.md#learningworkspaceservice_job).

Source: `services/studio-api/src/studio/api/learning_workspace.py:164` (`job`).

## GET /api/learning-workspace/jobs/{identifier}/artifacts/{name:path}

Download a named artifact belonging to a private learning job.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** identifier and relative artifact name; no body. Traversal and non-owned artifacts are rejected.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `identifier` (required) | path | `str` | `required` |
| `name` (required) | path | `str` | `required` |

**Response:** Binary application/octet-stream FileResponse with attachment filename; not a JSON object. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/learning-workspace/jobs/00000000-0000-4000-8000-000000000013/artifacts/result.json HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** The completed owned job has result.json listed in its retained artifact manifest.

```http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="result.json"

{"ok":true,"scientificStatus":"not_validated"}
```

**Failure response example:** Job artifact not found.

```http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "Job artifact not found",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [artifact](contracts-learning.md#artifact), [LearningWorkspaceService.artifact_path](contracts-learning.md#learningworkspaceserviceartifact_path).

Source: `services/studio-api/src/studio/api/learning_workspace.py:176` (`artifact`).

## GET /api/learning-workspace/models

List private local/self-hosted models.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No body; identifier path parameter for one model.

**Response:** Model descriptor: id, name, backend, location, state, details and timestamps; details carry license/provenance/evaluation metadata. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/learning-workspace/models HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** No private model is registered for this owner.

```http
HTTP/1.1 200 OK
Content-Type: application/json

[]
```

**Failure response example:** The session cookie is omitted and no Bearer session token is supplied.

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "errors": [
    {
      "code": "UNAUTHENTICATED",
      "message": "session required",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [models](contracts-learning.md#models), [LearningWorkspaceService.list_models](contracts-learning.md#learningworkspaceservicelist_models), [LearningWorkspaceService._model](contracts-learning.md#learningworkspaceservice_model).

Source: `services/studio-api/src/studio/api/learning_workspace.py:82` (`models`).

## GET /api/learning-workspace/models/{identifier}

Read one private model.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No body; identifier path parameter for one model.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `identifier` (required) | path | `str` | `required` |

**Response:** Model descriptor: id, name, backend, location, state, details and timestamps; details carry license/provenance/evaluation metadata. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/learning-workspace/models/00000000-0000-4000-8000-000000000012 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000012",
  "name": "Example local assistant",
  "backend": "transformers",
  "location": "/private/example-models/qwen3-0.6b",
  "details": {
    "license": "apache-2.0",
    "state": "ready"
  },
  "createdAt": "2026-11-02T00:00:00+00:00"
}
```

**Failure response example:** The session cookie is omitted and no Bearer session token is supplied.

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "errors": [
    {
      "code": "UNAUTHENTICATED",
      "message": "session required",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [model](contracts-learning.md#model), [LearningWorkspaceService.get_model](contracts-learning.md#learningworkspaceserviceget_model), [LearningWorkspaceService._model](contracts-learning.md#learningworkspaceservice_model).

Source: `services/studio-api/src/studio/api/learning_workspace.py:103` (`model`).

## GET /api/learning-workspace/worker/jobs/{identifier}/checkpoint

Download retained checkpoint state for the active worker lease.

**Access:** Authenticated session principal; all leases/jobs are restricted to its workspace and owner ID. The supported CLI uses an existing trusted owner/user session token, not an unauthenticated worker identity.

**Request:** identifier path parameter and workerId query parameter; active lease required.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `identifier` (required) | path | `str` | `required` |
| `workerId` (required) | query | `str` | `required` |

**Response:** Binary application/zip response. No arbitrary host path is accepted. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/learning-workspace/worker/jobs/00000000-0000-4000-8000-000000000013/checkpoint?workerId=worker-docs-001 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** This worker owns the live lease; the permitted retained files are zipped. The model endpoint can return an empty body when no transferable model artifacts exist.

```http
HTTP/1.1 200 OK
Content-Type: application/zip

<binary ZIP bytes; save the response to a file, do not JSON-decode>
```

**Failure response example:** Worker lease expired or does not own this job.

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "errors": [
    {
      "code": "CONFLICT",
      "message": "Worker lease expired or does not own this job",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [worker_checkpoint](contracts-learning.md#worker_checkpoint), [checkpoint_archive](contracts-learning.md#checkpoint_archive), [_leased](contracts-learning.md#_leased).

Source: `services/studio-api/src/studio/api/learning_workspace.py:229` (`worker_checkpoint`).

## GET /api/learning-workspace/worker/jobs/{identifier}/model

Download the permitted model artifact bundle for an active worker lease.

**Access:** Authenticated session principal; all leases/jobs are restricted to its workspace and owner ID. The supported CLI uses an existing trusted owner/user session token, not an unauthenticated worker identity.

**Request:** identifier path parameter and workerId query parameter; active lease required.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `identifier` (required) | path | `str` | `required` |
| `workerId` (required) | query | `str` | `required` |

**Response:** Binary application/zip response. No arbitrary host path is accepted. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/learning-workspace/worker/jobs/00000000-0000-4000-8000-000000000013/model?workerId=worker-docs-001 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** This worker owns the live lease; the permitted retained files are zipped. The model endpoint can return an empty body when no transferable model artifacts exist.

```http
HTTP/1.1 200 OK
Content-Type: application/zip

<binary ZIP bytes; save the response to a file, do not JSON-decode>
```

**Failure response example:** Worker lease expired or does not own this job.

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "errors": [
    {
      "code": "CONFLICT",
      "message": "Worker lease expired or does not own this job",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [worker_model](contracts-learning.md#worker_model), [model_archive](contracts-learning.md#model_archive), [_leased](contracts-learning.md#_leased).

Source: `services/studio-api/src/studio/api/learning_workspace.py:264` (`worker_model`).

## POST /api/learning-workspace/datasets/from-notebook

Build a private training dataset from eligible notebook pages.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** pageIds array; optional name and forAgent. Notebook/page training consent, ownership and source revocation are checked.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `payload` (required) | JSON body | `dict[str, Any]` | `required` |

**Response:** Dataset descriptor: id, name, state, dataKind, rights, report, source, digest, rowCount, partitions and createdAt; detail responses add at most 200 preview rows, previewTruncated and splits. See _dataset for conditional fields. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/learning-workspace/datasets/from-notebook HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "name": "Notebook training examples",
  "pageIds": [
    "00000000-0000-4000-8000-000000000005"
  ]
}
```

**Success response example:** The selected current page exists, has the synthetic content shown above, permits training, and has no restricted citations.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000011",
  "name": "Notebook training examples",
  "state": "validated",
  "dataKind": "user_authored",
  "rights": "owned",
  "report": {
    "total": 1,
    "accepted": 1,
    "rejected": 0,
    "duplicates": 0,
    "rejections": [],
    "rowKinds": {
      "assistant": 1
    },
    "validation": "structure_and_schema",
    "scientificStatus": "not_validated"
  },
  "source": {
    "kind": "private_notebook",
    "pages": [
      {
        "pageId": "00000000-0000-4000-8000-000000000005",
        "revision": 1,
        "citations": []
      }
    ],
    "contentRights": "user_authored_content_only"
  },
  "digest": "fa0d724b85c8964868ef44a82a3ebb2aed6601df83def92479e8f000c401e20e",
  "rowCount": 1,
  "partitions": {},
  "createdAt": "2026-11-02T00:00:00+00:00",
  "rows": [
    {
      "id": "row-1",
      "sourceRow": 1,
      "prompt": "Ethanol observation",
      "response": "Synthetic ethanol note.",
      "documentId": "00000000-0000-4000-8000-000000000005"
    }
  ],
  "previewTruncated": false,
  "splits": {}
}
```

**Failure response example:** training is disabled for this notebook.

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "errors": [
    {
      "code": "FORBIDDEN",
      "message": "training is disabled for this notebook",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [notebook_dataset](contracts-learning.md#notebook_dataset), [LearningWorkspaceService.import_notebook](contracts-learning.md#learningworkspaceserviceimport_notebook), [LearningWorkspaceService._dataset](contracts-learning.md#learningworkspaceservice_dataset).

Source: `services/studio-api/src/studio/api/learning_workspace.py:189` (`notebook_dataset`).

## POST /api/learning-workspace/datasets/from-source

Import a retained tabular research source as a property dataset.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** sourceId, property, unit and method; optional name, format, mapping, metadataColumns, filters and conditions. Sources must be usable and eligible; the result retains computational/literature provenance.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `payload` (required) | JSON body | `dict[str, Any]` | `required` |

**Response:** Dataset descriptor: id, name, state, dataKind, rights, report, source, digest, rowCount, partitions and createdAt; detail responses add at most 200 preview rows, previewTruncated and splits. See _dataset for conditional fields. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/learning-workspace/datasets/from-source HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "sourceId": "00000000-0000-4000-8000-000000000024",
  "name": "Published computed example",
  "format": "csv",
  "mapping": {
    "smiles": "smiles",
    "target": "target"
  },
  "property": "molecular_weight",
  "unit": "g/mol",
  "method": "published_calculation"
}
```

**Success response example:** The retained source original must be the declared synthetic CSV, with its actual checksum and explicit training rights. The response checksum is the SHA-256 of exactly smiles,target followed by CCO,46.069, each line newline-terminated; caller replacement content is never read.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000011",
  "name": "Published computed example",
  "state": "validated",
  "dataKind": "computed",
  "rights": "allowed",
  "report": {
    "total": 1,
    "accepted": 1,
    "rejected": 0,
    "duplicates": 0,
    "rejections": [],
    "rowKinds": {
      "molecular": 1
    },
    "validation": "structure_and_schema",
    "scientificStatus": "not_validated"
  },
  "source": {
    "kind": "external_computed",
    "sourceIds": [
      "00000000-0000-4000-8000-000000000024"
    ],
    "sourceRefs": [
      {
        "sourceId": "00000000-0000-4000-8000-000000000024",
        "revision": 1,
        "checksum": "07606ee731577b2d8e15fbe8a24c253d47d0fc7dea139b34f3ec45b3b847c614"
      }
    ],
    "citation": {
      "rights": {
        "retrieval": "allowed",
        "extraction": "allowed",
        "training": "allowed",
        "export": "allowed"
      }
    },
    "filters": {},
    "externalComputation": {
      "property": "molecular_weight",
      "unit": "g/mol",
      "method": "published_calculation",
      "conditions": {}
    },
    "scientificStatus": "not_validated",
    "importMeaning": "source_bytes_not_generated_labels"
  },
  "digest": "d4bfbcb3602aaed1a98c880999e19b23c504e3361dd3ddc41d157601ce8d4630",
  "rowCount": 1,
  "partitions": {},
  "createdAt": "2026-11-02T00:00:00+00:00",
  "rows": [
    {
      "id": "row-1",
      "sourceRow": 1,
      "smiles": "CCO",
      "target": 46.069,
      "unit": "g/mol",
      "method": "published_calculation",
      "property": "molecular_weight",
      "conditions": {},
      "originalSmiles": "CCO",
      "identity": "CCO",
      "scaffold": "CCO"
    }
  ],
  "previewTruncated": false,
  "splits": {}
}
```

**Failure response example:** Retained source must explicitly allow training.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "errors": [
    {
      "code": "DATA_RIGHTS_UNKNOWN",
      "message": "Retained source must explicitly allow training",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [source_dataset](contracts-learning.md#source_dataset), [LearningWorkspaceService.import_retained_dataset](contracts-learning.md#learningworkspaceserviceimport_retained_dataset), [LearningWorkspaceService._dataset](contracts-learning.md#learningworkspaceservice_dataset).

Source: `services/studio-api/src/studio/api/learning_workspace.py:198` (`source_dataset`).

## POST /api/learning-workspace/datasets/import

Parse and retain a private custom dataset.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** JSON name, dataKind, content, format and rights; optional source, mapping, metadataColumns and row metadata. Supported row kinds/formats, normalization, lineage and group-safe splitting are enforced by the linked parser.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `payload` (required) | JSON body | `dict[str, Any]` | `required` |

**Response:** Dataset descriptor: id, name, state, dataKind, rights, report, source, digest, rowCount, partitions and createdAt; detail responses add at most 200 preview rows, previewTruncated and splits. See _dataset for conditional fields. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/learning-workspace/datasets/import HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "name": "Synthetic assistant examples",
  "format": "jsonl",
  "dataKind": "synthetic",
  "rights": "owned",
  "source": {
    "kind": "documentation_fixture"
  },
  "content": "{\"prompt\": \"First synthetic question\", \"response\": \"First synthetic answer\", \"documentId\": \"doc-a\"}\n{\"prompt\": \"Second synthetic question\", \"response\": \"Second synthetic answer\", \"documentId\": \"doc-b\"}\n{\"prompt\": \"Third synthetic question\", \"response\": \"Third synthetic answer\", \"documentId\": \"doc-c\"}"
}
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000011",
  "name": "Synthetic assistant examples",
  "state": "validated",
  "dataKind": "synthetic",
  "rights": "owned",
  "report": {
    "total": 3,
    "accepted": 3,
    "rejected": 0,
    "duplicates": 0,
    "rejections": [],
    "rowKinds": {
      "assistant": 3
    },
    "validation": "structure_and_schema",
    "scientificStatus": "not_validated"
  },
  "source": {
    "kind": "documentation_fixture"
  },
  "digest": "5b731741ec23484b524eed160bfa40600d5f7b2d8bf1f533ecb6e6764ba8a12f",
  "rowCount": 3,
  "partitions": {},
  "createdAt": "2026-11-02T00:00:00+00:00",
  "rows": [
    {
      "id": "row-1",
      "sourceRow": 1,
      "prompt": "First synthetic question",
      "response": "First synthetic answer",
      "documentId": "doc-a"
    },
    {
      "id": "row-2",
      "sourceRow": 2,
      "prompt": "Second synthetic question",
      "response": "Second synthetic answer",
      "documentId": "doc-b"
    },
    {
      "id": "row-3",
      "sourceRow": 3,
      "prompt": "Third synthetic question",
      "response": "Third synthetic answer",
      "documentId": "doc-c"
    }
  ],
  "previewTruncated": false,
  "splits": {}
}
```

**Failure response example:** content must be UTF-8 text.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "errors": [
    {
      "code": "VALIDATION",
      "message": "content must be UTF-8 text",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [import_dataset](contracts-learning.md#import_dataset), [LearningWorkspaceService.import_dataset](contracts-learning.md#learningworkspaceserviceimport_dataset), [LearningWorkspaceService._dataset](contracts-learning.md#learningworkspaceservice_dataset), [validate_import](contracts-learning.md#validate_import).

Source: `services/studio-api/src/studio/api/learning_workspace.py:34` (`import_dataset`).

## POST /api/learning-workspace/datasets/upload

Import a UTF-8 dataset file with JSON metadata.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** Multipart file plus metadata JSON string (same fields as JSON import except content). Maximum 20 MiB. UTF-8 BOM accepted. Filename supplies default name and format.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `file` (required) | multipart | `Annotated[UploadFile, File()]` | `required` |
| `metadata` (optional) | multipart | `str` | `Form('{}')` |

**Response:** Dataset descriptor: id, name, state, dataKind, rights, report, source, digest, rowCount, partitions and createdAt; detail responses add at most 200 preview rows, previewTruncated and splits. See _dataset for conditional fields. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/learning-workspace/datasets/upload HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: multipart/form-data; boundary=studio-documentation-boundary

--studio-documentation-boundary
Content-Disposition: form-data; name="metadata"

{"name": "Synthetic assistant examples", "format": "jsonl", "dataKind": "synthetic", "rights": "owned", "source": {"kind": "documentation_fixture"}}
--studio-documentation-boundary
Content-Disposition: form-data; name="file"; filename="examples.jsonl"
Content-Type: application/jsonl

{"prompt": "First synthetic question", "response": "First synthetic answer", "documentId": "doc-a"}
{"prompt": "Second synthetic question", "response": "Second synthetic answer", "documentId": "doc-b"}
{"prompt": "Third synthetic question", "response": "Third synthetic answer", "documentId": "doc-c"}
--studio-documentation-boundary--
```

**Success response example:** The UTF-8 file contains the same three synthetic JSONL rows as datasets/import; a real multipart client emits CRLF boundaries.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000011",
  "name": "Synthetic assistant examples",
  "state": "validated",
  "dataKind": "synthetic",
  "rights": "owned",
  "report": {
    "total": 3,
    "accepted": 3,
    "rejected": 0,
    "duplicates": 0,
    "rejections": [],
    "rowKinds": {
      "assistant": 3
    },
    "validation": "structure_and_schema",
    "scientificStatus": "not_validated"
  },
  "source": {
    "kind": "documentation_fixture"
  },
  "digest": "5b731741ec23484b524eed160bfa40600d5f7b2d8bf1f533ecb6e6764ba8a12f",
  "rowCount": 3,
  "partitions": {},
  "createdAt": "2026-11-02T00:00:00+00:00",
  "rows": [
    {
      "id": "row-1",
      "sourceRow": 1,
      "prompt": "First synthetic question",
      "response": "First synthetic answer",
      "documentId": "doc-a"
    },
    {
      "id": "row-2",
      "sourceRow": 2,
      "prompt": "Second synthetic question",
      "response": "Second synthetic answer",
      "documentId": "doc-b"
    },
    {
      "id": "row-3",
      "sourceRow": 3,
      "prompt": "Third synthetic question",
      "response": "Third synthetic answer",
      "documentId": "doc-c"
    }
  ],
  "previewTruncated": false,
  "splits": {}
}
```

**Failure response example:** Upload requires UTF-8 content and JSON metadata.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "errors": [
    {
      "code": "VALIDATION",
      "message": "Upload requires UTF-8 content and JSON metadata",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [upload_dataset](contracts-learning.md#upload_dataset), [LearningWorkspaceService.import_dataset](contracts-learning.md#learningworkspaceserviceimport_dataset), [LearningWorkspaceService._dataset](contracts-learning.md#learningworkspaceservice_dataset), [validate_import](contracts-learning.md#validate_import).

Source: `services/studio-api/src/studio/api/learning_workspace.py:43` (`upload_dataset`).

## POST /api/learning-workspace/datasets/{identifier}/freeze

Freeze and split a dataset for reproducible training.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No body; identifier is required for a single dataset.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `identifier` (required) | path | `str` | `required` |

**Response:** Dataset descriptor: id, name, state, dataKind, rights, report, source, digest, rowCount, partitions and createdAt; detail responses add at most 200 preview rows, previewTruncated and splits. See _dataset for conditional fields. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/learning-workspace/datasets/00000000-0000-4000-8000-000000000011/freeze HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** The owned dataset has resolved training rights and the three independent document groups shown in the import example.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000011",
  "name": "Synthetic assistant examples",
  "state": "frozen",
  "dataKind": "synthetic",
  "rights": "owned",
  "report": {
    "total": 3,
    "accepted": 3,
    "rejected": 0,
    "duplicates": 0,
    "rejections": [],
    "rowKinds": {
      "assistant": 3
    },
    "validation": "structure_and_schema",
    "scientificStatus": "not_validated"
  },
  "source": {
    "kind": "documentation_fixture"
  },
  "digest": "30affb02e05a8dae705fce7afb61e567464794ef715f6358b056ee5ce91212cc",
  "rowCount": 3,
  "partitions": {
    "train": 1,
    "development": 1,
    "final": 1
  },
  "createdAt": "2026-11-02T00:00:00+00:00",
  "rows": [
    {
      "id": "row-1",
      "sourceRow": 1,
      "prompt": "First synthetic question",
      "response": "First synthetic answer",
      "documentId": "doc-a"
    },
    {
      "id": "row-2",
      "sourceRow": 2,
      "prompt": "Second synthetic question",
      "response": "Second synthetic answer",
      "documentId": "doc-b"
    },
    {
      "id": "row-3",
      "sourceRow": 3,
      "prompt": "Third synthetic question",
      "response": "Third synthetic answer",
      "documentId": "doc-c"
    }
  ],
  "previewTruncated": false,
  "splits": {
    "row-1": "train",
    "row-2": "development",
    "row-3": "final"
  }
}
```

**Failure response example:** Resolve training rights before freezing.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "errors": [
    {
      "code": "DATA_RIGHTS_UNKNOWN",
      "message": "Resolve training rights before freezing",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [freeze_dataset](contracts-learning.md#freeze_dataset), [LearningWorkspaceService.freeze_dataset](contracts-learning.md#learningworkspaceservicefreeze_dataset), [LearningWorkspaceService._dataset](contracts-learning.md#learningworkspaceservice_dataset).

Source: `services/studio-api/src/studio/api/learning_workspace.py:75` (`freeze_dataset`).

## POST /api/learning-workspace/jobs

Validate, budget and queue a durable learning job.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** kind, datasetId, optional modelId/name/workflowId and config. Config includes executionTarget (local/remote), device, maxSteps, batchSize, maxTokens, maxSeconds, saveEvery, seed, rank, learningRate and kind-specific options. Dataset must be frozen and authorized. The exact kind/backend matrix, bounds, evaluation and storage checks are in _prepare_job.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `payload` (required) | JSON body | `dict[str, Any]` | `required` |

**Response:** Job descriptor: id, name, kind, state, datasetId, modelId, config, result, events (latest 100), error, attempt, cancelRequested, createdAt, updatedAt and elapsedSeconds. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/learning-workspace/jobs HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "name": "Synthetic remote assistant adaptation",
  "datasetId": "00000000-0000-4000-8000-000000000011",
  "modelId": "00000000-0000-4000-8000-000000000012",
  "kind": "sft",
  "config": {
    "executionTarget": "remote",
    "device": "cpu",
    "maxSteps": 20
  }
}
```

**Success response example:** The frozen three-group dataset and declared ready model pass admission; a compatible owner-authenticated worker must still lease this remote job. No successful training is implied.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000013",
  "name": "Synthetic remote assistant adaptation",
  "kind": "sft",
  "state": "queued",
  "datasetId": "00000000-0000-4000-8000-000000000011",
  "modelId": "00000000-0000-4000-8000-000000000012",
  "config": {
    "executionTarget": "remote",
    "device": "cpu",
    "backend": "transformers",
    "maxSteps": 20,
    "batchSize": 1,
    "maxTokens": 256,
    "maxSeconds": 3600,
    "saveEvery": 10,
    "seed": 0,
    "rank": 8,
    "numGenerations": 2,
    "ensembleSize": 2,
    "hiddenDim": 64,
    "depth": 2,
    "learningRate": 1e-05
  },
  "result": {
    "datasetDigest": "30affb02e05a8dae705fce7afb61e567464794ef715f6358b056ee5ce91212cc",
    "dataKind": "synthetic",
    "scientificStatus": "not_validated",
    "storagePreflight": {
      "available": true,
      "freeBytes": 21474836480,
      "requiredFreeBytes": 134217728
    },
    "preflight": {
      "ready": true,
      "checks": [
        {
          "id": "inputs",
          "status": "pass",
          "message": "Dataset rights, model compatibility and parameter validation passed"
        },
        {
          "id": "heldout",
          "status": "pass",
          "message": "Independent train and final groups are present"
        },
        {
          "id": "runtime",
          "status": "pass",
          "message": "Self-hosted worker selected; a compatible worker must claim the job"
        },
        {
          "id": "model",
          "status": "pass",
          "message": "Model asset is ready"
        },
        {
          "id": "disk",
          "status": "pass",
          "message": "Output storage is available"
        },
        {
          "id": "data_origin",
          "status": "warn",
          "message": "Synthetic labels retain their data origin; training does not establish experimental properties"
        }
      ],
      "normalizedConfig": {
        "executionTarget": "remote",
        "device": "cpu",
        "backend": "transformers",
        "maxSteps": 20,
        "batchSize": 1,
        "maxTokens": 256,
        "maxSeconds": 3600,
        "saveEvery": 10,
        "seed": 0,
        "rank": 8,
        "numGenerations": 2,
        "ensembleSize": 2,
        "hiddenDim": 64,
        "depth": 2,
        "learningRate": 1e-05
      },
      "estimated": {
        "available": true,
        "freeBytes": 21474836480,
        "requiredFreeBytes": 134217728
      },
      "dataset": {
        "id": "00000000-0000-4000-8000-000000000011",
        "state": "frozen",
        "trainingRows": 1,
        "developmentRows": 1,
        "finalRows": 1
      },
      "model": {
        "id": "00000000-0000-4000-8000-000000000012",
        "backend": "transformers",
        "state": "ready"
      }
    }
  },
  "events": [],
  "error": null,
  "attempt": 0,
  "cancelRequested": false,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00",
  "elapsedSeconds": null
}
```

**Failure response example:** Freeze the validated dataset before starting a job.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "errors": [
    {
      "code": "VALIDATION",
      "message": "Freeze the validated dataset before starting a job",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [create_job](contracts-learning.md#create_job), [LearningWorkspaceService.create_job](contracts-learning.md#learningworkspaceservicecreate_job), [LearningWorkspaceService._prepare_job](contracts-learning.md#learningworkspaceservice_prepare_job), [LearningWorkspaceService._job](contracts-learning.md#learningworkspaceservice_job).

Source: `services/studio-api/src/studio/api/learning_workspace.py:134` (`create_job`).

## POST /api/learning-workspace/jobs/preflight

Inspect training/evaluation readiness before queueing a job.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** kind, datasetId, optional modelId/name/workflowId and config. Config includes executionTarget (local/remote), device, maxSteps, batchSize, maxTokens, maxSeconds, saveEvery, seed, rank, learningRate and kind-specific options. Dataset must be frozen and authorized. The exact kind/backend matrix, bounds, evaluation and storage checks are in _prepare_job.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `payload` (required) | JSON body | `dict[str, Any]` | `required` |

**Response:** Readiness/preflight report: blockers/warnings, selected runtime/device, normalized configuration, storage estimates and compatibility checks. No training job is created. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/learning-workspace/jobs/preflight HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "name": "Synthetic remote assistant adaptation",
  "datasetId": "00000000-0000-4000-8000-000000000011",
  "modelId": "00000000-0000-4000-8000-000000000012",
  "kind": "sft",
  "config": {
    "executionTarget": "remote",
    "device": "cpu",
    "maxSteps": 20
  }
}
```

**Success response example:** Remote execution is explicit, current data rights and held-out partitions pass, and output storage is available. Values describe the synthetic scenario.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "ready": true,
  "checks": [
    {
      "id": "inputs",
      "status": "pass",
      "message": "Dataset rights, model compatibility and parameter validation passed"
    },
    {
      "id": "heldout",
      "status": "pass",
      "message": "Independent train and final groups are present"
    },
    {
      "id": "runtime",
      "status": "pass",
      "message": "Self-hosted worker selected; a compatible worker must claim the job"
    },
    {
      "id": "model",
      "status": "pass",
      "message": "Model asset is ready"
    },
    {
      "id": "disk",
      "status": "pass",
      "message": "Output storage is available"
    },
    {
      "id": "data_origin",
      "status": "warn",
      "message": "Synthetic labels retain their data origin; training does not establish experimental properties"
    }
  ],
  "normalizedConfig": {
    "executionTarget": "remote",
    "device": "cpu",
    "backend": "transformers",
    "maxSteps": 20,
    "batchSize": 1,
    "maxTokens": 256,
    "maxSeconds": 3600,
    "saveEvery": 10,
    "seed": 0,
    "rank": 8,
    "numGenerations": 2,
    "ensembleSize": 2,
    "hiddenDim": 64,
    "depth": 2,
    "learningRate": 1e-05
  },
  "estimated": {
    "available": true,
    "freeBytes": 21474836480,
    "requiredFreeBytes": 134217728
  },
  "dataset": {
    "id": "00000000-0000-4000-8000-000000000011",
    "state": "frozen",
    "trainingRows": 1,
    "developmentRows": 1,
    "finalRows": 1
  },
  "model": {
    "id": "00000000-0000-4000-8000-000000000012",
    "backend": "transformers",
    "state": "ready"
  }
}
```

**Failure response example:** The existing dataset has not been frozen; preflight reports a failed check inside its 200 response.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "ready": false,
  "checks": [
    {
      "id": "inputs",
      "status": "fail",
      "message": "Freeze the validated dataset before starting a job"
    }
  ],
  "normalizedConfig": {
    "executionTarget": "remote",
    "device": "cpu",
    "maxSteps": 20
  }
}
```

**Exact JSON rules and response serialization:** [job_preflight](contracts-learning.md#job_preflight), [LearningWorkspaceService.preflight_job](contracts-learning.md#learningworkspaceservicepreflight_job), [LearningWorkspaceService._prepare_job](contracts-learning.md#learningworkspaceservice_prepare_job).

Source: `services/studio-api/src/studio/api/learning_workspace.py:143` (`job_preflight`).

## POST /api/learning-workspace/jobs/{identifier}/cancel

Request learning job cancellation.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** identifier path parameter; no body.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `identifier` (required) | path | `str` | `required` |

**Response:** Job descriptor: id, name, kind, state, datasetId, modelId, config, result, events (latest 100), error, attempt, cancelRequested, createdAt, updatedAt and elapsedSeconds. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/learning-workspace/jobs/00000000-0000-4000-8000-000000000013/cancel HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** The example job is queued; running jobs instead first set cancelRequested and retain checkpoints.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000013",
  "name": "Synthetic remote assistant adaptation",
  "kind": "sft",
  "state": "cancelled",
  "datasetId": "00000000-0000-4000-8000-000000000011",
  "modelId": "00000000-0000-4000-8000-000000000012",
  "config": {
    "executionTarget": "remote",
    "device": "cpu",
    "backend": "transformers",
    "maxSteps": 20,
    "batchSize": 1,
    "maxTokens": 256,
    "maxSeconds": 3600,
    "saveEvery": 10,
    "seed": 0,
    "rank": 8,
    "numGenerations": 2,
    "ensembleSize": 2,
    "hiddenDim": 64,
    "depth": 2,
    "learningRate": 1e-05
  },
  "result": {
    "datasetDigest": "30affb02e05a8dae705fce7afb61e567464794ef715f6358b056ee5ce91212cc",
    "dataKind": "synthetic",
    "scientificStatus": "not_validated",
    "storagePreflight": {
      "available": true,
      "freeBytes": 21474836480,
      "requiredFreeBytes": 134217728
    },
    "preflight": {
      "ready": true,
      "checks": [
        {
          "id": "inputs",
          "status": "pass",
          "message": "Dataset rights, model compatibility and parameter validation passed"
        },
        {
          "id": "heldout",
          "status": "pass",
          "message": "Independent train and final groups are present"
        },
        {
          "id": "runtime",
          "status": "pass",
          "message": "Self-hosted worker selected; a compatible worker must claim the job"
        },
        {
          "id": "model",
          "status": "pass",
          "message": "Model asset is ready"
        },
        {
          "id": "disk",
          "status": "pass",
          "message": "Output storage is available"
        },
        {
          "id": "data_origin",
          "status": "warn",
          "message": "Synthetic labels retain their data origin; training does not establish experimental properties"
        }
      ],
      "normalizedConfig": {
        "executionTarget": "remote",
        "device": "cpu",
        "backend": "transformers",
        "maxSteps": 20,
        "batchSize": 1,
        "maxTokens": 256,
        "maxSeconds": 3600,
        "saveEvery": 10,
        "seed": 0,
        "rank": 8,
        "numGenerations": 2,
        "ensembleSize": 2,
        "hiddenDim": 64,
        "depth": 2,
        "learningRate": 1e-05
      },
      "estimated": {
        "available": true,
        "freeBytes": 21474836480,
        "requiredFreeBytes": 134217728
      },
      "dataset": {
        "id": "00000000-0000-4000-8000-000000000011",
        "state": "frozen",
        "trainingRows": 1,
        "developmentRows": 1,
        "finalRows": 1
      },
      "model": {
        "id": "00000000-0000-4000-8000-000000000012",
        "backend": "transformers",
        "state": "ready"
      }
    }
  },
  "events": [],
  "error": null,
  "attempt": 0,
  "cancelRequested": false,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00",
  "elapsedSeconds": null
}
```

**Failure response example:** The session cookie is omitted and no Bearer session token is supplied.

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "errors": [
    {
      "code": "UNAUTHENTICATED",
      "message": "session required",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [cancel](contracts-learning.md#cancel), [LearningWorkspaceService.cancel_job](contracts-learning.md#learningworkspaceservicecancel_job), [LearningWorkspaceService._job](contracts-learning.md#learningworkspaceservice_job).

Source: `services/studio-api/src/studio/api/learning_workspace.py:169` (`cancel`).

## POST /api/learning-workspace/jobs/{identifier}/resume

Resume an interrupted learning job from retained state/checkpoints.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** identifier path parameter; no body.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `identifier` (required) | path | `str` | `required` |

**Response:** Job descriptor: id, name, kind, state, datasetId, modelId, config, result, events (latest 100), error, attempt, cancelRequested, createdAt, updatedAt and elapsedSeconds. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/learning-workspace/jobs/00000000-0000-4000-8000-000000000013/resume HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** The remote-target job is stopped and current preflight succeeds; existing checkpoints remain available.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000013",
  "name": "Synthetic remote assistant adaptation",
  "kind": "sft",
  "state": "queued",
  "datasetId": "00000000-0000-4000-8000-000000000011",
  "modelId": "00000000-0000-4000-8000-000000000012",
  "config": {
    "executionTarget": "remote",
    "device": "cpu",
    "backend": "transformers",
    "maxSteps": 20,
    "batchSize": 1,
    "maxTokens": 256,
    "maxSeconds": 3600,
    "saveEvery": 10,
    "seed": 0,
    "rank": 8,
    "numGenerations": 2,
    "ensembleSize": 2,
    "hiddenDim": 64,
    "depth": 2,
    "learningRate": 1e-05
  },
  "result": {
    "datasetDigest": "30affb02e05a8dae705fce7afb61e567464794ef715f6358b056ee5ce91212cc",
    "dataKind": "synthetic",
    "scientificStatus": "not_validated",
    "storagePreflight": {
      "available": true,
      "freeBytes": 21474836480,
      "requiredFreeBytes": 134217728
    },
    "preflight": {
      "ready": true,
      "checks": [
        {
          "id": "inputs",
          "status": "pass",
          "message": "Dataset rights, model compatibility and parameter validation passed"
        },
        {
          "id": "heldout",
          "status": "pass",
          "message": "Independent train and final groups are present"
        },
        {
          "id": "runtime",
          "status": "pass",
          "message": "Self-hosted worker selected; a compatible worker must claim the job"
        },
        {
          "id": "model",
          "status": "pass",
          "message": "Model asset is ready"
        },
        {
          "id": "disk",
          "status": "pass",
          "message": "Output storage is available"
        },
        {
          "id": "data_origin",
          "status": "warn",
          "message": "Synthetic labels retain their data origin; training does not establish experimental properties"
        }
      ],
      "normalizedConfig": {
        "executionTarget": "remote",
        "device": "cpu",
        "backend": "transformers",
        "maxSteps": 20,
        "batchSize": 1,
        "maxTokens": 256,
        "maxSeconds": 3600,
        "saveEvery": 10,
        "seed": 0,
        "rank": 8,
        "numGenerations": 2,
        "ensembleSize": 2,
        "hiddenDim": 64,
        "depth": 2,
        "learningRate": 1e-05
      },
      "estimated": {
        "available": true,
        "freeBytes": 21474836480,
        "requiredFreeBytes": 134217728
      },
      "dataset": {
        "id": "00000000-0000-4000-8000-000000000011",
        "state": "frozen",
        "trainingRows": 1,
        "developmentRows": 1,
        "finalRows": 1
      },
      "model": {
        "id": "00000000-0000-4000-8000-000000000012",
        "backend": "transformers",
        "state": "ready"
      }
    }
  },
  "events": [],
  "error": null,
  "attempt": 0,
  "cancelRequested": false,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00",
  "elapsedSeconds": null
}
```

**Failure response example:** Only a stopped or blocked job can be resumed.

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "errors": [
    {
      "code": "CONFLICT",
      "message": "Only a stopped or blocked job can be resumed",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [resume](contracts-learning.md#resume), [LearningWorkspaceService.resume_job](contracts-learning.md#learningworkspaceserviceresume_job), [LearningWorkspaceService._job](contracts-learning.md#learningworkspaceservice_job).

Source: `services/studio-api/src/studio/api/learning_workspace.py:182` (`resume`).

## POST /api/learning-workspace/models

Register a local model or queue an approved catalog download.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** catalogId selects an approved catalog model; otherwise backend, location, name and license describe an existing local model. Optional repairModelId repairs a registration; workflowId attaches permitted workflow accounting. Backend, path and licenses are checked.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `payload` (required) | JSON body | `dict[str, Any]` | `required` |

**Response:** Model descriptor, with any download job reflected in details/state. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/learning-workspace/models HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "name": "Example local assistant",
  "backend": "transformers",
  "location": "/private/example-models/qwen3-0.6b",
  "license": "apache-2.0"
}
```

**Success response example:** The synthetic absolute directory must be replaced with an existing model directory containing config.json and safetensors weights. Registering this asset does not activate it.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000012",
  "name": "Example local assistant",
  "backend": "transformers",
  "location": "/private/example-models/qwen3-0.6b",
  "details": {
    "license": "apache-2.0",
    "state": "ready"
  },
  "createdAt": "2026-11-02T00:00:00+00:00"
}
```

**Failure response example:** Local model path does not exist.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "errors": [
    {
      "code": "VALIDATION",
      "message": "Local model path does not exist",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [register_model](contracts-learning.md#register_model), [LearningWorkspaceService.register_model](contracts-learning.md#learningworkspaceserviceregister_model), [LearningWorkspaceService._model](contracts-learning.md#learningworkspaceservice_model).

Source: `services/studio-api/src/studio/api/learning_workspace.py:87` (`register_model`).

## POST /api/learning-workspace/models/{identifier}/activate

Approve an independently evaluated model for private agent use.

**Access:** Authenticated human user; approved=true and an independently successful compatible evaluation are required.

**Request:** approved must be true and evaluationJobId must identify a compatible successful evaluation.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `identifier` (required) | path | `str` | `required` |
| `payload` (required) | JSON body | `dict[str, Any]` | `required` |

**Response:** Updated model descriptor with activation/evaluation state. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/learning-workspace/models/00000000-0000-4000-8000-000000000012/activate HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "approved": true,
  "evaluationJobId": "00000000-0000-4000-8000-000000000016"
}
```

**Success response example:** An authenticated human explicitly approves a ready candidate with a completed matching final held-out evaluation. Example metric values are synthetic software-test results.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000012",
  "name": "Example local assistant",
  "backend": "transformers",
  "location": "/private/example-models/qwen3-0.6b",
  "details": {
    "license": "apache-2.0",
    "state": "ready",
    "active": true,
    "review": {
      "decision": "approved",
      "reviewedBy": "00000000-0000-4000-8000-000000000002",
      "reviewedAt": "2026-11-02T00:00:00+00:00",
      "evaluationJobId": "00000000-0000-4000-8000-000000000016",
      "baselineExactMatch": 0.5,
      "candidateExactMatch": 0.75
    }
  },
  "createdAt": "2026-11-02T00:00:00+00:00"
}
```

**Failure response example:** A completed independent held-out evaluation of this model is required.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "errors": [
    {
      "code": "MODEL_NOT_PROMOTABLE",
      "message": "A completed independent held-out evaluation of this model is required",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [activate_model](contracts-learning.md#activate_model), [LearningWorkspaceService.activate_model](contracts-learning.md#learningworkspaceserviceactivate_model), [LearningWorkspaceService._model](contracts-learning.md#learningworkspaceservice_model).

Source: `services/studio-api/src/studio/api/learning_workspace.py:108` (`activate_model`).

## POST /api/learning-workspace/models/{identifier}/chat

Run private local model inference.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** messages array, optional tools and maxTokens (default 2048). The backend-specific message/tool interface is forwarded only after model readiness checks.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `identifier` (required) | path | `str` | `required` |
| `payload` (required) | JSON body | `dict[str, Any]` | `required` |

**Response:** OpenAI-style inference completion from the supported local backend; tool support depends on backend. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/learning-workspace/models/00000000-0000-4000-8000-000000000012/chat HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "messages": [
    {
      "role": "user",
      "content": "State one question to check against the source."
    }
  ],
  "tools": [],
  "maxTokens": 64
}
```

**Success response example:** A ready local assistant and runtime generate this illustrative text; tool calls, if returned, must match the supplied catalog.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "Example local model answer."
      }
    }
  ],
  "model": "00000000-0000-4000-8000-000000000012"
}
```

**Failure response example:** Select a ready assistant model.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "errors": [
    {
      "code": "MODEL_INCOMPATIBLE",
      "message": "Select a ready assistant model",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [model_chat](contracts-learning.md#model_chat), [LearningWorkspaceService.infer_model](contracts-learning.md#learningworkspaceserviceinfer_model).

Source: `services/studio-api/src/studio/api/learning_workspace.py:117` (`model_chat`).

## POST /api/learning-workspace/models/{identifier}/preview

Run a bounded local model preview.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** prompt text required; optional maxTokens defaults to 128 and is clamped to 1–512.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `identifier` (required) | path | `str` | `required` |
| `payload` (required) | JSON body | `dict[str, Any]` | `required` |

**Response:** Preview completion/output and timing/runtime metadata; runtime must be available. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/learning-workspace/models/00000000-0000-4000-8000-000000000012/preview HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "prompt": "State one question to check against the source.",
  "maxTokens": 64
}
```

**Success response example:** The registered model and local Transformers runtime are available; generated text is illustrative, not a qualified chemistry answer.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "ok": true,
  "text": "Example local model answer.",
  "backend": "transformers"
}
```

**Failure response example:** Install the model's local runtime to preview it.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "errors": [
    {
      "code": "ENGINE_UNAVAILABLE",
      "message": "Install the model's local runtime to preview it",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [preview](contracts-learning.md#preview), [LearningWorkspaceService.preview_model](contracts-learning.md#learningworkspaceservicepreview_model).

Source: `services/studio-api/src/studio/api/learning_workspace.py:96` (`preview`).

## POST /api/learning-workspace/worker/jobs/{identifier}/complete

Finalize a leased worker attempt and retain bounded artifacts.

**Access:** Authenticated session principal; all leases/jobs are restricted to its workspace and owner ID. The supported CLI uses an existing trusted owner/user session token, not an unauthenticated worker identity.

**Request:** Multipart file (ZIP) and metadata JSON string containing workerId and result. Archive paths, total size, expected owner/lease, result schema and cancellation are checked.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `identifier` (required) | path | `str` | `required` |
| `file` (required) | multipart | `Annotated[UploadFile, File()]` | `required` |
| `metadata` (required) | multipart | `str` | `Form(...)` |

**Response:** Updated learning job/result state; uploaded artifacts are retained after validation. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/learning-workspace/worker/jobs/00000000-0000-4000-8000-000000000013/complete HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: multipart/form-data; boundary=studio-documentation-boundary

--studio-documentation-boundary
Content-Disposition: form-data; name="metadata"

{"workerId": "worker-docs-001", "result": {"ok": false, "error": "Example worker stopped"}}
--studio-documentation-boundary
Content-Disposition: form-data; name="file"; filename="checkpoint.zip"
Content-Type: application/zip


--studio-documentation-boundary--
```

**Success response example:** An owned live worker lease reports a failed attempt with an empty file part. HTTP 200 acknowledges retaining that terminal result; it does not mean training succeeded. Real multipart requests use CRLF boundaries.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000013",
  "name": "Synthetic remote assistant adaptation",
  "kind": "sft",
  "state": "failed",
  "datasetId": "00000000-0000-4000-8000-000000000011",
  "modelId": "00000000-0000-4000-8000-000000000012",
  "config": {
    "executionTarget": "remote",
    "device": "cpu",
    "backend": "transformers",
    "maxSteps": 20,
    "batchSize": 1,
    "maxTokens": 256,
    "maxSeconds": 3600,
    "saveEvery": 10,
    "seed": 0,
    "rank": 8,
    "numGenerations": 2,
    "ensembleSize": 2,
    "hiddenDim": 64,
    "depth": 2,
    "learningRate": 1e-05
  },
  "result": {
    "datasetDigest": "30affb02e05a8dae705fce7afb61e567464794ef715f6358b056ee5ce91212cc",
    "dataKind": "synthetic",
    "scientificStatus": "not_validated",
    "storagePreflight": {
      "available": true,
      "freeBytes": 21474836480,
      "requiredFreeBytes": 134217728
    },
    "preflight": {
      "ready": true,
      "checks": [
        {
          "id": "inputs",
          "status": "pass",
          "message": "Dataset rights, model compatibility and parameter validation passed"
        },
        {
          "id": "heldout",
          "status": "pass",
          "message": "Independent train and final groups are present"
        },
        {
          "id": "runtime",
          "status": "pass",
          "message": "Self-hosted worker selected; a compatible worker must claim the job"
        },
        {
          "id": "model",
          "status": "pass",
          "message": "Model asset is ready"
        },
        {
          "id": "disk",
          "status": "pass",
          "message": "Output storage is available"
        },
        {
          "id": "data_origin",
          "status": "warn",
          "message": "Synthetic labels retain their data origin; training does not establish experimental properties"
        }
      ],
      "normalizedConfig": {
        "executionTarget": "remote",
        "device": "cpu",
        "backend": "transformers",
        "maxSteps": 20,
        "batchSize": 1,
        "maxTokens": 256,
        "maxSeconds": 3600,
        "saveEvery": 10,
        "seed": 0,
        "rank": 8,
        "numGenerations": 2,
        "ensembleSize": 2,
        "hiddenDim": 64,
        "depth": 2,
        "learningRate": 1e-05
      },
      "estimated": {
        "available": true,
        "freeBytes": 21474836480,
        "requiredFreeBytes": 134217728
      },
      "dataset": {
        "id": "00000000-0000-4000-8000-000000000011",
        "state": "frozen",
        "trainingRows": 1,
        "developmentRows": 1,
        "finalRows": 1
      },
      "model": {
        "id": "00000000-0000-4000-8000-000000000012",
        "backend": "transformers",
        "state": "ready"
      }
    },
    "ok": false,
    "error": "Example worker stopped",
    "backend": "transformers",
    "artifacts": [],
    "execution": "authenticated_remote_worker",
    "baseLocation": "/private/example-models/qwen3-0.6b",
    "adapterPath": "/private/example-vault/00000000-0000-4000-8000-000000000001/learning/00000000-0000-4000-8000-000000000002/jobs/00000000-0000-4000-8000-000000000013/output"
  },
  "events": [],
  "error": "Example worker stopped",
  "attempt": 1,
  "cancelRequested": false,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00",
  "elapsedSeconds": null
}
```

**Failure response example:** Worker lease expired or does not own this job.

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "errors": [
    {
      "code": "CONFLICT",
      "message": "Worker lease expired or does not own this job",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [worker_complete](contracts-learning.md#worker_complete), [complete](contracts-learning.md#complete), [_leased](contracts-learning.md#_leased), [LearningWorkspaceService._job](contracts-learning.md#learningworkspaceservice_job).

Source: `services/studio-api/src/studio/api/learning_workspace.py:241` (`worker_complete`).

## POST /api/learning-workspace/worker/jobs/{identifier}/heartbeat

Refresh a worker lease and publish bounded progress events.

**Access:** Authenticated session principal; all leases/jobs are restricted to its workspace and owner ID. The supported CLI uses an existing trusted owner/user session token, not an unauthenticated worker identity.

**Request:** workerId and optional events array. Must match the active lease.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `identifier` (required) | path | `str` | `required` |
| `payload` (required) | JSON body | `dict[str, Any]` | `required` |

**Response:** cancelRequested and leaseSeconds=120. Revoked/unavailable dataset/model state can request cancellation. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/learning-workspace/worker/jobs/00000000-0000-4000-8000-000000000013/heartbeat HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "workerId": "worker-docs-001",
  "events": [
    {
      "type": "progress",
      "step": 1
    }
  ]
}
```

**Success response example:** This worker owns the current unexpired running-job lease.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "cancelRequested": false,
  "leaseSeconds": 120
}
```

**Failure response example:** Worker lease expired or does not own this job.

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "errors": [
    {
      "code": "CONFLICT",
      "message": "Worker lease expired or does not own this job",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [worker_heartbeat](contracts-learning.md#worker_heartbeat), [heartbeat](contracts-learning.md#heartbeat), [_leased](contracts-learning.md#_leased), [_worker_id](contracts-learning.md#_worker_id).

Source: `services/studio-api/src/studio/api/learning_workspace.py:218` (`worker_heartbeat`).

## POST /api/learning-workspace/worker/lease

Lease an eligible remote-target training job.

**Access:** Authenticated session principal; all leases/jobs are restricted to its workspace and owner ID. The supported CLI uses an existing trusted owner/user session token, not an unauthenticated worker identity.

**Request:** workerId and backends array. Only matching queued jobs pass dataset egress, ownership, model and lease checks.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `payload` (required) | JSON body | `dict[str, Any]` | `required` |

**Response:** jobId=null when no job matches; otherwise jobId, request, leaseSeconds=120 and resumeAvailable. Host filesystem model paths are removed from requests. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/learning-workspace/worker/lease HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "workerId": "worker-docs-001",
  "backends": [
    "transformers",
    "chemprop"
  ]
}
```

**Success response example:** There is no compatible queued remote job. A nonempty lease additionally returns request, leaseSeconds=120 and resumeAvailable.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "jobId": null
}
```

**Failure response example:** workerId must contain 8-100 letters, numbers or ._-.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "errors": [
    {
      "code": "VALIDATION",
      "message": "workerId must contain 8-100 letters, numbers or ._-",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [worker_lease](contracts-learning.md#worker_lease), [lease](contracts-learning.md#lease), [_worker_id](contracts-learning.md#_worker_id).

Source: `services/studio-api/src/studio/api/learning_workspace.py:207` (`worker_lease`).
