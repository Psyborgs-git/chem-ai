"""CS-0801 integration tests — TrainingRun lifecycle + eligibility gate.

AT-0801-1's live-container half lives in ``tests/engines/sft`` (engine
tests skip honestly without the image); here the gate, lifecycle,
persistence, and resume bookkeeping are verified with a stub trainer —
the stub's artifacts exercise the same vault/attribution code paths.
"""

from __future__ import annotations

import hashlib
import json
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
from studio.domain.learning.sft import TrainingRunService
from studio.domain.runs.admission import AdmissionService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Artifact,
    DatasetSnapshot,
    EvidenceClaim,
    ExtractedRecord,
    ImportBatch,
    Principal,
    PrincipalCapability,
    Project,
    ResearchSession,
    ResearchTask,
    RunAttempt,
    SessionMessage,
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
def env(session: Session, tmp_path: Path) -> dict[str, Any]:
    ws = Workspace(slug="training", display_name="Training tests")
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
        "datasets": DatasetService(session, ctx),
        "service": TrainingRunService(session, ctx, settings, vault),
        "vault": vault,
        "session": session,
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
        title="SFT task",
        workflow_state="active",
        target_kind="formulation",
        objective="o",
    )
    session.add(task)
    session.flush()
    return task


def _research_session(
    env: dict[str, Any],
    task: ResearchTask,
    *,
    with_hidden: bool = True,
    with_tools: bool = True,
    unreviewed: bool = False,
) -> ResearchSession:
    """One session with an observable prefix + reviewed assistant reply.

    Assistant messages authored by a principal count as reviewed
    responses (§17.2); rationale-kind messages are hidden traces.
    """
    session: Session = env["session"]
    rs = ResearchSession(
        workspace_id=env["ws"].id,
        task_id=task.id,
        status="ended",
        started_by=env["owner"].id,
    )
    session.add(rs)
    session.flush()

    # messages order by (created_at, id) — pin increasing timestamps or
    # random uuids reorder a same-second burst
    from datetime import UTC, datetime, timedelta

    tick = {"t": datetime(2026, 1, 1, tzinfo=UTC)}

    def msg(role: str, kind: str, content: str, by: Any = None, refs: Any = None) -> None:
        tick["t"] += timedelta(seconds=1)
        session.add(
            SessionMessage(
                workspace_id=env["ws"].id,
                session_id=rs.id,
                role=role,
                kind=kind,
                content=content,
                created_by=by,
                refs=refs or {},
                created_at=tick["t"],
            )
        )

    msg("user", "message", "What is the viscosity of the PEO electrolyte?")
    if with_hidden:
        msg("system", "rationale", "private chain-of-thought — never train on this")
    if with_tools:
        msg("assistant", "tool_call", "lookup claim", env["owner"].id, {"tool": "search"})
        msg("tool", "tool_result", "viscosity 900 mPa·s", None, {"tool": "search"})
    msg(
        "assistant",
        "message",
        "The viscosity is 900 mPa·s at 25 °C.",
        env["owner"].id if not unreviewed else None,
    )
    session.flush()
    return rs


def _supplier_claim(session: Session, ws: Workspace, *, training_rights: str) -> EvidenceClaim:
    """A document claim from an imported supplier sheet — the artifact
    rights decide the claim's live training right (AT-0801-2)."""
    art = Artifact(
        workspace_id=ws.id,
        storage_key="aa/" + "a" * 62,
        media_type="text/csv",
        byte_size=4,
        checksum_sha256="a" * 64,
        original_name="supplier.csv",
        rights={"training": training_rights},
        upload_state="committed",
    )
    session.add(art)
    session.flush()
    batch = ImportBatch(
        workspace_id=ws.id,
        artifact_id=art.id,
        checksum_sha256="a" * 64,
        original_name="supplier.csv",
        detected_type="csv",
        parser_name="csv",
        parser_version="1",
        document_group=art.id,
        status="parsed",
    )
    session.add(batch)
    session.flush()
    rec = ExtractedRecord(
        workspace_id=ws.id,
        batch_id=batch.id,
        kind="row",
        locator={"row": 1},
        original_text="supplier says viscosity 900",
        payload={},
        status="accepted",
    )
    session.add(rec)
    session.flush()
    claim = EvidenceClaim(
        workspace_id=ws.id,
        kind="document_claim",
        status="accepted",
        subject={"ref": "supplier.csv"},
        statement={"claim": "viscosity 900 mPa·s"},
        source_batch_id=batch.id,
        source_record_id=rec.id,
    )
    session.add(claim)
    session.flush()
    return claim


def _snapshot(env: dict[str, Any], task: ResearchTask, *, freeze: bool = True) -> DatasetSnapshot:
    datasets: DatasetService = env["datasets"]
    snap = datasets.build(purpose="assistant_sft", name="sft-fixture", task_id=task.id)
    if freeze:
        datasets.freeze(snap.id)
    return snap


def _attempt_id(session: Session, exec_run_id: uuid.UUID) -> uuid.UUID:
    attempt = session.execute(
        select(RunAttempt).where(RunAttempt.run_id == exec_run_id)
    ).scalar_one()
    return attempt.id


def _queued_run(env: dict[str, Any], task: ResearchTask) -> Any:
    snap = _snapshot(env, task)
    svc: TrainingRunService = env["service"]
    run = svc.create(snapshot_id=snap.id, name="t", task_id=task.id)
    svc.submit(run.id)
    svc.approve(run.id, decision="approved")
    return svc.queue(run.id)


def _fake_result(*, status: str = "succeeded", steps: int = 20, checkpoints: int = 1) -> Any:
    """Fabricated SftRunResult — exercises the same vault path as the
    real isolated trainer without needing the engine image."""
    from workers.training.sft.runtime import SftRunResult

    from engine_adapter_sft.contracts import (
        SftCheckpoint,
        SftOutcome,
        SftParameterProof,
    )

    artifacts: dict[str, bytes] = {
        "adapter/adapter_model.safetensors": b"\x00adapter-bytes" * 4,
        "config.json": json.dumps({"spec": "resolved"}).encode(),
        "result.json": json.dumps({"ok": True}).encode(),
        "train.jsonl": json.dumps({"step": steps, "loss": 2.1}).encode() + b"\n",
    }
    ckpt_steps = sorted({steps, max(steps // 2, 1)})[-checkpoints:]
    ckpts: list[SftCheckpoint] = []
    for step in ckpt_steps:
        body = f"ckpt-{step}".encode() * 8
        name = f"ckpt-{step:06d}"
        artifacts[f"{name}/adapter_model.safetensors"] = body
        artifacts[f"{name}/optimizer.pt"] = body + b"opt"
        artifacts[f"{name}/meta.json"] = json.dumps(
            {"step": step, "adapter_sha256": hashlib.sha256(body).hexdigest()}
        ).encode()
        ckpts.append(
            SftCheckpoint(
                step=step,
                sha256=hashlib.sha256(body).hexdigest(),
                artifact=name,
                optimizer_sha256=hashlib.sha256(body + b"opt").hexdigest(),
            )
        )
    ckpts.sort(key=lambda c: c.step)
    outcome = SftOutcome(
        status="succeeded" if status == "succeeded" else "interrupted",
        usable=status == "succeeded",
        classification="completed" if status == "succeeded" else "cancelled",
        steps_completed=steps,
        train_examples=4,
        eval_examples=2,
        final_train_loss=2.1,
        final_eval_loss=2.3,
        telemetry_tail=[{"event": "step", "step": steps, "loss": 2.1}],
        parameter_proof=SftParameterProof(
            adapter_before_sha256="0" * 64,
            adapter_after_sha256="a" * 64,
            frozen_before_sha256="b" * 64,
            frozen_after_sha256="b" * 64,
            adapter_changed=True,
            frozen_changed=False,
            reload_sha256="a" * 64,
            reload_matches=True,
        ),
        adapter_sha256="a" * 64,
        scientific_status="not_validated",
    )
    return SftRunResult(status=status, outcome=outcome, artifacts=artifacts, checkpoints=ckpts)


def _stub_trainer(monkeypatch: pytest.MonkeyPatch, result: Any) -> type:
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
    return _Stub


# ------------------------------------------------------------ AT-0801-1
class TestDatasetBuild:
    """§17.2-17.3 example construction from a frozen snapshot."""

    def test_drops_hidden_traces_and_records_exclusions(self, env: dict[str, Any]) -> None:
        task = _task(env)
        _research_session(env, task)
        snap = _snapshot(env, task)
        svc: TrainingRunService = env["service"]
        run = svc.create(snapshot_id=snap.id, name="t1", task_id=task.id)
        assert run.state == "dataset_validated"
        manifest = run.dataset_manifest
        assert manifest["exampleCount"] == 1
        reasons = {e["reason"] for e in manifest["exclusions"]}
        assert "hidden_reasoning_trace" in reasons
        assert manifest["scientificStatus"] == "not_validated"
        assert run.dataset_digest == manifest["datasetDigest"]
        assert run.dataset_artifact_id is not None
        # spec digest was rebound to the real dataset digest
        assert run.spec["dataset_digest"] == run.dataset_digest

    def test_unreviewed_response_excluded(self, env: dict[str, Any]) -> None:
        task = _task(env)
        _research_session(env, task, unreviewed=True)
        snap = _snapshot(env, task)
        run = env["service"].create(snapshot_id=snap.id, name="t2", task_id=task.id)
        manifest = run.dataset_manifest
        assert manifest["exampleCount"] == 0
        reasons = {e["reason"] for e in manifest["exclusions"]}
        assert "unreviewed_response" in reasons
        assert "hidden_reasoning_trace" in reasons

    def test_full_lifecycle_to_completed(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_trainer(monkeypatch, _fake_result())
        task = _task(env)
        _research_session(env, task)
        run = _queued_run(env, task)
        assert run.state == "queued"
        assert run.run_id is not None

        att = _attempt_id(env["session"], run.run_id)
        run = env["service"].execute(run.id, att)
        assert run.state == "completed"
        assert run.telemetry["stepsCompleted"] == 20
        assert run.telemetry["finalTrainLoss"] == 2.1
        assert len(run.checkpoints) == 1
        assert run.adapter_artifact_id is not None
        assert run.result_artifact_id is not None
        # artifacts landed in the vault as committed private blobs
        artifact = env["session"].get(Artifact, run.adapter_artifact_id)
        assert artifact is not None and artifact.upload_state == "committed"

    def test_labels_honest(self, env: dict[str, Any]) -> None:
        task = _task(env)
        snap = _snapshot(env, task)
        svc: TrainingRunService = env["service"]
        run = svc.create(snapshot_id=snap.id, name="labels", task_id=task.id)
        state = svc.public_state(run)
        assert state["capability"]["scientificStatus"] == "not_validated"
        assert state["capability"]["dataStatus"] == "fixture_only"

    def test_capability_required(self, env: dict[str, Any]) -> None:
        session: Session = env["session"]
        _, vctx = _principal(session, env["ws"], "viewer", "v1")
        svc = TrainingRunService(session, vctx, Settings(profile_training=True), env["vault"])
        with pytest.raises(DomainError):
            svc.create(snapshot_id=uuid.uuid4(), name="nope")


# ------------------------------------------------------------ AT-0801-2
class TestEligibilityGate:
    def test_unfrozen_snapshot_blocked(self, env: dict[str, Any]) -> None:
        task = _task(env)
        _research_session(env, task)
        snap = _snapshot(env, task, freeze=False)
        run = env["service"].create(snapshot_id=snap.id, name="b1", task_id=task.id)
        assert run.state == "blocked"
        assert run.error["code"] == "snapshot_not_frozen"

    def test_missing_approval_blocks_before_bytes(self, env: dict[str, Any]) -> None:
        task = _task(env)
        snap = _snapshot(env, task)
        svc: TrainingRunService = env["service"]
        run = svc.create(snapshot_id=snap.id, name="b2", task_id=task.id)
        svc.submit(run.id)
        # queue without approve → gate blocks; approval problem recorded
        run = svc.queue(run.id)
        assert run.state == "blocked"
        assert "approval" in run.error["detail"]["problems"]

    def test_revoked_rights_block_before_bytes(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Source training rights are re-resolved live at the gate —
        revoke after freeze and queue must block BEFORE the dataset
        blob is opened (AT-0801-2)."""
        session: Session = env["session"]
        task = _task(env)
        claim = _supplier_claim(session, env["ws"], training_rights="allowed")
        snap = _snapshot(env, task)
        svc: TrainingRunService = env["service"]
        run = svc.create(snapshot_id=snap.id, name="b3", task_id=task.id)
        svc.submit(run.id)
        svc.approve(run.id, decision="approved")
        # revoke rights on the source artifact post-freeze
        rec = session.get(ExtractedRecord, claim.source_record_id)
        batch = session.get(ImportBatch, rec.batch_id)  # type: ignore[arg-type]
        artifact = session.get(Artifact, batch.artifact_id)  # type: ignore[union-attr]
        assert artifact is not None
        artifact.rights = {**artifact.rights, "training": "denied"}
        session.flush()
        # sentinel: if a blob is opened the test must fail
        called: list[bool] = []
        original_open = env["vault"].open_blob

        def _spy(*a: Any, **k: Any) -> Any:
            called.append(True)
            return original_open(*a, **k)

        monkeypatch.setattr(env["service"].vault, "open_blob", _spy)
        run = svc.queue(run.id)
        assert run.state == "blocked"
        assert "trainingRights" in run.error["detail"]["problems"]
        assert not called

    def test_execute_gate_blocks_before_dataset_blob(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Tamper with the snapshot digest post-queue: execute blocks
        BEFORE open_blob is called on the dataset artifact."""
        task = _task(env)
        run = _queued_run(env, task)
        att = _attempt_id(env["session"], run.run_id)
        # corrupt the stored snapshot digest
        snap = env["session"].get(DatasetSnapshot, run.snapshot_id)
        snap.digest = "0" * 64
        env["session"].flush()

        opened: list[bool] = []
        original_open = env["vault"].open_blob

        def _spy(*a: Any, **k: Any) -> Any:
            opened.append(True)
            return original_open(*a, **k)

        monkeypatch.setattr(env["service"].vault, "open_blob", _spy)
        run = env["service"].execute(run.id, att)
        assert run.state == "blocked"
        assert "snapshotDigest" in run.error["detail"]["problems"]
        assert not opened

    def test_drift_blocks_queue(self, env: dict[str, Any]) -> None:
        task = _task(env)
        _research_session(env, task)
        snap = _snapshot(env, task)
        svc: TrainingRunService = env["service"]
        run = svc.create(snapshot_id=snap.id, name="b4", task_id=task.id)
        svc.submit(run.id)
        svc.approve(run.id, decision="approved")
        # mutate the source session so drift_status reports a change
        session: Session = env["session"]
        rs = session.execute(
            select(ResearchSession).where(ResearchSession.task_id == task.id)
        ).scalar_one()
        session.add(
            SessionMessage(
                workspace_id=env["ws"].id,
                session_id=rs.id,
                role="user",
                kind="message",
                content="post-freeze mutation",
            )
        )
        session.flush()
        run = svc.queue(run.id)
        assert run.state == "blocked"
        assert "drift" in run.error["detail"]["problems"]


# ------------------------------------------------------------ AT-0801-3
class TestResume:
    def test_cancelled_run_resumes_with_provenance(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_trainer(monkeypatch, _fake_result(status="cancelled", steps=10))
        task = _task(env)
        run = _queued_run(env, task)
        att = _attempt_id(env["session"], run.run_id)
        run = env["service"].execute(run.id, att)
        assert run.state == "cancelled"
        assert run.checkpoints, "cancel must preserve harvested checkpoints"
        first_exec_id = run.run_id

        run = env["service"].resume(run.id)
        assert run.state == "queued"
        resume = run.resume_from
        assert resume is not None
        assert resume["fromStep"] == 10
        assert resume["sourceRunId"] == str(first_exec_id)
        chain = run.provenance["chain"]
        assert chain[-1]["event"] == "resume"
        assert chain[-1]["fromStep"] == 10

    def test_resumed_execution_reports_resume_spec(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_trainer(monkeypatch, _fake_result(status="cancelled", steps=10))
        task = _task(env)
        run = _queued_run(env, task)
        att = _attempt_id(env["session"], run.run_id)
        run = env["service"].execute(run.id, att)
        first_exec_id = run.run_id

        # second stub captures the resume spec it receives
        captured: dict[str, Any] = {}
        from workers.training.sft import runtime as sft_runtime

        class _ResumeStub:
            def available(self) -> bool:
                return True

            def train(
                self,
                spec: Any,
                *,
                dataset: bytes,
                resume_files: Any = None,
                cancel: Any = None,
            ) -> Any:
                captured["resume"] = spec.resume
                captured["resume_files"] = resume_files
                return _fake_result(status="succeeded", steps=20)

        monkeypatch.setattr(sft_runtime, "IsolatedSft", _ResumeStub)
        run = env["service"].resume(run.id)
        assert run.state == "queued"
        assert run.run_id != first_exec_id
        att2 = _attempt_id(env["session"], run.run_id)
        run = env["service"].execute(run.id, att2)
        assert run.state == "completed"
        assert captured["resume"] is not None
        assert captured["resume"].from_step == 10
        assert captured["resume"].source_run_id == str(first_exec_id)
        # checkpoint bytes were re-loaded from the vault for the resume
        assert captured["resume_files"] is not None
        assert "adapter_model.safetensors" in captured["resume_files"]

    def test_cancel_drops_queued_run(self, env: dict[str, Any]) -> None:
        task = _task(env)
        run = _queued_run(env, task)
        run = env["service"].cancel(run.id)
        assert run.state == "cancelled"

    def test_resume_requires_checkpoint(self, env: dict[str, Any]) -> None:
        task = _task(env)
        run = _queued_run(env, task)
        run = env["service"].cancel(run.id)
        assert run.state == "cancelled"
        with pytest.raises(DomainError):
            env["service"].resume(run.id)

    def test_promoted_unreachable(self, env: dict[str, Any]) -> None:
        task = _task(env)
        snap = _snapshot(env, task)
        run = env["service"].create(snapshot_id=snap.id, name="p", task_id=task.id)
        with pytest.raises(DomainError) as exc:
            env["service"].transition(run.id, to_state="promoted")
        assert exc.value.code == ErrorCode.MODEL_NOT_PROMOTABLE
