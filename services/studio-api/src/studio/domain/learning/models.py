"""Model registry + serving compatibility (CS-0802, §17.5, §18.4).

The registry records each release's full lineage — dataset snapshot →
training run → adapter → release — plus base/tokenizer identities and
the adapter's training-time base binding (persisted by CS-0801).
Serving-time compatibility is structural and enforced on every bind:
an adapter paired with a wrong base or tokenizer is REJECTED, never
warned (AT-0802-1).

Sessions pin the release they began with (``session_model_pins``);
the workspace serving pointer moves atomically in one transaction and
never mutates existing pins (AT-0802-2). Rollback is the same atomic
move back to a known-good release — no schema or data rollback, no
audit-history overwrite (AT-0802-3). ``promoted`` is reachable only
through ``promote`` here, which requires a fresh ``model_release``
approval granted by a human-holdable capability — agents can never
grant it.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from chem_studio_policy.capabilities import CAP_MANAGE_MODELS, CAP_READ_PROJECT
from sqlalchemy import select
from sqlalchemy.orm import Session
from workers.inference.model_loading.contracts import (
    AdapterBinding,
    AdapterIdentity,
    BaseIdentity,
    LoadRequest,
    LoadValidationReport,
    TokenizerIdentity,
)
from workers.inference.model_loading.verify import BUNDLE_FORMAT, build_bundle

from studio.application.approvals import grant, require_valid
from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext
from studio.config.settings import Settings
from studio.domain.evidence.vault import Vault
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import (
    Approval,
    Artifact,
    ModelRelease,
    ResearchSession,
    ServingPointer,
    SessionModelPin,
    TrainingRun,
)

_APPROVAL_ACTION = "model_release"

# Serving-eligible release states — anything else is never bound.
_SERVABLE = {"validated", "promoted", "superseded"}


def _now() -> datetime:
    return datetime.now(UTC)


def _capability_labels(*, load_engine_live: bool) -> dict[str, Any]:
    return {
        "scientificStatus": "not_validated",
        "dataStatus": "fixture_only",
        "engineCapability": "live" if load_engine_live else "not_installed",
        "baseModel": "pico-gpt-char-v1 (locally constructed fixture, ~0.9M params)",
        "promotion": "approved serving pointer only — evaluation gates are CS-0803",
        "egress": "none",
        "confidentiality": "vault-scoped",
    }


def pin_session_start(
    db: Session, *, workspace_id: uuid.UUID, session_id: uuid.UUID
) -> SessionModelPin:
    """Freeze the session's release at start (§17.5). Internal helper —
    the caller is the session-start service; capability checks happen
    there. Captures the pointer as it is NOW; later pointer moves never
    touch this row."""
    pointer = db.execute(
        select(ServingPointer).where(ServingPointer.workspace_id == workspace_id)
    ).scalar_one_or_none()
    pin = SessionModelPin(
        workspace_id=workspace_id,
        session_id=session_id,
        release_id=pointer.release_id if pointer is not None else None,
    )
    db.add(pin)
    db.flush()
    return pin


class ModelRegistryService:
    def __init__(
        self,
        db: Session,
        ctx: ServiceContext,
        settings: Settings,
        vault: Vault | None = None,
        runtime: Any | None = None,
    ) -> None:
        self.db = db
        self.ctx = ctx
        self.settings = settings
        self.vault = vault or Vault(settings.vault_root)
        if runtime is None:
            from workers.inference.model_loading.runtime import ModelLoadRuntime

            runtime = ModelLoadRuntime()
        self.runtime = runtime

    # ------------------------------------------------------------- helpers

    def _get(self, release_id: uuid.UUID) -> ModelRelease:
        release = self.db.execute(
            select(ModelRelease).where(
                ModelRelease.id == release_id,
                ModelRelease.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if release is None:
            raise not_found("model release")
        return release

    def _pointer_row(self) -> ServingPointer:
        """SELECT … FOR UPDATE — the single row every atomic move locks."""
        pointer = self.db.execute(
            select(ServingPointer)
            .where(ServingPointer.workspace_id == self.ctx.workspace_id)
            .with_for_update()
        ).scalar_one_or_none()
        if pointer is None:
            pointer = ServingPointer(
                workspace_id=self.ctx.workspace_id, release_id=None, revision=0, reason=""
            )
            self.db.add(pointer)
            self.db.flush()
        return pointer

    def _artifact_bytes(self, artifact_id: uuid.UUID | None, what: str) -> bytes:
        if artifact_id is None:
            raise DomainError(ErrorCode.CONFLICT, f"{what} artifact missing — lineage incomplete")
        artifact = self.db.get(Artifact, artifact_id)
        if artifact is None or artifact.workspace_id != self.ctx.workspace_id:
            raise DomainError(ErrorCode.NOT_FOUND, f"{what} artifact missing from vault")
        with self.vault.open_blob(self.ctx.workspace_id, artifact.storage_key) as f:
            return f.read()

    def _persist_blob(
        self,
        data: bytes,
        *,
        original_name: str,
        source_ids: list[uuid.UUID] | None = None,
        media_type: str = "application/json",
    ) -> Artifact:
        """Derived bytes → private vault artifact (confidential, §17.5)."""
        artifact = Artifact(
            workspace_id=self.ctx.workspace_id,
            storage_key="",
            media_type=media_type,
            original_name=original_name,
            source_kind="derived",
            source_artifact_ids=[str(i) for i in (source_ids or [])],
            rights={
                "retrieval": "restricted",
                "extraction": "restricted",
                "training": "owned",
                "export": "denied",
                "redistribution": "denied",
            },
            created_by=self.ctx.principal_id,
        )
        self.db.add(artifact)
        self.db.flush()
        staging = self.vault.begin_staging(self.ctx.workspace_id, artifact.id)
        self.vault.append_bytes(staging, data)
        checksum = hashlib.sha256(data).hexdigest()
        key, size = self.vault.commit(self.ctx.workspace_id, artifact.id, checksum)
        artifact.storage_key = key
        artifact.checksum_sha256 = checksum
        artifact.byte_size = size
        artifact.upload_state = "committed"
        artifact.committed_at = _now()
        self.db.flush()
        return artifact

    def _identities(
        self, release: ModelRelease
    ) -> tuple[BaseIdentity, TokenizerIdentity, AdapterIdentity]:
        return (
            BaseIdentity(
                base_model_id=release.base_model_id,
                architecture=release.architecture,
                init_seed=release.init_seed,
                base_sha256=release.base_sha256,
                license_id=release.license_id,
                parameter_count=release.parameter_count,
            ),
            TokenizerIdentity(kind=release.tokenizer_kind, sha256=release.tokenizer_sha256),
            AdapterIdentity(
                artifact_id=(
                    str(release.adapter_artifact_id) if release.adapter_artifact_id else None
                ),
                sha256=release.adapter_sha256,
                method=release.adapter_method,
                config=release.adapter_config,
                base_binding=AdapterBinding(
                    base_sha256=release.adapter_base_sha256,
                    tokenizer_sha256=release.adapter_tokenizer_sha256,
                    architecture=release.adapter_architecture,
                ),
            ),
        )

    def _request(self, release: ModelRelease) -> LoadRequest:
        base, tokenizer, adapter = self._identities(release)
        return LoadRequest(
            base=base,
            tokenizer=tokenizer,
            adapter=adapter,
            serving_format=release.serving_format,
        )

    def _bound_inputs(self, release: ModelRelease) -> dict[str, Any]:
        """What a ``model_release`` approval binds to — the exact
        artifact digests the pointer will serve."""
        return {
            "releaseId": str(release.id),
            "adapterSha256": release.adapter_sha256,
            "baseSha256": release.base_sha256,
            "tokenizerSha256": release.tokenizer_sha256,
            "servingFormat": release.serving_format,
            "conversions": [
                {"artifactId": c.get("artifactId"), "checksum": c.get("checksum")}
                for c in release.conversions
            ],
        }

    def _validate_now(
        self, release: ModelRelease, *, update_row: bool = True
    ) -> LoadValidationReport:
        """Fresh stdlib(+isolated) validation against live vault bytes."""
        adapter_bytes = self._artifact_bytes(release.adapter_artifact_id, "adapter")
        bundle_bytes: bytes | None = None
        if release.serving_format == BUNDLE_FORMAT:
            bundle = next(
                (
                    c
                    for c in release.conversions
                    if c.get("format") == BUNDLE_FORMAT and c.get("artifactId")
                ),
                None,
            )
            if bundle is not None:
                bundle_bytes = self._artifact_bytes(
                    uuid.UUID(str(bundle["artifactId"])), "conversion"
                )
        report = self.runtime.validate(
            self._request(release), adapter_bytes=adapter_bytes, bundle_bytes=bundle_bytes
        )
        if update_row:
            release.validation = report.model_dump(mode="json")
            # A compatible verdict promotes registered → validated;
            # an incompatible one never silently flips a live state —
            # the caller rejects with MODEL_INCOMPATIBLE instead.
            if report.status == "compatible" and release.state == "registered":
                release.state = "validated"
            self.db.flush()
        return report

    # ------------------------------------------------------------- register

    def register(
        self,
        *,
        training_run_id: uuid.UUID,
        name: str,
        task_id: uuid.UUID | None = None,
        serving_format: str = "peft-adapter",
    ) -> ModelRelease:
        """Register a release from a training run's persisted lineage.

        Reads the run's resolved config + result artifacts (CS-0801) —
        the adapter's recorded base/tokenizer binding comes from what
        training actually measured, not caller claims. Registration runs
        the first compatibility validation immediately."""
        self.ctx.require(CAP_MANAGE_MODELS, task_id)
        run = self.db.execute(
            select(TrainingRun).where(
                TrainingRun.id == training_run_id,
                TrainingRun.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if run is None:
            raise not_found("training run")
        if run.state in ("failed", "cancelled", "blocked", "draft"):
            raise DomainError(
                ErrorCode.CONFLICT,
                f"training run is {run.state} — nothing to register",
            )
        if run.adapter_artifact_id is None or run.result_artifact_id is None:
            raise DomainError(
                ErrorCode.CONFLICT,
                "training run has no persisted adapter/result — cannot register",
            )
        from workers.inference.model_loading import runtime as load_runtime

        outcome = json.loads(self._artifact_bytes(run.result_artifact_id, "result").decode("utf-8"))
        # Base identity comes from the run's approved spec; the
        # adapter's recorded binding (what training actually measured)
        # comes from result.json — never from caller claims.
        base_cfg = (run.spec or {}).get("model") or {}
        adapter_cfg = (run.spec or {}).get("adapter") or {}
        base_sha = outcome.get("base_sha256") or ""
        tok_sha = outcome.get("tokenizer_sha256") or ""
        if not base_sha or not tok_sha or not outcome.get("adapter_sha256"):
            raise DomainError(
                ErrorCode.CONFLICT,
                "training result lacks recorded base/tokenizer/adapter digests — "
                "compatibility binding cannot be established",
            )
        release = ModelRelease(
            workspace_id=self.ctx.workspace_id,
            task_id=task_id or run.task_id,
            name=name[:160],
            state="registered",
            snapshot_id=run.snapshot_id,
            training_run_id=run.id,
            adapter_artifact_id=run.adapter_artifact_id,
            base_model_id=str(base_cfg.get("base_model_id") or ""),
            architecture=str(base_cfg.get("architecture") or ""),
            init_seed=int(base_cfg.get("init_seed") or 0),
            base_sha256=base_sha,
            license_id=str(base_cfg.get("license_id") or ""),
            parameter_count=None,
            tokenizer_kind="char-v1",
            tokenizer_sha256=tok_sha,
            adapter_sha256=str(outcome["adapter_sha256"]),
            adapter_method=str(adapter_cfg.get("method") or "lora"),
            adapter_config=adapter_cfg,
            adapter_base_sha256=base_sha,
            adapter_tokenizer_sha256=tok_sha,
            adapter_architecture=str(base_cfg.get("architecture") or ""),
            serving_format=serving_format,
            conversions=[],
            capability=_capability_labels(load_engine_live=load_runtime.available()),
            provenance={
                "lineage": {
                    "snapshotId": str(run.snapshot_id),
                    "trainingRunId": str(run.id),
                    "adapterArtifactId": str(run.adapter_artifact_id),
                    "resultArtifactId": str(run.result_artifact_id),
                },
                "createdBy": str(self.ctx.principal_id),
                "createdAt": _now().isoformat(),
            },
            created_by=self.ctx.principal_id,
        )
        self.db.add(release)
        self.db.flush()
        self._validate_now(release)
        audit_record(
            self.db,
            self.ctx,
            action="model_release.registered",
            target_type="model_release",
            target_id=release.id,
            detail={
                "trainingRunId": str(run.id),
                "state": release.state,
                "validation": release.validation.get("status"),
            },
        )
        return release

    def validate_release(self, release_id: uuid.UUID) -> ModelRelease:
        """Re-run compatibility validation and persist the verdict."""
        self.ctx.require(CAP_MANAGE_MODELS)
        release = self._get(release_id)
        self._validate_now(release)
        audit_record(
            self.db,
            self.ctx,
            action="model_release.validated",
            target_type="model_release",
            target_id=release.id,
            detail={"status": release.validation.get("status")},
        )
        return release

    # ------------------------------------------------------------- convert

    def convert(self, release_id: uuid.UUID, *, target_format: str = BUNDLE_FORMAT) -> ModelRelease:
        """Derive a serving-format conversion artifact (§17.5): the
        bundle embeds the adapter payload + identities, gets its own
        checksum, and carries a parity evaluation proving it loads the
        same weights as the registered pair."""
        self.ctx.require(CAP_MANAGE_MODELS)
        if target_format != BUNDLE_FORMAT:
            raise DomainError(
                ErrorCode.VALIDATION, f"unsupported conversion target {target_format!r}"
            )
        release = self._get(release_id)
        if release.state not in _SERVABLE:
            raise DomainError(
                ErrorCode.CONFLICT, f"release is {release.state}; only live releases convert"
            )
        adapter_bytes = self._artifact_bytes(release.adapter_artifact_id, "adapter")
        base, tokenizer, adapter = self._identities(release)
        steps = [
            {
                "step": "embed-adapter",
                "detail": "safetensors payload embedded verbatim",
                "sha256": release.adapter_sha256,
            },
            {"step": "canonical-json", "detail": "sorted keys, UTF-8, base64 payload"},
        ]
        blob = build_bundle(
            release_id=str(release.id),
            base=base,
            tokenizer=tokenizer,
            adapter=adapter,
            adapter_bytes=adapter_bytes,
            conversion_steps=steps,
        )
        artifact = self._persist_blob(
            blob,
            original_name=f"serving-bundle-{str(release.id)[:8]}.json",
            source_ids=[release.adapter_artifact_id] if release.adapter_artifact_id else [],
        )
        # Parity is evaluated NOW against the bytes just persisted.
        from workers.inference.model_loading.verify import bundle_parity

        parity = bundle_parity(blob, base=base, tokenizer=tokenizer, adapter=adapter)
        release.conversions = [
            *release.conversions,
            {
                "conversionId": str(uuid.uuid4()),
                "artifactId": str(artifact.id),
                "format": BUNDLE_FORMAT,
                "checksum": artifact.checksum_sha256,
                "steps": steps,
                "parity": parity.model_dump(mode="json"),
                "createdAt": _now().isoformat(),
            },
        ]
        if not parity.ok:
            release.validation = {
                **release.validation,
                "conversionParity": "failed",
            }
            self.db.flush()
            raise DomainError(
                ErrorCode.MODEL_INCOMPATIBLE,
                "conversion parity failed — derived artifact does not match the registered pair",
            )
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="model_release.converted",
            target_type="model_release",
            target_id=release.id,
            detail={"format": BUNDLE_FORMAT, "artifactId": str(artifact.id)},
        )
        return release

    # ----------------------------------------------------- approve/promote

    def approve(self, release_id: uuid.UUID, *, rationale: str | None = None) -> Approval:
        """Human-holdable grant: ``approve_model`` capability only —
        agents can never call this (grant() enforces server-side)."""
        release = self._get(release_id)
        approval = grant(
            self.db,
            self.ctx,
            action=_APPROVAL_ACTION,
            bound_inputs=self._bound_inputs(release),
            rationale=rationale,
        )
        release.approval_id = approval.id
        self.db.flush()
        return approval

    def promote(self, release_id: uuid.UUID) -> ModelRelease:
        """Atomic promotion (§18.4): ONE transaction — approval
        re-validated, release re-validated, pointer row FOR UPDATE,
        old release superseded, this release promoted, its training run
        (when still at candidate_release) marked ``promoted`` — the
        only path that makes §17.5 ``promoted`` reachable."""
        self.ctx.require(CAP_MANAGE_MODELS)
        release = self._get(release_id)
        if release.state not in _SERVABLE:
            raise DomainError(
                ErrorCode.MODEL_NOT_PROMOTABLE,
                f"release is {release.state}; only validated/promotable releases promote",
            )
        if release.training_run_id is not None:
            run = self.db.get(TrainingRun, release.training_run_id)
            if run is not None and run.state not in ("candidate_release", "promoted"):
                raise DomainError(
                    ErrorCode.MODEL_NOT_PROMOTABLE,
                    f"training run is {run.state}; promotion requires candidate_release",
                )
        approval = require_valid(
            self.db,
            self.ctx,
            action=_APPROVAL_ACTION,
            bound_inputs=self._bound_inputs(release),
        )
        report = self._validate_now(release)
        if report.status != "compatible":
            raise DomainError(
                ErrorCode.MODEL_INCOMPATIBLE,
                "fresh compatibility validation failed — refusing to serve",
                safe_details={"checks": [c.name for c in report.checks if not c.ok]},
            )
        pointer = self._pointer_row()
        previous_id = pointer.release_id
        if previous_id == release.id:
            return release  # already the serving release — idempotent
        if previous_id is not None:
            previous = self.db.get(ModelRelease, previous_id)
            if previous is not None and previous.state == "promoted":
                previous.state = "superseded"
        pointer.release_id = release.id
        pointer.revision = int(pointer.revision) + 1
        pointer.reason = "promote"
        pointer.updated_by = self.ctx.principal_id
        release.state = "promoted"
        release.approval_id = approval.id
        if release.training_run_id is not None:
            run = self.db.get(TrainingRun, release.training_run_id)
            if run is not None and run.state == "candidate_release":
                # The registry's guarded path is the only allowed way
                # to reach §17.5 ``promoted`` — direct service calls
                # still raise MODEL_NOT_PROMOTABLE.
                run.state = "promoted"
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="model_release.promoted",
            target_type="model_release",
            target_id=release.id,
            detail={
                "pointerRevision": pointer.revision,
                "superseded": str(previous_id) if previous_id else None,
                "approvalId": str(approval.id),
            },
        )
        return release

    def rollback(self, release_id: uuid.UUID | None = None) -> ModelRelease:
        """Atomic rollback to a known-good release (§18.4,
        AT-0802-3): the pointer moves back in the same transaction —
        no schema/data rollback, the previous release stays with valid
        rights/lineage, and audit history is never overwritten."""
        self.ctx.require(CAP_MANAGE_MODELS)
        pointer = self._pointer_row()
        target: ModelRelease | None = None
        if release_id is not None:
            target = self._get(release_id)
        else:
            candidates = (
                self.db.execute(
                    select(ModelRelease)
                    .where(
                        ModelRelease.workspace_id == self.ctx.workspace_id,
                        ModelRelease.state == "superseded",
                    )
                    .order_by(ModelRelease.updated_at.desc(), ModelRelease.id.desc())
                )
                .scalars()
                .all()
            )
            for candidate in candidates:
                if candidate.id != pointer.release_id:
                    target = candidate
                    break
        if target is None:
            raise DomainError(ErrorCode.CONFLICT, "no known-good release to roll back to")
        if target.state not in _SERVABLE:
            raise DomainError(
                ErrorCode.CONFLICT,
                f"rollback target is {target.state}; needs a validated/superseded release",
            )
        report = self._validate_now(target)
        if report.status != "compatible":
            raise DomainError(
                ErrorCode.MODEL_INCOMPATIBLE,
                "rollback target no longer validates — pick another release",
                safe_details={"checks": [c.name for c in report.checks if not c.ok]},
            )
        previous_id = pointer.release_id
        if previous_id == target.id:
            return target
        if previous_id is not None:
            previous = self.db.get(ModelRelease, previous_id)
            if previous is not None and previous.state == "promoted":
                previous.state = "superseded"
        pointer.release_id = target.id
        pointer.revision = int(pointer.revision) + 1
        pointer.reason = "rollback"
        pointer.updated_by = self.ctx.principal_id
        target.state = "promoted"
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="model_release.rollback",
            target_type="model_release",
            target_id=target.id,
            detail={
                "pointerRevision": pointer.revision,
                "from": str(previous_id) if previous_id else None,
            },
        )
        return target

    # ------------------------------------------------------------ serving

    def bind_session(self, session_id: uuid.UUID) -> tuple[ModelRelease, LoadValidationReport]:
        """Serving request (AT-0802-1/2): resolves the session's pinned
        release — the pin freezes at session start and a pointer move
        never mutates it — then REQUIRES a fresh compatible verdict.
        A mismatched pair raises MODEL_INCOMPATIBLE, never a warning."""
        self.ctx.require(CAP_READ_PROJECT)
        session = self.db.execute(
            select(ResearchSession).where(
                ResearchSession.id == session_id,
                ResearchSession.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if session is None:
            raise not_found("session")
        pin = self.db.execute(
            select(SessionModelPin).where(
                SessionModelPin.session_id == session_id,
                SessionModelPin.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        effective = pin.release_id if pin is not None else None
        if effective is None:
            pointer = self._pointer_row()
            effective = pointer.release_id
        if effective is None:
            raise DomainError(
                ErrorCode.CONFLICT, "no model release is being served for this session"
            )
        release = self._get(effective)
        if release.state not in _SERVABLE:
            raise DomainError(
                ErrorCode.MODEL_INCOMPATIBLE,
                f"pinned release is {release.state} — not servable",
            )
        report = self._validate_now(release)
        if report.status != "compatible":
            raise DomainError(
                ErrorCode.MODEL_INCOMPATIBLE,
                "serving compatibility validation failed",
                safe_details={
                    "releaseId": str(release.id),
                    "checks": [c.name for c in report.checks if not c.ok],
                },
            )
        # Latch: a session that began with no pointer serving (or a
        # legacy session with no pin row at all) pins the release its
        # first successful bind actually used.
        if pin is None:
            pin = SessionModelPin(
                workspace_id=self.ctx.workspace_id,
                session_id=session_id,
                release_id=release.id,
            )
            self.db.add(pin)
            self.db.flush()
        elif pin.release_id is None:
            pin.release_id = release.id
            self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="model_release.bound",
            target_type="research_session",
            target_id=session_id,
            detail={"releaseId": str(release.id), "mode": report.mode},
        )
        return release, report

    # ------------------------------------------------------------- queries

    def get(self, release_id: uuid.UUID) -> ModelRelease:
        self.ctx.require(CAP_READ_PROJECT)
        return self._get(release_id)

    def pointer(self) -> ServingPointer | None:
        self.ctx.require(CAP_READ_PROJECT)
        return self.db.execute(
            select(ServingPointer).where(ServingPointer.workspace_id == self.ctx.workspace_id)
        ).scalar_one_or_none()

    def session_pins(self, task_id: uuid.UUID | None = None) -> list[SessionModelPin]:
        self.ctx.require(CAP_READ_PROJECT)
        stmt = (
            select(SessionModelPin)
            .join(
                ResearchSession,
                (ResearchSession.id == SessionModelPin.session_id)
                & (ResearchSession.workspace_id == SessionModelPin.workspace_id),
            )
            .where(SessionModelPin.workspace_id == self.ctx.workspace_id)
        )
        if task_id is not None:
            stmt = stmt.where(ResearchSession.task_id == task_id)
        return list(self.db.execute(stmt.order_by(SessionModelPin.created_at)).scalars())

    def list(self, task_id: uuid.UUID | None = None) -> list[ModelRelease]:
        self.ctx.require(CAP_READ_PROJECT)
        stmt = select(ModelRelease).where(ModelRelease.workspace_id == self.ctx.workspace_id)
        if task_id is not None:
            stmt = stmt.where(ModelRelease.task_id == task_id)
        return list(self.db.execute(stmt.order_by(ModelRelease.created_at)).scalars())

    def public_state(self, release: ModelRelease) -> dict[str, Any]:
        """Honest public view — capability labels + validation verdict."""
        return {
            "id": str(release.id),
            "name": release.name,
            "state": release.state,
            "taskId": str(release.task_id) if release.task_id else None,
            "snapshotId": str(release.snapshot_id),
            "trainingRunId": (str(release.training_run_id) if release.training_run_id else None),
            "baseModelId": release.base_model_id,
            "architecture": release.architecture,
            "baseSha256": release.base_sha256,
            "licenseId": release.license_id,
            "tokenizerKind": release.tokenizer_kind,
            "tokenizerSha256": release.tokenizer_sha256,
            "adapterSha256": release.adapter_sha256,
            "adapterMethod": release.adapter_method,
            "servingFormat": release.serving_format,
            "conversions": release.conversions,
            "validation": release.validation,
            "capability": release.capability,
            "provenance": release.provenance,
            "approvalId": str(release.approval_id) if release.approval_id else None,
            "createdAt": release.created_at.isoformat() if release.created_at else None,
            "updatedAt": release.updated_at.isoformat() if release.updated_at else None,
        }


__all__ = ["ModelRegistryService", "pin_session_start"]
