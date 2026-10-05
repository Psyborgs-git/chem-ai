"""Independent model evaluation + promotion gate (CS-0803, §18.1-18.4).

``EvaluationService`` — the versioned suite registry (public contract:
tasks, allowed-context reference, pinned tool catalog, budget,
scoring, review rules, acceptance thresholds), the hidden-label store
(``evaluation_labels`` — readable only by the evaluation *service*
principal through the ``read_eval_labels`` capability, AT-0803-2),
and matched-comparison runs (§18.2: both arms on the same tasks,
tools, context and budget, with denominators/subgroups/uncertainty).

``PromotionService`` — the §18.4 promotion algorithm as a gate in
front of CS-0802's atomic pointer move: dataset rights/hashes →
contamination → load validation → matched-baseline comparison →
safety/privacy regression → thresholds (unknown = stored blockers,
never invented) → model card → scoped human release decision →
``ModelRegistryService.promote`` for the atomic pointer move. A
training loss improvement with worse held-out performance fails
(AT-0803-1); no release can carry a blanket 'better chemistry model'
claim (AT-0803-3).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from chem_studio_policy.capabilities import (
    CAP_MANAGE_MODELS,
    CAP_READ_EVAL_LABELS,
    CAP_READ_PROJECT,
)
from sqlalchemy import select
from sqlalchemy.orm import Session
from workers.training.evaluation.backend import EvaluationBackend, default_backend
from workers.training.evaluation.contracts import (
    EvalSuiteDef,
    EvalTarget,
)
from workers.training.evaluation.runner import run_matched_comparison

from studio.application.agent_tools.registry import default_registry
from studio.application.approvals import grant, require_valid
from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext, load_context
from studio.config.settings import Settings
from studio.domain.evidence.vault import Vault
from studio.domain.learning.splits import contamination_check
from studio.errors import DomainError, ErrorCode, forbidden, not_found
from studio.persistence.models import (
    Artifact,
    DatasetSnapshot,
    EvaluationLabel,
    EvaluationRun,
    EvaluationSuite,
    ModelRelease,
    Principal,
    PrincipalCapability,
    PromotionDecision,
    TrainingRun,
)

_EVAL_SERVICE_LOGIN = "evaluation-service"
_SCOPE_APPROVAL_ACTION = "model_release_scope"

_BLOCKER_HARD = "hard"
_BLOCKER_CLAIM = "claim"


def _now() -> datetime:
    return datetime.now(UTC)


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()


def _definition_digest(definition: Any) -> str:
    return hashlib.sha256(_canonical(definition)).hexdigest()


def _target_digest(target: dict[str, Any]) -> str:
    """Content hash of a hidden label — the only label-derived value
    the public suite definition carries."""
    return hashlib.sha256(_canonical(target)).hexdigest()


class EvaluationService:
    """Suite registry, hidden labels and matched-comparison runs."""

    def __init__(
        self,
        db: Session,
        ctx: ServiceContext,
        settings: Settings,
        vault: Vault | None = None,
        backend: EvaluationBackend | None = None,
    ) -> None:
        self.db = db
        self.ctx = ctx
        self.settings = settings
        self.vault = vault or Vault(settings.vault_root)
        self.backend = backend if backend is not None else default_backend()

    # ------------------------------------------------------------- helpers

    def _get_suite(self, suite_id: uuid.UUID) -> EvaluationSuite:
        suite = self.db.execute(
            select(EvaluationSuite).where(
                EvaluationSuite.id == suite_id,
                EvaluationSuite.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if suite is None:
            raise not_found("evaluation suite")
        return suite

    def _get_release(self, release_id: uuid.UUID) -> ModelRelease:
        release = self.db.execute(
            select(ModelRelease).where(
                ModelRelease.id == release_id,
                ModelRelease.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if release is None:
            raise not_found("model release")
        return release

    def _suite_def(self, suite: EvaluationSuite) -> EvalSuiteDef:
        return EvalSuiteDef.model_validate(suite.definition)

    def _persist_blob(
        self,
        data: bytes,
        *,
        original_name: str,
        source_ids: list[uuid.UUID] | None = None,
        media_type: str = "application/json",
    ) -> Artifact:
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

    # ------------------------------------------- hidden labels (AT-0803-2)

    def _evaluation_context(self) -> ServiceContext:
        """Resolve (lazily create) the workspace's evaluation service
        principal — the one identity whose grants keep
        ``read_eval_labels`` through context loading."""
        principal = self.db.execute(
            select(Principal).where(
                Principal.workspace_id == self.ctx.workspace_id,
                Principal.login == _EVAL_SERVICE_LOGIN,
                Principal.kind == "service",
            )
        ).scalar_one_or_none()
        if principal is None:
            principal = Principal(
                workspace_id=self.ctx.workspace_id,
                kind="service",
                login=_EVAL_SERVICE_LOGIN,
                display_name="Evaluation service",
            )
            self.db.add(principal)
            self.db.flush()
        grant_row = self.db.execute(
            select(PrincipalCapability).where(
                PrincipalCapability.workspace_id == self.ctx.workspace_id,
                PrincipalCapability.principal_id == principal.id,
                PrincipalCapability.capability == CAP_READ_EVAL_LABELS,
                PrincipalCapability.revoked_at.is_(None),
            )
        ).scalar_one_or_none()
        if grant_row is None:
            self.db.add(
                PrincipalCapability(
                    workspace_id=self.ctx.workspace_id,
                    principal_id=principal.id,
                    capability=CAP_READ_EVAL_LABELS,
                    granted_by=self.ctx.principal_id,
                )
            )
            self.db.flush()
        return load_context(self.db, self.ctx.workspace_id, principal.id)

    def _label_rows(self, suite: EvaluationSuite) -> dict[str, EvalTarget]:
        rows = (
            self.db.execute(
                select(EvaluationLabel).where(
                    EvaluationLabel.workspace_id == suite.workspace_id,
                    EvaluationLabel.suite_id == suite.id,
                )
            )
            .scalars()
            .all()
        )
        out: dict[str, EvalTarget] = {}
        for row in rows:
            payload = dict(row.target)
            payload["example_id"] = row.example_id
            out[row.example_id] = EvalTarget.model_validate(payload)
        return out

    def hidden_targets(self, suite_id: uuid.UUID) -> dict[str, EvalTarget]:
        """THE capability-gated label read path (AT-0803-2).

        Two independent checks, both at the capability layer: the
        context must hold ``read_eval_labels`` (a grant that
        ``effective_grants`` strips from every user and agent kind) AND
        the principal must be service-kind — even an owner ctx is
        refused. The agent tool layer additionally has no registered
        verb that reaches this store (closed catalog)."""
        self.ctx.require(CAP_READ_EVAL_LABELS)
        if self.ctx.principal_kind != "service":
            raise forbidden("evaluation labels")
        suite = self._get_suite(suite_id)
        targets = self._label_rows(suite)
        audit_record(
            self.db,
            self.ctx,
            action="evaluation.labels.read",
            target_type="evaluation_suite",
            target_id=suite.id,
            detail={"labels": len(targets)},
        )
        return targets

    def _targets_for_run(self, suite: EvaluationSuite) -> dict[str, EvalTarget]:
        """Scoring-time label read executed under the evaluation
        service principal — the caller's ctx never touches labels."""
        eval_ctx = self._evaluation_context()
        eval_ctx.require(CAP_READ_EVAL_LABELS)
        targets = self._label_rows(suite)
        audit_record(
            self.db,
            eval_ctx,
            action="evaluation.labels.read",
            target_type="evaluation_suite",
            target_id=suite.id,
            detail={"labels": len(targets), "for": "scoring"},
        )
        return targets

    # ---------------------------------------------------------- suite CRUD

    def create_suite(
        self,
        *,
        name: str,
        kind: str,
        task_id: uuid.UUID | None = None,
        tasks: list[dict[str, Any]],
        thresholds: list[dict[str, Any]] | None = None,
        budget: dict[str, Any] | None = None,
        scoring: dict[str, Any] | None = None,
        allowed_context: dict[str, Any] | None = None,
        review_rules: dict[str, Any] | None = None,
        purpose: str = "assistant_sft",
    ) -> EvaluationSuite:
        """Register a suite draft — the public contract only; hidden
        targets are attached by ``set_labels`` and hashed per task."""
        self.ctx.require(CAP_MANAGE_MODELS, task_id)
        if kind not in ("development", "final"):
            raise DomainError(ErrorCode.VALIDATION, "kind must be development|final")
        latest = self.db.execute(
            select(EvaluationSuite.version)
            .where(
                EvaluationSuite.workspace_id == self.ctx.workspace_id,
                EvaluationSuite.name == name,
            )
            .order_by(EvaluationSuite.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        version = 1 if latest is None else int(latest) + 1
        definition = EvalSuiteDef(
            name=name,
            version=version,
            purpose=purpose,
            kind=kind,
            tasks=[dict(t) for t in tasks],
            thresholds=[dict(t) for t in (thresholds or [])],
            budget=dict(budget or {}),
            scoring=dict(scoring or {}),
            allowed_context=dict(allowed_context or {}),
            review_rules=dict(review_rules or {}),
        ).model_dump(mode="json")
        suite = EvaluationSuite(
            workspace_id=self.ctx.workspace_id,
            task_id=task_id,
            name=name,
            version=version,
            purpose=purpose,
            kind=kind,
            state="draft",
            definition=definition,
            digest=_definition_digest(definition),
            capability=self._suite_capability(),
            provenance={"source": "manual", "createdBy": str(self.ctx.principal_id)},
            created_by=self.ctx.principal_id,
        )
        self.db.add(suite)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="evaluation.suite_created",
            target_type="evaluation_suite",
            target_id=suite.id,
            detail={"name": name, "version": version, "kind": kind},
        )
        return suite

    def _suite_capability(self) -> dict[str, Any]:
        return {
            "labelAccess": "evaluation service principal only — read_eval_labels is service-only",
            "dataStatus": "fixture_only",
            "scientificStatus": "not_validated",
            "separateFromOptimizerReward": True,
        }

    def set_labels(
        self,
        suite_id: uuid.UUID,
        labels: list[dict[str, Any]],
    ) -> EvaluationSuite:
        """Attach hidden targets to a draft suite (write path is
        ``manage_models``; the READ path stays service-only). Each
        label hashes into its task's ``target_hash`` — the definition
        binds labels without carrying them."""
        suite = self._get_suite(suite_id)
        self.ctx.require(CAP_MANAGE_MODELS, suite.task_id)
        if suite.state != "draft":
            raise DomainError(ErrorCode.CONFLICT, "labels attach only to a draft suite")
        task_ids = {t["example_id"] for t in suite.definition.get("tasks", [])}
        seen: dict[str, str] = {}
        for raw in labels:
            target = EvalTarget.model_validate(raw)
            if target.example_id not in task_ids:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    f"label for unknown example '{target.example_id}'",
                )
            if target.example_id in seen:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    f"duplicate label for '{target.example_id}'",
                )
            row = self.db.execute(
                select(EvaluationLabel).where(
                    EvaluationLabel.workspace_id == self.ctx.workspace_id,
                    EvaluationLabel.suite_id == suite.id,
                    EvaluationLabel.example_id == target.example_id,
                )
            ).scalar_one_or_none()
            payload = target.model_dump(mode="json")
            payload.pop("example_id", None)
            # the stored form is what the hash binds — a verifier can
            # reproduce target_hash from the label row alone.
            seen[target.example_id] = _target_digest(payload)
            if row is None:
                row = EvaluationLabel(
                    workspace_id=self.ctx.workspace_id,
                    suite_id=suite.id,
                    example_id=target.example_id,
                    target=payload,
                )
                self.db.add(row)
            else:
                row.target = payload
        # Rehash: each labelled task records its target digest.
        definition = dict(suite.definition)
        tasks = [dict(t) for t in definition.get("tasks", [])]
        for task in tasks:
            digest = seen.get(task["example_id"])
            if digest:
                task["target_hash"] = digest
        definition["tasks"] = tasks
        suite.definition = definition
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="evaluation.labels_set",
            target_type="evaluation_suite",
            target_id=suite.id,
            detail={"labels": len(seen)},
        )
        return suite

    def freeze(self, suite_id: uuid.UUID) -> EvaluationSuite:
        """Pin the suite: every task must be labelled, the live agent
        tool catalog is snapshotted into ``tool_versions``, and the
        definition digest becomes the suite's frozen identity."""
        suite = self._get_suite(suite_id)
        self.ctx.require(CAP_MANAGE_MODELS, suite.task_id)
        if suite.state != "draft":
            raise DomainError(ErrorCode.CONFLICT, "suite is already frozen")
        tasks = suite.definition.get("tasks", [])
        unlabeled = [t["example_id"] for t in tasks if not t.get("target_hash")]
        if unlabeled:
            raise DomainError(
                ErrorCode.VALIDATION,
                "every task needs a hidden label before freeze",
                safe_details={"unlabeled": unlabeled},
            )
        catalog = default_registry().catalog()
        definition = dict(suite.definition)
        definition["tool_versions"] = {
            "tools": [{"name": d["name"], "digest": _definition_digest(d)} for d in catalog],
            "catalog_digest": _definition_digest(catalog),
        }
        suite.definition = definition
        suite.digest = _definition_digest(definition)
        suite.state = "frozen"
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="evaluation.suite_frozen",
            target_type="evaluation_suite",
            target_id=suite.id,
            detail={"digest": suite.digest[:16]},
        )
        return suite

    # ------------------------------------------------------------- queries

    def list_suites(self, task_id: uuid.UUID | None = None) -> list[EvaluationSuite]:
        self.ctx.require(CAP_READ_PROJECT)
        stmt = select(EvaluationSuite).where(EvaluationSuite.workspace_id == self.ctx.workspace_id)
        if task_id is not None:
            stmt = stmt.where(EvaluationSuite.task_id == task_id)
        stmt = stmt.order_by(EvaluationSuite.created_at.desc(), EvaluationSuite.id.desc())
        return list(self.db.execute(stmt).scalars().all())

    def get_suite(self, suite_id: uuid.UUID) -> EvaluationSuite:
        self.ctx.require(CAP_READ_PROJECT)
        return self._get_suite(suite_id)

    def list_runs(
        self,
        model_release_id: uuid.UUID | None = None,
        suite_id: uuid.UUID | None = None,
    ) -> list[EvaluationRun]:
        self.ctx.require(CAP_READ_PROJECT)
        stmt = select(EvaluationRun).where(EvaluationRun.workspace_id == self.ctx.workspace_id)
        if model_release_id is not None:
            stmt = stmt.where(EvaluationRun.model_release_id == model_release_id)
        if suite_id is not None:
            stmt = stmt.where(EvaluationRun.suite_id == suite_id)
        stmt = stmt.order_by(EvaluationRun.created_at.desc(), EvaluationRun.id.desc())
        return list(self.db.execute(stmt).scalars().all())

    def get_run(self, run_id: uuid.UUID) -> EvaluationRun:
        self.ctx.require(CAP_READ_PROJECT)
        run = self.db.execute(
            select(EvaluationRun).where(
                EvaluationRun.id == run_id,
                EvaluationRun.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if run is None:
            raise not_found("evaluation run")
        return run

    def latest_run(self, suite_id: uuid.UUID, release_id: uuid.UUID) -> EvaluationRun | None:
        return self.db.execute(
            select(EvaluationRun)
            .where(
                EvaluationRun.workspace_id == self.ctx.workspace_id,
                EvaluationRun.suite_id == suite_id,
                EvaluationRun.model_release_id == release_id,
            )
            .order_by(EvaluationRun.created_at.desc(), EvaluationRun.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    # ---------------------------------------------------------------- runs

    def _lineage_ids(self, release: ModelRelease) -> set[str]:
        """Everything the model under test was trained/derived from —
        record ids in the approved snapshot manifest, run/snapshot ids,
        and the serialized dataset's example + source ids."""
        ids: set[str] = {str(release.id)}
        if release.training_run_id is None:
            return ids
        run = self.db.get(TrainingRun, release.training_run_id)
        if run is None:
            return ids
        ids.add(str(run.id))
        ids.add(str(run.snapshot_id))
        snapshot = self.db.get(DatasetSnapshot, run.snapshot_id)
        if snapshot is not None:
            for entry in snapshot.manifest.get("entries", []):
                rid = entry.get("recordId")
                if rid:
                    ids.add(str(rid))
        if run.dataset_artifact_id is not None:
            try:
                blob = self._artifact_bytes(run.dataset_artifact_id)
            except DomainError:
                blob = b""
            for line in blob.decode("utf-8", "replace").splitlines():
                if not line.strip():
                    continue
                try:
                    ex = json.loads(line)
                except ValueError:
                    continue
                for key in ("example_id",):
                    if ex.get(key):
                        ids.add(str(ex[key]))
                for key in ("session_id", "task_id", "manifest_id"):
                    value = (ex.get("context") or {}).get(key)
                    if value:
                        ids.add(str(value))
        return ids

    def _artifact_bytes(self, artifact_id: uuid.UUID) -> bytes:
        artifact = self.db.get(Artifact, artifact_id)
        if artifact is None or artifact.workspace_id != self.ctx.workspace_id:
            raise DomainError(ErrorCode.NOT_FOUND, "dataset artifact missing from vault")
        with self.vault.open_blob(self.ctx.workspace_id, artifact.storage_key) as f:
            return f.read()

    def _contamination(
        self,
        suite: EvaluationSuite,
        release: ModelRelease,
        targets: dict[str, EvalTarget],
    ) -> dict[str, Any]:
        """Lineage + context leakage check (§18.1), plus the
        dev-vs-final discipline: evaluating a training lineage against
        a final suite that already evaluated the same lineage is the
        'repeated tuning against final' finding."""
        definition = self._suite_def(suite)
        held_out_ids: set[str] = set()
        for task in definition.tasks:
            held_out_ids.add(task.example_id)
            held_out_ids.update(task.source_record_ids)
            held_out_ids.update(task.group_keys)
        held_out_labels = {t.value for t in targets.values() if t.value}
        for t in targets.values():
            held_out_labels.update(t.required_terms)
        context_texts = [m.content for t in definition.tasks for m in t.messages]
        if definition.allowed_context.reference:
            context_texts.append(definition.allowed_context.reference)
        report = contamination_check(
            held_out_ids=held_out_ids,
            held_out_labels=held_out_labels,
            predictor_lineage_ids=self._lineage_ids(release),
            context_texts=context_texts,
        )
        findings = list(report.findings)
        if suite.kind == "final" and release.training_run_id is not None:
            # A final set already used to select a sibling release of
            # the same training lineage is no longer unseen — repeated
            # tuning against it is a contamination finding (§18.1).
            run = self.db.get(TrainingRun, release.training_run_id)
            lineage_run_ids: list[uuid.UUID] = []
            if run is not None:
                lineage_run_ids = list(
                    self.db.execute(
                        select(TrainingRun.id).where(
                            TrainingRun.workspace_id == self.ctx.workspace_id,
                            TrainingRun.snapshot_id == run.snapshot_id,
                        )
                    )
                    .scalars()
                    .all()
                )
            reused = 0
            if lineage_run_ids:
                reused = len(
                    self.db.execute(
                        select(EvaluationRun.id)
                        .join(
                            ModelRelease,
                            EvaluationRun.model_release_id == ModelRelease.id,
                        )
                        .where(
                            EvaluationRun.workspace_id == self.ctx.workspace_id,
                            EvaluationRun.suite_id == suite.id,
                            EvaluationRun.state == "completed",
                            EvaluationRun.model_release_id != release.id,
                            ModelRelease.training_run_id.in_(lineage_run_ids),
                        )
                    )
                    .scalars()
                    .all()
                )
            if reused:
                findings.append(
                    "final set reuse: suite already evaluated "
                    f"{reused} sibling release(s) of this lineage"
                )
        return {
            "checked": True,
            "suiteKind": suite.kind,
            "findings": findings,
            "contaminated": bool(findings),
        }

    def start_run(
        self,
        *,
        suite_id: uuid.UUID,
        model_release_id: uuid.UUID,
        baseline_release_id: uuid.UUID | None = None,
    ) -> EvaluationRun:
        """Execute the §18.2 matched comparison: frozen suite, digest
        verified, both arms on the same tasks/tools/budget. Refuses
        honestly when no eval backend is installed — no fabricated
        scores ever stand in for a run."""
        suite = self._get_suite(suite_id)
        self.ctx.require(CAP_MANAGE_MODELS, suite.task_id)
        if suite.state != "frozen":
            raise DomainError(ErrorCode.CONFLICT, "suite must be frozen before a run")
        if _definition_digest(suite.definition) != suite.digest:
            raise DomainError(
                ErrorCode.CONFLICT,
                "suite definition drifted from its frozen digest — re-freeze a new version",
            )
        release = self._get_release(model_release_id)
        baseline = None
        if baseline_release_id is not None:
            baseline = self._get_release(baseline_release_id)
        capability = self.backend.capability()
        if capability is None:
            raise DomainError(
                ErrorCode.ENGINE_UNAVAILABLE,
                "no evaluation runtime installed — the matched comparison cannot fabricate scores",
            )
        definition = self._suite_def(suite)
        targets = self._targets_for_run(suite)
        missing_labels = [t.example_id for t in definition.tasks if t.example_id not in targets]
        run = EvaluationRun(
            workspace_id=self.ctx.workspace_id,
            suite_id=suite.id,
            suite_digest=suite.digest,
            model_release_id=release.id,
            baseline_release_id=baseline.id if baseline else None,
            state="running",
            backend=dict(capability),
            comparison={},
            contamination={},
            blockers=[],
            capability={
                "dataStatus": "fixture_only",
                "scientificStatus": "not_validated",
                "engineCapability": capability,
                "labelAccess": "evaluation service principal only",
            },
            created_by=self.ctx.principal_id,
        )
        self.db.add(run)
        self.db.flush()
        run.contamination = self._contamination(suite, release, targets)
        if missing_labels:
            run.state = "failed"
            run.error = {
                "code": "missing_labels",
                "message": "tasks without hidden labels cannot be scored",
                "examples": missing_labels,
            }
            self.db.flush()
            return run
        try:
            report = run_matched_comparison(
                suite=definition,
                targets=targets,
                backend=self.backend,
                tool_names=default_registry().names(),
            )
            report = report.model_copy(update={"suite_digest": suite.digest})
        except Exception as exc:  # engine failure is a run state, not a crash
            run.state = "failed"
            run.error = {"code": "engine_failure", "message": str(exc)[:300]}
            self.db.flush()
            return run
        artifact = self._persist_blob(
            json.dumps(report.model_dump(mode="json"), indent=1).encode(),
            original_name=f"eval-report-{run.id}.json",
            source_ids=[release.id],
        )
        run.report_artifact_id = artifact.id
        run.comparison = report.model_dump(mode="json")
        run.blockers = self._run_blockers(run)
        run.state = "completed"
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="evaluation.run_completed",
            target_type="evaluation_run",
            target_id=run.id,
            detail={
                "suiteId": str(suite.id),
                "releaseId": str(release.id),
                "verdict": report.verdict,
            },
        )
        return run

    def _run_blockers(self, run: EvaluationRun) -> list[dict[str, Any]]:
        """Run-level blocker summary — promotion re-derives these
        authoritatively; this copy is the run's own record."""
        blockers: list[dict[str, Any]] = []
        comparison = run.comparison or {}
        if run.contamination.get("contaminated"):
            blockers.append(
                {
                    "kind": "contamination",
                    "severity": _BLOCKER_HARD,
                    "detail": "; ".join(run.contamination.get("findings", []))[:400],
                }
            )
        safety = (comparison.get("safety_regression") or {}).get("new_failures") or []
        if safety:
            blockers.append(
                {
                    "kind": "safety_regression",
                    "severity": _BLOCKER_HARD,
                    "detail": f"new safety/privacy failures: {safety}",
                }
            )
        for th in comparison.get("thresholds") or []:
            if th.get("status") == "unknown":
                blockers.append(
                    {
                        "kind": "unknown_threshold",
                        "severity": _BLOCKER_CLAIM,
                        "detail": (
                            f"metric '{th.get('metric')}' has no declared acceptance value (U14)"
                        ),
                    }
                )
            elif th.get("status") == "fail":
                blockers.append(
                    {
                        "kind": "threshold_fail",
                        "severity": _BLOCKER_HARD,
                        "detail": (
                            f"metric '{th.get('metric')}' observed "
                            f"{th.get('observed')} failed "
                            f"{th.get('direction')} {th.get('value')}"
                        ),
                    }
                )
        verdict = comparison.get("verdict")
        if verdict in ("flat", "regressed"):
            blockers.append(
                {
                    "kind": "held_out_not_improved",
                    "severity": _BLOCKER_HARD,
                    "detail": (
                        f"held-out verdict '{verdict}' "
                        f"(delta {comparison.get('aggregate', {}).get('delta')})"
                    ),
                }
            )
        elif verdict == "incomplete":
            blockers.append(
                {
                    "kind": "evaluation_incomplete",
                    "severity": _BLOCKER_HARD,
                    "detail": "no comparable aggregate could be computed",
                }
            )
        return blockers


class PromotionService:
    """The §18.4 promotion gate in front of the atomic pointer move.

    ``decide`` records an auditable verdict; ``approve_scope`` is the
    documented human release decision binding scope + limitations +
    the exact gate digest; ``promote`` re-decides fresh, refuses on
    hard blockers (AT-0803-1), re-validates the scoped approval, and
    only then delegates to ``ModelRegistryService.promote`` — the
    CS-0802 machinery is reused, never duplicated.
    """

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

    def _latest_final_run(self, release: ModelRelease) -> EvaluationRun | None:
        return self.db.execute(
            select(EvaluationRun)
            .join(EvaluationSuite, EvaluationRun.suite_id == EvaluationSuite.id)
            .where(
                EvaluationRun.workspace_id == self.ctx.workspace_id,
                EvaluationRun.model_release_id == release.id,
                EvaluationRun.state == "completed",
                EvaluationSuite.kind == "final",
            )
            .order_by(EvaluationRun.created_at.desc(), EvaluationRun.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    def _scope_bound_inputs(
        self,
        release: ModelRelease,
        scope: str,
        limitations: list[str],
        decision: PromotionDecision,
    ) -> dict[str, Any]:
        """What a scoped release approval binds — the release, the
        documented scope/limitations AND the exact gate verdict the
        approver saw (decision digest)."""
        return {
            "releaseId": str(release.id),
            "scope": scope,
            "limitations": list(limitations),
            "decisionDigest": decision.decision_digest,
            "evaluationRunId": (
                str(decision.evaluation_run_id) if decision.evaluation_run_id else None
            ),
        }

    # ------------------------------------------------------------- decide

    def decide(self, release_id: uuid.UUID) -> PromotionDecision:
        """Run the §18.4 gate and record the verdict row.

        Hard blockers refuse promotion outright; claim blockers are
        stored promotion blockers — they bar any improvement claim and
        must be bound into the scoped release approval (§18.3)."""
        self.ctx.require(CAP_MANAGE_MODELS)
        release = self._get(release_id)
        blockers: list[dict[str, Any]] = []
        run_row: EvaluationRun | None = None

        # 1. lineage: dataset snapshot + rights/digest/drift (§18.4.1)
        run = None
        snapshot = None
        if release.training_run_id is not None:
            run = self.db.get(TrainingRun, release.training_run_id)
        if run is None:
            blockers.append(
                {
                    "kind": "lineage_incomplete",
                    "severity": _BLOCKER_HARD,
                    "detail": "release has no training run lineage",
                }
            )
        else:
            snapshot = self.db.get(DatasetSnapshot, run.snapshot_id)
            if snapshot is None:
                blockers.append(
                    {
                        "kind": "lineage_incomplete",
                        "severity": _BLOCKER_HARD,
                        "detail": "training run's dataset snapshot missing",
                    }
                )
            else:
                if snapshot.state != "frozen":
                    blockers.append(
                        {
                            "kind": "dataset_not_frozen",
                            "severity": _BLOCKER_HARD,
                            "detail": "dataset snapshot is not frozen",
                        }
                    )
                if snapshot.digest != run.snapshot_digest:
                    blockers.append(
                        {
                            "kind": "dataset_digest_drift",
                            "severity": _BLOCKER_HARD,
                            "detail": "snapshot digest drifted from the approved digest",
                        }
                    )

        # 2. training run must stand at candidate_release (§17.5)
        if run is not None and run.state not in ("candidate_release", "promoted"):
            blockers.append(
                {
                    "kind": "run_not_candidate",
                    "severity": _BLOCKER_HARD,
                    "detail": f"training run is {run.state}; promotion requires candidate_release",
                }
            )

        # 3. stored load/conversion validation verdict (§18.4.3) —
        #    promote() re-validates fresh via the registry.
        validation = release.validation or {}
        if validation.get("status") not in ("compatible", None):
            blockers.append(
                {
                    "kind": "validation_incompatible",
                    "severity": _BLOCKER_HARD,
                    "detail": f"latest validation verdict: {validation.get('status')}",
                }
            )
        if validation.get("status") is None:
            blockers.append(
                {
                    "kind": "validation_missing",
                    "severity": _BLOCKER_HARD,
                    "detail": "no compatibility validation on record",
                }
            )

        # 4. matched baseline comparison on a final-kind suite (§18.4.4)
        eval_run = self._latest_final_run(release)
        comparison: dict[str, Any] = {}
        suite: EvaluationSuite | None = None
        if eval_run is None:
            blockers.append(
                {
                    "kind": "missing_evaluation",
                    "severity": _BLOCKER_HARD,
                    "detail": "no completed final-kind evaluation run for this release",
                }
            )
        else:
            run_row = eval_run
            suite = self.db.get(EvaluationSuite, eval_run.suite_id)
            comparison = eval_run.comparison or {}
            if eval_run.suite_digest != (suite.digest if suite else ""):
                blockers.append(
                    {
                        "kind": "suite_drift",
                        "severity": _BLOCKER_HARD,
                        "detail": "the run's suite digest no longer matches the suite",
                    }
                )
            contamination = eval_run.contamination or {}
            if contamination.get("contaminated"):
                blockers.append(
                    {
                        "kind": "contamination",
                        "severity": _BLOCKER_HARD,
                        "detail": "; ".join(contamination.get("findings", []))[:400],
                    }
                )
            safety = (comparison.get("safety_regression") or {}).get("new_failures") or []
            if safety:
                blockers.append(
                    {
                        "kind": "safety_regression",
                        "severity": _BLOCKER_HARD,
                        "detail": f"new safety/privacy failures vs baseline: {safety}",
                    }
                )
            verdict = comparison.get("verdict")
            # §19.4: rising training performance with flat-or-worse
            # held-out performance is a failed promotion (AT-0803-1).
            if verdict != "improved":
                blockers.append(
                    {
                        "kind": "held_out_not_improved",
                        "severity": _BLOCKER_HARD,
                        "detail": (
                            f"held-out verdict '{verdict}': candidate aggregate "
                            f"{(comparison.get('aggregate') or {}).get('candidate')} vs "
                            f"baseline {(comparison.get('aggregate') or {}).get('baseline')}"
                        ),
                    }
                )
            denominators = comparison.get("denominators") or {}
            expected = (denominators.get("expected") or {}).get("candidate") or 0
            evaluated = (denominators.get("evaluated") or {}).get("candidate") or 0
            if expected and evaluated < expected:
                blockers.append(
                    {
                        "kind": "evaluation_incomplete",
                        "severity": _BLOCKER_HARD,
                        "detail": f"candidate evaluated {evaluated}/{expected} examples",
                    }
                )
            for th in comparison.get("thresholds") or []:
                if th.get("status") == "unknown":
                    blockers.append(
                        {
                            "kind": "unknown_threshold",
                            "severity": _BLOCKER_CLAIM,
                            "detail": (
                                f"metric '{th.get('metric')}' has no declared "
                                "acceptance value (U14) — stored blocker, never filled in"
                            ),
                        }
                    )
                elif th.get("status") == "fail":
                    blockers.append(
                        {
                            "kind": "threshold_fail",
                            "severity": _BLOCKER_HARD,
                            "detail": (
                                f"metric '{th.get('metric')}' observed "
                                f"{th.get('observed')} failed "
                                f"{th.get('direction')} {th.get('value')}"
                            ),
                        }
                    )

        eligible = not any(b["severity"] == _BLOCKER_HARD for b in blockers)
        model_card = self._model_card(release, run_row, suite, blockers, eligible)
        digest = hashlib.sha256(
            _canonical(
                {
                    "releaseId": str(release.id),
                    "evaluationRunId": str(run_row.id) if run_row else None,
                    "eligible": eligible,
                    "blockers": blockers,
                }
            )
        ).hexdigest()
        decision = PromotionDecision(
            workspace_id=self.ctx.workspace_id,
            model_release_id=release.id,
            evaluation_run_id=run_row.id if run_row else None,
            eligible=eligible,
            blockers=blockers,
            model_card=model_card,
            decision_digest=digest,
            created_by=self.ctx.principal_id,
        )
        self.db.add(decision)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="promotion.decision",
            target_type="model_release",
            target_id=release.id,
            detail={
                "eligible": eligible,
                "blockers": len(blockers),
                "evaluationRunId": str(run_row.id) if run_row else None,
            },
        )
        return decision

    def _model_card(
        self,
        release: ModelRelease,
        eval_run: EvaluationRun | None,
        suite: EvaluationSuite | None,
        blockers: list[dict[str, Any]],
        eligible: bool,
    ) -> dict[str, Any]:
        """The honest card (§18.3, AT-0803-3): scope, evidence,
        limitations, blockers — and no blanket 'better chemistry
        model' claim. Scoped improvement claims require eligibility
        AND no claim blockers; the blanket claim is never permitted."""
        claim_blockers = [b for b in blockers if b["severity"] == _BLOCKER_CLAIM]
        comparison = (eval_run.comparison or {}) if eval_run else {}
        limitations = [
            "fixture/reviewed-response evaluation data — not scientific validation",
            "scientific acceptance thresholds are pending U14",
        ]
        limitations.extend(b["detail"] for b in claim_blockers)
        scoped_permitted = eligible and not claim_blockers
        return {
            "releaseId": str(release.id),
            "name": release.name,
            "state": release.state,
            "evaluatedAgainst": {
                "suiteId": str(suite.id) if suite else None,
                "suiteName": suite.name if suite else None,
                "suiteVersion": suite.version if suite else None,
                "suiteKind": suite.kind if suite else None,
                "suiteDigest": eval_run.suite_digest if eval_run else None,
                "runId": str(eval_run.id) if eval_run else None,
                "verdict": comparison.get("verdict"),
            },
            "evidence": {
                "aggregate": comparison.get("aggregate"),
                "metrics": comparison.get("metrics"),
                "denominators": comparison.get("denominators"),
                "subgroups": comparison.get("subgroups"),
            },
            "limitations": limitations,
            "blockers": blockers,
            "claims": {
                # §18.3 — the blanket claim is never permitted, even
                # when every gate passes.
                "blanketImprovedChemistry": "not_permitted",
                "scopedImprovement": "permitted" if scoped_permitted else "not_permitted",
            },
            "scientificStatus": "not_validated",
            "scope": None,
            "approvedLimitations": [],
            "capability": {
                "promotion": "approved serving pointer via scoped release decision (§18.4)",
                "labelAccess": "evaluation service principal only",
                "dataStatus": "fixture_only",
            },
        }

    # -------------------------------------------------- approve / promote

    def latest_decision(self, release_id: uuid.UUID) -> PromotionDecision | None:
        self.ctx.require(CAP_READ_PROJECT)
        return self.db.execute(
            select(PromotionDecision)
            .where(
                PromotionDecision.workspace_id == self.ctx.workspace_id,
                PromotionDecision.model_release_id == release_id,
            )
            .order_by(PromotionDecision.created_at.desc(), PromotionDecision.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    def approve_scope(
        self,
        release_id: uuid.UUID,
        *,
        scope: str,
        limitations: list[str] | None = None,
        rationale: str | None = None,
    ) -> PromotionDecision:
        """The documented human release decision (§18.3-4): binds
        scope + limitations + the exact gate verdict into a
        ``model_release_scope`` approval (``approve_model`` capability
        — agents can never grant it)."""
        release = self._get(release_id)
        decision = self.db.execute(
            select(PromotionDecision)
            .where(
                PromotionDecision.workspace_id == self.ctx.workspace_id,
                PromotionDecision.model_release_id == release.id,
            )
            .order_by(PromotionDecision.created_at.desc(), PromotionDecision.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if decision is None:
            raise DomainError(
                ErrorCode.VALIDATION,
                "no promotion decision on record — run promotion_decide first",
            )
        bound = self._scope_bound_inputs(release, scope, list(limitations or []), decision)
        approval = grant(
            self.db,
            self.ctx,
            action=_SCOPE_APPROVAL_ACTION,
            bound_inputs=bound,
            rationale=rationale,
        )
        decision.approval_id = approval.id
        card = dict(decision.model_card)
        card["scope"] = scope
        card["approvedLimitations"] = list(limitations or [])
        decision.model_card = card
        self.db.flush()
        return decision

    def promote(
        self,
        release_id: uuid.UUID,
        *,
        scope: str,
        limitations: list[str] | None = None,
    ) -> PromotionDecision:
        """Gated promotion (§18.4): fresh decision → hard blockers
        refuse (AT-0803-1) → scoped approval re-validated at execution
        time → ``ModelRegistryService.promote`` performs its own
        release approval + compatibility re-check + atomic pointer
        move. Training runs never self-approve — the human
        ``approve_model`` grants do."""
        self.ctx.require(CAP_MANAGE_MODELS)
        release = self._get(release_id)
        decision = self.decide(release_id)
        hard = [b for b in decision.blockers if b["severity"] == _BLOCKER_HARD]
        if hard:
            raise DomainError(
                ErrorCode.MODEL_NOT_PROMOTABLE,
                "promotion blocked by the evaluation gate",
                safe_details={
                    "blockers": hard,
                    "decisionId": str(decision.id),
                },
            )
        bound = self._scope_bound_inputs(release, scope, list(limitations or []), decision)
        approval = require_valid(
            self.db,
            self.ctx,
            action=_SCOPE_APPROVAL_ACTION,
            bound_inputs=bound,
        )
        from studio.domain.learning.models import ModelRegistryService

        registry = ModelRegistryService(self.db, self.ctx, self.settings, vault=self.vault)
        registry.promote(release.id)
        decision.approval_id = approval.id
        card = dict(decision.model_card)
        card["scope"] = scope
        card["approvedLimitations"] = list(limitations or [])
        decision.model_card = card
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="promotion.executed",
            target_type="model_release",
            target_id=release.id,
            detail={
                "decisionId": str(decision.id),
                "scopeApprovalId": str(approval.id),
            },
        )
        return decision
