"""Molecular-design job requests end to end (CS-0903, §13, §16.4).

Flow for one job:

    request()  validate spec + input kind + license/provenance ->
               persist job input artifact (vault, private) ->
               RunService.request -> admission or block
    execute()  reload the persisted payload -> rebuild the spec ->
               IsolatedDesign (network-denied container) -> honestly
               classify -> persist result artifact -> complete/fail

Two rules dominate: an input that is not an explicit small-molecule
representation (a formulation, a polymer distribution, an unknown
kind) is *blocked* as ``unsupported`` — never coerced to a generic
molecule (AT-0903-2); and a model whose declared license or provenance
cannot be verified against the reviewed registry is blocked
``license_unavailable`` before anything runs (U13). Every candidate is
labeled ``proposed`` — the outcome never claims experimental
properties (AT-0903-1).
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session
from workers.chemistry.design.runtime import IsolatedDesign, available

from engine_adapter_reinvent.contracts import (
    DesignJobSpec,
    EngineFailure,
)
from engine_adapter_reinvent.validation import build_job_payload, check_input_kind
from studio.auth.context import ServiceContext
from studio.config.settings import Settings, get_settings
from studio.domain.evidence.vault import Vault
from studio.domain.runs.admission import AdmissionService
from studio.domain.runs.queue import RunService
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import Artifact

RUN_KIND = "design"
_RESULT_NAME_PREFIX = "reinvent-result-"


def _spec_from_request(payload: dict[str, Any], request: dict[str, Any]) -> DesignJobSpec:
    """Rebuild the validated spec from the persisted job payload + the
    bounded run request — rebuilding is exact, nothing is re-read from
    caller input at execution time."""
    return DesignJobSpec.model_validate(
        {
            "schema_version": request["schema_version"],
            "method": "reinvent_de_novo_sampling",
            "anchor": payload["anchor"],
            "model": payload["model"],
            "num_smiles": payload["num_smiles"],
            "unique_molecules": payload["unique_molecules"],
            "randomize_smiles": payload["randomize_smiles"],
            "resources": request["resources"],
        }
    )


class DesignService:
    """Application service for molecular-design runs."""

    def __init__(
        self,
        db: Session,
        ctx: ServiceContext,
        settings: Settings | None = None,
        vault: Vault | None = None,
        engine: IsolatedDesign | None = None,
    ) -> None:
        self.db = db
        self.ctx = ctx
        self.settings = settings or get_settings()
        self.vault = vault or Vault(self.settings.vault_root)
        self.engine = engine or IsolatedDesign()
        self.runs = RunService(db, ctx)
        self.admission = AdmissionService(db, ctx)

    # ------------------------------------------------------------- request

    def request(
        self,
        raw: dict[str, Any],
        *,
        task_id: uuid.UUID | None = None,
    ) -> Any:
        """Validate + persist + request one design run.

        An unsupported input kind (formulation, polymer, unknown) is
        recorded as a ``blocked`` run with ``unsupported``; a model
        failing the license/provenance gate is blocked
        ``license_unavailable`` — both before any execution attempt
        (AT-0903-2, U13)."""
        if not self.settings.profile_design:
            raise DomainError(
                ErrorCode.ENGINE_UNAVAILABLE,
                "design profile is disabled by policy; set STUDIO_PROFILE_DESIGN",
            )
        try:
            anchor_kind = (raw.get("anchor") or {}).get("kind")
            check_input_kind(anchor_kind)
            spec = DesignJobSpec.model_validate(raw)
            payload = build_job_payload(spec)
        except (ValidationError, EngineFailure) as e:
            code = getattr(e, "code", None)
            if isinstance(e, EngineFailure) and code == "ENGINE_UNSUPPORTED_INPUT":
                capability = "unsupported"
            elif isinstance(e, EngineFailure) and code == "LICENSE_UNAVAILABLE":
                capability = "license_unavailable"
            else:
                capability = "insufficient_inputs"
            detail = (
                "; ".join(
                    f"{'.'.join(str(x) for x in err.get('loc', ()))} {err.get('msg', '')}"
                    for err in e.errors()[:8]
                )
                if isinstance(e, ValidationError)
                else e.message
            )
            run = self.runs.request(
                kind=RUN_KIND,
                request={
                    "rejected": True,
                    "spec_digest": hashlib.sha256(
                        json.dumps(raw, sort_keys=True, default=str).encode()
                    ).hexdigest(),
                },
                task_id=task_id,
                max_attempts=1,
            )
            return self.runs.block(
                run.id,
                reason=capability,
                detail={
                    "capability": capability,
                    "detail": detail[:800],
                    "policy": "unsupported input kinds are rejected, never "
                    "coerced; unlicensed or undeclared models are blocked "
                    "before any download or run attempt",
                },
            )
        input_bytes = json.dumps(payload, sort_keys=True).encode()
        input_artifact = self._persist_blob(
            input_bytes,
            original_name=f"reinvent-input-{spec.digest()[:12]}.json",
        )
        run = self.runs.request(
            kind=RUN_KIND,
            request={
                "schema_version": "1",
                "method": payload["method"],
                "method_version": payload["method_version"],
                "resources": spec.resources.model_dump(mode="json"),
                "input_artifact_id": str(input_artifact.id),
                "spec_digest": spec.digest(),
            },
            task_id=task_id,
            max_attempts=1,
        )
        if not available():
            return self.runs.block(
                run.id,
                reason="engine_not_installed",
                detail={
                    "capability": "not_installed",
                    "detail": "pinned worker image chem-studio-reinvent:4.8-v1 "
                    "unavailable; build workers/chemistry/design/Dockerfile",
                },
            )
        self.admission.admit(
            run.id,
            {
                "cpu_cores": spec.resources.ncores,
                "memory_bytes": spec.resources.memory_mebibytes * 1024**2,
                "storage_bytes": len(input_bytes) + 64 * 1024**2,
                "wall_seconds": spec.resources.wall_seconds,
            },
            queue_name="design",
        )
        return self.runs.get(run.id)

    # ------------------------------------------------------------- execute

    def execute(
        self,
        run_id: uuid.UUID,
        attempt_id: uuid.UUID,
        *,
        cancel: threading.Event | None = None,
    ) -> Any:
        """Run one admitted attempt inside the isolated worker and map
        the outcome onto the run record."""
        run = self.runs.get(run_id)
        request = run.request or {}
        artifact_id = request.get("input_artifact_id")
        if not artifact_id:
            raise DomainError(ErrorCode.VALIDATION, "run has no persisted input artifact")
        artifact = self.db.get(Artifact, uuid.UUID(str(artifact_id)))
        if (
            artifact is None
            or artifact.workspace_id != self.ctx.workspace_id
            or artifact.upload_state != "committed"
        ):
            raise not_found("input artifact")
        with self.vault.open_blob(self.ctx.workspace_id, artifact.storage_key) as f:
            payload = json.loads(f.read().decode())
        spec = _spec_from_request(payload, request)
        self.runs.accept_attempt(
            run_id=run_id,
            attempt_id=attempt_id,
            external_id=f"design-{attempt_id}",
        )
        self.runs.start_attempt(run_id=run_id, attempt_id=attempt_id)
        try:
            outcome = self.engine.compute(spec, payload=payload, cancel=cancel)
        except EngineFailure as e:
            self.admission.release(run_id)
            if e.code == "RUN_CANCELLED":
                return self.runs.confirm_cancelled(run_id)
            if e.code == "RUN_TIMEOUT":
                return self.runs.timeout_attempt(run_id=run_id, attempt_id=attempt_id)
            return self.runs.fail_attempt(
                run_id=run_id,
                attempt_id=attempt_id,
                code=e.code,
                message=e.message,
                retryable=False,
            )
        result_artifact = self._persist_blob(
            json.dumps(outcome.model_dump(mode="json"), sort_keys=True).encode(),
            original_name=f"{_RESULT_NAME_PREFIX}{str(run_id)[:12]}.json",
        )
        summary = {
            "usable": outcome.usable,
            "classification": outcome.classification,
            "method": outcome.method,
            "method_version": outcome.method_version,
            "engine": outcome.engine,
            "engine_version": outcome.engine_version,
            "label": outcome.label,
            "num_generated": outcome.num_generated,
            "evidence_class": outcome.evidence_class,
            "execution_gate": outcome.execution_gate,
            "does_not_establish": list(outcome.does_not_establish),
            "provenance": outcome.provenance,
            "input_artifact_id": str(artifact_id),
            "result_artifact_id": str(result_artifact.id),
            "scientific_status": outcome.scientific_status,
            "isolation": outcome.isolation,
        }
        self.admission.release(run_id)
        if outcome.usable:
            return self.runs.complete_attempt(
                run_id=run_id, attempt_id=attempt_id, result_summary=summary
            )
        return self.runs.fail_attempt(
            run_id=run_id,
            attempt_id=attempt_id,
            code=outcome.classification,
            message=(outcome.error or {}).get("message", "engine result not usable"),
            retryable=False,
        )

    def cancel(self, run_id: uuid.UUID) -> Any:
        return self.runs.request_cancel(run_id)

    # ------------------------------------------------------------- intern

    def _persist_blob(self, data: bytes, *, original_name: str) -> Artifact:
        """Store derived bytes in the private vault as a committed
        artifact — content-addressed, workspace-scoped, never served."""
        artifact = Artifact(
            workspace_id=self.ctx.workspace_id,
            storage_key="",
            media_type="application/json",
            original_name=original_name,
            source_kind="derived",
            created_by=self.ctx.principal_id,
        )
        self.db.add(artifact)
        self.db.flush()
        staging = self.vault.begin_staging(self.ctx.workspace_id, artifact.id)
        self.vault.append_bytes(staging, data)
        key, size = self.vault.commit(
            self.ctx.workspace_id, artifact.id, hashlib.sha256(data).hexdigest()
        )
        artifact.storage_key = key
        artifact.checksum_sha256 = hashlib.sha256(data).hexdigest()
        artifact.byte_size = size
        artifact.upload_state = "committed"
        artifact.committed_at = datetime.now(UTC)
        self.db.flush()
        return artifact
