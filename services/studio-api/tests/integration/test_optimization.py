"""CS-0603 application/persistence/authorization; synthetic data only."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from starlette.testclient import TestClient
from strawberry import relay
from workers.optimization.runtime import IsolatedBayBE

from engine_adapter_baybe.contracts import Recommendation
from studio.api.app import create_app
from studio.auth.context import ServiceContext, load_context
from studio.config.settings import Settings
from studio.domain.learning.datasets import DatasetService
from studio.domain.learning.optimization import OptimizationService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    LabBatch,
    LabExecution,
    LabSample,
    Measurement,
    OptimizationCampaign,
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    SuccessContractRevision,
    Workspace,
)

pytestmark = pytest.mark.integration


def raw_spec() -> dict:
    return json.loads(Path("fixtures/synthetic/optimization-campaign.json").read_text())["spec"]


@pytest.fixture()
def setup(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> tuple[ServiceContext, ResearchTask, OptimizationService]:
    def fixture_recommend(self: object, spec: object, **kwargs: object) -> Recommendation:
        # Application tests are dependency-free fixtures, not live BayBE evidence.
        reserved = kwargs["reserved"]
        rows = [{"a": str(a), "b": str(100 - a)} for a in (0, 25, 50, 75)]
        available = [p for p in rows if p not in reserved]
        return Recommendation(
            status="suggested" if available else "exhausted",
            suggestions=available[: kwargs["batch_size"]],
            rejected={},
            seed=17,
            recommender="fixture-only",
            scientific_status="fixture_only",
        )

    monkeypatch.setattr(IsolatedBayBE, "recommend", fixture_recommend)
    ws = Workspace(slug="optimization", display_name="Synthetic optimization tests")
    session.add(ws)
    session.flush()
    owner = Principal(workspace_id=ws.id, kind="user", login="owner", display_name="fixture-owner")
    session.add(owner)
    session.flush()
    for cap in capabilities_for_role("owner"):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=owner.id, capability=cap))
    project = Project(workspace_id=ws.id, slug="fixture", name="Fixture-only")
    session.add(project)
    session.flush()
    task = ResearchTask(
        workspace_id=ws.id,
        project_id=project.id,
        mode="discover",
        title="Synthetic, non-scientific",
        target_kind="formulation",
        workflow_state="active",
    )
    session.add(task)
    session.flush()
    payload = json.loads(Path("fixtures/synthetic/contract-improve.json").read_text())
    contract = SuccessContractRevision(
        workspace_id=ws.id,
        task_id=task.id,
        revision=1,
        status="frozen",
        payload=payload,
        content_hash="f" * 64,
    )
    session.add(contract)
    session.flush()
    task.current_contract_revision_id = contract.id
    session.flush()
    ctx = load_context(session, ws.id, owner.id)
    return ctx, task, OptimizationService(session, ctx, Settings(profile_optimization=True))


def recommend(
    service: OptimizationService, row: OptimizationCampaign, key: str = "r1", batch: int = 1
) -> OptimizationCampaign:
    return service.command(
        row.id, expected_revision=row.revision, key=key, operation="recommend", batch_size=batch
    )


def test_at0603_2_unsupported_campaign_creation_rejected(session: Session, setup: tuple) -> None:
    _, task, service = setup
    raw = raw_spec()
    raw["constraints"][0]["scope"] = "interpoint"
    with pytest.raises(DomainError) as exc:
        service.create(task.id, raw, "bad")
    assert exc.value.code == ErrorCode.ENGINE_UNSUPPORTED_INPUT

    assert session.query(OptimizationCampaign).count() == 0


def test_at0603_3_restart_idempotency_cancel_pending(session: Session, setup: tuple) -> None:
    _, task, service = setup
    row = service.create(task.id, raw_spec(), "create")
    assert service.create(task.id, raw_spec(), "create").id == row.id
    row = recommend(service, row, batch=2)
    experiments = row.replay["experiments"]
    cancelled, pending = experiments
    revision = row.revision
    session.commit()
    session.expire_all()
    row = service.command(
        row.id, expected_revision=1, key="r1", operation="recommend", batch_size=2
    )
    assert row.revision == revision and len(row.replay["experiments"]) == 2
    service.command(
        row.id,
        expected_revision=row.revision,
        key="cancel",
        operation="cancelled",
        experiment_id=cancelled["id"],
        reason="fixture cancellation",
    )
    recommend(service, row, key="r2")
    assert all(e["outcome"] is None for e in row.replay["experiments"])
    assert row.replay["experiments"][0]["status"] == "cancelled"
    assert row.replay["experiments"][1]["status"] == "pending"
    assert row.replay["experiments"][-1]["parameters"] not in [
        cancelled["parameters"],
        pending["parameters"],
    ]
    with pytest.raises(DomainError) as exc:
        service.command(row.id, expected_revision=1, key="stale", operation="recommend")
    assert exc.value.code == ErrorCode.REVISION_CONFLICT


def test_reviewed_observation_frozen_rights_and_source_drift(
    session: Session, setup: tuple
) -> None:
    ctx, task, service = setup
    row = recommend(service, service.create(task.id, raw_spec(), "create"))
    experiment = row.replay["experiments"][0]
    execution = LabExecution(workspace_id=ctx.workspace_id, task_id=task.id, historical=True)
    session.add(execution)
    session.flush()
    batch = LabBatch(workspace_id=ctx.workspace_id, execution_id=execution.id, label="fixture")
    session.add(batch)
    session.flush()
    sample = LabSample(
        workspace_id=ctx.workspace_id, batch_id=batch.id, label="synthetic", kind="aliquot"
    )
    session.add(sample)
    session.flush()
    m = Measurement(
        workspace_id=ctx.workspace_id,
        sample_id=sample.id,
        method=raw_spec()["target"]["method"],
        metric=raw_spec()["target"]["name"],
        repeat_type="independent_batch",
        value_type="numeric",
        value={"kind": "numeric", "value": "0", "unit": "dimensionless"},
        status="accepted",
        reviewed_by=ctx.principal_id,
        conditions={
            "actual": {
                "optimization": {
                    "campaignId": str(row.id),
                    "experimentId": experiment["id"],
                    "parameters": experiment["parameters"],
                    "context": raw_spec()["context"],
                }
            }
        },
    )
    session.add(m)
    session.flush()
    datasets = DatasetService(session, ctx)
    snapshot = datasets.build(purpose="property_prediction", name="fixture-only", task_id=task.id)
    datasets.freeze(snapshot.id)
    service.command(
        row.id,
        expected_revision=row.revision,
        key="observe",
        operation="observed",
        experiment_id=experiment["id"],
        measurement_id=m.id,
        snapshot_id=snapshot.id,
    )
    assert row.replay["experiments"][0]["outcome"] == "0"
    assert row.replay["experiments"][0]["measurement_id"] == str(m.id)
    m.status = "superseded"
    session.flush()
    with pytest.raises(DomainError) as exc:
        recommend(service, row, key="after-drift")
    assert exc.value.code == ErrorCode.EVAL_CONTAMINATION


def test_no_observation_values_allowed_on_cancel(session: Session, setup: tuple) -> None:
    _, task, service = setup
    row = recommend(service, service.create(task.id, raw_spec(), "create"))
    with pytest.raises(DomainError) as exc:
        service.command(
            row.id,
            expected_revision=row.revision,
            key="bad-zero",
            operation="cancelled",
            experiment_id=row.replay["experiments"][0]["id"],
            measurement_id=uuid.uuid4(),
            reason="cancel",
        )
    assert exc.value.code == ErrorCode.VALIDATION
    assert row.replay["experiments"][0]["outcome"] is None


def test_permissions_and_cross_workspace_denied(session: Session, setup: tuple) -> None:
    ctx, task, service = setup
    row = service.create(task.id, raw_spec(), "create")
    # Even direct owner grants are filtered for agent-kind principals server-side.
    from chem_studio_policy.capabilities import effective_grants

    agent = ServiceContext(
        session=session,
        workspace_id=ctx.workspace_id,
        principal_id=ctx.principal_id,
        principal_kind="agent",
        grants=effective_grants("agent", ctx.grants),
    )
    with pytest.raises(DomainError) as exc:
        OptimizationService(session, agent, Settings()).create(task.id, raw_spec(), "agent")
    assert exc.value.code == ErrorCode.FORBIDDEN
    stranger = ServiceContext(
        session=session,
        workspace_id=uuid.uuid4(),
        principal_id=ctx.principal_id,
        principal_kind="user",
        grants=ctx.grants,
    )
    with pytest.raises(DomainError) as exc:
        OptimizationService(session, stranger, Settings()).command(
            row.id, expected_revision=1, key="foreign", operation="recommend"
        )
    assert exc.value.code == ErrorCode.NOT_FOUND


def test_campaign_definition_immutable_and_profile_off(session: Session, setup: tuple) -> None:
    ctx, task, service = setup
    row = service.create(task.id, raw_spec(), "create")
    with pytest.raises(DBAPIError), session.begin_nested():
        session.execute(
            text("UPDATE optimization_campaigns SET spec_digest = 'changed' WHERE id = :id"),
            {"id": row.id},
        )
    disabled = OptimizationService(session, ctx, Settings())
    with pytest.raises(DomainError) as exc:
        recommend(disabled, row)
    assert exc.value.code == ErrorCode.ENGINE_UNAVAILABLE
    assert row.replay["experiments"] == []


def test_engine_failure_does_not_commit_pending(
    session: Session, setup: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from engine_adapter_baybe import EngineFailure

    _, task, service = setup
    row = service.create(task.id, raw_spec(), "create")

    def unavailable(*args: object, **kwargs: object) -> None:
        raise EngineFailure("ENGINE_UNAVAILABLE", "fixture worker failure")

    monkeypatch.setattr(IsolatedBayBE, "recommend", unavailable)
    with pytest.raises(DomainError):
        recommend(service, row)
    assert row.revision == 1 and row.commands == {} and row.replay["experiments"] == []


def test_direction_and_contract_hard_constraints_fail_closed(
    session: Session, setup: tuple
) -> None:
    _, task, service = setup
    raw = raw_spec()
    raw["target"]["mode"] = "minimize"
    with pytest.raises(DomainError) as exc:
        service.create(task.id, raw, "wrong-direction")
    assert exc.value.code == ErrorCode.ENGINE_UNSUPPORTED_INPUT
    prior = session.get(SuccessContractRevision, task.current_contract_revision_id)
    next_contract = SuccessContractRevision(
        workspace_id=task.workspace_id,
        task_id=task.id,
        revision=2,
        status="frozen",
        payload={**prior.payload, "hard_constraints": [{"fixture_unsupported": True}]},
        content_hash="e" * 64,
    )
    session.add(next_contract)
    session.flush()
    task.current_contract_revision_id = next_contract.id
    session.flush()
    with pytest.raises(DomainError) as exc:
        service.create(task.id, raw_spec(), "unknown-hard-constraint")
    assert exc.value.code == ErrorCode.ENGINE_UNSUPPORTED_INPUT


def test_graphql_create_recommend_and_query_scope(
    db_url: str, session: Session, setup: tuple
) -> None:
    from studio.auth.setup import hash_password

    ctx, task, _ = setup
    owner = session.get(Principal, ctx.principal_id)
    owner.credential_hash = hash_password("fixture-test-password")
    session.commit()
    client = TestClient(create_app(Settings(database_url=db_url, profile_optimization=True)))
    headers = {"host": "127.0.0.1:8787", "origin": "http://127.0.0.1:8787"}
    login = client.post(
        "/api/auth/login",
        json={"login": "owner", "password": "fixture-test-password"},
        headers=headers,
    )
    assert login.status_code == 200, login.text
    task_id = str(relay.GlobalID(type_name="Task", node_id=str(task.id)))
    query = """mutation($input: OptimizationCreateInput!) {
      optimization { create(input: $input) {
        task { id optimizationCampaigns { id revision manifest } } errors { code }
      } }
    }"""
    result = client.post(
        "/graphql",
        headers=headers,
        json={
            "query": query,
            "variables": {
                "input": {
                    "taskId": task_id,
                    "definition": raw_spec(),
                    "idempotencyKey": "gql-create",
                }
            },
        },
    ).json()
    assert "errors" not in result, result
    created = result["data"]["optimization"]["create"]
    assert created["errors"] == [], created
    campaign = created["task"]["optimizationCampaigns"][0]
    command = """mutation($input: OptimizationCommandInput!) {
      optimization { command(input: $input) {
        task { optimizationCampaigns { revision manifest } } errors { code }
      } }
    }"""
    result = client.post(
        "/graphql",
        headers=headers,
        json={
            "query": command,
            "variables": {
                "input": {
                    "campaignId": campaign["id"],
                    "expectedRevision": 1,
                    "operation": "recommend",
                    "batchSize": 1,
                    "idempotencyKey": "gql-recommend",
                }
            },
        },
    ).json()
    assert "errors" not in result, result
    returned = result["data"]["optimization"]["command"]
    assert returned["errors"] == [], returned
    manifest = returned["task"]["optimizationCampaigns"][0]["manifest"]
    assert manifest["scientificStatus"] == "fixture_only"
    assert manifest["state"]["experiments"][0]["outcome"] is None
    assert "scratch_dir" not in json.dumps(manifest)
