"""CS-0803 security tests — hidden evaluation labels (AT-0803-2).

Only the evaluation *service* principal may read hidden targets.
The denial is enforced at the capability/tool layer in three
independent ways, all tested:

1. ``read_eval_labels`` is a service-only capability — ``effective_grants``
   strips it from user AND agent principals even when a grant row exists.
2. ``EvaluationService.hidden_targets`` additionally refuses any
   non-service principal kind (an owner ctx is denied too).
3. The closed agent tool catalog has no verb that reaches the label
   store — an agent asking for labels gets UNKNOWN_TOOL.
"""

from __future__ import annotations

import pytest
from chem_studio_policy.capabilities import (
    CAP_READ_EVAL_LABELS,
    Grant,
    capabilities_for_role,
    effective_grants,
)
from sqlalchemy.orm import Session

from studio.application.agent_tools import ToolDispatcher, default_registry
from studio.auth.context import load_context
from studio.config.settings import Settings
from studio.domain.learning.promotion import EvaluationService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    EvaluationLabel,
    Principal,
    PrincipalCapability,
    Workspace,
)

pytestmark = pytest.mark.security


def _principal(session: Session, ws: Workspace, kind: str, login: str, caps: list[str]):
    p = Principal(workspace_id=ws.id, kind=kind, login=login, display_name=login)
    session.add(p)
    session.flush()
    for cap in caps:
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=p.id, capability=cap))
    session.flush()
    return p, load_context(session, ws.id, p.id)


def _suite_with_label(session: Session, ws: Workspace):
    """A frozen suite + one hidden label row, written directly (the
    label write path is manage_models-gated, covered elsewhere)."""
    from studio.persistence.models import EvaluationSuite

    suite = EvaluationSuite(
        workspace_id=ws.id,
        task_id=None,
        name="s",
        version=1,
        purpose="assistant_sft",
        kind="final",
        state="frozen",
        definition={"tasks": [], "name": "s", "version": 1, "kind": "final"},
        digest="d" * 64,
        capability={},
        provenance={},
        created_by=None,
    )
    session.add(suite)
    session.flush()
    session.add(
        EvaluationLabel(
            workspace_id=ws.id,
            suite_id=suite.id,
            example_id="ex1",
            target={"expect": "exact", "value": "secret-answer"},
        )
    )
    session.flush()
    return suite


@pytest.fixture()
def setup(session: Session):
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    suite = _suite_with_label(session, ws)
    settings = Settings(profile_training=True)
    return ws, suite, settings


def test_read_eval_labels_is_service_only() -> None:
    """The capability ceiling strips read_eval_labels from every
    non-service kind — even with an explicit grant row."""
    grant = Grant(CAP_READ_EVAL_LABELS, None)
    assert effective_grants("agent", frozenset({grant})) == frozenset()
    assert effective_grants("user", frozenset({grant})) == frozenset()
    assert effective_grants("service", frozenset({grant})) == frozenset({grant})


def test_agent_tool_catalog_has_no_label_verb() -> None:
    names = default_registry().names()
    assert not any("label" in n or "eval" in n or "target" in n for n in names)


def test_agent_denied_at_capability_layer(session: Session, setup) -> None:
    """AT-0803-2: an agent principal (even one holding a stray grant
    row) is denied — effective_grants strips the capability AND the
    principal-kind check refuses it."""
    ws, suite, settings = setup
    _, ctx = _principal(session, ws, "agent", "bot", [CAP_READ_EVAL_LABELS])
    svc = EvaluationService(session, ctx, settings)
    with pytest.raises(DomainError) as err:
        svc.hidden_targets(suite.id)
    assert err.value.code == ErrorCode.FORBIDDEN


def test_user_denied_even_with_full_role(session: Session, setup) -> None:
    """Even an owner ctx — which legitimately holds every role
    capability — cannot read labels: kind must be 'service'."""
    ws, suite, settings = setup
    _, ctx = _principal(session, ws, "user", "owner", sorted(capabilities_for_role("owner")))
    svc = EvaluationService(session, ctx, settings)
    with pytest.raises(DomainError) as err:
        svc.hidden_targets(suite.id)
    assert err.value.code == ErrorCode.FORBIDDEN


def test_viewer_denied(session: Session, setup) -> None:
    ws, suite, settings = setup
    _, ctx = _principal(session, ws, "user", "viewer", sorted(capabilities_for_role("viewer")))
    svc = EvaluationService(session, ctx, settings)
    with pytest.raises(DomainError) as err:
        svc.hidden_targets(suite.id)
    assert err.value.code == ErrorCode.FORBIDDEN


def test_agent_dispatcher_cannot_reach_labels(session: Session, setup) -> None:
    """The closed catalog refuses any label verb an agent might guess —
    the denial lands as UNKNOWN_TOOL, before any service runs."""
    ws, suite, _ = setup
    _, ctx = _principal(session, ws, "agent", "bot", [])
    dispatcher = ToolDispatcher(session, ctx)
    for verb in ("read_eval_labels", "hidden_targets", "evaluation_labels_read"):
        res = dispatcher.call(verb, {"suite_id": str(suite.id)})
        assert res["ok"] is False
        assert res["error"]["code"] == "UNKNOWN_TOOL"


def test_evaluation_service_principal_reads_labels(session: Session, setup) -> None:
    """The intended path: the service principal the service itself
    materializes holds the grant and passes both checks."""
    ws, suite, settings = setup
    _, owner_ctx = _principal(session, ws, "user", "owner", sorted(capabilities_for_role("owner")))
    svc = EvaluationService(session, owner_ctx, settings)
    eval_ctx = svc._evaluation_context()
    assert eval_ctx.principal_kind == "service"
    eval_svc = EvaluationService(session, eval_ctx, settings)
    targets = eval_svc.hidden_targets(suite.id)
    assert targets["ex1"].value == "secret-answer"


def test_labels_only_reach_service_path_not_definition(session: Session, setup) -> None:
    """The public suite definition must never carry label payloads."""
    _, suite, _settings = setup
    import json

    assert "secret-answer" not in json.dumps(suite.definition)
