"""Durable task memory and session snapshots (§10.1, §11.1, CS-0304).

Memory layers stay separate: structured task state (tasks, contracts,
candidates, claims) is authoritative; decisions, open questions,
session messages, and generated summaries are their own tables. A
summary is a *derived* navigation aid — pinned to the contract
revision and source IDs it drew on, marked stale on read, and never
written back into structured state.

A session starts by compiling a token-budgeted ``ContextManifest``:
hard constraints and unresolved safety/identity warnings are pinned
and can never be budgeted away; everything else is selected in
priority order and omissions are disclosed explicitly — nothing is
silently dropped and no unit is ever truncated mid-quantity.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from chem_studio_policy.capabilities import CAP_EDIT_TASK, CAP_READ_PROJECT
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext
from studio.errors import DomainError, ErrorCode, not_found
from studio.events.outbox import publish
from studio.persistence.models import (
    CandidatePatch,
    CandidateRevision,
    ContextManifest,
    EvidenceClaim,
    ExperimentPlan,
    LabExecution,
    ResearchSession,
    ResearchTask,
    SessionMessage,
    SuccessContractRevision,
    TaskDecision,
    TaskQuestion,
    TaskSummary,
)

COMPILER_VERSION = "context-compiler-1"
DEFAULT_TOKEN_BUDGET = 8_000


def estimate_tokens(text: str) -> int:
    """Deterministic ~4-chars-per-token estimate. An approximation —
    recorded on the manifest so selection is auditable without a
    tokenizer dependency."""
    return max(1, (len(text) + 3) // 4)


@dataclass
class ManifestItem:
    """One selectable unit of context. ``pinned`` items (hard
    constraints, safety/identity warnings, blocking questions) are
    always included — the budget cannot evict them."""

    kind: str
    ref_id: str | None
    text: str
    pinned: bool = False
    tokens: int = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = estimate_tokens(self.text)


def compile_manifest(
    items: list[ManifestItem], token_budget: int
) -> tuple[list[ManifestItem], list[ManifestItem], bool]:
    """Select items under a token budget.

    Pinned items are always selected — even if they alone exceed the
    budget, in which case ``over_budget`` is reported rather than a
    constraint dropped. Remaining items are taken in the order given
    (callers pass them priority-sorted) until the next item would
    exceed the budget; everything left out is returned as the
    disclosed omission list. Items are never truncated — selection is
    at item granularity so a quantity/unit can never be split.
    """
    pinned = [i for i in items if i.pinned]
    rest = [i for i in items if not i.pinned]
    selected = list(pinned)
    used = sum(i.tokens for i in selected)
    omitted: list[ManifestItem] = []
    for item in rest:
        if used + item.tokens <= token_budget:
            selected.append(item)
            used += item.tokens
        else:
            omitted.append(item)
    return selected, omitted, used > token_budget


class TaskMemoryService:
    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    # ------------------------------------------------------ internals

    def _task(self, task_id: uuid.UUID) -> ResearchTask:
        task = self.db.execute(
            select(ResearchTask).where(
                ResearchTask.id == task_id,
                ResearchTask.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if task is None:
            raise not_found("task")
        return task

    def _session(self, session_id: uuid.UUID) -> ResearchSession:
        row = self.db.execute(
            select(ResearchSession).where(
                ResearchSession.id == session_id,
                ResearchSession.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("research session")
        return row

    # --------------------------------------------------- session flow

    def collect_items(self, task: ResearchTask) -> tuple[list[ManifestItem], list[ManifestItem]]:
        """Gather manifest candidates in priority order.

        Pinned (never evictable): the current contract revision's
        constraints + warnings, blocking open questions, and claims
        carrying a safety/identity warning condition. Everything else
        follows in §10.1 order: contract summary → selected candidate
        revisions → decisions (incl. rejected approaches) → open
        questions → reviewed evidence → prior-session history.
        """
        ws = self.ctx.workspace_id
        warnings: list[ManifestItem] = []
        contract = None
        if task.current_contract_revision_id is not None:
            contract = self.db.execute(
                select(SuccessContractRevision).where(
                    SuccessContractRevision.id == task.current_contract_revision_id
                )
            ).scalar_one_or_none()
        if contract is not None:
            payload = contract.payload or {}
            for text in payload.get("constraints", []) or []:
                warnings.append(
                    ManifestItem("constraint", str(contract.id), f"hard constraint: {text}", True)
                )
            for text in payload.get("warnings", []) or []:
                warnings.append(ManifestItem("warning", str(contract.id), f"warning: {text}", True))

        blocking = self.db.execute(
            select(TaskQuestion).where(
                TaskQuestion.workspace_id == ws,
                TaskQuestion.task_id == task.id,
                TaskQuestion.status == "open",
                TaskQuestion.blocking.is_(True),
            )
        ).scalars()
        warnings.extend(
            ManifestItem("question", str(q.id), f"blocking question: {q.question}", True)
            for q in blocking
        )

        warn_claims = self.db.execute(
            select(EvidenceClaim).where(
                EvidenceClaim.workspace_id == ws,
                EvidenceClaim.conditions["warning"].astext == "true",
            )
        ).scalars()
        warnings.extend(
            ManifestItem("warning", str(c.id), f"safety/identity warning on claim {c.id}", True)
            for c in warn_claims
        )

        items: list[ManifestItem] = []
        if contract is not None:
            items.append(
                ManifestItem(
                    "contract",
                    str(contract.id),
                    f"success contract revision {contract.revision} "
                    f"({contract.status}): {contract.payload}",
                )
            )
        if task.objective:
            items.append(ManifestItem("objective", str(task.id), f"objective: {task.objective}"))

        candidates = self.db.execute(
            select(CandidateRevision).where(
                CandidateRevision.workspace_id == ws,
                CandidateRevision.task_id == task.id,
                CandidateRevision.status.in_(["submitted", "accepted_for_research"]),
            )
        ).scalars()
        items.extend(
            ManifestItem(
                "candidate",
                str(c.id),
                f"selected candidate revision {c.revision} ({c.status}): {c.payload}",
            )
            for c in candidates
        )

        # accepted/rejected approaches — decisions plus rejected
        # patches/revisions keep their reasons (AT-0304-1).
        decisions = self.db.execute(
            select(TaskDecision)
            .where(TaskDecision.workspace_id == ws, TaskDecision.task_id == task.id)
            .order_by(TaskDecision.created_at)
        ).scalars()
        items.extend(
            ManifestItem("decision", str(d.id), f"decision ({d.kind}): {d.payload}")
            for d in decisions
        )
        rejected_patches = self.db.execute(
            select(CandidatePatch).where(
                CandidatePatch.workspace_id == ws,
                CandidatePatch.status == "rejected",
            )
        ).scalars()
        all_cand_ids = {
            row.id
            for row in self.db.execute(
                select(CandidateRevision).where(
                    CandidateRevision.workspace_id == ws,
                    CandidateRevision.task_id == task.id,
                )
            ).scalars()
        }
        items.extend(
            ManifestItem(
                "rejected_approach",
                str(p.id),
                f"rejected patch on candidate {p.candidate_id}: {p.rejection_reason}",
            )
            for p in rejected_patches
            if p.candidate_id in all_cand_ids
        )
        rejected_revisions = self.db.execute(
            select(CandidateRevision).where(
                CandidateRevision.workspace_id == ws,
                CandidateRevision.task_id == task.id,
                CandidateRevision.status == "rejected",
            )
        ).scalars()
        items.extend(
            ManifestItem(
                "rejected_approach",
                str(c.id),
                f"rejected candidate revision {c.revision}: {c.payload}",
            )
            for c in rejected_revisions
        )

        open_questions = self.db.execute(
            select(TaskQuestion).where(
                TaskQuestion.workspace_id == ws,
                TaskQuestion.task_id == task.id,
                TaskQuestion.status == "open",
                TaskQuestion.blocking.is_(False),
            )
        ).scalars()
        items.extend(
            ManifestItem("question", str(q.id), f"open question: {q.question}")
            for q in open_questions
        )

        claims = self.db.execute(
            select(EvidenceClaim).where(
                EvidenceClaim.workspace_id == ws,
                EvidenceClaim.status == "accepted",
            )
        ).scalars()
        items.extend(
            ManifestItem(
                "evidence",
                str(c.id),
                f"reviewed {c.kind} claim {c.id}: {c.statement}",
            )
            for c in claims
        )

        # experiment outcomes — a stopped execution or one carrying
        # deviations/observations must inform the next session; failure
        # causes are evidence, not invisible history (§25.4).
        executions = self.db.execute(
            select(LabExecution)
            .outerjoin(ExperimentPlan, LabExecution.plan_id == ExperimentPlan.id)
            .where(
                LabExecution.workspace_id == ws,
                or_(
                    ExperimentPlan.task_id == task.id,
                    LabExecution.task_id == task.id,
                ),
                or_(
                    LabExecution.status == "stopped",
                    func.jsonb_array_length(LabExecution.deviations) > 0,
                    LabExecution.observations.isnot(None),
                ),
            )
            .order_by(LabExecution.created_at)
        ).scalars()
        items.extend(
            ManifestItem(
                "experiment_outcome",
                str(e.id),
                f"execution {e.id} ({e.status}): "
                f"observations={e.observations or '—'}; "
                f"deviations={e.deviations or []}",
            )
            for e in executions
        )

        prior = self.db.execute(
            select(ResearchSession)
            .where(
                ResearchSession.workspace_id == ws,
                ResearchSession.task_id == task.id,
                ResearchSession.status == "ended",
            )
            .order_by(ResearchSession.ended_at)
        ).scalars()
        items.extend(
            ManifestItem(
                "history",
                str(s.id),
                f"prior session {s.id} ended {s.ended_at}: {s.end_snapshot}",
            )
            for s in prior
        )
        return warnings + items, warnings

    def start_session(
        self, task_id: uuid.UUID, *, token_budget: int = DEFAULT_TOKEN_BUDGET
    ) -> ResearchSession:
        """Compile the context manifest and open a session anchored to
        it (§11.1) — resumption is from this snapshot, not an empty
        chat."""
        if token_budget <= 0:
            raise DomainError(
                ErrorCode.VALIDATION,
                "token budget must be positive",
                field_path="input.tokenBudget",
            )
        task = self._task(task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        items, _ = self.collect_items(task)
        selected, omitted, over_budget = compile_manifest(items, token_budget)
        manifest = ContextManifest(
            workspace_id=self.ctx.workspace_id,
            task_id=task.id,
            contract_revision_id=task.current_contract_revision_id,
            compiler_version=COMPILER_VERSION,
            token_budget=token_budget,
            token_estimate=sum(i.tokens for i in selected),
            over_budget=over_budget,
            items=[
                {
                    "kind": i.kind,
                    "refId": i.ref_id,
                    "text": i.text,
                    "tokens": i.tokens,
                    "pinned": i.pinned,
                }
                for i in selected
            ],
            omitted=[{"kind": i.kind, "refId": i.ref_id, "tokens": i.tokens} for i in omitted],
            warnings=[
                {"kind": i.kind, "refId": i.ref_id, "text": i.text} for i in selected if i.pinned
            ],
            created_by=self.ctx.principal_id,
        )
        self.db.add(manifest)
        self.db.flush()
        session = ResearchSession(
            workspace_id=self.ctx.workspace_id,
            task_id=task.id,
            start_manifest_id=manifest.id,
            start_contract_revision_id=task.current_contract_revision_id,
            status="active",
            started_by=self.ctx.principal_id,
        )
        self.db.add(session)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="research_session",
            aggregate_id=session.id,
            event_type="session.started",
            payload={"taskId": str(task.id), "manifestId": str(manifest.id)},
        )
        return session

    def end_session(self, session_id: uuid.UUID) -> ResearchSession:
        """Close a session with a structured end snapshot — counts and
        IDs, not prose that could be mistaken for canonical state."""
        session = self._session(session_id)
        task = self._task(session.task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if session.status != "active":
            raise DomainError(
                ErrorCode.CONFLICT,
                f"session is already '{session.status}'",
                field_path="input.sessionId",
            )
        open_q = self.db.execute(
            select(func.count(TaskQuestion.id)).where(
                TaskQuestion.workspace_id == self.ctx.workspace_id,
                TaskQuestion.task_id == task.id,
                TaskQuestion.status == "open",
            )
        ).scalar_one()
        decisions = self.db.execute(
            select(func.count(TaskDecision.id)).where(
                TaskDecision.workspace_id == self.ctx.workspace_id,
                TaskDecision.task_id == task.id,
            )
        ).scalar_one()
        candidate_ids = [
            str(c.id)
            for c in self.db.execute(
                select(CandidateRevision).where(
                    CandidateRevision.workspace_id == self.ctx.workspace_id,
                    CandidateRevision.task_id == task.id,
                )
            ).scalars()
        ]
        session.status = "ended"
        session.ended_at = datetime.now(UTC)
        session.end_snapshot = {
            "contractRevisionId": (
                str(task.current_contract_revision_id)
                if task.current_contract_revision_id
                else None
            ),
            "openQuestions": open_q,
            "decisionCount": decisions,
            "candidateRevisionIds": candidate_ids,
        }
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="research_session",
            aggregate_id=session.id,
            event_type="session.ended",
            payload={"taskId": str(task.id)},
        )
        return session

    def sessions(self, task_id: uuid.UUID) -> list[ResearchSession]:
        task = self._task(task_id)
        self.ctx.require(CAP_READ_PROJECT, task.project_id)
        return list(
            self.db.execute(
                select(ResearchSession)
                .where(
                    ResearchSession.workspace_id == self.ctx.workspace_id,
                    ResearchSession.task_id == task.id,
                )
                .order_by(ResearchSession.created_at)
            ).scalars()
        )

    def manifest(self, manifest_id: uuid.UUID) -> ContextManifest:
        row = self.db.execute(
            select(ContextManifest).where(
                ContextManifest.id == manifest_id,
                ContextManifest.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("context manifest")
        task = self._task(row.task_id)
        self.ctx.require(CAP_READ_PROJECT, task.project_id)
        return row

    # ------------------------------------------------------- messages

    def post_message(
        self,
        session_id: uuid.UUID,
        *,
        role: str,
        kind: str = "message",
        content: str,
        refs: dict[str, Any] | None = None,
    ) -> SessionMessage:
        session = self._session(session_id)
        task = self._task(session.task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if session.status != "active":
            raise DomainError(
                ErrorCode.CONFLICT,
                "cannot post to an ended session",
                field_path="input.sessionId",
            )
        if role not in ("user", "assistant", "system", "tool"):
            raise DomainError(
                ErrorCode.VALIDATION,
                f"unknown message role '{role}'",
                field_path="input.role",
            )
        if kind not in ("message", "proposal", "tool_call", "tool_result", "rationale"):
            raise DomainError(
                ErrorCode.VALIDATION,
                f"unknown message kind '{kind}'",
                field_path="input.kind",
            )
        if not (content or "").strip():
            raise DomainError(
                ErrorCode.VALIDATION,
                "message content must not be empty",
                field_path="input.content",
            )
        row = SessionMessage(
            workspace_id=self.ctx.workspace_id,
            session_id=session.id,
            role=role,
            kind=kind,
            content=content,
            refs=refs or {},
            created_by=self.ctx.principal_id,
        )
        self.db.add(row)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="research_session",
            aggregate_id=session.id,
            event_type="session.message.posted",
            payload={
                "sessionId": str(session.id),
                "taskId": str(session.task_id),
                "messageId": str(row.id),
                "role": role,
                "kind": kind,
                "content": content,
                "refs": refs or {},
            },
        )
        return row

    def messages(self, session_id: uuid.UUID) -> list[SessionMessage]:
        session = self._session(session_id)
        task = self._task(session.task_id)
        self.ctx.require(CAP_READ_PROJECT, task.project_id)
        return list(
            self.db.execute(
                select(SessionMessage)
                .where(
                    SessionMessage.workspace_id == self.ctx.workspace_id,
                    SessionMessage.session_id == session.id,
                )
                .order_by(SessionMessage.created_at)
            ).scalars()
        )

    # ------------------------------------------------------ questions

    def raise_question(
        self, task_id: uuid.UUID, *, question: str, blocking: bool = False
    ) -> TaskQuestion:
        task = self._task(task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if not (question or "").strip():
            raise DomainError(
                ErrorCode.VALIDATION,
                "question must not be empty",
                field_path="input.question",
            )
        row = TaskQuestion(
            workspace_id=self.ctx.workspace_id,
            task_id=task.id,
            question=question,
            blocking=blocking,
            status="open",
            raised_by=self.ctx.principal_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def resolve_question(self, question_id: uuid.UUID, *, resolution: str) -> TaskQuestion:
        row = self.db.execute(
            select(TaskQuestion).where(
                TaskQuestion.id == question_id,
                TaskQuestion.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("task question")
        task = self._task(row.task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if row.status != "open":
            raise DomainError(
                ErrorCode.CONFLICT,
                f"question is already '{row.status}'",
                field_path="input.questionId",
            )
        if not (resolution or "").strip():
            raise DomainError(
                ErrorCode.VALIDATION,
                "a resolution is required",
                field_path="input.resolution",
            )
        row.status = "resolved"
        row.resolution = resolution
        row.resolved_at = datetime.now(UTC)
        self.db.flush()
        return row

    def questions(self, task_id: uuid.UUID) -> list[TaskQuestion]:
        task = self._task(task_id)
        self.ctx.require(CAP_READ_PROJECT, task.project_id)
        return list(
            self.db.execute(
                select(TaskQuestion)
                .where(
                    TaskQuestion.workspace_id == self.ctx.workspace_id,
                    TaskQuestion.task_id == task.id,
                )
                .order_by(TaskQuestion.created_at)
            ).scalars()
        )

    # ------------------------------------------------------ summaries

    def create_summary(
        self,
        task_id: uuid.UUID,
        *,
        body: str,
        source_ids: list[str],
        generator: str,
    ) -> TaskSummary:
        """Persist a derived summary pinned to the *current* contract
        revision and its source IDs. The summary never writes back —
        there is deliberately no apply/update path from a summary into
        structured state (§10.1)."""
        task = self._task(task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if not (body or "").strip():
            raise DomainError(
                ErrorCode.VALIDATION,
                "summary body must not be empty",
                field_path="input.body",
            )
        if not (generator or "").strip():
            raise DomainError(
                ErrorCode.VALIDATION,
                "generator (model/version or 'deterministic') is required",
                field_path="input.generator",
            )
        coverage: dict[str, int] = {"claims": 0, "decisions": 0, "chunks": 0}
        claim_ids = {
            str(c.id)
            for c in self.db.execute(
                select(EvidenceClaim).where(EvidenceClaim.workspace_id == self.ctx.workspace_id)
            ).scalars()
        }
        decision_ids = {
            str(d.id)
            for d in self.db.execute(
                select(TaskDecision).where(
                    TaskDecision.workspace_id == self.ctx.workspace_id,
                    TaskDecision.task_id == task.id,
                )
            ).scalars()
        }
        for sid in source_ids:
            if sid in claim_ids:
                coverage["claims"] += 1
            elif sid in decision_ids:
                coverage["decisions"] += 1
            else:
                coverage["chunks"] += 1
        row = TaskSummary(
            workspace_id=self.ctx.workspace_id,
            task_id=task.id,
            contract_revision_id=task.current_contract_revision_id,
            body=body,
            source_ids=source_ids,
            coverage=coverage,
            generator=generator,
            created_by=self.ctx.principal_id,
        )
        self.db.add(row)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="task.summary.create",
            target_type="task_summary",
            target_id=row.id,
            detail={"taskId": str(task.id), "generator": generator},
        )
        return row

    def summaries(self, task_id: uuid.UUID) -> list[tuple[TaskSummary, bool]]:
        """Summaries with their *computed* staleness (§10.1): stale
        when the contract has moved past the pinned revision or any
        referenced claim is no longer in its reviewed state. Staleness
        is derived at read time — a stale summary can never masquerade
        as current, and it can never overwrite structured state."""
        task = self._task(task_id)
        self.ctx.require(CAP_READ_PROJECT, task.project_id)
        rows = list(
            self.db.execute(
                select(TaskSummary)
                .where(
                    TaskSummary.workspace_id == self.ctx.workspace_id,
                    TaskSummary.task_id == task.id,
                )
                .order_by(TaskSummary.created_at)
            ).scalars()
        )
        all_ids = {sid for r in rows for sid in r.source_ids}
        claim_status: dict[str, str] = {}
        if all_ids:
            for c in self.db.execute(
                select(EvidenceClaim).where(
                    EvidenceClaim.workspace_id == self.ctx.workspace_id,
                    EvidenceClaim.id.in_([uuid.UUID(s) for s in all_ids if _is_uuid(s)]),
                )
            ).scalars():
                claim_status[str(c.id)] = c.status
        result: list[tuple[TaskSummary, bool]] = []
        for r in rows:
            stale = r.contract_revision_id != task.current_contract_revision_id
            for sid in r.source_ids:
                if sid in claim_status and claim_status[sid] not in ("accepted",):
                    stale = True
            result.append((r, stale))
        return result


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError):
        return False
    return True
