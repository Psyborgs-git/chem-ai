"""CS-0902 integration tests — RL TrainingRun lifecycle + eligibility
gate + rollout-envelope bookkeeping.

AT-0902-1's live-container half lives in ``tests/engines/rl`` (engine
tests skip honestly without the image); here the gate, lifecycle,
persistence and resume bookkeeping are verified with a stub trainer —
the stub's artifacts exercise the same vault/attribution code paths.

AT-0902-3's host half is exercised end-to-end here: a
``budget_exhausted`` trainer outcome lands the run in ``failed`` with
the BUDGET_EXHAUSTED classification + counters — the compute envelope
stops work and no cloud fallback exists anywhere in the path.
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
from studio.domain.learning.rl import RlRunService
from studio.domain.runs.admission import AdmissionService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Artifact,
    DatasetSnapshot,
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

AGENT_GRANTS = sorted(capabilities_for_role("agent"))


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
    ws = Workspace(slug="rl-training", display_name="RL training tests")
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
        "service": RlRunService(session, ctx, settings, vault),
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
        title="RL task",
        workflow_state="active",
        target_kind="formulation",
        objective="o",
    )
    session.add(task)
    session.flush()
    return task


def _snapshot(env: dict[str, Any], task: ResearchTask, *, freeze: bool = True) -> DatasetSnapshot:
    datasets: DatasetService = env["datasets"]
    snap = datasets.build(purpose="assistant_sft", name="rl-anchor", task_id=task.id)
    if freeze:
        datasets.freeze(snap.id)
    return snap


def _corpus() -> dict[str, Any]:
    """A minimal valid corpus — two tasks with replay-pinned tools."""
    return {
        "schema_name": "rl_training_corpus",
        "env_contract_version": 1,
        "reward_contract_version": 1,
        "tasks": [
            {
                "task_id": "rl-t1",
                "messages": [{"role": "user", "content": "what is the viscosity?"}],
                "subgroup": "easy",
                "answerable": True,
                "allowed_tools": ["search_evidence", "get_evidence_record"],
                "target": {
                    "expect": "exact",
                    "value": "900 mPa·s",
                    "required_evidence_ids": ["ev-a"],
                },
            },
            {
                "task_id": "rl-t2",
                "messages": [{"role": "user", "content": "report the unknown density"}],
                "subgroup": "hard",
                "answerable": False,
                "allowed_tools": ["search_evidence"],
                "target": {"expect": "abstain"},
            },
        ],
        "snapshot": {
            "snapshot_id": "snap-rl-1",
            "evidence_ids": ["ev-a", "ev-b"],
            "replay": [
                {
                    "replay_id": "r-a",
                    "tool": "search_evidence",
                    "arguments": {"query": "viscosity"},
                    "result": {"results": [{"evidence_id": "ev-a"}]},
                    "provenance": {"run_id": "fx"},
                }
            ],
            "meta": {},
        },
        "policy": {
            "policy_id": "rl-fixture-policy",
            "kind": "agent",
            "grants": AGENT_GRANTS,
            "allowed_tools": ["search_evidence", "get_evidence_record"],
        },
    }


def _attempt_id(session: Session, exec_run_id: uuid.UUID) -> uuid.UUID:
    attempt = session.execute(
        select(RunAttempt).where(RunAttempt.run_id == exec_run_id)
    ).scalar_one()
    return attempt.id


def _queued_run(env: dict[str, Any], task: ResearchTask) -> Any:
    snap = _snapshot(env, task)
    svc: RlRunService = env["service"]
    run = svc.create(snapshot_id=snap.id, corpus=_corpus(), name="rl", task_id=task.id)
    svc.submit(run.id)
    svc.approve(run.id, decision="approved")
    return svc.queue(run.id)


def _fake_result(
    *,
    status: str = "succeeded",
    steps: int = 8,
    episodes: int = 8,
) -> Any:
    """Fabricated RlRunResult — exercises the same vault path as the
    real isolated trainer without needing the engine image."""
    from workers.training.rl.trainer.runtime import RlRunResult

    from engine_adapter_rl.contracts import (
        RlCheckpoint,
        RlEpisodeSummary,
        RlOutcome,
        RlParameterProof,
    )

    body = f"ckpt-{steps}".encode() * 8
    adapter_bytes = b"\x00rl-adapter-bytes" * 4
    adapter_sha = hashlib.sha256(adapter_bytes).hexdigest()
    artifacts: dict[str, bytes] = {
        "adapter/adapter_model.safetensors": adapter_bytes,
        # result.json carries the real recorded digests — the registry
        # binds the release from THESE values, never from caller claims
        "result.json": json.dumps(
            {
                "status": "succeeded" if status == "succeeded" else "cancelled",
                "usable": status == "succeeded",
                "classification": "completed" if status == "succeeded" else "cancelled",
                "base_sha256": "b" * 64,
                "tokenizer_sha256": "t" * 64,
                "adapter_sha256": adapter_sha,
                "config_digest": hashlib.sha256(b"rl-config").hexdigest(),
                "corpus_digest": hashlib.sha256(b"corpus").hexdigest(),
                "optimizer_steps": steps,
                "episodes_completed": episodes,
                "scientific_status": "not_validated",
            }
        ).encode(),
        "train.jsonl": json.dumps({"step": steps, "loss": 1.9}).encode() + b"\n",
        "rewards.jsonl": json.dumps(
            {
                "episode_id": "ep-0001",
                "reward_contract_version": 1,
                "scalar": 0.8,
                "eligible": True,
            }
        ).encode()
        + b"\n",
        "episodes/ep-0000.json": json.dumps({"episode_id": "ep-0000"}).encode(),
        "episodes/ep-0001.json": json.dumps({"episode_id": "ep-0001"}).encode(),
    }
    artifacts["hf/checkpoint-8/adapter_model.safetensors"] = body
    artifacts["hf/checkpoint-8/optimizer.pt"] = body + b"opt"
    artifacts["hf/checkpoint-8/meta.json"] = json.dumps(
        {"step": steps, "adapter_sha256": hashlib.sha256(body).hexdigest()}
    ).encode()
    ckpts = [
        RlCheckpoint(
            step=steps,
            sha256=hashlib.sha256(body).hexdigest(),
            artifact="hf/checkpoint-8",
            optimizer_sha256=hashlib.sha256(body + b"opt").hexdigest(),
        )
    ]
    outcome = RlOutcome(
        status="succeeded" if status == "succeeded" else "cancelled",
        usable=status == "succeeded",
        classification="completed" if status == "succeeded" else "cancelled",
        base_sha256="b" * 64,
        tokenizer_sha256="t" * 64,
        adapter_sha256=adapter_sha,
        optimizer_steps=steps,
        episodes_completed=episodes,
        reward_first_mean=0.2,
        reward_last_mean=0.7,
        budget={
            "episodes": episodes,
            "computeUnits": 12.5,
            "policyTokens": 4000,
            "envelope": {"max_episodes": 256},
            "cloudFallback": "none — exhausted envelopes stop work by design",
        },
        episodes=[
            RlEpisodeSummary(
                episode_id="ep-0000",
                task_id="rl-t1",
                seed=0,
                eligible=True,
                scalar=0.8,
                task_completed=True,
            )
        ],
        parameter_proof=RlParameterProof(
            adapter_before_sha256="0" * 64,
            adapter_after_sha256=adapter_sha,
            frozen_before_sha256="b" * 64,
            frozen_after_sha256="b" * 64,
            adapter_changed=True,
            frozen_changed=False,
            reload_sha256=adapter_sha,
            reload_matches=True,
        ),
        scientific_status="not_validated",
    )
    return RlRunResult(status=status, outcome=outcome, artifacts=artifacts, checkpoints=ckpts)


def _stub_trainer(monkeypatch: pytest.MonkeyPatch, result: Any) -> type:
    from workers.training.rl.trainer import runtime as rl_runtime

    class _Stub:
        def available(self) -> bool:
            return True

        def capability(self) -> dict[str, Any]:
            return {"capability": "stub"}

        def train(
            self,
            spec: Any,
            *,
            corpus: bytes,
            resume_files: Any = None,
            cancel: Any = None,
        ) -> Any:
            return result

    monkeypatch.setattr(rl_runtime, "IsolatedRl", _Stub)
    return _Stub


# ------------------------------------------------------------ create/gate


class TestCorpusValidation:
    def test_valid_corpus_validates_and_rebinds_spec(self, env: dict[str, Any]) -> None:
        task = _task(env)
        snap = _snapshot(env, task)
        svc: RlRunService = env["service"]
        run = svc.create(snapshot_id=snap.id, corpus=_corpus(), name="c1", task_id=task.id)
        assert run.state == "dataset_validated"
        manifest = run.dataset_manifest
        assert manifest["kind"] == "rl_corpus"
        assert manifest["taskCount"] == 2
        assert manifest["policyId"] == "rl-fixture-policy"
        assert run.dataset_artifact_id is not None
        # the spec digest covers the real corpus digest
        assert run.spec["corpus_digest"] == run.dataset_digest
        # corpus persisted as a committed confidential vault artifact
        artifact = env["session"].get(Artifact, run.dataset_artifact_id)
        assert artifact is not None and artifact.upload_state == "committed"
        assert artifact.checksum_sha256 == run.dataset_digest

    def test_invalid_corpus_blocks(self, env: dict[str, Any]) -> None:
        task = _task(env)
        snap = _snapshot(env, task)
        svc: RlRunService = env["service"]
        run = svc.create(snapshot_id=snap.id, corpus={"tasks": []}, name="c2", task_id=task.id)
        assert run.state == "blocked"
        assert run.error["code"] == "invalid_corpus"

    def test_unfrozen_snapshot_blocked(self, env: dict[str, Any]) -> None:
        task = _task(env)
        snap = _snapshot(env, task, freeze=False)
        run = env["service"].create(
            snapshot_id=snap.id, corpus=_corpus(), name="c3", task_id=task.id
        )
        assert run.state == "blocked"
        assert run.error["code"] == "snapshot_not_frozen"

    def test_corpus_digest_override_ignored(self, env: dict[str, Any]) -> None:
        """The caller cannot dictate the corpus digest — the service
        computes it from the validated bytes (server-owned field)."""
        task = _task(env)
        snap = _snapshot(env, task)
        svc: RlRunService = env["service"]
        run = svc.create(
            snapshot_id=snap.id,
            corpus=_corpus(),
            name="c4",
            task_id=task.id,
            spec={"corpus_digest": "0" * 64},
        )
        assert run.state == "dataset_validated"
        assert run.spec["corpus_digest"] == run.dataset_digest != "0" * 64


class TestEligibilityGate:
    def test_missing_approval_blocks_before_bytes(self, env: dict[str, Any]) -> None:
        task = _task(env)
        snap = _snapshot(env, task)
        svc: RlRunService = env["service"]
        run = svc.create(snapshot_id=snap.id, corpus=_corpus(), name="g1", task_id=task.id)
        svc.submit(run.id)
        run = svc.queue(run.id)
        assert run.state == "blocked"
        assert "approval" in run.error["detail"]["problems"]

    def test_execute_gate_blocks_before_corpus_blob(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Tamper with the corpus artifact checksum post-queue: execute
        blocks BEFORE open_blob reads it."""
        task = _task(env)
        run = _queued_run(env, task)
        att = _attempt_id(env["session"], run.run_id)
        artifact = env["session"].get(Artifact, run.dataset_artifact_id)
        artifact.checksum_sha256 = "0" * 64  # corrupted vault metadata
        env["session"].flush()

        opened: list[bool] = []
        original_open = env["vault"].open_blob

        def _spy(*a: Any, **k: Any) -> Any:
            opened.append(True)
            return original_open(*a, **k)

        monkeypatch.setattr(env["service"].vault, "open_blob", _spy)
        run = env["service"].execute(run.id, att)
        assert run.state == "blocked"
        assert "corpusArtifact" in run.error["detail"]["problems"]
        assert not opened

    def test_drift_blocks_queue(self, env: dict[str, Any]) -> None:
        task = _task(env)
        session: Session = env["session"]
        # a session row whose mutation makes drift_status report a change
        rs = ResearchSession(
            workspace_id=env["ws"].id,
            task_id=task.id,
            status="ended",
            started_by=env["owner"].id,
        )
        session.add(rs)
        session.flush()
        snap = _snapshot(env, task)
        svc: RlRunService = env["service"]
        run = svc.create(snapshot_id=snap.id, corpus=_corpus(), name="g2", task_id=task.id)
        svc.submit(run.id)
        svc.approve(run.id, decision="approved")
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


# ------------------------------------------------------------ lifecycle


class TestLifecycle:
    def test_full_lifecycle_to_completed(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_trainer(monkeypatch, _fake_result())
        task = _task(env)
        run = _queued_run(env, task)
        assert run.state == "queued"
        assert run.run_id is not None

        att = _attempt_id(env["session"], run.run_id)
        run = env["service"].execute(run.id, att)
        assert run.state == "completed"
        assert run.telemetry["optimizerSteps"] == 8
        assert run.telemetry["episodesCompleted"] == 8
        # reward telemetry persisted — the training-reward story the
        # release gate compares against held-out evaluation
        assert run.telemetry["rewardLastMean"] > run.telemetry["rewardFirstMean"]
        assert run.telemetry["budget"]["episodes"] == 8
        assert len(run.checkpoints) == 1
        assert run.adapter_artifact_id is not None
        assert run.result_artifact_id is not None
        artifact = env["session"].get(Artifact, run.adapter_artifact_id)
        assert artifact is not None and artifact.upload_state == "committed"
        # reward records + episode traces landed in the vault
        names = {a.original_name for a in env["session"].execute(select(Artifact)).scalars().all()}
        assert any(n.startswith("rl-rewards-") for n in names)
        assert any("episodes_ep-" in (n or "") for n in names)

    def test_labels_honest(self, env: dict[str, Any]) -> None:
        task = _task(env)
        snap = _snapshot(env, task)
        svc: RlRunService = env["service"]
        run = svc.create(snapshot_id=snap.id, corpus=_corpus(), name="l1", task_id=task.id)
        state = svc.public_state(run)
        assert state["capability"]["scientificStatus"] == "not_validated"
        assert state["capability"]["dataStatus"] == "fixture_only"
        assert "none" in state["capability"]["cloudFallback"]

    def test_capability_required(self, env: dict[str, Any]) -> None:
        session: Session = env["session"]
        _, vctx = _principal(session, env["ws"], "viewer", "v1")
        svc = RlRunService(session, vctx, Settings(profile_training=True), env["vault"])
        with pytest.raises(DomainError):
            svc.create(snapshot_id=uuid.uuid4(), corpus=_corpus(), name="nope")

    def test_promoted_unreachable(self, env: dict[str, Any]) -> None:
        task = _task(env)
        snap = _snapshot(env, task)
        run = env["service"].create(
            snapshot_id=snap.id, corpus=_corpus(), name="p", task_id=task.id
        )
        with pytest.raises(DomainError) as exc:
            env["service"].transition(run.id, to_state="promoted")
        assert exc.value.code == ErrorCode.MODEL_NOT_PROMOTABLE


# ------------------------------------------------------------ AT-0902-3


class TestBudgetExhaustion:
    def test_exhausted_envelope_ends_run_failed(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The rollout scheduler stopped admitting episodes — the run
        records the exhausted counters and fails honestly; no cloud
        fallback is attempted anywhere in the path."""
        from workers.training.rl.trainer.runtime import RlRunResult

        from engine_adapter_rl.contracts import RlOutcome

        outcome = RlOutcome(
            status="budget_exhausted",
            usable=False,
            classification="budget_exhausted",
            optimizer_steps=1,
            episodes_completed=5,
            budget={
                "episodes": 5,
                "computeUnits": 5.0,
                "envelope": {"max_episodes": 5},
                "cloudFallback": "none — exhausted envelopes stop work by design",
            },
            error={"code": "BUDGET_EXHAUSTED", "message": "episodes envelope reached"},
            scientific_status="not_validated",
        )
        _stub_trainer(
            monkeypatch,
            RlRunResult(
                status="budget_exhausted",
                outcome=outcome,
                artifacts={},
                checkpoints=[],
                error={"code": "BUDGET_EXHAUSTED", "message": "episodes envelope reached"},
            ),
        )
        task = _task(env)
        run = _queued_run(env, task)
        att = _attempt_id(env["session"], run.run_id)
        run = env["service"].execute(run.id, att)
        assert run.state == "failed"
        assert run.error["code"] == "BUDGET_EXHAUSTED"
        assert run.error["detail"]["classification"] == "budget_exhausted"
        assert "none" in run.error["detail"]["cloudFallback"]
        # the meter snapshot is the run's honest record
        assert run.telemetry["budget"]["episodes"] == 5

    def test_admission_denial_blocks_run(self, env: dict[str, Any]) -> None:
        """The host-side envelope is the second fence: when the compute
        group cannot fit the run envelope, admission denies and the run
        blocks — again with no fallback."""
        session: Session = env["session"]
        AdmissionService(session, env["ctx"]).ensure_group(
            "compute",
            capacity={"cpu_cores": 0, "memory_bytes": 0, "storage_bytes": 0, "concurrency": 0},
            reserve={},
        )
        session.flush()
        task = _task(env)
        snap = _snapshot(env, task)
        svc: RlRunService = env["service"]
        run = svc.create(snapshot_id=snap.id, corpus=_corpus(), name="a1", task_id=task.id)
        svc.submit(run.id)
        svc.approve(run.id, decision="approved")
        run = svc.queue(run.id)
        assert run.state == "blocked"
        assert run.error["code"] == "insufficient_local_resources"


# ------------------------------------------------------------ resume


class TestResume:
    def test_cancelled_run_resumes_with_provenance(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_trainer(monkeypatch, _fake_result(status="cancelled", steps=4))
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
        assert resume["fromStep"] == 4
        assert resume["sourceRunId"] == str(first_exec_id)
        chain = run.provenance["chain"]
        assert chain[-1]["event"] == "resume"
        assert chain[-1]["fromStep"] == 4

    def test_resumed_execution_reports_resume_spec(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_trainer(monkeypatch, _fake_result(status="cancelled", steps=4))
        task = _task(env)
        run = _queued_run(env, task)
        att = _attempt_id(env["session"], run.run_id)
        run = env["service"].execute(run.id, att)
        first_exec_id = run.run_id

        captured: dict[str, Any] = {}
        from workers.training.rl.trainer import runtime as rl_runtime

        class _ResumeStub:
            def available(self) -> bool:
                return True

            def train(
                self,
                spec: Any,
                *,
                corpus: bytes,
                resume_files: Any = None,
                cancel: Any = None,
            ) -> Any:
                captured["resume"] = spec.resume
                captured["resume_files"] = resume_files
                return _fake_result(status="succeeded", steps=8)

        monkeypatch.setattr(rl_runtime, "IsolatedRl", _ResumeStub)
        run = env["service"].resume(run.id)
        assert run.state == "queued"
        assert run.run_id != first_exec_id
        att2 = _attempt_id(env["session"], run.run_id)
        run = env["service"].execute(run.id, att2)
        assert run.state == "completed"
        assert captured["resume"] is not None
        assert captured["resume"].from_step == 4
        assert captured["resume"].source_run_id == str(first_exec_id)
        # checkpoint bytes were re-loaded from the vault for the resume
        assert captured["resume_files"] is not None
        assert "adapter_model.safetensors" in captured["resume_files"]
