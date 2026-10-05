"""Project commands (§5.1, §11).

A project scopes tasks/materials/experiments inside a workspace.
"""

from __future__ import annotations

import uuid

from chem_studio_policy.capabilities import CAP_EDIT_TASK, CAP_READ_PROJECT
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext
from studio.errors import DomainError, ErrorCode, not_found
from studio.events.outbox import publish
from studio.persistence.models import Project


class ProjectService:
    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    def get(self, project_id: uuid.UUID) -> Project:
        self.ctx.require(CAP_READ_PROJECT)
        row = self.db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("project")
        return row

    def create(self, *, slug: str, name: str, description: str | None = None) -> Project:
        self.ctx.require(CAP_EDIT_TASK)
        if not slug.strip():
            raise DomainError(ErrorCode.VALIDATION, "slug is required", field_path="input.slug")
        if not name.strip():
            raise DomainError(ErrorCode.VALIDATION, "name is required", field_path="input.name")
        project = Project(
            workspace_id=self.ctx.workspace_id,
            slug=slug.strip(),
            name=name.strip(),
            description=description,
        )
        self.db.add(project)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="project",
            aggregate_id=project.id,
            event_type="project.created",
            payload={"projectId": str(project.id), "slug": project.slug},
        )
        audit_record(
            self.db,
            self.ctx,
            action="project.create",
            target_type="project",
            target_id=project.id,
            detail={"slug": project.slug},
        )
        return project
