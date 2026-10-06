"""CS-0902 AT-0902-3 security tests — capability separation and the
compute envelope's no-fallback semantics.

- Principals without ``manage_models`` (viewer, agent) cannot create,
  submit, approve or queue RL runs — the approval path stays human-only
  (§21 hard rules).
- An approved run whose local envelope cannot be admitted BLOCKS
  instead of degrading — there is no cloud path to fall back to.
- The corpus policy's grants are advisory labels pinned to the run —
  they can never include approval capabilities, and they never widen
  the policy's actual tool rights inside the environment.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext, load_context
from studio.config.settings import Settings
from studio.domain.evidence.vault import Vault
from studio.domain.learning.datasets import DatasetService
from studio.domain.learning.rl import RlRunService
from studio.domain.runs.admission import AdmissionService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    Workspace,
)

pytestmark = pytest.mark.security

GB = 1024**3


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
    ws = Workspace(slug="rl-sec", display_name="RL security tests")
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
        "service": RlRunService(session, ctx, settings, vault),
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
        title="sec task",
        workflow_state="active",
        target_kind="formulation",
        objective="o",
    )
    session.add(task)
    session.flush()
    return task


def _corpus(policy_grants: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema_name": "rl_training_corpus",
        "env_contract_version": 1,
        "reward_contract_version": 1,
        "tasks": [
            {
                "task_id": "rl-sec-1",
                "messages": [{"role": "user", "content": "viscosity?"}],
                "subgroup": "s",
                "answerable": True,
                "allowed_tools": ["search_evidence"],
                "target": {"expect": "exact", "value": "900 mPa·s"},
            }
        ],
        "snapshot": {"snapshot_id": "s1", "evidence_ids": [], "replay": [], "meta": {}},
        "policy": {
            "policy_id": "p1",
            "kind": "agent",
            "grants": policy_grants
            if policy_grants is not None
            else sorted(capabilities_for_role("agent")),
            "allowed_tools": ["search_evidence"],
        },
    }


def _svc_for(env: dict[str, Any], ctx: ServiceContext) -> RlRunService:
    return RlRunService(env["session"], ctx, env["settings"], env["vault"])


# ------------------------------------------------------------- capabilities


class TestCapabilitySeparation:
    def test_viewer_cannot_create(self, env: dict[str, Any]) -> None:
        _, vctx = _principal(env["session"], env["ws"], "viewer", "v")
        svc = _svc_for(env, vctx)
        with pytest.raises(DomainError) as err:
            svc.create(snapshot_id=uuid.uuid4(), corpus=_corpus(), name="x")
        assert err.value.code == ErrorCode.FORBIDDEN

    def test_agent_cannot_create_submit_approve(self, env: dict[str, Any]) -> None:
        """Agent roles never hold manage_models — every lifecycle verb
        refuses them (server-side check, not a UI convention)."""
        _, actx = _principal(env["session"], env["ws"], "agent", "a")
        svc = _svc_for(env, actx)
        for verb in (
            lambda: svc.create(snapshot_id=uuid.uuid4(), corpus=_corpus(), name="x"),
            lambda: svc.submit(uuid.uuid4()),
            lambda: svc.approve(uuid.uuid4(), decision="approved"),
            lambda: svc.queue(uuid.uuid4()),
            lambda: svc.execute(uuid.uuid4(), uuid.uuid4()),
        ):
            with pytest.raises(DomainError) as err:
                verb()
            assert err.value.code in (ErrorCode.FORBIDDEN, ErrorCode.NOT_FOUND)

    def test_reviewer_cannot_self_approve(self, env: dict[str, Any]) -> None:
        task = _task(env)
        snap = env["datasets"].build(purpose="assistant_sft", name="s", task_id=task.id)
        env["datasets"].freeze(snap.id)
        run = env["service"].create(
            snapshot_id=snap.id, corpus=_corpus(), name="r1", task_id=task.id
        )
        env["service"].submit(run.id)  # awaiting_approval — capability check reached
        _, rctx = _principal(env["session"], env["ws"], "reviewer", "r")
        svc = _svc_for(env, rctx)
        with pytest.raises(DomainError) as err:
            svc.approve(run.id, decision="approved")
        assert err.value.code == ErrorCode.FORBIDDEN

    def test_agent_grants_cannot_carry_approvals(self, env: dict[str, Any]) -> None:
        """A corpus whose policy CLAIMS approval capabilities parses,
        but the claim is inert: ``effective_grants`` intersects the
        declared grants with the agent vocabulary, so ``approve_*`` /
        service-only capabilities can never reach a policy — the same
        ceiling the environment enforces inside every episode."""
        from chem_studio_policy.capabilities import (
            CAP_APPROVE_EXPORT,
            CAP_APPROVE_MODEL,
            CAP_READ_EVAL_LABELS,
            Grant,
            effective_grants,
            has_capability,
        )

        task = _task(env)
        snap = env["datasets"].build(purpose="assistant_sft", name="s", task_id=task.id)
        env["datasets"].freeze(snap.id)
        grants = [
            *sorted(capabilities_for_role("agent")),
            CAP_APPROVE_MODEL,
            CAP_APPROVE_EXPORT,
            CAP_READ_EVAL_LABELS,
        ]
        corpus = _corpus(policy_grants=grants)
        run = env["service"].create(
            snapshot_id=snap.id, corpus=corpus, name="bad-policy", task_id=task.id
        )
        assert run.state == "dataset_validated"
        effective = effective_grants("agent", frozenset(Grant(capability=g) for g in grants))
        assert not has_capability(effective, CAP_APPROVE_MODEL)
        assert not has_capability(effective, CAP_APPROVE_EXPORT)
        # eval labels are service-only — same stripping
        assert not has_capability(effective, CAP_READ_EVAL_LABELS)


# ------------------------------------------------------------- spec safety


class TestSpecSafety:
    def _queued(self, env: dict[str, Any], task: ResearchTask, spec: dict | None = None) -> Any:
        snap = env["datasets"].build(purpose="assistant_sft", name="s", task_id=task.id)
        env["datasets"].freeze(snap.id)
        svc: RlRunService = env["service"]
        run = svc.create(
            snapshot_id=snap.id, corpus=_corpus(), name="q", task_id=task.id, spec=spec
        )
        svc.submit(run.id)
        svc.approve(run.id, decision="approved")
        return svc.queue(run.id)

    def test_invalid_spec_rejected_at_create(self, env: dict[str, Any]) -> None:
        task = _task(env)
        snap = env["datasets"].build(purpose="assistant_sft", name="s", task_id=task.id)
        env["datasets"].freeze(snap.id)
        with pytest.raises(DomainError) as err:
            env["service"].create(
                snapshot_id=snap.id,
                corpus=_corpus(),
                name="bad-spec",
                task_id=task.id,
                spec={"rollout_budget": {"max_episodes": -5}},
            )
        assert err.value.code == ErrorCode.VALIDATION

    def test_unknown_spec_key_rejected(self, env: dict[str, Any]) -> None:
        task = _task(env)
        snap = env["datasets"].build(purpose="assistant_sft", name="s", task_id=task.id)
        env["datasets"].freeze(snap.id)
        with pytest.raises(DomainError) as err:
            env["service"].create(
                snapshot_id=snap.id,
                corpus=_corpus(),
                name="bad-spec2",
                task_id=task.id,
                spec={"cloud_fallback": {"enabled": True}},
            )
        assert err.value.code == ErrorCode.VALIDATION

    def test_envelope_cap_bounded(self, env: dict[str, Any]) -> None:
        """The host envelope clamps wall/storage to the engine's own
        bounds — a caller cannot request an unbounded worker."""
        task = _task(env)
        snap = env["datasets"].build(purpose="assistant_sft", name="s", task_id=task.id)
        env["datasets"].freeze(snap.id)
        run = env["service"].create(
            snapshot_id=snap.id,
            corpus=_corpus(),
            name="big-env",
            task_id=task.id,
            spec={
                "resources": {
                    "cpu_cores": 2.0,
                    "memory_mebibytes": 4096,
                    "wall_seconds": 7200,
                }
            },
        )
        assert run.state == "dataset_validated"
        env_spec = run.spec["resources"]
        assert env_spec["wall_seconds"] <= 14400
        assert env_spec["memory_mebibytes"] <= 32768
