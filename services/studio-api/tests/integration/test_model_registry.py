"""CS-0802 integration tests — model registry, serving compatibility,
session pinning, atomic pointer + rollback.

The load-engine image is not required: without it, validation runs
the stdlib structural layer (honest ``mode="stdlib"`` labels). The
containerized torch load is covered by engine tests and re-runs
automatically whenever the image is present.
"""

from __future__ import annotations

import hashlib
import json
import struct
import uuid
from pathlib import Path
from typing import Any

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext, load_context
from studio.config.settings import Settings
from studio.domain.evidence.vault import Vault
from studio.domain.learning.datasets import DatasetService
from studio.domain.learning.models import ModelRegistryService
from studio.domain.learning.sft import TrainingRunService
from studio.domain.runs.admission import AdmissionService
from studio.domain.tasks.memory import TaskMemoryService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    ServingPointer,
    SessionModelPin,
    Workspace,
)

pytestmark = pytest.mark.integration

GB = 1024**3


# ------------------------------------------------------------- fixtures


def _principal(
    session: Session, ws: Workspace, role: str, login: str
) -> tuple[Principal, ServiceContext]:
    user = Principal(workspace_id=ws.id, kind="user", login=login, display_name=login)
    session.add(user)
    session.flush()
    for cap in sorted(capabilities_for_role(role)):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=user.id, capability=cap))
    session.flush()
    return user, load_context(session, ws.id, user.id)


@pytest.fixture()
def env(session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """stdlib-only validation — deterministic with or without the
    ``chem-studio-model-load`` image (the isolated layer is covered by
    tests/engines/model_loading when the image is present)."""
    from workers.inference.model_loading import runtime as load_runtime

    monkeypatch.setattr(load_runtime, "available", lambda: False)
    ws = Workspace(slug="models", display_name="Registry tests")
    session.add(ws)
    session.flush()
    owner, ctx = _principal(session, ws, "owner", "owner")
    AdmissionService(session, ctx).ensure_group(
        "compute",
        capacity={
            "cpu_cores": 8,
            "memory_bytes": 16 * GB,
            "storage_bytes": 256 * GB,
            "concurrency": 4,
        },
        reserve={},
    )
    session.flush()
    vault_root = tmp_path / "vault"
    vault = Vault(vault_root)
    settings = Settings(profile_training=True, vault_root=vault_root)
    return {
        "ws": ws,
        "owner": owner,
        "ctx": ctx,
        "session": session,
        "vault": vault,
        "settings": settings,
        "datasets": DatasetService(session, ctx),
        "trainer": TrainingRunService(session, ctx, settings, vault),
        "registry": ModelRegistryService(session, ctx, settings, vault),
        "memory": TaskMemoryService(session, ctx),
    }


def _task(env: dict[str, Any]) -> ResearchTask:
    session: Session = env["session"]
    project = Project(workspace_id=env["ws"].id, slug="p", name="P")
    session.add(project)
    session.flush()
    task = ResearchTask(
        workspace_id=env["ws"].id,
        project_id=project.id,
        mode="improve",
        title="registry task",
        workflow_state="active",
        target_kind="formulation",
        objective="o",
    )
    session.add(task)
    session.flush()
    return task


def _safetensors(payload: bytes = b"\x00" * 16) -> bytes:
    """A real minimal safetensors file — the structural layer parses
    its header on every serving request."""
    header = json.dumps(
        {"w": {"dtype": "F32", "shape": [4], "data_offsets": [0, len(payload)]}}
    ).encode()
    return struct.pack("<Q", len(header)) + header + payload


def _fake_result(
    *,
    adapter_bytes: bytes,
    base_sha: str,
    tokenizer_sha: str,
) -> Any:
    """Fabricated SftRunResult whose result.json carries the digests
    the real trainer measures (base/tokenizer/adapter sha256)."""
    from workers.training.sft.runtime import SftRunResult

    from engine_adapter_sft.contracts import SftOutcome, SftParameterProof

    adapter_sha = hashlib.sha256(adapter_bytes).hexdigest()
    artifacts: dict[str, bytes] = {
        "adapter/adapter_model.safetensors": adapter_bytes,
        "result.json": json.dumps(
            {
                "status": "succeeded",
                "usable": True,
                "classification": "completed",
                "base_sha256": base_sha,
                "tokenizer_sha256": tokenizer_sha,
                "adapter_sha256": adapter_sha,
                "config_digest": hashlib.sha256(b"resolved-config").hexdigest(),
                "scientific_status": "not_validated",
            }
        ).encode(),
        "train.jsonl": b"{" + b'"step": 20, "loss": 2.1' + b"}\n",
    }
    body = b"ckpt" * 8
    artifacts["ckpt-000010/adapter_model.safetensors"] = body
    artifacts["ckpt-000010/meta.json"] = json.dumps(
        {"step": 10, "adapter_sha256": hashlib.sha256(body).hexdigest()}
    ).encode()
    outcome = SftOutcome(
        status="succeeded",
        usable=True,
        classification="completed",
        steps_completed=20,
        train_examples=4,
        eval_examples=2,
        final_train_loss=2.1,
        final_eval_loss=2.3,
        telemetry_tail=[{"event": "step", "step": 20, "loss": 2.1}],
        parameter_proof=SftParameterProof(
            adapter_before_sha256="0" * 64,
            adapter_after_sha256=adapter_sha,
            frozen_before_sha256="b" * 64,
            frozen_after_sha256="b" * 64,
            adapter_changed=True,
            frozen_changed=False,
            reload_sha256=adapter_sha,
            reload_matches=True,
        ),
        adapter_sha256=adapter_sha,
        scientific_status="not_validated",
    )
    from engine_adapter_sft.contracts import SftCheckpoint

    ckpts = [
        SftCheckpoint(
            step=10,
            sha256=hashlib.sha256(body).hexdigest(),
            artifact="ckpt-000010",
            optimizer_sha256=None,
        )
    ]
    return SftRunResult(status="succeeded", outcome=outcome, artifacts=artifacts, checkpoints=ckpts)


def _stub_trainer(monkeypatch: pytest.MonkeyPatch, result: Any) -> None:
    from workers.training.sft import runtime as sft_runtime

    class _Stub:
        def available(self) -> bool:
            return True

        def capability(self) -> dict[str, Any]:
            return {"capability": "stub"}

        def train(
            self,
            spec: Any,
            *,
            dataset: bytes,
            resume_files: Any = None,
            cancel: Any = None,
        ) -> Any:
            return result

    monkeypatch.setattr(sft_runtime, "IsolatedSft", _Stub)


def _attempt_id(session: Session, exec_run_id: uuid.UUID) -> uuid.UUID:
    from studio.persistence.models import RunAttempt

    return (
        session.execute(select(RunAttempt).where(RunAttempt.run_id == exec_run_id)).scalar_one().id
    )


def _completed_run(
    env: dict[str, Any],
    task: ResearchTask,
    monkeypatch: pytest.MonkeyPatch,
    *,
    adapter_bytes: bytes | None = None,
    base_sha: str = "a" * 64,
    tokenizer_sha: str = "b" * 64,
) -> Any:
    """Drive a run to candidate_release with fabricated but
    well-formed trainer artifacts (real safetensors + result.json
    digests the trainer would have measured)."""
    adapter_bytes = adapter_bytes or _safetensors()
    _stub_trainer(
        monkeypatch,
        _fake_result(adapter_bytes=adapter_bytes, base_sha=base_sha, tokenizer_sha=tokenizer_sha),
    )
    session: Session = env["session"]
    snap = env["datasets"].build(purpose="assistant_sft", name="sft", task_id=task.id)
    env["datasets"].freeze(snap.id)
    trainer: TrainingRunService = env["trainer"]
    run = trainer.create(snapshot_id=snap.id, name="run", task_id=task.id)
    trainer.submit(run.id)
    trainer.approve(run.id, decision="approved")
    run = trainer.queue(run.id)
    assert run.state == "queued", run.error
    run = trainer.execute(run.id, _attempt_id(session, run.run_id))
    assert run.state == "completed"
    run = trainer.transition(run.id, to_state="evaluating")
    return trainer.transition(run.id, to_state="candidate_release")


def _registry(env: dict[str, Any]) -> ModelRegistryService:
    return env["registry"]


def _promote(env: dict[str, Any], release_id: uuid.UUID) -> Any:
    registry = _registry(env)
    registry.approve(release_id)
    return registry.promote(release_id)


def _pin(session: Session, ws_id: uuid.UUID, session_id: uuid.UUID) -> SessionModelPin | None:
    return session.execute(
        select(SessionModelPin).where(
            SessionModelPin.workspace_id == ws_id,
            SessionModelPin.session_id == session_id,
        )
    ).scalar_one_or_none()


def _pointer(session: Session, ws_id: uuid.UUID) -> ServingPointer:
    return session.execute(
        select(ServingPointer).where(ServingPointer.workspace_id == ws_id)
    ).scalar_one()


# ------------------------------------------------------------ AT-0802-1


class TestCompatibilityRejectsMismatchedPair:
    """AT-0802-1: an adapter recorded against a different base or
    tokenizer is REJECTED at serving-request time — never warned."""

    def test_wrong_base_binding_rejected_on_bind(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task = _task(env)
        run = _completed_run(env, task, monkeypatch)
        registry = _registry(env)
        release = registry.register(training_run_id=run.id, name="rel", task_id=task.id)
        assert release.state == "validated"
        _promote(env, release.id)
        # the recorded adapter/base pairing diverges after promotion —
        # e.g. the registry row now describes an adapter trained
        # against a different base. Serving-time re-validation must
        # catch it (compat checks run fresh on every bind).
        release.adapter_base_sha256 = "f" * 64
        env["session"].flush()
        rs = env["memory"].start_session(task.id)
        with pytest.raises(DomainError) as err:
            registry.bind_session(rs.id)
        assert err.value.code == ErrorCode.MODEL_INCOMPATIBLE
        failed = {c["name"] for c in release.validation["checks"] if not c["ok"]}
        assert "adapter_base_hash" in failed

    def test_wrong_tokenizer_binding_rejected_on_bind(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task = _task(env)
        run = _completed_run(env, task, monkeypatch)
        registry = _registry(env)
        release = registry.register(training_run_id=run.id, name="rel2", task_id=task.id)
        _promote(env, release.id)
        release.adapter_tokenizer_sha256 = "e" * 64
        env["session"].flush()
        rs = env["memory"].start_session(task.id)
        with pytest.raises(DomainError) as err:
            registry.bind_session(rs.id)
        assert err.value.code == ErrorCode.MODEL_INCOMPATIBLE
        failed = {c["name"] for c in release.validation["checks"] if not c["ok"]}
        assert "adapter_tokenizer_hash" in failed

    def test_mismatch_rejected_at_promote_too(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task = _task(env)
        run = _completed_run(env, task, monkeypatch)
        registry = _registry(env)
        release = registry.register(training_run_id=run.id, name="rel3", task_id=task.id)
        release.adapter_base_sha256 = "0" * 64
        env["session"].flush()
        registry.approve(release.id)
        with pytest.raises(DomainError) as err:
            registry.promote(release.id)
        assert err.value.code == ErrorCode.MODEL_INCOMPATIBLE
        # pointer never moved — nothing is servable
        pointer = (
            env["session"]
            .execute(select(ServingPointer).where(ServingPointer.workspace_id == env["ws"].id))
            .scalar_one_or_none()
        )
        assert pointer is None or pointer.release_id is None


# ------------------------------------------------------------ AT-0802-2


class TestSessionPinning:
    """AT-0802-2: a session pins the release it began with; an atomic
    pointer move never mutates an open session's pin."""

    def test_old_session_stays_pinned_new_session_uses_pointer(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session: Session = env["session"]
        registry = _registry(env)
        task = _task(env)

        run_a = _completed_run(env, task, monkeypatch, adapter_bytes=_safetensors(b"\x01" * 16))
        rel_a = registry.register(training_run_id=run_a.id, name="release-a", task_id=task.id)
        _promote(env, rel_a.id)
        assert _pointer(session, env["ws"].id).release_id == rel_a.id

        session_a = env["memory"].start_session(task.id)
        pin_a = _pin(session, env["ws"].id, session_a.id)
        assert pin_a is not None and pin_a.release_id == rel_a.id

        run_b = _completed_run(env, task, monkeypatch, adapter_bytes=_safetensors(b"\x02" * 16))
        rel_b = registry.register(training_run_id=run_b.id, name="release-b", task_id=task.id)
        _promote(env, rel_b.id)
        pointer = _pointer(session, env["ws"].id)
        assert pointer.release_id == rel_b.id
        assert pointer.revision == 2
        assert rel_a.state == "superseded"

        # the open session is NOT re-anchored
        session.refresh(pin_a)
        assert pin_a.release_id == rel_a.id

        session_b = env["memory"].start_session(task.id)
        pin_b = _pin(session, env["ws"].id, session_b.id)
        assert pin_b is not None and pin_b.release_id == rel_b.id

        # serving bindings resolve through the pin, not the pointer
        assert registry.bind_session(session_a.id)[0].id == rel_a.id
        assert registry.bind_session(session_b.id)[0].id == rel_b.id

    def test_unpinned_legacy_session_binds_current_pointer(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session: Session = env["session"]
        registry = _registry(env)
        task = _task(env)
        run = _completed_run(env, task, monkeypatch)
        rel = registry.register(training_run_id=run.id, name="rel", task_id=task.id)
        _promote(env, rel.id)
        rs = env["memory"].start_session(task.id)
        # delete the pin to model a pre-registry session
        pin = _pin(session, env["ws"].id, rs.id)
        session.delete(pin)
        session.flush()
        bound = registry.bind_session(rs.id)
        assert bound[0].id == rel.id
        # first successful bind latches the pin permanently
        assert _pin(session, env["ws"].id, rs.id).release_id == rel.id

    def test_no_pointer_no_release_conflicts(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task = _task(env)
        rs = env["memory"].start_session(task.id)
        with pytest.raises(DomainError) as err:
            env["registry"].bind_session(rs.id)
        assert err.value.code == ErrorCode.CONFLICT


# ------------------------------------------------------------ AT-0802-3


class TestRollback:
    """AT-0802-3: rollback restores the serving pointer to the
    known-good release in one atomic move — no data/schema rollback,
    prior releases keep their lineage."""

    def test_rollback_restores_previous_release(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session: Session = env["session"]
        registry = _registry(env)
        task = _task(env)
        run_a = _completed_run(env, task, monkeypatch, adapter_bytes=_safetensors(b"\x01" * 16))
        rel_a = registry.register(training_run_id=run_a.id, name="a", task_id=task.id)
        _promote(env, rel_a.id)
        run_b = _completed_run(env, task, monkeypatch, adapter_bytes=_safetensors(b"\x02" * 16))
        rel_b = registry.register(training_run_id=run_b.id, name="b", task_id=task.id)
        _promote(env, rel_b.id)
        assert _pointer(session, env["ws"].id).release_id == rel_b.id

        registry.rollback()
        pointer = _pointer(session, env["ws"].id)
        assert pointer.release_id == rel_a.id
        assert pointer.revision == 3
        assert pointer.reason == "rollback"
        session.refresh(rel_a)
        session.refresh(rel_b)
        assert rel_a.state == "promoted"
        assert rel_b.state == "superseded"
        # history preserved — no row deleted, lineage intact
        assert rel_b.training_run_id == run_b.id
        assert rel_b.snapshot_id == run_b.snapshot_id

    def test_rollback_to_explicit_release(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session: Session = env["session"]
        registry = _registry(env)
        task = _task(env)
        run_a = _completed_run(env, task, monkeypatch, adapter_bytes=_safetensors(b"\x01" * 16))
        rel_a = registry.register(training_run_id=run_a.id, name="a", task_id=task.id)
        _promote(env, rel_a.id)
        run_b = _completed_run(env, task, monkeypatch, adapter_bytes=_safetensors(b"\x02" * 16))
        rel_b = registry.register(training_run_id=run_b.id, name="b", task_id=task.id)
        _promote(env, rel_b.id)
        registry.rollback(release_id=rel_a.id)
        assert _pointer(session, env["ws"].id).release_id == rel_a.id

    def test_rollback_requires_valid_release(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task = _task(env)
        run = _completed_run(env, task, monkeypatch)
        rel = env["registry"].register(training_run_id=run.id, name="r", task_id=task.id)
        _promote(env, rel.id)
        # target a never-promoted registered release → not a known-good
        rel2 = env["registry"].register(training_run_id=run.id, name="r2", task_id=task.id)
        rel2.state = "revoked"  # not a known-good release
        env["session"].flush()
        with pytest.raises(DomainError) as err:
            env["registry"].rollback(release_id=rel2.id)
        assert err.value.code == ErrorCode.CONFLICT


# --------------------------------------------------------------- guards


class TestGuards:
    def test_register_requires_manage_models(self, env: dict[str, Any]) -> None:
        session: Session = env["session"]
        _, vctx = _principal(session, env["ws"], "viewer", "v1")
        svc = ModelRegistryService(session, vctx, env["settings"], env["vault"])
        with pytest.raises(DomainError):
            svc.register(training_run_id=uuid.uuid4(), name="nope")

    def test_promote_requires_human_approval(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task = _task(env)
        run = _completed_run(env, task, monkeypatch)
        registry = _registry(env)
        release = registry.register(training_run_id=run.id, name="r", task_id=task.id)
        with pytest.raises(DomainError) as err:
            registry.promote(release.id)
        assert err.value.code == ErrorCode.FORBIDDEN

    def test_direct_run_transition_to_promoted_refused(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task = _task(env)
        run = _completed_run(env, task, monkeypatch)
        with pytest.raises(DomainError) as err:
            env["trainer"].transition(run.id, to_state="promoted")
        assert err.value.code == ErrorCode.MODEL_NOT_PROMOTABLE

    def test_labels_honest(self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
        task = _task(env)
        run = _completed_run(env, task, monkeypatch)
        release = env["registry"].register(training_run_id=run.id, name="labels", task_id=task.id)
        assert release.capability["scientificStatus"] == "not_validated"
        assert release.capability["dataStatus"] == "fixture_only"
        assert "evaluation gates" in release.capability["promotion"]
