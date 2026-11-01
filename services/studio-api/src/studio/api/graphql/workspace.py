"""Owner-private GraphQL surfaces sharing the REST and agent domain services."""

from __future__ import annotations

import uuid
from typing import Any, cast

import strawberry
from strawberry.scalars import JSON

from studio.api.graphql.context import gql_ctx
from studio.domain.agent_workspace.service import AgentWorkspaceService
from studio.domain.learning.workspace import LearningWorkspaceService
from studio.domain.library import contracts
from studio.domain.library.service import LibraryService
from studio.errors import DomainError, ErrorCode


@strawberry.type
class PrivateNotebookInfo:
    id: strawberry.ID
    title: str
    folder_id: strawberry.ID | None
    revision: int
    ai_enabled: bool
    training_enabled: bool


@strawberry.type
class PrivatePageInfo:
    id: strawberry.ID
    notebook_id: strawberry.ID
    title: str
    kind: str
    revision: int
    content: JSON
    citations: list[JSON]


@strawberry.type
class PrivateLibraryInfo:
    folders: list[JSON]
    notebooks: list[PrivateNotebookInfo]
    pages: list[PrivatePageInfo]
    memory: list[JSON]
    downloads: list[JSON]


@strawberry.type
class PrivateAgentInfo:
    threads: list[JSON]
    providers: list[JSON]
    policy: JSON


@strawberry.type
class PrivateLearningInfo:
    datasets: list[JSON]
    models: list[JSON]
    jobs: list[JSON]


def _object(value: JSON) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DomainError(ErrorCode.VALIDATION, "Input must be a JSON object")
    return cast(dict[str, Any], value)


def _library(info: strawberry.Info) -> LibraryService:
    context = gql_ctx(info)
    return LibraryService(context.db, context.service_ctx(), vault_root=context.settings.vault_root)


@strawberry.type
class WorkspaceQueries:
    @strawberry.field
    def private_library(self, info: strawberry.Info) -> PrivateLibraryInfo:
        state = _library(info).list_all()
        return PrivateLibraryInfo(
            folders=state["folders"],
            notebooks=[
                PrivateNotebookInfo(
                    id=strawberry.ID(row["id"]),
                    title=row["title"],
                    folder_id=strawberry.ID(row["folderId"]) if row.get("folderId") else None,
                    revision=row["revision"],
                    ai_enabled=row["aiEnabled"],
                    training_enabled=row["trainingEnabled"],
                )
                for row in state["notebooks"]
            ],
            pages=[
                PrivatePageInfo(
                    id=strawberry.ID(row["id"]),
                    notebook_id=strawberry.ID(row["notebookId"]),
                    title=row["title"],
                    kind=row["kind"],
                    revision=row["revision"],
                    content=row["content"],
                    citations=row["citations"],
                )
                for row in state["pages"]
            ],
            memory=state["memory"],
            downloads=state["sources"],
        )

    @strawberry.field
    def private_agent(self, info: strawberry.Info) -> PrivateAgentInfo:
        context = gql_ctx(info)
        service = AgentWorkspaceService(context.db, context.service_ctx())
        result = PrivateAgentInfo(
            threads=[cast(JSON, row) for row in service.list_threads()],
            providers=[cast(JSON, row) for row in service.providers()],
            policy=cast(JSON, service.policy()),
        )
        context.db.commit()
        return result

    @strawberry.field
    def private_agent_run(self, info: strawberry.Info, id: strawberry.ID) -> JSON:
        context = gql_ctx(info)
        return cast(
            JSON, AgentWorkspaceService(context.db, context.service_ctx()).run_detail(uuid.UUID(id))
        )

    @strawberry.field
    def private_learning(self, info: strawberry.Info) -> PrivateLearningInfo:
        context = gql_ctx(info)
        service = LearningWorkspaceService(context.db, context.service_ctx(), context.settings)
        return PrivateLearningInfo(
            datasets=[cast(JSON, row) for row in service.list_datasets()],
            models=[cast(JSON, row) for row in service.list_models()],
            jobs=[cast(JSON, row) for row in service.list_jobs()],
        )


@strawberry.type
class WorkspaceMutations:
    @strawberry.mutation
    def notebook_create(
        self, info: strawberry.Info, title: str, folder_id: strawberry.ID | None = None
    ) -> JSON:
        context = gql_ctx(info)
        result = _library(info).create_notebook(
            **contracts.CreateNotebook(
                title=title, folder_id=str(folder_id) if folder_id else None
            ).model_dump()
        )
        context.db.commit()
        return cast(JSON, result)

    @strawberry.mutation
    def notebook_page_create(self, info: strawberry.Info, input: JSON) -> JSON:
        context = gql_ctx(info)
        result = _library(info).create_page(
            **contracts.CreatePage.model_validate(input).model_dump()
        )
        context.db.commit()
        return cast(JSON, result)

    @strawberry.mutation
    def notebook_page_update(self, info: strawberry.Info, id: strawberry.ID, input: JSON) -> JSON:
        context = gql_ctx(info)
        result = _library(info).update_page(
            str(id), **contracts.UpdatePage.model_validate(input).model_dump(exclude_unset=True)
        )
        context.db.commit()
        return cast(JSON, result)

    @strawberry.mutation
    def private_agent_thread_create(self, info: strawberry.Info, input: JSON) -> JSON:
        context = gql_ctx(info)
        result = AgentWorkspaceService(context.db, context.service_ctx()).create_thread(
            _object(input)
        )
        context.db.commit()
        return cast(JSON, result)

    @strawberry.mutation
    def private_agent_run_start(
        self, info: strawberry.Info, thread_id: strawberry.ID, input: JSON
    ) -> JSON:
        context = gql_ctx(info)
        result = AgentWorkspaceService(context.db, context.service_ctx()).create_run(
            uuid.UUID(thread_id), _object(input)
        )
        context.db.commit()
        return cast(JSON, result)

    @strawberry.mutation
    def private_learning_dataset_import(self, info: strawberry.Info, input: JSON) -> JSON:
        context = gql_ctx(info)
        service = LearningWorkspaceService(context.db, context.service_ctx(), context.settings)
        result: Any = service.import_dataset(_object(input))
        context.db.commit()
        return cast(JSON, result)

    @strawberry.mutation
    def private_learning_job_start(self, info: strawberry.Info, input: JSON) -> JSON:
        context = gql_ctx(info)
        service = LearningWorkspaceService(context.db, context.service_ctx(), context.settings)
        result: Any = service.create_job(_object(input))
        context.db.commit()
        return cast(JSON, result)
