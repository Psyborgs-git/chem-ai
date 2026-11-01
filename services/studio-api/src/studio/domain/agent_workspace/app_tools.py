"""Additional workbench draft/read tools, with no arbitrary mutation proxy."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext
from studio.config.settings import Settings
from studio.domain.agent_workspace.service import ident
from studio.errors import DomainError, ErrorCode


def catalog() -> list[dict[str, Any]]:
    string, obj = {"type": "string"}, {"type": "object"}
    entries = [
        ("list_projects", "List projects available to this user.", {}, []),
        (
            "list_tasks",
            "List accessible research tasks, optionally for one project.",
            {"projectId": string},
            [],
        ),
        ("read_task", "Read current task objective and workflow state.", {"id": string}, ["id"]),
        (
            "create_project",
            "Create a project to organize research work.",
            {"name": string, "slug": string, "description": string},
            ["name", "slug"],
        ),
        (
            "create_task",
            "Create a draft task without inventing missing task inputs.",
            {
                "projectId": string,
                "title": string,
                "mode": string,
                "objective": string,
                "targetKind": string,
                "modeInputs": obj,
            },
            ["projectId", "title", "mode"],
        ),
        (
            "calculation_status",
            "Read a calculation's actual status, error and result.",
            {"id": string},
            ["id"],
        ),
        (
            "cancel_calculation",
            "Request cancellation of an accessible calculation.",
            {"id": string},
            ["id"],
        ),
        (
            "list_materials",
            "List material identities and their current structure review state.",
            {},
            [],
        ),
        (
            "create_material_identity",
            (
                "Register a material identity with an unreviewed SMILES structure, "
                "for later human review."
            ),
            {
                "name": string,
                "kind": string,
                "structure": string,
                "structureFormat": string,
                "identifiers": {"type": "array", "items": obj},
            },
            ["name", "kind"],
        ),
        ("list_formulations", "List formulation families and draft/reviewed revisions.", {}, []),
        (
            "draft_formulation",
            "Create a draft formulation revision from typed ingredient quantities.",
            {"name": string, "familyId": string, "payload": obj},
            ["payload"],
        ),
        (
            "list_lab_plans",
            "List experiment plan drafts for an accessible task.",
            {"taskId": string},
            ["taskId"],
        ),
        (
            "draft_lab_plan",
            "Create an experiment plan draft; release still uses normal review.",
            {"taskId": string, "title": string, "payload": obj},
            ["taskId", "title", "payload"],
        ),
        (
            "read_lab_results",
            "Read actual recorded experiment executions and replication results.",
            {"planId": string},
            ["planId"],
        ),
        (
            "list_optimization_campaigns",
            "List optimization campaigns and their real status for a task.",
            {"taskId": string},
            ["taskId"],
        ),
    ]
    return [
        {
            "name": name,
            "description": description,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        }
        for name, description, properties, required in entries
    ]


def _record(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {"id": str(row.id)}
    for field in fields:
        value = getattr(row, field, None)
        key = field.split("_")[0] + "".join(part.title() for part in field.split("_")[1:])
        result[key] = str(value) if hasattr(value, "hex") else value
    return result


def execute(
    db: Session, ctx: ServiceContext, settings: Settings, name: str, args: dict[str, Any]
) -> Any:
    from studio.domain.projects.service import ProjectService
    from studio.domain.tasks.service import TaskService
    from studio.persistence.models import (
        FormulationFamily,
        FormulationRevision,
        MaterialIdentity,
        Project,
        ResearchTask,
    )

    if name == "list_projects":
        return [
            _record(row, ("name", "slug", "description"))
            for row in db.scalars(
                select(Project).where(Project.workspace_id == ctx.workspace_id).limit(100)
            )
            if ctx.has("read_project", row.id)
        ]
    if name == "list_tasks":
        query = select(ResearchTask).where(ResearchTask.workspace_id == ctx.workspace_id)
        if args.get("projectId"):
            query = query.where(ResearchTask.project_id == ident(args["projectId"]))
        return [
            _record(row, ("title", "project_id", "mode", "workflow_state", "objective"))
            for row in db.scalars(query.order_by(ResearchTask.updated_at.desc()).limit(100))
            if ctx.has("read_project", row.project_id)
        ]
    if name == "read_task":
        return _record(
            TaskService(db, ctx).get(ident(args["id"])),
            (
                "title",
                "project_id",
                "mode",
                "workflow_state",
                "objective",
                "mode_inputs",
                "current_contract_revision_id",
            ),
        )
    if name == "create_project":
        return _record(
            ProjectService(db, ctx).create(
                name=args["name"], slug=args["slug"], description=args.get("description")
            ),
            ("name", "slug"),
        )
    if name == "create_task":
        return _record(
            TaskService(db, ctx).create(
                project_id=ident(args["projectId"]),
                title=args["title"],
                mode=args["mode"],
                objective=args.get("objective"),
                target_kind=args.get("targetKind"),
                mode_inputs=args.get("modeInputs"),
            ),
            ("title", "project_id", "workflow_state"),
        )
    if name in {"calculation_status", "cancel_calculation"}:
        from studio.domain.runs.queue import RunService

        service = RunService(db, ctx)
        row = (
            service.get(ident(args["id"]))
            if name == "calculation_status"
            else service.request_cancel(ident(args["id"]))
        )
        if row.task_id:
            TaskService(db, ctx).get(row.task_id)
        else:
            ctx.require("read_project")
        return _record(row, ("kind", "status", "task_id", "result_summary", "error", "request"))
    if name in {"list_materials", "list_formulations"}:
        ctx.require("read_project")
        if name == "list_materials":
            return [
                _record(
                    row,
                    (
                        "name",
                        "kind",
                        "structure",
                        "structure_format",
                        "structure_review_state",
                        "identifiers",
                    ),
                )
                for row in db.scalars(
                    select(MaterialIdentity)
                    .where(MaterialIdentity.workspace_id == ctx.workspace_id)
                    .limit(100)
                )
            ]
        return {
            "families": [
                _record(row, ("name", "description"))
                for row in db.scalars(
                    select(FormulationFamily)
                    .where(FormulationFamily.workspace_id == ctx.workspace_id)
                    .limit(100)
                )
            ],
            "revisions": [
                _record(row, ("family_id", "revision", "status", "payload"))
                for row in db.scalars(
                    select(FormulationRevision)
                    .where(FormulationRevision.workspace_id == ctx.workspace_id)
                    .limit(100)
                )
            ],
        }
    if name == "create_material_identity":
        from studio.domain.materials.service import MaterialService

        return _record(
            MaterialService(db, ctx).create_identity(
                name=args["name"],
                kind=args["kind"],
                structure=args.get("structure"),
                structure_format=args.get("structureFormat"),
                identifiers=args.get("identifiers"),
            ),
            ("name", "kind", "structure_review_state"),
        )
    if name == "draft_formulation":
        from studio.domain.materials.formulations import FormulationService

        formulations = FormulationService(db, ctx)
        family_id = (
            ident(args["familyId"])
            if args.get("familyId")
            else formulations.create_family(name=args.get("name", "Research formulation")).id
        )
        return _record(
            formulations.draft_revision(family_id=family_id, payload=args["payload"]),
            ("family_id", "revision", "status", "payload"),
        )
    if name in {"list_lab_plans", "draft_lab_plan", "read_lab_results"}:
        from studio.domain.lab.plans import LabPlanService

        plans = LabPlanService(db, ctx)
        if name == "list_lab_plans":
            return [
                _record(row, ("task_id", "title", "status", "payload", "blockers"))
                for row in plans.list_for_task(ident(args["taskId"]))
            ]
        if name == "draft_lab_plan":
            return _record(
                plans.create(ident(args["taskId"]), title=args["title"], payload=args["payload"]),
                ("task_id", "title", "status", "payload", "blockers"),
            )
        from studio.domain.lab.measurements import LabMeasurementService

        measurements = LabMeasurementService(db, ctx)
        return [
            {
                **_record(row, ("status", "observations", "deviations", "actuals")),
                "replication": measurements.replication_summary(row.id),
            }
            for row in measurements.list_executions(ident(args["planId"]))
        ]
    if name == "list_optimization_campaigns":
        from studio.domain.learning.optimization import OptimizationService

        return [
            _record(row, ("task_id", "status", "definition", "history"))
            for row in OptimizationService(db, ctx, settings).list(ident(args["taskId"]))
        ]
    raise DomainError(ErrorCode.VALIDATION, "unknown workbench tool")
