"""Retrosynthesis job requests end to end (CS-0903, §13, §16.4).

Flow for one job:

    request()  validate spec + input kind + license/provenance ->
               persist job input artifact (vault, private) ->
               RunService.request -> admission or block
    execute()  reload the persisted payload -> rebuild the spec ->
               IsolatedSynthesis (network-denied container) -> honestly
               classify -> persist result artifact -> complete/fail

Three rules dominate: an input that is not an explicit small-molecule
representation is *blocked* as ``unsupported`` — never coerced to a
generic molecule (AT-0903-2); a model/stock/template asset failing the
license/provenance gate is blocked ``license_unavailable`` before
anything runs (U13); and every proposed route — including ones whose
precursors all sit in the purchasable stock list — is a hypothesis
requiring independent human plan approval, never an executable
protocol (AT-0903-3).
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
from workers.chemistry.synthesis.runtime import IsolatedSynthesis, available

from engine_adapter_aizynthfinder.contracts import (
    EngineFailure,
    RouteJobSpec,
    RouteOutcome,
)
from engine_adapter_aizynthfinder.validation import (
    build_job_payload,
    check_input_kind,
    evaluate_execution,
)
from studio.auth.context import ServiceContext
from studio.config.settings import Settings, get_settings
from studio.domain.evidence.vault import Vault
from studio.domain.runs.admission import AdmissionService
from studio.domain.runs.queue import RunService
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import Artifact

RUN_KIND = "synthesis"
_RESULT_NAME_PREFIX = "aizynthfinder-result-"


def _spec_from_request(payload: dict[str, Any], request: dict[str, Any]) -> RouteJobSpec:
    """Rebuild the validated spec from the persisted job payload + the
    bounded run request — rebuilding is exact, nothing is re-read from
    caller input at execution time."""
    return RouteJobSpec.model_validate(
        {
            "schema_version": request["schema_version"],
            "method": "aizynthfinder_mcts_route",
            "target": payload["target"],
            "policy_model": payload["policy_model"],
            "templates": payload["templates"],
            "stock": payload["stock"],
            "filter_model": payload.get("filter_model"),
            "search": payload["search"],
            "resources": request["resources"],
        }
    )


class SynthesisService:
    """Application service for retrosynthesis runs."""

    def __init__(
        self,
        db: Session,
        ctx: ServiceContext,
        settings: Settings | None = None,
        vault: Vault | None = None,
        engine: IsolatedSynthesis | None = None,
    ) -> None:
        self.db = db
        self.ctx = ctx
        self.settings = settings or get_settings()
        self.vault = vault or Vault(self.settings.vault_root)
        self.engine = engine or IsolatedSynthesis()
        self.runs = RunService(db, ctx)
        self.admission = AdmissionService(db, ctx)

    # ------------------------------------------------------------- request

    def request(
        self,
        raw: dict[str, Any],
        *,
        task_id: uuid.UUID | None = None,
    ) -> Any:
        """Validate + persist + request one retrosynthesis run.

        An unsupported input kind (formulation, polymer, unknown) is
        recorded as a ``blocked`` run with ``unsupported``; an asset
        failing the license/provenance gate is blocked
        ``license_unavailable`` — both before any execution attempt
        (AT-0903-2, U13)."""
        if not self.settings.profile_synthesis:
            raise DomainError(
                ErrorCode.ENGINE_UNAVAILABLE,
                "synthesis profile is disabled by policy; set STUDIO_PROFILE_SYNTHESIS",
            )
        try:
            target_kind = (raw.get("target") or {}).get("kind")
            check_input_kind(target_kind)
            spec = RouteJobSpec.model_validate(raw)
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
                    "coerced; unlicensed or undeclared models/stocks are "
                    "blocked before any download or run attempt",
                },
            )
        input_bytes = json.dumps(payload, sort_keys=True).encode()
        input_artifact = self._persist_blob(
            input_bytes,
            original_name=f"aizynthfinder-input-{spec.digest()[:12]}.json",
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
                    "detail": "pinned worker image chem-studio-aizynthfinder:4.4.1-v1 "
                    "unavailable; build workers/chemistry/synthesis/Dockerfile",
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
            queue_name="synthesis",
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
            external_id=f"synthesis-{attempt_id}",
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
            "num_solved": outcome.num_solved,
            "num_routes": len(outcome.routes),
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

    # ------------------------------------------------------------ evaluate

    def assess_execution(self, outcome: RouteOutcome) -> dict[str, Any]:
        """AT-0903-3: decide whether this route output may execute in
        the lab. Even when every precursor sits in the purchasable
        stock list the answer is a typed
        ``independent_plan_approval_required`` verdict — the route is a
        proposed hypothesis; the system never auto-releases a protocol
        and only a human ``approve_experiment`` principal can approve
        an experiment plan (§14.1, §21.1)."""
        return evaluate_execution(outcome)

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
