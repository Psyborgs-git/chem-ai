"""Quantum job requests end to end (CS-0701, §13, §16.2).

Flow for one job:

    request()  validate spec -> persist QCSchema input artifact (vault,
               private) -> RunService.request -> admission or block
    execute()  reload the persisted payload -> rebuild the spec ->
               IsolatedQuantum (network-denied container) -> honestly
               classify -> persist result artifact -> complete/fail

Two rules dominate: inputs that cannot express an explicit molecular
job (a polymer composition, a missing charge/spin) are *blocked* — no
surrogate molecule is ever invented; and exit-0 with malformed or
nonconverged output is failed, not scientific success (AT-0701-2/3).
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
from workers.chemistry.quantum.runtime import IsolatedQuantum, available

from engine_adapter_qcengine.contracts import EngineFailure, QuantumJobSpec
from engine_adapter_qcengine.validation import build_atomic_input
from studio.auth.context import ServiceContext
from studio.config.settings import Settings, get_settings
from studio.domain.evidence.vault import Vault
from studio.domain.runs.admission import AdmissionService
from studio.domain.runs.queue import RunService
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import Artifact

RUN_KIND = "quantum"
_RESULT_NAME_PREFIX = "qcengine-result-"


def _spec_from_request(payload: dict[str, Any], request: dict[str, Any]) -> QuantumJobSpec:
    """Rebuild the validated spec: parameters from the bounded run
    request, the molecule from the persisted QCSchema payload (whose
    geometry is bohr — units are set accordingly so rebuilding is exact)."""
    mol = payload["molecule"]
    return QuantumJobSpec.model_validate(
        {
            "schema_version": request["schema_version"],
            "program": request["program"],
            "method": request["method"],
            "driver": request["driver"],
            "basis": request.get("basis"),
            "keywords": request.get("keywords") or {},
            "resources": request["resources"],
            "molecule": {
                "symbols": mol["symbols"],
                "geometry": mol["geometry"],
                "units": "bohr",
                "charge": mol["molecular_charge"],
                "multiplicity": mol["molecular_multiplicity"],
                "name": mol.get("name"),
                "provenance": payload.get("extras", {}).get("studio", {}).get("geometry_provenance")
                or {"kind": "imported", "source": "persisted-qcschema"},
            },
        }
    )


class QuantumService:
    """Application service for quantum compute runs."""

    def __init__(
        self,
        db: Session,
        ctx: ServiceContext,
        settings: Settings | None = None,
        vault: Vault | None = None,
        engine: IsolatedQuantum | None = None,
    ) -> None:
        self.db = db
        self.ctx = ctx
        self.settings = settings or get_settings()
        self.vault = vault or Vault(self.settings.vault_root)
        self.engine = engine or IsolatedQuantum()
        self.runs = RunService(db, ctx)
        self.admission = AdmissionService(db, ctx)

    # ------------------------------------------------------------- request

    def request(
        self,
        raw: dict[str, Any],
        *,
        task_id: uuid.UUID | None = None,
    ) -> Any:
        """Validate + persist + request one quantum run.

        Anything that cannot be a supported explicit molecular job is
        still recorded — as a ``blocked`` run with an explicit reason —
        never approximated and never silently dropped (AT-0701-3).
        """
        if not self.settings.profile_quantum:
            raise DomainError(
                ErrorCode.ENGINE_UNAVAILABLE,
                "quantum profile is disabled by policy; set STUDIO_PROFILE_QUANTUM",
            )
        try:
            spec = QuantumJobSpec.model_validate(raw)
            payload = build_atomic_input(spec)
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
                    "policy": "no surrogate molecule or guessed parameters are substituted",
                },
            )
        input_bytes = json.dumps(payload, sort_keys=True).encode()
        input_artifact = self._persist_blob(
            input_bytes,
            original_name=f"qcschema-input-{spec.digest()[:12]}.json",
        )
        run = self.runs.request(
            kind=RUN_KIND,
            request={
                "schema_version": "1",
                "program": spec.program,
                "method": spec.method,
                "driver": spec.driver,
                "basis": spec.basis,
                "keywords": dict(spec.keywords),
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
                    "detail": "pinned worker image chem-studio-qcengine:0.51.0-v1 "
                    "unavailable; build workers/chemistry/quantum/Dockerfile",
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
            queue_name="quantum",
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
            external_id=f"quantum-{attempt_id}",
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
            "engine": outcome.engine,
            "engine_version": outcome.engine_version,
            "qcengine_version": outcome.qcengine_version,
            "energy_hartree": outcome.energy_hartree,
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
