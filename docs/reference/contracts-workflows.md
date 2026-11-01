# Research workflow API — JSON contract details

These excerpts are generated from the implementation without importing it. They specify accepted fields, conditional validation, defaults and response construction for flexible JSON interfaces. They complement the endpoint prose; implementation expressions refer to the named source service rather than a live execution.

## create

Source: `services/studio-api/src/studio/api/research_workflows.py:create`.

```python
@router.post("")
def create(body: dict[str, Any], request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = WorkflowService(db, ctx).create(body, request.app.state.settings)
    db.commit()
    return result
```

## detail

Source: `services/studio-api/src/studio/api/research_workflows.py:detail`.

```python
@router.get("/{identifier}")
def detail(identifier: uuid.UUID, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    service = WorkflowService(db, ctx)
    return service.describe(service.get(identifier))
```

## workflows

Source: `services/studio-api/src/studio/api/research_workflows.py:workflows`.

```python
@router.get("")
def workflows(db: DbSession, ctx: Ctx) -> list[dict[str, Any]]:
    service = WorkflowService(db, ctx)
    return [
        service.describe(row)
        for row in db.scalars(
            select(ResearchWorkflow)
            .where(
                ResearchWorkflow.workspace_id == ctx.workspace_id,
                ResearchWorkflow.owner_id == ctx.principal_id,
            )
            .order_by(ResearchWorkflow.created_at.desc())
        )
    ]
```

## WorkflowService.create

Source: `services/studio-api/src/studio/domain/agent_workspace/workflows.py:WorkflowService.create`.

```python
    def create(self, payload: dict[str, Any], settings: Any) -> dict[str, Any]:
        from studio.domain.agent_workspace.service import AgentWorkspaceService, ident
        from studio.domain.inference.providers import ProviderService
        from studio.domain.library.service import LibraryService

        name = str(payload.get("name", "Research workflow")).strip()
        if not name or len(name) > 200:
            raise DomainError(ErrorCode.VALIDATION, "Workflow name must contain 1-200 characters")
        provider = ProviderService(self.db, self.ctx).get(ident(payload.get("providerId")))
        if not provider.enabled:
            raise DomainError(ErrorCode.VALIDATION, "Select an enabled provider")
        limits = {}
        for key, default, maximum in (
            ("trainingSeconds", 14400, 86400),
            ("simulationSeconds", 14400, 86400),
            ("paidCostUsd", 20, 10000),
        ):
            value = payload.get(key, default)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 < value <= maximum
            ):
                raise DomainError(ErrorCode.VALIDATION, f"Invalid {key}")
            limits[key] = float(value)
        library = LibraryService(self.db, self.ctx, vault_root=settings.vault_root)
        notebook = library.create_notebook(name)
        thread = AgentWorkspaceService(self.db, self.ctx).create_thread(
            {
                "title": name,
                "notebookId": notebook["id"],
            }
        )
        row = ResearchWorkflow(
            workspace_id=self.ctx.workspace_id,
            owner_id=self.ctx.principal_id,
            name=name,
            thread_id=uuid.UUID(thread["id"]),
            notebook_id=uuid.UUID(notebook["id"]),
            provider_id=provider.id,
            provider_revision=provider.version,
            specification={
                "publicSourcesOnly": True,
                "limits": limits,
                "goal": str(payload.get("goal", ""))[:16000],
            },
            ledger={"resources": {}, "allocations": [], "stages": []},
        )
        self.db.add(row)
        self.db.flush()
        return self.describe(row)
```

## WorkflowService.describe

Source: `services/studio-api/src/studio/domain/agent_workspace/workflows.py:WorkflowService.describe`.

```python
    def describe(self, row: ResearchWorkflow) -> dict[str, Any]:
        from studio.domain.agent_workspace.models import AgentRun

        costs = [
            float((run.checkpoint or {}).get("costUsd", 0))
            for run in self.db.scalars(
                select(AgentRun).where(
                    AgentRun.thread_id == row.thread_id,
                    AgentRun.owner_id == row.owner_id,
                    AgentRun.workspace_id == row.workspace_id,
                )
            )
            if (run.checkpoint or {}).get("workflowId") == str(row.id)
        ]
        return {
            "id": str(row.id),
            "name": row.name,
            "threadId": str(row.thread_id),
            "notebookId": str(row.notebook_id),
            "providerId": str(row.provider_id),
            "specification": row.specification,
            "ledger": row.ledger,
            "paidCostUsd": sum(costs),
        }
```

## WorkflowService.get

Source: `services/studio-api/src/studio/domain/agent_workspace/workflows.py:WorkflowService.get`.

```python
    def get(self, identifier: Any, *, lock: bool = False) -> ResearchWorkflow:
        try:
            identifier = uuid.UUID(str(identifier))
        except (ValueError, TypeError) as exc:
            raise DomainError(ErrorCode.VALIDATION, "Invalid workflow identifier") from exc
        statement = select(ResearchWorkflow).where(
            ResearchWorkflow.id == identifier,
            ResearchWorkflow.workspace_id == self.ctx.workspace_id,
            ResearchWorkflow.owner_id == self.ctx.principal_id,
        )
        row = self.db.scalar(statement.with_for_update() if lock else statement)
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, "Private research workflow not found")
        return row
```
