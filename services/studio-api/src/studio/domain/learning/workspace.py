"""Owner-scoped learning API shared by the UI and the agent's typed tools."""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext
from studio.config.settings import Settings
from studio.domain.learning.workspace_runtime.data import digest, split_rows, validate_import
from studio.domain.learning.workspace_runtime.models import (
    LearningDataset,
    LearningJob,
    LearningModel,
)
from studio.errors import DomainError, ErrorCode

CATALOG: list[dict[str, Any]] = [
    {
        "id": "qwen3-0.6b-mlx",
        "name": "Qwen3 0.6B · MLX 4-bit",
        "repo": "mlx-community/Qwen3-0.6B-4bit",
        "backend": "mlx",
        "license": "apache-2.0",
        "sizeHint": "~0.5 GB",
        "estimatedBytes": 500_000_000,
        "tasks": ["sft", "evaluate"],
    },
    {
        "id": "qwen3-0.6b",
        "name": "Qwen3 0.6B · Transformers",
        "repo": "Qwen/Qwen3-0.6B",
        "backend": "transformers",
        "license": "apache-2.0",
        "sizeHint": "~1.3 GB",
        "estimatedBytes": 1_300_000_000,
        "tasks": ["sft", "dpo", "grpo", "evaluate"],
    },
]
KINDS = {
    "sft",
    "dpo",
    "grpo",
    "chemprop",
    "molecular_transfer",
    "molecular_rl",
    "evaluate",
    "predict",
}
DEPENDENCIES = {
    "mlx": ["mlx_lm", "mlx"],
    "transformers": ["torch", "transformers", "peft", "trl", "datasets"],
    "chemprop": ["torch", "chemprop", "rdkit", "pydantic"],
    "reinvent": ["reinvent", "torch", "rdkit"],
    "download": ["huggingface_hub"],
}
_T = TypeVar("_T", LearningDataset, LearningModel, LearningJob)


def storage_preflight(settings: Settings, required_bytes: int) -> dict[str, Any]:
    path = settings.vault_root
    while not path.exists() and path != path.parent:
        path = path.parent
    free = shutil.disk_usage(path).free
    return {
        "available": free >= required_bytes,
        "freeBytes": free,
        "requiredFreeBytes": required_bytes,
    }


def job_storage_requirement(kind: str, config: dict[str, Any]) -> int:
    if kind in {"evaluate", "predict"}:
        return 16 * 1024**2
    if config.get("executionTarget") == "remote":
        return 128 * 1024**2
    if config.get("backend") == "chemprop":
        return 64 * 1024**2
    factor = 32 if config.get("backend") == "mlx" else 64
    return max(128, int(config.get("rank", 8)) * factor) * 1024**2


def runtime_python(backend: str) -> str:
    key = {
        "mlx": "STUDIO_MLX_PYTHON",
        "chemprop": "STUDIO_CHEMPROP_PYTHON",
        "reinvent": "STUDIO_REINVENT_PYTHON",
        "transformers": "STUDIO_TRANSFORMERS_PYTHON",
    }.get(backend, "STUDIO_TRAINING_PYTHON")
    configured = os.environ.get(key) or os.environ.get("STUDIO_TRAINING_PYTHON")
    if configured:
        return configured
    environment = {
        "mlx": "learning-mlx",
        "download": "learning-mlx",
        "chemprop": "learning-science",
        "transformers": "learning-transformers",
        "reinvent": "learning-reinvent",
    }.get(backend)
    if environment:
        # Local desktop install: keep optional Metal deps out of the API environment.
        candidate = Path(__file__).resolve().parents[6] / ".runtime" / environment / "bin/python"
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def runtime_capability(backend: str) -> dict[str, Any]:
    python = runtime_python(backend)
    deps = DEPENDENCIES.get(backend, [])
    missing = []
    if python == sys.executable:
        missing = [dep for dep in deps if importlib.util.find_spec(dep) is None]
    else:
        # Only the administrator-configured interpreter executes; request data never becomes code.
        try:
            probe = subprocess.run(  # noqa: S603 — interpreter is administrator configured
                [
                    python,
                    "-c",
                    "import importlib.util,json,sys; "
                    "print(json.dumps([x for x in sys.argv[1:] "
                    "if importlib.util.find_spec(x) is None]))",
                    *deps,
                ],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            missing = json.loads(probe.stdout) if probe.returncode == 0 else deps
        except (OSError, ValueError, subprocess.TimeoutExpired):
            missing = deps
    platform_ok = backend != "mlx" or (
        platform.system() == "Darwin" and platform.machine() == "arm64"
    )
    device_ok = True
    if backend == "mlx" and not missing and platform_ok:
        try:
            metal = subprocess.run(  # noqa: S603 — fixed hardware probe
                [python, "-c", "import mlx.core as mx; print(mx.metal.is_available())"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            device_ok = metal.returncode == 0 and metal.stdout.strip() == "True"
        except (OSError, subprocess.TimeoutExpired):
            device_ok = False
    return {
        "backend": backend,
        "available": not missing and platform_ok and device_ok,
        "missing": missing,
        "platformSupported": platform_ok,
        "deviceAvailable": device_ok,
        "execution": "native_local_process",
        "installCommand": {
            "mlx": 'python -m pip install "mlx-lm[train]"',
            "transformers": "python -m pip install torch transformers peft trl datasets accelerate",
            "chemprop": "python -m pip install chemprop==2.3.1 rdkit pydantic",
            "reinvent": "Install MolecularAI/REINVENT4 and register a licensed local prior",
            "download": "python -m pip install huggingface-hub",
        }.get(backend),
    }


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise DomainError(ErrorCode.VALIDATION, "Invalid learning workspace identifier") from exc


def _text(value: Any, name: str, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise DomainError(ErrorCode.VALIDATION, f"{name} must contain 1-{maximum} characters")
    return value.strip()


def _time(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class LearningWorkspaceService:
    def __init__(self, db: Session, ctx: ServiceContext, settings: Settings) -> None:
        self.db, self.ctx, self.settings = db, ctx, settings

    def _owned(self, cls: type[_T], identifier: str) -> _T:
        row = self.db.execute(
            select(cls).where(
                cls.id == _uuid(identifier),
                cls.workspace_id == self.ctx.workspace_id,
                cls.owner_id == self.ctx.principal_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, "Learning workspace record not found")
        return row

    def _list(self, cls: type[_T]) -> list[_T]:
        return list(
            self.db.execute(
                select(cls)
                .where(
                    cls.workspace_id == self.ctx.workspace_id,
                    cls.owner_id == self.ctx.principal_id,
                )
                .order_by(cls.created_at.desc())
                .limit(200)
            ).scalars()
        )

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

    def list_datasets(self) -> list[dict[str, Any]]:
        return [self._dataset(row) for row in self._list(LearningDataset)]

    def get_dataset(self, identifier: str) -> dict[str, Any]:
        return self._dataset(self._owned(LearningDataset, identifier), full=True)

    def authorize_dataset_egress(
        self, identifier: str, *, provider_bound: bool = True, training: bool = False
    ) -> bool:
        """Recheck retained source ACLs/rights before rows enter a provider or remote worker."""
        from studio.domain.library.artifacts import authorize_retained_artifact
        from studio.domain.library.service import LibraryService

        dataset = self._owned(LearningDataset, identifier)
        check_dataset_sources(self.db, dataset)
        library = LibraryService(self.db, self.ctx, vault_root=self.settings.vault_root)
        seen: set[str] = set()

        def check(value: Any, depth: int = 0) -> None:
            if depth > 20:
                raise DomainError(
                    ErrorCode.VALIDATION, "Dataset source provenance is too deeply nested"
                )
            if isinstance(value, list):
                for item in value:
                    check(item, depth + 1)
            elif isinstance(value, dict):
                rights = value.get("rights", {})
                if provider_bound and isinstance(rights, dict) and rights.get("export") == "denied":
                    raise DomainError(ErrorCode.FORBIDDEN, "Dataset source does not allow transfer")
                artifact = authorize_retained_artifact(
                    self.db, self.ctx, value, provider_bound=provider_bound
                )
                if (
                    training
                    and artifact is not None
                    and (artifact.rights or {}).get("training") not in {"owned", "allowed"}
                ):
                    raise DomainError(
                        ErrorCode.DATA_RIGHTS_UNKNOWN,
                        "Current source rights do not permit training",
                    )
                page_id = value.get("pageId")
                if page_id and "page:" + str(page_id) not in seen:
                    seen.add("page:" + str(page_id))
                    page = library.get_page(_uuid(str(page_id)), for_agent=True)
                    check(page.get("citations", []), depth + 1)
                source_ids = value.get("sourceIds", [])
                if not isinstance(source_ids, list):
                    raise DomainError(ErrorCode.VALIDATION, "sourceIds must be a list")
                identifiers = ([value["sourceId"]] if value.get("sourceId") else []) + source_ids
                for source_id in identifiers:
                    key = "source:" + str(source_id)
                    if key not in seen:
                        seen.add(key)
                        source = library.get_source(_uuid(str(source_id)))
                        check(source.get("citation", {}), depth + 1)
                for nested in value.values():
                    if isinstance(nested, (dict, list)):
                        check(nested, depth + 1)

        check(dataset.source)
        return True

    def authorize_dataset_training(self, identifier: str) -> bool:
        return self.authorize_dataset_egress(identifier, provider_bound=False, training=True)

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
                "splitPolicy": "identity_scaffold_document/v1",
            }
        )
        row.state = "frozen"
        self.db.flush()
        return self._dataset(row, full=True)

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

    def _model(self, row: LearningModel) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "name": row.name,
            "backend": row.backend,
            "location": row.location,
            "details": row.details,
            "createdAt": _time(row.created_at),
        }

    def list_models(self) -> list[dict[str, Any]]:
        return [self._model(row) for row in self._list(LearningModel)]

    def get_model(self, identifier: str) -> dict[str, Any]:
        return self._model(self._owned(LearningModel, identifier))

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
        from studio.domain.learning.workspace_runtime.dispatcher import run_preview

        result = run_preview(
            model, "", min(4096, max(1, max_tokens)), self.settings, messages=messages, tools=tools
        )
        raw = str(result.get("text", ""))
        allowed = {tool.get("function", {}).get("name") for tool in (tools or [])}
        calls: list[dict[str, Any]] = []
        for block in re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", raw, flags=re.DOTALL):
            try:
                value = json.loads(block)
                name = value.get("name")
                arguments = value.get("arguments", {})
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                if name in allowed and isinstance(arguments, dict):
                    calls.append(
                        {
                            "id": "local_" + uuid.uuid4().hex,
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)},
                        }
                    )
            except (ValueError, TypeError, AttributeError):
                continue
        if not calls and raw.strip().startswith("{"):
            try:
                value = json.loads(raw)
                name = value.get("tool", value.get("name"))
                if name in allowed and isinstance(value.get("arguments"), dict):
                    calls.append(
                        {
                            "id": "local_" + uuid.uuid4().hex,
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(value["arguments"])},
                        }
                    )
            except (ValueError, TypeError, AttributeError):
                pass
        content = re.sub(r"<tool_call>.*?</tool_call>", "", raw, flags=re.DOTALL).strip()
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

    def register_model(self, payload: dict[str, Any]) -> dict[str, Any]:
        catalog = next((item for item in CATALOG if item["id"] == payload.get("catalogId")), None)
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
                {"catalogId": catalog["id"], "repo": catalog["repo"], "state": "downloading"}
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
        row = LearningModel(
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
        self.db.add(row)
        self.db.flush()
        if catalog:
            capability = runtime_capability("download")
            storage = storage_preflight(
                self.settings, int(catalog["estimatedBytes"] * 1.25) + 64 * 1024**2
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
                    "maxSeconds": 1800,
                    "requiredFreeBytes": storage["requiredFreeBytes"],
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

    def list_jobs(self) -> list[dict[str, Any]]:
        return [self._job(row) for row in self._list(LearningJob)]

    def _job(self, row: LearningJob) -> dict[str, Any]:
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
        }

    def get_job(self, identifier: str) -> dict[str, Any]:
        return self._job(self._owned(LearningJob, identifier))

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

    def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
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
        config = dict(payload.get("config") or {})
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
        training_rows = [r for r in dataset.rows if dataset.splits.get(r["id"]) == "train"]
        if kind == "chemprop":
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
        if needed and not any(all(key in row for key in needed) for row in training_rows):
            raise DomainError(
                ErrorCode.VALIDATION, f"Train rows require fields: {', '.join(needed)}"
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
        if config.get("executionTarget") == "remote":
            self.authorize_dataset_egress(str(dataset.id))
        capability = runtime_capability(backend)
        ready = capability["available"] and (model is None or model.details.get("state") == "ready")
        if config.get("executionTarget") == "remote":
            ready = True
        storage = storage_preflight(self.settings, job_storage_requirement(str(kind), config))
        ready = ready and storage["available"]
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
            },
            events=[],
            error=None
            if ready
            else (
                "Insufficient free disk space for job outputs"
                if not storage["available"]
                else "Selected model is not ready"
                if model and model.details.get("state") != "ready"
                else "Runtime unavailable: "
                + (
                    ", ".join(capability["missing"])
                    or (
                        "Metal GPU unavailable to this process"
                        if not capability["deviceAvailable"]
                        else "unsupported platform"
                    )
                )
            ),
        )
        self.db.add(row)
        self.db.flush()
        return self._job(row)

    def cancel_job(self, identifier: str) -> dict[str, Any]:
        row = self._owned(LearningJob, identifier)
        if row.state in {"queued", "blocked", "interrupted"}:
            row.state = "cancelled"
        if row.state == "running":
            row.cancel_requested = True
        self.db.flush()
        return self._job(row)

    def resume_job(self, identifier: str) -> dict[str, Any]:
        row = self._owned(LearningJob, identifier)
        if row.state not in {"cancelled", "failed", "interrupted", "blocked", "timed_out"}:
            raise DomainError(ErrorCode.CONFLICT, "Only a stopped or blocked job can be resumed")
        cap = runtime_capability(row.config.get("backend", "transformers"))
        if not cap["available"] and row.config.get("executionTarget") != "remote":
            raise DomainError(
                ErrorCode.ENGINE_UNAVAILABLE, "Install the selected runtime before resuming"
            )
        row.state, row.cancel_requested, row.error = "queued", False, None
        row.lease_owner, row.lease_expires_at = None, None
        self.db.flush()
        return self._job(row)

    def preview_model(self, identifier: str, payload: dict[str, Any]) -> dict[str, Any]:
        model = self._owned(LearningModel, identifier)
        prompt = _text(payload.get("prompt"), "Preview prompt", 16_000)
        from studio.domain.learning.workspace_runtime.dispatcher import run_preview

        return run_preview(
            model, prompt, min(512, max(1, int(payload.get("maxTokens", 128)))), self.settings
        )


def check_dataset_sources(db: Session, dataset: LearningDataset) -> None:
    """Opt-outs apply to frozen notebook snapshots as well as new exports."""
    if dataset.source.get("kind") != "private_notebook":
        return
    from studio.domain.library.models import Notebook, NotebookPage

    for source in dataset.source.get("pages", []):
        page = db.get(NotebookPage, _uuid(str(source.get("pageId", ""))))
        if (
            page is None
            or page.owner_id != dataset.owner_id
            or page.workspace_id != dataset.workspace_id
        ):
            raise DomainError(ErrorCode.FORBIDDEN, "A notebook dataset source is unavailable")
        notebook = db.get(Notebook, page.notebook_id)
        if (
            notebook is None
            or notebook.owner_id != dataset.owner_id
            or notebook.workspace_id != dataset.workspace_id
            or not notebook.training_enabled
            or page.deleted_at is not None
        ):
            raise DomainError(
                ErrorCode.FORBIDDEN, "A notebook source is no longer enabled for training"
            )
