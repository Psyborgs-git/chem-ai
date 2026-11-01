"""GraphQL private surfaces preserve ownership and optimistic revisions."""

from types import SimpleNamespace

import pytest
from chem_studio_policy.capabilities import capabilities_for_role

from studio.api.graphql.schema import schema
from studio.auth.context import load_context
from studio.config.settings import Settings
from studio.persistence.models import Principal, PrincipalCapability, Workspace

pytestmark = pytest.mark.integration


def test_graphql_private_library_is_owner_only_and_mutations_use_revision_checks(session, tmp_path):
    workspace = Workspace(slug="graphql-private", display_name="Private GraphQL")
    session.add(workspace)
    session.flush()
    owners = []
    for login in ("author", "workspace-admin"):
        user = Principal(workspace_id=workspace.id, kind="user", login=login, display_name=login)
        session.add(user)
        session.flush()
        for capability in capabilities_for_role("owner"):
            session.add(
                PrincipalCapability(
                    workspace_id=workspace.id,
                    principal_id=user.id,
                    capability=capability,
                )
            )
        session.flush()
        owners.append(load_context(session, workspace.id, user.id))

    def context(owner):
        return SimpleNamespace(
            db=session, settings=Settings(vault_root=tmp_path), service_ctx=lambda: owner
        )

    created = schema.execute_sync(
        'mutation { notebookCreate(title:"Private chemistry") }',
        context_value=context(owners[0]),
    )
    assert not created.errors
    notebook = created.data["notebookCreate"]
    page_result = schema.execute_sync(
        "mutation($input:JSON!){notebookPageCreate(input:$input)}",
        variable_values={
            "input": {
                "notebookId": notebook["id"],
                "title": "Private formula",
                "kind": "formula",
                "content": {"latex": "c=n/V"},
            }
        },
        context_value=context(owners[0]),
    )
    assert not page_result.errors
    page = page_result.data["notebookPageCreate"]
    query = (
        "query{privateLibrary{notebooks{id title aiEnabled trainingEnabled} "
        "pages{id title content revision}} privateLearning{datasets models jobs}}"
    )
    author = schema.execute_sync(query, context_value=context(owners[0]))
    assert not author.errors
    assert author.data["privateLibrary"]["pages"][0]["content"]["latex"] == "c=n/V"
    outsider = schema.execute_sync(query, context_value=context(owners[1]))
    assert not outsider.errors
    assert outsider.data["privateLibrary"] == {"notebooks": [], "pages": []}
    assert outsider.data["privateLearning"] == {"datasets": [], "models": [], "jobs": []}
    conflict = schema.execute_sync(
        "mutation($id:ID!,$input:JSON!){notebookPageUpdate(id:$id,input:$input)}",
        variable_values={
            "id": page["id"],
            "input": {"title": "overwrite", "expectedRevision": 999},
        },
        context_value=context(owners[0]),
    )
    assert conflict.errors
    session.rollback()
    retained = schema.execute_sync(query, context_value=context(owners[0]))
    assert retained.data["privateLibrary"]["pages"][0]["title"] == "Private formula"
