"""Local RL training runs (CS-0902, §19.4).

Lifecycle — the same §17.5 state machine as SFT, enforced by
``_ALLOWED``:

    draft → dataset_validated → awaiting_approval → queued → running →
    completed → evaluating → candidate_release → promoted | rejected
    (+ failed / cancelled / blocked)

- ``completed`` means outputs exist in the vault — never deployable;
  ``promoted`` is reachable only through the CS-0802 registry's
  approved serving-pointer move — ``transition()`` still raises
  MODEL_NOT_PROMOTABLE so no manual path can skip the gate.
- The corpus is the approval-bound input: a caller-supplied
  ``{tasks, snapshot, policy}`` document validated against the real
  CS-0901 environment contracts, persisted as a confidential vault
  artifact and digested into ``spec.corpus_digest``. The runner
  re-verifies the digest inside the container before any episode.
- Eligibility gate (mirrors AT-0801-2): at queue AND execute time the
  service re-verifies the anchor snapshot's digest/drift, live training
  rights of its included records, model license, and the bound
  approval — all BEFORE a single corpus byte leaves the vault.
- AT-0902-3: the run-level rollout envelope (``spec.rollout_budget``)
  is enforced inside the trainer by the rollout scheduler — the first
  admission that would exceed it ends the run as
  ``budget_exhausted``. There is no cloud fallback path anywhere;
  exhaustion is terminal and honest.
- AT-0902-2: rising training reward with flat/worse independent
  evaluation is rejected by the shared CS-0803 promotion gate — the RL
  run flows through ``ModelRegistryService.register`` +
  ``PromotionService.decide`` unchanged; no RL-specific gate exists
  and none may be added.
- The trainer is the pinned ``workers/training/rl/trainer`` image
  (torch CPU + trl/GRPO via ``rollout_func``, ``--network none``,
  read-only root, non-root, bounded resources, HF_HUB_OFFLINE=1); the
  policy is a locally constructed pico-RL fixture — capability labels
  stay ``fixture_only``/``not_validated``.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from chem_studio_policy.capabilities import (
    CAP_MANAGE_MODELS,
    CAP_READ_PROJECT,
    CAP_REVIEW_SCIENCE,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine_adapter_rl.contracts import (
    RL_MODEL_LICENSES,
    RlResumeSpec,
    RlTrainSpec,
    TrainerFailure,
)
from studio.application.approvals import bound_digest, grant, require_valid
from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext
from studio.config.settings import Settings
from studio.domain.evidence.vault import Vault
from studio.domain.learning.datasets import DatasetService, _canon
from studio.domain.runs.admission import AdmissionService
from studio.domain.runs.queue import RunService
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import (
    Artifact,
    DatasetSnapshot,
    EvidenceClaim,
    ExtractedRecord,
    ImportBatch,
    ResearchTask,
    RunAttempt,
    TrainingRun,
)

_APPROVAL_ACTION = "training_run"
_QUEUE_NAME = "training"
_KIND = "rl_training"

# §17.5 transitions — anything not listed is rejected; nothing leaves
# a terminal state. Identical machine to SFT.
_ALLOWED: dict[str, frozenset[str]] = {
    "draft": frozenset({"dataset_validated", "blocked", "cancelled"}),
    "dataset_validated": frozenset({"awaiting_approval", "blocked", "cancelled"}),
    "awaiting_approval": frozenset({"queued", "rejected", "blocked", "cancelled"}),
    "queued": frozenset({"running", "cancelled", "blocked"}),
    "running": frozenset({"completed", "failed", "cancelled", "blocked"}),
    "completed": frozenset({"evaluating", "rejected"}),
    "evaluating": frozenset({"candidate_release", "rejected"}),
    # promoted is reachable only through the CS-0802 registry's guarded
    # promote path (approved pointer move); the public transition()
    # still refuses it so reviewers cannot self-promote.
    "candidate_release": frozenset({"promoted", "rejected"}),
    "cancelled": frozenset({"queued"}),  # resume re-queues
    "failed": frozenset({"queued"}),  # resume re-queues
}

REVIEWER_STATES = {"evaluating", "candidate_release", "rejected"}


def _envelope(spec: dict[str, Any]) -> dict[str, int]:
    """Translate the spec's resource section into an integer admission
    envelope — fractional cores reserve whole cores."""
    import math

    resources = spec.get("resources") or {}
    cores = resources.get("cpu_cores", 1.0)
    return {
        "cpu_cores": math.ceil(float(cores)),
        "memory_bytes": int(resources.get("memory_mebibytes", 2048)) * 1024**2,
        "storage_bytes": 1024 * 1024**2,
        "wall_seconds": int(resources.get("wall_seconds", 3600)),
    }


def _now() -> datetime:
    return datetime.now(UTC)


def _default_spec() -> dict[str, Any]:
    """Default tiny local spec — pico-RL fixture base, LoRA adapter,
    strictly on-policy GRPO via rollout_func, bounded episode driver."""
    return {
        "schema_name": "rl_train_spec",
        "schema_version": 1,
        "model": {
            "base_model_id": "pico-rl-char-v1",
            "architecture": "pico-rl-v1",
            "init_seed": 0,
            "license_id": "fixture-internal",
        },
        "adapter": {
            "method": "lora",
            "rank": 8,
            "alpha": 16,
            "dropout": 0.0,
            "target_modules": ["c_attn", "c_proj"],
        },
        "optimizer": {
            "name": "adamw",
            "learning_rate": 3e-4,
            "scheduler": "linear",
            "warmup_steps": 0,
            "weight_decay": 0.0,
            "max_grad_norm": 1.0,
        },
        "algorithm": {
            "family": "grpo",
            "num_generations": 4,
            "tasks_per_batch": 2,
            "epsilon": 0.2,
            "epsilon_high": 0.2,
            "beta": 0.0,
            "scale_rewards": "group",
            "loss_type": "dapo",
            "temperature": 1.0,
            "importance_sampling_level": "token",
        },
        "rollout": {
            "max_episode_actions": 12,
            "max_candidates": 24,
            "prompt_max_tokens": 128,
            "completion_max_tokens": 896,
        },
        "rollout_budget": {
            "max_episodes": 256,
            "max_compute_units": 256.0,
            "max_policy_tokens": 4_000_000,
            "max_wall_seconds": 3600,
            "max_concurrent_rollouts": 1,
        },
        "max_steps": 8,
        "checkpoint": {"every_steps": 4, "keep_last": 3},
        "seed": 0,
        "reward_contract_version": 1,
        "resources": {"cpu_cores": 1.0, "memory_mebibytes": 2048, "wall_seconds": 3600},
        "corpus_digest": "",
    }


def _merge_spec(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Merge caller overrides over the pinned defaults (shallow per
    top-level section; nested sections merge one level)."""
    spec = _default_spec()
    for key, value in (raw or {}).items():
        if key == "corpus_digest":
            continue  # server-owned — filled from the validated corpus
        if isinstance(value, dict) and isinstance(spec.get(key), dict):
            spec[key] = {**spec[key], **value}
        else:
            spec[key] = value
    return spec


def _capability_labels(*, image_available: bool) -> dict[str, Any]:
    return {
        "scientificStatus": "not_validated",
        "dataStatus": "fixture_only",
        "engineCapability": "live" if image_available else "not_installed",
        "baseModel": "pico-rl-char-v1 (locally constructed fixture, ~0.9M params)",
        "promotion": "gated — CS-0803 evaluation machinery required",
        "egress": "none",
        "confidentiality": "vault-scoped",
        "cloudFallback": "none — exhausted envelopes stop work by design",
    }


class RlRunService:
    def __init__(
        self,
        db: Session,
        ctx: ServiceContext,
        settings: Settings,
        vault: Vault | None = None,
    ) -> None:
        self.db = db
        self.ctx = ctx
        self.settings = settings
        self.vault = vault or Vault(settings.vault_root)
        self.runs = RunService(db, ctx)
        self.admission = AdmissionService(db, ctx)
        self.datasets = DatasetService(db, ctx)

    # ------------------------------------------------------------- helpers

    def _get(self, run_id: uuid.UUID) -> TrainingRun:
        run = self.db.execute(
            select(TrainingRun).where(
                TrainingRun.id == run_id,
                TrainingRun.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if run is None:
            raise not_found("training run")
        return run

    def _transition(self, run: TrainingRun, to: str) -> None:
        allowed = _ALLOWED.get(run.state, frozenset())
        if to not in allowed:
            raise DomainError(
                ErrorCode.CONFLICT,
                f"training run cannot transition {run.state} -> {to}",
                safe_details={"state": run.state, "to": to},
            )
        run.state = to

    def _block(self, run: TrainingRun, code: str, message: str, detail: dict[str, Any]) -> None:
        run.state = "blocked"
        run.error = {"code": code, "message": message, "detail": detail}
        audit_record(
            self.db,
            self.ctx,
            action="training_run.blocked",
            target_type="training_run",
            target_id=run.id,
            detail={"code": code, **detail},
        )

    def _bound_inputs(self, run: TrainingRun) -> dict[str, Any]:
        spec = dict(run.spec)
        spec.pop("resume", None)  # resume is provenance, not approval input
        manifest = run.dataset_manifest or {}
        return {
            "snapshotId": str(run.snapshot_id),
            "snapshotDigest": run.snapshot_digest,
            "datasetDigest": run.dataset_digest,
            "specDigest": run.spec_digest,
            "modelLicense": spec.get("model", {}).get("license_id"),
            "baseModelId": spec.get("model", {}).get("base_model_id"),
            "envContractVersion": manifest.get("envContractVersion"),
            "rewardContractVersion": manifest.get("rewardContractVersion"),
        }

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

    # ------------------------------------------------------------- create

    def create(
        self,
        *,
        snapshot_id: uuid.UUID,
        corpus: dict[str, Any],
        name: str,
        task_id: uuid.UUID | None = None,
        spec: dict[str, Any] | None = None,
    ) -> TrainingRun:
        """draft → dataset_validated (or blocked): validates the corpus
        against the real CS-0901 contracts, persists corpus + config
        artifacts, and stamps ``spec.corpus_digest``. No corpus bytes
        are read for any other purpose."""
        self.ctx.require(CAP_MANAGE_MODELS, task_id)
        snap = self.db.execute(
            select(DatasetSnapshot).where(
                DatasetSnapshot.id == snapshot_id,
                DatasetSnapshot.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if snap is None:
            raise not_found("dataset snapshot")
        if task_id is not None:
            task = self.db.execute(
                select(ResearchTask).where(
                    ResearchTask.id == task_id,
                    ResearchTask.workspace_id == self.ctx.workspace_id,
                )
            ).scalar_one_or_none()
            if task is None:
                raise not_found("task")
        try:
            parsed = RlTrainSpec.model_validate(_merge_spec(spec))
        except Exception as exc:
            raise DomainError(ErrorCode.VALIDATION, f"invalid training spec: {exc}") from exc

        from workers.training.rl.trainer import runtime as rl_runtime

        run = TrainingRun(
            workspace_id=self.ctx.workspace_id,
            task_id=task_id,
            name=name[:160],
            state="draft",
            snapshot_id=snap.id,
            snapshot_digest=snap.digest,
            spec=parsed.model_dump(mode="json"),
            spec_digest=parsed.digest(),
            provenance={
                "createdBy": str(self.ctx.principal_id),
                "createdAt": _now().isoformat(),
                "chain": [],
            },
            capability=_capability_labels(image_available=rl_runtime.available()),
            created_by=self.ctx.principal_id,
        )
        self.db.add(run)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="training_run.created",
            target_type="training_run",
            target_id=run.id,
            detail={"snapshotId": str(snap.id), "specDigest": run.spec_digest},
        )
        self._validate_corpus(run, snap, corpus)
        return run

    def _validate_corpus(
        self, run: TrainingRun, snap: DatasetSnapshot, corpus: dict[str, Any]
    ) -> None:
        """draft → dataset_validated; the corpus artifact is persisted
        and digested here so approval binds to exact bytes."""
        from workers.training.rl.corpus import parse_corpus
        from workers.training.rl.environment.contracts import (
            ENV_CONTRACT_VERSION,
            REWARD_CONTRACT_VERSION,
            canonical_json,
        )
        from workers.training.rl.trainer import runtime as rl_runtime

        if snap.state != "frozen":
            self._block(
                run,
                "snapshot_not_frozen",
                "snapshot is not frozen — only frozen manifests can anchor a run",
                {"snapshotState": snap.state},
            )
            return
        drift = self.datasets.drift_status(snap.id)
        if drift["drift"]:
            self._block(
                run,
                "snapshot_drift",
                "source records changed since the snapshot was frozen",
                {"changed": drift["changed"], "missing": drift["missing"]},
            )
            return
        try:
            parsed_corpus = parse_corpus(corpus)
        except Exception as exc:
            self._block(
                run,
                "invalid_corpus",
                "corpus failed CS-0901 contract validation",
                {"detail": str(exc)[:400]},
            )
            return
        if (
            parsed_corpus.env_contract_version != ENV_CONTRACT_VERSION
            or parsed_corpus.reward_contract_version != REWARD_CONTRACT_VERSION
        ):
            self._block(
                run,
                "contract_version",
                "corpus contract versions are not the pinned service versions",
                {
                    "envContractVersion": parsed_corpus.env_contract_version,
                    "rewardContractVersion": parsed_corpus.reward_contract_version,
                },
            )
            return
        payload = canonical_json(parsed_corpus.model_dump(mode="json")).encode("utf-8")
        corpus_artifact = self._persist_blob(
            payload,
            original_name=f"rl-corpus-{str(run.id)[:8]}.json",
        )
        run.dataset_artifact_id = corpus_artifact.id
        run.dataset_digest = parsed_corpus.digest()
        run.dataset_manifest = {
            "kind": "rl_corpus",
            "taskCount": len(parsed_corpus.tasks),
            "snapshotId": parsed_corpus.snapshot.snapshot_id,
            "snapshotDigest": parsed_corpus.snapshot.digest(),
            "policyId": parsed_corpus.policy.policy_id,
            "envContractVersion": parsed_corpus.env_contract_version,
            "rewardContractVersion": parsed_corpus.reward_contract_version,
        }

        # Re-stamp the spec with the real corpus digest; the approved
        # digest covers it (§17.4, §19.4).
        spec_dict = dict(run.spec)
        spec_dict["corpus_digest"] = run.dataset_digest
        parsed = RlTrainSpec.model_validate(spec_dict)
        run.spec = parsed.model_dump(mode="json")
        run.spec_digest = parsed.digest()

        config = {
            "spec": run.spec,
            "specDigest": run.spec_digest,
            "corpusDigest": run.dataset_digest,
            "snapshotDigest": run.snapshot_digest,
            "trainerImage": rl_runtime.IMAGE,
            "boundAt": _now().isoformat(),
        }
        config_artifact = self._persist_blob(
            json.dumps(config, indent=2, sort_keys=True).encode(),
            original_name=f"rl-config-{str(run.id)[:8]}.json",
            source_ids=[corpus_artifact.id],
        )
        run.config_artifact_id = config_artifact.id
        self._transition(run, "dataset_validated")

    # ------------------------------------------------------- lifecycle

    def submit(self, run_id: uuid.UUID) -> TrainingRun:
        """dataset_validated → awaiting_approval."""
        self.ctx.require(CAP_MANAGE_MODELS)
        run = self._get(run_id)
        self._transition(run, "awaiting_approval")
        run.provenance = {
            **run.provenance,
            "submittedBy": str(self.ctx.principal_id),
            "submittedAt": _now().isoformat(),
        }
        audit_record(
            self.db,
            self.ctx,
            action="training_run.submitted",
            target_type="training_run",
            target_id=run.id,
            detail={"specDigest": run.spec_digest},
        )
        self.db.flush()
        return run

    def approve(
        self, run_id: uuid.UUID, *, decision: str, rationale: str | None = None
    ) -> TrainingRun:
        """Bind an approval to this run's exact inputs (§21.1 — the
        caller must hold ``approve_model``; agents never do)."""
        run = self._get(run_id)
        if run.state != "awaiting_approval":
            raise DomainError(
                ErrorCode.CONFLICT,
                f"training run is {run.state}, not awaiting_approval",
            )
        inputs = self._bound_inputs(run)
        approval = grant(
            self.db,
            self.ctx,
            action=_APPROVAL_ACTION,
            bound_inputs=inputs,
            decision=decision,
            rationale=rationale,
        )
        run.approval_id = approval.id
        run.bound_digest = bound_digest(inputs)
        if decision == "rejected":
            self._transition(run, "rejected")
        run.provenance = {
            **run.provenance,
            "approvalId": str(approval.id),
            "approvedBy": str(self.ctx.principal_id),
            "approvedAt": _now().isoformat(),
            "decision": decision,
        }
        self.db.flush()
        return run

    def queue(self, run_id: uuid.UUID) -> TrainingRun:
        """awaiting_approval → queued: approval re-checked, resources
        admitted, execution Run created (§13.6, §19.4)."""
        self.ctx.require(CAP_MANAGE_MODELS)
        if not self.settings.profile_training:
            raise DomainError(
                ErrorCode.ENGINE_UNAVAILABLE,
                "training profile is disabled (STUDIO_PROFILE_TRAINING=0)",
            )
        run = self._get(run_id)
        if run.state != "awaiting_approval":
            raise DomainError(
                ErrorCode.CONFLICT,
                f"training run is {run.state}, not awaiting_approval",
            )
        if self._gate(run, stage="queue"):
            return run

        exec_run = self.runs.request(
            kind=_KIND,
            request={
                "schema_version": "1",
                "training_run_id": str(run.id),
                "snapshot_id": str(run.snapshot_id),
                "snapshot_digest": run.snapshot_digest,
                "dataset_digest": run.dataset_digest,
                "spec_digest": run.spec_digest,
                "dataset_artifact_id": str(run.dataset_artifact_id),
                "resume": run.resume_from,
            },
            task_id=run.task_id,
            max_attempts=1,
        )
        decision = self.admission.admit(exec_run.id, _envelope(run.spec), queue_name=_QUEUE_NAME)
        run.run_id = exec_run.id
        if not decision.admitted:
            # The execution run was blocked by admission; mirror the
            # reason onto the training run honestly.
            self._block(
                run,
                "insufficient_local_resources",
                "resource admission denied the training run",
                {"execRunId": str(exec_run.id)},
            )
            self.db.flush()
            return run
        self._transition(run, "queued")
        audit_record(
            self.db,
            self.ctx,
            action="training_run.queued",
            target_type="training_run",
            target_id=run.id,
            detail={"runId": str(exec_run.id)},
        )
        self.db.flush()
        return run

    def execute(
        self,
        run_id: uuid.UUID,
        attempt_id: uuid.UUID,
        *,
        cancel: threading.Event | None = None,
    ) -> TrainingRun:
        """queued → running → completed/failed/cancelled. The full
        eligibility gate runs BEFORE any corpus bytes leave the vault;
        a ``budget_exhausted`` outcome lands as an honest ``failed``
        run — the envelope stopped work, nothing fell back to cloud."""
        if not self.settings.profile_training:
            raise DomainError(
                ErrorCode.ENGINE_UNAVAILABLE,
                "training profile is disabled (STUDIO_PROFILE_TRAINING=0)",
            )
        run = self._get(run_id)
        if run.state not in ("queued", "running"):
            raise DomainError(
                ErrorCode.CONFLICT, f"training run is {run.state}, not queued/running"
            )
        if self._gate(run, stage="execute"):
            return run
        if run.run_id is None:
            raise DomainError(ErrorCode.CONFLICT, "training run has no execution run attached")

        self.runs.accept_attempt(
            run_id=run.run_id, attempt_id=attempt_id, external_id=f"rl-{attempt_id}"
        )
        self.runs.start_attempt(run_id=run.run_id, attempt_id=attempt_id)
        if run.state == "queued":
            self._transition(run, "running")

        corpus_artifact = self.db.get(Artifact, run.dataset_artifact_id)
        if corpus_artifact is None:
            raise DomainError(ErrorCode.NOT_FOUND, "corpus artifact missing")
        # --- the only place corpus bytes are read: after all gates ---
        with self.vault.open_blob(self.ctx.workspace_id, corpus_artifact.storage_key) as f:
            corpus_bytes = f.read()

        resume_files: dict[str, bytes] | None = None
        spec = RlTrainSpec.model_validate(run.spec)
        if run.resume_from:
            resume_files = self._checkpoint_files(run, run.resume_from["checkpoint"])
            spec = spec.model_copy(
                update={
                    "resume": RlResumeSpec(
                        checkpoint_sha256=run.resume_from["checkpoint"]["sha256"],
                        from_step=run.resume_from["checkpoint"]["step"],
                        source_run_id=run.resume_from["sourceRunId"],
                        source_attempt_id=run.resume_from["sourceAttemptId"],
                    )
                }
            )

        from workers.training.rl.trainer import runtime as rl_runtime

        try:
            result = rl_runtime.IsolatedRl().train(
                spec, corpus=corpus_bytes, resume_files=resume_files, cancel=cancel
            )
        except TrainerFailure as exc:
            self._finish_exec(run, "failed", {"code": exc.code, "message": exc.message})
            self._transition(run, "failed")
            run.error = {"code": exc.code, "message": exc.message}
            self.db.flush()
            return run

        outcome = result.outcome
        # Persist harvested artifacts — checkpoints, telemetry, reward
        # records, episodes, adapter, result — confidential vault
        # blobs (§17.5).
        self._persist_run_artifacts(run, result)
        if outcome is not None:
            run.telemetry = {
                "optimizerSteps": outcome.optimizer_steps,
                "episodesCompleted": outcome.episodes_completed,
                "rewardFirstMean": outcome.reward_first_mean,
                "rewardLastMean": outcome.reward_last_mean,
                "budget": outcome.budget,
                "tail": outcome.telemetry_tail,
            }

        if result.status == "succeeded" and outcome is not None and outcome.usable:
            self._finish_exec(
                run,
                "succeeded",
                {
                    "adapter_sha256": outcome.adapter_sha256,
                    "optimizer_steps": outcome.optimizer_steps,
                    "episodes_completed": outcome.episodes_completed,
                    "parameter_proof": outcome.parameter_proof.model_dump(mode="json")
                    if outcome.parameter_proof
                    else None,
                },
            )
            self._transition(run, "completed")
        elif result.status == "cancelled":
            self._finish_exec(run, "cancelled", None)
            self._transition(run, "cancelled")
        elif result.status == "timed_out":
            self._finish_exec(run, "timed_out", {"code": "RUN_TIMEOUT"})
            self._transition(run, "failed")
            run.error = {"code": "RUN_TIMEOUT", "message": "training run timed out"}
        elif result.status == "budget_exhausted":
            # AT-0902-3: the rollout scheduler refused further episodes —
            # an honest terminal classification, never a fallback.
            error = (result.error or {}) or {
                "code": "BUDGET_EXHAUSTED",
                "message": "rollout compute envelope exhausted — work stopped",
            }
            self._finish_exec(run, "failed", error)
            self._transition(run, "failed")
            run.error = {
                "code": "BUDGET_EXHAUSTED",
                "message": error.get("message", "rollout compute envelope exhausted"),
                "detail": {
                    "classification": "budget_exhausted",
                    "budget": outcome.budget if outcome is not None else {},
                    "cloudFallback": "none — exhausted envelopes stop work by design",
                },
            }
        else:
            code = (result.error or {}).get("code", "training_failed")
            self._finish_exec(run, "failed", result.error or {"code": code})
            self._transition(run, "failed")
            run.error = result.error or {"code": code, "message": "trainer failed"}
        self.db.flush()
        return run

    def cancel(self, run_id: uuid.UUID) -> TrainingRun:
        """Cancel: pre-queue states stop immediately; a queued attempt
        is dropped and confirmed dead (nothing was executing); a
        running attempt is flagged cancel_requested — the executing
        thread's cancel event kills the container and lands the run in
        ``cancelled`` with its harvested checkpoint."""
        self.ctx.require(CAP_MANAGE_MODELS)
        run = self._get(run_id)
        if run.state in ("draft", "dataset_validated", "awaiting_approval"):
            self._transition(run, "cancelled")
        elif run.state == "queued" and run.run_id is not None:
            self.runs.request_cancel(run.run_id)
            self.runs.confirm_cancelled(run.run_id)
            self.admission.release(run.run_id)
            self._transition(run, "cancelled")
        elif run.state == "running" and run.run_id is not None:
            self.runs.request_cancel(run.run_id)
        self.db.flush()
        return run

    def resume(self, run_id: uuid.UUID) -> TrainingRun:
        """cancelled/failed → queued from the newest harvested
        checkpoint; the resume source + config are recorded so outputs
        stay attributable (mirrors AT-0801-3)."""
        self.ctx.require(CAP_MANAGE_MODELS)
        run = self._get(run_id)
        if run.state not in ("cancelled", "failed"):
            raise DomainError(
                ErrorCode.CONFLICT,
                f"training run is {run.state}; only cancelled/failed can resume",
            )
        if not run.checkpoints:
            raise DomainError(
                ErrorCode.CONFLICT, "no checkpoint to resume from — nothing was persisted"
            )
        latest = sorted(run.checkpoints, key=lambda c: c["step"])[-1]
        # Re-validate the approval for the SAME bound inputs — the
        # resume does not change corpus/spec digests.
        require_valid(
            self.db, self.ctx, action=_APPROVAL_ACTION, bound_inputs=self._bound_inputs(run)
        )
        source_run_id = str(run.run_id) if run.run_id else "unknown"
        run.resume_from = {
            "checkpoint": latest,
            "fromStep": latest["step"],
            "sourceRunId": source_run_id,
            "sourceAttemptId": latest.get("attemptId", source_run_id),
            "resumedAt": _now().isoformat(),
        }
        run.provenance = {
            **run.provenance,
            "chain": [
                *run.provenance.get("chain", []),
                {
                    "event": "resume",
                    "fromStep": latest["step"],
                    "checkpointSha256": latest["sha256"],
                    "sourceRunId": source_run_id,
                    "resumedBy": str(self.ctx.principal_id),
                    "resumedAt": _now().isoformat(),
                },
            ],
        }
        run.error = None
        # Re-queue: admit + enqueue a fresh execution Run.
        exec_run = self.runs.request(
            kind=_KIND,
            request={
                "schema_version": "1",
                "training_run_id": str(run.id),
                "snapshot_id": str(run.snapshot_id),
                "snapshot_digest": run.snapshot_digest,
                "dataset_digest": run.dataset_digest,
                "spec_digest": run.spec_digest,
                "dataset_artifact_id": str(run.dataset_artifact_id),
                "resume": run.resume_from,
            },
            task_id=run.task_id,
            max_attempts=1,
        )
        decision = self.admission.admit(exec_run.id, _envelope(run.spec), queue_name=_QUEUE_NAME)
        run.run_id = exec_run.id
        if not decision.admitted:
            self._block(
                run,
                "insufficient_local_resources",
                "resource admission denied the resume",
                {"execRunId": str(exec_run.id)},
            )
            self.db.flush()
            return run
        self._transition(run, "queued")
        audit_record(
            self.db,
            self.ctx,
            action="training_run.resumed",
            target_type="training_run",
            target_id=run.id,
            detail={"fromStep": latest["step"], "checkpointSha256": latest["sha256"]},
        )
        self.db.flush()
        return run

    def transition(
        self, run_id: uuid.UUID, *, to_state: str, rationale: str | None = None
    ) -> TrainingRun:
        """Reviewer-driven lifecycle moves: completed → evaluating →
        candidate_release → rejected. ``promoted`` is reachable only via
        the CS-0802 model registry's approved serving pointer move —
        a reviewer can never promote a run directly here."""
        self.ctx.require(CAP_REVIEW_SCIENCE)
        run = self._get(run_id)
        if to_state == "promoted":
            raise DomainError(
                ErrorCode.MODEL_NOT_PROMOTABLE,
                "promotion requires the model registry's approved serving pointer",
            )
        if to_state not in REVIEWER_STATES:
            raise DomainError(
                ErrorCode.VALIDATION, f"cannot transition a run into '{to_state}' manually"
            )
        self._transition(run, to_state)
        run.provenance = {
            **run.provenance,
            "chain": [
                *run.provenance.get("chain", []),
                {
                    "event": "transition",
                    "to": to_state,
                    "by": str(self.ctx.principal_id),
                    "at": _now().isoformat(),
                    "rationale": rationale,
                },
            ],
        }
        audit_record(
            self.db,
            self.ctx,
            action="training_run.transition",
            target_type="training_run",
            target_id=run.id,
            detail={"to": to_state},
        )
        self.db.flush()
        return run

    # ------------------------------------------------------------- gate

    def _gate(self, run: TrainingRun, *, stage: str) -> bool:
        """Eligibility gate (mirrors AT-0801-2). Every check runs
        BEFORE any corpus byte is read; a failure puts the run in
        ``blocked`` and returns True."""
        snap = self.db.get(DatasetSnapshot, run.snapshot_id)
        problems: dict[str, Any] = {}

        # 1. anchor snapshot still frozen + digest intact + no drift
        if snap is None or snap.state != "frozen":
            problems["snapshot"] = "missing or unfrozen"
        else:
            if snap.digest != run.snapshot_digest:
                problems["snapshotDigest"] = "run approved against a different snapshot"
            recomputed = hashlib.sha256(_canon(snap.manifest)).hexdigest()
            if recomputed != snap.digest:
                problems["manifestTampered"] = "manifest digest no longer matches content"
            else:
                drift = self.datasets.drift_status(snap.id)
                if drift["drift"]:
                    problems["drift"] = {
                        "changed": drift["changed"],
                        "missing": drift["missing"],
                    }

        # 2. live training rights for every included record — rights
        #    can be revoked after freeze; re-resolve, never trust the
        #    frozen label. The corpus is caller-supplied, but it is
        #    anchored to this snapshot's provenance, so the same
        #    contract applies.
        if snap is not None:
            blocked_records = self._live_rights_violations(snap)
            if blocked_records:
                problems["trainingRights"] = blocked_records

        # 3. model license approval — the license must still permit
        #    training for this architecture.
        spec = run.spec or {}
        license_id = (spec.get("model") or {}).get("license_id")
        license_row = RL_MODEL_LICENSES.get(str(license_id))
        if license_row is None or license_row.get("training") != "allowed":
            problems["license"] = f"license {license_id} does not permit training"

        # 4. approval still valid for exactly these bound inputs
        try:
            require_valid(
                self.db,
                self.ctx,
                action=_APPROVAL_ACTION,
                bound_inputs=self._bound_inputs(run),
            )
        except DomainError as exc:
            problems["approval"] = exc.code.value

        # 5. corpus artifact exists and its checksum still matches the
        #    approved digest (tamper check — metadata only, no bytes).
        if run.dataset_artifact_id:
            artifact = self.db.get(Artifact, run.dataset_artifact_id)
            if artifact is None or artifact.upload_state != "committed":
                problems["corpusArtifact"] = "missing"
            elif artifact.checksum_sha256 != run.dataset_digest:
                problems["corpusArtifact"] = "checksum mismatch — bytes tampered"

        if not problems:
            return False
        self._block(
            run,
            "eligibility_gate",
            f"training blocked at {stage}: eligibility checks failed",
            {"stage": stage, "problems": problems},
        )
        self.db.flush()
        return True

    def _live_rights_violations(self, snap: DatasetSnapshot) -> list[str]:
        """Re-resolve training rights for included manifest entries
        against LIVE source rows (claims → source artifact rights);
        sessions are internal records and stay 'owned'."""
        violations: list[str] = []
        for entry in snap.manifest.get("entries", []):
            if entry.get("excluded"):
                continue
            if entry.get("recordKind") != "claim":
                continue  # sessions + measurements are internal-owned
            rid = uuid.UUID(str(entry["recordId"]))
            claim = self.db.get(EvidenceClaim, rid)
            if claim is None:
                violations.append(str(rid))
                continue
            rights = self._claim_training_rights(claim)
            if rights not in ("allowed", "owned"):
                violations.append(str(rid))
        return violations

    def _claim_training_rights(self, claim: EvidenceClaim) -> str:
        artifact = None
        if claim.source_record_id:
            rec = self.db.get(ExtractedRecord, claim.source_record_id)
            if rec is not None:
                batch = self.db.get(ImportBatch, rec.batch_id)
                if batch is not None:
                    artifact = self.db.get(Artifact, batch.artifact_id)
        rights = (artifact.rights or {}) if artifact else {}
        return str(rights.get("training", "unknown"))

    def _checkpoint_files(self, run: TrainingRun, checkpoint: dict[str, Any]) -> dict[str, bytes]:
        """Re-load a persisted checkpoint dir's files from the vault."""
        files: dict[str, bytes] = {}
        for name, artifact_id in (checkpoint.get("artifacts") or {}).items():
            artifact = self.db.get(Artifact, uuid.UUID(str(artifact_id)))
            if artifact is None:
                raise DomainError(
                    ErrorCode.NOT_FOUND, f"checkpoint artifact {name} missing from vault"
                )
            with self.vault.open_blob(self.ctx.workspace_id, artifact.storage_key) as f:
                files[name] = f.read()
        return files

    # ------------------------------------------------------- artifacts

    def _persist_run_artifacts(self, run: TrainingRun, result: Any) -> None:
        """Harvested scratch artifacts → confidential vault blobs:
        reward records + episode provenance (§19.4), checkpoints,
        telemetry, adapter, result."""
        artifacts = result.artifacts
        checkpoint_records: list[dict[str, Any]] = []
        for ckpt in result.checkpoints:
            prefix = ckpt.artifact + "/"
            files = {
                name[len(prefix) :]: self._persist_blob(
                    data,
                    original_name=name.replace("/", "_"),
                    source_ids=[run.dataset_artifact_id] if run.dataset_artifact_id else [],
                    media_type="application/octet-stream",
                ).id
                for name, data in artifacts.items()
                if name.startswith(prefix)
            }
            checkpoint_records.append(
                {
                    "step": ckpt.step,
                    "sha256": ckpt.sha256,
                    "artifacts": {k: str(v) for k, v in files.items()},
                }
            )
        if checkpoint_records:
            run.checkpoints = checkpoint_records
        if "adapter/adapter_model.safetensors" in artifacts:
            adapter = self._persist_blob(
                artifacts["adapter/adapter_model.safetensors"],
                original_name=f"rl-adapter-{str(run.id)[:8]}.safetensors",
                source_ids=[run.dataset_artifact_id] if run.dataset_artifact_id else [],
                media_type="application/octet-stream",
            )
            run.adapter_artifact_id = adapter.id
        result_payload = artifacts.get("result.json")
        if result_payload is None and result.outcome is not None:
            result_payload = json.dumps(
                result.outcome.model_dump(mode="json"), sort_keys=True
            ).encode()
        if result_payload is not None:
            result_artifact = self._persist_blob(
                result_payload,
                original_name=f"rl-result-{str(run.id)[:8]}.json",
                source_ids=[run.dataset_artifact_id] if run.dataset_artifact_id else [],
            )
            run.result_artifact_id = result_artifact.id
        if "train.jsonl" in artifacts:
            self._persist_blob(
                artifacts["train.jsonl"],
                original_name=f"rl-telemetry-{str(run.id)[:8]}.jsonl",
                source_ids=[run.dataset_artifact_id] if run.dataset_artifact_id else [],
                media_type="application/jsonl",
            )
        if "rewards.jsonl" in artifacts:
            self._persist_blob(
                artifacts["rewards.jsonl"],
                original_name=f"rl-rewards-{str(run.id)[:8]}.jsonl",
                source_ids=[run.dataset_artifact_id] if run.dataset_artifact_id else [],
                media_type="application/jsonl",
            )
        # Episode records (full provenance) — one blob per episode.
        for name, data in sorted(artifacts.items()):
            if name.startswith("episodes/") and name.endswith(".json"):
                self._persist_blob(
                    data,
                    original_name=name.replace("/", "_"),
                    source_ids=[run.dataset_artifact_id] if run.dataset_artifact_id else [],
                )

    def _finish_exec(self, run: TrainingRun, status: str, summary: Any) -> None:
        """Mirror the outcome onto the execution Run row."""
        if run.run_id is None:
            return
        attempt = (
            self.db.execute(
                select(RunAttempt)
                .where(RunAttempt.run_id == run.run_id)
                .order_by(RunAttempt.attempt_number.desc())
            )
            .scalars()
            .first()
        )
        if attempt is None:
            return
        # Every terminal path frees the compute reservation in the same
        # transaction as the run's terminal update (§13.5, AT-0403-2).
        self.admission.release(run.run_id)
        if status == "succeeded":
            self.runs.complete_attempt(
                run_id=run.run_id, attempt_id=attempt.id, result_summary=summary or {}
            )
        elif status == "cancelled":
            self.runs.confirm_cancelled(run.run_id)
        elif status == "timed_out":
            self.runs.timeout_attempt(run_id=run.run_id, attempt_id=attempt.id)
        else:
            self.runs.fail_attempt(
                run_id=run.run_id,
                attempt_id=attempt.id,
                code=(summary or {}).get("code", "training_failed"),
                message=(summary or {}).get("message", "training failed"),
                retryable=False,
            )

    # ------------------------------------------------------------- queries

    def get(self, run_id: uuid.UUID) -> TrainingRun:
        self.ctx.require(CAP_READ_PROJECT)
        return self._get(run_id)

    def list(self, task_id: uuid.UUID | None = None) -> list[TrainingRun]:
        self.ctx.require(CAP_READ_PROJECT)
        stmt = select(TrainingRun).where(TrainingRun.workspace_id == self.ctx.workspace_id)
        if task_id is not None:
            stmt = stmt.where(TrainingRun.task_id == task_id)
        return list(self.db.execute(stmt.order_by(TrainingRun.created_at)).scalars())

    def public_state(self, run: TrainingRun) -> dict[str, Any]:
        """Honest public view — capability labels always visible."""
        return {
            "id": str(run.id),
            "name": run.name,
            "kind": _KIND,
            "state": run.state,
            "snapshotId": str(run.snapshot_id),
            "snapshotDigest": run.snapshot_digest,
            "specDigest": run.spec_digest,
            "corpusDigest": run.dataset_digest,
            "corpusManifest": run.dataset_manifest,
            "telemetry": run.telemetry,
            "checkpoints": run.checkpoints,
            "resumeFrom": run.resume_from,
            "provenance": run.provenance,
            "capability": run.capability,
            "error": run.error,
            "runId": str(run.run_id) if run.run_id else None,
            "createdAt": run.created_at.isoformat() if run.created_at else None,
        }
