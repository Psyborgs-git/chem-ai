"""Materials/thermodynamics job requests end to end (CS-0702, §13, §16.3).

Flow for one job:

    request()  validate spec + parameter coverage -> persist job input
               artifact (vault, private) -> RunService.request ->
               admission or block
    execute()  reload the persisted payload -> rebuild the spec ->
               IsolatedMaterials (network-denied container) -> honestly
               classify -> persist result artifact -> complete/fail

Two rules dominate: a job that cannot be expressed as two explicit
UNIFAC-LLE subgroup decompositions with full interaction-parameter
coverage is *blocked* — no surrogate molecule, no zero-filled pair
(AT-0702-1); and the computed equilibrium miscibility proxy never
establishes storage/emulsion/kinetic stability or any product claim —
`assess_endpoint` returns the typed verdict (AT-0702-2).
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
from workers.chemistry.materials.runtime import IsolatedMaterials, available

from engine_adapter_materials.contracts import (
    EngineFailure,
    MaterialsJobSpec,
    MaterialsOutcome,
)
from engine_adapter_materials.validation import build_job_payload, evaluate_endpoint
from studio.auth.context import ServiceContext
from studio.config.settings import Settings, get_settings
from studio.domain.evidence.vault import Vault
from studio.domain.runs.admission import AdmissionService
from studio.domain.runs.queue import RunService
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import Artifact

RUN_KIND = "materials"
_RESULT_NAME_PREFIX = "thermo-result-"


def _spec_from_request(payload: dict[str, Any], request: dict[str, Any]) -> MaterialsJobSpec:
    """Rebuild the validated spec from the persisted job payload + the
    bounded run request — rebuilding is exact, nothing is re-read from
    caller input at execution time."""
    return MaterialsJobSpec.model_validate(
        {
            "schema_version": request["schema_version"],
            "method": "unifac_lle_screen",
            "components": payload["components"],
            "conditions": payload["conditions"],
            "grid_points": payload["grid_points"],
            "resources": request["resources"],
        }
    )


class MaterialsService:
    """Application service for materials/thermodynamics runs."""

    def __init__(
        self,
        db: Session,
        ctx: ServiceContext,
        settings: Settings | None = None,
        vault: Vault | None = None,
        engine: IsolatedMaterials | None = None,
    ) -> None:
        self.db = db
        self.ctx = ctx
        self.settings = settings or get_settings()
        self.vault = vault or Vault(self.settings.vault_root)
        self.engine = engine or IsolatedMaterials()
        self.runs = RunService(db, ctx)
        self.admission = AdmissionService(db, ctx)

    # ------------------------------------------------------------- request

    def request(
        self,
        raw: dict[str, Any],
        *,
        task_id: uuid.UUID | None = None,
    ) -> Any:
        """Validate + persist + request one materials run.

        Missing required parameters (no subgroup decomposition, a
        parameter pair UNIFAC-LLE never regressed, a temperature outside
        the declared domain) are recorded as a ``blocked`` run with
        ``insufficient_inputs`` — never approximated (AT-0702-1).
        """
        if not self.settings.profile_materials:
            raise DomainError(
                ErrorCode.ENGINE_UNAVAILABLE,
                "materials profile is disabled by policy; set STUDIO_PROFILE_MATERIALS",
            )
        try:
            spec = MaterialsJobSpec.model_validate(raw)
            payload = build_job_payload(spec)
        except (ValidationError, EngineFailure) as e:
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
                reason="insufficient_inputs",
                detail={
                    "capability": "insufficient_inputs",
                    "detail": detail[:800],
                    "policy": "no surrogate molecule or zero-filled interaction "
                    "parameter is substituted",
                },
            )
        input_bytes = json.dumps(payload, sort_keys=True).encode()
        input_artifact = self._persist_blob(
            input_bytes,
            original_name=f"materials-input-{spec.digest()[:12]}.json",
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
                    "detail": "pinned worker image chem-studio-materials:0.6.1-v1 "
                    "unavailable; build workers/chemistry/materials/Dockerfile",
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
            queue_name="materials",
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
            external_id=f"materials-{attempt_id}",
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
            "phase_state": outcome.phase_state,
            "evidence_class": outcome.evidence_class,
            "supports_endpoints": list(outcome.supports_endpoints),
            "does_not_establish": list(outcome.does_not_establish),
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

    # ------------------------------------------------------------ evaluate

    def assess_endpoint(self, outcome: MaterialsOutcome, endpoint: str) -> dict[str, Any]:
        """AT-0702-2: decide whether this computed result *establishes* an
        endpoint. ``equilibrium_miscibility`` is the only endpoint in
        scope; ``storage_stability``/``emulsion_stability``/kinetic or
        product-performance endpoints return ``not_established`` with a
        typed basis — the proxy stays structurally separate from product
        performance claims."""
        if outcome.status != "succeeded" or not outcome.usable:
            return {
                "endpoint": endpoint,
                "established": False,
                "verdict": "not_evaluated",
                "basis": "no_usable_proxy_output",
                "detail": "the run produced no usable equilibrium proxy output",
            }
        return evaluate_endpoint(outcome.supports_endpoints, endpoint)

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
