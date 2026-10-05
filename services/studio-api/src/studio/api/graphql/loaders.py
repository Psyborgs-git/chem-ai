"""Request-scoped batch loaders (§8.2).

One Loaders instance per request + workspace. DataLoader caches die
with the request — no cross-user cached authorization.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
from strawberry.dataloader import DataLoader

from studio.persistence.models import Principal, Project, ResearchTask


def _in_scope(model, workspace_id: uuid.UUID, ids: list[uuid.UUID]):  # type: ignore[no-untyped-def]
    return select(model).where(model.workspace_id == workspace_id, model.id.in_(ids))


class Loaders:
    def __init__(self, db: Session, workspace_id: uuid.UUID) -> None:
        self._db = db
        self._ws = workspace_id

        async def _projects(keys: list[str]) -> list[Project | None]:
            uuids = [uuid.UUID(k) for k in keys]
            rows = self._db.execute(_in_scope(Project, self._ws, uuids)).scalars().all()
            by_id = {str(r.id): r for r in rows}
            return [by_id.get(k) for k in keys]

        async def _tasks(keys: list[str]) -> list[ResearchTask | None]:
            uuids = [uuid.UUID(k) for k in keys]
            rows = self._db.execute(_in_scope(ResearchTask, self._ws, uuids)).scalars().all()
            by_id = {str(r.id): r for r in rows}
            return [by_id.get(k) for k in keys]

        async def _principals(keys: list[str]) -> list[Principal | None]:
            uuids = [uuid.UUID(k) for k in keys]
            rows = self._db.execute(_in_scope(Principal, self._ws, uuids)).scalars().all()
            by_id = {str(r.id): r for r in rows}
            return [by_id.get(k) for k in keys]

        self.projects: DataLoader[str, Project | None] = DataLoader(load_fn=_projects)
        self.tasks: DataLoader[str, ResearchTask | None] = DataLoader(load_fn=_tasks)
        self.principals: DataLoader[str, Principal | None] = DataLoader(load_fn=_principals)
