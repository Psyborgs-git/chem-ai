"""Core persistence models (handoff §5, §26.2 order).

Scope + principals + projects + task/contract revisions. Materials,
formulations, runs, lab, datasets and exports arrive in their own
migrations in dependency order.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from studio.persistence.base import (
    Base,
    OptimisticLock,
    Timestamped,
    UUIDPrimaryKey,
    WorkspaceScoped,
)

# ---------------------------------------------------------------- scope


class Workspace(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "workspaces"

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)


class Principal(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped, OptimisticLock):
    """A user, agent or service identity inside one workspace (§21.1)."""

    __tablename__ = "principals"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_principals_scope_id"),
        UniqueConstraint("workspace_id", "login", name="uq_principals_scope_login"),
        CheckConstraint("kind IN ('user','agent','service')", name="kind"),
    )

    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    login: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    credential_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PrincipalCapability(Base):
    """Granted capability assignments (§21.1). Capability vocabulary is
    constrained text, not a PostgreSQL enum (§5.3)."""

    __tablename__ = "principal_capabilities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "principal_id"],
            ["principals.workspace_id", "principals.id"],
            ondelete="CASCADE",
            name="fk_principal_capabilities_scope",
        ),
        UniqueConstraint(
            "workspace_id",
            "principal_id",
            "capability",
            "scope_ref",
            name="uq_principal_capabilities_grant",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    principal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    # Optional narrowing reference (e.g. a project id); NULL = workspace-wide.
    scope_ref: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthSession(Base, UUIDPrimaryKey, WorkspaceScoped):
    """Opaque-token session; only the sha256 hash is stored (§21.2)."""

    __tablename__ = "auth_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "principal_id"],
            ["principals.workspace_id", "principals.id"],
            ondelete="CASCADE",
            name="fk_auth_sessions_scope_principal",
        ),
        UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
        Index(
            "ix_auth_sessions_principal",
            "workspace_id",
            "principal_id",
            "expires_at",
        ),
    )

    principal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Project(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped, OptimisticLock):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_projects_scope_id"),
        Index(
            "ix_projects_scope_list",
            "workspace_id",
            "created_at",
            "id",
        ),
    )

    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="active",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    tasks: Mapped[list[ResearchTask]] = relationship(back_populates="project")


# ------------------------------------------------------- tasks + contracts

TASK_STATES = (
    "draft",
    "active",
    "paused",
    "awaiting_review",
    "closed",
    "cancelled",
)

TASK_MODES = ("improve", "match_reference", "discover")

TASK_CLOSURES = (
    "supported_success",
    "supported_failure",
    "inconclusive",
    "stopped",
)


class ResearchTask(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped, OptimisticLock):
    __tablename__ = "research_tasks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "project_id"],
            ["projects.workspace_id", "projects.id"],
            name="fk_research_tasks_scope_project",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "reviewer_id"],
            ["principals.workspace_id", "principals.id"],
            name="fk_research_tasks_scope_reviewer",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "owner_id"],
            ["principals.workspace_id", "principals.id"],
            name="fk_research_tasks_scope_owner",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_research_tasks_scope_id"),
        CheckConstraint(f"workflow_state IN {TASK_STATES!r}", name="workflow_state"),
        CheckConstraint(f"mode IN {TASK_MODES!r}", name="mode"),
        CheckConstraint(
            f"closure_decision IS NULL OR closure_decision IN {TASK_CLOSURES!r}",
            name="closure_decision",
        ),
        Index("ix_research_tasks_scope_list", "workspace_id", "project_id", "created_at", "id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Mode-scoped inputs kept faithfully as provided (§11): unknowns
    # stay unknown — nothing is fabricated or defaulted into them.
    mode_inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    workflow_state: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    closure_decision: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # Increments on each reopen; evaluations/decisions tag the cycle
    # they belong to so a reopened task never rewrites prior packets.
    evaluation_cycle: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_contract_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    project: Mapped[Project] = relationship(back_populates="tasks")
    contract_revisions: Mapped[list[SuccessContractRevision]] = relationship(back_populates="task")


REVISION_STATUSES_CONTRACT = ("draft", "frozen", "superseded")


class SuccessContractRevision(Base, UUIDPrimaryKey):
    """Versioned, immutable-once-frozen success contract (§5.2, §7.4)."""

    __tablename__ = "success_contract_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["research_tasks.workspace_id", "research_tasks.id"],
            name="fk_success_contract_revisions_scope_task",
        ),
        UniqueConstraint("task_id", "revision", name="uq_contract_task_revision"),
        CheckConstraint(f"status IN {REVISION_STATUSES_CONTRACT!r}", name="status"),
        Index(
            "ix_success_contract_revisions_task",
            "workspace_id",
            "task_id",
            "revision",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    task: Mapped[ResearchTask] = relationship(back_populates="contract_revisions")


DECISION_KINDS = ("closure", "reopen", "review_return", "state_change")


class TaskDecision(Base, UUIDPrimaryKey, WorkspaceScoped):
    """Recorded task decision (§7.1): closures keep the exact contract
    revision they were made under, reopens keep the prior packet — a
    later contract never rewrites an earlier signed decision."""

    __tablename__ = "task_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["research_tasks.workspace_id", "research_tasks.id"],
            name="fk_task_decisions_scope_task",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decided_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_task_decisions_scope_decider",
        ),
        CheckConstraint(f"kind IN {DECISION_KINDS!r}", name="kind"),
        Index("ix_task_decisions_task", "workspace_id", "task_id", "created_at", "id"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # e.g. {"closureDecision": ..., "contractRevisionId": ...,
    #       "evaluationCycle": ..., "reason": ...}
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ------------------------------------------------------------- artifacts

ARTIFACT_UPLOAD_STATES = ("receiving", "committed", "aborted")
ARTIFACT_REVIEW_STATES = (
    "quarantined",
    "parsed",
    "needs_review",
    "accepted",
    "rejected",
    "superseded",
    "revoked",
)
ARTIFACT_CLASSIFICATIONS = ("internal", "confidential", "restricted")
ARTIFACT_SOURCE_KINDS = ("upload", "import", "derived")


class Artifact(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped, OptimisticLock):
    """Private blob record (§5.2). Bytes live in the vault, never in the
    DB; the storage key is opaque and workspace-scoped. Rights decisions
    are per-use (§9.4): retrieval/extraction/training/export/
    redistribution each start as 'unknown' (quarantine default)."""

    __tablename__ = "artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "created_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_artifacts_scope_creator",
        ),
        UniqueConstraint("workspace_id", "storage_key", name="uq_artifacts_scope_key"),
        CheckConstraint(f"upload_state IN {ARTIFACT_UPLOAD_STATES!r}", name="upload_state"),
        CheckConstraint(f"review_state IN {ARTIFACT_REVIEW_STATES!r}", name="review_state"),
        CheckConstraint(f"classification IN {ARTIFACT_CLASSIFICATIONS!r}", name="classification"),
        CheckConstraint(f"source_kind IN {ARTIFACT_SOURCE_KINDS!r}", name="source_kind"),
        Index("ix_artifacts_scope_list", "workspace_id", "created_at", "id"),
        Index("ix_artifacts_checksum", "workspace_id", "checksum_sha256"),
    )

    # Opaque vault-relative key (e.g. "ab/abc123…"); never a client path.
    storage_key: Mapped[str] = mapped_column(String(160), nullable=False)
    media_type: Mapped[str] = mapped_column(String(200), nullable=False)
    byte_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    declared_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="upload")
    classification: Mapped[str] = mapped_column(String(16), nullable=False, default="confidential")
    review_state: Mapped[str] = mapped_column(String(16), nullable=False, default="quarantined")
    upload_state: Mapped[str] = mapped_column(String(16), nullable=False, default="receiving")
    rights: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {
            "retrieval": "unknown",
            "extraction": "unknown",
            "training": "unknown",
            "export": "unknown",
            "redistribution": "unknown",
        },
    )
    parser_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    access_scope: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    retention: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Downstream lineage (§17.5): the source artifacts this artifact
    # derives from (dataset built from documents, report quoting
    # chunks...). Revoking a source marks these for re-review — it
    # never implies the derivation "forgot" the source.
    source_artifact_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ------------------------------------------------- commands + outbox + audit

IDEMPOTENCY_STATUSES = ("succeeded", "failed")


class IdempotencyRecord(Base, UUIDPrimaryKey, WorkspaceScoped):
    """Command outcome stored in the same transaction as the domain
    change (§7.4): same key + same payload replays the original result;
    same key + different payload is IDEMPOTENCY_MISMATCH."""

    __tablename__ = "idempotency_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "principal_id"],
            ["principals.workspace_id", "principals.id"],
            name="fk_idempotency_scope_principal",
        ),
        UniqueConstraint(
            "workspace_id",
            "operation",
            "key",
            name="uq_idempotency_scope_op_key",
        ),
        CheckConstraint(f"status IN {IDEMPOTENCY_STATUSES!r}", name="status"),
    )

    principal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    operation: Mapped[str] = mapped_column(String(120), nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="succeeded")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutboxEvent(Base, UUIDPrimaryKey, WorkspaceScoped):
    """Transactional outbox row (§7.4): enqueued in the same transaction
    as the state change; delivered at least once."""

    __tablename__ = "outbox_events"
    __table_args__ = (Index("ix_outbox_events_pending", "workspace_id", "created_at", "id"),)

    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    command_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    seq: Mapped[int] = mapped_column(
        BigInteger,
        server_default=text("nextval('outbox_events_seq_seq'::regclass)"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OutboxDelivery(Base):
    """Consumer dedupe ledger (§7.4): at-least-once delivery means a
    consumer records (event, consumer) exactly once."""

    __tablename__ = "outbox_deliveries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id"],
            ["outbox_events.id"],
            ondelete="CASCADE",
            name="fk_outbox_deliveries_event",
        ),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    consumer: Mapped[str] = mapped_column(String(80), primary_key=True)
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


APPROVAL_DECISIONS = ("approved", "rejected")


class Approval(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped):
    """Approval envelope (§7.4): binds principal, action, the exact
    bound-input digest, contract/method/policy versions, envelope and
    expiry. Any bound change invalidates — never a mutable task id."""

    __tablename__ = "approvals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "decided_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_approvals_scope_decider",
        ),
        CheckConstraint(f"decision IN {APPROVAL_DECISIONS!r}", name="decision"),
        Index("ix_approvals_scope_action", "workspace_id", "action", "created_at"),
    )

    action: Mapped[str] = mapped_column(String(80), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    decided_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # sha256 over the canonical bound-input document.
    bound_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    bound_inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    envelope: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base, UUIDPrimaryKey, WorkspaceScoped):
    """Minimal audit metadata (§21.3): actor, action, target, timestamp
    — never prompts, formulas, spectra or document payloads."""

    __tablename__ = "audit_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "actor_id"],
            ["principals.workspace_id", "principals.id"],
            name="fk_audit_scope_actor",
        ),
        Index("ix_audit_events_scope_list", "workspace_id", "created_at", "id"),
        Index("ix_audit_events_target", "workspace_id", "target_type", "target_id"),
    )

    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ------------------------------------------------ materials registry (§5)

MATERIAL_KINDS = (
    "defined_molecule",
    "polymer",
    "commercial_mixture",
    "substance_class",
    "unknown",
)

IDENTITY_EVIDENCE_STATUSES = ("unverified", "documented", "reviewed")

# A structure is only usable by structure-required tools when its
# provenance is reviewed — a proposed match never unblocks (AT-0203-3).
STRUCTURE_STATUSES = ("none", "unreviewed", "reviewed")

MATCH_STATUSES = ("proposed", "accepted", "rejected")

COMPOSITION_KNOWLEDGE = ("known", "partial", "unknown")

CONFIDENTIALITY = ("public", "internal", "confidential")


class MaterialIdentity(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped, OptimisticLock):
    """A material as *identified* — molecule, polymer, class, mixture,
    or honestly unknown (§5). Identifiers keep their sources; aliases
    are reviewable proposals; ambiguous candidate matches are kept."""

    __tablename__ = "material_identities"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_material_identities_scope_id"),
        CheckConstraint(f"kind IN {MATERIAL_KINDS!r}", name="kind"),
        CheckConstraint(
            f"evidence_status IN {IDENTITY_EVIDENCE_STATUSES!r}", name="evidence_status"
        ),
        CheckConstraint(f"structure_status IN {STRUCTURE_STATUSES!r}", name="structure_status"),
        CheckConstraint(f"confidentiality IN {CONFIDENTIALITY!r}", name="confidentiality"),
        Index("ix_material_identities_scope_list", "workspace_id", "created_at", "id"),
    )

    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    # [{"scheme": "cas"|"inchi_key"|"supplier_sku"|..., "value": str,
    #   "source": str}] — sources are part of the identifier.
    identifiers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    structure: Mapped[str | None] = mapped_column(Text, nullable=True)
    structure_format: Mapped[str | None] = mapped_column(
        String(24), nullable=True
    )  # smiles | inchi | molfile
    structure_status: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    aliases: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    confidentiality: Mapped[str] = mapped_column(String(24), nullable=False, default="internal")
    evidence_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unverified")


class IdentityMatch(Base, UUIDPrimaryKey, WorkspaceScoped):
    """A *proposed* equivalence between two identities (§5): proposals
    are created by imports/tools; only a human review accepts one."""

    __tablename__ = "identity_matches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "source_identity_id"],
            ["material_identities.workspace_id", "material_identities.id"],
            name="fk_identity_matches_scope_source",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "candidate_identity_id"],
            ["material_identities.workspace_id", "material_identities.id"],
            name="fk_identity_matches_scope_candidate",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "reviewed_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_identity_matches_scope_reviewer",
        ),
        CheckConstraint(f"status IN {MATCH_STATUSES!r}", name="status"),
        Index("ix_identity_matches_scope_list", "workspace_id", "created_at", "id"),
    )

    source_identity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    candidate_identity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_by: Mapped[str] = mapped_column(
        String(80), nullable=False, default="user"
    )  # "import:x" | "agent:y" | principal login — provenance, not authz
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MaterialGrade(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped, OptimisticLock):
    """A commercial grade — supplier's trade product. Two grades sharing
    a molecule identifier stay distinct until a reviewed reconciliation
    (§5, AT-0203-2): the registry never auto-collapses them."""

    __tablename__ = "material_grades"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "material_id"],
            ["material_identities.workspace_id", "material_identities.id"],
            name="fk_material_grades_scope_material",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_material_grades_scope_id"),
        Index("ix_material_grades_scope_list", "workspace_id", "material_id", "created_at", "id"),
    )

    material_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    supplier: Mapped[str] = mapped_column(String(300), nullable=False)
    grade_name: Mapped[str] = mapped_column(String(300), nullable=False)
    # active content / purity as a serialized Quantity DTO — basis is
    # mandatory inside it (as_supplied vs active_solids).
    active_content: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    specifications: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # reviewed reconciliation pointer — never silently set
    reconciled_into: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class MaterialLot(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped):
    """A physical lot of a grade — what was actually weighed out."""

    __tablename__ = "material_lots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "grade_id"],
            ["material_grades.workspace_id", "material_grades.id"],
            name="fk_material_lots_scope_grade",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_material_lots_scope_id"),
        Index("ix_material_lots_scope_list", "workspace_id", "grade_id", "created_at", "id"),
    )

    grade_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lot_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # certificate / document artifact ids, kept as references — the
    # bytes live in the vault, never in this table.
    certificate_artifact_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReferenceProduct(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped, OptimisticLock):
    """A purchased/reference product. Its composition knowledge may be
    `unknown` — in which case *no ingredient list exists* (AT-0203-1)."""

    __tablename__ = "reference_products"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_reference_products_scope_id"),
        CheckConstraint(
            f"composition_knowledge IN {COMPOSITION_KNOWLEDGE!r}",
            name="composition_knowledge",
        ),
        Index("ix_reference_products_scope_list", "workspace_id", "created_at", "id"),
    )

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    aliases: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    supplier: Mapped[str | None] = mapped_column(String(300), nullable=True)
    category: Mapped[str | None] = mapped_column(String(160), nullable=True)
    composition_knowledge: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unknown"
    )
    # source document artifact ids
    documentation_artifact_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class ReferenceProductRevision(Base, UUIDPrimaryKey):
    """Versioned reference-product content — claimed vs measured
    properties stay separate; measured properties link evidence."""

    __tablename__ = "reference_product_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "product_id"],
            ["reference_products.workspace_id", "reference_products.id"],
            name="fk_reference_product_revisions_scope_product",
        ),
        UniqueConstraint("product_id", "revision", name="uq_refprod_product_revision"),
        CheckConstraint(f"status IN {REVISION_STATUSES_CONTRACT!r}", name="status"),
        Index(
            "ix_reference_product_revisions_product",
            "workspace_id",
            "product_id",
            "revision",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    # {"compositionKnowledge": ..., "composition": [...]|None,
    #  "claimedProperties": {...}, "measuredProperties": [{metricId,
    #  evidenceIds: [...]}], "sampleLotRefs": [...]}
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# --------------------------------- formulations + candidates (§5, §7.2)

REVISION_STATUSES_FORMULATION = ("draft", "accepted", "superseded")

# §7.2: accepted *content* is immutable; eligibility is a separate
# axis that never mutates content.
CANDIDATE_STATUSES = ("draft", "submitted", "accepted_for_research", "rejected")
CANDIDATE_ELIGIBILITY = (
    "not_assessed",
    "eligible_for_computation",
    "needs_review",
    "blocked",
    "eligible_for_approved_experiment",
)
ENTITY_KINDS = ("formulation", "molecule", "material")
PATCH_STATUSES = ("proposed", "accepted", "rejected")


class FormulationFamily(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped, OptimisticLock):
    """A formulation lineage — revisions hang off the family."""

    __tablename__ = "formulation_families"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_formulation_families_scope_id"),
        Index("ix_formulation_families_scope_list", "workspace_id", "created_at", "id"),
    )

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class FormulationRevision(Base, UUIDPrimaryKey):
    """Versioned formulation content (§5). Drafts may be incomplete;
    acceptance runs declared-basis validation with an explicit
    tolerance — totals are never normalized (§6.2, AT-0204-1)."""

    __tablename__ = "formulation_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "family_id"],
            ["formulation_families.workspace_id", "formulation_families.id"],
            name="fk_formulation_revisions_scope_family",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "parent_revision_id"],
            ["formulation_revisions.workspace_id", "formulation_revisions.id"],
            name="fk_formulation_revisions_scope_parent",
        ),
        UniqueConstraint("family_id", "revision", name="uq_formulation_family_revision"),
        UniqueConstraint("workspace_id", "id", name="uq_formulation_revisions_scope_id"),
        CheckConstraint(f"status IN {REVISION_STATUSES_FORMULATION!r}", name="status"),
        Index(
            "ix_formulation_revisions_family",
            "workspace_id",
            "family_id",
            "revision",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    parent_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # {"ingredients": [{materialId|name|alias, amount: QuantityDTO,
    #   role}], "amountBasis", "declaredTotal", "tolerance",
    #  "completeness": "draft"|"complete", "processRevisionId",
    #  "substrateContext", "applicationContext", "authorSource",
    #  "validationFindings": [...]}
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProcessRevision(Base, UUIDPrimaryKey):
    """Ordered process steps (§5): order is significant and preserved
    verbatim — steps are never sorted (§6.2, AT-0204-3). Formula and
    process version together but stay distinct objects."""

    __tablename__ = "process_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "family_id"],
            ["formulation_families.workspace_id", "formulation_families.id"],
            name="fk_process_revisions_scope_family",
        ),
        UniqueConstraint("family_id", "revision", name="uq_process_family_revision"),
        CheckConstraint(f"status IN {REVISION_STATUSES_FORMULATION!r}", name="status"),
        Index("ix_process_revisions_family", "workspace_id", "family_id", "revision"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    # {"steps": [{order, action, inputs, outputs, conditions|null,
    #   equipment}], "source", "approvalStatus", "unknownConditions":[]}
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CandidateRevision(Base, UUIDPrimaryKey):
    """A proposed candidate content revision inside a task (§5, §7.2).
    Accepted content is immutable; rankings/measurements never mutate
    it — they live elsewhere and reference this revision."""

    __tablename__ = "candidate_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["research_tasks.workspace_id", "research_tasks.id"],
            name="fk_candidate_revisions_scope_task",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "contract_revision_id"],
            ["success_contract_revisions.workspace_id", "success_contract_revisions.id"],
            name="fk_candidate_revisions_scope_contract",
        ),
        UniqueConstraint("task_id", "revision", name="uq_candidate_task_revision"),
        UniqueConstraint("workspace_id", "id", name="uq_candidate_revisions_scope_id"),
        CheckConstraint(f"status IN {CANDIDATE_STATUSES!r}", name="status"),
        CheckConstraint(f"eligibility IN {CANDIDATE_ELIGIBILITY!r}", name="eligibility"),
        CheckConstraint(f"entity_kind IN {ENTITY_KINDS!r}", name="entity_kind"),
        Index("ix_candidate_revisions_task", "workspace_id", "task_id", "revision"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    eligibility: Mapped[str] = mapped_column(String(40), nullable=False, default="not_assessed")
    entity_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    entity_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    parent_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    contract_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    # {"proposedDifferences": [...], "evidenceIds": [...]}
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CandidatePatch(Base, UUIDPrimaryKey, WorkspaceScoped):
    """A proposed content patch to a candidate (§5): accepting creates
    a *new* candidate revision; rejecting retains the reason and leaves
    the target content untouched (AT-0204-2)."""

    __tablename__ = "candidate_patches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "candidate_id"],
            ["candidate_revisions.workspace_id", "candidate_revisions.id"],
            name="fk_candidate_patches_scope_candidate",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "reviewed_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_candidate_patches_scope_reviewer",
        ),
        CheckConstraint(f"status IN {PATCH_STATUSES!r}", name="status"),
        Index("ix_candidate_patches_scope_list", "workspace_id", "created_at", "id"),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    patch: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    proposed_by: Mapped[str] = mapped_column(String(80), nullable=False, default="user")
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ------------------------------------------------------------------
# CS-0301 — quarantined ingestion (§9.1, §9.2)

IMPORT_STATUSES = ("quarantined", "parsed", "failed")
RECORD_STATUSES = ("proposed", "accepted", "rejected")


class ImportBatch(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped):
    """One ingestion run against an artifact. Idempotent on
    (scope, checksum, parser_version) — a reimport of the same bytes
    with the same parser returns the existing batch rather than
    duplicating records (AT-0301-3). ``document_group`` +
    ``source_revision`` model the source lineage: changed bytes of the
    same logical document create a new revision, never overwrite."""

    __tablename__ = "import_batches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "artifact_id"],
            ["artifacts.workspace_id", "artifacts.id"],
            name="fk_import_batches_scope_artifact",
        ),
        UniqueConstraint(
            "workspace_id",
            "checksum_sha256",
            "parser_version",
            name="uq_import_batches_dedup",
        ),
        CheckConstraint(f"status IN {IMPORT_STATUSES!r}", name="import_status"),
        Index("ix_import_batches_scope_list", "workspace_id", "created_at", "id"),
        Index("ix_import_batches_group", "workspace_id", "document_group"),
    )

    artifact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    detected_type: Mapped[str] = mapped_column(String(16), nullable=False)
    parser_name: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    document_group: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class ExtractedRecord(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped):
    """A proposed extraction — candidate data, never automatically
    accepted (§9.2). Locator + original text are always preserved;
    flags carry every ambiguity the parser detected."""

    __tablename__ = "extracted_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "batch_id"],
            ["import_batches.workspace_id", "import_batches.id"],
            name="fk_extracted_records_scope_batch",
        ),
        CheckConstraint(f"status IN {RECORD_STATUSES!r}", name="record_status"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="record_confidence_range"),
        Index("ix_extracted_records_batch", "workspace_id", "batch_id", "id"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    locator: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ------------------------------------------------------------------
# CS-0302 — evidence claims + provenance (§9.2, §10)

CLAIM_KINDS = ("document_claim", "inferred_suggestion", "measured_outcome")
CLAIM_STATUSES = ("proposed", "accepted", "rejected", "superseded")
CLAIM_RELATIONS = ("supports", "contradicts")


class EvidenceClaim(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped):
    """A reviewed claim with provenance (§10). Three distinct kinds:
    document claims (parsed from a source), inferred suggestions
    (tool/model output), measured outcomes (lab results). Source
    locator + original text are always carried; conditions capture
    the context the claim is true under."""

    __tablename__ = "evidence_claims"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "source_record_id"],
            ["extracted_records.workspace_id", "extracted_records.id"],
            name="fk_evidence_claims_scope_record",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "source_batch_id"],
            ["import_batches.workspace_id", "import_batches.id"],
            name="fk_evidence_claims_scope_batch",
        ),
        CheckConstraint(f"kind IN {CLAIM_KINDS!r}", name="claim_kind"),
        CheckConstraint(f"status IN {CLAIM_STATUSES!r}", name="claim_status"),
        Index("ix_evidence_claims_scope_list", "workspace_id", "created_at", "id"),
        Index("ix_evidence_claims_kind", "workspace_id", "kind"),
    )

    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    subject: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    statement: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    locator: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    conditions: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClaimLink(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped):
    """Support/contradiction edges between claims (§10). A
    contradiction never demotes or hides either claim — both stay
    visible with their conditions and provenance (AT-0302-2)."""

    __tablename__ = "claim_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "from_claim_id"],
            ["evidence_claims.workspace_id", "evidence_claims.id"],
            name="fk_claim_links_scope_from",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "to_claim_id"],
            ["evidence_claims.workspace_id", "evidence_claims.id"],
            name="fk_claim_links_scope_to",
        ),
        CheckConstraint(f"relation IN {CLAIM_RELATIONS!r}", name="claim_relation"),
        CheckConstraint("from_claim_id <> to_claim_id", name="claim_link_distinct"),
        UniqueConstraint(
            "workspace_id",
            "from_claim_id",
            "to_claim_id",
            "relation",
            name="uq_claim_links_edge",
        ),
        Index("ix_claim_links_from", "workspace_id", "from_claim_id"),
        Index("ix_claim_links_to", "workspace_id", "to_claim_id"),
    )

    from_claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    to_claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    relation: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


# ------------------------------------------------------------------
# CS-0303 — scoped retrieval + source rights (§9.4, §10, §21)

CHUNK_STATUSES = ("active", "superseded", "revoked")


class SourceChunk(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped):
    """An indexed text chunk (§10 SourceChunk). Carries the exact
    source locator, the extraction method + uncertainty, original and
    normalized text, the chunking version that produced it, and the
    rights/ACL decisions that gate who may retrieve it."""

    __tablename__ = "source_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "artifact_id"],
            ["artifacts.workspace_id", "artifacts.id"],
            name="fk_source_chunks_scope_artifact",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "batch_id"],
            ["import_batches.workspace_id", "import_batches.id"],
            name="fk_source_chunks_scope_batch",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "record_id"],
            ["extracted_records.workspace_id", "extracted_records.id"],
            name="fk_source_chunks_scope_record",
        ),
        CheckConstraint(f"status IN {CHUNK_STATUSES!r}", name="chunk_status"),
        Index("ix_source_chunks_scope_list", "workspace_id", "created_at", "id"),
        Index("ix_source_chunks_artifact", "workspace_id", "artifact_id"),
        Index("ix_source_chunks_status", "workspace_id", "status"),
    )

    artifact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    locator: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(64), nullable=False)
    uncertainty: Mapped[float | None] = mapped_column(Float, nullable=True)
    chunking_version: Mapped[str] = mapped_column(String(32), nullable=False)
    rights: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    acl_scope: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    eval_allowed: Mapped[bool] = mapped_column(nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class RetrievalManifest(Base, UUIDPrimaryKey, WorkspaceScoped):
    """What a search returned, to whom, keyed by query + scope +
    permissions + source-index/policy versions (§10). Recorded for
    every search — the audit trail of evidence exposure."""

    __tablename__ = "retrieval_manifests"
    __table_args__ = (Index("ix_retrieval_manifests_scope", "workspace_id", "created_at", "id"),)

    principal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    query_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_index_version: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    eval_context: Mapped[bool] = mapped_column(nullable=False, default=False)
    chunk_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    cached: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RetrievalCache(Base, UUIDPrimaryKey, WorkspaceScoped):
    """Result cache keyed by (scope, permissions, query, source-index
    version, policy version, eval context) — revocation/supersession
    changes the index version so stale entries can never be hit."""

    __tablename__ = "retrieval_cache"
    __table_args__ = (UniqueConstraint("workspace_id", "cache_key", name="uq_retrieval_cache_key"),)

    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ------------------------------------------------------------------
# CS-0304 — durable task memory & session snapshots (§10.1, §11.1)

SESSION_STATUSES = ("active", "ended")
MESSAGE_ROLES = ("user", "assistant", "system", "tool")
MESSAGE_KINDS = ("message", "proposal", "tool_call", "tool_result", "rationale")
QUESTION_STATUSES = ("open", "resolved")


class ContextManifest(Base, UUIDPrimaryKey, WorkspaceScoped):
    """The compiled task context a session starts from (§10.1).

    ``items`` is the ordered, token-budgeted selection —
    ``[{kind, refId, text, tokens, pinned}]``; ``omitted`` discloses
    what the budget excluded (``[{kind, refId, tokens}]``) so a
    dropped piece of evidence is never silent. ``warnings`` carries
    the hard constraints and unresolved safety/identity warnings that
    are always preserved regardless of budget."""

    __tablename__ = "context_manifests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["research_tasks.workspace_id", "research_tasks.id"],
            name="fk_context_manifests_scope_task",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "contract_revision_id"],
            ["success_contract_revisions.workspace_id", "success_contract_revisions.id"],
            name="fk_context_manifests_scope_contract",
        ),
        Index("ix_context_manifests_task", "workspace_id", "task_id", "created_at", "id"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    contract_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    compiler_version: Mapped[str] = mapped_column(String(32), nullable=False)
    token_budget: Mapped[int] = mapped_column(Integer, nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False)
    over_budget: Mapped[bool] = mapped_column(nullable=False, default=False)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    omitted: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ResearchSession(Base, UUIDPrimaryKey, WorkspaceScoped):
    """A research session on a task (§11.1). Resumes from the manifest
    compiled at start — old sessions stay linked to the context that
    existed at *their* start, never silently re-anchored."""

    __tablename__ = "research_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["research_tasks.workspace_id", "research_tasks.id"],
            name="fk_research_sessions_scope_task",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "start_manifest_id"],
            ["context_manifests.workspace_id", "context_manifests.id"],
            name="fk_research_sessions_scope_manifest",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "started_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_research_sessions_scope_starter",
        ),
        CheckConstraint(f"status IN {SESSION_STATUSES!r}", name="session_status"),
        Index("ix_research_sessions_task", "workspace_id", "task_id", "created_at", "id"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    start_manifest_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Contract revision the session opened under — preserved so a
    # later contract never rewrites what this session saw (§7.4).
    start_contract_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    started_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Snapshot written at end: {"contractRevisionId", "openQuestions",
    #   "decisionCount", "candidateRevisionIds"} — a snapshot, not
    #   a summary; structured state stays in its own tables.
    end_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SessionMessage(Base, UUIDPrimaryKey, WorkspaceScoped):
    """One layer of §10.1 memory: session messages. Structured
    references (``refs``: claim/candidate/decision ids) ride
    alongside text so a message can point at canonical state instead
    of paraphrasing it."""

    __tablename__ = "session_messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "session_id"],
            ["research_sessions.workspace_id", "research_sessions.id"],
            name="fk_session_messages_scope_session",
        ),
        CheckConstraint(f"role IN {MESSAGE_ROLES!r}", name="message_role"),
        CheckConstraint(f"kind IN {MESSAGE_KINDS!r}", name="message_kind"),
        Index("ix_session_messages_session", "workspace_id", "session_id", "created_at", "id"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="message")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    refs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TaskQuestion(Base, UUIDPrimaryKey, WorkspaceScoped):
    """An open question on a task (§10.1). Blocking questions are
    hard-pinned into every context manifest — they can never be
    budgeted away."""

    __tablename__ = "task_questions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["research_tasks.workspace_id", "research_tasks.id"],
            name="fk_task_questions_scope_task",
        ),
        CheckConstraint(f"status IN {QUESTION_STATUSES!r}", name="question_status"),
        Index("ix_task_questions_task", "workspace_id", "task_id", "created_at", "id"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    blocking: Mapped[bool] = mapped_column(nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    raised_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskSummary(Base, UUIDPrimaryKey, WorkspaceScoped):
    """A generated summary — a *derived* navigation aid (§10.1),
    never canonical state. ``contract_revision_id`` pins the contract
    it was written against and ``source_ids`` lists the claims,
    decisions, and chunks it drew on, so staleness is checkable at
    read time instead of trusting the prose. A summary can never be
    written back into structured state — there is no apply path."""

    __tablename__ = "task_summaries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["research_tasks.workspace_id", "research_tasks.id"],
            name="fk_task_summaries_scope_task",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "contract_revision_id"],
            ["success_contract_revisions.workspace_id", "success_contract_revisions.id"],
            name="fk_task_summaries_scope_contract",
        ),
        Index("ix_task_summaries_task", "workspace_id", "task_id", "created_at", "id"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    contract_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # e.g. {"claims": 3, "decisions": 1, "chunks": 5}
    coverage: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # What produced it — a model id/version or "deterministic";
    # recorded so provenance is auditable (§10.1).
    generator: Mapped[str] = mapped_column(String(120), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ------------------------------------------------------------------
# CS-0305 — source revocation + impact records (§9.4, §17.5)


class SourceRevocation(Base, UUIDPrimaryKey, WorkspaceScoped):
    """The persisted record of a source revocation and its point-in-
    time impact report (§17.5). Honest by construction: it records
    what was *marked affected* and who was *exposed* — never an
    unlearning guarantee."""

    __tablename__ = "source_revocations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "artifact_id"],
            ["artifacts.workspace_id", "artifacts.id"],
            name="fk_source_revocations_scope_artifact",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "revoked_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_source_revocations_scope_revoker",
        ),
        UniqueConstraint("workspace_id", "artifact_id", name="uq_source_revocations_artifact"),
        Index("ix_source_revocations_scope_list", "workspace_id", "created_at", "id"),
    )

    artifact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Point-in-time report: {"chunksRevoked", "recordsRejected",
    #   "claimsSuperseded", "affectedDerivedIds", "exposedManifestIds",
    #   "exposedPrincipalIds", "affectedDatasetIds",
    #   "affectedModelReleaseIds", "unlearningGuarantee": false}
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


RUN_STATUSES = (
    "requested",
    "awaiting_approval",
    "queued",
    "running",
    "succeeded",
    "failed",
    "timed_out",
    "cancelled",
    "cancel_requested",
    "blocked",
    "interrupted",
)
RUN_TERMINAL = ("succeeded", "failed", "timed_out", "cancelled")

RUN_ATTEMPT_STATUSES = (
    "queued",
    "running",
    "succeeded",
    "failed",
    "timed_out",
    "cancelled",
    "interrupted",
)


class Run(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped, OptimisticLock):
    """Authoritative user-visible execution record (§7.3, §13).

    The Run is the record of truth; queue job ids and external workflow
    ids are attributes of *attempts*, never the source of status. State
    transitions are compare-and-swap: a late callback can never
    resurrect a terminal run."""

    __tablename__ = "runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["research_tasks.workspace_id", "research_tasks.id"],
            name="fk_runs_scope_task",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "requested_by"],
            ["principals.workspace_id", "principals.id"],
            name="fk_runs_scope_requester",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_runs_scope_id"),
        CheckConstraint(f"status IN {RUN_STATUSES!r}", name="status"),
        Index("ix_runs_scope_list", "workspace_id", "status", "created_at", "id"),
    )

    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="requested")
    # Scoped record IDs + bounded metadata only — never engine input
    # payloads, secrets, or unbounded text (§13.1/§7.4).
    request: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    attempts: Mapped[list[RunAttempt]] = relationship(back_populates="run")


class RunAttempt(Base, UUIDPrimaryKey, WorkspaceScoped):
    """One execution attempt of a Run (§7.3).

    ``external_id`` is the queue/workflow job id — reconciled before
    retry so a duplicate submission can never create a second logical
    attempt. ``callbacks`` preserves late/conflicting callbacks that
    arrived after a terminal state."""

    __tablename__ = "run_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["runs.workspace_id", "runs.id"],
            name="fk_run_attempts_scope_run",
        ),
        UniqueConstraint("workspace_id", "run_id", "attempt_number", name="uq_run_attempts_number"),
        UniqueConstraint("workspace_id", "external_id", name="uq_run_attempts_external"),
        CheckConstraint(f"status IN {RUN_ATTEMPT_STATUSES!r}", name="status"),
        Index("ix_run_attempts_scope_run", "workspace_id", "run_id", "attempt_number"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    queue_name: Mapped[str] = mapped_column(String(64), nullable=False, default="runs")
    external_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    enqueued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    callbacks: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)

    run: Mapped[Run] = relationship(back_populates="attempts")


class ResourceGroup(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped):
    """A schedulable resource pool (§13.4) — capacity minus ``reserve``
    (headroom kept for the OS/API/UI) is what admission may allocate."""

    __tablename__ = "resource_groups"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_resource_groups_name"),
        UniqueConstraint("workspace_id", "id", name="uq_resource_groups_scope_id"),
    )

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # {"cpu_cores": int, "memory_bytes": int, "gpu_devices": int,
    #  "storage_bytes": int, "concurrency": int} — None values mean
    # the dimension is unobserved and therefore not schedulable.
    capacity: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reserve: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class ResourceReservation(Base, UUIDPrimaryKey, WorkspaceScoped):
    """A transactional hold on a resource group (§13.4).

    Reservations are created in the same transaction that enqueues the
    run, are released when the run leaves the queue/terminates, and
    expire so a lost worker cannot hold capacity forever."""

    __tablename__ = "resource_reservations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "group_id"],
            ["resource_groups.workspace_id", "resource_groups.id"],
            name="fk_reservations_scope_group",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["runs.workspace_id", "runs.id"],
            name="fk_reservations_scope_run",
        ),
        UniqueConstraint("workspace_id", "run_id", name="uq_reservations_run"),
        CheckConstraint("status IN ('active','released','consumed','expired')", name="status"),
        Index("ix_reservations_group_active", "workspace_id", "group_id", "status"),
    )

    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    envelope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RunCacheEntry(Base, UUIDPrimaryKey, WorkspaceScoped):
    """An immutable cached run result (§13.5).

    Keyed by the full scientific context digest (workers.common.cache);
    scoped per workspace. Entries are insert-only: a superseding run
    creates a new key, never overwrites. ``invalidated`` marks entries
    that must not be served (e.g. a source/policy revocation)."""

    __tablename__ = "run_cache_entries"
    __table_args__ = (
        UniqueConstraint("workspace_id", "key", name="uq_run_cache_key"),
        CheckConstraint("status IN ('valid','invalidated')", name="status"),
        Index("ix_run_cache_scope", "workspace_id", "created_at", "id"),
    )

    key: Mapped[str] = mapped_column(String(64), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    produced_by_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="valid")
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidate_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


EXPERIMENT_PLAN_STATUSES = ("draft", "submitted", "approved", "rejected")


class ExperimentPlan(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped, OptimisticLock):
    """Experiment plan (§14.1): drafts reference immutable
    candidate/process/contract/method revisions; approval binds the
    exact bound-input digest — any later change makes the release
    approval stale at packet-export time, never silently valid."""

    __tablename__ = "experiment_plans"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["research_tasks.workspace_id", "research_tasks.id"],
            name="fk_experiment_plans_scope_task",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "approval_id"],
            ["approvals.workspace_id", "approvals.id"],
            name="fk_experiment_plans_scope_approval",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_experiment_plans_scope_id"),
        CheckConstraint(f"status IN {EXPERIMENT_PLAN_STATUSES!r}", name="status"),
        Index("ix_experiment_plans_scope_task", "workspace_id", "task_id", "created_at", "id"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    # plan content: candidate/contract/process revision ids, method,
    # sample plan, acceptance criteria, hazard notes, resource needs
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # resolved bound inputs + their digest at last write — the approval
    # envelope binds this digest, not the mutable row
    bound_inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    blockers: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    packet: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


EXECUTION_STATUSES = ("in_progress", "completed", "stopped")
REPEAT_TYPES = (
    "same_sample",
    "independent_batch",
    "independent_operator",
    "timepoint",
)
MEASUREMENT_VALUE_TYPES = (
    "numeric",
    "interval",
    "below_detection",
    "above_quantification",
    "ordinal",
    "categorical",
    "missing",
)
MISSING_REASONS = (
    "not_measured",
    "instrument_failure",
    "sample_lost",
    "unknown",
)
MEASUREMENT_STATUSES = ("proposed", "accepted", "rejected", "superseded")
SAMPLE_KINDS = ("aliquot", "timepoint", "whole")


class LabExecution(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped, OptimisticLock):
    """One operator-run execution of an approved plan (§14.1): actual
    materials/lots/conditions, deviations and observations as recorded
    by the human operator. Historical imports (no preapproval) are
    marked ``historical`` and can never claim a release approval."""

    __tablename__ = "lab_executions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "plan_id"],
            ["experiment_plans.workspace_id", "experiment_plans.id"],
            name="fk_lab_executions_scope_plan",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_lab_executions_scope_id"),
        CheckConstraint(f"status IN {EXECUTION_STATUSES!r}", name="status"),
        Index(
            "ix_lab_executions_scope_plan",
            "workspace_id",
            "plan_id",
            "created_at",
            "id",
        ),
    )

    plan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # task back-reference for scope resolution on historical imports
    # (plan_id is NULL there)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="in_progress")
    historical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # actual materials/lots/conditions vs the plan payload, as recorded
    actual: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    deviations: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LabBatch(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped, OptimisticLock):
    """Independently prepared batch within an execution (§14.2) — the
    unit that replication counting treats as one independent trial."""

    __tablename__ = "lab_batches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "execution_id"],
            ["lab_executions.workspace_id", "lab_executions.id"],
            name="fk_lab_batches_scope_execution",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_lab_batches_scope_id"),
        Index(
            "ix_lab_batches_scope_execution",
            "workspace_id",
            "execution_id",
            "created_at",
            "id",
        ),
    )

    execution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class LabSample(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped, OptimisticLock):
    """Sample / aliquot / timepoint drawn from one batch (§14.2)."""

    __tablename__ = "lab_samples"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "batch_id"],
            ["lab_batches.workspace_id", "lab_batches.id"],
            name="fk_lab_samples_scope_batch",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_lab_samples_scope_id"),
        CheckConstraint(f"kind IN {SAMPLE_KINDS!r}", name="kind"),
        Index(
            "ix_lab_samples_scope_batch",
            "workspace_id",
            "batch_id",
            "created_at",
            "id",
        ),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="aliquot")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class Measurement(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped, OptimisticLock):
    """One reading on one sample (§6.3, §14.2): typed value payload,
    repeat semantics, planned-vs-actual conditions, integrity review
    and applicability flag. Corrected only via amendment — never
    overwritten (AT-0502-3)."""

    __tablename__ = "measurements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "sample_id"],
            ["lab_samples.workspace_id", "lab_samples.id"],
            name="fk_measurements_scope_sample",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_measurements_scope_id"),
        CheckConstraint(f"status IN {MEASUREMENT_STATUSES!r}", name="status"),
        CheckConstraint(f"repeat_type IN {REPEAT_TYPES!r}", name="repeat_type"),
        CheckConstraint(f"value_type IN {MEASUREMENT_VALUE_TYPES!r}", name="value_type"),
        Index(
            "ix_measurements_scope_sample",
            "workspace_id",
            "sample_id",
            "created_at",
            "id",
        ),
    )

    sample_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    method: Mapped[str] = mapped_column(String(300), nullable=False)
    # Contract metric id/name this reading addresses (e.g.
    # "metric.synthetic-performance"). NULL = unattributed — it can
    # never satisfy a contract metric (§12.3).
    metric: Mapped[str | None] = mapped_column(String(300), nullable=True)
    repeat_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value_type: Mapped[str] = mapped_column(String(24), nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # {"planned": {...}, "actual": {...}} — deviations live here, not
    # silently merged into one conditions blob (§14.2)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    applicable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    applicability_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    pipeline_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class MeasurementAmendment(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped):
    """Amendment record (§14.2): a corrected value with reason and
    source. The superseded measurement row keeps its original value —
    downstream consumers see ``superseded`` status."""

    __tablename__ = "measurement_amendments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "measurement_id"],
            ["measurements.workspace_id", "measurements.id"],
            name="fk_amendments_scope_measurement",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_amendments_scope_id"),
        Index(
            "ix_amendments_scope_measurement",
            "workspace_id",
            "measurement_id",
            "created_at",
            "id",
        ),
    )

    measurement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


# ------------------------------------------------------------------
# CS-0601 — dataset snapshots + training eligibility (§17.2)

DATASET_PURPOSES = (
    "property_prediction",
    "extraction_correction",
    "assistant_sft",
    "preference_pairs",
    "rl_tasks",
)
DATASET_STATES = ("draft", "frozen")


class DatasetSnapshot(Base, UUIDPrimaryKey, WorkspaceScoped, Timestamped):
    """Immutable point-in-time training manifest (§17.2): entry list
    with record ids, revisions, per-record hashes, source classes,
    rights and exclusion semantics. A frozen snapshot is never
    rewritten — source drift is detected by re-hashing, not by
    updating the manifest (AT-0601-3)."""

    __tablename__ = "dataset_snapshots"
    __table_args__ = (
        CheckConstraint(f"purpose IN {DATASET_PURPOSES!r}", name="dataset_purpose"),
        CheckConstraint(f"state IN {DATASET_STATES!r}", name="dataset_state"),
        Index("ix_dataset_snapshots_scope", "workspace_id", "created_at", "id"),
    )

    purpose: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Entries: [{recordId, recordKind, sourceClass, hash,
    #            rightsTraining, labelKind, semantics, excluded,
    #            exclusionReason}]
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    frozen_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
