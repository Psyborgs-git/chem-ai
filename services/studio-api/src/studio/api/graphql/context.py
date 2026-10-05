"""Per-request GraphQL context (§8.2).

The ServiceContext is built lazily, once per request — unauthenticated
calls raise UNAUTHENTICATED inside resolvers (a typed GraphQL error)
rather than at transport level. Request-scoped DataLoaders live here so
batching can never cross workspaces or sessions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

import strawberry
from fastapi import Request
from sqlalchemy.orm import Session
from strawberry.fastapi import BaseContext

from studio.api.deps import build_context
from studio.api.graphql.loaders import Loaders
from studio.auth.context import ServiceContext
from studio.config.settings import Settings


@dataclass
class GraphQLContext(BaseContext):
    request: Request
    db: Session
    settings: Settings
    _service_ctx: ServiceContext | None = field(default=None, repr=False)
    _loaders: Loaders | None = field(default=None, repr=False)

    def service_ctx(self) -> ServiceContext:
        if self._service_ctx is None:
            self._service_ctx = build_context(self.request, self.db)
        return self._service_ctx

    def loaders(self) -> Loaders:
        if self._loaders is None:
            ctx = self.service_ctx()
            self._loaders = Loaders(self.db, ctx.workspace_id)
        return self._loaders


def make_context(request: Request, db: Session, settings: Settings) -> GraphQLContext:
    return GraphQLContext(request=request, db=db, settings=settings)


def gql_ctx(info: strawberry.Info) -> GraphQLContext:
    return cast(GraphQLContext, info.context)
