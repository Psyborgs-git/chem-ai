# Local learning and worker API — JSON contract details

These excerpts are generated from the implementation without importing it. They specify accepted fields, conditional validation, defaults and response construction for flexible JSON interfaces. They complement the endpoint prose; implementation expressions refer to the named source service rather than a live execution.

## activate_model

Source: `services/studio-api/src/studio/api/learning_workspace.py:activate_model`.

```python
@router.post("/models/{identifier}/activate")
def activate_model(
    identifier: str, payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).activate_model(identifier, payload)
    db.commit()
    return result
```

## artifact

Source: `services/studio-api/src/studio/api/learning_workspace.py:artifact`.

```python
@router.get("/jobs/{identifier}/artifacts/{name:path}")
def artifact(identifier: str, name: str, request: Request, db: DbSession, ctx: Ctx) -> FileResponse:
    path = _service(request, db, ctx).artifact_path(identifier, name)
    return FileResponse(path, media_type="application/octet-stream", filename=path.name)
```

## cancel

Source: `services/studio-api/src/studio/api/learning_workspace.py:cancel`.

```python
@router.post("/jobs/{identifier}/cancel")
def cancel(identifier: str, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = _service(request, db, ctx).cancel_job(identifier)
    db.commit()
    return result
```

## capabilities

Source: `services/studio-api/src/studio/api/learning_workspace.py:capabilities`.

```python
@router.get("/capabilities")
def capabilities(request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return _service(request, db, ctx).catalog()
```

## create_job

Source: `services/studio-api/src/studio/api/learning_workspace.py:create_job`.

```python
@router.post("/jobs")
def create_job(
    payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).create_job(payload)
    db.commit()
    return result
```

## dataset

Source: `services/studio-api/src/studio/api/learning_workspace.py:dataset`.

```python
@router.get("/datasets/{identifier}")
def dataset(identifier: str, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return _service(request, db, ctx).get_dataset(identifier)
```

## datasets

Source: `services/studio-api/src/studio/api/learning_workspace.py:datasets`.

```python
@router.get("/datasets")
def datasets(request: Request, db: DbSession, ctx: Ctx) -> list[dict[str, Any]]:
    return _service(request, db, ctx).list_datasets()
```

## default_job_preflight

Source: `services/studio-api/src/studio/api/learning_workspace.py:default_job_preflight`.

```python
@router.get("/jobs/preflight")
def default_job_preflight(
    request: Request,
    db: DbSession,
    ctx: Ctx,
    datasetId: str,
    kind: str = "sft",
    modelId: str | None = None,
) -> dict[str, Any]:
    return _service(request, db, ctx).preflight_job(
        {"datasetId": datasetId, "kind": kind, "modelId": modelId}
    )
```

## freeze_dataset

Source: `services/studio-api/src/studio/api/learning_workspace.py:freeze_dataset`.

```python
@router.post("/datasets/{identifier}/freeze")
def freeze_dataset(identifier: str, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = _service(request, db, ctx).freeze_dataset(identifier)
    db.commit()
    return result
```

## import_dataset

Source: `services/studio-api/src/studio/api/learning_workspace.py:import_dataset`.

```python
@router.post("/datasets/import")
def import_dataset(
    payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).import_dataset(payload)
    db.commit()
    return result
```

## job

Source: `services/studio-api/src/studio/api/learning_workspace.py:job`.

```python
@router.get("/jobs/{identifier}")
def job(identifier: str, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return _service(request, db, ctx).get_job(identifier)
```

## job_preflight

Source: `services/studio-api/src/studio/api/learning_workspace.py:job_preflight`.

```python
@router.post("/jobs/preflight")
def job_preflight(
    payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    return _service(request, db, ctx).preflight_job(payload)
```

## jobs

Source: `services/studio-api/src/studio/api/learning_workspace.py:jobs`.

```python
@router.get("/jobs")
def jobs(request: Request, db: DbSession, ctx: Ctx) -> list[dict[str, Any]]:
    return _service(request, db, ctx).list_jobs()
```

## model

Source: `services/studio-api/src/studio/api/learning_workspace.py:model`.

```python
@router.get("/models/{identifier}")
def model(identifier: str, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return _service(request, db, ctx).get_model(identifier)
```

## model_chat

Source: `services/studio-api/src/studio/api/learning_workspace.py:model_chat`.

```python
@router.post("/models/{identifier}/chat")
def model_chat(
    identifier: str, payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    return _service(request, db, ctx).infer_model(
        identifier,
        payload.get("messages", []),
        payload.get("tools"),
        int(payload.get("maxTokens", 2048)),
    )
```

## models

Source: `services/studio-api/src/studio/api/learning_workspace.py:models`.

```python
@router.get("/models")
def models(request: Request, db: DbSession, ctx: Ctx) -> list[dict[str, Any]]:
    return _service(request, db, ctx).list_models()
```

## notebook_dataset

Source: `services/studio-api/src/studio/api/learning_workspace.py:notebook_dataset`.

```python
@router.post("/datasets/from-notebook")
def notebook_dataset(
    payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).import_notebook(payload)
    db.commit()
    return result
```

## preview

Source: `services/studio-api/src/studio/api/learning_workspace.py:preview`.

```python
@router.post("/models/{identifier}/preview")
def preview(
    identifier: str, payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    return _service(request, db, ctx).preview_model(identifier, payload)
```

## register_model

Source: `services/studio-api/src/studio/api/learning_workspace.py:register_model`.

```python
@router.post("/models")
def register_model(
    payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).register_model(payload)
    db.commit()
    return result
```

## resume

Source: `services/studio-api/src/studio/api/learning_workspace.py:resume`.

```python
@router.post("/jobs/{identifier}/resume")
def resume(identifier: str, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = _service(request, db, ctx).resume_job(identifier)
    db.commit()
    return result
```

## source_dataset

Source: `services/studio-api/src/studio/api/learning_workspace.py:source_dataset`.

```python
@router.post("/datasets/from-source")
def source_dataset(
    payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).import_retained_dataset(payload)
    db.commit()
    return result
```

## upload_dataset

Source: `services/studio-api/src/studio/api/learning_workspace.py:upload_dataset`.

```python
@router.post("/datasets/upload")
async def upload_dataset(
    request: Request,
    db: DbSession,
    ctx: Ctx,
    file: Annotated[UploadFile, File()],
    metadata: str = Form("{}"),
) -> dict[str, Any]:
    content = await file.read(MAX_DATASET_BYTES + 1)
    if len(content) > MAX_DATASET_BYTES:
        raise DomainError(ErrorCode.VALIDATION, "Dataset exceeds the 20 MiB import limit")
    try:
        payload = json.loads(metadata)
        if not isinstance(payload, dict):
            raise ValueError("metadata must be a JSON object")
        payload["content"] = content.decode("utf-8-sig")
    except (ValueError, UnicodeDecodeError) as exc:
        raise DomainError(
            ErrorCode.VALIDATION, "Upload requires UTF-8 content and JSON metadata"
        ) from exc
    payload.setdefault("name", file.filename or "Imported dataset")
    payload.setdefault("format", (file.filename or "data.csv").rsplit(".", 1)[-1])
    result = _service(request, db, ctx).import_dataset(payload)
    db.commit()
    return result
```

## worker_checkpoint

Source: `services/studio-api/src/studio/api/learning_workspace.py:worker_checkpoint`.

```python
@router.get("/worker/jobs/{identifier}/checkpoint")
def worker_checkpoint(
    identifier: str, workerId: str, request: Request, db: DbSession, ctx: Ctx
) -> Response:
    from studio.domain.learning.workspace_runtime.remote import checkpoint_archive

    return Response(
        checkpoint_archive(_service(request, db, ctx), identifier, workerId),
        media_type="application/zip",
    )
```

## worker_complete

Source: `services/studio-api/src/studio/api/learning_workspace.py:worker_complete`.

```python
@router.post("/worker/jobs/{identifier}/complete")
async def worker_complete(
    identifier: str,
    request: Request,
    db: DbSession,
    ctx: Ctx,
    file: Annotated[UploadFile, File()],
    metadata: str = Form(...),
) -> dict[str, Any]:
    from studio.domain.learning.workspace_runtime.remote import MAX_ARTIFACT_BYTES, complete

    content = await file.read(MAX_ARTIFACT_BYTES + 1)
    try:
        payload = json.loads(metadata)
        if not isinstance(payload, dict):
            raise ValueError("metadata must be a JSON object")
    except ValueError as exc:
        raise DomainError(ErrorCode.VALIDATION, "Invalid worker completion metadata") from exc
    result = complete(_service(request, db, ctx), identifier, payload, content)
    db.commit()
    return result
```

## worker_heartbeat

Source: `services/studio-api/src/studio/api/learning_workspace.py:worker_heartbeat`.

```python
@router.post("/worker/jobs/{identifier}/heartbeat")
def worker_heartbeat(
    identifier: str, payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    from studio.domain.learning.workspace_runtime.remote import heartbeat

    result = heartbeat(_service(request, db, ctx), identifier, payload)
    db.commit()
    return result
```

## worker_lease

Source: `services/studio-api/src/studio/api/learning_workspace.py:worker_lease`.

```python
@router.post("/worker/lease")
def worker_lease(
    payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    from studio.domain.learning.workspace_runtime.remote import lease

    result = lease(_service(request, db, ctx), payload)
    db.commit()
    return result
```

## worker_model

Source: `services/studio-api/src/studio/api/learning_workspace.py:worker_model`.

```python
@router.get("/worker/jobs/{identifier}/model")
def worker_model(
    identifier: str, workerId: str, request: Request, db: DbSession, ctx: Ctx
) -> Response:
    from studio.domain.learning.workspace_runtime.remote import model_archive

    return Response(
        model_archive(_service(request, db, ctx), identifier, workerId),
        media_type="application/zip",
    )
```

## LearningWorkspaceService._dataset

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService._dataset`.

```python
    def _dataset(self, row: LearningDataset, *, full: bool = False) -> dict[str, Any]:
        value = {
            "id": str(row.id),
            "name": row.name,
            "state": row.state,
            "dataKind": row.data_kind,
            "rights": row.rights,
            "report": row.report,
            "source": row.source,
            "digest": row.digest,
            "rowCount": len(row.rows),
            "partitions": dict(Counter(row.splits.values())),
            "createdAt": _time(row.created_at),
        }
        if full:
            value.update(
                {
                    "rows": row.rows[:200],
                    "previewTruncated": len(row.rows) > 200,
                    "splits": row.splits,
                }
            )
        return value
```

## LearningWorkspaceService._job

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService._job`.

```python
    def _job(self, row: LearningJob) -> dict[str, Any]:
        elapsed = row.result.get("elapsedSeconds")
        if row.state == "running" and row.result.get("attemptStartedAt"):
            try:
                started = datetime.fromisoformat(row.result["attemptStartedAt"])
                elapsed = float(row.result.get("elapsedBeforeAttempt", 0)) + max(
                    0, (datetime.now(UTC) - started).total_seconds()
                )
            except (TypeError, ValueError):
                pass
        return {
            "id": str(row.id),
            "name": row.name,
            "kind": row.kind,
            "state": row.state,
            "datasetId": str(row.dataset_id) if row.dataset_id else None,
            "modelId": str(row.model_id) if row.model_id else None,
            "config": row.config,
            "result": row.result,
            "events": row.events[-100:],
            "error": row.error,
            "attempt": row.attempt,
            "cancelRequested": row.cancel_requested,
            "createdAt": _time(row.created_at),
            "updatedAt": _time(row.updated_at),
            "elapsedSeconds": elapsed,
        }
```

## LearningWorkspaceService._model

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService._model`.

```python
    def _model(self, row: LearningModel) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "name": row.name,
            "backend": row.backend,
            "location": row.location,
            "details": row.details,
            "createdAt": _time(row.created_at),
        }
```

## LearningWorkspaceService._prepare_job

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService._prepare_job`.

```python
    def _prepare_job(
        self, payload: dict[str, Any]
    ) -> tuple[str, LearningDataset, LearningModel | None, dict[str, Any]]:
        kind = payload.get("kind", "sft")
        if kind not in KINDS:
            raise DomainError(ErrorCode.VALIDATION, "Unknown learning job kind")
        dataset = self._owned(LearningDataset, str(payload.get("datasetId", "")))
        if dataset.state != "frozen":
            raise DomainError(
                ErrorCode.VALIDATION, "Freeze the validated dataset before starting a job"
            )
        check_dataset_sources(self.db, dataset)
        self.authorize_dataset_training(str(dataset.id))
        model = (
            self._owned(LearningModel, str(payload["modelId"])) if payload.get("modelId") else None
        )
        if kind != "chemprop" and model is None:
            raise DomainError(ErrorCode.VALIDATION, "Select a local model for this job")
        if model and model.details.get("license", "unknown") == "unknown":
            raise DomainError(
                ErrorCode.DATA_RIGHTS_UNKNOWN, "Declare the base model's license before training"
            )
        raw_config = payload.get("config") or {}
        if not isinstance(raw_config, dict):
            raise DomainError(ErrorCode.VALIDATION, "config must be a JSON object")
        config = dict(raw_config)
        if config.get("executionTarget", "local") not in {"local", "remote"}:
            raise DomainError(ErrorCode.VALIDATION, "executionTarget must be local or remote")
        if kind == "chemprop" and "epochs" in config:
            config["maxSteps"] = config["epochs"]
        backend = "chemprop" if kind == "chemprop" else (model.backend if model else "transformers")
        config["backend"] = backend
        device = config.get("device", "auto")
        if device not in {"auto", "cpu", "cuda", "mps"}:
            raise DomainError(ErrorCode.VALIDATION, "device must be auto, cpu, cuda or mps")
        if backend == "mlx" and device not in {"auto", "mps"}:
            raise DomainError(
                ErrorCode.ENGINE_UNSUPPORTED_INPUT, "MLX training uses Metal; choose auto or mps"
            )
        try:
            for name, default, lower, upper in [
                ("maxSteps", 20, 1, 100_000),
                ("batchSize", 1, 1, 128),
                ("maxTokens", 256, 16, 8192),
                ("maxSeconds", 3600, 10, 86_400),
                ("saveEvery", 10, 1, 1000),
                ("seed", 0, 0, 2**31 - 1),
                ("rank", 8, 1, 128),
                ("numGenerations", 2, 2, 16),
                ("ensembleSize", 2, 1, 8),
                ("hiddenDim", 64, 32, 2048),
                ("depth", 2, 1, 12),
            ]:
                value = int(config.get(name, default))
                if not lower <= value <= upper:
                    raise ValueError(f"{name} must be between {lower} and {upper}")
                config[name] = value
            learning_rate = float(config.get("learningRate", 1e-5))
            if not 0 < learning_rate <= 0.01:
                raise ValueError("learningRate must be between 0 and 0.01")
            config["learningRate"] = learning_rate
        except (ValueError, TypeError) as exc:
            raise DomainError(ErrorCode.VALIDATION, str(exc)) from exc
        expected_backend = {
            "dpo": {"transformers"},
            "grpo": {"transformers"},
            "molecular_transfer": {"reinvent"},
            "molecular_rl": {"reinvent"},
            "predict": {"chemprop"},
            "evaluate": {"mlx", "transformers", "chemprop"},
            "sft": {"mlx", "transformers"},
            "chemprop": {"chemprop"},
        }
        if backend not in expected_backend[kind]:
            raise DomainError(
                ErrorCode.VALIDATION, f"{kind} is unsupported by the selected backend"
            )
        if kind == "molecular_transfer" and config["maxSteps"] > 1000:
            raise DomainError(
                ErrorCode.VALIDATION, "Molecular transfer supports at most 1000 epochs"
            )
        training_rows = [r for r in dataset.rows if dataset.splits.get(r["id"]) == "train"]
        if kind == "chemprop":
            if len(training_rows) > 20_000 or any(
                len(str(row.get("smiles", ""))) > 512 for row in dataset.rows
            ):
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "Property jobs support at most 20,000 train rows and 512-character SMILES",
                )
            task = config.get("propertyTask", "regression")
            if task not in {"regression", "classification"}:
                raise DomainError(
                    ErrorCode.VALIDATION, "propertyTask must be regression or classification"
                )
            if task == "classification":
                labels = {row["target"] for row in training_rows if "target" in row}
                if labels != {0.0, 1.0} or any(
                    row.get("target") not in {0.0, 1.0} for row in dataset.rows
                ):
                    raise DomainError(
                        ErrorCode.VALIDATION,
                        "Binary classification requires 0/1 labels and both classes "
                        "in the train partition",
                    )
            config["propertyTask"] = task
        needed = {
            "sft": ("prompt", "response"),
            "dpo": ("prompt", "chosen", "rejected"),
            "grpo": ("prompt", "expected"),
            "chemprop": ("smiles", "target"),
            "molecular_transfer": ("smiles",),
            "molecular_rl": ("smiles",),
        }.get(kind, ())
        if kind == "sft":
            compatible_rows = [
                row
                for row in training_rows
                if row.get("messages") or (row.get("prompt") and row.get("response"))
            ]
        else:
            compatible_rows = [row for row in training_rows if all(key in row for key in needed)]
        if needed and (not training_rows or len(compatible_rows) != len(training_rows)):
            raise DomainError(
                ErrorCode.VALIDATION, f"Train rows require fields: {', '.join(needed)}"
            )
        if kind in {"chemprop", "predict"} or (kind == "evaluate" and backend == "chemprop"):
            for key in ("unit", "method", "property"):
                values = {str(row[key]) for row in dataset.rows if row.get(key)}
                if len(values) > 1:
                    raise DomainError(
                        ErrorCode.VALIDATION, f"One property job cannot mix {key} contexts"
                    )
            if dataset.source.get("kind") == "external_computed":
                computation = dataset.source["externalComputation"]
                for config_key, source_key in (
                    ("target", "property"),
                    ("unit", "unit"),
                    ("method", "method"),
                ):
                    if config_key in config and str(config[config_key]) != str(
                        computation[source_key]
                    ):
                        raise DomainError(
                            ErrorCode.VALIDATION,
                            f"{config_key} must match the retained dataset property context",
                        )
                    config[config_key] = computation[source_key]
            conditions = {
                json.dumps(row["conditions"], sort_keys=True)
                for row in dataset.rows
                if row.get("conditions")
            }
            if len(conditions) > 1:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "One property model requires consistent temperature, "
                    "pressure and process conditions",
                )
            if not re.fullmatch(
                r"[A-Za-z][A-Za-z0-9_.-]{0,95}", str(config.get("target", "property"))
            ):
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "Property name must be an identifier of at most 96 characters",
                )
            for field, maximum in (("unit", 64), ("method", 300)):
                if (
                    not 1
                    <= len(str(config.get(field, "1" if field == "unit" else "custom_dataset")))
                    <= maximum
                ):
                    raise DomainError(
                        ErrorCode.VALIDATION, f"{field} exceeds the property context limit"
                    )
            if kind == "chemprop" and config["maxSteps"] > 300:
                raise DomainError(ErrorCode.VALIDATION, "Property training supports 1-300 epochs")
            if model is not None and backend == "chemprop":
                scope = model.details.get("scope") or {}
                for field, scope_key in (
                    ("property", "name"),
                    ("unit", "unit"),
                    ("method", "method"),
                ):
                    actual = {str(row[field]) for row in dataset.rows if row.get(field)}
                    if actual and actual != {str(scope.get(scope_key))}:
                        raise DomainError(
                            ErrorCode.MODEL_INCOMPATIBLE,
                            f"Dataset {field} differs from the trained property model",
                        )
                trained_conditions = {
                    json.dumps(value, sort_keys=True)
                    for value in model.details.get("trainingConditions", [])
                }
                if (
                    conditions
                    and trained_conditions
                    and not conditions.issubset(trained_conditions)
                ):
                    raise DomainError(
                        ErrorCode.MODEL_INCOMPATIBLE,
                        "Dataset conditions differ from the trained property model",
                    )
        if kind == "evaluate":
            final_rows = [row for row in dataset.rows if dataset.splits.get(row["id"]) == "final"]
            required = ("smiles", "target") if backend == "chemprop" else ()
            if not final_rows or any(not all(key in row for key in required) for row in final_rows):
                raise DomainError(
                    ErrorCode.VALIDATION, "Evaluation requires compatible labelled final rows"
                )
            if backend != "chemprop" and any(
                not row.get("messages")
                and not (row.get("prompt") and (row.get("response") or row.get("expected")))
                for row in final_rows
            ):
                raise DomainError(
                    ErrorCode.VALIDATION, "Assistant final rows need prompts and reference answers"
                )
        if kind == "molecular_rl":
            if config.get("reward", "qed") not in {"qed", "molecular_weight", "logp"}:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "Molecular RL reward must be qed, molecular_weight or logp",
                )
        if kind == "grpo":
            if config.get("reward", "exact_match") != "exact_match":
                raise DomainError(
                    ErrorCode.ENGINE_UNSUPPORTED_INPUT,
                    "GRPO currently supports a grounded exact_match reward",
                )
            config["reward"] = "exact_match"
        # Request payload cannot inject arbitrary executable options or environment values.
        allowed = {
            "backend",
            "maxSteps",
            "batchSize",
            "maxTokens",
            "maxSeconds",
            "saveEvery",
            "seed",
            "rank",
            "learningRate",
            "reward",
            "target",
            "unit",
            "method",
            "ensembleSize",
            "hiddenDim",
            "depth",
            "device",
            "executionTarget",
            "resumeCheckpoint",
            "numGenerations",
            "rewardMin",
            "rewardMax",
            "propertyTask",
        }
        config = {k: v for k, v in config.items() if k in allowed}
        if backend == "chemprop":
            # The narrow Chemprop adapter uses its pinned engine schedule. Do not
            # record an assistant trainer's learning-rate field as if it were used.
            config.pop("learningRate", None)
            config["learningRateSchedule"] = {
                "engine": "chemprop-2.3.1-default",
                "initial": 0.0001,
                "maximum": 0.001,
                "final": 0.0001,
                "warmupEpochs": 2,
            }
        if config.get("executionTarget") == "remote":
            self.authorize_dataset_egress(str(dataset.id))
        return str(kind), dataset, model, config
```

## LearningWorkspaceService.activate_model

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.activate_model`.

```python
    def activate_model(self, identifier: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Human-only owner binding, independent of the fixture model registry."""
        if self.ctx.principal_kind != "user" or payload.get("approved") is not True:
            raise DomainError(
                ErrorCode.FORBIDDEN, "Explicit owner approval is required to activate a model"
            )
        row = self._owned(LearningModel, identifier)
        evaluation = self._owned(LearningJob, str(payload.get("evaluationJobId", "")))
        if (
            evaluation.kind != "evaluate"
            or evaluation.state != "completed"
            or evaluation.model_id != row.id
            or evaluation.result.get("partition") != "final"
            or not evaluation.result.get("matchedExamples")
            or not evaluation.result.get("ok")
        ):
            raise DomainError(
                ErrorCode.MODEL_NOT_PROMOTABLE,
                "A completed independent held-out evaluation of this model is required",
            )
        if row.backend not in {"mlx", "transformers"} or row.details.get("state") != "ready":
            raise DomainError(ErrorCode.MODEL_NOT_PROMOTABLE, "Select a ready assistant model")
        # Serialize active-pointer changes for this owner, including when no model is active yet.
        from studio.persistence.models import Principal

        self.db.execute(
            select(Principal)
            .where(
                Principal.id == self.ctx.principal_id,
                Principal.workspace_id == self.ctx.workspace_id,
            )
            .with_for_update()
        ).scalar_one()
        all_models = self.db.execute(
            select(LearningModel)
            .where(
                LearningModel.workspace_id == self.ctx.workspace_id,
                LearningModel.owner_id == self.ctx.principal_id,
            )
            .with_for_update()
        ).scalars()
        for model in all_models:
            model.details = {**model.details, "active": model.id == row.id}
        row.details = {
            **row.details,
            "review": {
                "decision": "approved",
                "reviewedBy": str(self.ctx.principal_id),
                "reviewedAt": datetime.now(UTC).isoformat(),
                "evaluationJobId": str(evaluation.id),
                "baselineExactMatch": evaluation.result.get("baseExactMatch"),
                "candidateExactMatch": evaluation.result.get("candidateExactMatch"),
            },
            "active": True,
        }
        self.db.flush()
        return self._model(row)
```

## LearningWorkspaceService.artifact_path

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.artifact_path`.

```python
    def artifact_path(self, identifier: str, name: str) -> Path:
        from studio.domain.learning.workspace_runtime.dispatcher import job_directory

        job = self._owned(LearningJob, identifier)
        if name not in {item.get("path") for item in job.result.get("artifacts", [])}:
            raise DomainError(ErrorCode.NOT_FOUND, "Job artifact not found")
        directory = (job_directory(self.settings, job) / "output").resolve()
        path = (directory / name).resolve()
        if not path.is_relative_to(directory) or not path.is_file():
            raise DomainError(ErrorCode.NOT_FOUND, "Job artifact not found")
        return path
```

## LearningWorkspaceService.cancel_job

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.cancel_job`.

```python
    def cancel_job(self, identifier: str) -> dict[str, Any]:
        row = self._owned(LearningJob, identifier)
        if row.state in {"queued", "blocked", "interrupted"}:
            row.state = "cancelled"
        if row.state == "running":
            row.cancel_requested = True
        self.db.flush()
        return self._job(row)
```

## LearningWorkspaceService.catalog

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.catalog`.

```python
    def catalog(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "platform": platform.system(),
            "architecture": platform.machine(),
            "backends": [runtime_capability(name) for name in DEPENDENCIES],
            "catalog": CATALOG,
            "privacy": "Datasets, jobs and trained models are private to their owner",
            "formats": ["csv", "jsonl", "smi", "sdf"],
            "jobKinds": sorted(KINDS),
            "taskParameters": {
                "sft": {
                    "stepLabel": "Optimizer steps",
                    "requires": ["messages or prompt/response", "assistant model"],
                },
                "chemprop": {
                    "stepLabel": "Epochs",
                    "maxSteps": 300,
                    "requires": ["SMILES and target", "property/unit/method"],
                },
                "evaluate": {
                    "stepLabel": "Held-out evaluation",
                    "requires": ["trained candidate", "final partition"],
                },
            },
            "limits": {"datasetBytes": 20 * 1024 * 1024, "datasetRows": 50_000},
            "storage": storage_preflight(self.settings, 128 * 1024**2),
            "hardwareProfiles": [
                {"id": "apple_silicon", "backend": "mlx", "kinds": ["sft", "evaluate"]},
                {
                    "id": "cpu_or_cuda",
                    "backend": "transformers",
                    "kinds": ["sft", "dpo", "grpo", "evaluate"],
                },
            ],
        }
```

## LearningWorkspaceService.create_job

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.create_job`.

```python
    def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        kind, dataset, model, config = self._prepare_job(payload)
        preflight = self.preflight_job(payload)
        ready = preflight["ready"]
        storage = preflight["estimated"]
        ready = ready and storage["available"]
        if payload.get("workflowId"):
            config["workflowId"] = str(payload["workflowId"])
            config["requiredFreeBytes"] = storage["requiredFreeBytes"]
        from studio.domain.agent_workspace.workflows import admit_job, record_job

        workflow, seconds = (
            admit_job(self.db, self.ctx, payload, "training")
            if ready
            else (None, int(config["maxSeconds"]))
        )
        if workflow is not None:
            config = {**config, "workflowId": str(workflow.id), "maxSeconds": seconds}
        row = LearningJob(
            workspace_id=self.ctx.workspace_id,
            owner_id=self.ctx.principal_id,
            name=_text(payload.get("name") or f"{kind} · {dataset.name}", "Job name"),
            kind=kind,
            dataset_id=dataset.id,
            model_id=model.id if model else None,
            state="queued" if ready else "blocked",
            config=config,
            result={
                "datasetDigest": dataset.digest,
                "dataKind": dataset.data_kind,
                "scientificStatus": "not_validated",
                "storagePreflight": storage,
                "preflight": preflight,
            },
            events=[],
            error=None
            if ready
            else "; ".join(
                item["message"] for item in preflight["checks"] if item["status"] == "fail"
            ),
        )
        self.db.add(row)
        self.db.flush()
        record_job(self.db, workflow, row.id, "training", seconds)
        return self._job(row)
```

## LearningWorkspaceService.freeze_dataset

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.freeze_dataset`.

```python
    def freeze_dataset(self, identifier: str) -> dict[str, Any]:
        row = self._owned(LearningDataset, identifier)
        if row.state == "frozen":
            return self._dataset(row, full=True)
        if row.rights not in {"owned", "allowed"}:
            raise DomainError(
                ErrorCode.DATA_RIGHTS_UNKNOWN, "Resolve training rights before freezing"
            )
        if not row.rows:
            raise DomainError(ErrorCode.VALIDATION, "Dataset has no valid rows")
        row.splits = split_rows(row.rows)
        row.digest = digest(
            {
                "dataDigest": row.digest,
                "splits": row.splits,
                "splitPolicy": "identity_scaffold_document_tool_strata/v2",
            }
        )
        row.state = "frozen"
        self.db.flush()
        return self._dataset(row, full=True)
```

## LearningWorkspaceService.get_dataset

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.get_dataset`.

```python
    def get_dataset(self, identifier: str) -> dict[str, Any]:
        return self._dataset(self._owned(LearningDataset, identifier), full=True)
```

## LearningWorkspaceService.get_job

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.get_job`.

```python
    def get_job(self, identifier: str) -> dict[str, Any]:
        return self._job(self._owned(LearningJob, identifier))
```

## LearningWorkspaceService.get_model

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.get_model`.

```python
    def get_model(self, identifier: str) -> dict[str, Any]:
        return self._model(self._owned(LearningModel, identifier))
```

## LearningWorkspaceService.import_dataset

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.import_dataset`.

```python
    def import_dataset(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = _text(payload.get("name"), "Dataset name")
        kind = payload.get("dataKind", "experimental")
        rights = payload.get("rights", "unknown")
        if kind not in {"experimental", "literature", "computed", "synthetic", "user_authored"}:
            raise DomainError(ErrorCode.VALIDATION, "Unknown dataKind")
        if rights not in {"owned", "allowed", "unknown", "denied"}:
            raise DomainError(ErrorCode.VALIDATION, "Unknown training rights")
        source = payload.get("source") or {}
        if not isinstance(source, dict) or len(json.dumps(source)) > 20_000:
            raise DomainError(
                ErrorCode.VALIDATION, "Source provenance must be bounded JSON metadata"
            )
        try:
            rows, report = validate_import(payload)
        except ImportError as exc:
            raise DomainError(
                ErrorCode.ENGINE_UNAVAILABLE, "Install RDKit to validate molecular datasets"
            ) from exc
        except (ValueError, TypeError) as exc:
            raise DomainError(ErrorCode.VALIDATION, str(exc)) from exc
        row = LearningDataset(
            workspace_id=self.ctx.workspace_id,
            owner_id=self.ctx.principal_id,
            name=name,
            data_kind=kind,
            rights=rights,
            rows=rows,
            report=report,
            source=source,
            digest=digest({"rows": rows, "kind": kind, "rights": rights, "source": source}),
            state="validated" if rows else "rejected",
            splits={},
        )
        self.db.add(row)
        self.db.flush()
        return self._dataset(row, full=True)
```

## LearningWorkspaceService.import_notebook

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.import_notebook`.

```python
    def import_notebook(self, payload: dict[str, Any]) -> dict[str, Any]:
        from studio.domain.library.service import LibraryService

        identifiers = payload.get("pageIds", [])
        if not isinstance(identifiers, list) or not 1 <= len(identifiers) <= 100:
            raise DomainError(ErrorCode.VALIDATION, "Select between 1 and 100 notebook pages")
        library = LibraryService(self.db, self.ctx, vault_root=self.settings.vault_root)
        pages = [
            library.export_training_page(
                _uuid(identifier), for_agent=bool(payload.get("forAgent", False))
            )
            for identifier in identifiers
        ]
        records = [
            {"prompt": page["title"], "response": page["body"], "documentId": str(page["id"])}
            for page in pages
        ]
        return self.import_dataset(
            {
                "name": payload.get("name") or "Notebook research dataset",
                "format": "jsonl",
                "content": "\n".join(json.dumps(record) for record in records),
                "dataKind": "user_authored",
                "rights": "owned",
                "source": {
                    "kind": "private_notebook",
                    "pages": [
                        {
                            "pageId": str(page["id"]),
                            "revision": page["revision"],
                            "citations": page["citations"],
                        }
                        for page in pages
                    ],
                    "contentRights": "user_authored_content_only",
                },
            }
        )
```

## LearningWorkspaceService.import_retained_dataset

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.import_retained_dataset`.

```python
    def import_retained_dataset(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Import external computed values from immutable retained bytes, never agent labels."""
        from studio.domain.library.service import LibraryService

        library = LibraryService(self.db, self.ctx, vault_root=self.settings.vault_root)
        source = library.get_source(_uuid(str(payload.get("sourceId", ""))))
        rights = (source.get("citation") or {}).get("rights", {})
        if rights.get("training") not in {"owned", "allowed"}:
            raise DomainError(
                ErrorCode.DATA_RIGHTS_UNKNOWN, "Retained source must explicitly allow training"
            )
        path, _media_type, _filename = library.source_file(source["id"])
        if path.stat().st_size > 20 * 1024**2:
            raise DomainError(
                ErrorCode.VALIDATION, "Retained dataset exceeds the 20 MiB import limit"
            )
        original = path.read_bytes()
        checksum = hashlib.sha256(original).hexdigest()
        if checksum != source["checksum"]:
            raise DomainError(ErrorCode.VALIDATION, "Retained dataset checksum no longer matches")
        try:
            content = original.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DomainError(
                ErrorCode.VALIDATION, "Retained datasets require UTF-8 CSV or JSONL"
            ) from exc
        fmt = payload.get("format", "csv")
        if fmt not in {"csv", "jsonl"}:
            raise DomainError(
                ErrorCode.VALIDATION, "Retained computed datasets support CSV and JSONL"
            )
        filters = payload.get("filters") or {}
        if not isinstance(filters, dict) or len(filters) > 10:
            raise DomainError(
                ErrorCode.VALIDATION, "filters must contain at most ten exact column matches"
            )
        if filters:
            try:
                originals = (
                    list(csv.DictReader(io.StringIO(content)))
                    if fmt == "csv"
                    else [json.loads(line) for line in content.splitlines() if line.strip()]
                )
                selected = [
                    row
                    for row in originals
                    if all(str(row.get(key)) == str(value) for key, value in filters.items())
                ]
                content = "\n".join(json.dumps(row) for row in selected)
                fmt = "jsonl"
            except (ValueError, TypeError) as exc:
                raise DomainError(
                    ErrorCode.VALIDATION, "Source dataset could not be parsed"
                ) from exc
        unit = _text(payload.get("unit"), "Property unit", 64)
        method = _text(payload.get("method"), "Computation method", 300)
        property_name = _text(payload.get("property"), "Property name", 96)
        return self.import_dataset(
            {
                "name": payload.get("name") or source["title"],
                "format": fmt,
                "content": content,
                "dataKind": "computed",
                "rights": "allowed",
                "mapping": payload.get("mapping") or {},
                "metadataColumns": payload.get("metadataColumns") or [],
                "defaults": {
                    "unit": unit,
                    "method": method,
                    "property": property_name,
                    "conditions": payload.get("conditions") or {},
                },
                "source": {
                    "kind": "external_computed",
                    "sourceIds": [source["id"]],
                    "sourceRefs": [
                        {
                            "sourceId": source["id"],
                            "revision": source["revision"],
                            "checksum": checksum,
                        }
                    ],
                    "citation": source.get("citation"),
                    "filters": filters,
                    "externalComputation": {
                        "property": property_name,
                        "unit": unit,
                        "method": method,
                        "conditions": payload.get("conditions") or {},
                    },
                    "scientificStatus": "not_validated",
                    "importMeaning": "source_bytes_not_generated_labels",
                },
            }
        )
```

## LearningWorkspaceService.infer_model

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.infer_model`.

```python
    def infer_model(
        self,
        identifier: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        model = self._owned(LearningModel, identifier)
        if model.backend not in {"mlx", "transformers"} or model.details.get("state") != "ready":
            raise DomainError(ErrorCode.MODEL_INCOMPATIBLE, "Select a ready assistant model")
        if (
            not isinstance(messages, list)
            or not 1 <= len(messages) <= 128
            or len(json.dumps(messages)) > 200_000
        ):
            raise DomainError(
                ErrorCode.VALIDATION, "Chat history exceeds the local model context limit"
            )
        if tools is not None and (
            not isinstance(tools, list) or len(tools) > 128 or len(json.dumps(tools)) > 200_000
        ):
            raise DomainError(
                ErrorCode.VALIDATION, "Tool catalog exceeds the local model context limit"
            )
        # The application's catalog uses name/input_schema, while model chat
        # templates and completion parsing use the OpenAI function envelope.
        # Normalize once so the prompt and the allowlist name the same tools.
        normalized_tools: list[dict[str, Any]] = []
        for tool in tools or []:
            if not isinstance(tool, dict):
                raise DomainError(ErrorCode.VALIDATION, "Local model tools must be objects")
            function = tool.get("function") if "function" in tool else {
                "name": tool.get("name"),
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            }
            if (
                not isinstance(function, dict)
                or not isinstance(function.get("name"), str)
                or not function["name"].strip()
                or not isinstance(function.get("parameters", {}), dict)
            ):
                raise DomainError(
                    ErrorCode.VALIDATION, "Local model tools require a name and object schema"
                )
            normalized_tools.append({"type": "function", "function": dict(function)})
        from studio.domain.learning.workspace_runtime.dispatcher import run_preview

        result = run_preview(
            model,
            "",
            min(4096, max(1, max_tokens)),
            self.settings,
            messages=messages,
            tools=normalized_tools,
        )
        raw = str(result.get("text", ""))
        allowed = {tool["function"]["name"] for tool in normalized_tools}
        calls: list[dict[str, Any]] = []
        protocol: list[Any] | None = None
        tagged = False
        try:
            value = json.loads(raw)
        except ValueError:
            # Only a response entirely made of protocol blocks is executable.
            # Fenced examples and explanatory text containing tags are answers.
            blocks = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", flags=re.DOTALL)
            matches = list(blocks.finditer(raw))
            if matches and not blocks.sub("", raw).strip():
                tagged = True
                try:
                    protocol = [json.loads(match.group(1)) for match in matches]
                except ValueError as exc:
                    raise DomainError(
                        ErrorCode.MODEL_INCOMPATIBLE, "Local model returned a malformed tool call"
                    ) from exc
        else:
            # Parse whole JSON first so literal protocol-looking strings inside
            # a trained answer schema cannot execute or be stripped from it.
            if isinstance(value, dict) and set(value) in (
                {"tool", "arguments"}, {"name", "arguments"}
            ):
                protocol = [value]
        for value in protocol or []:
            if not isinstance(value, dict) or set(value) not in (
                {"tool", "arguments"}, {"name", "arguments"}
            ):
                raise DomainError(
                    ErrorCode.MODEL_INCOMPATIBLE, "Local model returned a malformed tool call"
                )
            name, arguments = value.get("tool", value.get("name")), value["arguments"]
            if tagged and isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except ValueError as exc:
                    raise DomainError(
                        ErrorCode.MODEL_INCOMPATIBLE,
                        "Local model returned malformed tool arguments",
                    ) from exc
            if not isinstance(name, str) or not name.strip() or not isinstance(arguments, dict):
                raise DomainError(
                    ErrorCode.MODEL_INCOMPATIBLE, "Local model returned a malformed tool call"
                )
            if name in allowed:
                calls.append({
                    "id": "local_" + uuid.uuid4().hex,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                })
        if protocol is not None and not calls:
            raise DomainError(
                ErrorCode.MODEL_INCOMPATIBLE,
                "Local model returned only unsupported or malformed tool calls; "
                "select a compatible model or review its training",
            )
        content = "" if protocol is not None else raw.strip()
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": content or None,
                        **({"tool_calls": calls} if calls else {}),
                    }
                }
            ],
            "model": str(model.id),
        }
```

## LearningWorkspaceService.list_datasets

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.list_datasets`.

```python
    def list_datasets(self) -> list[dict[str, Any]]:
        return [self._dataset(row) for row in self._list(LearningDataset)]
```

## LearningWorkspaceService.list_jobs

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.list_jobs`.

```python
    def list_jobs(self) -> list[dict[str, Any]]:
        return [self._job(row) for row in self._list(LearningJob)]
```

## LearningWorkspaceService.list_models

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.list_models`.

```python
    def list_models(self) -> list[dict[str, Any]]:
        return [self._model(row) for row in self._list(LearningModel)]
```

## LearningWorkspaceService.preflight_job

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.preflight_job`.

```python
    def preflight_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        """The UI, agent and dispatcher share the same admission checks."""
        checks: list[dict[str, Any]] = []
        try:
            kind, dataset, model, config = self._prepare_job(payload)
        except DomainError as exc:
            return {
                "ready": False,
                "checks": [{"id": "inputs", "status": "fail", "message": exc.message}],
                "normalizedConfig": payload.get("config")
                if isinstance(payload.get("config"), dict)
                else {},
            }
        backend = str(config["backend"])
        counts = Counter(dataset.splits.values())
        checks.append(
            {
                "id": "inputs",
                "status": "pass",
                "message": "Dataset rights, model compatibility and parameter validation passed",
            }
        )
        heldout = counts.get("final", 0) > 0 and counts.get("train", 0) > 0
        if kind not in {"predict"}:
            checks.append(
                {
                    "id": "heldout",
                    "status": "pass" if heldout else "fail",
                    "message": "Independent train and final groups are present"
                    if heldout
                    else "Add at least three independent source/structure groups "
                    "and freeze again to create held-out partitions",
                }
            )
        if kind in {"sft", "dpo", "grpo"} and not counts.get("development"):
            checks.append(
                {
                    "id": "development",
                    "status": "fail",
                    "message": "Assistant training requires a development partition",
                }
            )
        remote = config.get("executionTarget") == "remote"
        capability = runtime_capability(backend)
        available = remote or capability["available"]
        checks.append(
            {
                "id": "runtime",
                "status": "pass" if available else "fail",
                "message": "Self-hosted worker selected; a compatible worker must claim the job"
                if remote
                else "Local runtime is available"
                if available
                else "Runtime unavailable: "
                + (", ".join(capability["missing"]) or "selected hardware is unavailable"),
            }
        )
        if not remote and available:
            device = str(config.get("device", "auto"))
            device_ready = selected_device_available(backend, device)
            checks.append(
                {
                    "id": "device",
                    "status": "pass" if device_ready else "fail",
                    "message": f"Selected {device} device is available"
                    if device_ready
                    else f"Selected {device} accelerator is unavailable; "
                    "select CPU/auto or a compatible worker",
                }
            )
        model_ready = model is None or model.details.get("state") == "ready" or remote
        checks.append(
            {
                "id": "model",
                "status": "pass" if model_ready else "fail",
                "message": "Model asset is ready"
                if model_ready
                else "Wait for the selected model download to complete",
            }
        )
        storage = storage_preflight(
            self.settings, _workflow_storage(payload, job_storage_requirement(kind, config))
        )
        checks.append(
            {
                "id": "disk",
                "status": "pass" if storage["available"] else "fail",
                "message": "Output storage is available"
                if storage["available"]
                else "Insufficient free disk space for job outputs",
            }
        )
        if dataset.data_kind in {"computed", "synthetic"}:
            checks.append(
                {
                    "id": "data_origin",
                    "status": "warn",
                    "message": f"{dataset.data_kind.capitalize()} labels retain their data origin; "
                    "training does not establish experimental properties",
                }
            )
        return {
            "ready": not any(item["status"] == "fail" for item in checks),
            "checks": checks,
            "normalizedConfig": config,
            "estimated": storage,
            "dataset": {
                "id": str(dataset.id),
                "state": dataset.state,
                "trainingRows": counts.get("train", 0),
                "developmentRows": counts.get("development", 0),
                "finalRows": counts.get("final", 0),
            },
            "model": {
                "id": str(model.id) if model else None,
                "backend": backend,
                "state": model.details.get("state") if model else "new_fit",
            },
        }
```

## LearningWorkspaceService.preview_model

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.preview_model`.

```python
    def preview_model(self, identifier: str, payload: dict[str, Any]) -> dict[str, Any]:
        model = self._owned(LearningModel, identifier)
        if model.backend not in {"mlx", "transformers"} or model.details.get("state") != "ready":
            raise DomainError(
                ErrorCode.MODEL_INCOMPATIBLE,
                "Text preview requires a ready assistant model; "
                "use a prediction job for molecular property models",
            )
        prompt = _text(payload.get("prompt"), "Preview prompt", 16_000)
        from studio.domain.learning.workspace_runtime.dispatcher import run_preview

        return run_preview(
            model, prompt, min(512, max(1, int(payload.get("maxTokens", 128)))), self.settings
        )
```

## LearningWorkspaceService.register_model

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.register_model`.

```python
    def register_model(self, payload: dict[str, Any]) -> dict[str, Any]:
        catalog = next((item for item in CATALOG if item["id"] == payload.get("catalogId")), None)
        if "catalogId" in payload and catalog is None:
            raise DomainError(ErrorCode.VALIDATION, "Unknown curated model catalog entry")
        repair = (
            self._owned(LearningModel, str(payload["repairModelId"]))
            if payload.get("repairModelId")
            else None
        )
        if repair and (
            not catalog
            or repair.details.get("catalogId") != catalog["id"]
            or repair.details.get("revision") != catalog["revision"]
        ):
            raise DomainError(ErrorCode.VALIDATION, "Repair requires the same pinned catalog asset")
        if repair and any(
            job.model_id == repair.id and job.state in {"queued", "running"}
            for job in self._list(LearningJob)
        ):
            raise DomainError(
                ErrorCode.VALIDATION, "Wait for this model's active job before repair"
            )
        backend = catalog["backend"] if catalog else payload.get("backend", "transformers")
        if backend not in {"mlx", "transformers", "reinvent"}:
            raise DomainError(
                ErrorCode.VALIDATION, "Imported model backend must be mlx, transformers or reinvent"
            )
        model_id = uuid.uuid4()
        details: dict[str, Any] = {
            "license": catalog["license"] if catalog else payload.get("license", "unknown"),
            "state": "ready",
        }
        if catalog:
            location = (
                self.settings.vault_root
                / str(self.ctx.workspace_id)
                / "learning"
                / str(self.ctx.principal_id)
                / "models"
                / str(model_id)
            )
            details.update(
                {
                    "catalogId": catalog["id"],
                    "repo": catalog["repo"],
                    "revision": catalog["revision"],
                    "state": "downloading",
                }
            )
        else:
            location = (
                Path(_text(payload.get("location"), "Local model path", 2000))
                .expanduser()
                .resolve()
            )
            if not location.is_absolute() or not location.exists():
                raise DomainError(ErrorCode.VALIDATION, "Local model path does not exist")
            if backend == "reinvent":
                if not location.is_file() or location.suffix not in {".prior", ".model", ".chkpt"}:
                    raise DomainError(
                        ErrorCode.VALIDATION,
                        "Select a licensed REINVENT prior/model/checkpoint file",
                    )
            elif not location.is_dir() or not (location / "config.json").is_file():
                raise DomainError(
                    ErrorCode.VALIDATION, "Select a local model directory containing config.json"
                )
            if backend != "reinvent" and not any(location.glob("*.safetensors")):
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "Local model requires safetensors weights; pickle weights are not accepted",
                )
        row = repair or LearningModel(
            id=model_id,
            workspace_id=self.ctx.workspace_id,
            owner_id=self.ctx.principal_id,
            name=_text(
                payload.get("name") or (catalog["name"] if catalog else location.name), "Model name"
            ),
            backend=backend,
            location=str(location),
            details=details,
        )
        if repair:
            row.details = {**row.details, "state": "downloading"}
        self.db.add(row)
        self.db.flush()
        if catalog:
            capability = runtime_capability("download")
            storage = storage_preflight(
                self.settings,
                _workflow_storage(payload, int(catalog["estimatedBytes"] * 1.25) + 64 * 1024**2),
            )
            download_ready = capability["available"] and storage["available"]
            if not download_ready:
                row.details = {**row.details, "state": "blocked"}
            job = LearningJob(
                workspace_id=self.ctx.workspace_id,
                owner_id=self.ctx.principal_id,
                name=f"Download {row.name}",
                kind="download_model",
                model_id=row.id,
                state="queued" if download_ready else "blocked",
                config={
                    "backend": "download",
                    "repo": catalog["repo"],
                    "revision": catalog["revision"],
                    "license": catalog["license"],
                    "maxSeconds": 1800,
                    "requiredFreeBytes": storage["requiredFreeBytes"],
                    **(
                        {"workflowId": str(payload["workflowId"])}
                        if payload.get("workflowId")
                        else {}
                    ),
                },
                error=None
                if download_ready
                else (
                    "Insufficient free disk space for model download"
                    if not storage["available"]
                    else "Install huggingface-hub to download catalog models"
                ),
                result={"storagePreflight": storage},
                events=[],
            )
            self.db.add(job)
            self.db.flush()
            return {**self._model(row), "downloadJobId": str(job.id)}
        return self._model(row)
```

## LearningWorkspaceService.resume_job

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.resume_job`.

```python
    def resume_job(self, identifier: str) -> dict[str, Any]:
        row = self._owned(LearningJob, identifier)
        if row.state not in {"cancelled", "failed", "interrupted", "blocked", "timed_out"}:
            raise DomainError(ErrorCode.CONFLICT, "Only a stopped or blocked job can be resumed")
        cap = runtime_capability(row.config.get("backend", "transformers"))
        if not cap["available"] and row.config.get("executionTarget") != "remote":
            raise DomainError(
                ErrorCode.ENGINE_UNAVAILABLE, "Install the selected runtime before resuming"
            )
        if row.kind != "download_model":
            inputs = {
                "kind": row.kind,
                "datasetId": str(row.dataset_id),
                "modelId": str(row.model_id) if row.model_id else None,
                "config": row.config,
                "workflowId": row.config.get("workflowId"),
            }
            preflight = self.preflight_job(inputs)
            if not preflight["ready"]:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "; ".join(
                        item["message"] for item in preflight["checks"] if item["status"] == "fail"
                    ),
                )
        from studio.domain.agent_workspace.workflows import admit_job, record_job

        workflow, seconds = (
            admit_job(
                self.db,
                self.ctx,
                {"workflowId": row.config.get("workflowId"), "config": row.config},
                "training",
            )
            if row.kind != "download_model"
            else (None, int(row.config.get("maxSeconds", 1800)))
        )
        if workflow is not None:
            row.config = {**row.config, "maxSeconds": seconds}
        row.state, row.cancel_requested, row.error = "queued", False, None
        row.lease_owner, row.lease_expires_at = None, None
        self.db.flush()
        record_job(self.db, workflow, row.id, "training", seconds)
        return self._job(row)
```

## validate_import

Source: `services/studio-api/src/studio/domain/learning/workspace_runtime/data.py:validate_import`.

```python
def validate_import(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    content = payload.get("content")
    if not isinstance(content, str):
        raise ValueError("content must be UTF-8 text")
    mapping = payload.get("mapping") or {}
    if not isinstance(mapping, dict):
        raise ValueError("mapping must map field names to source columns")
    parsed = _parse(content, str(payload.get("format", "csv")).lower())
    rows: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    duplicates = 0
    seen: set[str] = set()
    for index, original in enumerate(parsed, 1):
        try:
            if "_parseError" in original:
                raise ValueError(original["_parseError"])
            record: dict[str, Any] = {"id": f"row-{index}", "sourceRow": index}
            for key in (
                "smiles",
                "target",
                "prompt",
                "response",
                "chosen",
                "rejected",
                "expected",
                "unit",
                "method",
                "documentId",
                "psmiles",
                "polymerId",
                "property",
                "sourceId",
                "metadata",
                "conditions",
                "sourceRefs",
                "evaluation",
                "messages",
                "tools",
            ):
                source_key = mapping.get(key, key)
                if source_key and source_key in original and original[source_key] is not None:
                    value = original[source_key]
                    if len(str(value)) > MAX_CELL:
                        raise ValueError(f"{key} exceeds {MAX_CELL} characters")
                    record[key] = value
            for key in ("metadata", "conditions", "sourceRefs", "evaluation", "tools"):
                if key in record and isinstance(record[key], str):
                    record[key] = json.loads(record[key])
            if "messages" in record:
                record["messages"] = chat_record(record["messages"])
            if "tools" in record and (
                not isinstance(record["tools"], list) or len(record["tools"]) > 128
            ):
                raise ValueError("tools must be a bounded list")
            metadata_columns = payload.get("metadataColumns", [])
            if not isinstance(metadata_columns, list) or len(metadata_columns) > 30:
                raise ValueError("metadataColumns must contain at most 30 columns")
            if metadata_columns:
                record["metadata"] = {
                    **(record.get("metadata") or {}),
                    **{str(key): original[key] for key in metadata_columns if key in original},
                }
            defaults = payload.get("defaults") or {}
            if not isinstance(defaults, dict):
                raise ValueError("defaults must be a metadata object")
            for key in ("unit", "method", "property", "conditions"):
                if key not in record and key in defaults:
                    record[key] = copy.deepcopy(defaults[key])
            if not record.get("smiles") and record.get("psmiles"):
                record["smiles"] = str(record["psmiles"])
            if record.get("smiles"):
                record["originalSmiles"] = str(record["smiles"])
                record.update(canonical_structure(str(record["smiles"])))
            if "target" in record and str(record["target"]).strip():
                value = float(record["target"])
                if not math.isfinite(value):
                    raise ValueError("Target must be a finite number")
                record["target"] = value
            elif "target" in record:
                del record["target"]
            if not record.get("smiles") and not record.get("prompt") and not record.get("messages"):
                raise ValueError("A row needs a valid SMILES structure, prompt or conversation")
            if record.get("chosen") and not record.get("rejected"):
                raise ValueError("Preference data requires both chosen and rejected responses")
            # Equal records retain exactly one identity; conflicting measurements remain visible.
            signature = digest(
                {k: v for k, v in record.items() if k not in {"id", "sourceRow", "originalSmiles"}}
            )
            if signature in seen:
                duplicates += 1
                continue
            seen.add(signature)
            rows.append(record)
        except (ValueError, TypeError, KeyError) as exc:
            rejects.append({"row": index, "reason": str(exc)[:300]})
    counts = Counter("molecular" if "smiles" in row else "assistant" for row in rows)
    return rows, {
        "total": len(parsed),
        "accepted": len(rows),
        "rejected": len(rejects),
        "duplicates": duplicates,
        "rejections": rejects[:1000],
        "rowKinds": dict(counts),
        "validation": "structure_and_schema",
        "scientificStatus": "not_validated",
    }
```

## _leased

Source: `services/studio-api/src/studio/domain/learning/workspace_runtime/remote.py:_leased`.

```python
def _leased(service: LearningWorkspaceService, identifier: str, worker_id: str) -> LearningJob:
    job = service._owned(LearningJob, identifier)
    now = datetime.now(UTC)
    expiry = job.lease_expires_at
    if expiry is not None and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    if job.state != "running" or job.lease_owner != worker_id or expiry is None or expiry < now:
        raise DomainError(ErrorCode.CONFLICT, "Worker lease expired or does not own this job")
    return job
```

## _worker_id

Source: `services/studio-api/src/studio/domain/learning/workspace_runtime/remote.py:_worker_id`.

```python
def _worker_id(payload: dict[str, Any]) -> str:
    identifier = str(payload.get("workerId", ""))
    if not re.fullmatch(r"[A-Za-z0-9_.-]{8,100}", identifier):
        raise DomainError(
            ErrorCode.VALIDATION, "workerId must contain 8-100 letters, numbers or ._-"
        )
    return identifier
```

## checkpoint_archive

Source: `services/studio-api/src/studio/domain/learning/workspace_runtime/remote.py:checkpoint_archive`.

```python
def checkpoint_archive(service: LearningWorkspaceService, identifier: str, worker_id: str) -> bytes:
    job = _leased(service, identifier, worker_id)
    directory = job_directory(service.settings, job) / "output"
    buffer = io.BytesIO()
    if directory.exists():
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
            total = 0
            for path in directory.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    total += path.stat().st_size
                    if total > MAX_ARTIFACT_BYTES:
                        raise DomainError(
                            ErrorCode.VALIDATION, "Checkpoint exceeds remote transfer limit"
                        )
                    archive.write(path, str(path.relative_to(directory)))
    return buffer.getvalue()
```

## complete

Source: `services/studio-api/src/studio/domain/learning/workspace_runtime/remote.py:complete`.

```python
def complete(
    service: LearningWorkspaceService, identifier: str, payload: dict[str, Any], content: bytes
) -> dict[str, Any]:
    job = _leased(service, identifier, _worker_id(payload))
    if len(content) > MAX_ARTIFACT_BYTES:
        raise DomainError(ErrorCode.VALIDATION, "Artifacts exceed the 256 MiB upload limit")
    directory = job_directory(service.settings, job)
    output = directory / "output"
    staging = directory / "remote-staging"
    staging.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest: list[dict[str, Any]] = []
    try:
        if content:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                members = archive.infolist()
                if (
                    len(members) > 5000
                    or sum(item.file_size for item in members) > MAX_ARTIFACT_BYTES
                ):
                    raise ValueError("Artifact archive exceeds limits")
                capacity = storage_preflight(
                    service.settings, sum(item.file_size for item in members) + 16 * 1024**2
                )
                if not capacity["available"]:
                    raise ValueError("Insufficient free disk space to retain worker artifacts")
                for member in members:
                    name = Path(member.filename)
                    if name.is_absolute() or ".." in name.parts or "\\" in member.filename:
                        raise ValueError("Unsafe artifact path")
                    if member.is_dir():
                        continue
                    path = staging / name
                    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    data = archive.read(member)
                    path.write_bytes(data)
                    path.chmod(0o600)
                    manifest.append(
                        {
                            "path": str(name),
                            "bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest(),
                        }
                    )
        result = payload.get("result", {})
        if not isinstance(result, dict) or len(json.dumps(result)) > 1_000_000:
            raise ValueError("Result must contain bounded JSON metadata")
        # Never allow remote output to redirect preview/model loading to another host path.
        safe = {
            key: value
            for key, value in result.items()
            if key
            not in {
                "location",
                "baseLocation",
                "adapterPath",
                "artifacts",
                "registeredModelId",
                "active",
                "review",
                "activation",
                "approval",
            }
        }
        safe.update(
            {
                "backend": job.config["backend"],
                "artifacts": manifest,
                "scientificStatus": "not_validated",
                "execution": "authenticated_remote_worker",
            }
        )
        if job.config["backend"] in {"mlx", "transformers"}:
            base = service._owned(LearningModel, str(job.model_id))
            safe.update({"baseLocation": base.location, "adapterPath": str(output)})
        if job.config["backend"] == "reinvent":
            safe["location"] = str(
                output / ("trained.model" if job.kind == "molecular_transfer" else "trained.chkpt")
            )
        success = bool(result.get("ok")) and not job.cancel_requested
        if (
            success
            and job.kind in {"sft", "dpo", "grpo"}
            and not any(item["path"].endswith(".safetensors") for item in manifest)
        ):
            raise ValueError("Successful training must include adapter weights")
        if output.exists():
            shutil.rmtree(output)
        staging.replace(output)
        job.result = {**job.result, **safe}
        job.state = "completed" if success else ("cancelled" if job.cancel_requested else "failed")
        job.error = None if success else str(result.get("error", "Remote job stopped"))[:500]
        job.lease_owner, job.lease_expires_at = None, None
        if success:
            _register_result(service.db, job, directory)
        service.db.flush()
        return service._job(job)
    except (ValueError, zipfile.BadZipFile) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise DomainError(ErrorCode.VALIDATION, str(exc)) from exc
```

## heartbeat

Source: `services/studio-api/src/studio/domain/learning/workspace_runtime/remote.py:heartbeat`.

```python
def heartbeat(
    service: LearningWorkspaceService, identifier: str, payload: dict[str, Any]
) -> dict[str, Any]:
    job = _leased(service, identifier, _worker_id(payload))
    try:
        _request(service.db, job, service.settings)
        if job.dataset_id:
            service.authorize_dataset_egress(str(job.dataset_id))
    except (ValueError, DomainError):
        job.cancel_requested = True
    job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=120)
    events = payload.get("events", [])
    if isinstance(events, list) and len(json.dumps(events)) < 100_000:
        job.events = [event for event in events[-100:] if isinstance(event, dict)]
    service.db.flush()
    return {"cancelRequested": job.cancel_requested, "leaseSeconds": 120}
```

## lease

Source: `services/studio-api/src/studio/domain/learning/workspace_runtime/remote.py:lease`.

```python
def lease(service: LearningWorkspaceService, payload: dict[str, Any]) -> dict[str, Any]:
    worker_id = _worker_id(payload)
    backends = payload.get("backends", [])
    if not isinstance(backends, list) or any(
        name not in {"transformers", "chemprop", "reinvent", "mlx"} for name in backends
    ):
        raise DomainError(ErrorCode.VALIDATION, "Worker must declare supported training backends")
    rows = service.db.execute(
        select(LearningJob)
        .where(
            LearningJob.workspace_id == service.ctx.workspace_id,
            LearningJob.owner_id == service.ctx.principal_id,
            LearningJob.state == "queued",
        )
        .order_by(LearningJob.created_at)
        .with_for_update(skip_locked=True)
    ).scalars()
    for job in rows:
        if (
            job.config.get("executionTarget") != "remote"
            or job.config.get("backend") not in backends
        ):
            continue
        request = _request(service.db, job, service.settings)
        if job.dataset_id:
            service.authorize_dataset_egress(str(job.dataset_id))
        if request["model"]:
            model = service._owned(LearningModel, str(job.model_id))
            # A remote machine receives a model ID/repository, never host filesystem paths.
            request["model"] = {
                "id": str(model.id),
                "backend": model.backend,
                "repo": model.details.get("repo"),
                "details": {
                    key: value
                    for key, value in model.details.items()
                    if key
                    in {
                        "license",
                        "catalogId",
                        "modelDigest",
                        "scope",
                        "trainingJobId",
                        "artifacts",
                        "baseModelId",
                        "revision",
                        "baseRevision",
                    }
                },
            }
        job.state, job.lease_owner = "running", worker_id
        job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=120)
        job.attempt += 1
        service.db.flush()
        return {
            "jobId": str(job.id),
            "request": request,
            "leaseSeconds": 120,
            "resumeAvailable": (job_directory(service.settings, job) / "output").exists(),
        }
    return {"jobId": None}
```

## model_archive

Source: `services/studio-api/src/studio/domain/learning/workspace_runtime/remote.py:model_archive`.

```python
def model_archive(service: LearningWorkspaceService, identifier: str, worker_id: str) -> bytes:
    job = _leased(service, identifier, worker_id)
    model = service._owned(LearningModel, str(job.model_id))
    source_id = model.details.get("trainingJobId")
    if not source_id:
        return b""
    source = service._owned(LearningJob, str(source_id))
    directory = job_directory(service.settings, source) / "output"
    buffer = io.BytesIO()
    total = 0
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for item in model.details.get("artifacts", []):
            path = (directory / item["path"]).resolve()
            if (
                not path.is_relative_to(directory.resolve())
                or not path.is_file()
                or path.is_symlink()
            ):
                raise DomainError(ErrorCode.NOT_FOUND, "Private model artifact unavailable")
            total += path.stat().st_size
            if total > MAX_ARTIFACT_BYTES:
                raise DomainError(
                    ErrorCode.VALIDATION, "Model artifacts exceed remote transfer limit"
                )
            archive.write(path, item["path"])
    return buffer.getvalue()
```
