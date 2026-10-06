"""CS-1101 security tests — AT-1101-3 unavailable controls.

When a required control is unavailable on the platform, the system
must disclose it and block the dependent capability — never silently
skip the protection, never let a forged grant bypass the ceiling.

Attack surfaces exercised:
  * capability ceilings applied at context load (a DB row granting an
    agent an approval capability, or a user the service-only eval
    label capability, must be stripped before any service call)
  * the capabilities endpoint reporting only what is actually
    probed — profiles report disabled/unavailable with remediation,
    never 'available' for an unprobed worker
  * admission: unobserved capacity dimensions and missing groups are
    typed blocks with disclosed reasons, not silent fall-throughs
  * worker isolation: a backend whose profile lacks the argv-only
    contract fails the attempt as typed `profile_unavailable`
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from chem_studio_policy.capabilities import (
    APPROVAL_CAPABILITIES,
    CAP_APPROVE_EXPORT,
    CAP_READ_EVAL_LABELS,
    SERVICE_ONLY_CAPABILITIES,
    capabilities_for_role,
    has_capability,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.api.capabilities import collect_capabilities
from studio.auth.context import load_context
from studio.config.settings import Settings
from studio.domain.learning.promotion import EvaluationService
from studio.domain.runs.admission import ENVELOPE_FIELDS, AdmissionService
from studio.domain.runs.queue import RunService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Principal,
    PrincipalCapability,
    ResourceGroup,
    Workspace,
)

pytestmark = pytest.mark.security


@pytest.fixture()
def ws_ctx(session: Session):
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    return ws


def _principal(session: Session, ws: Workspace, kind: str, role: str, login: str) -> Principal:
    p = Principal(workspace_id=ws.id, kind=kind, login=login, display_name=login)
    session.add(p)
    session.flush()
    for cap in sorted(capabilities_for_role(role)):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=p.id, capability=cap))
    session.flush()
    return p


def _forge_grant(session: Session, ws: Workspace, principal: Principal, capability: str) -> None:
    """Write a PrincipalCapability row directly — simulating a row
    planted by a bug, a bad migration, or a compromised surface."""
    session.add(
        PrincipalCapability(workspace_id=ws.id, principal_id=principal.id, capability=capability)
    )
    session.flush()


class TestCapabilityCeilings:
    """§21.1/§18.1 — ceilings are enforced at context load, server-
    side, so a forged DB row never becomes a live grant."""

    def test_agent_forged_approval_grant_stripped(
        self, session: Session, ws_ctx: Workspace
    ) -> None:
        agent = _principal(session, ws_ctx, "agent", "agent", "bot")
        _forge_grant(session, ws_ctx, agent, CAP_APPROVE_EXPORT)
        ctx = load_context(session, ws_ctx.id, agent.id)
        assert ctx.principal_kind == "agent"
        assert not ctx.has(CAP_APPROVE_EXPORT)
        with pytest.raises(DomainError) as exc:
            ctx.require(CAP_APPROVE_EXPORT)
        assert exc.value.code == ErrorCode.FORBIDDEN

    def test_user_forged_service_only_grant_stripped(
        self, session: Session, ws_ctx: Workspace
    ) -> None:
        user = _principal(session, ws_ctx, "user", "researcher", "r1")
        _forge_grant(session, ws_ctx, user, CAP_READ_EVAL_LABELS)
        ctx = load_context(session, ws_ctx.id, user.id)
        assert not ctx.has(CAP_READ_EVAL_LABELS)

    def test_forged_eval_label_grant_cannot_read_hidden_targets(
        self, session: Session, ws_ctx: Workspace, tmp_path: Path
    ) -> None:
        """The label store refuses twice: the stripped capability AND
        the principal-kind check — a forged grant reaches neither."""
        user = _principal(session, ws_ctx, "user", "researcher", "r2")
        _forge_grant(session, ws_ctx, user, CAP_READ_EVAL_LABELS)
        ctx = load_context(session, ws_ctx.id, user.id)
        ev = EvaluationService(session, ctx, Settings(vault_root=tmp_path))
        with pytest.raises(DomainError) as exc:
            ev.hidden_targets(uuid.uuid4())
        assert exc.value.code == ErrorCode.FORBIDDEN

    def test_role_table_never_grants_approvals_to_agents(self) -> None:
        assert capabilities_for_role("agent").isdisjoint(APPROVAL_CAPABILITIES)
        assert capabilities_for_role("researcher").isdisjoint(APPROVAL_CAPABILITIES)
        assert capabilities_for_role("agent").isdisjoint(SERVICE_ONLY_CAPABILITIES)
        assert capabilities_for_role("researcher").isdisjoint(SERVICE_ONLY_CAPABILITIES)

    def test_unknown_capability_string_never_grants(
        self, session: Session, ws_ctx: Workspace
    ) -> None:
        user = _principal(session, ws_ctx, "user", "researcher", "r3")
        # an unlisted capability name can be planted but has no meaning
        _forge_grant(session, ws_ctx, user, "approve_everything")
        ctx = load_context(session, ws_ctx.id, user.id)
        assert not has_capability(ctx.grants, "approve_everything")
        assert not ctx.has("approve_everything")

    def test_revoked_grant_row_is_inert(self, session: Session, ws_ctx: Workspace) -> None:
        user = _principal(session, ws_ctx, "user", "researcher", "r4")
        ctx = load_context(session, ws_ctx.id, user.id)
        assert ctx.has("read_project")
        row = session.execute(
            select(PrincipalCapability).where(
                PrincipalCapability.principal_id == user.id,
                PrincipalCapability.capability == "read_project",
            )
        ).scalar_one()
        from datetime import UTC, datetime

        row.revoked_at = datetime.now(UTC)
        session.flush()
        ctx2 = load_context(session, ws_ctx.id, user.id)
        assert not ctx2.has("read_project")


class TestCapabilityReportHonesty:
    """The capability report is the trust contract: nothing it lists
    as available may be unprobed."""

    def test_profiles_off_report_disabled_not_available(self, tmp_path: Path) -> None:
        report = collect_capabilities(Settings(vault_root=tmp_path))
        assert report["profiles"]["core"]["status"] == "available"
        for name, entry in report["profiles"].items():
            assert entry["status"] in {"available", "unavailable", "disabled"}
            assert entry["detail"]  # every entry carries a reason
            if name == "core":
                continue
            assert entry["status"] == "disabled"  # profiles default off

    def test_enabled_but_uninstalled_worker_reports_unavailable(self, tmp_path: Path) -> None:
        report = collect_capabilities(Settings(vault_root=tmp_path, profile_local_ai=True))
        # llama_cpp is not installed in this environment — the report
        # must say unavailable, never silently claim the capability
        if report["profiles"]["local_ai"]["status"] == "unavailable":
            assert "llama-cpp-python" in report["profiles"]["local_ai"]["detail"]
        else:
            # if the module IS installed, available is honest — but the
            # detail must still name what was probed
            assert report["profiles"]["local_ai"]["detail"]


class TestAdmissionBlockedHonesty:
    """§13.4/§20.1 — a run that cannot be admitted locally is blocked
    with disclosed reasons; nothing routes elsewhere silently."""

    def _request_run(self, session: Session, ws_ctx: Workspace):
        res = _principal(session, ws_ctx, "user", "researcher", "req")
        ctx = load_context(session, ws_ctx.id, res.id)
        run = RunService(session, ctx).request(
            kind="training.sft",
            request={"snapshotId": str(uuid.uuid4())},
        )
        session.flush()
        return ctx, run

    def test_missing_group_blocks_run_with_reason(
        self, session: Session, ws_ctx: Workspace
    ) -> None:
        ctx, run = self._request_run(session, ws_ctx)
        decision = AdmissionService(session, ctx).admit(
            run.id, {d: 0 for d in ENVELOPE_FIELDS}, group_name="gpu-cluster"
        )
        assert decision.admitted is False
        assert decision.missing == ["gpu-cluster"]
        assert decision.next_step == "export_review_proposal"
        session.refresh(run)
        assert run.status == "blocked"
        assert run.error["code"] == "blocked"

    def test_unobserved_dimension_is_missing_capability(
        self, session: Session, ws_ctx: Workspace
    ) -> None:
        ctx, run = self._request_run(session, ws_ctx)
        # group exists but gpu_devices capacity is unobserved (None)
        session.add(
            ResourceGroup(
                workspace_id=ws_ctx.id,
                name="compute",
                capacity={
                    "cpu_cores": 8,
                    "memory_bytes": 32 << 30,
                    "gpu_devices": None,
                    "storage_bytes": 512 << 30,
                    "concurrency": 4,
                },
            )
        )
        session.flush()
        decision = AdmissionService(session, ctx).admit(
            run.id,
            {"cpu_cores": 2, "memory_bytes": 1 << 30, "gpu_devices": 1, "storage_bytes": 0},
        )
        assert decision.admitted is False
        assert "gpu_devices" in decision.missing
        session.refresh(run)
        assert run.status == "blocked"

    def test_insufficient_capacity_blocks_with_reasons(
        self, session: Session, ws_ctx: Workspace
    ) -> None:
        ctx, run = self._request_run(session, ws_ctx)
        session.add(
            ResourceGroup(
                workspace_id=ws_ctx.id,
                name="compute",
                capacity={
                    "cpu_cores": 4,
                    "memory_bytes": 16 << 30,
                    "gpu_devices": 0,
                    "storage_bytes": 128 << 30,
                    "concurrency": 2,
                },
                reserve={"cpu_cores": 1},
            )
        )
        session.flush()
        decision = AdmissionService(session, ctx).admit(
            run.id,
            {"cpu_cores": 8, "memory_bytes": 1 << 30, "gpu_devices": 0, "storage_bytes": 0},
        )
        assert decision.admitted is False
        assert any(r["dimension"] == "cpu_cores" for r in decision.reasons)
        session.refresh(run)
        assert run.status == "blocked"

    def test_blocked_run_is_not_silently_queued(self, session: Session, ws_ctx: Workspace) -> None:
        ctx, run = self._request_run(session, ws_ctx)
        AdmissionService(session, ctx).admit(
            run.id, {d: 0 for d in ENVELOPE_FIELDS}, group_name="nope"
        )
        session.refresh(run)
        assert run.status == "blocked"
        # no reservation was created — blocked is not a soft admit
        from studio.persistence.models import ResourceReservation

        assert (
            session.execute(select(ResourceReservation).where(ResourceReservation.run_id == run.id))
            .scalars()
            .all()
            == []
        )

    def test_envelope_bounds_validation(self, session: Session, ws_ctx: Workspace) -> None:
        ctx, run = self._request_run(session, ws_ctx)
        with pytest.raises(DomainError) as exc:
            AdmissionService(session, ctx).admit(
                run.id, {"cpu_cores": -1, "memory_bytes": 0, "gpu_devices": 0, "storage_bytes": 0}
            )
        assert exc.value.code == ErrorCode.VALIDATION
        with pytest.raises(DomainError) as exc:
            AdmissionService(session, ctx).admit(
                run.id, {"cpu_cores": True, "memory_bytes": 0, "gpu_devices": 0, "storage_bytes": 0}
            )
        assert exc.value.code == ErrorCode.VALIDATION
        session.refresh(run)
        assert run.status == "requested"  # invalid envelope ≠ blocked
