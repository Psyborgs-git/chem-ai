"""Conversation uses scoped, bounded event order, not tied timestamps."""

import uuid

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session

from studio.application.agent_tools.history import recent_conversation
from studio.auth.context import ServiceContext, load_context
from studio.domain.tasks.memory import TaskMemoryService
from studio.errors import DomainError
from studio.persistence.models import (
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    Workspace,
)


@pytest.fixture
def agent_ctx(session: Session) -> ServiceContext:
    workspace = Workspace(slug="history-fixture", display_name="History fixture")
    session.add(workspace)
    session.flush()
    principal = Principal(
        workspace_id=workspace.id, kind="agent", login="agent", display_name="agent"
    )
    session.add(principal)
    session.flush()
    for capability in capabilities_for_role("agent"):
        session.add(
            PrincipalCapability(
                workspace_id=workspace.id, principal_id=principal.id, capability=capability
            )
        )
    session.flush()
    return load_context(session, workspace.id, principal.id)


@pytest.fixture
def task(session: Session, agent_ctx: ServiceContext) -> ResearchTask:
    project = Project(workspace_id=agent_ctx.workspace_id, slug="history", name="History")
    session.add(project)
    session.flush()
    result = ResearchTask(
        workspace_id=agent_ctx.workspace_id,
        project_id=project.id,
        mode="discover",
        title="History test",
        workflow_state="active",
    )
    session.add(result)
    session.flush()
    return result


pytestmark = pytest.mark.integration


def test_event_order_excludes_tools_cancel_and_current(
    session: Session, agent_ctx: ServiceContext, task: ResearchTask
) -> None:
    mem = TaskMemoryService(session, agent_ctx)
    research = mem.start_session(task.id)
    for role, kind, content, refs in [
        ("user", "message", "first question", {}),
        ("assistant", "tool_call", "internal call", {}),
        ("tool", "tool_result", "untrusted result", {}),
        ("assistant", "message", "local secret source quotation", {}),
        ("assistant", "message", "legacy provider quotation", {"provider_id": str(uuid.uuid4())}),
        (
            "assistant",
            "message",
            "first answer",
            {"provider_id": str(uuid.uuid4()), "provider_egress_policy": "source-export-v1"},
        ),
        ("user", "message", "cancel requested", {"turn_cancel": "turn-1"}),
        ("assistant", "message", "turn cancelled by operator", {"cancelled": True}),
        ("assistant", "message", "request failed", {"error": True}),
        ("user", "message", "second question", {}),
    ]:
        current = mem.post_message(research.id, role=role, kind=kind, content=content, refs=refs)
    result = recent_conversation(session, agent_ctx, research.id, exclude_message_id=current.id)
    assert result == [{"role": "user", "content": "first question"}]


def test_bounds_prioritize_recent_content_and_label_truncation(
    session: Session, agent_ctx: ServiceContext, task: ResearchTask
) -> None:
    mem = TaskMemoryService(session, agent_ctx)
    research = mem.start_session(task.id)
    mem.post_message(research.id, role="user", content="old")
    mem.post_message(
        research.id,
        role="user",
        content="x" * 100,
        refs={"provider_id": str(uuid.uuid4()), "provider_egress_policy": "source-export-v1"},
    )
    current = mem.post_message(research.id, role="user", content="new")
    result = recent_conversation(
        session, agent_ctx, research.id, exclude_message_id=current.id, max_messages=2, max_chars=32
    )
    assert len(result) == 1
    assert result[0]["content"].endswith("[truncated]")
    assert sum(len(message["content"]) for message in result) <= 32


def test_unknown_session_is_not_disclosed(session: Session, agent_ctx: ServiceContext) -> None:
    with pytest.raises(DomainError):
        recent_conversation(session, agent_ctx, uuid.uuid4(), exclude_message_id=uuid.uuid4())


def test_other_workspace_cannot_read_session_history(
    session: Session, agent_ctx: ServiceContext, task: ResearchTask
) -> None:
    memory = TaskMemoryService(session, agent_ctx)
    research = memory.start_session(task.id)
    current = memory.post_message(research.id, role="user", content="private question")
    other = Workspace(slug="other-history", display_name="Other workspace")
    session.add(other)
    session.flush()
    principal = Principal(
        workspace_id=other.id, kind="agent", login="other-agent", display_name="other"
    )
    session.add(principal)
    session.flush()
    for capability in capabilities_for_role("agent"):
        session.add(
            PrincipalCapability(
                workspace_id=other.id, principal_id=principal.id, capability=capability
            )
        )
    session.flush()
    other_ctx = load_context(session, other.id, principal.id)
    with pytest.raises(DomainError) as failure:
        recent_conversation(session, other_ctx, research.id, exclude_message_id=current.id)
    assert failure.value.code.value == "NOT_FOUND"
