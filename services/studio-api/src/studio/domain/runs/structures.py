"""Task-bound, durable RDKit calculations over the real isolated adapter.

The input is an immutable vault artifact. Run requests contain references,
not molecule payloads. The bounded worker runs outside a DB transaction and
the request's event loop; each thread owns its database sessions.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from workers.common.resources import detect

from engine_adapter_rdkit import EngineError, RDKitAdapter, StructuralResult
from studio.application.idempotency import canonical_json, run_idempotent
from studio.auth.context import ServiceContext, load_context
from studio.config.settings import Settings
from studio.domain.evidence.vault import Vault
from studio.domain.projects.service import ProjectService
from studio.domain.runs.admission import AdmissionService
from studio.domain.runs.queue import TERMINAL, RunService
from studio.domain.tasks.service import TaskService
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import (
    Artifact,
    Project,
    ResearchTask,
    ResourceGroup,
    Run,
    RunAttempt,
    Workspace,
)

KIND = "rdkit_descriptors"
METHOD = "rdkit-descriptors/v1"
GROUP = "structure"
MIB = 1024**2
ENVELOPE = {
    "cpu_cores": 1,
    "memory_bytes": 512 * MIB,
    "storage_bytes": 64 * MIB,
    "gpu_devices": 0,
    "wall_seconds": 60,
}


def _validate_smiles(smiles: str) -> None:
    if (
        not smiles.strip()
        or len(smiles) > 8192
        or "\x00" in smiles
        or any(0xD800 <= ord(char) <= 0xDFFF for char in smiles)
    ):
        raise DomainError(
            ErrorCode.VALIDATION,
            "SMILES must contain 1-8192 valid Unicode characters and no NUL bytes",
            field_path="input.smiles",
        )


def input_summary(
    db: Session, vault: Vault, ctx: ServiceContext, run: Run
) -> dict[str, Any] | None:
    """Read only this workspace's checksum-verified calculation input."""
    if run.kind != KIND or run.workspace_id != ctx.workspace_id:
        return None
    ctx.require("read_project", run.task_id)
    try:
        artifact_id = uuid.UUID(str(run.request["inputArtifactId"]))
    except (KeyError, ValueError, TypeError):
        raise not_found("calculation input") from None
    artifact = db.execute(
        select(Artifact).where(
            Artifact.workspace_id == ctx.workspace_id,
            Artifact.id == artifact_id,
            Artifact.upload_state == "committed",
        )
    ).scalar_one_or_none()
    if artifact is None:
        raise not_found("calculation input")
    with vault.open_blob(ctx.workspace_id, artifact.storage_key) as blob:
        raw = blob.read(128 * 1024)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != artifact.checksum_sha256 or digest != run.request.get("inputDigest"):
        raise DomainError(ErrorCode.PROVENANCE_UNKNOWN, "calculation input checksum mismatch")
    payload = json.loads(raw)
    return {
        "smiles": payload["smiles"],
        "method": METHOD,
        "inputArtifactId": str(artifact_id),
        "inputDigest": digest,
    }


class StructureRunService:
    def __init__(self, factory: sessionmaker[Session], settings: Settings) -> None:
        self.factory = factory
        self.settings = settings
        self.vault = Vault(settings.vault_root)

    def quick_describe(
        self,
        workspace_id: uuid.UUID,
        principal_id: uuid.UUID,
        auth_session_id: uuid.UUID | None,
        smiles: str,
        idempotency_key: str,
        project_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Organize one calculation automatically, then use the same durable engine lane.

        The organization command commits before execution. A retry after a
        disconnect or process crash reuses both its task and its run key.
        """
        _validate_smiles(smiles)
        digest = hashlib.sha256(canonical_json({"smiles": smiles}).encode()).hexdigest()
        with self.factory() as db:
            ctx = load_context(db, workspace_id, principal_id, auth_session_id)
            ctx.require("read_project")
            ctx.require("request_compute")
            ctx.require("edit_task", project_id)

            def organize() -> dict[str, Any]:
                # Project slugs are not unique in the legacy schema. Serialize
                # automatic organization so first-use and concurrent keys reuse
                # exactly one active Quick calculations project.
                db.execute(
                    select(Workspace).where(Workspace.id == workspace_id).with_for_update()
                ).scalar_one()
                if project_id is not None:
                    project = db.execute(
                        select(Project).where(
                            Project.workspace_id == workspace_id, Project.id == project_id
                        )
                    ).scalar_one_or_none()
                    if project is None:
                        raise not_found("project")
                    if project.status != "active":
                        raise DomainError(
                            ErrorCode.CONFLICT,
                            "selected project is not active",
                            field_path="input.projectId",
                        )
                else:
                    project = db.execute(
                        select(Project)
                        .where(
                            Project.workspace_id == workspace_id,
                            Project.slug == "quick-calculations",
                            Project.status == "active",
                        )
                        .order_by(Project.created_at, Project.id)
                        .limit(1)
                    ).scalar_one_or_none()
                    if project is None:
                        project = ProjectService(db, ctx).create(
                            slug="quick-calculations",
                            name="Quick calculations",
                            description=(
                                "Molecule calculations saved automatically from the home screen."
                            ),
                        )
                task = TaskService(db, ctx).create(
                    project_id=project.id,
                    title=f"Structure analysis: {smiles.strip()[:80]}",
                    mode="discover",
                    target_kind="molecule",
                    objective=(
                        "Calculate molecular descriptors and a 2D structure depiction with RDKit. "
                        "Computational structure analysis; no laboratory validation is implied."
                    ),
                )
                return {"taskId": str(task.id), "projectId": str(project.id)}

            response = run_idempotent(
                db,
                ctx,
                operation="runs.quick_describe_structure",
                key=idempotency_key,
                payload={
                    "projectId": str(project_id) if project_id else None,
                    "inputDigest": digest,
                    "method": METHOD,
                },
                fn=organize,
            )
            db.commit()
        # Separate namespace from explicit task-bound calculations, within the
        # existing 200-character idempotency-key limit even for long client keys.
        run_key = "quick:" + hashlib.sha256(idempotency_key.encode()).hexdigest()
        return self.describe(
            workspace_id,
            principal_id,
            auth_session_id,
            uuid.UUID(response["taskId"]),
            smiles,
            run_key,
        )

    def describe(
        self,
        workspace_id: uuid.UUID,
        principal_id: uuid.UUID,
        auth_session_id: uuid.UUID | None,
        task_id: uuid.UUID,
        smiles: str,
        idempotency_key: str,
    ) -> uuid.UUID:
        _validate_smiles(smiles)
        raw = canonical_json({"smiles": smiles}).encode()
        digest = hashlib.sha256(raw).hexdigest()
        created: dict[str, uuid.UUID] = {}
        blobs: list[tuple[uuid.UUID, str]] = []
        with self.factory() as db:
            ctx = load_context(db, workspace_id, principal_id, auth_session_id)
            ctx.require("request_compute", task_id)
            task = db.execute(
                select(ResearchTask).where(
                    ResearchTask.id == task_id, ResearchTask.workspace_id == workspace_id
                )
            ).scalar_one_or_none()
            if task is None:
                raise not_found("task")

            def prepare() -> dict[str, Any]:
                db.refresh(task, with_for_update=True)
                if task.workflow_state in {"closed", "cancelled"}:
                    raise DomainError(
                        ErrorCode.CONFLICT,
                        "closed or cancelled tasks cannot start calculations",
                        field_path="input.taskId",
                    )
                artifact_id = uuid.uuid4()
                artifact = Artifact(
                    id=artifact_id,
                    workspace_id=workspace_id,
                    storage_key=f"pending/{artifact_id}",
                    original_name="structure-input.json",
                    media_type="application/json",
                    source_kind="derived",
                    access_scope=task_id,
                    created_by=principal_id,
                )
                db.add(artifact)
                db.flush()
                staging = self.vault.begin_staging(workspace_id, artifact_id)
                self.vault.append_bytes(staging, raw)
                key, size = self.vault.commit(workspace_id, artifact_id, digest)
                blobs.append((artifact_id, key))
                artifact.storage_key = key
                artifact.byte_size = size
                artifact.checksum_sha256 = digest
                artifact.upload_state = "committed"
                artifact.committed_at = datetime.now(UTC)
                runs = RunService(db, ctx)
                run = runs.request(
                    kind=KIND,
                    task_id=task_id,
                    request={
                        "inputArtifactId": str(artifact_id),
                        "inputDigest": digest,
                        "method": METHOD,
                    },
                    max_attempts=1,
                    deadline_at=datetime.now(UTC) + timedelta(seconds=60),
                )
                created["run"] = run.id
                self._ensure_group(db, ctx)
                self._recover_expired(db, ctx)
                admission = AdmissionService(db, ctx).admit(
                    run.id, ENVELOPE, group_name=GROUP, queue_name="structure-inline"
                )
                if admission.admitted:
                    attempt = db.execute(
                        select(RunAttempt).where(RunAttempt.run_id == run.id)
                    ).scalar_one()
                    runs.accept_attempt(
                        run_id=run.id, attempt_id=attempt.id, external_id=f"structure-{attempt.id}"
                    )
                    runs.start_attempt(
                        run_id=run.id, attempt_id=attempt.id, worker_id="local-rdkit"
                    )
                    created["attempt"] = attempt.id
                return {"id": str(run.id)}

            try:
                response = run_idempotent(
                    db,
                    ctx,
                    operation="runs.describe_structure",
                    key=idempotency_key,
                    payload={"taskId": str(task_id), "inputDigest": digest, "method": METHOD},
                    fn=prepare,
                )
                db.commit()
            except Exception:
                db.rollback()
                for _, key in blobs:
                    self.vault.remove_blob(workspace_id, key)
                raise
            run_id = uuid.UUID(response["id"])
            # A concurrent replay may have rolled back prepare's losing rows.
            if created.get("run") != run_id:
                for _, key in blobs:
                    self.vault.remove_blob(workspace_id, key)
                return run_id
            if "attempt" not in created:
                return run_id

        cancel, stopped = threading.Event(), threading.Event()
        watcher = threading.Thread(
            target=self._watch_cancel,
            args=(workspace_id, run_id, cancel, stopped),
            daemon=True,
        )
        watcher.start()
        try:
            try:
                result = RDKitAdapter().describe(smiles=smiles, cancel=cancel)
            except Exception:
                result = EngineError("INTERNAL", "local structure calculation failed", "execution")
            with self.factory() as db:
                # Completion records must survive revocation while a worker is stopping.
                ctx = replace(ctx, session=db)
                runs = RunService(db, ctx)
                run = db.execute(select(Run).where(Run.id == run_id).with_for_update()).scalar_one()
                if run.status in TERMINAL:
                    AdmissionService(db, ctx).release(run_id)
                    db.commit()
                    return run_id
                common: dict[str, Any] = {
                    "input": {"smiles": smiles},
                    "inputArtifactId": run.request["inputArtifactId"],
                    "inputDigest": digest,
                    "method": METHOD,
                    "adapter_version": result.adapter_version,
                    "evidence_type": "descriptor",
                    "scientific_status": "not_validated",
                    "execution": result.execution,
                }
                if run.status == "cancel_requested" or (
                    isinstance(result, EngineError) and result.code == "CANCELLED"
                ):
                    runs.confirm_cancelled(run_id)
                    run.result_summary = common
                elif isinstance(result, StructuralResult):
                    runs.complete_attempt(
                        run_id=run_id,
                        attempt_id=created["attempt"],
                        result_summary={
                            **common,
                            "engine": {"id": result.engine_id, "version": result.engine_version},
                            "structure": {
                                "canonical_smiles": result.canonical_smiles,
                                "inchi_key": result.inchi_key,
                                "formula": result.formula,
                                "depiction_svg": result.depiction_svg,
                                "depiction_error": result.depiction_error,
                            },
                            "descriptors": result.descriptors,
                        },
                    )
                elif result.code == "TIMED_OUT":
                    runs.timeout_attempt(run_id=run_id, attempt_id=created["attempt"])
                    run.result_summary = common
                else:
                    runs.fail_attempt(
                        run_id=run_id,
                        attempt_id=created["attempt"],
                        code=result.code,
                        message=result.message,
                    )
                    run.result_summary = {
                        **common,
                        "error": {
                            "code": result.code,
                            "stage": result.stage,
                            "message": result.message,
                        },
                    }
                AdmissionService(db, ctx).release(run_id)
                db.commit()
        finally:
            stopped.set()
            watcher.join(timeout=2)
        return run_id

    def _watch_cancel(
        self,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
        cancel: threading.Event,
        stopped: threading.Event,
    ) -> None:
        while not stopped.is_set():
            try:
                with self.factory() as db:
                    status = db.execute(
                        select(Run.status).where(Run.workspace_id == workspace_id, Run.id == run_id)
                    ).scalar_one()
                if status == "cancel_requested":
                    cancel.set()
                    return
            except Exception:
                cancel.set()  # lost control channel: stop the actual worker
                return
            stopped.wait(0.2)

    @staticmethod
    def _ensure_group(db: Session, ctx: ServiceContext) -> None:
        # Serialize only first-use pool creation; never overwrite configured budgets.
        db.execute(
            select(Workspace).where(Workspace.id == ctx.workspace_id).with_for_update()
        ).scalar_one()
        if (
            db.execute(
                select(ResourceGroup).where(
                    ResourceGroup.workspace_id == ctx.workspace_id, ResourceGroup.name == GROUP
                )
            ).scalar_one_or_none()
            is not None
        ):
            return
        hw = detect()
        AdmissionService(db, ctx).ensure_group(
            GROUP,
            capacity={
                "cpu_cores": hw.cpu_count_logical,
                "memory_bytes": hw.ram_total_bytes,
                "storage_bytes": hw.disk_free_bytes,
                "gpu_devices": 0,
                "concurrency": 1,
            },
            reserve={
                "cpu_cores": 1 if (hw.cpu_count_logical or 0) > 1 else 0,
                "memory_bytes": 1024 * MIB,
                "storage_bytes": 64 * MIB,
            },
        )

    @staticmethod
    def _recover_expired(db: Session, ctx: ServiceContext) -> None:
        """A crashed process cannot leave an old descriptor run looking live."""
        rows = RunService(db, ctx).reconcile(
            stale_before=datetime.now(UTC) - timedelta(seconds=90),
            retry_transient=False,
            kind=KIND,
            include_cancel_requested=True,
        )
        for run in rows:
            AdmissionService(db, ctx).release(run.id)
