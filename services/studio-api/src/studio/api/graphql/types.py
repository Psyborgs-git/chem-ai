"""GraphQL object types (§5.1, §8.2).

Every scoped record is a ``relay.Node`` — the public ``id`` is a
canonical GlobalID (``<Type>:<uuid>``, base64). ``resolve_nodes``
always filters by the request's workspace: a foreign ID resolves to
``null``, never to content or an existence hint.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Literal, Self, overload

import strawberry
from chem_studio_policy.capabilities import CAP_READ_PROJECT
from sqlalchemy import select
from strawberry import relay
from strawberry.scalars import JSON
from strawberry.utils.await_maybe import AwaitableOrValue

from studio.api.graphql.context import gql_ctx
from studio.domain.tasks.service import unresolved_inputs
from studio.persistence.models import (
    CandidateRevision as CandidateRow,
)
from studio.persistence.models import (
    ClaimLink as ClaimLinkRow,
)
from studio.persistence.models import (
    ContextManifest as ContextManifestRow,
)
from studio.persistence.models import (
    EvidenceClaim as EvidenceClaimRow,
)
from studio.persistence.models import (
    ExperimentPlan as ExperimentPlanRow,
)
from studio.persistence.models import (
    ExtractedRecord as ExtractedRecordRow,
)
from studio.persistence.models import (
    ImportBatch as ImportBatchRow,
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
    MaterialGrade as MaterialGradeRow,
)
from studio.persistence.models import (
    MaterialIdentity as MaterialIdentityRow,
)
from studio.persistence.models import (
    Measurement as MeasurementRow,
)
from studio.persistence.models import (
    MeasurementAmendment as MeasurementAmendmentRow,
)
from studio.persistence.models import (
    Principal as PrincipalRow,
)
from studio.persistence.models import (
    Project as ProjectRow,
)
from studio.persistence.models import (
    ReferenceProduct as ReferenceProductRow,
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
    RunAttempt as RunAttemptRow,
)
from studio.persistence.models import (
    SessionMessage as SessionMessageRow,
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
    TaskSummary as TaskSummaryRow,
)
from studio.persistence.models import (
    Workspace as WorkspaceRow,
)


def _by_ids(info: strawberry.Info, model: type[Any], node_ids: Iterable[str]) -> dict[str, Any]:
    """Scoped batch lookup: rows outside the request workspace are
    excluded, so callers can never distinguish missing from foreign."""
    gql = gql_ctx(info)
    ctx = gql.service_ctx()
    ctx.require(CAP_READ_PROJECT)
    uuids: list[uuid.UUID] = []
    for nid in node_ids:
        try:
            uuids.append(uuid.UUID(nid))
        except ValueError:
            continue
    if not uuids:
        return {}
    rows = (
        gql.db.execute(
            select(model).where(model.workspace_id == ctx.workspace_id, model.id.in_(uuids))
        )
        .scalars()
        .all()
    )
    return {str(r.id): r for r in rows}


@strawberry.type
class User(relay.Node):
    id: relay.NodeID[str]
    display_name: str
    kind: str

    @classmethod
    def from_row(cls, row: PrincipalRow) -> Self:
        return cls(id=str(row.id), display_name=row.display_name, kind=row.kind)

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    # impl produces both overload shapes; mypy can't express that
    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, PrincipalRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class Workspace(relay.Node):
    id: relay.NodeID[str]
    slug: str
    display_name: str

    @classmethod
    def from_row(cls, row: WorkspaceRow) -> Self:
        return cls(id=str(row.id), slug=row.slug, display_name=row.display_name)

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    # impl produces both overload shapes; mypy can't express that
    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, WorkspaceRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class Task(relay.Node):
    id: relay.NodeID[str]
    title: str
    mode: str
    workflow_state: str
    target_kind: str
    objective: str | None
    closure_decision: str | None
    evaluation_cycle: int
    unresolved_inputs: list[str]
    created_at: datetime

    @classmethod
    def from_row(cls, row: TaskRow) -> Self:
        return cls(
            id=str(row.id),
            title=row.title,
            mode=row.mode,
            workflow_state=row.workflow_state,
            target_kind=row.target_kind,
            objective=row.objective,
            closure_decision=row.closure_decision,
            evaluation_cycle=row.evaluation_cycle,
            unresolved_inputs=unresolved_inputs(row),
            created_at=row.created_at,
        )

    @strawberry.field
    async def project(self, info: strawberry.Info) -> Project | None:
        gql = gql_ctx(info)
        row = gql.db.get(TaskRow, uuid.UUID(self.id))
        if row is None:
            return None
        loaded = await gql.loaders().projects.load(str(row.project_id))
        return Project.from_row(loaded) if loaded else None

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    # impl produces both overload shapes; mypy can't express that
    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, TaskRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class Project(relay.Node):
    id: relay.NodeID[str]
    slug: str
    name: str
    status: str
    description: str | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: ProjectRow) -> Self:
        return cls(
            id=str(row.id),
            slug=row.slug,
            name=row.name,
            status=row.status,
            description=row.description,
            created_at=row.created_at,
        )

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    # impl produces both overload shapes; mypy can't express that
    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, ProjectRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class ContractRevision(relay.Node):
    id: relay.NodeID[str]
    revision: int
    status: str
    content_hash: str
    created_at: datetime

    @classmethod
    def from_row(cls, row: ContractRow) -> Self:
        return cls(
            id=str(row.id),
            revision=row.revision,
            status=row.status,
            content_hash=row.content_hash,
            created_at=row.created_at,
        )

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    # impl produces both overload shapes; mypy can't express that
    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, ContractRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class Decision(relay.Node):
    """A recorded task decision (closure/reopen/review return). The
    payload keeps the contract revision and evaluation cycle the
    decision was made under (§7.1)."""

    id: relay.NodeID[str]
    kind: str
    payload: JSON
    created_at: datetime

    @classmethod
    def from_row(cls, row: DecisionRow) -> Self:
        return cls(
            id=str(row.id), kind=row.kind, payload=JSON(row.payload), created_at=row.created_at
        )

    @strawberry.field
    async def decided_by(self, info: strawberry.Info) -> User | None:
        gql = gql_ctx(info)
        row = gql.db.get(DecisionRow, uuid.UUID(self.id))
        if row is None or row.decided_by is None:
            return None
        loaded = await gql.loaders().principals.load(str(row.decided_by))
        return User.from_row(loaded) if loaded else None

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    # impl produces both overload shapes; mypy can't express that
    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, DecisionRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class MaterialIdentity(relay.Node):
    """Registry identity (§5): structure status is exposed so clients
    can see *why* a structure-required tool is blocked."""

    id: relay.NodeID[str]
    kind: str
    name: str
    structure_status: str
    evidence_status: str
    identifiers: JSON
    aliases: JSON
    created_at: datetime

    @classmethod
    def from_row(cls, row: MaterialIdentityRow) -> Self:
        return cls(
            id=str(row.id),
            kind=row.kind,
            name=row.name,
            structure_status=row.structure_status,
            evidence_status=row.evidence_status,
            identifiers=JSON(row.identifiers),
            aliases=JSON(row.aliases),
            created_at=row.created_at,
        )

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    # impl produces both overload shapes; mypy can't express that
    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, MaterialIdentityRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class MaterialGrade(relay.Node):
    id: relay.NodeID[str]
    supplier: str
    grade_name: str
    active_content: JSON | None
    specifications: JSON
    reconciled_into: relay.GlobalID | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: MaterialGradeRow) -> Self:
        return cls(
            id=str(row.id),
            supplier=row.supplier,
            grade_name=row.grade_name,
            active_content=JSON(row.active_content) if row.active_content else None,
            specifications=JSON(row.specifications),
            reconciled_into=(
                relay.GlobalID("MaterialGrade", str(row.reconciled_into))
                if row.reconciled_into
                else None
            ),
            created_at=row.created_at,
        )

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    # impl produces both overload shapes; mypy can't express that
    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, MaterialGradeRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class ReferenceProduct(relay.Node):
    """Purchased/reference product. `compositionKnowledge` advertises
    honesty: 'unknown' means no ingredient list exists."""

    id: relay.NodeID[str]
    name: str
    supplier: str | None
    category: str | None
    composition_knowledge: str
    aliases: JSON
    created_at: datetime

    @classmethod
    def from_row(cls, row: ReferenceProductRow) -> Self:
        return cls(
            id=str(row.id),
            name=row.name,
            supplier=row.supplier,
            category=row.category,
            composition_knowledge=row.composition_knowledge,
            aliases=JSON(row.aliases),
            created_at=row.created_at,
        )

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    # impl produces both overload shapes; mypy can't express that
    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, ReferenceProductRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class ReferenceProductRevision(relay.Node):
    id: relay.NodeID[str]
    revision: int
    status: str
    content_hash: str
    created_at: datetime

    @classmethod
    def from_row(cls, row: RefRevRow) -> Self:
        return cls(
            id=str(row.id),
            revision=row.revision,
            status=row.status,
            content_hash=row.content_hash,
            created_at=row.created_at,
        )

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    # impl produces both overload shapes; mypy can't express that
    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, RefRevRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class CandidateRevision(relay.Node):
    """A candidate content revision (§5, §7.2): immutable once
    accepted; eligibility is a separate assessment axis exposed
    alongside — never conflated with status."""

    id: relay.NodeID[str]
    revision: int
    status: str
    eligibility: str
    entity_kind: str
    hypothesis: str | None
    payload: JSON
    parent_revision_id: str | None
    entity_revision_id: str | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: CandidateRow) -> Self:
        return cls(
            id=str(row.id),
            revision=row.revision,
            status=row.status,
            eligibility=row.eligibility,
            entity_kind=row.entity_kind,
            hypothesis=row.hypothesis,
            payload=JSON(row.payload),
            parent_revision_id=(str(row.parent_revision_id) if row.parent_revision_id else None),
            entity_revision_id=(str(row.entity_revision_id) if row.entity_revision_id else None),
            created_at=row.created_at,
        )

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    # impl produces both overload shapes; mypy can't express that
    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, CandidateRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


# ------------------------------------------------------------------
# CS-0301/CS-0302 — ingestion batches, extracted records, claims


@strawberry.type
class ImportBatch(relay.Node):
    """One quarantined ingestion run — parser version and dedup
    identity are part of the record's provenance."""

    id: relay.NodeID[str]
    original_name: str
    detected_type: str
    parser_name: str
    parser_version: str
    source_revision: int
    status: str
    record_count: int
    findings: JSON
    created_at: datetime

    @classmethod
    def from_row(cls, row: ImportBatchRow) -> Self:
        return cls(
            id=str(row.id),
            original_name=row.original_name,
            detected_type=row.detected_type,
            parser_name=row.parser_name,
            parser_version=row.parser_version,
            source_revision=row.source_revision,
            status=row.status,
            record_count=row.record_count,
            findings=JSON(row.findings),
            created_at=row.created_at,
        )

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, ImportBatchRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class ExtractedRecord(relay.Node):
    """A proposed extraction — flags carry every ambiguity the parser
    detected; the record is never accepted automatically."""

    id: relay.NodeID[str]
    batch_id: str
    kind: str
    locator: JSON
    original_text: str
    payload: JSON | None
    flags: list[str]
    confidence: float
    status: str
    created_at: datetime

    @classmethod
    def from_row(cls, row: ExtractedRecordRow) -> Self:
        return cls(
            id=str(row.id),
            batch_id=str(row.batch_id),
            kind=row.kind,
            locator=JSON(row.locator),
            original_text=row.original_text,
            payload=JSON(row.payload) if row.payload is not None else None,
            flags=list(row.flags),
            confidence=row.confidence,
            status=row.status,
            created_at=row.created_at,
        )

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, ExtractedRecordRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class EvidenceClaim(relay.Node):
    """A reviewed claim — kind distinguishes document claims from
    inferred suggestions and measured outcomes; locator + original
    text always travel with the claim."""

    id: relay.NodeID[str]
    kind: str
    status: str
    subject: JSON
    statement: JSON
    locator: JSON | None
    original_text: str | None
    conditions: JSON | None
    source_record_id: str | None
    reviewed_at: datetime | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: EvidenceClaimRow) -> Self:
        return cls(
            id=str(row.id),
            kind=row.kind,
            status=row.status,
            subject=JSON(row.subject),
            statement=JSON(row.statement),
            locator=JSON(row.locator) if row.locator is not None else None,
            original_text=row.original_text,
            conditions=JSON(row.conditions) if row.conditions is not None else None,
            source_record_id=(str(row.source_record_id) if row.source_record_id else None),
            reviewed_at=row.reviewed_at,
            created_at=row.created_at,
        )

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, EvidenceClaimRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class ClaimLink:
    """A support/contradiction edge — plain object, not a Node; the
    claims it joins are the addressable things."""

    from_claim_id: str
    to_claim_id: str
    relation: str
    note: str | None

    @classmethod
    def from_row(cls, row: ClaimLinkRow) -> Self:
        return cls(
            from_claim_id=str(row.from_claim_id),
            to_claim_id=str(row.to_claim_id),
            relation=row.relation,
            note=row.note,
        )


# ------------------------------------------------------------------
# CS-0304 — task memory: sessions, manifests, messages, questions,
# derived summaries (§10.1)


@strawberry.type
class ContextManifest:
    """The token-budgeted context a session opened with. ``items`` is
    the selected context; ``omitted`` discloses what the budget
    excluded — a dropped piece of evidence is never silent (§10.1)."""

    id: str
    compiler_version: str
    token_budget: int
    token_estimate: int
    over_budget: bool
    items: JSON
    omitted: JSON
    warnings: JSON
    created_at: datetime

    @classmethod
    def from_row(cls, row: ContextManifestRow) -> Self:
        return cls(
            id=str(row.id),
            compiler_version=row.compiler_version,
            token_budget=row.token_budget,
            token_estimate=row.token_estimate,
            over_budget=row.over_budget,
            items=JSON(row.items),
            omitted=JSON(row.omitted),
            warnings=JSON(row.warnings),
            created_at=row.created_at,
        )


@strawberry.type
class ResearchSession(relay.Node):
    """A research session anchored to the manifest + contract revision
    that existed at its start (§11.1)."""

    id: relay.NodeID[str]
    status: str
    start_contract_revision_id: str | None
    end_snapshot: JSON | None
    created_at: datetime
    ended_at: datetime | None

    @classmethod
    def from_row(cls, row: ResearchSessionRow) -> Self:
        return cls(
            id=str(row.id),
            status=row.status,
            start_contract_revision_id=(
                str(row.start_contract_revision_id) if row.start_contract_revision_id else None
            ),
            end_snapshot=JSON(row.end_snapshot) if row.end_snapshot is not None else None,
            created_at=row.created_at,
            ended_at=row.ended_at,
        )

    @strawberry.field
    async def start_manifest(self, info: strawberry.Info) -> ContextManifest | None:
        gql = gql_ctx(info)
        row = gql.db.get(ResearchSessionRow, uuid.UUID(self.id))
        if row is None or row.start_manifest_id is None:
            return None
        manifest = gql.db.get(ContextManifestRow, row.start_manifest_id)
        return ContextManifest.from_row(manifest) if manifest else None

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, ResearchSessionRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class SessionMessage:
    """One session message with structured refs to canonical state."""

    id: str
    role: str
    kind: str
    content: str
    refs: JSON
    created_at: datetime

    @classmethod
    def from_row(cls, row: SessionMessageRow) -> Self:
        return cls(
            id=str(row.id),
            role=row.role,
            kind=row.kind,
            content=row.content,
            refs=JSON(row.refs),
            created_at=row.created_at,
        )


@strawberry.type
class TaskQuestion(relay.Node):
    """An open/resolved question; blocking ones are pinned into every
    session manifest."""

    id: relay.NodeID[str]
    question: str
    blocking: bool
    status: str
    resolution: str | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: TaskQuestionRow) -> Self:
        return cls(
            id=str(row.id),
            question=row.question,
            blocking=row.blocking,
            status=row.status,
            resolution=row.resolution,
            created_at=row.created_at,
        )

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, TaskQuestionRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class TaskSummary:
    """A derived navigation aid — never canonical state. ``stale`` is
    computed at read time against the current contract revision and
    source states."""

    id: str
    body: str
    source_ids: JSON
    coverage: JSON
    generator: str
    contract_revision_id: str | None
    stale: bool
    created_at: datetime

    @classmethod
    def from_row(cls, row: TaskSummaryRow, *, stale: bool) -> Self:
        return cls(
            id=str(row.id),
            body=row.body,
            source_ids=JSON(row.source_ids),
            coverage=JSON(row.coverage),
            generator=row.generator,
            contract_revision_id=(
                str(row.contract_revision_id) if row.contract_revision_id else None
            ),
            stale=stale,
            created_at=row.created_at,
        )


@strawberry.type(name="RunAttempt")
class RunAttemptNode(relay.Node):
    id: relay.NodeID[str]
    status: str
    queue: str
    worker_id: str | None
    attempt_number: int
    enqueued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: JSON | None

    @classmethod
    def from_row(cls, row: RunAttemptRow) -> Self:
        return cls(
            id=str(row.id),
            status=row.status,
            queue=row.queue_name,
            worker_id=row.worker_id,
            attempt_number=row.attempt_number,
            enqueued_at=row.enqueued_at,
            started_at=row.started_at,
            finished_at=row.finished_at,
            error=JSON(row.error) if row.error is not None else None,
        )

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, RunAttemptRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type(name="Run")
class RunNode(relay.Node):
    id: relay.NodeID[str]
    kind: str
    status: str
    attempt_count: int
    max_attempts: int
    queued_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    cancel_requested_at: datetime | None
    deadline_at: datetime | None
    error: JSON | None
    result_summary: JSON | None

    @classmethod
    def from_row(cls, row: RunRow) -> Self:
        return cls(
            id=str(row.id),
            kind=row.kind,
            status=row.status,
            attempt_count=row.attempt_count,
            max_attempts=row.max_attempts,
            queued_at=row.queued_at,
            started_at=row.started_at,
            finished_at=row.finished_at,
            cancel_requested_at=row.cancel_requested_at,
            deadline_at=row.deadline_at,
            error=JSON(row.error) if row.error is not None else None,
            result_summary=JSON(row.result_summary) if row.result_summary is not None else None,
        )

    @strawberry.field
    def attempts(self, info: strawberry.Info) -> list[RunAttemptNode]:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_READ_PROJECT)
        rows = (
            gql.db.execute(
                select(RunAttemptRow)
                .where(
                    RunAttemptRow.workspace_id == ctx.workspace_id,
                    RunAttemptRow.run_id == uuid.UUID(self.id),
                )
                .order_by(RunAttemptRow.attempt_number)
            )
            .scalars()
            .all()
        )
        return [RunAttemptNode.from_row(r) for r in rows]

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, RunRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class ExperimentPlan(relay.Node):
    """Experiment plan bound to immutable revisions (§14.1, CS-0501)."""

    id: relay.NodeID[str]
    task_id: str
    title: str
    status: str
    content_digest: str
    blockers: JSON
    payload: JSON
    approval_id: str | None
    packet: JSON | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: ExperimentPlanRow) -> Self:
        return cls(
            id=str(row.id),
            task_id=str(row.task_id),
            title=row.title,
            status=row.status,
            content_digest=row.content_digest,
            blockers=JSON(row.blockers),
            payload=JSON(row.payload),
            approval_id=str(row.approval_id) if row.approval_id else None,
            packet=JSON(row.packet) if row.packet is not None else None,
            created_at=row.created_at,
        )

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, ExperimentPlanRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class Measurement(relay.Node):
    """One reading on one sample (§6.3, §14.2, CS-0502)."""

    id: relay.NodeID[str]
    sample_id: str
    method: str
    repeat_type: str
    metric: str | None
    value_type: str
    value: JSON
    conditions: JSON
    applicable: bool
    applicability_note: str | None
    status: str
    review_note: str | None
    pipeline_version: str | None
    superseded_by: str | None
    created_at: datetime

    @strawberry.field
    def amendments(self, info: strawberry.Info) -> JSON:
        """Amendment chain — corrected values with reason/source; the
        original row stays immutable (§14.2, AT-0502-3)."""
        gql = gql_ctx(info)
        gql.service_ctx().require(CAP_READ_PROJECT)
        rows = (
            gql.db.execute(
                select(MeasurementAmendmentRow)
                .where(
                    MeasurementAmendmentRow.workspace_id == gql.service_ctx().workspace_id,
                    MeasurementAmendmentRow.measurement_id == uuid.UUID(self.id),
                )
                .order_by(MeasurementAmendmentRow.created_at)
            )
            .scalars()
            .all()
        )
        return JSON(
            [
                {
                    "id": str(a.id),
                    "reason": a.reason,
                    "source": a.source,
                    "value": a.value,
                    "createdAt": a.created_at.isoformat(),
                }
                for a in rows
            ]
        )

    @classmethod
    def from_row(cls, row: MeasurementRow) -> Self:
        return cls(
            id=str(row.id),
            sample_id=str(row.sample_id),
            method=row.method,
            repeat_type=row.repeat_type,
            metric=row.metric,
            value_type=row.value_type,
            value=JSON(row.value),
            conditions=JSON(row.conditions),
            applicable=row.applicable,
            applicability_note=row.applicability_note,
            status=row.status,
            review_note=row.review_note,
            pipeline_version=row.pipeline_version,
            superseded_by=str(row.superseded_by) if row.superseded_by else None,
            created_at=row.created_at,
        )

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, MeasurementRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class LabSample(relay.Node):
    id: relay.NodeID[str]
    batch_id: str
    label: str
    kind: str
    payload: JSON
    created_at: datetime

    @classmethod
    def from_row(cls, row: LabSampleRow) -> Self:
        return cls(
            id=str(row.id),
            batch_id=str(row.batch_id),
            label=row.label,
            kind=row.kind,
            payload=JSON(row.payload),
            created_at=row.created_at,
        )

    @strawberry.field
    def measurements(self, info: strawberry.Info) -> list[Measurement]:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_READ_PROJECT)
        rows = (
            gql.db.execute(
                select(MeasurementRow)
                .where(
                    MeasurementRow.workspace_id == ctx.workspace_id,
                    MeasurementRow.sample_id == uuid.UUID(self.id),
                )
                .order_by(MeasurementRow.created_at, MeasurementRow.id)
            )
            .scalars()
            .all()
        )
        return [Measurement.from_row(r) for r in rows]

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, LabSampleRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class LabBatch(relay.Node):
    id: relay.NodeID[str]
    execution_id: str
    label: str
    payload: JSON
    created_at: datetime

    @classmethod
    def from_row(cls, row: LabBatchRow) -> Self:
        return cls(
            id=str(row.id),
            execution_id=str(row.execution_id),
            label=row.label,
            payload=JSON(row.payload),
            created_at=row.created_at,
        )

    @strawberry.field
    def samples(self, info: strawberry.Info) -> list[LabSample]:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_READ_PROJECT)
        rows = (
            gql.db.execute(
                select(LabSampleRow)
                .where(
                    LabSampleRow.workspace_id == ctx.workspace_id,
                    LabSampleRow.batch_id == uuid.UUID(self.id),
                )
                .order_by(LabSampleRow.created_at, LabSampleRow.id)
            )
            .scalars()
            .all()
        )
        return [LabSample.from_row(r) for r in rows]

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, LabBatchRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]


@strawberry.type
class LabExecution(relay.Node):
    id: relay.NodeID[str]
    plan_id: str | None
    status: str
    historical: bool
    actual: JSON
    deviations: JSON
    observations: str | None
    closed_at: datetime | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: LabExecutionRow) -> Self:
        return cls(
            id=str(row.id),
            plan_id=str(row.plan_id) if row.plan_id else None,
            status=row.status,
            historical=row.historical,
            actual=JSON(row.actual),
            deviations=JSON(row.deviations),
            observations=row.observations,
            closed_at=row.closed_at,
            created_at=row.created_at,
        )

    @strawberry.field
    def batches(self, info: strawberry.Info) -> list[LabBatch]:
        gql = gql_ctx(info)
        ctx = gql.service_ctx()
        ctx.require(CAP_READ_PROJECT)
        rows = (
            gql.db.execute(
                select(LabBatchRow)
                .where(
                    LabBatchRow.workspace_id == ctx.workspace_id,
                    LabBatchRow.execution_id == uuid.UUID(self.id),
                )
                .order_by(LabBatchRow.created_at, LabBatchRow.id)
            )
            .scalars()
            .all()
        )
        return [LabBatch.from_row(r) for r in rows]

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[True],
    ) -> AwaitableOrValue[Iterable[Self]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: Literal[False] = ...,
    ) -> AwaitableOrValue[Iterable[Self | None]]: ...

    @overload
    @classmethod
    def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool
    ) -> AwaitableOrValue[Iterable[Self]] | AwaitableOrValue[Iterable[Self | None]]: ...

    @classmethod  # type: ignore[misc]
    def resolve_nodes(
        cls,
        *,
        info: strawberry.Info,
        node_ids: Iterable[str],
        required: bool = False,
    ) -> list[Self | None]:
        ids = list(node_ids)
        rows = _by_ids(info, LabExecutionRow, ids)
        return [cls.from_row(rows[nid]) if nid in rows else None for nid in ids]
