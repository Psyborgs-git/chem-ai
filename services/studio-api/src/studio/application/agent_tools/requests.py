"""Request boundary for research turns; blocking I/O owns its DB sessions."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from studio.application.agent_tools.turn import AgentTurnRunner
from studio.application.idempotency import run_idempotent
from studio.application.inference.runtime import OpenAICompatibleRuntime
from studio.auth.context import load_context
from studio.domain.inference.providers import ProviderService
from studio.domain.tasks.memory import TaskMemoryService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import SessionMessage


def run_research_turn(
    factory: sessionmaker[Session],
    *,
    workspace_id: uuid.UUID,
    principal_id: uuid.UUID,
    auth_session_id: uuid.UUID | None,
    session_id: uuid.UUID,
    content: str,
    turn_id: str,
    idempotency_key: str | None,
    provider_id: uuid.UUID | None,
    provider_revision: int | None,
    allow_provider_data_transfer: bool,
) -> dict[str, Any]:
    if not turn_id or len(turn_id) > 100:
        raise DomainError(ErrorCode.VALIDATION, "turnId must be 1-100 characters")
    with factory() as db:
        ctx = load_context(db, workspace_id, principal_id, auth_session_id)
        memory = TaskMemoryService(db, ctx)
        research_session = memory._session(session_id)
        task = memory._task(research_session.task_id)
        ctx.require("edit_task", task.project_id)
        # Serialize turns for this scoped session before external I/O. The
        # generic final-record idempotency race alone cannot undo a duplicate
        # provider request. An advisory lock leaves cancellation inserts free
        # to commit (a FOR UPDATE lock would block their foreign-key checks).
        lock_id = int.from_bytes(
            hashlib.sha256(f"research-turn:{workspace_id}:{session_id}".encode()).digest()[:8],
            signed=True,
        )
        db.execute(text("SELECT pg_advisory_xact_lock(:turn_lock)"), {"turn_lock": lock_id})
        runtime: OpenAICompatibleRuntime | None = None
        if provider_id is not None:
            if ctx.principal_kind != "user":
                raise DomainError(
                    ErrorCode.FORBIDDEN,
                    "provider data transfer requires a human user's explicit consent",
                    field_path="allowProviderDataTransfer",
                )
            service = ProviderService(db, ctx)
            provider = service.get(provider_id)
            if provider_revision != provider.version:
                raise DomainError(
                    ErrorCode.CONFLICT,
                    "selected provider changed; review its current destination and consent again",
                    field_path="providerRevision",
                )
            if not provider.enabled:
                raise DomainError(ErrorCode.CONFLICT, "selected inference provider is disabled")
            if not allow_provider_data_transfer:
                raise DomainError(
                    ErrorCode.FORBIDDEN,
                    "confirm sending this turn's task context, question "
                    "and tool results to the selected provider",
                    field_path="allowProviderDataTransfer",
                )
            runtime = OpenAICompatibleRuntime(provider, service.secrets)

        def cancel_check() -> bool:
            # A separate transaction sees cancellation while the turn's
            # messages/domain effects remain in their atomic command.
            with factory() as probe:
                return (
                    probe.query(SessionMessage.id)
                    .filter(
                        SessionMessage.workspace_id == workspace_id,
                        SessionMessage.session_id == session_id,
                        SessionMessage.refs["turn_cancel"].astext == turn_id,
                    )
                    .first()
                    is not None
                )

        def execute() -> dict[str, Any]:
            outcome = AgentTurnRunner(db, ctx, runtime=runtime).run_turn(
                session_id,
                content,
                turn_id=turn_id,
                cancel_check=cancel_check,
            )
            return {
                "finishedReason": outcome.finished_reason,
                "finalMessageId": str(outcome.final_message_id)
                if outcome.final_message_id
                else None,
                "toolCalls": outcome.tool_calls,
                "detail": outcome.detail,
                "provider": runtime.provenance if runtime else {"runtime": "llama.cpp"},
            }

        result = run_idempotent(
            db,
            ctx,
            operation=f"research.turn_request:{principal_id}",
            key=idempotency_key or f"turn:{turn_id}",
            payload={
                "sessionId": str(session_id),
                "content": content,
                "turnId": turn_id,
                "providerId": str(provider_id) if provider_id else None,
                "providerRevision": provider_revision,
                "allowProviderDataTransfer": allow_provider_data_transfer,
            },
            fn=execute,
        )
        db.commit()
        return result
