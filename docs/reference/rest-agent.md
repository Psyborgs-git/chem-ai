# Private agent API

Provider model assignments, disclosure policies, private threads, bounded recurring work and durable agent runs.

[Shared authentication, errors and transport](rest-overview.md). Examples use synthetic values; replace resource IDs with records from your workspace.

## GET /api/agent-workspace/policies

Read private disclosure, automation and scheduling policy.

**Access:** Authenticated human user; private workspace/owner ownership checks apply in the service.

**Request:** No body.

**Response:** remoteDisclosures map, legacy remoteDisclosure, autopilot limits and schedules. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/agent-workspace/policies HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** No private policy has been saved; these are the defaults.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "remoteDisclosures": {},
  "remoteDisclosure": null,
  "autopilot": {
    "enabled": false,
    "maxDocumentsPerDay": 100,
    "maxHours": 4,
    "maxTrainingJobs": 1,
    "maxPaidCostUsd": 0
  }
}
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

**Exact JSON rules and response serialization:** [policy](contracts-agent.md#policy), [AgentWorkspaceService.policy](contracts-agent.md#agentworkspaceservicepolicy).

Source: `services/studio-api/src/studio/api/agent_workspace.py:55` (`policy`).

## GET /api/agent-workspace/providers

List configured providers and their model/role assignments.

**Access:** Authenticated human user; private workspace/owner ownership checks apply in the service.

**Request:** No body.

**Response:** providers array; API keys are not returned. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/agent-workspace/providers HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** No provider has been configured. Configured results include revision, destination, enabled/local/API style, hasApiKey, and child models; never plaintext keys.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "providers": []
}
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

**Exact JSON rules and response serialization:** [providers](contracts-agent.md#providers), [AgentWorkspaceService.providers](contracts-agent.md#agentworkspaceserviceproviders), [AgentWorkspaceService.model_json](contracts-agent.md#agentworkspaceservicemodel_json).

Source: `services/studio-api/src/studio/api/agent_workspace.py:34` (`providers`).

## GET /api/agent-workspace/runs/{run_id}

Read one private run and its tool/message progress.

**Access:** Authenticated human user; private workspace/owner ownership checks apply in the service.

**Request:** run_id UUID; no body.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `run_id` (required) | path | `uuid.UUID` | `required` |

**Response:** Run detail/descriptor with status, cancellation, progress, error and timestamps. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/agent-workspace/runs/00000000-0000-4000-8000-000000000009 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000009",
  "threadId": "00000000-0000-4000-8000-000000000008",
  "providerId": "00000000-0000-4000-8000-000000000010",
  "modelId": "example-model",
  "localModelId": null,
  "role": "planner",
  "status": "queued",
  "autopilot": false,
  "progress": {
    "step": 0,
    "toolCalls": 0,
    "documents": 0,
    "trainingJobs": 0,
    "costUsd": 0.0,
    "localModelId": null,
    "localModelFingerprint": null,
    "workflowId": null
  },
  "error": null,
  "cancelRequested": false,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "startedAt": null,
  "completedAt": null,
  "messages": [],
  "toolEvents": []
}
```

**Failure response example:** private agent resource not found or not accessible.

```http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "private agent resource not found or not accessible",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [run](contracts-agent.md#run), [AgentWorkspaceService.run_detail](contracts-agent.md#agentworkspaceservicerun_detail), [AgentWorkspaceService.run_json](contracts-agent.md#agentworkspaceservicerun_json).

Source: `services/studio-api/src/studio/api/agent_workspace.py:114` (`run`).

## GET /api/agent-workspace/threads

Search and page private thread summaries.

**Access:** Authenticated human user; private workspace/owner ownership checks apply in the service.

**Request:** Optional q, offset and limit query arguments, bounded as listed below.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `q` (optional) | query | `str` | `Query(default='', max_length=200)` |
| `offset` (optional) | query | `int` | `Query(default=0, ge=0)` |
| `limit` (optional) | query | `int` | `Query(default=50, ge=1, le=100)` |

**Response:** Thread summaries and pagination/count information; does not return complete message histories. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/agent-workspace/threads?q=ethanol&offset=0&limit=20 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** No owned threads match; pagination reports no next offset.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "threads": [],
  "nextOffset": null,
  "query": "ethanol",
  "ownerScope": "00000000-0000-4000-8000-000000000001:00000000-0000-4000-8000-000000000002"
}
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

**Exact JSON rules and response serialization:** [threads](contracts-agent.md#threads), [AgentWorkspaceService.list_threads_page](contracts-agent.md#agentworkspaceservicelist_threads_page), [AgentWorkspaceService.thread_json](contracts-agent.md#agentworkspaceservicethread_json).

Source: `services/studio-api/src/studio/api/agent_workspace.py:67` (`threads`).

## GET /api/agent-workspace/threads/{thread_id}

Read a private thread and bounded message history.

**Access:** Authenticated human user; private workspace/owner ownership checks apply in the service.

**Request:** thread_id UUID; optional before message UUID and bounded limit.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `thread_id` (required) | path | `uuid.UUID` | `required` |
| `before` (optional) | query | `uuid.UUID \| None` | `None` |
| `limit` (optional) | query | `int` | `Query(default=1000, ge=1, le=1000)` |

**Response:** Thread, messages, runs, automation and pagination fields; message entries include id, runId, role, kind, content, refs and createdAt. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/agent-workspace/threads/00000000-0000-4000-8000-000000000008?limit=50 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000008",
  "title": "Ethanol literature review",
  "taskId": null,
  "notebookId": null,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00",
  "automation": null,
  "messages": [],
  "hasEarlierMessages": false,
  "oldestMessageId": null,
  "runs": []
}
```

**Failure response example:** private agent resource not found or not accessible.

```http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "private agent resource not found or not accessible",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [thread](contracts-agent.md#thread), [AgentWorkspaceService.thread_detail](contracts-agent.md#agentworkspaceservicethread_detail), [AgentWorkspaceService.thread_json](contracts-agent.md#agentworkspaceservicethread_json), [AgentWorkspaceService.message_json](contracts-agent.md#agentworkspaceservicemessage_json), [AgentWorkspaceService.run_json](contracts-agent.md#agentworkspaceservicerun_json).

Source: `services/studio-api/src/studio/api/agent_workspace.py:85` (`thread`).

## GET /api/agent-workspace/tools

List the private agent tool catalog.

**Access:** Authenticated principal with kind=user.

**Request:** No body.

**Response:** tools array describing names, arguments and supported actions. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/agent-workspace/tools HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** This source-defined tool catalog contains schemas only. Reading it does not invoke any tool or grant its capability.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "tools": [
    {
      "name": "search_studio_docs",
      "description": "Search bundled Chemistry Studio Help for using screens, editing notes, setup, training and troubleshooting. Use this first for app/how-to questions; returns article IDs, excerpts and stable /help links. No private workspace data.",
      "input_schema": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200
          },
          "section": {
            "type": "string",
            "enum": [
              "usage",
              "development",
              "operations",
              "reference"
            ]
          },
          "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10
          }
        },
        "required": [
          "query"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "read_studio_doc",
      "description": "Read an allowlisted Studio Help article/heading returned by search_studio_docs. Cite its /help URL and explain the actual documented UI steps. Use next_offset with the same article/heading to continue text; next_heading_offset pages the table of contents. Manuals describe behavior, not live readiness or job success.",
      "input_schema": {
        "type": "object",
        "properties": {
          "article_id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 160
          },
          "heading": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1024
          },
          "offset": {
            "type": "integer",
            "minimum": 0,
            "maximum": 2097152
          },
          "max_chars": {
            "type": "integer",
            "minimum": 1,
            "maximum": 6000
          },
          "heading_offset": {
            "type": "integer",
            "minimum": 0,
            "maximum": 10000
          }
        },
        "required": [
          "article_id"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "search_evidence",
      "description": "Lexical search over scoped, rights-gated sources.",
      "input_schema": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string"
          },
          "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20
          }
        },
        "required": [
          "query"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "read_candidate_revision",
      "description": "Read one scoped candidate revision.",
      "input_schema": {
        "type": "object",
        "properties": {
          "candidate_revision_id": {
            "type": "string",
            "format": "uuid"
          }
        },
        "required": [
          "candidate_revision_id"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "validate_formulation",
      "description": "Run the deterministic verifier on a candidate revision.",
      "input_schema": {
        "type": "object",
        "properties": {
          "task_id": {
            "type": "string",
            "format": "uuid"
          },
          "candidate_revision_id": {
            "type": "string",
            "format": "uuid"
          }
        },
        "required": [
          "task_id",
          "candidate_revision_id"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "propose_candidate_patch",
      "description": "Propose a candidate patch — proposal only; a human applies.",
      "input_schema": {
        "type": "object",
        "properties": {
          "candidate_id": {
            "type": "string",
            "format": "uuid"
          },
          "patch": {
            "type": "object",
            "additionalProperties": true
          },
          "reason": {
            "type": "string"
          }
        },
        "required": [
          "candidate_id",
          "patch"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "request_calculation",
      "description": "Request a queued run under admission and budgets.",
      "input_schema": {
        "type": "object",
        "properties": {
          "kind": {
            "type": "string"
          },
          "request": {
            "type": "object",
            "additionalProperties": true
          },
          "task_id": {
            "type": "string",
            "format": "uuid"
          }
        },
        "required": [
          "kind",
          "request"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "summarize_task_evidence",
      "description": "Counts and status of claims and candidates for a task.",
      "input_schema": {
        "type": "object",
        "properties": {
          "task_id": {
            "type": "string",
            "format": "uuid"
          }
        },
        "required": [
          "task_id"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "list_projects",
      "description": "List projects available to this user.",
      "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "name": "list_tasks",
      "description": "List accessible research tasks, optionally for one project.",
      "input_schema": {
        "type": "object",
        "properties": {
          "projectId": {
            "type": "string"
          }
        },
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "name": "read_task",
      "description": "Read current task objective and workflow state.",
      "input_schema": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          }
        },
        "required": [
          "id"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "create_project",
      "description": "Create a project to organize research work.",
      "input_schema": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string"
          },
          "slug": {
            "type": "string"
          },
          "description": {
            "type": "string"
          }
        },
        "required": [
          "name",
          "slug"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "create_task",
      "description": "Create a draft task without inventing missing task inputs.",
      "input_schema": {
        "type": "object",
        "properties": {
          "projectId": {
            "type": "string"
          },
          "title": {
            "type": "string"
          },
          "mode": {
            "type": "string"
          },
          "objective": {
            "type": "string"
          },
          "targetKind": {
            "type": "string"
          },
          "modeInputs": {
            "type": "object"
          }
        },
        "required": [
          "projectId",
          "title",
          "mode"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "calculation_status",
      "description": "Read a calculation's actual status, error and result.",
      "input_schema": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          }
        },
        "required": [
          "id"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "cancel_calculation",
      "description": "Request cancellation of an accessible calculation.",
      "input_schema": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          }
        },
        "required": [
          "id"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "list_materials",
      "description": "List material identities and their current structure review state.",
      "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "name": "create_material_identity",
      "description": "Register a material identity with an unreviewed SMILES structure, for later human review.",
      "input_schema": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string"
          },
          "kind": {
            "type": "string"
          },
          "structure": {
            "type": "string"
          },
          "structureFormat": {
            "type": "string"
          },
          "identifiers": {
            "type": "array",
            "items": {
              "type": "object"
            }
          }
        },
        "required": [
          "name",
          "kind"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "list_formulations",
      "description": "List formulation families and draft/reviewed revisions.",
      "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "name": "draft_formulation",
      "description": "Create a draft formulation revision from typed ingredient quantities.",
      "input_schema": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string"
          },
          "familyId": {
            "type": "string"
          },
          "payload": {
            "type": "object"
          }
        },
        "required": [
          "payload"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "list_lab_plans",
      "description": "List experiment plan drafts for an accessible task.",
      "input_schema": {
        "type": "object",
        "properties": {
          "taskId": {
            "type": "string"
          }
        },
        "required": [
          "taskId"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "draft_lab_plan",
      "description": "Create an experiment plan draft; release still uses normal review.",
      "input_schema": {
        "type": "object",
        "properties": {
          "taskId": {
            "type": "string"
          },
          "title": {
            "type": "string"
          },
          "payload": {
            "type": "object"
          }
        },
        "required": [
          "taskId",
          "title",
          "payload"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "read_lab_results",
      "description": "Read actual recorded experiment executions and replication results.",
      "input_schema": {
        "type": "object",
        "properties": {
          "planId": {
            "type": "string"
          }
        },
        "required": [
          "planId"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "list_optimization_campaigns",
      "description": "List optimization campaigns and their real status for a task.",
      "input_schema": {
        "type": "object",
        "properties": {
          "taskId": {
            "type": "string"
          }
        },
        "required": [
          "taskId"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "list_private_library",
      "description": "List your private folders, notebooks, research sources and memory.",
      "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "name": "search_private_library",
      "description": "Search your private notes and research memory, returning source references.",
      "input_schema": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string"
          },
          "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20
          }
        },
        "required": [
          "query"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "create_folder",
      "description": "Create an owner-private notebook folder.",
      "input_schema": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string"
          },
          "parentId": {
            "type": "string"
          }
        },
        "required": [
          "name"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "create_notebook",
      "description": "Create an owner-private research notebook.",
      "input_schema": {
        "type": "object",
        "properties": {
          "title": {
            "type": "string"
          },
          "folderId": {
            "type": "string"
          }
        },
        "required": [
          "title"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "read_note",
      "description": "Read an owner-private note, recipe or formula.",
      "input_schema": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          }
        },
        "required": [
          "id"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "create_note",
      "description": "Persist an owner-private note, recipe or formula with source citations. Mark generated content as a draft.",
      "input_schema": {
        "type": "object",
        "properties": {
          "notebookId": {
            "type": "string"
          },
          "title": {
            "type": "string"
          },
          "kind": {
            "type": "string",
            "enum": [
              "note",
              "recipe",
              "formula"
            ]
          },
          "content": {
            "type": "object",
            "description": "Note body, usually {markdown: '...'}; formulae may use latex/smiles/variables.",
            "properties": {
              "markdown": {
                "type": "string"
              },
              "latex": {
                "type": "string"
              },
              "smiles": {
                "type": "string"
              },
              "variables": {
                "type": "object",
                "additionalProperties": {
                  "type": [
                    "string",
                    "number"
                  ]
                }
              },
              "steps": {
                "type": "array",
                "items": {
                  "type": "string"
                }
              },
              "ingredients": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "name": {
                      "type": "string"
                    },
                    "amount": {
                      "type": [
                        "string",
                        "number"
                      ]
                    },
                    "unit": {
                      "type": "string"
                    }
                  },
                  "required": [
                    "name"
                  ],
                  "additionalProperties": false
                }
              }
            },
            "additionalProperties": false
          },
          "citations": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "sourceId": {
                  "type": "string"
                },
                "artifactId": {
                  "type": "string"
                },
                "url": {
                  "type": "string"
                },
                "title": {
                  "type": "string"
                },
                "locator": {
                  "type": "object"
                },
                "archiveStatus": {
                  "type": "string"
                }
              },
              "additionalProperties": false
            }
          }
        },
        "required": [
          "notebookId",
          "title",
          "content"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "update_note",
      "description": "Update your private note with optimistic revision checking.",
      "input_schema": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          },
          "expectedRevision": {
            "type": "integer",
            "minimum": 1
          },
          "title": {
            "type": "string"
          },
          "content": {
            "type": "object",
            "description": "Note body, usually {markdown: '...'}; formulae may use latex/smiles/variables.",
            "properties": {
              "markdown": {
                "type": "string"
              },
              "latex": {
                "type": "string"
              },
              "smiles": {
                "type": "string"
              },
              "variables": {
                "type": "object",
                "additionalProperties": {
                  "type": [
                    "string",
                    "number"
                  ]
                }
              },
              "steps": {
                "type": "array",
                "items": {
                  "type": "string"
                }
              },
              "ingredients": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "name": {
                      "type": "string"
                    },
                    "amount": {
                      "type": [
                        "string",
                        "number"
                      ]
                    },
                    "unit": {
                      "type": "string"
                    }
                  },
                  "required": [
                    "name"
                  ],
                  "additionalProperties": false
                }
              }
            },
            "additionalProperties": false
          },
          "citations": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "sourceId": {
                  "type": "string"
                },
                "artifactId": {
                  "type": "string"
                },
                "url": {
                  "type": "string"
                },
                "title": {
                  "type": "string"
                },
                "locator": {
                  "type": "object"
                },
                "archiveStatus": {
                  "type": "string"
                }
              },
              "additionalProperties": false
            }
          }
        },
        "required": [
          "id",
          "expectedRevision"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "save_research_memory",
      "description": "Save source-backed research memory for continuing this work later; preserve uncertainty and open questions.",
      "input_schema": {
        "type": "object",
        "properties": {
          "title": {
            "type": "string"
          },
          "body": {
            "type": "string"
          },
          "sourceRefs": {
            "type": "array",
            "minItems": 1,
            "maxItems": 100,
            "items": {
              "type": "object",
              "properties": {
                "kind": {
                  "type": "string",
                  "enum": [
                    "page",
                    "source"
                  ]
                },
                "id": {
                  "type": "string",
                  "description": "The saved page or retained source ID."
                },
                "revision": {
                  "type": "integer",
                  "minimum": 1
                }
              },
              "required": [
                "kind",
                "id"
              ],
              "additionalProperties": false
            }
          }
        },
        "required": [
          "title",
          "body",
          "sourceRefs"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "search_resources",
      "description": "Search scholarly papers, chemical resources or the web. Available connectors: openalex, crossref, pubchem, web. Web needs configured SearXNG.",
      "input_schema": {
        "type": "object",
        "properties": {
          "connector": {
            "type": "string",
            "enum": [
              "openalex",
              "crossref",
              "pubchem",
              "web"
            ]
          },
          "query": {
            "type": "string"
          },
          "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20
          }
        },
        "required": [
          "connector",
          "query"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "fetch_resource",
      "description": "Fetch a public research resource into your private library, preserving original content, citations and a readable copy. No private network destinations. Set forceRefresh to check a previously saved URL for changes.",
      "input_schema": {
        "type": "object",
        "properties": {
          "url": {
            "type": "string"
          },
          "title": {
            "type": "string"
          },
          "citation": {
            "type": "object"
          },
          "forceRefresh": {
            "type": "boolean"
          }
        },
        "required": [
          "url"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "read_resource",
      "description": "Read a previously fetched private research source.",
      "input_schema": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          },
          "offset": {
            "type": "integer",
            "minimum": 0
          },
          "maxChars": {
            "type": "integer",
            "minimum": 100,
            "maximum": 20000
          }
        },
        "required": [
          "id"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "learning_catalog",
      "description": "Inspect available local model, dataset, training and evaluation capabilities; unavailable engines are explicit.",
      "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "name": "list_datasets",
      "description": "List your custom molecular and assistant training datasets.",
      "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "name": "read_dataset",
      "description": "Inspect a private custom dataset and validation report.",
      "input_schema": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          },
          "offset": {
            "type": "integer",
            "minimum": 0
          },
          "maxRows": {
            "type": "integer",
            "minimum": 1,
            "maximum": 50
          },
          "rejectionOffset": {
            "type": "integer",
            "minimum": 0
          },
          "maxRejections": {
            "type": "integer",
            "minimum": 1,
            "maximum": 50
          }
        },
        "required": [
          "id"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "create_dataset",
      "description": "Import agent-written CSV/JSONL/SMI/SDF data; default origin is synthetic. Experimental and user_authored labels are refused. Literature requires source.sourceRefs [{sourceId,locator:{quote}}] matching fetched source text. Computed data requires source.resultRefs [{runId or jobId,resultPath:[keys]}] resolving to completed owned engine results. Checks do not establish scientific truth.",
      "input_schema": {
        "type": "object",
        "properties": {
          "payload": {
            "type": "object"
          }
        },
        "required": [
          "payload"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "freeze_dataset",
      "description": "Freeze a validated immutable dataset version for local training.",
      "input_schema": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          }
        },
        "required": [
          "id"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "dataset_from_notebook",
      "description": "Create a sourced dataset from selected private notebook pages, respecting each notebook's AI and training opt-outs.",
      "input_schema": {
        "type": "object",
        "properties": {
          "pageIds": {
            "type": "array",
            "items": {
              "type": "string"
            },
            "minItems": 1
          },
          "name": {
            "type": "string"
          }
        },
        "required": [
          "pageIds",
          "name"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "list_local_models",
      "description": "List local training model assets and registered outputs.",
      "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "name": "register_local_model",
      "description": "Register a local model asset, or download a curated pinned Hugging Face model by catalogId. Downloads return a durable job reference. To verify and repair missing files in an existing catalog asset, include its repairModelId with the same catalogId; cached valid weights are reused.",
      "input_schema": {
        "type": "object",
        "properties": {
          "payload": {
            "type": "object"
          }
        },
        "required": [
          "payload"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "import_retained_dataset",
      "description": "Import original retained public computed data with verified source rights and property/method provenance. Values come from the saved source, never agent-written replacements.",
      "input_schema": {
        "type": "object",
        "properties": {
          "payload": {
            "type": "object"
          }
        },
        "required": [
          "payload"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "prepare_polymer_research_dataset",
      "description": "Compile approximately 400 auditable assistant teaching examples from this workflow's imported property datasets and actually executed tools. Origin stays synthetic; source measurements are not invented.",
      "input_schema": {
        "type": "object",
        "properties": {
          "payload": {
            "type": "object"
          }
        },
        "required": [
          "payload"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "merge_datasets",
      "description": "Merge two to ten owned synthetic assistant dataset shards, preserving source lineage, tool conversations and evaluation groups. Current parent rights are rechecked; no measured labels are generated.",
      "input_schema": {
        "type": "object",
        "properties": {
          "payload": {
            "type": "object"
          }
        },
        "required": [
          "payload"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "training_preflight",
      "description": "Check task, model, dataset, runtime, held-out partitions, storage and budget before queueing a real job.",
      "input_schema": {
        "type": "object",
        "properties": {
          "payload": {
            "type": "object"
          }
        },
        "required": [
          "payload"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "simulation_capabilities",
      "description": "Inspect the actual atomistic simulation runtime.",
      "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "name": "start_simulation_job",
      "description": "Queue a bounded owner-private RadonPy/LAMMPS polymer MD pilot. Returns a durable job ID; no fabric properties are inferred from mere structure validity.",
      "input_schema": {
        "type": "object",
        "properties": {
          "payload": {
            "type": "object"
          }
        },
        "required": [
          "payload"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "simulation_job_status",
      "description": "Read numerical stability, equilibration status and artifacts from a real simulation.",
      "input_schema": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          }
        },
        "required": [
          "id"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "await_simulation_job",
      "description": "Wait durably for an atomistic simulation job, releasing the agent worker while computation continues.",
      "input_schema": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          }
        },
        "required": [
          "id"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "cancel_simulation_job",
      "description": "Stop an owned simulation while preserving checkpoints.",
      "input_schema": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          }
        },
        "required": [
          "id"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "resume_simulation_job",
      "description": "Resume a stopped owned simulation from its retained checkpoint within the remaining workflow budget.",
      "input_schema": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          }
        },
        "required": [
          "id"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "resume_training_job",
      "description": "Resume a stopped owned download/training/evaluation job from its saved state, enforcing current rights and remaining workflow budget.",
      "input_schema": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          }
        },
        "required": [
          "id"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "list_training_jobs",
      "description": "List persistent local training and evaluation jobs.",
      "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      }
    },
    {
      "name": "start_training_job",
      "description": "Queue real local SFT/DPO/GRPO, SMILES property training, molecular fine-tuning/RL, or evaluation. Returns a durable job ID, never a fabricated result.",
      "input_schema": {
        "type": "object",
        "properties": {
          "payload": {
            "type": "object"
          }
        },
        "required": [
          "payload"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "training_job_status",
      "description": "Read actual progress, validation metrics and errors from a local training or evaluation job.",
      "input_schema": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          }
        },
        "required": [
          "id"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "await_training_job",
      "description": "Wait durably for a training/evaluation job to finish, then continue research. The worker releases its slot between polls and survives application restart.",
      "input_schema": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          }
        },
        "required": [
          "id"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "calculate_smiles",
      "description": "Calculate real RDKit descriptors for SMILES through the existing durable engine lane. Results are computed data, never experimental measurements.",
      "input_schema": {
        "type": "object",
        "properties": {
          "smiles": {
            "type": "string"
          }
        },
        "required": [
          "smiles"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "cancel_training_job",
      "description": "Request cancellation of your local training job, keeping its checkpoint.",
      "input_schema": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          }
        },
        "required": [
          "id"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "preview_local_model",
      "description": "Run a supported real prediction or generation preview on a registered local model.",
      "input_schema": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          },
          "payload": {
            "type": "object"
          }
        },
        "required": [
          "id",
          "payload"
        ],
        "additionalProperties": false
      }
    },
    {
      "name": "consult_role",
      "description": "Ask another configured model role for a focused review. It receives only the question you supply; it cannot change settings or approve data.",
      "input_schema": {
        "type": "object",
        "properties": {
          "role": {
            "type": "string",
            "enum": [
              "planner",
              "researcher",
              "extractor",
              "reviewer"
            ]
          },
          "question": {
            "type": "string"
          }
        },
        "required": [
          "role",
          "question"
        ],
        "additionalProperties": false
      }
    }
  ]
}
```

**Failure response example:** private tools require a user.

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "errors": [
    {
      "code": "FORBIDDEN",
      "message": "private tools require a user",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [tool_catalog](contracts-agent.md#tool_catalog).

Source: `services/studio-api/src/studio/api/agent_workspace.py:23` (`tool_catalog`).

## POST /api/agent-workspace/providers/{provider_id}/discover

Discover available model IDs from the selected provider.

**Access:** Provider administrator; provider must be enabled and configured.

**Request:** No body; provider_id path UUID.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `provider_id` (required) | path | `uuid.UUID` | `required` |

**Response:** Provider discovery result; this can contact the configured provider. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/agent-workspace/providers/00000000-0000-4000-8000-000000000010/discover HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** A permitted existing provider returned example-model from its model catalog; this sends no research completion prompt.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "models": [
    {
      "modelId": "example-model"
    }
  ]
}
```

**Failure response example:** provider did not return a model list.

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "errors": [
    {
      "code": "CONFLICT",
      "message": "provider did not return a model list",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [discover](contracts-agent.md#discover), [AgentWorkspaceService.discover](contracts-agent.md#agentworkspaceservicediscover).

Source: `services/studio-api/src/studio/api/agent_workspace.py:50` (`discover`).

## POST /api/agent-workspace/providers/{provider_id}/models

Save one provider model and move its selected roles from sibling models.

**Access:** Provider administrator (ProviderService._admin), authenticated human.

**Request:** modelId required; roles is a list of supported roles. Optional label, apiStyle (inherit/chat_completions/responses), enabled, supportsTools and nonnegative inputPricePerMillionUsd/outputPricePerMillionUsd.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `provider_id` (required) | path | `uuid.UUID` | `required` |
| `body` (required) | JSON body | `dict[str, Any]` | `required` |

**Response:** Model id, providerId, modelId, label, roles, supportsTools, apiStyle, enabled and nullable prices. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/agent-workspace/providers/00000000-0000-4000-8000-000000000010/models HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "modelId": "example-model",
  "label": "Example model",
  "roles": [
    "planner"
  ],
  "supportsTools": true,
  "apiStyle": "inherit",
  "enabled": true
}
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000022",
  "modelId": "example-model",
  "label": "Example model",
  "roles": [
    "planner"
  ],
  "supportsTools": true,
  "apiStyle": "inherit",
  "enabled": true,
  "inputPricePerMillionUsd": null,
  "outputPricePerMillionUsd": null
}
```

**Failure response example:** a model ID and valid model roles are required.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "errors": [
    {
      "code": "VALIDATION",
      "message": "a model ID and valid model roles are required",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [save_model](contracts-agent.md#save_model), [AgentWorkspaceService.save_model](contracts-agent.md#agentworkspaceservicesave_model), [AgentWorkspaceService.model_json](contracts-agent.md#agentworkspaceservicemodel_json).

Source: `services/studio-api/src/studio/api/agent_workspace.py:41` (`save_model`).

## POST /api/agent-workspace/runs/{run_id}/cancel

Request cancellation of a private agent run.

**Access:** Authenticated human user; private workspace/owner ownership checks apply in the service.

**Request:** run_id UUID; no body. Cancellation acknowledgment is not evidence that a worker has stopped.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `run_id` (required) | path | `uuid.UUID` | `required` |

**Response:** Run detail/descriptor with status, cancellation, progress, error and timestamps. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/agent-workspace/runs/00000000-0000-4000-8000-000000000009/cancel HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** The run was queued, so cancellation immediately records cancelled; a running run may only acknowledge cancelRequested.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000009",
  "threadId": "00000000-0000-4000-8000-000000000008",
  "providerId": "00000000-0000-4000-8000-000000000010",
  "modelId": "example-model",
  "localModelId": null,
  "role": "planner",
  "status": "cancelled",
  "autopilot": false,
  "progress": {
    "step": 0,
    "toolCalls": 0,
    "documents": 0,
    "trainingJobs": 0,
    "costUsd": 0.0,
    "localModelId": null,
    "localModelFingerprint": null,
    "workflowId": null
  },
  "error": null,
  "cancelRequested": true,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "startedAt": null,
  "completedAt": "2026-11-02T00:00:00+00:00"
}
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

**Exact JSON rules and response serialization:** [cancel](contracts-agent.md#cancel), [AgentWorkspaceService.cancel](contracts-agent.md#agentworkspaceservicecancel), [AgentWorkspaceService.run_json](contracts-agent.md#agentworkspaceservicerun_json).

Source: `services/studio-api/src/studio/api/agent_workspace.py:119` (`cancel`).

## POST /api/agent-workspace/runs/{run_id}/resume

Resume a recoverable private agent run.

**Access:** Authenticated human user; private workspace/owner ownership checks apply in the service.

**Request:** run_id UUID; no body. Provider/configuration and ownership are rechecked.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `run_id` (required) | path | `uuid.UUID` | `required` |

**Response:** Run detail/descriptor with status, cancellation, progress, error and timestamps. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/agent-workspace/runs/00000000-0000-4000-8000-000000000009/resume HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** A stopped recoverable run is queued after current permissions, provider/disclosure and workflow checks.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000009",
  "threadId": "00000000-0000-4000-8000-000000000008",
  "providerId": "00000000-0000-4000-8000-000000000010",
  "modelId": "example-model",
  "localModelId": null,
  "role": "planner",
  "status": "queued",
  "autopilot": false,
  "progress": {
    "step": 0,
    "toolCalls": 0,
    "documents": 0,
    "trainingJobs": 0,
    "costUsd": 0.0,
    "localModelId": null,
    "localModelFingerprint": null,
    "workflowId": null
  },
  "error": null,
  "cancelRequested": false,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "startedAt": null,
  "completedAt": null
}
```

**Failure response example:** only stopped runs can be resumed.

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "errors": [
    {
      "code": "CONFLICT",
      "message": "only stopped runs can be resumed",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [resume](contracts-agent.md#resume), [AgentWorkspaceService.resume](contracts-agent.md#agentworkspaceserviceresume), [AgentWorkspaceService.run_json](contracts-agent.md#agentworkspaceservicerun_json).

Source: `services/studio-api/src/studio/api/agent_workspace.py:126` (`resume`).

## POST /api/agent-workspace/threads

Create a private research thread.

**Access:** Authenticated human user; private workspace/owner ownership checks apply in the service.

**Request:** Optional title, taskId and notebookId. Bound records must be accessible and owned; title defaults to New research.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `body` (required) | JSON body | `dict[str, Any]` | `required` |

**Response:** Thread id, title, taskId, notebookId, createdAt and updatedAt. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/agent-workspace/threads HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "title": "Ethanol literature review"
}
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000008",
  "title": "Ethanol literature review",
  "taskId": null,
  "notebookId": null,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00"
}
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

**Exact JSON rules and response serialization:** [create_thread](contracts-agent.md#create_thread), [AgentWorkspaceService.create_thread](contracts-agent.md#agentworkspaceservicecreate_thread), [AgentWorkspaceService.thread_json](contracts-agent.md#agentworkspaceservicethread_json).

Source: `services/studio-api/src/studio/api/agent_workspace.py:78` (`create_thread`).

## POST /api/agent-workspace/threads/{thread_id}/runs

Queue a durable tool-using research turn.

**Access:** Authenticated human user; private workspace/owner ownership checks apply in the service.

**Request:** message is required (bounded text); role and optional providerId/modelId/localModelId, workflowId and autopilot select execution. A provider or local model must pass consent/availability checks.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `thread_id` (required) | path | `uuid.UUID` | `required` |
| `body` (required) | JSON body | `dict[str, Any]` | `required` |

**Response:** Run descriptor with id, threadId, providerId/modelId/localModelId, role, status, autopilot, progress, error, cancellation and timestamps. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/agent-workspace/threads/00000000-0000-4000-8000-000000000008/runs HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "message": "Summarize the retained ethanol notes and list open questions.",
  "providerId": "00000000-0000-4000-8000-000000000010",
  "modelId": "example-model",
  "role": "planner",
  "autopilot": false
}
```

**Success response example:** An enabled existing provider/model is selected and any needed private-context disclosure is current. Queued acknowledgment does not prove generation completed.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000009",
  "threadId": "00000000-0000-4000-8000-000000000008",
  "providerId": "00000000-0000-4000-8000-000000000010",
  "modelId": "example-model",
  "localModelId": null,
  "role": "planner",
  "status": "queued",
  "autopilot": false,
  "progress": {
    "step": 0,
    "toolCalls": 0,
    "documents": 0,
    "trainingJobs": 0,
    "costUsd": 0.0,
    "localModelId": null,
    "localModelFingerprint": null,
    "workflowId": null
  },
  "error": null,
  "cancelRequested": false,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "startedAt": null,
  "completedAt": null
}
```

**Failure response example:** a run is already active in this thread.

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "errors": [
    {
      "code": "CONFLICT",
      "message": "a run is already active in this thread",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [create_run](contracts-agent.md#create_run), [AgentWorkspaceService.create_run](contracts-agent.md#agentworkspaceservicecreate_run), [AgentWorkspaceService.run_json](contracts-agent.md#agentworkspaceservicerun_json).

Source: `services/studio-api/src/studio/api/agent_workspace.py:105` (`create_run`).

## PUT /api/agent-workspace/policies

Replace bounded autopilot and provider-specific private-context consent.

**Access:** Authenticated human user; private workspace/owner ownership checks apply in the service.

**Request:** autopilot includes enabled, maxDocumentsPerDay, maxHours, maxTrainingJobs, maxPaidCostUsd. remoteDisclosures maps provider UUIDs to providerRevision and allowPrivate; stale revisions fail. Existing schedules are preserved.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `body` (required) | JSON body | `dict[str, Any]` | `required` |

**Response:** Normalized policy object; remote provider origins/revisions come from the stored provider. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
PUT /api/agent-workspace/policies HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "remoteDisclosures": {},
  "remoteDisclosure": null,
  "autopilot": {
    "enabled": false,
    "maxDocumentsPerDay": 100,
    "maxHours": 4,
    "maxTrainingJobs": 1,
    "maxPaidCostUsd": 0
  }
}
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "remoteDisclosures": {},
  "remoteDisclosure": null,
  "autopilot": {
    "enabled": false,
    "maxDocumentsPerDay": 100,
    "maxHours": 4,
    "maxTrainingJobs": 1,
    "maxPaidCostUsd": 0
  },
  "schedules": {}
}
```

**Failure response example:** maxPaidCostUsd must be between zero and 10000.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "errors": [
    {
      "code": "VALIDATION",
      "message": "maxPaidCostUsd must be between zero and 10000",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [save_policy](contracts-agent.md#save_policy), [AgentWorkspaceService.save_policy](contracts-agent.md#agentworkspaceservicesave_policy).

Source: `services/studio-api/src/studio/api/agent_workspace.py:60` (`save_policy`).

## PUT /api/agent-workspace/threads/{thread_id}/automation

Set a thread recurring research schedule.

**Access:** Authenticated human user; private workspace/owner ownership checks apply in the service.

**Request:** enabled, researchGoal, scheduleHours (0.05–720), optional providerId/modelId/localModelId and role. Enabling requires bounded autopilot and any remote disclosure consent.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `thread_id` (required) | path | `uuid.UUID` | `required` |
| `body` (required) | JSON body | `dict[str, Any]` | `required` |

**Response:** Normalized enabled/goal/cadence/model selection plus nextWakeAt, lastRunId and lastError. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
PUT /api/agent-workspace/threads/00000000-0000-4000-8000-000000000008/automation HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "enabled": false,
  "researchGoal": "Review newly retained ethanol sources.",
  "scheduleHours": 24,
  "role": "planner"
}
```

**Success response example:** The schedule is saved disabled. Enabling requires bounded owner autopilot and current provider disclosure where applicable.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "enabled": false,
  "researchGoal": "Review newly retained ethanol sources.",
  "scheduleHours": 24.0,
  "providerId": null,
  "modelId": null,
  "localModelId": null,
  "role": "planner",
  "nextWakeAt": "2026-11-03T00:00:00+00:00",
  "lastRunId": null,
  "lastError": null
}
```

**Failure response example:** enable bounded autopilot before scheduling research.

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "errors": [
    {
      "code": "FORBIDDEN",
      "message": "enable bounded autopilot before scheduling research",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [automation](contracts-agent.md#automation), [AgentWorkspaceService.save_automation](contracts-agent.md#agentworkspaceservicesave_automation).

Source: `services/studio-api/src/studio/api/agent_workspace.py:96` (`automation`).
