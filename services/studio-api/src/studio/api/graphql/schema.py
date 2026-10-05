"""GraphQL schema assembly (§8.1, CS-0104).

Root queries: viewer, workspace, projects (bounded keyset connection),
researchTask, node/nodes (Relay), engineCapabilities,
hardwareCapabilities. Mutation groups land in dependency order;
``taskCreate`` is present to prove the canonical-ID roundtrip
(AT-0104-1). Evidence/approval/model/export roots arrive with their
domain tables — they are not stubbed.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from enum import Enum
from typing import Any, cast

import strawberry
from chem_studio_policy.capabilities import CAP_READ_PROJECT, CAP_REQUEST_COMPUTE
from fastapi import Request
from sqlalchemy import or_, select
from strawberry import relay
from strawberry.fastapi import GraphQLRouter
from strawberry.scalars import JSON

from studio.api.capabilities import collect_capabilities
from studio.api.graphql.connections import PageInfo, keyset_page, page_args, reject_backward
from studio.api.graphql.context import GraphQLContext, gql_ctx, make_context
from studio.api.graphql.ids import scope_signature
from studio.api.graphql.types import (
    CandidateRevision,
    ClaimLink,
    ContractRevision,
    DatasetSnapshotInfo,
    Decision,
    EvidenceClaim,
    ExperimentPlan,
    ExtractedRecord,
    ImportBatch,
    LabBatch,
    LabExecution,
    LabSample,
    MaterialGrade,
    MaterialIdentity,
    Measurement,
    Project,
    ReferenceProduct,
    ReferenceProductRevision,
    ResearchSession,
    RunNode,
    SessionMessage,
    Task,
    TaskQuestion,
    TaskSummary,
    User,
    Workspace,
)
from studio.application.idempotency import run_idempotent
from studio.config.settings import Settings
from studio.domain.candidates.service import CandidateService
from studio.domain.evidence.claims import ClaimService
from studio.domain.evidence.imports import ImportService
from studio.domain.evidence.revocation import RevocationService
from studio.domain.lab.measurements import LabMeasurementService
from studio.domain.lab.plans import LabPlanService
from studio.domain.learning.datasets import DatasetService
from studio.domain.materials.service import MaterialService
from studio.domain.projects.service import ProjectService
from studio.domain.runs.admission import AdmissionService
from studio.domain.runs.queue import RunService
from studio.domain.tasks.evaluation import TaskEvaluationService
from studio.domain.tasks.memory import TaskMemoryService
from studio.domain.tasks.report import TaskReportService
from studio.domain.tasks.service import TaskService
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import (
    CandidateRevision as CandidateRow,
)
from studio.persistence.models import (
    ClaimLink as LinkRow,
)
from studio.persistence.models import (
    EvidenceClaim as ClaimRow,
)
from studio.persistence.models import (
    ExperimentPlan as PlanRow,
)
from studio.persistence.models import (
    ExtractedRecord as RecordRow,
)
from studio.persistence.models import (
    ImportBatch as BatchRow,
)
from studio.persistence.models import (
    LabBatch as LabBatchRow,
)
from studio.persistence.models import (
    LabExecution as LabExecutionRow,
)
from studio.persistence.models import (
    LabSample as LabSampleRow,
)
from studio.persistence.models import (
    MaterialGrade as GradeRow,
)
from studio.persistence.models import (
    MaterialIdentity as MaterialRow,
)
from studio.persistence.models import (
    Measurement as MeasurementRow,
)
from studio.persistence.models import (
    Principal as PrincipalRow,
)
from studio.persistence.models import (
    Project as ProjectRow,
)
from studio.persistence.models import (
    ReferenceProduct as RefProductRow,
)
from studio.persistence.models import (
    ReferenceProductRevision as RefRevRow,
)
from studio.persistence.models import (
    ResearchSession as ResearchSessionRow,
)
from studio.persistence.models import (
    ResearchTask as TaskRow,
)
from studio.persistence.models import (
    Run as RunRow,
)
from studio.persistence.models import (
    SessionMessage as SessionMessageRow,
)
from studio.persistence.models import (
    SourceRevocation as RevocationRow,
)
from studio.persistence.models import (
    SuccessContractRevision as ContractRow,
)
from studio.persistence.models import (
    TaskDecision as DecisionRow,
)
from studio.persistence.models import (
    TaskQuestion as TaskQuestionRow,
)
from studio.persistence.models import (
    Workspace as WorkspaceRow,
)

# ------------------------------------------------------------------
# connections


@strawberry.type
class ProjectEdge:
    cursor: str
    node: Project


@strawberry.type
class ProjectConnection:
    edges: list[ProjectEdge]
    page_info: PageInfo


@strawberry.type
class TaskEdge:
    cursor: str
    node: Task


@strawberry.type
class TaskConnection:
    edges: list[TaskEdge]
    page_info: PageInfo


@strawberry.type
class DecisionEdge:
    cursor: str
    node: Decision


@strawberry.type
class DecisionConnection:
    edges: list[DecisionEdge]
    page_info: PageInfo


@strawberry.type
class ResearchSessionEdge:
    cursor: str
    node: ResearchSession


@strawberry.type
class ResearchSessionConnection:
    edges: list[ResearchSessionEdge]
    page_info: PageInfo


@strawberry.type
class SessionMessageEdge:
    cursor: str
    node: SessionMessage


@strawberry.type
class SessionMessageConnection:
    edges: list[SessionMessageEdge]
    page_info: PageInfo


@strawberry.type
class RunEdge:
    cursor: str
    node: RunNode


@strawberry.type
class RunConnection:
    edges: list[RunEdge]
    page_info: PageInfo


@strawberry.type
class CandidateEdge:
    cursor: str
    node: CandidateRevision


@strawberry.type
class CandidateConnection:
    edges: list[CandidateEdge]
    page_info: PageInfo


@strawberry.type
class ImportBatchEdge:
    cursor: str
    node: ImportBatch


@strawberry.type
class ImportBatchConnection:
    edges: list[ImportBatchEdge]
    page_info: PageInfo


@strawberry.type
class ExtractedRecordEdge:
    cursor: str
    node: ExtractedRecord


@strawberry.type
class ExtractedRecordConnection:
    edges: list[ExtractedRecordEdge]
    page_info: PageInfo


@strawberry.type
class EvidenceClaimEdge:
    cursor: str
    node: EvidenceClaim


@strawberry.type
class EvidenceClaimConnection:
    edges: list[EvidenceClaimEdge]
    page_info: PageInfo


@strawberry.type
class ExperimentPlanEdge:
    cursor: str
    node: ExperimentPlan


@strawberry.type
class ExperimentPlanConnection:
    edges: list[ExperimentPlanEdge]
    page_info: PageInfo


# ------------------------------------------------------------------
# capability reports


@strawberry.type
class CapabilityStatus:
    status: str
    detail: str


@strawberry.type
class ProfileCapabilities:
    core: CapabilityStatus
    local_ai: CapabilityStatus
    optimization: CapabilityStatus
    quantum: CapabilityStatus
    materials: CapabilityStatus
    training: CapabilityStatus


@strawberry.type
class HardwareCapabilities:
    os: str
    arch: str
    gpu: str


def _cap(d: dict[str, str]) -> CapabilityStatus:
    return CapabilityStatus(status=d["status"], detail=d["detail"])


# ------------------------------------------------------------------
# mutation payloads


@strawberry.type
class DomainErrorPayload:
    code: str
    message: str
    field_path: str | None
    retryable: bool
    safe_details: JSON


@strawberry.input
class TaskCreateInput:
    project_id: relay.GlobalID
    title: str
    mode: str
    objective: str | None = None
    target_kind: str | None = None
    mode_inputs: JSON | None = None
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class ProjectCreateInput:
    slug: str
    name: str
    description: str | None = None
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class TaskTransitionInput:
    task_id: relay.GlobalID
    to_state: str
    reason: str | None = None
    expected_version: int | None = None
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class TaskCloseInput:
    task_id: relay.GlobalID
    closure_decision: str
    packet: JSON | None = None
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class TaskReopenInput:
    task_id: relay.GlobalID
    reason: str
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class ContractDraftCreateInput:
    task_id: relay.GlobalID
    payload: JSON
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class ContractFreezeInput:
    revision_id: relay.GlobalID
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.type
class TaskCreateResult:
    task: Task | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class ProjectResult:
    project: Project | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class TaskResult:
    task: Task | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class ContractRevisionResult:
    contract_revision: ContractRevision | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class CandidateRevisionResult:
    candidate: CandidateRevision | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class CandidatePatchResult:
    patch_id: str | None
    status: str | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class ImportBatchResult:
    batch: ImportBatch | None
    deduplicated: bool
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class ExtractedRecordResult:
    record: ExtractedRecord | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class EvidenceClaimResult:
    claim: EvidenceClaim | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class ClaimLinkResult:
    link: ClaimLink | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.input
class ImportArtifactInput:
    artifact_id: str  # raw uuid — artifacts are vault records, not Nodes
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class ReviewRecordInput:
    record_id: relay.GlobalID
    decision: str
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class PromoteRecordInput:
    record_id: relay.GlobalID
    subject: JSON
    statement: JSON
    conditions: JSON | None = None
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class ClaimCreateInput:
    kind: str
    subject: JSON
    statement: JSON
    locator: JSON | None = None
    original_text: str | None = None
    conditions: JSON | None = None
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class ClaimReviewInput:
    claim_id: relay.GlobalID
    decision: str
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class ClaimLinkInput:
    from_claim_id: relay.GlobalID
    to_claim_id: relay.GlobalID
    relation: str
    note: str | None = None
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class CandidateCreateInput:
    task_id: relay.GlobalID
    entity_kind: str
    entity_revision_id: str | None = None
    hypothesis: str | None = None
    proposed_differences: JSON | None = None
    evidence_ids: JSON | None = None
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class CandidateSubmitInput:
    candidate_id: relay.GlobalID
    client_mutation_id: str | None = None


@strawberry.input
class CandidateReviewInput:
    candidate_id: relay.GlobalID
    accept: bool
    client_mutation_id: str | None = None


@strawberry.input
class CandidatePatchProposeInput:
    candidate_id: relay.GlobalID
    patch: JSON
    reason: str | None = None
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class CandidatePatchReviewInput:
    patch_id: str
    accept: bool
    rejection_reason: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class SessionStartInput:
    task_id: relay.GlobalID
    token_budget: int | None = None
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class SessionEndInput:
    session_id: relay.GlobalID
    client_mutation_id: str | None = None


@strawberry.input
class MessagePostInput:
    session_id: relay.GlobalID
    role: str
    content: str
    kind: str | None = None
    refs: JSON | None = None
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class QuestionRaiseInput:
    task_id: relay.GlobalID
    question: str
    blocking: bool | None = None
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class QuestionResolveInput:
    question_id: relay.GlobalID
    resolution: str
    client_mutation_id: str | None = None


@strawberry.input
class SummaryCreateInput:
    task_id: relay.GlobalID
    body: str
    source_ids: list[str]
    generator: str
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class SourceRevokeInput:
    artifact_id: str  # raw uuid — artifacts are vault records, not Nodes
    reason: str
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.type
class SourceRevokeResult:
    report: JSON | None
    revocation_id: str | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class ResearchSessionResult:
    session: ResearchSession | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class SessionMessageResult:
    message: SessionMessage | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class TaskQuestionResult:
    question: TaskQuestion | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class TaskSummaryResult:
    summary_id: str | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.input
class MaterialIdentityCreateInput:
    kind: str
    name: str
    identifiers: JSON | None = None
    aliases: JSON | None = None
    structure: str | None = None
    structure_format: str | None = None
    confidentiality: str = "internal"
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class MaterialGradeCreateInput:
    material_id: relay.GlobalID
    supplier: str
    grade_name: str
    active_content: JSON | None = None
    specifications: JSON | None = None
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class ReferenceProductCreateInput:
    name: str
    supplier: str | None = None
    category: str | None = None
    composition_knowledge: str = "unknown"
    aliases: JSON | None = None
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class ReferenceRevisionDraftInput:
    product_id: relay.GlobalID
    payload: JSON
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class ReferenceRevisionFreezeInput:
    revision_id: relay.GlobalID
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class MaterialStructureReviewInput:
    identity_id: relay.GlobalID
    client_mutation_id: str | None = None


@strawberry.input
class MaterialMatchProposeInput:
    source_identity_id: relay.GlobalID
    candidate_identity_id: relay.GlobalID
    confidence: str | None = None
    rationale: str | None = None
    proposed_by: str = "user"
    client_mutation_id: str | None = None


@strawberry.input
class MaterialMatchReviewInput:
    match_id: relay.GlobalID
    decision: str
    rationale: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class MaterialGradeReconcileInput:
    keep_grade_id: relay.GlobalID
    merge_grade_id: relay.GlobalID
    reason: str
    client_mutation_id: str | None = None


@strawberry.type
class MaterialIdentityResult:
    identity: MaterialIdentity | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class MaterialGradeResult:
    grade: MaterialGrade | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class ReferenceProductResult:
    product: ReferenceProduct | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class ReferenceRevisionResult:
    revision: ReferenceProductRevision | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


def _mutate(
    gql: GraphQLContext,
    *,
    key: str | None,
    operation: str,
    payload: dict[str, Any],
    fn: Callable[[], dict[str, str]],
) -> dict[str, str]:
    ctx = gql.service_ctx()
    if key:
        return run_idempotent(gql.db, ctx, operation=operation, key=key, payload=payload, fn=fn)
    return fn()


def _err_payload(exc: DomainError) -> DomainErrorPayload:
    return DomainErrorPayload(
        code=str(exc.code),
        message=exc.message,
        field_path=exc.field_path,
        retryable=exc.retryable,
        safe_details=JSON(exc.safe_details),
    )


# ------------------------------------------------------------------
# query


@strawberry.type
class Query:
    node: relay.Node | None = relay.node()

    @strawberry.field
    def nodes(self, info: strawberry.Info, ids: list[relay.GlobalID]) -> list[relay.Node | None]:
        # Resolve through the same scoped machinery as node(); each id
        # returns its node or null (never leaks foreign existence).
        return [gid.resolve_node_sync(info) for gid in ids]

    @strawberry.field
    def viewer(self, info: strawberry.Info) -> User:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        row = gql.db.get(PrincipalRow, ctx.principal_id)
        if row is None:  # pragma: no cover - principal always exists
            raise not_found("principal")
        return User.from_row(row)

    @strawberry.field
    def workspace(self, info: strawberry.Info) -> Workspace:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        row = gql.db.get(WorkspaceRow, ctx.workspace_id)
        if row is None:  # pragma: no cover
            raise not_found("workspace")
        return Workspace.from_row(row)

    @strawberry.field
    def projects(
        self,
        info: strawberry.Info,
        first: int | None = None,
        after: str | None = None,
        last: int | None = None,
        before: str | None = None,
    ) -> ProjectConnection:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_READ_PROJECT)
        reject_backward(before, last)
        sig = scope_signature("projects", ctx.workspace_id, "created_at|id")
        args = page_args(first, after, kind="projects", sig=sig)
        stmt = select(ProjectRow).where(ProjectRow.workspace_id == ctx.workspace_id)
        rows: list[ProjectRow]
        rows, cursors, info_page = keyset_page(
            gql.db,
            stmt,
            ProjectRow.created_at,
            ProjectRow.id,
            args,
            kind="projects",
            sig=sig,
        )
        edges = [
            ProjectEdge(cursor=c, node=Project.from_row(r))
            for r, c in zip(rows, cursors, strict=True)
        ]
        return ProjectConnection(edges=edges, page_info=info_page)

    @strawberry.field
    def project_tasks(
        self,
        info: strawberry.Info,
        project_id: relay.GlobalID,
        first: int | None = None,
        after: str | None = None,
        last: int | None = None,
        before: str | None = None,
    ) -> TaskConnection:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_READ_PROJECT)
        reject_backward(before, last)
        if project_id.type_name != "Project":
            raise DomainError(ErrorCode.VALIDATION, "expected a Project id", field_path="projectId")
        try:
            p_uuid = uuid.UUID(project_id.node_id)
        except ValueError as exc:
            raise DomainError(ErrorCode.VALIDATION, "malformed Project id") from exc
        sig = scope_signature("project_tasks", ctx.workspace_id, str(p_uuid), "created_at|id")
        args = page_args(first, after, kind="project_tasks", sig=sig)
        stmt = select(TaskRow).where(
            TaskRow.workspace_id == ctx.workspace_id, TaskRow.project_id == p_uuid
        )
        rows: list[TaskRow]
        rows, cursors, info_page = keyset_page(
            gql.db,
            stmt,
            TaskRow.created_at,
            TaskRow.id,
            args,
            kind="project_tasks",
            sig=sig,
        )
        edges = [
            TaskEdge(cursor=c, node=Task.from_row(r)) for r, c in zip(rows, cursors, strict=True)
        ]
        return TaskConnection(edges=edges, page_info=info_page)

    @strawberry.field
    def task_decisions(
        self,
        info: strawberry.Info,
        task_id: relay.GlobalID,
        first: int | None = None,
        after: str | None = None,
        last: int | None = None,
        before: str | None = None,
    ) -> DecisionConnection:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_READ_PROJECT)
        reject_backward(before, last)
        t_uuid = _gid_uuid(task_id, "Task", "taskId")
        sig = scope_signature("task_decisions", ctx.workspace_id, str(t_uuid), "created_at|id")
        args = page_args(first, after, kind="task_decisions", sig=sig)
        stmt = select(DecisionRow).where(
            DecisionRow.workspace_id == ctx.workspace_id, DecisionRow.task_id == t_uuid
        )
        rows: list[DecisionRow]
        rows, cursors, info_page = keyset_page(
            gql.db,
            stmt,
            DecisionRow.created_at,
            DecisionRow.id,
            args,
            kind="task_decisions",
            sig=sig,
        )
        edges = [
            DecisionEdge(cursor=c, node=Decision.from_row(r))
            for r, c in zip(rows, cursors, strict=True)
        ]
        return DecisionConnection(edges=edges, page_info=info_page)

    @strawberry.field
    def task_candidate_revisions(
        self,
        info: strawberry.Info,
        task_id: relay.GlobalID,
        first: int | None = None,
        after: str | None = None,
        last: int | None = None,
        before: str | None = None,
    ) -> CandidateConnection:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_READ_PROJECT)
        reject_backward(before, last)
        t_uuid = _gid_uuid(task_id, "Task", "taskId")
        sig = scope_signature(
            "task_candidate_revisions", ctx.workspace_id, str(t_uuid), "created_at|id"
        )
        args = page_args(first, after, kind="task_candidate_revisions", sig=sig)
        stmt = select(CandidateRow).where(
            CandidateRow.workspace_id == ctx.workspace_id,
            CandidateRow.task_id == t_uuid,
        )
        rows: list[CandidateRow]
        rows, cursors, info_page = keyset_page(
            gql.db,
            stmt,
            CandidateRow.created_at,
            CandidateRow.id,
            args,
            kind="task_candidate_revisions",
            sig=sig,
        )
        edges = [
            CandidateEdge(cursor=c, node=CandidateRevision.from_row(r))
            for r, c in zip(rows, cursors, strict=True)
        ]
        return CandidateConnection(edges=edges, page_info=info_page)

    @strawberry.field
    def research_task(self, info: strawberry.Info, id: relay.GlobalID) -> Task | None:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_READ_PROJECT)
        if id.type_name != "Task":
            return None
        try:
            t_uuid = uuid.UUID(id.node_id)
        except ValueError:
            return None
        row = gql.db.execute(
            select(TaskRow).where(TaskRow.id == t_uuid, TaskRow.workspace_id == ctx.workspace_id)
        ).scalar_one_or_none()
        return Task.from_row(row) if row else None

    @strawberry.field
    def task_sessions(
        self,
        info: strawberry.Info,
        task_id: relay.GlobalID,
        first: int | None = None,
        after: str | None = None,
        last: int | None = None,
        before: str | None = None,
    ) -> ResearchSessionConnection:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_READ_PROJECT)
        reject_backward(before, last)
        t_uuid = _gid_uuid(task_id, "Task", "taskId")
        sig = scope_signature("task_sessions", ctx.workspace_id, str(t_uuid), "created_at|id")
        args = page_args(first, after, kind="task_sessions", sig=sig)
        stmt = select(ResearchSessionRow).where(
            ResearchSessionRow.workspace_id == ctx.workspace_id,
            ResearchSessionRow.task_id == t_uuid,
        )
        rows: list[ResearchSessionRow]
        rows, cursors, info_page = keyset_page(
            gql.db,
            stmt,
            ResearchSessionRow.created_at,
            ResearchSessionRow.id,
            args,
            kind="task_sessions",
            sig=sig,
        )
        edges = [
            ResearchSessionEdge(cursor=c, node=ResearchSession.from_row(r))
            for r, c in zip(rows, cursors, strict=True)
        ]
        return ResearchSessionConnection(edges=edges, page_info=info_page)

    @strawberry.field
    def task_runs(
        self,
        info: strawberry.Info,
        task_id: relay.GlobalID,
        first: int | None = None,
        after: str | None = None,
        last: int | None = None,
        before: str | None = None,
    ) -> RunConnection:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_READ_PROJECT)
        reject_backward(before, last)
        t_uuid = _gid_uuid(task_id, "Task", "taskId")
        sig = scope_signature("task_runs", ctx.workspace_id, str(t_uuid), "created_at|id")
        args = page_args(first, after, kind="task_runs", sig=sig)
        stmt = select(RunRow).where(
            RunRow.workspace_id == ctx.workspace_id,
            RunRow.task_id == t_uuid,
        )
        rows: list[RunRow]
        rows, cursors, info_page = keyset_page(
            gql.db,
            stmt,
            RunRow.created_at,
            RunRow.id,
            args,
            kind="task_runs",
            sig=sig,
        )
        edges = [
            RunEdge(cursor=c, node=RunNode.from_row(r)) for r, c in zip(rows, cursors, strict=True)
        ]
        return RunConnection(edges=edges, page_info=info_page)

    @strawberry.field
    def task_plans(
        self,
        info: strawberry.Info,
        task_id: relay.GlobalID,
        first: int | None = None,
        after: str | None = None,
        last: int | None = None,
        before: str | None = None,
    ) -> ExperimentPlanConnection:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_READ_PROJECT)
        reject_backward(before, last)
        t_uuid = _gid_uuid(task_id, "Task", "taskId")
        sig = scope_signature("task_plans", ctx.workspace_id, str(t_uuid), "created_at|id")
        args = page_args(first, after, kind="task_plans", sig=sig)
        stmt = select(PlanRow).where(
            PlanRow.workspace_id == ctx.workspace_id,
            PlanRow.task_id == t_uuid,
        )
        rows: list[PlanRow]
        rows, cursors, info_page = keyset_page(
            gql.db,
            stmt,
            PlanRow.created_at,
            PlanRow.id,
            args,
            kind="task_plans",
            sig=sig,
        )
        edges = [
            ExperimentPlanEdge(cursor=c, node=ExperimentPlan.from_row(r))
            for r, c in zip(rows, cursors, strict=True)
        ]
        return ExperimentPlanConnection(edges=edges, page_info=info_page)

    @strawberry.field
    def plan_executions(self, info: strawberry.Info, plan_id: relay.GlobalID) -> list[LabExecution]:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_READ_PROJECT)
        p_uuid = _gid_uuid(plan_id, "ExperimentPlan", "planId")
        rows = (
            gql.db.execute(
                select(LabExecutionRow)
                .where(
                    LabExecutionRow.workspace_id == ctx.workspace_id,
                    LabExecutionRow.plan_id == p_uuid,
                )
                .order_by(LabExecutionRow.created_at, LabExecutionRow.id)
            )
            .scalars()
            .all()
        )
        return [LabExecution.from_row(r) for r in rows]

    @strawberry.field
    def task_executions(self, info: strawberry.Info, task_id: relay.GlobalID) -> list[LabExecution]:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_READ_PROJECT)
        t_uuid = _gid_uuid(task_id, "Task", "taskId")
        rows = (
            gql.db.execute(
                select(LabExecutionRow)
                .outerjoin(PlanRow, LabExecutionRow.plan_id == PlanRow.id)
                .where(
                    LabExecutionRow.workspace_id == ctx.workspace_id,
                    or_(
                        PlanRow.task_id == t_uuid,
                        LabExecutionRow.task_id == t_uuid,
                    ),
                )
                .order_by(LabExecutionRow.created_at, LabExecutionRow.id)
            )
            .scalars()
            .all()
        )
        return [LabExecution.from_row(r) for r in rows]

    @strawberry.field
    def replication_summary(self, info: strawberry.Info, execution_id: relay.GlobalID) -> JSON:
        gql = gql_ctx(info)
        e_uuid = _gid_uuid(execution_id, "LabExecution", "executionId")
        return JSON(LabMeasurementService(gql.db, gql.service_ctx()).replication_summary(e_uuid))

    @strawberry.field
    def measurement_contract_check(
        self, info: strawberry.Info, measurement_id: relay.GlobalID, metric: JSON
    ) -> JSON:
        gql = gql_ctx(info)
        m_uuid = _gid_uuid(measurement_id, "Measurement", "measurementId")
        return JSON(
            LabMeasurementService(gql.db, gql.service_ctx()).compare_to_contract(
                m_uuid, cast(dict[str, Any], metric)
            )
        )

    @strawberry.field
    def task_evaluation(self, info: strawberry.Info, task_id: relay.GlobalID) -> JSON:
        gql = gql_ctx(info)
        t_uuid = _gid_uuid(task_id, "Task", "taskId")
        return JSON(TaskEvaluationService(gql.db, gql.service_ctx()).evaluate(t_uuid))

    @strawberry.field
    def task_closeout_packet(self, info: strawberry.Info, task_id: relay.GlobalID) -> JSON:
        gql = gql_ctx(info)
        t_uuid = _gid_uuid(task_id, "Task", "taskId")
        return JSON(TaskEvaluationService(gql.db, gql.service_ctx()).closeout_packet(t_uuid))

    @strawberry.field
    def task_reassessment_status(self, info: strawberry.Info, task_id: relay.GlobalID) -> JSON:
        gql = gql_ctx(info)
        t_uuid = _gid_uuid(task_id, "Task", "taskId")
        return JSON(TaskEvaluationService(gql.db, gql.service_ctx()).reassessment_status(t_uuid))

    @strawberry.field
    def task_report(self, info: strawberry.Info, task_id: relay.GlobalID) -> JSON:
        gql = gql_ctx(info)
        t_uuid = _gid_uuid(task_id, "Task", "taskId")
        return JSON(TaskReportService(gql.db, gql.service_ctx()).report(t_uuid))

    @strawberry.field
    def dataset_snapshots(
        self, info: strawberry.Info, task_id: relay.GlobalID | None = None
    ) -> list[DatasetSnapshotInfo]:
        gql = gql_ctx(info)
        t_uuid = _gid_uuid(task_id, "Task", "taskId") if task_id is not None else None
        rows = DatasetService(gql.db, gql.service_ctx()).list(t_uuid)
        return [DatasetSnapshotInfo.from_row(r) for r in rows]

    @strawberry.field
    def dataset_snapshot_drift(self, info: strawberry.Info, snapshot_id: relay.GlobalID) -> JSON:
        gql = gql_ctx(info)
        s_uuid = _gid_uuid(snapshot_id, "DatasetSnapshot", "snapshotId")
        return JSON(DatasetService(gql.db, gql.service_ctx()).drift_status(s_uuid))

    @strawberry.field
    def session_messages(
        self,
        info: strawberry.Info,
        session_id: relay.GlobalID,
        first: int | None = None,
        after: str | None = None,
        last: int | None = None,
        before: str | None = None,
    ) -> SessionMessageConnection:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_READ_PROJECT)
        reject_backward(before, last)
        s_uuid = _gid_uuid(session_id, "ResearchSession", "sessionId")
        sig = scope_signature("session_messages", ctx.workspace_id, str(s_uuid), "created_at|id")
        args = page_args(first, after, kind="session_messages", sig=sig)
        stmt = select(SessionMessageRow).where(
            SessionMessageRow.workspace_id == ctx.workspace_id,
            SessionMessageRow.session_id == s_uuid,
        )
        rows: list[SessionMessageRow]
        rows, cursors, info_page = keyset_page(
            gql.db,
            stmt,
            SessionMessageRow.created_at,
            SessionMessageRow.id,
            args,
            kind="session_messages",
            sig=sig,
        )
        edges = [
            SessionMessageEdge(cursor=c, node=SessionMessage.from_row(r))
            for r, c in zip(rows, cursors, strict=True)
        ]
        return SessionMessageConnection(edges=edges, page_info=info_page)

    @strawberry.field
    def task_questions(self, info: strawberry.Info, task_id: relay.GlobalID) -> list[TaskQuestion]:
        gql = gql_ctx(info)
        t_uuid = _gid_uuid(task_id, "Task", "taskId")
        rows = TaskMemoryService(gql.db, gql.service_ctx()).questions(t_uuid)
        return [TaskQuestion.from_row(r) for r in rows]

    @strawberry.field
    def task_summaries(self, info: strawberry.Info, task_id: relay.GlobalID) -> list[TaskSummary]:
        gql = gql_ctx(info)
        t_uuid = _gid_uuid(task_id, "Task", "taskId")
        rows = TaskMemoryService(gql.db, gql.service_ctx()).summaries(t_uuid)
        return [TaskSummary.from_row(r, stale=stale) for r, stale in rows]

    @strawberry.field
    def data_quality_report(
        self, info: strawberry.Info, batch_id: relay.GlobalID | None = None
    ) -> JSON:
        """§9.3 data-quality rollup: counts, flag taxonomy, coverage
        matrix, and outcome categories — never a single inflated
        score."""
        gql = gql_ctx(info)
        svc = ImportService(gql.db, None)
        ctx = gql.service_ctx()
        if batch_id is not None:
            b_uuid = _gid_uuid(batch_id, "ImportBatch", "batchId")
            return JSON(svc.batch_quality_report(ctx, b_uuid))
        return JSON(svc.quality_report(ctx))

    @strawberry.field
    def revocation_impact(self, info: strawberry.Info, artifact_id: str) -> JSON:
        """Read-only preview of a source revocation's impact (§17.5)."""
        gql = gql_ctx(info)
        try:
            a_uuid = uuid.UUID(artifact_id)
        except ValueError as exc:
            raise DomainError(
                ErrorCode.VALIDATION, "malformed artifact id", field_path="artifactId"
            ) from exc
        ctx = gql.service_ctx()
        return JSON(RevocationService(gql.db, ctx).impact(ctx, a_uuid))

    @strawberry.field
    def source_revocations(self, info: strawberry.Info, artifact_id: str | None = None) -> JSON:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        a_uuid = None
        if artifact_id is not None:
            try:
                a_uuid = uuid.UUID(artifact_id)
            except ValueError as exc:
                raise DomainError(
                    ErrorCode.VALIDATION, "malformed artifact id", field_path="artifactId"
                ) from exc
        rows = RevocationService(gql.db, ctx).revocations(ctx, a_uuid)
        return JSON(
            [
                {
                    "id": str(r.id),
                    "artifactId": str(r.artifact_id),
                    "reason": r.reason,
                    "report": r.report,
                    "createdAt": r.created_at.isoformat(),
                }
                for r in rows
            ]
        )

    @strawberry.field
    def engine_capabilities(self, info: strawberry.Info) -> ProfileCapabilities:
        gql = gql_ctx(info)
        profiles = collect_capabilities(gql.settings)["profiles"]
        return ProfileCapabilities(
            core=_cap(profiles["core"]),
            local_ai=_cap(profiles["local_ai"]),
            optimization=_cap(profiles["optimization"]),
            quantum=_cap(profiles["quantum"]),
            materials=_cap(profiles["materials"]),
            training=_cap(profiles["training"]),
        )

    @strawberry.field
    def hardware_capabilities(self, info: strawberry.Info) -> HardwareCapabilities:
        gql = gql_ctx(info)
        hw = collect_capabilities(gql.settings)["hardware"]
        return HardwareCapabilities(os=hw["os"], arch=hw["arch"], gpu=hw["gpu"])

    @strawberry.field
    def compute_resources(self, info: strawberry.Info) -> JSON:
        """Observed hardware report + resource-group utilization
        (§13.4/§20.1): every unobservable field is reported unknown —
        nothing is fabricated."""
        from workers.common.resources import detect

        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_REQUEST_COMPUTE)
        adm = AdmissionService(gql.db, ctx)
        return JSON(
            {
                "hardware": detect().to_dict(),
                "groups": [
                    {
                        "name": g.name,
                        "capacity": g.capacity,
                        "reserve": g.reserve,
                        "reserved": adm.utilization(g.name)["reserved"],
                    }
                    for g in adm.groups()
                ],
            }
        )

    @strawberry.field
    def import_batches(
        self,
        info: strawberry.Info,
        first: int | None = None,
        after: str | None = None,
        last: int | None = None,
        before: str | None = None,
    ) -> ImportBatchConnection:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_READ_PROJECT)
        reject_backward(before, last)
        sig = scope_signature("import_batches", ctx.workspace_id, "created_at|id")
        args = page_args(first, after, kind="import_batches", sig=sig)
        stmt = select(BatchRow).where(BatchRow.workspace_id == ctx.workspace_id)
        rows: list[BatchRow]
        rows, cursors, info_page = keyset_page(
            gql.db,
            stmt,
            BatchRow.created_at,
            BatchRow.id,
            args,
            kind="import_batches",
            sig=sig,
        )
        edges = [
            ImportBatchEdge(cursor=c, node=ImportBatch.from_row(r))
            for r, c in zip(rows, cursors, strict=True)
        ]
        return ImportBatchConnection(edges=edges, page_info=info_page)

    @strawberry.field
    def import_records(
        self,
        info: strawberry.Info,
        batch_id: relay.GlobalID,
        first: int | None = None,
        after: str | None = None,
        last: int | None = None,
        before: str | None = None,
    ) -> ExtractedRecordConnection:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_READ_PROJECT)
        reject_backward(before, last)
        b_uuid = _gid_uuid(batch_id, "ImportBatch", "batchId")
        sig = scope_signature("import_records", ctx.workspace_id, str(b_uuid), "created_at|id")
        args = page_args(first, after, kind="import_records", sig=sig)
        stmt = select(RecordRow).where(
            RecordRow.workspace_id == ctx.workspace_id,
            RecordRow.batch_id == b_uuid,
        )
        rows: list[RecordRow]
        rows, cursors, info_page = keyset_page(
            gql.db,
            stmt,
            RecordRow.created_at,
            RecordRow.id,
            args,
            kind="import_records",
            sig=sig,
        )
        edges = [
            ExtractedRecordEdge(cursor=c, node=ExtractedRecord.from_row(r))
            for r, c in zip(rows, cursors, strict=True)
        ]
        return ExtractedRecordConnection(edges=edges, page_info=info_page)

    @strawberry.field
    def evidence_claims(
        self,
        info: strawberry.Info,
        kind: str | None = None,
        status: str | None = None,
        first: int | None = None,
        after: str | None = None,
        last: int | None = None,
        before: str | None = None,
    ) -> EvidenceClaimConnection:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_READ_PROJECT)
        reject_backward(before, last)
        sig = scope_signature(
            "evidence_claims",
            ctx.workspace_id,
            kind or "-",
            status or "-",
            "created_at|id",
        )
        args = page_args(first, after, kind="evidence_claims", sig=sig)
        stmt = select(ClaimRow).where(ClaimRow.workspace_id == ctx.workspace_id)
        if kind is not None:
            stmt = stmt.where(ClaimRow.kind == kind)
        if status is not None:
            stmt = stmt.where(ClaimRow.status == status)
        rows: list[ClaimRow]
        rows, cursors, info_page = keyset_page(
            gql.db,
            stmt,
            ClaimRow.created_at,
            ClaimRow.id,
            args,
            kind="evidence_claims",
            sig=sig,
        )
        edges = [
            EvidenceClaimEdge(cursor=c, node=EvidenceClaim.from_row(r))
            for r, c in zip(rows, cursors, strict=True)
        ]
        return EvidenceClaimConnection(edges=edges, page_info=info_page)

    @strawberry.field
    def claim_links(self, info: strawberry.Info, claim_id: relay.GlobalID) -> list[ClaimLink]:
        """Support/contradiction edges touching one claim — both sides
        stay visible regardless of relation (AT-0302-2)."""
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_READ_PROJECT)
        c_uuid = _gid_uuid(claim_id, "EvidenceClaim", "claimId")
        rows = ClaimService(gql.db).links_for(ctx, c_uuid)
        return [ClaimLink.from_row(r) for r in rows]


# ------------------------------------------------------------------
# mutation helpers


def _gid_uuid(gid: relay.GlobalID, type_name: str, field: str) -> uuid.UUID:
    """Decode a scoped node ID or raise a fielded VALIDATION error."""
    if gid.type_name != type_name:
        raise DomainError(
            ErrorCode.VALIDATION, f"expected a {type_name} id", field_path=f"input.{field}"
        )
    try:
        return uuid.UUID(gid.node_id)
    except ValueError as exc:
        raise DomainError(
            ErrorCode.VALIDATION, f"malformed {type_name} id", field_path=f"input.{field}"
        ) from exc


# ------------------------------------------------------------------
# mutation


@strawberry.type
class Mutation:
    @strawberry.mutation
    def project_create(self, info: strawberry.Info, input: ProjectCreateInput) -> ProjectResult:
        gql = gql_ctx(info)
        try:
            ctx = gql.service_ctx()
            svc = ProjectService(gql.db, ctx)
            payload = {"slug": input.slug, "name": input.name, "description": input.description}

            def _do() -> dict[str, str]:
                project = svc.create(
                    slug=input.slug, name=input.name, description=input.description
                )
                return {"projectId": str(project.id)}

            result = (
                run_idempotent(
                    gql.db,
                    ctx,
                    operation="project.create",
                    key=input.idempotency_key,
                    payload=payload,
                    fn=_do,
                )
                if input.idempotency_key
                else _do()
            )
            gql.db.commit()
            row = gql.db.get(ProjectRow, uuid.UUID(result["projectId"]))
            if row is None:  # pragma: no cover
                raise not_found("project")
            return ProjectResult(
                project=Project.from_row(row),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ProjectResult(
                project=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def task_create(self, info: strawberry.Info, input: TaskCreateInput) -> TaskCreateResult:
        gql = gql_ctx(info)
        try:
            ctx = gql.service_ctx()
            svc = TaskService(gql.db, ctx)
            p_uuid = _gid_uuid(input.project_id, "Project", "projectId")
            command_payload = {
                "projectId": str(p_uuid),
                "title": input.title,
                "mode": input.mode,
                "objective": input.objective,
                "targetKind": input.target_kind,
                "modeInputs": input.mode_inputs,
            }

            def _do() -> dict[str, str]:
                task = svc.create(
                    project_id=p_uuid,
                    title=input.title,
                    mode=input.mode,
                    objective=input.objective,
                    target_kind=input.target_kind,
                    mode_inputs=cast(dict[str, Any], input.mode_inputs)
                    if input.mode_inputs is not None
                    else None,
                )
                return {"taskId": str(task.id)}

            result = (
                run_idempotent(
                    gql.db,
                    ctx,
                    operation="task.create",
                    key=input.idempotency_key,
                    payload=command_payload,
                    fn=_do,
                )
                if input.idempotency_key
                else _do()
            )
            gql.db.commit()
            task = gql.db.get(TaskRow, uuid.UUID(result["taskId"]))
            if task is None:  # pragma: no cover - created/committed above
                raise not_found("task")
            return TaskCreateResult(
                task=Task.from_row(task),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return TaskCreateResult(
                task=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def task_transition(self, info: strawberry.Info, input: TaskTransitionInput) -> TaskResult:
        gql = gql_ctx(info)
        try:
            ctx = gql.service_ctx()
            svc = TaskService(gql.db, ctx)
            t_uuid = _gid_uuid(input.task_id, "Task", "taskId")
            payload = {
                "taskId": str(t_uuid),
                "toState": input.to_state,
                "reason": input.reason,
                "expectedVersion": input.expected_version,
            }

            def _do() -> dict[str, str]:
                task = svc.transition(
                    task_id=t_uuid,
                    to_state=input.to_state,
                    reason=input.reason,
                    expected_version=input.expected_version,
                )
                return {"taskId": str(task.id)}

            result = (
                run_idempotent(
                    gql.db,
                    ctx,
                    operation="task.transition",
                    key=input.idempotency_key,
                    payload=payload,
                    fn=_do,
                )
                if input.idempotency_key
                else _do()
            )
            gql.db.commit()
            row = gql.db.get(TaskRow, uuid.UUID(result["taskId"]))
            if row is None:  # pragma: no cover
                raise not_found("task")
            return TaskResult(
                task=Task.from_row(row),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return TaskResult(
                task=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def task_close(self, info: strawberry.Info, input: TaskCloseInput) -> TaskResult:
        gql = gql_ctx(info)
        try:
            ctx = gql.service_ctx()
            svc = TaskService(gql.db, ctx)
            t_uuid = _gid_uuid(input.task_id, "Task", "taskId")
            payload = {
                "taskId": str(t_uuid),
                "closureDecision": input.closure_decision,
                "packet": input.packet,
            }

            def _do() -> dict[str, str]:
                task = svc.close(
                    task_id=t_uuid,
                    closure_decision=input.closure_decision,
                    packet=cast(dict[str, Any], input.packet) if input.packet is not None else None,
                )
                return {"taskId": str(task.id)}

            result = (
                run_idempotent(
                    gql.db,
                    ctx,
                    operation="task.close",
                    key=input.idempotency_key,
                    payload=payload,
                    fn=_do,
                )
                if input.idempotency_key
                else _do()
            )
            gql.db.commit()
            row = gql.db.get(TaskRow, uuid.UUID(result["taskId"]))
            if row is None:  # pragma: no cover
                raise not_found("task")
            return TaskResult(
                task=Task.from_row(row),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return TaskResult(
                task=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def task_reopen(self, info: strawberry.Info, input: TaskReopenInput) -> TaskResult:
        gql = gql_ctx(info)
        try:
            ctx = gql.service_ctx()
            svc = TaskService(gql.db, ctx)
            t_uuid = _gid_uuid(input.task_id, "Task", "taskId")
            payload = {"taskId": str(t_uuid), "reason": input.reason}

            def _do() -> dict[str, str]:
                task = svc.reopen(task_id=t_uuid, reason=input.reason)
                return {"taskId": str(task.id)}

            result = (
                run_idempotent(
                    gql.db,
                    ctx,
                    operation="task.reopen",
                    key=input.idempotency_key,
                    payload=payload,
                    fn=_do,
                )
                if input.idempotency_key
                else _do()
            )
            gql.db.commit()
            row = gql.db.get(TaskRow, uuid.UUID(result["taskId"]))
            if row is None:  # pragma: no cover
                raise not_found("task")
            return TaskResult(
                task=Task.from_row(row),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return TaskResult(
                task=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def contract_draft_create(
        self, info: strawberry.Info, input: ContractDraftCreateInput
    ) -> ContractRevisionResult:
        gql = gql_ctx(info)
        try:
            ctx = gql.service_ctx()
            svc = TaskService(gql.db, ctx)
            t_uuid = _gid_uuid(input.task_id, "Task", "taskId")
            payload = {"taskId": str(t_uuid), "payload": input.payload}

            def _do() -> dict[str, str]:
                rev = svc.draft_contract(
                    task_id=t_uuid, payload=cast(dict[str, Any], input.payload)
                )
                return {"revisionId": str(rev.id)}

            result = (
                run_idempotent(
                    gql.db,
                    ctx,
                    operation="contract.draft",
                    key=input.idempotency_key,
                    payload=payload,
                    fn=_do,
                )
                if input.idempotency_key
                else _do()
            )
            gql.db.commit()
            row = gql.db.get(ContractRow, uuid.UUID(result["revisionId"]))
            if row is None:  # pragma: no cover
                raise not_found("contract revision")
            return ContractRevisionResult(
                contract_revision=ContractRevision.from_row(row),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ContractRevisionResult(
                contract_revision=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def contract_freeze(
        self, info: strawberry.Info, input: ContractFreezeInput
    ) -> ContractRevisionResult:
        gql = gql_ctx(info)
        try:
            ctx = gql.service_ctx()
            svc = TaskService(gql.db, ctx)
            r_uuid = _gid_uuid(input.revision_id, "ContractRevision", "revisionId")
            payload = {"revisionId": str(r_uuid)}

            def _do() -> dict[str, str]:
                rev = svc.freeze_contract(revision_id=r_uuid)
                return {"revisionId": str(rev.id)}

            result = (
                run_idempotent(
                    gql.db,
                    ctx,
                    operation="contract.freeze",
                    key=input.idempotency_key,
                    payload=payload,
                    fn=_do,
                )
                if input.idempotency_key
                else _do()
            )
            gql.db.commit()
            row = gql.db.get(ContractRow, uuid.UUID(result["revisionId"]))
            if row is None:  # pragma: no cover
                raise not_found("contract revision")
            return ContractRevisionResult(
                contract_revision=ContractRevision.from_row(row),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ContractRevisionResult(
                contract_revision=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def materials(self) -> MaterialsMutation:
        """Materials-registry commands under one namespace (CS-0203)."""
        return MaterialsMutation()

    @strawberry.mutation
    def candidates(self) -> CandidatesMutation:
        """Candidate lifecycle commands under one namespace (CS-0206)."""
        return CandidatesMutation()

    @strawberry.mutation
    def imports(self) -> ImportsMutation:
        """Extraction-review commands under one namespace (CS-0302)."""
        return ImportsMutation()

    @strawberry.mutation
    def evidence(self) -> EvidenceMutation:
        """Evidence-claim commands under one namespace (CS-0302)."""
        return EvidenceMutation()

    @strawberry.mutation
    def research(self) -> ResearchMutation:
        """Session/memory commands under one namespace (CS-0304)."""
        return ResearchMutation()

    @strawberry.field
    def runs(self) -> RunsMutation:
        return RunsMutation()

    @strawberry.mutation
    def lab(self) -> LabMutation:
        """Experiment-plan commands under one namespace (CS-0501)."""
        return LabMutation()

    @strawberry.mutation
    def learning(self) -> LearningMutation:
        """Dataset/training-eligibility commands (CS-0601)."""
        return LearningMutation()

    @strawberry.field
    def optimization(self) -> OptimizationMutation:
        return OptimizationMutation()


@strawberry.input
class DatasetSnapshotBuildInput:
    purpose: str
    name: str
    task_id: relay.GlobalID | None = None
    client_mutation_id: str | None = None


@strawberry.input
class DatasetSnapshotIdInput:
    snapshot_id: relay.GlobalID
    client_mutation_id: str | None = None


@strawberry.type
class DatasetSnapshotResult:
    snapshot: DatasetSnapshotInfo | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class DatasetPrepareResult:
    report: JSON | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class LearningMutation:
    """Dataset snapshot commands (§17.2, CS-0601). Build/freeze/
    prepare are `manage_models`-gated; the rights gate blocks freezes
    with DATA_RIGHTS_UNKNOWN."""

    @strawberry.mutation
    def snapshot_build(
        self, info: strawberry.Info, input: DatasetSnapshotBuildInput
    ) -> DatasetSnapshotResult:
        gql = gql_ctx(info)
        try:
            t_uuid = (
                _gid_uuid(input.task_id, "Task", "taskId") if input.task_id is not None else None
            )
            snap = DatasetService(gql.db, gql.service_ctx()).build(
                purpose=input.purpose, name=input.name, task_id=t_uuid
            )
            gql.db.commit()
            return DatasetSnapshotResult(
                snapshot=DatasetSnapshotInfo.from_row(snap),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return DatasetSnapshotResult(
                snapshot=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def snapshot_freeze(
        self, info: strawberry.Info, input: DatasetSnapshotIdInput
    ) -> DatasetSnapshotResult:
        gql = gql_ctx(info)
        try:
            s_uuid = _gid_uuid(input.snapshot_id, "DatasetSnapshot", "snapshotId")
            snap = DatasetService(gql.db, gql.service_ctx()).freeze(s_uuid)
            gql.db.commit()
            return DatasetSnapshotResult(
                snapshot=DatasetSnapshotInfo.from_row(snap),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return DatasetSnapshotResult(
                snapshot=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def snapshot_prepare_run(
        self, info: strawberry.Info, input: DatasetSnapshotIdInput
    ) -> DatasetPrepareResult:
        gql = gql_ctx(info)
        try:
            s_uuid = _gid_uuid(input.snapshot_id, "DatasetSnapshot", "snapshotId")
            report = DatasetService(gql.db, gql.service_ctx()).prepare_run(s_uuid)
            gql.db.commit()
            return DatasetPrepareResult(
                report=JSON(report),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return DatasetPrepareResult(
                report=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )


def graphql_app(settings: Settings) -> GraphQLRouter:
    def get_context(request: Request) -> GraphQLContext:
        db = request.app.state.session_factory()
        request.state.studio_db = db
        return make_context(request, db, settings)

    return GraphQLRouter(schema, context_getter=get_context, graphql_ide=None)


# ------------------------------------------------------------------
# materials registry mutations (CS-0203)


@strawberry.type
class MaterialsMutation:
    @strawberry.mutation
    def identity_create(
        self, info: strawberry.Info, input: MaterialIdentityCreateInput
    ) -> MaterialIdentityResult:
        gql = gql_ctx(info)
        try:
            svc = MaterialService(gql.db, gql.service_ctx())
            payload = {
                "kind": input.kind,
                "name": input.name,
                "identifiers": input.identifiers,
                "aliases": input.aliases,
                "structure": input.structure,
                "structureFormat": input.structure_format,
                "confidentiality": input.confidentiality,
            }

            def _do() -> dict[str, str]:
                row = svc.create_identity(
                    kind=input.kind,
                    name=input.name,
                    identifiers=cast(list[dict[str, Any]], input.identifiers)
                    if input.identifiers is not None
                    else None,
                    aliases=cast(list[dict[str, Any]], input.aliases)
                    if input.aliases is not None
                    else None,
                    structure=input.structure,
                    structure_format=input.structure_format,
                    confidentiality=input.confidentiality,
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="material.identity_create",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(MaterialRow, uuid.UUID(result["id"]))
            return MaterialIdentityResult(
                identity=MaterialIdentity.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return MaterialIdentityResult(
                identity=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def structure_review(
        self, info: strawberry.Info, input: MaterialStructureReviewInput
    ) -> MaterialIdentityResult:
        gql = gql_ctx(info)
        try:
            svc = MaterialService(gql.db, gql.service_ctx())
            i_uuid = _gid_uuid(input.identity_id, "MaterialIdentity", "identityId")

            def _do() -> dict[str, str]:
                row = svc.review_structure(identity_id=i_uuid)
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=None,
                operation="material.structure_review",
                payload={"identityId": str(i_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(MaterialRow, uuid.UUID(result["id"]))
            return MaterialIdentityResult(
                identity=MaterialIdentity.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return MaterialIdentityResult(
                identity=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def match_propose(
        self, info: strawberry.Info, input: MaterialMatchProposeInput
    ) -> MaterialIdentityResult:
        gql = gql_ctx(info)
        try:
            svc = MaterialService(gql.db, gql.service_ctx())
            s_uuid = _gid_uuid(input.source_identity_id, "MaterialIdentity", "sourceIdentityId")
            c_uuid = _gid_uuid(
                input.candidate_identity_id, "MaterialIdentity", "candidateIdentityId"
            )

            def _do() -> dict[str, str]:
                svc.propose_match(
                    source_identity_id=s_uuid,
                    candidate_identity_id=c_uuid,
                    confidence=input.confidence,
                    rationale=input.rationale,
                    proposed_by=input.proposed_by,
                )
                return {"id": str(s_uuid)}

            result = _mutate(
                gql,
                key=None,
                operation="material.match_propose",
                payload={"source": str(s_uuid), "candidate": str(c_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(MaterialRow, uuid.UUID(result["id"]))
            return MaterialIdentityResult(
                identity=MaterialIdentity.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return MaterialIdentityResult(
                identity=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def match_review(
        self, info: strawberry.Info, input: MaterialMatchReviewInput
    ) -> MaterialIdentityResult:
        gql = gql_ctx(info)
        try:
            svc = MaterialService(gql.db, gql.service_ctx())
            m_uuid = _gid_uuid(input.match_id, "IdentityMatch", "matchId")

            def _do() -> dict[str, str]:
                row = svc.review_match(
                    match_id=m_uuid, decision=input.decision, rationale=input.rationale
                )
                return {"id": str(row.source_identity_id)}

            result = _mutate(
                gql,
                key=None,
                operation="material.match_review",
                payload={"matchId": str(m_uuid), "decision": input.decision},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(MaterialRow, uuid.UUID(result["id"]))
            return MaterialIdentityResult(
                identity=MaterialIdentity.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return MaterialIdentityResult(
                identity=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def grade_create(
        self, info: strawberry.Info, input: MaterialGradeCreateInput
    ) -> MaterialGradeResult:
        gql = gql_ctx(info)
        try:
            svc = MaterialService(gql.db, gql.service_ctx())
            m_uuid = _gid_uuid(input.material_id, "MaterialIdentity", "materialId")
            payload = {
                "materialId": str(m_uuid),
                "supplier": input.supplier,
                "gradeName": input.grade_name,
                "activeContent": input.active_content,
                "specifications": input.specifications,
            }

            def _do() -> dict[str, str]:
                row = svc.create_grade(
                    material_id=m_uuid,
                    supplier=input.supplier,
                    grade_name=input.grade_name,
                    active_content=cast(dict[str, Any], input.active_content)
                    if input.active_content is not None
                    else None,
                    specifications=cast(dict[str, Any], input.specifications)
                    if input.specifications is not None
                    else None,
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="material.grade_create",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(GradeRow, uuid.UUID(result["id"]))
            return MaterialGradeResult(
                grade=MaterialGrade.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return MaterialGradeResult(
                grade=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def grade_reconcile(
        self, info: strawberry.Info, input: MaterialGradeReconcileInput
    ) -> MaterialGradeResult:
        gql = gql_ctx(info)
        try:
            svc = MaterialService(gql.db, gql.service_ctx())
            keep = _gid_uuid(input.keep_grade_id, "MaterialGrade", "keepGradeId")
            merge = _gid_uuid(input.merge_grade_id, "MaterialGrade", "mergeGradeId")

            def _do() -> dict[str, str]:
                row = svc.reconcile_grades(
                    keep_grade_id=keep, merge_grade_id=merge, reason=input.reason
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=None,
                operation="material.grade_reconcile",
                payload={"keep": str(keep), "merge": str(merge), "reason": input.reason},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(GradeRow, uuid.UUID(result["id"]))
            return MaterialGradeResult(
                grade=MaterialGrade.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return MaterialGradeResult(
                grade=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def reference_product_create(
        self, info: strawberry.Info, input: ReferenceProductCreateInput
    ) -> ReferenceProductResult:
        gql = gql_ctx(info)
        try:
            svc = MaterialService(gql.db, gql.service_ctx())
            payload = {
                "name": input.name,
                "supplier": input.supplier,
                "category": input.category,
                "compositionKnowledge": input.composition_knowledge,
                "aliases": input.aliases,
            }

            def _do() -> dict[str, str]:
                row = svc.create_reference_product(
                    name=input.name,
                    supplier=input.supplier,
                    category=input.category,
                    composition_knowledge=input.composition_knowledge,
                    aliases=cast(list[dict[str, Any]], input.aliases)
                    if input.aliases is not None
                    else None,
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="material.reference_create",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(RefProductRow, uuid.UUID(result["id"]))
            return ReferenceProductResult(
                product=ReferenceProduct.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ReferenceProductResult(
                product=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def reference_revision_draft(
        self, info: strawberry.Info, input: ReferenceRevisionDraftInput
    ) -> ReferenceRevisionResult:
        gql = gql_ctx(info)
        try:
            svc = MaterialService(gql.db, gql.service_ctx())
            p_uuid = _gid_uuid(input.product_id, "ReferenceProduct", "productId")
            payload = {"productId": str(p_uuid), "payload": input.payload}

            def _do() -> dict[str, str]:
                row = svc.draft_reference_revision(
                    product_id=p_uuid, payload=cast(dict[str, Any], input.payload)
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="material.ref_rev_draft",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(RefRevRow, uuid.UUID(result["id"]))
            return ReferenceRevisionResult(
                revision=ReferenceProductRevision.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ReferenceRevisionResult(
                revision=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def reference_revision_freeze(
        self, info: strawberry.Info, input: ReferenceRevisionFreezeInput
    ) -> ReferenceRevisionResult:
        gql = gql_ctx(info)
        try:
            svc = MaterialService(gql.db, gql.service_ctx())
            r_uuid = _gid_uuid(input.revision_id, "ReferenceProductRevision", "revisionId")

            def _do() -> dict[str, str]:
                row = svc.freeze_reference_revision(revision_id=r_uuid)
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="material.ref_rev_freeze",
                payload={"revisionId": str(r_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(RefRevRow, uuid.UUID(result["id"]))
            return ReferenceRevisionResult(
                revision=ReferenceProductRevision.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ReferenceRevisionResult(
                revision=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )


@strawberry.type
class CandidatesMutation:
    """Candidate revisions + proposal patches (§5, §7.2): content is
    immutable once accepted; a patch is the only content path and
    always goes through human review."""

    @strawberry.mutation
    def create(self, info: strawberry.Info, input: CandidateCreateInput) -> CandidateRevisionResult:
        gql = gql_ctx(info)
        try:
            ctx = gql.service_ctx()
            svc = CandidateService(gql.db, ctx)
            t_uuid = _gid_uuid(input.task_id, "Task", "taskId")
            entity_rev = uuid.UUID(input.entity_revision_id) if input.entity_revision_id else None
            payload = {
                "taskId": str(t_uuid),
                "entityKind": input.entity_kind,
                "entityRevisionId": input.entity_revision_id,
                "hypothesis": input.hypothesis,
            }

            def _do() -> dict[str, str]:
                row = svc.create_candidate(
                    task_id=t_uuid,
                    entity_kind=input.entity_kind,
                    entity_revision_id=entity_rev,
                    hypothesis=input.hypothesis,
                    proposed_differences=cast(
                        list[dict[str, Any]] | None, input.proposed_differences
                    ),
                    evidence_ids=cast(list[str] | None, input.evidence_ids),
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="candidate.create",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(CandidateRow, uuid.UUID(result["id"]))
            return CandidateRevisionResult(
                candidate=CandidateRevision.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return CandidateRevisionResult(
                candidate=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def submit(self, info: strawberry.Info, input: CandidateSubmitInput) -> CandidateRevisionResult:
        gql = gql_ctx(info)
        try:
            ctx = gql.service_ctx()
            svc = CandidateService(gql.db, ctx)
            c_uuid = _gid_uuid(input.candidate_id, "CandidateRevision", "candidateId")
            row = svc.submit_candidate(candidate_id=c_uuid)
            gql.db.commit()
            return CandidateRevisionResult(
                candidate=CandidateRevision.from_row(row),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return CandidateRevisionResult(
                candidate=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def review(self, info: strawberry.Info, input: CandidateReviewInput) -> CandidateRevisionResult:
        gql = gql_ctx(info)
        try:
            ctx = gql.service_ctx()
            svc = CandidateService(gql.db, ctx)
            c_uuid = _gid_uuid(input.candidate_id, "CandidateRevision", "candidateId")
            row = svc.review_candidate(candidate_id=c_uuid, accept=input.accept)
            gql.db.commit()
            return CandidateRevisionResult(
                candidate=CandidateRevision.from_row(row),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return CandidateRevisionResult(
                candidate=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def patch_propose(
        self, info: strawberry.Info, input: CandidatePatchProposeInput
    ) -> CandidatePatchResult:
        gql = gql_ctx(info)
        try:
            ctx = gql.service_ctx()
            svc = CandidateService(gql.db, ctx)
            c_uuid = _gid_uuid(input.candidate_id, "CandidateRevision", "candidateId")

            def _do() -> dict[str, str]:
                row = svc.propose_patch(
                    candidate_id=c_uuid,
                    patch=cast(dict[str, Any], input.patch),
                    reason=input.reason,
                )
                return {"id": str(row.id), "status": row.status}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="candidate.patch_propose",
                payload={
                    "candidateId": str(c_uuid),
                    "patch": cast(dict[str, Any], input.patch),
                },
                fn=_do,
            )
            gql.db.commit()
            return CandidatePatchResult(
                patch_id=result["id"],
                status=result["status"],
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return CandidatePatchResult(
                patch_id=None,
                status=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def patch_review(
        self, info: strawberry.Info, input: CandidatePatchReviewInput
    ) -> CandidatePatchResult:
        gql = gql_ctx(info)
        try:
            ctx = gql.service_ctx()
            svc = CandidateService(gql.db, ctx)
            row = svc.review_patch(
                patch_id=uuid.UUID(input.patch_id),
                accept=input.accept,
                rejection_reason=input.rejection_reason,
            )
            gql.db.commit()
            return CandidatePatchResult(
                patch_id=str(row.id),
                status=row.status,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return CandidatePatchResult(
                patch_id=None,
                status=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )


# ------------------------------------------------------------------
# extraction review + evidence mutations (CS-0302)


@strawberry.type
class ImportsMutation:
    @strawberry.mutation
    def source_revoke(self, info: strawberry.Info, input: SourceRevokeInput) -> SourceRevokeResult:
        """Revoke a source and propagate supersession through index,
        records, claims, and downstream lineage (§9.4, §17.5)."""
        gql = gql_ctx(info)
        try:
            try:
                a_uuid = uuid.UUID(input.artifact_id)
            except ValueError as exc:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "malformed artifact id",
                    field_path="input.artifactId",
                ) from exc
            payload = {"artifactId": str(a_uuid), "reason": input.reason}

            def _do() -> dict[str, str]:
                row = RevocationService(gql.db, gql.service_ctx()).revoke(
                    gql.service_ctx(), a_uuid, reason=input.reason
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="imports.source_revoke",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(RevocationRow, uuid.UUID(result["id"]))
            return SourceRevokeResult(
                report=JSON(row.report) if row else None,
                revocation_id=result["id"],
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return SourceRevokeResult(
                report=None,
                revocation_id=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def artifact_import(
        self, info: strawberry.Info, input: ImportArtifactInput
    ) -> ImportBatchResult:
        """Run the quarantined ingestion pipeline over a committed
        artifact — dedup makes a reimport return the existing batch."""
        gql = gql_ctx(info)
        try:
            try:
                a_uuid = uuid.UUID(input.artifact_id)
            except ValueError as exc:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "malformed artifact id",
                    field_path="input.artifactId",
                ) from exc
            payload = {"artifactId": str(a_uuid)}
            from studio.domain.evidence.vault import Vault

            def _do() -> dict[str, str]:
                batch, deduped = ImportService(
                    gql.db, Vault(gql.settings.vault_root)
                ).import_artifact(gql.service_ctx(), a_uuid)
                return {"id": str(batch.id), "deduplicated": str(deduped)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="imports.artifact_import",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(BatchRow, uuid.UUID(result["id"]))
            return ImportBatchResult(
                batch=ImportBatch.from_row(row) if row else None,
                deduplicated=result["deduplicated"] == "True",
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ImportBatchResult(
                batch=None,
                deduplicated=False,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def record_review(
        self, info: strawberry.Info, input: ReviewRecordInput
    ) -> ExtractedRecordResult:
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.record_id, "ExtractedRecord", "recordId")
            payload = {"recordId": str(r_uuid), "decision": input.decision}

            def _do() -> dict[str, str]:
                row = ImportService(gql.db, None).review_record(
                    gql.service_ctx(), r_uuid, input.decision
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="imports.record_review",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(RecordRow, uuid.UUID(result["id"]))
            return ExtractedRecordResult(
                record=ExtractedRecord.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ExtractedRecordResult(
                record=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def record_promote(
        self, info: strawberry.Info, input: PromoteRecordInput
    ) -> EvidenceClaimResult:
        """Promote an extracted field to a proposed evidence claim —
        ambiguity stays visible; nothing is auto-accepted."""
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.record_id, "ExtractedRecord", "recordId")
            payload = {
                "recordId": str(r_uuid),
                "subject": input.subject,
                "statement": input.statement,
            }

            def _do() -> dict[str, str]:
                row = ClaimService(gql.db).promote_record(
                    gql.service_ctx(),
                    r_uuid,
                    subject=cast(dict[str, Any], input.subject),
                    statement=cast(dict[str, Any], input.statement),
                    conditions=cast(dict[str, Any] | None, input.conditions),
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="imports.record_promote",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(ClaimRow, uuid.UUID(result["id"]))
            return EvidenceClaimResult(
                claim=EvidenceClaim.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return EvidenceClaimResult(
                claim=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )


@strawberry.type
class EvidenceMutation:
    @strawberry.mutation
    def claim_create(self, info: strawberry.Info, input: ClaimCreateInput) -> EvidenceClaimResult:
        gql = gql_ctx(info)
        try:
            payload = {"kind": input.kind, "subject": input.subject}

            def _do() -> dict[str, str]:
                row = ClaimService(gql.db).create_claim(
                    gql.service_ctx(),
                    kind=input.kind,
                    subject=cast(dict[str, Any], input.subject),
                    statement=cast(dict[str, Any], input.statement),
                    locator=cast(dict[str, Any] | None, input.locator),
                    original_text=input.original_text,
                    conditions=cast(dict[str, Any] | None, input.conditions),
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="evidence.claim_create",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(ClaimRow, uuid.UUID(result["id"]))
            return EvidenceClaimResult(
                claim=EvidenceClaim.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return EvidenceClaimResult(
                claim=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def claim_review(self, info: strawberry.Info, input: ClaimReviewInput) -> EvidenceClaimResult:
        gql = gql_ctx(info)
        try:
            c_uuid = _gid_uuid(input.claim_id, "EvidenceClaim", "claimId")
            payload = {"claimId": str(c_uuid), "decision": input.decision}

            def _do() -> dict[str, str]:
                row = ClaimService(gql.db).review(gql.service_ctx(), c_uuid, input.decision)
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="evidence.claim_review",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(ClaimRow, uuid.UUID(result["id"]))
            return EvidenceClaimResult(
                claim=EvidenceClaim.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return EvidenceClaimResult(
                claim=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def claim_link(self, info: strawberry.Info, input: ClaimLinkInput) -> ClaimLinkResult:
        gql = gql_ctx(info)
        try:
            f_uuid = _gid_uuid(input.from_claim_id, "EvidenceClaim", "fromClaimId")
            t_uuid = _gid_uuid(input.to_claim_id, "EvidenceClaim", "toClaimId")
            payload = {
                "from": str(f_uuid),
                "to": str(t_uuid),
                "relation": input.relation,
            }

            def _do() -> dict[str, str]:
                row = ClaimService(gql.db).link(
                    gql.service_ctx(),
                    f_uuid,
                    t_uuid,
                    input.relation,
                    note=input.note,
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="evidence.claim_link",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(LinkRow, uuid.UUID(result["id"]))
            return ClaimLinkResult(
                link=ClaimLink.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ClaimLinkResult(
                link=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )


# ------------------------------------------------------------------
# research memory mutations (CS-0304)


@strawberry.input
class RunRequestInput:
    task_id: relay.GlobalID
    kind: str
    request: JSON | None = None
    max_attempts: int | None = None
    requires_approval: bool = False
    client_mutation_id: str | None = None
    idempotency_key: str = strawberry.field(default="")


@strawberry.input
class RunCancelInput:
    run_id: relay.GlobalID
    client_mutation_id: str | None = None


@strawberry.type
class RunResult:
    run: RunNode | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class RunsMutation:
    @strawberry.mutation
    def request(self, info: strawberry.Info, input: RunRequestInput) -> RunResult:
        gql = gql_ctx(info)
        try:
            t_uuid = _gid_uuid(input.task_id, "Task", "taskId")
            payload = {"taskId": str(t_uuid), "kind": input.kind}

            def _do() -> dict[str, str]:
                kwargs: dict[str, Any] = {}
                if input.max_attempts is not None:
                    kwargs["max_attempts"] = input.max_attempts
                row = RunService(gql.db, gql.service_ctx()).request(
                    kind=input.kind,
                    request=cast(dict[str, Any], input.request) if input.request else {},
                    task_id=t_uuid,
                    requires_approval=input.requires_approval,
                    **kwargs,
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key or None,
                operation="runs.request",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(RunRow, uuid.UUID(result["id"]))
            return RunResult(
                run=RunNode.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return RunResult(
                run=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def request_cancel(self, info: strawberry.Info, input: RunCancelInput) -> RunResult:
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.run_id, "Run", "runId")

            def _do() -> dict[str, str]:
                row = RunService(gql.db, gql.service_ctx()).request_cancel(r_uuid)
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=None,
                operation="runs.request_cancel",
                payload={"runId": str(r_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(RunRow, uuid.UUID(result["id"]))
            return RunResult(
                run=RunNode.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return RunResult(
                run=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )


@strawberry.type
class ResearchMutation:
    @strawberry.mutation
    def session_start(
        self, info: strawberry.Info, input: SessionStartInput
    ) -> ResearchSessionResult:
        gql = gql_ctx(info)
        try:
            t_uuid = _gid_uuid(input.task_id, "Task", "taskId")
            payload = {"taskId": str(t_uuid), "tokenBudget": input.token_budget}

            def _do() -> dict[str, str]:
                kwargs: dict[str, Any] = {}
                if input.token_budget is not None:
                    kwargs["token_budget"] = input.token_budget
                row = TaskMemoryService(gql.db, gql.service_ctx()).start_session(t_uuid, **kwargs)
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="research.session_start",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(ResearchSessionRow, uuid.UUID(result["id"]))
            return ResearchSessionResult(
                session=ResearchSession.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ResearchSessionResult(
                session=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def session_end(self, info: strawberry.Info, input: SessionEndInput) -> ResearchSessionResult:
        gql = gql_ctx(info)
        try:
            s_uuid = _gid_uuid(input.session_id, "ResearchSession", "sessionId")

            def _do() -> dict[str, str]:
                row = TaskMemoryService(gql.db, gql.service_ctx()).end_session(s_uuid)
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=None,
                operation="research.session_end",
                payload={"sessionId": str(s_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(ResearchSessionRow, uuid.UUID(result["id"]))
            return ResearchSessionResult(
                session=ResearchSession.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ResearchSessionResult(
                session=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def message_post(self, info: strawberry.Info, input: MessagePostInput) -> SessionMessageResult:
        gql = gql_ctx(info)
        try:
            s_uuid = _gid_uuid(input.session_id, "ResearchSession", "sessionId")
            payload = {
                "sessionId": str(s_uuid),
                "role": input.role,
                "kind": input.kind,
                "content": input.content,
            }

            def _do() -> dict[str, str]:
                row = TaskMemoryService(gql.db, gql.service_ctx()).post_message(
                    s_uuid,
                    role=input.role,
                    kind=input.kind or "message",
                    content=input.content,
                    refs=cast(dict[str, Any], input.refs) if input.refs else None,
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="research.message_post",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(SessionMessageRow, uuid.UUID(result["id"]))
            return SessionMessageResult(
                message=SessionMessage.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return SessionMessageResult(
                message=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def question_raise(
        self, info: strawberry.Info, input: QuestionRaiseInput
    ) -> TaskQuestionResult:
        gql = gql_ctx(info)
        try:
            t_uuid = _gid_uuid(input.task_id, "Task", "taskId")
            payload = {"taskId": str(t_uuid), "question": input.question}

            def _do() -> dict[str, str]:
                row = TaskMemoryService(gql.db, gql.service_ctx()).raise_question(
                    t_uuid, question=input.question, blocking=bool(input.blocking)
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="research.question_raise",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(TaskQuestionRow, uuid.UUID(result["id"]))
            return TaskQuestionResult(
                question=TaskQuestion.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return TaskQuestionResult(
                question=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def question_resolve(
        self, info: strawberry.Info, input: QuestionResolveInput
    ) -> TaskQuestionResult:
        gql = gql_ctx(info)
        try:
            q_uuid = _gid_uuid(input.question_id, "TaskQuestion", "questionId")

            def _do() -> dict[str, str]:
                row = TaskMemoryService(gql.db, gql.service_ctx()).resolve_question(
                    q_uuid, resolution=input.resolution
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=None,
                operation="research.question_resolve",
                payload={"questionId": str(q_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(TaskQuestionRow, uuid.UUID(result["id"]))
            return TaskQuestionResult(
                question=TaskQuestion.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return TaskQuestionResult(
                question=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def summary_create(self, info: strawberry.Info, input: SummaryCreateInput) -> TaskSummaryResult:
        gql = gql_ctx(info)
        try:
            t_uuid = _gid_uuid(input.task_id, "Task", "taskId")
            payload = {"taskId": str(t_uuid), "generator": input.generator}

            def _do() -> dict[str, str]:
                row = TaskMemoryService(gql.db, gql.service_ctx()).create_summary(
                    t_uuid,
                    body=input.body,
                    source_ids=list(input.source_ids),
                    generator=input.generator,
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="research.summary_create",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            return TaskSummaryResult(
                summary_id=result["id"],
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return TaskSummaryResult(
                summary_id=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )


# ------------------------------------------------------------------
# experiment plan mutations (CS-0501)


@strawberry.input
class PlanCreateInput:
    task_id: relay.GlobalID
    title: str
    payload: JSON
    idempotency_key: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class PlanUpdateInput:
    plan_id: relay.GlobalID
    payload: JSON
    client_mutation_id: str | None = None


@strawberry.input
class PlanIdInput:
    plan_id: relay.GlobalID
    client_mutation_id: str | None = None


@strawberry.input
class PlanReviewInput:
    plan_id: relay.GlobalID
    decision: str
    rationale: str | None = None
    client_mutation_id: str | None = None


@strawberry.type
class PlanResult:
    plan: ExperimentPlan | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class PacketResult:
    packet: JSON | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class LabMutation:
    @strawberry.mutation
    def plan_create(self, info: strawberry.Info, input: PlanCreateInput) -> PlanResult:
        gql = gql_ctx(info)
        try:
            t_uuid = _gid_uuid(input.task_id, "Task", "taskId")
            payload = {"taskId": str(t_uuid), "title": input.title}

            def _do() -> dict[str, str]:
                row = LabPlanService(gql.db, gql.service_ctx()).create(
                    t_uuid,
                    title=input.title,
                    payload=cast(dict[str, Any], input.payload),
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="lab.plan_create",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(PlanRow, uuid.UUID(result["id"]))
            return PlanResult(
                plan=ExperimentPlan.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return PlanResult(
                plan=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def plan_update(self, info: strawberry.Info, input: PlanUpdateInput) -> PlanResult:
        gql = gql_ctx(info)
        try:
            p_uuid = _gid_uuid(input.plan_id, "ExperimentPlan", "planId")

            def _do() -> dict[str, str]:
                row = LabPlanService(gql.db, gql.service_ctx()).update(
                    p_uuid, payload=cast(dict[str, Any], input.payload)
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=None,
                operation="lab.plan_update",
                payload={"planId": str(p_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(PlanRow, uuid.UUID(result["id"]))
            return PlanResult(
                plan=ExperimentPlan.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return PlanResult(
                plan=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def plan_submit(self, info: strawberry.Info, input: PlanIdInput) -> PlanResult:
        gql = gql_ctx(info)
        try:
            p_uuid = _gid_uuid(input.plan_id, "ExperimentPlan", "planId")

            def _do() -> dict[str, str]:
                row = LabPlanService(gql.db, gql.service_ctx()).submit(p_uuid)
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=None,
                operation="lab.plan_submit",
                payload={"planId": str(p_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(PlanRow, uuid.UUID(result["id"]))
            return PlanResult(
                plan=ExperimentPlan.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return PlanResult(
                plan=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def plan_review(self, info: strawberry.Info, input: PlanReviewInput) -> PlanResult:
        gql = gql_ctx(info)
        try:
            p_uuid = _gid_uuid(input.plan_id, "ExperimentPlan", "planId")

            def _do() -> dict[str, str]:
                row = LabPlanService(gql.db, gql.service_ctx()).review(
                    p_uuid, decision=input.decision, rationale=input.rationale
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=None,
                operation="lab.plan_review",
                payload={
                    "planId": str(p_uuid),
                    "decision": input.decision,
                    "rationale": input.rationale,
                },
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(PlanRow, uuid.UUID(result["id"]))
            return PlanResult(
                plan=ExperimentPlan.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return PlanResult(
                plan=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def packet_export(self, info: strawberry.Info, input: PlanIdInput) -> PacketResult:
        """Manual-execution packet — gated by a valid, current release
        approval (AT-0501-1/3)."""
        gql = gql_ctx(info)
        try:
            p_uuid = _gid_uuid(input.plan_id, "ExperimentPlan", "planId")

            def _do() -> dict[str, str]:
                LabPlanService(gql.db, gql.service_ctx()).export_packet(p_uuid)
                return {"id": str(p_uuid)}

            result = _mutate(
                gql,
                key=None,
                operation="lab.packet_export",
                payload={"planId": str(p_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(PlanRow, uuid.UUID(result["id"]))
            return PacketResult(
                packet=JSON(row.packet) if row is not None else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return PacketResult(
                packet=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def measurements(self) -> LabMeasurementsMutation:
        """Execution/measurement recording under one namespace (CS-0502)."""
        return LabMeasurementsMutation()


# ------------------------------------------------------------------
# lab executions / measurements mutations (CS-0502)


@strawberry.input
class ExecutionOpenInput:
    plan_id: relay.GlobalID
    client_mutation_id: str | None = None


@strawberry.input
class ExecutionHistoricalInput:
    task_id: relay.GlobalID
    payload: JSON
    client_mutation_id: str | None = None


@strawberry.input
class ExecutionCloseInput:
    execution_id: relay.GlobalID
    status: str = "completed"
    client_mutation_id: str | None = None


@strawberry.input
class ActualsRecordInput:
    execution_id: relay.GlobalID
    actual: JSON | None = None
    deviations: JSON | None = None
    observations: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class BatchAddInput:
    execution_id: relay.GlobalID
    label: str
    payload: JSON | None = None
    client_mutation_id: str | None = None


@strawberry.input
class SampleAddInput:
    batch_id: relay.GlobalID
    label: str
    kind: str = "aliquot"
    payload: JSON | None = None
    client_mutation_id: str | None = None


@strawberry.input
class MeasurementRecordInput:
    sample_id: relay.GlobalID
    method: str
    repeat_type: str
    value: JSON
    metric: str | None = None
    value_type: str | None = None
    conditions: JSON | None = None
    pipeline_version: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class MeasurementReviewInput:
    measurement_id: relay.GlobalID
    decision: str
    note: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class MeasurementApplicabilityInput:
    measurement_id: relay.GlobalID
    applicable: bool
    note: str | None = None
    client_mutation_id: str | None = None


@strawberry.input
class MeasurementAmendInput:
    measurement_id: relay.GlobalID
    reason: str
    value: JSON
    source: str | None = None
    conditions: JSON | None = None
    client_mutation_id: str | None = None


@strawberry.type
class ExecutionResult:
    execution: LabExecution | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class BatchResult:
    batch: LabBatch | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class SampleResult:
    sample: LabSample | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class MeasurementResult:
    measurement: Measurement | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


def _lab_mutation(
    gql: GraphQLContext,
    *,
    operation: str,
    payload: dict[str, Any],
    fn: Callable[[], dict[str, str]],
) -> dict[str, str]:
    result = _mutate(gql, key=None, operation=operation, payload=payload, fn=fn)
    gql.db.commit()
    return result


def _execution_result(
    gql: GraphQLContext, result: dict[str, str], cmid: str | None
) -> ExecutionResult:
    row = gql.db.get(LabExecutionRow, uuid.UUID(result["id"]))
    return ExecutionResult(
        execution=LabExecution.from_row(row) if row else None,
        errors=[],
        client_mutation_id=cmid,
    )


def _execution_error(exc: DomainError, cmid: str | None) -> ExecutionResult:
    return ExecutionResult(execution=None, errors=[_err_payload(exc)], client_mutation_id=cmid)


def _measurement_error(exc: DomainError, cmid: str | None) -> MeasurementResult:
    return MeasurementResult(measurement=None, errors=[_err_payload(exc)], client_mutation_id=cmid)


@strawberry.type
class LabMeasurementsMutation:
    @strawberry.mutation
    def execution_open(self, info: strawberry.Info, input: ExecutionOpenInput) -> ExecutionResult:
        gql = gql_ctx(info)
        try:
            p_uuid = _gid_uuid(input.plan_id, "ExperimentPlan", "planId")

            def _do() -> dict[str, str]:
                row = LabMeasurementService(gql.db, gql.service_ctx()).open_execution(p_uuid)
                return {"id": str(row.id)}

            result = _lab_mutation(
                gql,
                operation="lab.execution_open",
                payload={"planId": str(p_uuid)},
                fn=_do,
            )
            return _execution_result(gql, result, input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return _execution_error(exc, input.client_mutation_id)

    @strawberry.mutation
    def execution_historical_import(
        self, info: strawberry.Info, input: ExecutionHistoricalInput
    ) -> ExecutionResult:
        """Historical record — marked, never retrospectively approved."""
        gql = gql_ctx(info)
        try:
            t_uuid = _gid_uuid(input.task_id, "Task", "taskId")

            def _do() -> dict[str, str]:
                row = LabMeasurementService(gql.db, gql.service_ctx()).import_historical(
                    t_uuid, payload=cast(dict[str, Any], input.payload)
                )
                return {"id": str(row.id)}

            result = _lab_mutation(
                gql,
                operation="lab.execution_historical",
                payload={"taskId": str(t_uuid)},
                fn=_do,
            )
            return _execution_result(gql, result, input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return _execution_error(exc, input.client_mutation_id)

    @strawberry.mutation
    def execution_close(self, info: strawberry.Info, input: ExecutionCloseInput) -> ExecutionResult:
        gql = gql_ctx(info)
        try:
            e_uuid = _gid_uuid(input.execution_id, "LabExecution", "executionId")

            def _do() -> dict[str, str]:
                row = LabMeasurementService(gql.db, gql.service_ctx()).close_execution(
                    e_uuid, status=input.status
                )
                return {"id": str(row.id)}

            result = _lab_mutation(
                gql,
                operation="lab.execution_close",
                payload={"executionId": str(e_uuid), "status": input.status},
                fn=_do,
            )
            return _execution_result(gql, result, input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return _execution_error(exc, input.client_mutation_id)

    @strawberry.mutation
    def actuals_record(self, info: strawberry.Info, input: ActualsRecordInput) -> ExecutionResult:
        gql = gql_ctx(info)
        try:
            e_uuid = _gid_uuid(input.execution_id, "LabExecution", "executionId")

            def _do() -> dict[str, str]:
                row = LabMeasurementService(gql.db, gql.service_ctx()).record_actuals(
                    e_uuid,
                    actual=cast(dict[str, Any] | None, input.actual),
                    deviations=cast(list[dict[str, Any]] | None, input.deviations),
                    observations=input.observations,
                )
                return {"id": str(row.id)}

            result = _lab_mutation(
                gql,
                operation="lab.actuals_record",
                payload={"executionId": str(e_uuid)},
                fn=_do,
            )
            return _execution_result(gql, result, input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return _execution_error(exc, input.client_mutation_id)

    @strawberry.mutation
    def batch_add(self, info: strawberry.Info, input: BatchAddInput) -> BatchResult:
        gql = gql_ctx(info)
        try:
            e_uuid = _gid_uuid(input.execution_id, "LabExecution", "executionId")

            def _do() -> dict[str, str]:
                row = LabMeasurementService(gql.db, gql.service_ctx()).add_batch(
                    e_uuid,
                    label=input.label,
                    payload=cast(dict[str, Any] | None, input.payload),
                )
                return {"id": str(row.id)}

            result = _lab_mutation(
                gql,
                operation="lab.batch_add",
                payload={"executionId": str(e_uuid), "label": input.label},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(LabBatchRow, uuid.UUID(result["id"]))
            return BatchResult(
                batch=LabBatch.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return BatchResult(
                batch=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def sample_add(self, info: strawberry.Info, input: SampleAddInput) -> SampleResult:
        gql = gql_ctx(info)
        try:
            b_uuid = _gid_uuid(input.batch_id, "LabBatch", "batchId")

            def _do() -> dict[str, str]:
                row = LabMeasurementService(gql.db, gql.service_ctx()).add_sample(
                    b_uuid,
                    label=input.label,
                    kind=input.kind,
                    payload=cast(dict[str, Any] | None, input.payload),
                )
                return {"id": str(row.id)}

            result = _lab_mutation(
                gql,
                operation="lab.sample_add",
                payload={"batchId": str(b_uuid), "label": input.label},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(LabSampleRow, uuid.UUID(result["id"]))
            return SampleResult(
                sample=LabSample.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return SampleResult(
                sample=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )

    @strawberry.mutation
    def measurement_record(
        self, info: strawberry.Info, input: MeasurementRecordInput
    ) -> MeasurementResult:
        gql = gql_ctx(info)
        try:
            s_uuid = _gid_uuid(input.sample_id, "LabSample", "sampleId")

            def _do() -> dict[str, str]:
                row = LabMeasurementService(gql.db, gql.service_ctx()).record_measurement(
                    s_uuid,
                    method=input.method,
                    repeat_type=input.repeat_type,
                    value=cast(dict[str, Any], input.value),
                    metric=input.metric,
                    value_type=input.value_type,
                    conditions=cast(dict[str, Any] | None, input.conditions),
                    pipeline_version=input.pipeline_version,
                )
                return {"id": str(row.id)}

            result = _lab_mutation(
                gql,
                operation="lab.measurement_record",
                payload={"sampleId": str(s_uuid), "method": input.method},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(MeasurementRow, uuid.UUID(result["id"]))
            return MeasurementResult(
                measurement=Measurement.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return _measurement_error(exc, input.client_mutation_id)

    @strawberry.mutation
    def measurement_review(
        self, info: strawberry.Info, input: MeasurementReviewInput
    ) -> MeasurementResult:
        gql = gql_ctx(info)
        try:
            m_uuid = _gid_uuid(input.measurement_id, "Measurement", "measurementId")

            def _do() -> dict[str, str]:
                row = LabMeasurementService(gql.db, gql.service_ctx()).review(
                    m_uuid, decision=input.decision, note=input.note
                )
                return {"id": str(row.id)}

            result = _lab_mutation(
                gql,
                operation="lab.measurement_review",
                payload={"measurementId": str(m_uuid), "decision": input.decision},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(MeasurementRow, uuid.UUID(result["id"]))
            return MeasurementResult(
                measurement=Measurement.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return _measurement_error(exc, input.client_mutation_id)

    @strawberry.mutation
    def measurement_applicability(
        self, info: strawberry.Info, input: MeasurementApplicabilityInput
    ) -> MeasurementResult:
        gql = gql_ctx(info)
        try:
            m_uuid = _gid_uuid(input.measurement_id, "Measurement", "measurementId")

            def _do() -> dict[str, str]:
                row = LabMeasurementService(gql.db, gql.service_ctx()).set_applicability(
                    m_uuid, applicable=input.applicable, note=input.note
                )
                return {"id": str(row.id)}

            result = _lab_mutation(
                gql,
                operation="lab.measurement_applicability",
                payload={"measurementId": str(m_uuid), "applicable": input.applicable},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(MeasurementRow, uuid.UUID(result["id"]))
            return MeasurementResult(
                measurement=Measurement.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return _measurement_error(exc, input.client_mutation_id)

    @strawberry.mutation
    def measurement_amend(
        self, info: strawberry.Info, input: MeasurementAmendInput
    ) -> MeasurementResult:
        gql = gql_ctx(info)
        try:
            m_uuid = _gid_uuid(input.measurement_id, "Measurement", "measurementId")

            def _do() -> dict[str, str]:
                LabMeasurementService(gql.db, gql.service_ctx()).amend(
                    m_uuid,
                    reason=input.reason,
                    source=input.source,
                    value=cast(dict[str, Any], input.value),
                    conditions=cast(dict[str, Any] | None, input.conditions),
                )
                return {"id": str(m_uuid)}

            result = _lab_mutation(
                gql,
                operation="lab.measurement_amend",
                payload={"measurementId": str(m_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(MeasurementRow, uuid.UUID(result["id"]))
            return MeasurementResult(
                measurement=Measurement.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return _measurement_error(exc, input.client_mutation_id)


@strawberry.input
class OptimizationCreateInput:
    task_id: relay.GlobalID
    definition: JSON
    idempotency_key: str
    client_mutation_id: str | None = None


@strawberry.enum
class OptimizationOperation(Enum):
    recommend = "recommend"
    observed = "observed"
    cancelled = "cancelled"
    failed = "failed"


@strawberry.input
class OptimizationCommandInput:
    campaign_id: relay.GlobalID
    expected_revision: int
    idempotency_key: str
    operation: OptimizationOperation
    batch_size: int = 1
    experiment_id: str | None = None
    measurement_id: relay.GlobalID | None = None
    snapshot_id: relay.GlobalID | None = None
    reason: str | None = None
    client_mutation_id: str | None = None


@strawberry.type
class OptimizationResult:
    task: Task | None
    errors: list[DomainErrorPayload]
    client_mutation_id: str | None


@strawberry.type
class OptimizationMutation:
    @strawberry.mutation
    def create(self, info: strawberry.Info, input: OptimizationCreateInput) -> OptimizationResult:
        from studio.domain.learning.optimization import OptimizationService

        gql = gql_ctx(info)
        try:
            if not isinstance(input.definition, dict):
                raise DomainError(ErrorCode.VALIDATION, "definition must be an object")
            row = OptimizationService(gql.db, gql.service_ctx(), gql.settings).create(
                _gid_uuid(input.task_id, "Task", "taskId"), input.definition, input.idempotency_key
            )
            gql.db.commit()
            task = gql.db.get(TaskRow, row.task_id)
            return OptimizationResult(
                task=Task.from_row(task) if task else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return OptimizationResult(
                task=None, errors=[_err_payload(exc)], client_mutation_id=input.client_mutation_id
            )

    @strawberry.mutation
    def command(self, info: strawberry.Info, input: OptimizationCommandInput) -> OptimizationResult:
        from studio.domain.learning.optimization import OptimizationService

        gql = gql_ctx(info)
        try:
            row = OptimizationService(gql.db, gql.service_ctx(), gql.settings).command(
                _gid_uuid(input.campaign_id, "OptimizationCampaign", "campaignId"),
                expected_revision=input.expected_revision,
                key=input.idempotency_key,
                operation=input.operation.value,
                batch_size=input.batch_size,
                experiment_id=input.experiment_id,
                measurement_id=_gid_uuid(input.measurement_id, "Measurement", "measurementId")
                if input.measurement_id
                else None,
                snapshot_id=_gid_uuid(input.snapshot_id, "DatasetSnapshot", "snapshotId")
                if input.snapshot_id
                else None,
                reason=input.reason,
            )
            gql.db.commit()
            task = gql.db.get(TaskRow, row.task_id)
            return OptimizationResult(
                task=Task.from_row(task) if task else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return OptimizationResult(
                task=None, errors=[_err_payload(exc)], client_mutation_id=input.client_mutation_id
            )


schema = strawberry.Schema(query=Query, mutation=Mutation)
