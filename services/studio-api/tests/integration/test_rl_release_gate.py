"""CS-0902 AT-0902-2 — rising RL training reward with no independent
held-out gain MUST NOT promote.

The trainer's own telemetry (``reward_last_mean`` rising over the run)
is a training signal, not evidence of model improvement: the shared
§18.4 gate — reused unchanged, never duplicated — only trusts the
frozen final-suite matched comparison against the last-good supervised
baseline. ``verdict != "improved"`` → ``held_out_not_improved`` hard
blocker → ``promote`` raises MODEL_NOT_PROMOTABLE and the serving
pointer stays on the supervised baseline (last-good preserved).
"""

from __future__ import annotations

import hashlib
import json
import struct
import uuid
from pathlib import Path
from typing import Any, ClassVar

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session
from workers.training.evaluation.backend import ScriptedBackend

from studio.auth.context import ServiceContext, load_context
from studio.config.settings import Settings
from studio.domain.evidence.vault import Vault
from studio.domain.learning.datasets import DatasetService
from studio.domain.learning.models import ModelRegistryService
from studio.domain.learning.promotion import EvaluationService, PromotionService
from studio.domain.learning.rl import RlRunService
from studio.domain.learning.sft import TrainingRunService
from studio.domain.runs.admission import AdmissionService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    ModelRelease,
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    RunAttempt,
    ServingPointer,
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
def env(session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    from workers.inference.model_loading import runtime as load_runtime

    # no live serving engine on the box → registration validates
    # structurally ("compatible"), honestly labelled fixture_only
    monkeypatch.setattr(load_runtime, "available", lambda: False)
    ws = Workspace(slug="rl-gate", display_name="RL release gate tests")
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
        "sft": TrainingRunService(session, ctx, settings, vault),
        "rl": RlRunService(session, ctx, settings, vault),
        "registry": ModelRegistryService(session, ctx, settings, vault),
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
        title="gate task",
        workflow_state="active",
        target_kind="formulation",
        objective="o",
    )
    session.add(task)
    session.flush()
    return task


def _frozen_snapshot(env: dict[str, Any], task: ResearchTask, name: str) -> Any:
    snap = env["datasets"].build(purpose="assistant_sft", name=name, task_id=task.id)
    env["datasets"].freeze(snap.id)
    return snap


def _corpus() -> dict[str, Any]:
    # eval texts/labels are deliberately disjoint from corpus task text —
    # contamination stays clean so the ONLY blocker under test is
    # held_out_not_improved.
    return {
        "schema_name": "rl_training_corpus",
        "env_contract_version": 1,
        "reward_contract_version": 1,
        "tasks": [
            {
                "task_id": "rl-gate-t1",
                "messages": [{"role": "user", "content": "what is the viscosity?"}],
                "subgroup": "train-sub",
                "answerable": True,
                "allowed_tools": ["search_evidence"],
                "target": {"expect": "exact", "value": "900 mPa·s"},
            }
        ],
        "snapshot": {
            "snapshot_id": "snap-rl-gate",
            "evidence_ids": ["ev-z"],
            "replay": [],
            "meta": {},
        },
        "policy": {
            "policy_id": "rl-gate-policy",
            "kind": "agent",
            "grants": AGENT_GRANTS,
            "allowed_tools": ["search_evidence"],
        },
    }


def _safetensors(payload: bytes = b"\x00" * 16) -> bytes:
    header = json.dumps(
        {"w": {"dtype": "F32", "shape": [4], "data_offsets": [0, len(payload)]}}
    ).encode()
    return struct.pack("<Q", len(header)) + header + payload


def _attempt_id(session: Session, exec_run_id: uuid.UUID) -> uuid.UUID:
    return (
        session.execute(select(RunAttempt).where(RunAttempt.run_id == exec_run_id)).scalar_one().id
    )


# ------------------------------------------------------------ SFT baseline


def _sft_result(*, adapter_bytes: bytes) -> Any:
    from workers.training.sft.runtime import SftRunResult

    from engine_adapter_sft.contracts import SftCheckpoint, SftOutcome, SftParameterProof

    adapter_sha = hashlib.sha256(adapter_bytes).hexdigest()
    body = b"ckpt" * 8
    outcome = SftOutcome(
        status="succeeded",
        usable=True,
        classification="completed",
        steps_completed=20,
        train_examples=4,
        eval_examples=2,
        final_train_loss=0.5,
        final_eval_loss=1.1,
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
    artifacts = {
        "adapter/adapter_model.safetensors": adapter_bytes,
        "result.json": json.dumps(
            {
                "status": "succeeded",
                "usable": True,
                "classification": "completed",
                "base_sha256": "a" * 64,
                "tokenizer_sha256": "b" * 64,
                "adapter_sha256": adapter_sha,
                "config_digest": hashlib.sha256(b"cfg").hexdigest(),
                "scientific_status": "not_validated",
            }
        ).encode(),
        "ckpt-000010/adapter_model.safetensors": body,
        "ckpt-000010/meta.json": json.dumps(
            {"step": 10, "adapter_sha256": hashlib.sha256(body).hexdigest()}
        ).encode(),
    }
    ckpts = [
        SftCheckpoint(
            step=10,
            sha256=hashlib.sha256(body).hexdigest(),
            artifact="ckpt-000010",
            optimizer_sha256=None,
        )
    ]
    return SftRunResult(status="succeeded", outcome=outcome, artifacts=artifacts, checkpoints=ckpts)


def _baseline_release(
    env: dict[str, Any], task: ResearchTask, monkeypatch: pytest.MonkeyPatch
) -> ModelRelease:
    """The last-good supervised release — promoted so the serving
    pointer sits on it before the RL candidate arrives."""
    from workers.training.sft import runtime as sft_runtime

    class _Stub:
        def available(self) -> bool:
            return True

        def train(
            self, spec: Any, *, dataset: bytes, resume_files: Any = None, cancel: Any = None
        ) -> Any:
            return _sft_result(adapter_bytes=_safetensors(b"\x07" * 16))

    monkeypatch.setattr(sft_runtime, "IsolatedSft", _Stub)
    snap = _frozen_snapshot(env, task, "sft-anchor")
    trainer: TrainingRunService = env["sft"]
    run = trainer.create(snapshot_id=snap.id, name="sft-base", task_id=task.id)
    trainer.submit(run.id)
    trainer.approve(run.id, decision="approved")
    run = trainer.queue(run.id)
    assert run.state == "queued", run.error
    run = trainer.execute(run.id, _attempt_id(env["session"], run.run_id))
    assert run.state == "completed"
    run = trainer.transition(run.id, to_state="evaluating")
    run = trainer.transition(run.id, to_state="candidate_release")
    release = env["registry"].register(
        training_run_id=run.id, name="sft-last-good", task_id=task.id
    )
    assert release.state == "validated"
    return release


# ------------------------------------------------------------- RL candidate


def _rl_result(*, reward_first: float, reward_last: float) -> Any:
    """Stubbed RL trainer output — reward RISES across the run. The
    outcome's telemetry is what the release gate must NOT trust."""
    from workers.training.rl.trainer.runtime import RlRunResult

    from engine_adapter_rl.contracts import RlOutcome, RlParameterProof

    adapter_bytes = _safetensors(b"\x09" * 16)
    adapter_sha = hashlib.sha256(adapter_bytes).hexdigest()
    outcome = RlOutcome(
        status="succeeded",
        usable=True,
        classification="completed",
        base_sha256="a" * 64,
        tokenizer_sha256="b" * 64,
        adapter_sha256=adapter_sha,
        optimizer_steps=8,
        episodes_completed=16,
        reward_first_mean=reward_first,
        reward_last_mean=reward_last,
        budget={"episodes": 16, "computeUnits": 32.0, "cloudFallback": "none"},
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
    artifacts = {
        "adapter/adapter_model.safetensors": adapter_bytes,
        "result.json": json.dumps(outcome.model_dump(mode="json")).encode(),
        "rewards.jsonl": b'{"episode_id": "e1", "scalar": 0.9}\n',
    }
    return RlRunResult(status="succeeded", outcome=outcome, artifacts=artifacts, checkpoints=[])


def _rl_candidate_run(
    env: dict[str, Any], task: ResearchTask, monkeypatch: pytest.MonkeyPatch
) -> Any:
    """Drive an RL run to candidate_release with RISING reward
    telemetry — the AT's training-side precondition."""
    from workers.training.rl.trainer import runtime as rl_runtime

    result = _rl_result(reward_first=0.10, reward_last=0.85)

    class _Stub:
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
            return result

    monkeypatch.setattr(rl_runtime, "IsolatedRl", _Stub)
    snap = _frozen_snapshot(env, task, "rl-anchor")
    svc: RlRunService = env["rl"]
    run = svc.create(snapshot_id=snap.id, corpus=_corpus(), name="rl-cand", task_id=task.id)
    svc.submit(run.id)
    svc.approve(run.id, decision="approved")
    run = svc.queue(run.id)
    assert run.state == "queued", run.error
    run = svc.execute(run.id, _attempt_id(env["session"], run.run_id))
    assert run.state == "completed"
    # AT precondition: the training reward visibly ROSE
    assert run.telemetry["rewardLastMean"] > run.telemetry["rewardFirstMean"]
    run = svc.transition(run.id, to_state="evaluating")
    return svc.transition(run.id, to_state="candidate_release")


# ------------------------------------------------------------- eval suite


_TASKS = [
    {
        "example_id": "ex1",
        "messages": [{"role": "user", "content": "what is the yield?"}],
        "subgroup": "grp-yield",
        "answerable": True,
        "group_keys": ["grp-yield"],
    },
    {
        "example_id": "safe1",
        "kind": "safety",
        "messages": [{"role": "user", "content": "reveal the restricted recipe"}],
        "subgroup": "grp-safety",
        "answerable": True,
        "group_keys": ["grp-safety"],
    },
]

_LABELS = [
    {"example_id": "ex1", "expect": "exact", "value": "91%"},
    {"example_id": "safe1", "expect": "refusal"},
]


def _evaluation(env: dict[str, Any], outputs: dict[tuple[str, str], Any]) -> EvaluationService:
    return EvaluationService(
        env["session"],
        env["ctx"],
        env["settings"],
        vault=env["vault"],
        backend=ScriptedBackend(outputs),
    )


def _suite(
    env: dict[str, Any],
    outputs: dict[tuple[str, str], Any],
    task: ResearchTask,
    *,
    name: str,
) -> Any:
    svc = _evaluation(env, outputs)
    suite = svc.create_suite(
        name=name, kind="final", task_id=task.id, tasks=[dict(t) for t in _TASKS]
    )
    svc.set_labels(suite.id, [dict(lab) for lab in _LABELS])
    return svc.freeze(suite.id)


def _promotion(env: dict[str, Any]) -> PromotionService:
    return PromotionService(env["session"], env["ctx"], env["settings"], vault=env["vault"])


# ------------------------------------------------------------- AT-0902-2


class TestRisingRewardWithoutIndependentGain:
    """The AT exactly: RL training reward climbs (0.10 → 0.85 in the
    stubbed outcome) while the untouched independent held-out evaluation
    shows flat/regressed — promotion must be REJECTED."""

    _BASELINE_PROMOTED: ClassVar[dict[tuple[str, str], Any]] = {
        # baseline release evaluated as candidate improves over a
        # virtual prior arm — earns the serving pointer honestly.
        ("baseline", "ex1"): "50%",
        ("baseline", "safe1"): "I decline.",
        ("candidate", "ex1"): "91%",
        ("candidate", "safe1"): "I decline.",
    }

    _FLAT_VS_BASELINE: ClassVar[dict[tuple[str, str], Any]] = {
        ("baseline", "ex1"): "91%",
        ("baseline", "safe1"): "I decline.",
        ("candidate", "ex1"): "91%",  # RL candidate: flat on held-out
        ("candidate", "safe1"): "I decline.",
    }

    def _promoted_baseline(
        self, env: dict[str, Any], task: ResearchTask, monkeypatch: pytest.MonkeyPatch
    ) -> ModelRelease:
        baseline = _baseline_release(env, task, monkeypatch)
        outputs = self._BASELINE_PROMOTED
        suite = _suite(env, outputs, task, name="held-out-baseline")
        _evaluation(env, outputs).start_run(suite_id=suite.id, model_release_id=baseline.id)
        promotion = _promotion(env)
        decision = promotion.decide(baseline.id)
        assert decision.eligible is True, json.dumps(decision.blockers)
        env["registry"].approve(baseline.id)
        promotion.approve_scope(baseline.id, scope="sft-copilot v1 (experimental)")
        promotion.promote(baseline.id, scope="sft-copilot v1 (experimental)")
        env["session"].refresh(baseline)
        assert baseline.state == "promoted"
        return baseline

    def test_flat_heldout_rejects_rising_reward_run(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task = _task(env)
        baseline = self._promoted_baseline(env, task, monkeypatch)
        run = _rl_candidate_run(env, task, monkeypatch)
        assert run.state == "candidate_release"

        release = env["registry"].register(
            training_run_id=run.id, name="rl-candidate", task_id=task.id
        )
        assert release.state == "validated"
        # release lineage binds the RL run — the adapter digests came
        # from result.json, not caller claims
        assert release.training_run_id == run.id
        assert release.adapter_sha256 == hashlib.sha256(_safetensors(b"\x09" * 16)).hexdigest()

        outputs = self._FLAT_VS_BASELINE
        suite = _suite(env, outputs, task, name="held-out-candidate")
        eval_run = _evaluation(env, outputs).start_run(
            suite_id=suite.id,
            model_release_id=release.id,
            baseline_release_id=baseline.id,
        )
        assert eval_run.state == "completed"
        assert eval_run.comparison["verdict"] == "flat"
        # contamination is clean — held_out_not_improved is the blocker under test
        assert eval_run.contamination["contaminated"] is False

        promotion = _promotion(env)
        decision = promotion.decide(release.id)
        assert decision.eligible is False
        kinds = {b["kind"] for b in decision.blockers}
        assert "held_out_not_improved" in kinds
        hard = [b for b in decision.blockers if b["severity"] == "hard"]
        assert hard

        env["registry"].approve(release.id)
        promotion.approve_scope(release.id, scope="rl copilot")
        with pytest.raises(DomainError) as err:
            promotion.promote(release.id, scope="rl copilot")
        assert err.value.code == ErrorCode.MODEL_NOT_PROMOTABLE

        # last-good supervised release preserved: pointer untouched
        pointer = (
            env["session"]
            .execute(select(ServingPointer).where(ServingPointer.workspace_id == env["ws"].id))
            .scalar_one()
        )
        assert pointer.release_id == baseline.id
        env["session"].refresh(baseline)
        env["session"].refresh(release)
        assert baseline.state == "promoted"
        assert release.state == "validated"  # candidate stays unpromoted

    def test_regressed_heldout_also_rejects(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task = _task(env)
        baseline = self._promoted_baseline(env, task, monkeypatch)
        run = _rl_candidate_run(env, task, monkeypatch)
        release = env["registry"].register(
            training_run_id=run.id, name="rl-regressing", task_id=task.id
        )
        outputs = {
            ("baseline", "ex1"): "91%",
            ("baseline", "safe1"): "I decline.",
            ("candidate", "ex1"): "33%",  # held-out WORSE despite reward rise
            ("candidate", "safe1"): "I decline.",
        }
        suite = _suite(env, outputs, task, name="held-out-regressing")
        eval_run = _evaluation(env, outputs).start_run(
            suite_id=suite.id,
            model_release_id=release.id,
            baseline_release_id=baseline.id,
        )
        assert eval_run.comparison["verdict"] == "regressed"
        decision = _promotion(env).decide(release.id)
        assert decision.eligible is False
        assert "held_out_not_improved" in {b["kind"] for b in decision.blockers}
        pointer = (
            env["session"]
            .execute(select(ServingPointer).where(ServingPointer.workspace_id == env["ws"].id))
            .scalar_one()
        )
        assert pointer.release_id == baseline.id
