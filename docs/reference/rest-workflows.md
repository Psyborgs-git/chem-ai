# Research workflow API

Human-created public-source workflows with pinned provider revisions and bounded paid/training/simulation budgets.

[Shared authentication, errors and transport](rest-overview.md). Examples use synthetic values; replace resource IDs with records from your workspace.

## GET /api/research-workflows

List public-source research workflows owned by the current user.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No body; identifier UUID for detail.

**Response:** id, name, threadId, notebookId, providerId, specification, ledger and paidCostUsd; list returns an array. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/research-workflows HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** This owner has no public-source workflows.

```http
HTTP/1.1 200 OK
Content-Type: application/json

[]
```

**Failure response example:** The session cookie is omitted and no Bearer session token is supplied.

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "errors": [
    {
      "code": "UNAUTHENTICATED",
      "message": "session required",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [workflows](contracts-workflows.md#workflows), [WorkflowService.describe](contracts-workflows.md#workflowservicedescribe), [WorkflowService.describe](contracts-workflows.md#workflowservicedescribe).

Source: `services/studio-api/src/studio/api/research_workflows.py:16` (`workflows`).

## GET /api/research-workflows/{identifier}

Read one owned workflow and its accounting ledger.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No body; identifier UUID for detail.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `identifier` (required) | path | `uuid.UUID` | `required` |

**Response:** id, name, threadId, notebookId, providerId, specification, ledger and paidCostUsd; list returns an array. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/research-workflows/00000000-0000-4000-8000-000000000014 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000014",
  "name": "Synthetic public-source research",
  "threadId": "00000000-0000-4000-8000-000000000008",
  "notebookId": "00000000-0000-4000-8000-000000000004",
  "providerId": "00000000-0000-4000-8000-000000000010",
  "specification": {
    "publicSourcesOnly": true,
    "limits": {
      "trainingSeconds": 600.0,
      "simulationSeconds": 600.0,
      "paidCostUsd": 1.0
    },
    "goal": "Review public ethanol descriptor sources."
  },
  "ledger": {
    "resources": {},
    "allocations": [],
    "stages": []
  },
  "paidCostUsd": 0
}
```

**Failure response example:** Private research workflow not found.

```http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "Private research workflow not found",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [detail](contracts-workflows.md#detail), [WorkflowService.get](contracts-workflows.md#workflowserviceget), [WorkflowService.describe](contracts-workflows.md#workflowservicedescribe).

Source: `services/studio-api/src/studio/api/research_workflows.py:39` (`detail`).

## POST /api/research-workflows

Create a human-approved bounded public-source workflow and its notebook/thread.

**Access:** Authenticated human user; workflow creation also creates a private AgentWorkspaceService thread, which enforces kind=user.

**Request:** providerId required; optional name, goal, trainingSeconds, simulationSeconds and paidCostUsd. Positive bounded budgets and an enabled provider are required.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `body` (required) | JSON body | `dict[str, Any]` | `required` |

**Response:** Workflow descriptor with specification.publicSourcesOnly=true, pinned provider revision and ledger accounting. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/research-workflows HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "name": "Synthetic public-source research",
  "providerId": "00000000-0000-4000-8000-000000000010",
  "goal": "Review public ethanol descriptor sources.",
  "trainingSeconds": 600,
  "simulationSeconds": 600,
  "paidCostUsd": 1
}
```

**Success response example:** The selected provider exists and is enabled; this human action creates a workflow notebook/thread and fixed positive limits. The example does not start a research run or authorize private-source disclosure.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000014",
  "name": "Synthetic public-source research",
  "threadId": "00000000-0000-4000-8000-000000000008",
  "notebookId": "00000000-0000-4000-8000-000000000004",
  "providerId": "00000000-0000-4000-8000-000000000010",
  "specification": {
    "publicSourcesOnly": true,
    "limits": {
      "trainingSeconds": 600.0,
      "simulationSeconds": 600.0,
      "paidCostUsd": 1.0
    },
    "goal": "Review public ethanol descriptor sources."
  },
  "ledger": {
    "resources": {},
    "allocations": [],
    "stages": []
  },
  "paidCostUsd": 0
}
```

**Failure response example:** Select an enabled provider.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "errors": [
    {
      "code": "VALIDATION",
      "message": "Select an enabled provider",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [create](contracts-workflows.md#create), [WorkflowService.create](contracts-workflows.md#workflowservicecreate), [WorkflowService.describe](contracts-workflows.md#workflowservicedescribe).

Source: `services/studio-api/src/studio/api/research_workflows.py:32` (`create`).
