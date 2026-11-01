# Private agent API — JSON contract details

These excerpts are generated from the implementation without importing it. They specify accepted fields, conditional validation, defaults and response construction for flexible JSON interfaces. They complement the endpoint prose; implementation expressions refer to the named source service rather than a live execution.

## automation

Source: `services/studio-api/src/studio/api/agent_workspace.py:automation`.

```python
@agent_router.put("/threads/{thread_id}/automation")
def automation(
    thread_id: uuid.UUID, db: DbSession, ctx: Ctx, body: dict[str, Any]
) -> dict[str, Any]:
    result = AgentWorkspaceService(db, ctx).save_automation(thread_id, body)
    db.commit()
    return result
```

## cancel

Source: `services/studio-api/src/studio/api/agent_workspace.py:cancel`.

```python
@agent_router.post("/runs/{run_id}/cancel")
def cancel(run_id: uuid.UUID, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = AgentWorkspaceService(db, ctx).cancel(run_id)
    db.commit()
    return result
```

## create_run

Source: `services/studio-api/src/studio/api/agent_workspace.py:create_run`.

```python
@agent_router.post("/threads/{thread_id}/runs")
def create_run(
    thread_id: uuid.UUID, db: DbSession, ctx: Ctx, body: dict[str, Any]
) -> dict[str, Any]:
    result = AgentWorkspaceService(db, ctx).create_run(thread_id, body)
    db.commit()
    return result
```

## create_thread

Source: `services/studio-api/src/studio/api/agent_workspace.py:create_thread`.

```python
@agent_router.post("/threads")
def create_thread(db: DbSession, ctx: Ctx, body: dict[str, Any]) -> dict[str, Any]:
    result = AgentWorkspaceService(db, ctx).create_thread(body)
    db.commit()
    return result
```

## discover

Source: `services/studio-api/src/studio/api/agent_workspace.py:discover`.

```python
@agent_router.post("/providers/{provider_id}/discover")
def discover(provider_id: uuid.UUID, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return AgentWorkspaceService(db, ctx).discover(provider_id)
```

## policy

Source: `services/studio-api/src/studio/api/agent_workspace.py:policy`.

```python
@agent_router.get("/policies")
def policy(db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return AgentWorkspaceService(db, ctx).policy()
```

## providers

Source: `services/studio-api/src/studio/api/agent_workspace.py:providers`.

```python
@agent_router.get("/providers")
def providers(db: DbSession, ctx: Ctx) -> dict[str, Any]:
    rows = AgentWorkspaceService(db, ctx).providers()
    db.commit()
    return {"providers": rows}
```

## resume

Source: `services/studio-api/src/studio/api/agent_workspace.py:resume`.

```python
@agent_router.post("/runs/{run_id}/resume")
def resume(run_id: uuid.UUID, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = AgentWorkspaceService(db, ctx).resume(run_id)
    db.commit()
    return result
```

## run

Source: `services/studio-api/src/studio/api/agent_workspace.py:run`.

```python
@agent_router.get("/runs/{run_id}")
def run(run_id: uuid.UUID, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return AgentWorkspaceService(db, ctx).run_detail(run_id)
```

## save_model

Source: `services/studio-api/src/studio/api/agent_workspace.py:save_model`.

```python
@agent_router.post("/providers/{provider_id}/models")
def save_model(
    provider_id: uuid.UUID, db: DbSession, ctx: Ctx, body: dict[str, Any]
) -> dict[str, Any]:
    result = AgentWorkspaceService(db, ctx).save_model(provider_id, body)
    db.commit()
    return result
```

## save_policy

Source: `services/studio-api/src/studio/api/agent_workspace.py:save_policy`.

```python
@agent_router.put("/policies")
def save_policy(db: DbSession, ctx: Ctx, body: dict[str, Any]) -> dict[str, Any]:
    result = AgentWorkspaceService(db, ctx).save_policy(body)
    db.commit()
    return result
```

## thread

Source: `services/studio-api/src/studio/api/agent_workspace.py:thread`.

```python
@agent_router.get("/threads/{thread_id}")
def thread(
    thread_id: uuid.UUID,
    db: DbSession,
    ctx: Ctx,
    before: uuid.UUID | None = None,
    limit: int = Query(default=1000, ge=1, le=1000),
) -> dict[str, Any]:
    return AgentWorkspaceService(db, ctx).thread_detail(thread_id, before=before, limit=limit)
```

## threads

Source: `services/studio-api/src/studio/api/agent_workspace.py:threads`.

```python
@agent_router.get("/threads")
def threads(
    db: DbSession,
    ctx: Ctx,
    q: str = Query(default="", max_length=200),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    return AgentWorkspaceService(db, ctx).list_threads_page(q=q, offset=offset, limit=limit)
```

## tool_catalog

Source: `services/studio-api/src/studio/api/agent_workspace.py:tool_catalog`.

```python
@agent_router.get("/tools")
def tool_catalog(ctx: Ctx) -> dict[str, Any]:
    from studio.domain.agent_workspace.tools import catalog

    if ctx.principal_kind != "user":
        from studio.errors import DomainError, ErrorCode

        raise DomainError(ErrorCode.FORBIDDEN, "private tools require a user")
    return {"tools": catalog()}
```

## AgentWorkspaceService.cancel

Source: `services/studio-api/src/studio/domain/agent_workspace/service.py:AgentWorkspaceService.cancel`.

```python
    def cancel(self, run_id: uuid.UUID) -> dict[str, Any]:
        row = self._owned(AgentRun, run_id, lock=True)
        if row.status not in TERMINAL:
            row.cancel_requested = True
            if row.status == "queued":
                row.status = "cancelled"
                row.completed_at = datetime.now(UTC)
        self.db.flush()
        return self.run_json(row)
```

## AgentWorkspaceService.create_run

Source: `services/studio-api/src/studio/domain/agent_workspace/service.py:AgentWorkspaceService.create_run`.

```python
    def create_run(self, thread_id: uuid.UUID, payload: dict[str, Any]) -> dict[str, Any]:
        thread = self._owned(AgentThread, thread_id, lock=True)
        from studio.domain.agent_workspace.workflows import ResearchWorkflow, WorkflowService

        workflow = self.db.scalar(
            select(ResearchWorkflow).where(
                ResearchWorkflow.thread_id == thread_id,
                ResearchWorkflow.workspace_id == self.ctx.workspace_id,
                ResearchWorkflow.owner_id == self.ctx.principal_id,
            )
        )
        if payload.get("workflowId"):
            workflow = WorkflowService(self.db, self.ctx).get(payload["workflowId"])
            if workflow.thread_id != thread_id:
                raise DomainError(
                    ErrorCode.FORBIDDEN, "Workflow belongs to a different conversation"
                )
        existing = self.db.scalar(
            select(AgentRun.id).where(
                AgentRun.thread_id == thread_id,
                AgentRun.workspace_id == self.ctx.workspace_id,
                AgentRun.owner_id == self.ctx.principal_id,
                AgentRun.status.in_(["queued", "running"]),
            )
        )
        if existing:
            raise DomainError(ErrorCode.CONFLICT, "a run is already active in this thread")
        prompt = payload.get("message")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 32000:
            raise DomainError(ErrorCode.VALIDATION, "message must contain 1-32000 characters")
        role = payload.get("role", "planner")
        if role not in ROLES:
            raise DomainError(ErrorCode.VALIDATION, "invalid agent role")
        provider_id = (
            ident(payload["providerId"])
            if payload.get("providerId")
            else (workflow.provider_id if workflow and not payload.get("localModelId") else None)
        )
        model_id, provider_revision = None, None
        local_model_id = ident(payload["localModelId"]) if payload.get("localModelId") else None
        if provider_id and local_model_id:
            raise DomainError(
                ErrorCode.VALIDATION, "select a provider model or private local model"
            )
        local_fingerprint = None
        if local_model_id:
            from studio.domain.learning.workspace_runtime.models import LearningModel

            if workflow:
                WorkflowService(self.db, self.ctx).require_resource(
                    workflow, "model", local_model_id
                )

            local_model = self.db.scalar(
                select(LearningModel).where(
                    LearningModel.id == local_model_id,
                    LearningModel.workspace_id == self.ctx.workspace_id,
                    LearningModel.owner_id == self.ctx.principal_id,
                )
            )
            if local_model is None:
                raise not_found("private local model")
            if local_model.backend not in {"mlx", "transformers"}:
                raise DomainError(
                    ErrorCode.VALIDATION, "this model backend cannot run the research agent"
                )
            local_fingerprint = hashlib.sha256(
                json.dumps(
                    {"location": local_model.location, "details": local_model.details},
                    sort_keys=True,
                    default=str,
                ).encode()
            ).hexdigest()
            model_id = str(local_model.id)
        if provider_id:
            provider = ProviderService(self.db, self.ctx).get(provider_id)
            if not provider.enabled:
                raise DomainError(ErrorCode.CONFLICT, "provider is disabled")
            if workflow:
                if (
                    provider.id != workflow.provider_id
                    or provider.version != workflow.provider_revision
                ):
                    raise DomainError(
                        ErrorCode.FORBIDDEN,
                        "Workflow provider changed; create a new reviewed workflow",
                    )
            else:
                self.ensure_disclosure(provider)
            models = self.providers()
            selected = next((item for item in models if item["id"] == str(provider.id)), None)
            choices = selected["models"] if selected else []
            desired_model = payload.get("modelId")
            model = next(
                (
                    item
                    for item in choices
                    if item["enabled"]
                    and (
                        item["modelId"] == desired_model if desired_model else role in item["roles"]
                    )
                ),
                None,
            )
            if model is None:
                raise DomainError(ErrorCode.VALIDATION, "select an enabled provider model")
            model_id, provider_revision = model["modelId"], provider.version
        autopilot = payload.get("autopilot") is True or workflow is not None
        if autopilot and not workflow and not self.policy()["autopilot"]["enabled"]:
            raise DomainError(
                ErrorCode.FORBIDDEN, "enable bounded autopilot in Agent settings first"
            )
        run = AgentRun(
            workspace_id=self.ctx.workspace_id,
            owner_id=self.ctx.principal_id,
            thread_id=thread.id,
            provider_id=provider_id,
            provider_revision=provider_revision,
            model_id=model_id,
            role=role,
            status="queued",
            prompt=prompt.strip(),
            autopilot=autopilot,
            checkpoint={
                "step": 0,
                "toolCalls": 0,
                "documents": 0,
                "trainingJobs": 0,
                "costUsd": 0.0,
                "messages": [],
                "localModelId": str(local_model_id) if local_model_id else None,
                "localModelFingerprint": local_fingerprint,
                "workflowId": str(workflow.id) if workflow else None,
            },
            cancel_requested=False,
        )
        self.db.add(run)
        self.db.flush()
        self.db.add(
            AgentMessage(
                workspace_id=self.ctx.workspace_id,
                owner_id=self.ctx.principal_id,
                thread_id=thread.id,
                run_id=run.id,
                role="user",
                kind="message",
                content=prompt.strip(),
                refs={},
                created_at=datetime.now(UTC),
            )
        )
        thread.updated_at = datetime.now(UTC)
        self.db.flush()
        return self.run_json(run)
```

## AgentWorkspaceService.create_thread

Source: `services/studio-api/src/studio/domain/agent_workspace/service.py:AgentWorkspaceService.create_thread`.

```python
    def create_thread(self, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = ident(payload["taskId"]) if payload.get("taskId") else None
        if task_id:
            task = self.db.scalar(
                select(ResearchTask).where(
                    ResearchTask.id == task_id, ResearchTask.workspace_id == self.ctx.workspace_id
                )
            )
            if task is None:
                raise not_found("task")
            self.ctx.require("read_project", task.project_id)
        notebook_id = ident(payload["notebookId"]) if payload.get("notebookId") else None
        if notebook_id:
            from studio.domain.library.models import Notebook

            notebook = self.db.scalar(
                select(Notebook).where(
                    Notebook.id == notebook_id,
                    Notebook.workspace_id == self.ctx.workspace_id,
                    Notebook.owner_id == self.ctx.principal_id,
                )
            )
            if notebook is None:
                raise not_found("private notebook")
            if not notebook.ai_enabled:
                raise DomainError(ErrorCode.FORBIDDEN, "AI access is disabled for this notebook")
        row = AgentThread(
            workspace_id=self.ctx.workspace_id,
            owner_id=self.ctx.principal_id,
            title=str(payload.get("title") or "New research")[:200],
            task_id=task_id,
            notebook_id=notebook_id,
        )
        self.db.add(row)
        self.db.flush()
        return self.thread_json(row)
```

## AgentWorkspaceService.discover

Source: `services/studio-api/src/studio/domain/agent_workspace/service.py:AgentWorkspaceService.discover`.

```python
    def discover(self, provider_id: uuid.UUID) -> dict[str, Any]:
        service = ProviderService(self.db, self.ctx)
        service._admin()
        provider = service.get(provider_id)
        data = OpenAICompatibleRuntime(provider, service.secrets).models().get("data")
        if not isinstance(data, list):
            raise DomainError(ErrorCode.CONFLICT, "provider did not return a model list")
        return {
            "models": [
                {"modelId": item["id"]}
                for item in data[:500]
                if isinstance(item, dict)
                and isinstance(item.get("id"), str)
                and len(item["id"]) <= 160
            ]
        }
```

## AgentWorkspaceService.list_threads_page

Source: `services/studio-api/src/studio/domain/agent_workspace/service.py:AgentWorkspaceService.list_threads_page`.

```python
    def list_threads_page(self, *, q: str = "", offset: int = 0, limit: int = 50) -> dict[str, Any]:
        if not isinstance(q, str) or len(q) > 200:
            raise DomainError(
                ErrorCode.VALIDATION, "Conversation search accepts at most 200 characters"
            )
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise DomainError(
                ErrorCode.VALIDATION, "Conversation offset must be a nonnegative integer"
            )
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise DomainError(
                ErrorCode.VALIDATION, "Conversation page size must be between 1 and 100"
            )
        query = q.strip()
        message_scope = (
            AgentMessage.thread_id == AgentThread.id,
            AgentMessage.workspace_id == self.ctx.workspace_id,
            AgentMessage.owner_id == self.ctx.principal_id,
        )
        visible_scope = (
            *message_scope,
            AgentMessage.kind == "message",
            AgentMessage.role.in_(["user", "assistant"]),
        )
        count = (
            select(func.count(AgentMessage.id))
            .where(*visible_scope)
            .correlate(AgentThread)
            .scalar_subquery()
        )
        preview = (
            select(func.substr(AgentMessage.content, 1, 160))
            .where(*visible_scope)
            .order_by(AgentMessage.created_at.desc(), AgentMessage.id.desc())
            .limit(1)
            .correlate(AgentThread)
            .scalar_subquery()
        )
        status = (
            select(AgentRun.status)
            .where(
                AgentRun.thread_id == AgentThread.id,
                AgentRun.workspace_id == self.ctx.workspace_id,
                AgentRun.owner_id == self.ctx.principal_id,
            )
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            .limit(1)
            .correlate(AgentThread)
            .scalar_subquery()
        )
        statement = select(AgentThread, count, preview, status).where(
            AgentThread.workspace_id == self.ctx.workspace_id,
            AgentThread.owner_id == self.ctx.principal_id,
        )
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            matching_message = (
                select(AgentMessage.id)
                .where(*visible_scope, AgentMessage.content.ilike(pattern, escape="\\"))
                .correlate(AgentThread)
                .exists()
            )
            statement = statement.where(
                or_(AgentThread.title.ilike(pattern, escape="\\"), matching_message)
            )
        rows = list(
            self.db.execute(
                statement.order_by(AgentThread.updated_at.desc(), AgentThread.id.desc())
                .offset(offset)
                .limit(limit + 1)
            )
        )
        return {
            "threads": [
                {
                    **self.thread_json(row),
                    "messageCount": int(total),
                    "lastMessagePreview": last_message or "",
                    "lastRunStatus": last_status,
                }
                for row, total, last_message, last_status in rows[:limit]
            ],
            "nextOffset": offset + limit if len(rows) > limit else None,
            "query": query,
            "ownerScope": f"{self.ctx.workspace_id}:{self.ctx.principal_id}",
        }
```

## AgentWorkspaceService.message_json

Source: `services/studio-api/src/studio/domain/agent_workspace/service.py:AgentWorkspaceService.message_json`.

```python
    @staticmethod
    def message_json(row: AgentMessage) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "runId": str(row.run_id) if row.run_id else None,
            "role": row.role,
            "kind": row.kind,
            "content": row.content,
            "refs": row.refs,
            "createdAt": timestamp(row.created_at),
        }
```

## AgentWorkspaceService.model_json

Source: `services/studio-api/src/studio/domain/agent_workspace/service.py:AgentWorkspaceService.model_json`.

```python
    @staticmethod
    def model_json(row: ProviderModel) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "modelId": row.model_id,
            "label": row.label,
            "roles": row.roles,
            "supportsTools": row.supports_tools,
            "apiStyle": row.api_style,
            "enabled": row.enabled,
            "inputPricePerMillionUsd": row.input_price,
            "outputPricePerMillionUsd": row.output_price,
        }
```

## AgentWorkspaceService.policy

Source: `services/studio-api/src/studio/domain/agent_workspace/service.py:AgentWorkspaceService.policy`.

```python
    def policy(self) -> dict[str, Any]:
        row = self.db.scalar(
            select(AgentPolicy).where(
                AgentPolicy.workspace_id == self.ctx.workspace_id,
                AgentPolicy.owner_id == self.ctx.principal_id,
            )
        )
        return copy.deepcopy(row.payload if row else DEFAULT_POLICY)
```

## AgentWorkspaceService.providers

Source: `services/studio-api/src/studio/domain/agent_workspace/service.py:AgentWorkspaceService.providers`.

```python
    def providers(self) -> list[dict[str, Any]]:
        rows = ProviderService(self.db, self.ctx).list()
        result = []
        for row in rows:
            models = list(
                self.db.scalars(
                    select(ProviderModel)
                    .where(
                        ProviderModel.workspace_id == self.ctx.workspace_id,
                        ProviderModel.provider_id == row.id,
                    )
                    .order_by(ProviderModel.created_at)
                )
            )
            # Providers saved after the migration receive a legacy-compatible first model.
            if not models:
                model = ProviderModel(
                    workspace_id=self.ctx.workspace_id,
                    provider_id=row.id,
                    model_id=row.model,
                    label=row.model,
                    roles=sorted(ROLES),
                    supports_tools=row.supports_tools,
                    enabled=True,
                )
                self.db.add(model)
                self.db.flush()
                models = [model]
            result.append(
                {
                    "id": str(row.id),
                    "revision": row.version,
                    "name": row.name,
                    "baseUrl": row.base_url,
                    "enabled": row.enabled,
                    "local": is_loopback_url(row.base_url),
                    "apiStyle": row.api_style,
                    "hasApiKey": row.credential_ref is not None,
                    "models": [self.model_json(model) for model in models],
                }
            )
        return result
```

## AgentWorkspaceService.resume

Source: `services/studio-api/src/studio/domain/agent_workspace/service.py:AgentWorkspaceService.resume`.

```python
    def resume(self, run_id: uuid.UUID) -> dict[str, Any]:
        row = self._owned(AgentRun, run_id, lock=True)
        if row.status not in {"failed", "cancelled", "budget_exhausted", "paused"}:
            raise DomainError(ErrorCode.CONFLICT, "only stopped runs can be resumed")
        from studio.domain.agent_workspace.workflows import WorkflowService, workflow_for_run

        workflow = workflow_for_run(self.db, self.ctx, row, lock=True)
        if workflow and row.checkpoint.get("localModelId"):
            WorkflowService(self.db, self.ctx).require_resource(
                workflow, "model", row.checkpoint["localModelId"]
            )
        if row.provider_id:
            provider = ProviderService(self.db, self.ctx).get(row.provider_id)
            if workflow:
                if (
                    provider.id != workflow.provider_id
                    or provider.version != workflow.provider_revision
                    or not provider.enabled
                ):
                    raise DomainError(ErrorCode.FORBIDDEN, "Workflow provider changed")
            else:
                self.ensure_disclosure(provider)
            row.provider_revision = provider.version
        row.status, row.error, row.cancel_requested = "queued", None, False
        if row.completed_at is not None:
            checkpoint = copy.deepcopy(row.checkpoint)
            checkpoint["step"] = 0
            row.checkpoint = checkpoint
            row.started_at = None
        row.lease_owner, row.lease_expires_at, row.completed_at = None, None, None
        self.db.flush()
        return self.run_json(row)
```

## AgentWorkspaceService.run_detail

Source: `services/studio-api/src/studio/domain/agent_workspace/service.py:AgentWorkspaceService.run_detail`.

```python
    def run_detail(self, run_id: uuid.UUID) -> dict[str, Any]:
        run = self._owned(AgentRun, run_id)
        rows = self.db.scalars(
            select(AgentMessage)
            .where(
                AgentMessage.run_id == run.id,
                AgentMessage.workspace_id == self.ctx.workspace_id,
                AgentMessage.owner_id == self.ctx.principal_id,
            )
            .order_by(AgentMessage.created_at, AgentMessage.id)
        )
        messages = [self.message_json(row) for row in rows]
        return {
            **self.run_json(run),
            "messages": messages,
            "toolEvents": [
                message for message in messages if message["kind"] in {"tool_call", "tool_result"}
            ],
        }
```

## AgentWorkspaceService.run_json

Source: `services/studio-api/src/studio/domain/agent_workspace/service.py:AgentWorkspaceService.run_json`.

```python
    @staticmethod
    def run_json(row: AgentRun) -> dict[str, Any]:
        stats = {
            key: value
            for key, value in (row.checkpoint or {}).items()
            if key not in {"messages", "pendingCalls", "contextEpoch"}
        }
        return {
            "id": str(row.id),
            "threadId": str(row.thread_id),
            "providerId": str(row.provider_id) if row.provider_id else None,
            "modelId": row.model_id,
            "localModelId": (row.checkpoint or {}).get("localModelId"),
            "role": row.role,
            "status": row.status,
            "autopilot": row.autopilot,
            "progress": stats,
            "error": row.error,
            "cancelRequested": row.cancel_requested,
            "createdAt": timestamp(row.created_at),
            "startedAt": timestamp(row.started_at),
            "completedAt": timestamp(row.completed_at),
        }
```

## AgentWorkspaceService.save_automation

Source: `services/studio-api/src/studio/domain/agent_workspace/service.py:AgentWorkspaceService.save_automation`.

```python
    def save_automation(self, thread_id: uuid.UUID, payload: dict[str, Any]) -> dict[str, Any]:
        self._owned(AgentThread, thread_id)
        goal = str(payload.get("researchGoal") or "").strip()
        cadence = payload.get("scheduleHours", 24)
        if not isinstance(cadence, (int, float)) or not 0.05 <= cadence <= 720:
            raise DomainError(ErrorCode.VALIDATION, "scheduleHours must be between 0.05 and 720")
        if payload.get("enabled") and (not goal or len(goal) > 16000):
            raise DomainError(ErrorCode.VALIDATION, "an enabled automation needs a research goal")
        row = self.db.scalar(
            select(AgentPolicy)
            .where(
                AgentPolicy.workspace_id == self.ctx.workspace_id,
                AgentPolicy.owner_id == self.ctx.principal_id,
            )
            .with_for_update()
        )
        if row is None:
            self.save_policy(DEFAULT_POLICY)
            row = self.db.scalar(
                select(AgentPolicy)
                .where(
                    AgentPolicy.workspace_id == self.ctx.workspace_id,
                    AgentPolicy.owner_id == self.ctx.principal_id,
                )
                .with_for_update()
            )
        if row is None:
            raise RuntimeError("owner policy could not be created")
        policy = copy.deepcopy(row.payload)
        if payload.get("enabled") and not policy["autopilot"]["enabled"]:
            raise DomainError(
                ErrorCode.FORBIDDEN, "enable bounded autopilot before scheduling research"
            )
        provider_id = ident(payload["providerId"]) if payload.get("providerId") else None
        if provider_id:
            provider = ProviderService(self.db, self.ctx).get(provider_id)
            self.ensure_disclosure(provider)
        role = payload.get("role", "planner")
        if role not in ROLES:
            raise DomainError(ErrorCode.VALIDATION, "invalid automation model role")
        previous = policy.get("schedules", {}).get(str(thread_id), {})
        automation = {
            "enabled": payload.get("enabled") is True,
            "researchGoal": goal,
            "scheduleHours": float(cadence),
            "providerId": str(provider_id) if provider_id else None,
            "modelId": payload.get("modelId"),
            "localModelId": payload.get("localModelId"),
            "role": role,
            "nextWakeAt": timestamp(datetime.now(UTC) + timedelta(hours=float(cadence))),
            "lastRunId": previous.get("lastRunId"),
            "lastError": None,
        }
        policy.setdefault("schedules", {})[str(thread_id)] = automation
        row.payload = policy
        self.db.flush()
        return copy.deepcopy(automation)
```

## AgentWorkspaceService.save_model

Source: `services/studio-api/src/studio/domain/agent_workspace/service.py:AgentWorkspaceService.save_model`.

```python
    def save_model(self, provider_id: uuid.UUID, payload: dict[str, Any]) -> dict[str, Any]:
        service = ProviderService(self.db, self.ctx)
        service._admin()
        provider = service.get(provider_id)
        model_id = str(payload.get("modelId") or "").strip()
        roles = payload.get("roles", [])
        if (
            not model_id
            or len(model_id) > 160
            or not isinstance(roles, list)
            or any(role not in ROLES for role in roles)
        ):
            raise DomainError(ErrorCode.VALIDATION, "a model ID and valid model roles are required")
        row = self.db.scalar(
            select(ProviderModel).where(
                ProviderModel.workspace_id == self.ctx.workspace_id,
                ProviderModel.provider_id == provider.id,
                ProviderModel.model_id == model_id,
            )
        )
        if row is None:
            row = ProviderModel(
                workspace_id=self.ctx.workspace_id, provider_id=provider.id, model_id=model_id
            )
            self.db.add(row)
        style = payload.get("apiStyle", row.api_style or "inherit")
        if style not in {"inherit", "chat_completions", "responses"}:
            raise DomainError(
                ErrorCode.VALIDATION, "apiStyle must be inherit, chat_completions or responses"
            )
        row.api_style = style
        row.label = str(payload.get("label") or model_id)[:200]
        row.roles = sorted(set(roles))
        # A role names an assignment, rather than an ambiguous membership.
        # Moving reviewer to a second model immediately changes consultations.
        for sibling in self.db.scalars(
            select(ProviderModel).where(
                ProviderModel.workspace_id == self.ctx.workspace_id,
                ProviderModel.provider_id == provider.id,
                ProviderModel.model_id != model_id,
            )
        ):
            sibling.roles = [role for role in sibling.roles if role not in roles]
        row.enabled = payload.get("enabled", True) is True
        row.supports_tools = payload.get("supportsTools", True) is True
        for field, key in (
            ("input_price", "inputPricePerMillionUsd"),
            ("output_price", "outputPricePerMillionUsd"),
        ):
            price = payload.get(key)
            if price is not None and (
                not isinstance(price, (int, float)) or not 0 <= price <= 100000
            ):
                raise DomainError(ErrorCode.VALIDATION, "model token prices must be nonnegative")
            setattr(row, field, float(price) if price is not None else None)
        self.db.flush()
        return self.model_json(row)
```

## AgentWorkspaceService.save_policy

Source: `services/studio-api/src/studio/domain/agent_workspace/service.py:AgentWorkspaceService.save_policy`.

```python
    def save_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        autopilot = payload.get("autopilot") or {}
        for key, maximum in (
            ("maxDocumentsPerDay", 10000),
            ("maxHours", 24),
            ("maxTrainingJobs", 10),
        ):
            value = autopilot.get(key, DEFAULT_POLICY["autopilot"][key])
            if (
                not isinstance(value, (float, int))
                or isinstance(value, bool)
                or not 0 < value <= maximum
            ):
                raise DomainError(
                    ErrorCode.VALIDATION, f"{key} must be positive and at most {maximum}"
                )
        paid = autopilot.get("maxPaidCostUsd", 0)
        if not isinstance(paid, (int, float)) or isinstance(paid, bool) or not 0 <= paid <= 10000:
            raise DomainError(ErrorCode.VALIDATION, "maxPaidCostUsd must be between zero and 10000")
        disclosures = copy.deepcopy(
            payload.get("remoteDisclosures", self.policy().get("remoteDisclosures", {}))
        )
        if not isinstance(disclosures, dict):
            raise DomainError(ErrorCode.VALIDATION, "remoteDisclosures must be a provider-ID map")
        legacy = payload.get("remoteDisclosure")
        if legacy:
            disclosures[str(legacy.get("providerId"))] = legacy
        normalized = {}
        for key, disclosure in disclosures.items():
            if not isinstance(disclosure, dict):
                raise DomainError(ErrorCode.VALIDATION, "invalid provider disclosure")
            provider = ProviderService(self.db, self.ctx).get(ident(key))
            if disclosure.get("providerRevision") != provider.version:
                raise DomainError(ErrorCode.CONFLICT, "provider changed; review disclosure again")
            normalized[str(provider.id)] = {
                "providerId": str(provider.id),
                "providerRevision": provider.version,
                "origin": provider.base_url,
                "allowPrivate": disclosure.get("allowPrivate") is True,
            }
        disclosure = normalized.get(str(legacy.get("providerId"))) if legacy else None
        row = self.db.scalar(
            select(AgentPolicy)
            .where(
                AgentPolicy.workspace_id == self.ctx.workspace_id,
                AgentPolicy.owner_id == self.ctx.principal_id,
            )
            .with_for_update()
        )
        if row is None:
            row = AgentPolicy(workspace_id=self.ctx.workspace_id, owner_id=self.ctx.principal_id)
            self.db.add(row)
        row.payload = {
            "schedules": copy.deepcopy((row.payload or {}).get("schedules", {})),
            "remoteDisclosures": normalized,
            "remoteDisclosure": disclosure,
            "autopilot": {
                "enabled": autopilot.get("enabled") is True,
                "maxDocumentsPerDay": int(autopilot.get("maxDocumentsPerDay", 100)),
                "maxHours": float(autopilot.get("maxHours", 4)),
                "maxTrainingJobs": int(autopilot.get("maxTrainingJobs", 1)),
                "maxPaidCostUsd": float(paid),
            },
        }
        self.db.flush()
        return copy.deepcopy(row.payload)
```

## AgentWorkspaceService.thread_detail

Source: `services/studio-api/src/studio/domain/agent_workspace/service.py:AgentWorkspaceService.thread_detail`.

```python
    def thread_detail(
        self, thread_id: uuid.UUID, *, before: uuid.UUID | None = None, limit: int = 1000
    ) -> dict[str, Any]:
        row = self._owned(AgentThread, thread_id)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise DomainError(ErrorCode.VALIDATION, "Message page size must be between 1 and 1000")
        statement = select(AgentMessage).where(
            AgentMessage.thread_id == row.id,
            AgentMessage.workspace_id == self.ctx.workspace_id,
            AgentMessage.owner_id == self.ctx.principal_id,
        )
        if before is not None:
            cursor = self._owned(AgentMessage, ident(before))
            if cursor.thread_id != row.id:
                raise not_found("conversation message cursor")
            statement = statement.where(
                tuple_(AgentMessage.created_at, AgentMessage.id) < (cursor.created_at, cursor.id)
            )
        recent = list(
            self.db.scalars(
                statement.order_by(AgentMessage.created_at.desc(), AgentMessage.id.desc()).limit(
                    limit + 1
                )
            )
        )
        messages = list(reversed(recent[:limit]))
        runs = self.db.scalars(
            select(AgentRun)
            .where(
                AgentRun.thread_id == row.id,
                AgentRun.workspace_id == self.ctx.workspace_id,
                AgentRun.owner_id == self.ctx.principal_id,
            )
            .order_by(AgentRun.created_at.desc())
            .limit(100)
        )
        return {
            **self.thread_json(row),
            "automation": self.policy().get("schedules", {}).get(str(row.id)),
            "messages": [self.message_json(message) for message in messages],
            "hasEarlierMessages": len(recent) > limit,
            "oldestMessageId": str(messages[0].id) if messages else None,
            "runs": [self.run_json(run) for run in runs],
        }
```

## AgentWorkspaceService.thread_json

Source: `services/studio-api/src/studio/domain/agent_workspace/service.py:AgentWorkspaceService.thread_json`.

```python
    @staticmethod
    def thread_json(row: AgentThread) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "title": row.title,
            "taskId": str(row.task_id) if row.task_id else None,
            "notebookId": str(row.notebook_id) if row.notebook_id else None,
            "createdAt": timestamp(row.created_at),
            "updatedAt": timestamp(row.updated_at),
        }
```
