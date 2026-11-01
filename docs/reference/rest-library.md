# Private library API

Folders, notebooks, versioned pages, sourced memory, retained files and research search. Records are workspace- and owner-scoped.

[Shared authentication, errors and transport](rest-overview.md). Examples use synthetic values; replace resource IDs with records from your workspace.

## DELETE /api/library/folders/{ident}

Delete an empty owned folder after checking its expected revision.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No JSON body; use the path/query fields below.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `ident` (required) | path | `uuid.UUID` | `required` |
| `expectedRevision` (required) | query | `int` | `Query(alias='expectedRevision', ge=1)` |

**Response:** deleted=true after the empty folder row is removed; a folder containing child folders or notebooks is rejected. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
DELETE /api/library/folders/00000000-0000-4000-8000-000000000003?expectedRevision=1 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** The owned folder has revision 1 and no child folders or notebooks. Its empty folder row is deleted; source/content records are not implicitly purged.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "deleted": true
}
```

**Failure response example:** private library record changed since the expected version; reload and retry.

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "errors": [
    {
      "code": "REVISION_CONFLICT",
      "message": "private library record changed since the expected version; reload and retry",
      "fieldPath": null,
      "retryable": true,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [folder_delete](contracts-library.md#folder_delete), [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [LibraryService.delete_folder](contracts-library.md#libraryservicedelete_folder).

Source: `services/studio-api/src/studio/api/library.py:71` (`folder_delete`).

## DELETE /api/library/memory/{ident}

Forget a private research memory record.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No JSON body; use the path/query fields below.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `ident` (required) | path | `uuid.UUID` | `required` |

**Response:** Deletion/forget acknowledgment object; source bytes and history follow documented retention policy. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
DELETE /api/library/memory/00000000-0000-4000-8000-000000000007 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "forgotten": true
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

**Exact JSON rules and response serialization:** [memory_forget](contracts-library.md#memory_forget), [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [LibraryService.forget_memory](contracts-library.md#libraryserviceforget_memory).

Source: `services/studio-api/src/studio/api/library.py:181` (`memory_forget`).

## DELETE /api/library/notebooks/{ident}

Delete an empty owned notebook after checking its expected revision.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No JSON body; use the path/query fields below.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `ident` (required) | path | `uuid.UUID` | `required` |
| `expectedRevision` (required) | query | `int` | `Query(alias='expectedRevision', ge=1)` |

**Response:** deleted=true after the notebook row is removed; saved or recoverable trashed pages must be handled first. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
DELETE /api/library/notebooks/00000000-0000-4000-8000-000000000004?expectedRevision=1 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** The owned notebook has revision 1 and contains no saved or recoverable trashed pages. Its empty notebook row is deleted.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "deleted": true
}
```

**Failure response example:** private library record changed since the expected version; reload and retry.

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "errors": [
    {
      "code": "REVISION_CONFLICT",
      "message": "private library record changed since the expected version; reload and retry",
      "fieldPath": null,
      "retryable": true,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [notebook_delete](contracts-library.md#notebook_delete), [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [LibraryService.delete_notebook](contracts-library.md#libraryservicedelete_notebook).

Source: `services/studio-api/src/studio/api/library.py:104` (`notebook_delete`).

## DELETE /api/library/pages/{ident}

Soft-delete a page using its expected revision.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No JSON body; use the path/query fields below.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `ident` (required) | path | `uuid.UUID` | `required` |
| `expectedRevision` (required) | query | `int` | `Query(alias='expectedRevision', ge=1)` |

**Response:** Deletion/forget acknowledgment object; source bytes and history follow documented retention policy. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
DELETE /api/library/pages/00000000-0000-4000-8000-000000000005?expectedRevision=1 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "deleted": true
}
```

**Failure response example:** private library record changed since the expected version; reload and retry.

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "errors": [
    {
      "code": "REVISION_CONFLICT",
      "message": "private library record changed since the expected version; reload and retry",
      "fieldPath": null,
      "retryable": true,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [page_delete](contracts-library.md#page_delete), [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [LibraryService.delete_page](contracts-library.md#libraryservicedelete_page).

Source: `services/studio-api/src/studio/api/library.py:139` (`page_delete`).

## DELETE /api/library/sources/{ident}

Soft-delete a source and invalidate source-derived context.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No JSON body; use the path/query fields below.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `ident` (required) | path | `uuid.UUID` | `required` |
| `expectedRevision` (required) | query | `int` | `Query(alias='expectedRevision', ge=1)` |

**Response:** Deletion/forget acknowledgment object; source bytes and history follow documented retention policy. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
DELETE /api/library/sources/00000000-0000-4000-8000-000000000006?expectedRevision=1 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "deleted": true
}
```

**Failure response example:** private library record changed since the expected version; reload and retry.

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "errors": [
    {
      "code": "REVISION_CONFLICT",
      "message": "private library record changed since the expected version; reload and retry",
      "fieldPath": null,
      "retryable": true,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [source_delete](contracts-library.md#source_delete), [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [LibraryService.delete_source](contracts-library.md#libraryservicedelete_source).

Source: `services/studio-api/src/studio/api/library.py:276` (`source_delete`).

## GET /api/library

List the owner-private folder/notebook/source/memory workspace.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No JSON body; use the path/query fields below.

**Response:** Folders, notebooks, pages/source summaries and memory for this owner; _record specifies each record variant. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/library HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** An owner with no private records; the displayed path is synthetic.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "downloadsRoot": "/private/example-downloads/00000000-0000-4000-8000-000000000001/00000000-0000-4000-8000-000000000002",
  "ownerKey": "00000000-0000-4000-8000-000000000001:00000000-0000-4000-8000-000000000002",
  "folders": [],
  "notebooks": [],
  "pages": [],
  "memory": [],
  "sources": [],
  "trash": []
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

**Exact JSON rules and response serialization:** [library](contracts-library.md#library), [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [LibraryService.list_all](contracts-library.md#libraryservicelist_all).

Source: `services/studio-api/src/studio/api/library.py:48` (`library`).

## GET /api/library/pages/{ident}

Read a page, citations and revision history.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No JSON body; use the path/query fields below.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `ident` (required) | path | `uuid.UUID` | `required` |

**Response:** Owned record descriptor with id, revision, timestamps and type-specific metadata; exact conditional shape is in LibraryService._record. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/library/pages/00000000-0000-4000-8000-000000000005 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000005",
  "revision": 1,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00",
  "title": "Ethanol observation",
  "notebookId": "00000000-0000-4000-8000-000000000004",
  "kind": "note",
  "content": {
    "markdown": "Synthetic ethanol note.",
    "ingredients": [],
    "steps": [],
    "latex": "",
    "smiles": "",
    "variables": {}
  },
  "citations": [],
  "deletedAt": null,
  "revisions": [
    {
      "id": "00000000-0000-4000-8000-000000000020",
      "revision": 1,
      "title": "Ethanol observation",
      "content": {
        "markdown": "Synthetic ethanol note.",
        "ingredients": [],
        "steps": [],
        "latex": "",
        "smiles": "",
        "variables": {}
      },
      "citations": [],
      "createdAt": "2026-11-02T00:00:00+00:00"
    }
  ]
}
```

**Failure response example:** private library record not found or not accessible.

```http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "private library record not found or not accessible",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [page_get](contracts-library.md#page_get), [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [LibraryService.get_page](contracts-library.md#libraryserviceget_page).

Source: `services/studio-api/src/studio/api/library.py:125` (`page_get`).

## GET /api/library/research/search

Search an external public research connector.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** connector enum openalex/crossref/pubchem/web, bounded q and limit. This makes a public research search request; web requires configured SearXNG.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `connector` (required) | query | `Literal['openalex', 'crossref', 'pubchem', 'web']` | `required` |
| `q` (required) | query | `str` | `Query(min_length=1, max_length=500)` |
| `limit` (optional) | query | `int` | `Query(default=10, ge=1, le=20)` |

**Response:** results array of bounded search hits with source/link/locator metadata. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/library/research/search?connector=openalex&q=ethanol&limit=5 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** The selected public connector responds successfully with no matching records.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "results": []
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

**Exact JSON rules and response serialization:** [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [research_search](contracts-library.md#research_search).

Source: `services/studio-api/src/studio/api/library.py:188` (`research_search`).

## GET /api/library/search

Search eligible private notebook and research content.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No JSON body; use the path/query fields below.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `q` (required) | query | `str` | `Query(min_length=1, max_length=500)` |
| `limit` (optional) | query | `int` | `Query(default=20, ge=1, le=50)` |

**Response:** results array of bounded search hits with source/link/locator metadata. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/library/search?q=ethanol&limit=20 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** No currently eligible private records match the query.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "results": []
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

**Exact JSON rules and response serialization:** [search](contracts-library.md#search), [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [LibraryService.search](contracts-library.md#libraryservicesearch).

Source: `services/studio-api/src/studio/api/library.py:152` (`search`).

## GET /api/library/sources/{ident}

Read retained research source metadata and extraction.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No JSON body; use the path/query fields below.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `ident` (required) | path | `uuid.UUID` | `required` |

**Response:** Owned record descriptor with id, revision, timestamps and type-specific metadata; exact conditional shape is in LibraryService._record. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/library/sources/00000000-0000-4000-8000-000000000006 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000006",
  "revision": 1,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00",
  "title": "Example source",
  "url": "https://example.org/source.txt",
  "sourceUrl": "https://example.org/source.txt",
  "mediaType": "text/plain",
  "byteSize": 25,
  "checksum": "7b69d4175ba56dab8ec303d5d064bd699aa5d9abbd7aabedeef68d382fc6a0b4",
  "citation": {
    "rights": {
      "retrieval": "allowed",
      "extraction": "allowed",
      "training": "allowed",
      "export": "allowed"
    }
  },
  "archiveStatus": "saved",
  "downloadName": "source.txt",
  "originalName": "source.txt",
  "originalDownloadUrl": "/api/library/sources/00000000-0000-4000-8000-000000000006/content?format=original",
  "textDownloadUrl": "/api/library/sources/00000000-0000-4000-8000-000000000006/content?format=text",
  "metadataDownloadUrl": "/api/library/sources/00000000-0000-4000-8000-000000000006/content?format=metadata",
  "downloadDirectory": "/private/example-downloads/00000000-0000-4000-8000-000000000001/00000000-0000-4000-8000-000000000002/00000000-0000-4000-8000-000000000006",
  "extractionStatus": "extracted",
  "deletedAt": null,
  "extractedText": "Example research source.\n"
}
```

**Failure response example:** private library record not found or not accessible.

```http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "private library record not found or not accessible",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [source_get](contracts-library.md#source_get), [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [LibraryService.get_source](contracts-library.md#libraryserviceget_source).

Source: `services/studio-api/src/studio/api/library.py:205` (`source_get`).

## GET /api/library/sources/{ident}/content

Download an owned retained research original.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No JSON body; use the path/query fields below.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `ident` (required) | path | `uuid.UUID` | `required` |
| `format` (optional) | query | `Literal['original', 'text', 'metadata']` | `'original'` |

**Response:** Binary original file with its stored media type and safe attachment filename. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/library/sources/00000000-0000-4000-8000-000000000006/content?format=original HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: text/plain
Content-Disposition: attachment; filename="source.txt"
Cache-Control: no-store

Example research source.

```

**Failure response example:** private library record not found or not accessible.

```http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "private library record not found or not accessible",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [source_content](contracts-library.md#source_content), [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [LibraryService.source_file](contracts-library.md#libraryservicesource_file).

Source: `services/studio-api/src/studio/api/library.py:255` (`source_content`).

## GET /api/library/structures/preview

Render a bounded molecular structure preview from SMILES.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No JSON body; use the path/query fields below.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `smiles` (required) | query | `str` | `Query(min_length=1, max_length=10000)` |

**Response:** Structure preview representation and availability/error state; RDKit must support the supplied SMILES. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/library/structures/preview?smiles=CCO HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** RDKit is installed. Invalid SMILES or missing RDKit is also reported as an error field within a 200 JSON response.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "smiles": "CCO",
  "canonicalSmiles": "CCO",
  "formula": "C2H6O",
  "svg": "<?xml version='1.0' encoding='iso-8859-1'?>\n<svg version='1.1' baseProfile='full'\n              xmlns='http://www.w3.org/2000/svg'\n                      xmlns:rdkit='http://www.rdkit.org/xml'\n                      xmlns:xlink='http://www.w3.org/1999/xlink'\n                  xml:space='preserve'\nwidth='420px' height='300px' viewBox='0 0 420 300'>\n<!-- END OF HEADER -->\n<rect style='opacity:1.0;fill:#FFFFFF;stroke:none' width='420.0' height='300.0' x='0.0' y='0.0'> </rect>\n<path class='bond-0 atom-0 atom-1' d='M 36.4,187.0 L 190.2,98.2' style='fill:none;fill-rule:evenodd;stroke:#000000;stroke-width:2.0px;stroke-linecap:butt;stroke-linejoin:miter;stroke-opacity:1' />\n<path class='bond-1 atom-1 atom-2' d='M 190.2,98.2 L 257.7,137.2' style='fill:none;fill-rule:evenodd;stroke:#000000;stroke-width:2.0px;stroke-linecap:butt;stroke-linejoin:miter;stroke-opacity:1' />\n<path class='bond-1 atom-1 atom-2' d='M 257.7,137.2 L 325.2,176.1' style='fill:none;fill-rule:evenodd;stroke:#FF0000;stroke-width:2.0px;stroke-linecap:butt;stroke-linejoin:miter;stroke-opacity:1' />\n<path d='M 182.5,102.6 L 190.2,98.2 L 193.6,100.2' style='fill:none;stroke:#000000;stroke-width:2.0px;stroke-linecap:butt;stroke-linejoin:miter;stroke-miterlimit:10;stroke-opacity:1;' />\n<path class='atom-2' d='M 331.1 187.1\nQ 331.1 180.3, 334.4 176.5\nQ 337.8 172.7, 344.1 172.7\nQ 350.3 172.7, 353.7 176.5\nQ 357.1 180.3, 357.1 187.1\nQ 357.1 194.0, 353.7 197.9\nQ 350.3 201.8, 344.1 201.8\nQ 337.8 201.8, 334.4 197.9\nQ 331.1 194.0, 331.1 187.1\nM 344.1 198.6\nQ 348.4 198.6, 350.7 195.7\nQ 353.1 192.8, 353.1 187.1\nQ 353.1 181.6, 350.7 178.8\nQ 348.4 175.9, 344.1 175.9\nQ 339.7 175.9, 337.4 178.7\nQ 335.1 181.5, 335.1 187.1\nQ 335.1 192.8, 337.4 195.7\nQ 339.7 198.6, 344.1 198.6\n' fill='#FF0000'/>\n<path class='atom-2' d='M 361.5 173.0\nL 365.3 173.0\nL 365.3 185.1\nL 379.8 185.1\nL 379.8 173.0\nL 383.6 173.0\nL 383.6 201.4\nL 379.8 201.4\nL 379.8 188.3\nL 365.3 188.3\nL 365.3 201.4\nL 361.5 201.4\nL 361.5 173.0\n' fill='#FF0000'/>\n</svg>\n"
}
```

**Failure response example:** The authenticated request contains smiles=invalid; this endpoint reports parser failure inside its 200 response.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "smiles": "invalid",
  "error": "The supplied SMILES could not be parsed"
}
```

**Exact JSON rules and response serialization:** [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [structure_preview](contracts-library.md#structure_preview).

Source: `services/studio-api/src/studio/api/library.py:289` (`structure_preview`).

## PATCH /api/library/folders/{ident}

Rename or move a folder with optimistic revision checking.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** UpdateFolder JSON (camelCase aliases and Python field names are accepted; unknown keys rejected). Exact fields, bounds and defaults are in the linked request class.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `ident` (required) | path | `uuid.UUID` | `required` |
| `data` (required) | JSON body | `UpdateFolder` | `required` |

**Response:** Owned record descriptor with id, revision, timestamps and type-specific metadata; exact conditional shape is in LibraryService._record. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
PATCH /api/library/folders/00000000-0000-4000-8000-000000000003 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "name": "Reviewed research",
  "expectedRevision": 1
}
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000003",
  "revision": 2,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00",
  "name": "Reviewed research",
  "parentId": null
}
```

**Failure response example:** private library record changed since the expected version; reload and retry.

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "errors": [
    {
      "code": "REVISION_CONFLICT",
      "message": "private library record changed since the expected version; reload and retry",
      "fieldPath": null,
      "retryable": true,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [folder_update](contracts-library.md#folder_update), [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [UpdateFolder](contracts-library.md#updatefolder), [LibraryService.update_folder](contracts-library.md#libraryserviceupdate_folder).

Source: `services/studio-api/src/studio/api/library.py:62` (`folder_update`).

## PATCH /api/library/notebooks/{ident}

Edit notebook metadata or AI/training consent.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** UpdateNotebook JSON (camelCase aliases and Python field names are accepted; unknown keys rejected). Exact fields, bounds and defaults are in the linked request class.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `ident` (required) | path | `uuid.UUID` | `required` |
| `data` (required) | JSON body | `UpdateNotebook` | `required` |

**Response:** Owned record descriptor with id, revision, timestamps and type-specific metadata; exact conditional shape is in LibraryService._record. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
PATCH /api/library/notebooks/00000000-0000-4000-8000-000000000004 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "title": "Reviewed ethanol notes",
  "aiEnabled": false,
  "trainingEnabled": false,
  "expectedRevision": 1
}
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000004",
  "revision": 2,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00",
  "title": "Reviewed ethanol notes",
  "folderId": null,
  "aiEnabled": false,
  "trainingEnabled": false
}
```

**Failure response example:** private library record changed since the expected version; reload and retry.

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "errors": [
    {
      "code": "REVISION_CONFLICT",
      "message": "private library record changed since the expected version; reload and retry",
      "fieldPath": null,
      "retryable": true,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [notebook_update](contracts-library.md#notebook_update), [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [UpdateNotebook](contracts-library.md#updatenotebook), [LibraryService.update_notebook](contracts-library.md#libraryserviceupdate_notebook).

Source: `services/studio-api/src/studio/api/library.py:93` (`notebook_update`).

## PATCH /api/library/pages/{ident}

Save a page revision with source/citation validation.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** UpdatePage JSON (camelCase aliases and Python field names are accepted; unknown keys rejected). Exact fields, bounds and defaults are in the linked request class.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `ident` (required) | path | `uuid.UUID` | `required` |
| `data` (required) | JSON body | `UpdatePage` | `required` |

**Response:** Owned record descriptor with id, revision, timestamps and type-specific metadata; exact conditional shape is in LibraryService._record. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
PATCH /api/library/pages/00000000-0000-4000-8000-000000000005 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "title": "Reviewed ethanol observation",
  "content": {
    "markdown": "Synthetic revised note."
  },
  "expectedRevision": 1
}
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000005",
  "revision": 2,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00",
  "title": "Reviewed ethanol observation",
  "notebookId": "00000000-0000-4000-8000-000000000004",
  "kind": "note",
  "content": {
    "markdown": "Synthetic revised note.",
    "ingredients": [],
    "steps": [],
    "latex": "",
    "smiles": "",
    "variables": {}
  },
  "citations": [],
  "deletedAt": null
}
```

**Failure response example:** private library record changed since the expected version; reload and retry.

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "errors": [
    {
      "code": "REVISION_CONFLICT",
      "message": "private library record changed since the expected version; reload and retry",
      "fieldPath": null,
      "retryable": true,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [page_update](contracts-library.md#page_update), [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [UpdatePage](contracts-library.md#updatepage), [PageContent](contracts-library.md#pagecontent), [Ingredient](contracts-library.md#ingredient), [Citation](contracts-library.md#citation), [LibraryService.update_page](contracts-library.md#libraryserviceupdate_page).

Source: `services/studio-api/src/studio/api/library.py:130` (`page_update`).

## POST /api/library/downloads/reveal

Reveal the current user’s research Downloads folder on the local host.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No JSON body; use the path/query fields below.

**Response:** Local folder reveal result; host support is required. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/library/downloads/reveal HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** A permitted local macOS folder reveal succeeds; this is the synthetic owner-specific path.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "opened": true,
  "directory": "/private/example-downloads/00000000-0000-4000-8000-000000000001/00000000-0000-4000-8000-000000000002"
}
```

**Failure response example:** folder reveal is available on macOS.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "errors": [
    {
      "code": "ENGINE_UNAVAILABLE",
      "message": "folder reveal is available on macOS",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [downloads_reveal](contracts-library.md#downloads_reveal).

Source: `services/studio-api/src/studio/api/library.py:312` (`downloads_reveal`).

## POST /api/library/folders

Create a private notebook folder.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** CreateFolder JSON (camelCase aliases and Python field names are accepted; unknown keys rejected). Exact fields, bounds and defaults are in the linked request class.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `data` (required) | JSON body | `CreateFolder` | `required` |

**Response:** Owned record descriptor with id, revision, timestamps and type-specific metadata; exact conditional shape is in LibraryService._record. Default success status: 201. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/library/folders HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "name": "Example research",
  "parentId": null
}
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000003",
  "revision": 1,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00",
  "name": "Example research",
  "parentId": null
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

**Exact JSON rules and response serialization:** [folder_create](contracts-library.md#folder_create), [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [CreateFolder](contracts-library.md#createfolder), [LibraryService.create_folder](contracts-library.md#libraryservicecreate_folder).

Source: `services/studio-api/src/studio/api/library.py:55` (`folder_create`).

## POST /api/library/memory

Save sourced private research memory.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** CreateMemory JSON (camelCase aliases and Python field names are accepted; unknown keys rejected). Exact fields, bounds and defaults are in the linked request class.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `data` (required) | JSON body | `CreateMemory` | `required` |

**Response:** Owned record descriptor with id, revision, timestamps and type-specific metadata; exact conditional shape is in LibraryService._record. Default success status: 201. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/library/memory HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "title": "Follow-up question",
  "body": "Compare the computed descriptor with reviewed evidence.",
  "sourceRefs": [
    {
      "kind": "page",
      "id": "00000000-0000-4000-8000-000000000005",
      "revision": 1
    }
  ]
}
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000007",
  "revision": 1,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00",
  "title": "Follow-up question",
  "body": "Compare the computed descriptor with reviewed evidence.",
  "sourceRefs": [
    {
      "kind": "page",
      "id": "00000000-0000-4000-8000-000000000005",
      "revision": 1
    }
  ],
  "status": "active",
  "generator": "user"
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

**Exact JSON rules and response serialization:** [memory_create](contracts-library.md#memory_create), [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [CreateMemory](contracts-library.md#creatememory), [SourceRef](contracts-library.md#sourceref), [LibraryService.save_memory](contracts-library.md#libraryservicesave_memory).

Source: `services/studio-api/src/studio/api/library.py:174` (`memory_create`).

## POST /api/library/notebooks

Create a private notebook.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** CreateNotebook JSON (camelCase aliases and Python field names are accepted; unknown keys rejected). Exact fields, bounds and defaults are in the linked request class.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `data` (required) | JSON body | `CreateNotebook` | `required` |

**Response:** Owned record descriptor with id, revision, timestamps and type-specific metadata; exact conditional shape is in LibraryService._record. Default success status: 201. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/library/notebooks HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "title": "Ethanol notes"
}
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000004",
  "revision": 1,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00",
  "title": "Ethanol notes",
  "folderId": null,
  "aiEnabled": true,
  "trainingEnabled": true
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

**Exact JSON rules and response serialization:** [notebook_create](contracts-library.md#notebook_create), [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [CreateNotebook](contracts-library.md#createnotebook), [LibraryService.create_notebook](contracts-library.md#libraryservicecreate_notebook).

Source: `services/studio-api/src/studio/api/library.py:84` (`notebook_create`).

## POST /api/library/pages

Create a typed notebook page with structured content and citations.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** CreatePage JSON (camelCase aliases and Python field names are accepted; unknown keys rejected). Exact fields, bounds and defaults are in the linked request class.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `data` (required) | JSON body | `CreatePage` | `required` |

**Response:** Owned record descriptor with id, revision, timestamps and type-specific metadata; exact conditional shape is in LibraryService._record. Default success status: 201. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/library/pages HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "notebookId": "00000000-0000-4000-8000-000000000004",
  "title": "Ethanol observation",
  "kind": "note",
  "content": {
    "markdown": "Synthetic ethanol note."
  },
  "citations": []
}
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000005",
  "revision": 1,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00",
  "title": "Ethanol observation",
  "notebookId": "00000000-0000-4000-8000-000000000004",
  "kind": "note",
  "content": {
    "markdown": "Synthetic ethanol note.",
    "ingredients": [],
    "steps": [],
    "latex": "",
    "smiles": "",
    "variables": {}
  },
  "citations": [],
  "deletedAt": null
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

**Exact JSON rules and response serialization:** [page_create](contracts-library.md#page_create), [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [CreatePage](contracts-library.md#createpage), [PageContent](contracts-library.md#pagecontent), [Ingredient](contracts-library.md#ingredient), [Citation](contracts-library.md#citation), [LibraryService.create_page](contracts-library.md#libraryservicecreate_page).

Source: `services/studio-api/src/studio/api/library.py:117` (`page_create`).

## POST /api/library/pages/{ident}/restore

Restore an owned soft-deleted page with revision verification.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** RestorePage JSON (camelCase aliases and Python field names are accepted; unknown keys rejected). Exact fields, bounds and defaults are in the linked request class.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `ident` (required) | path | `uuid.UUID` | `required` |
| `data` (required) | JSON body | `RestorePage` | `required` |

**Response:** Owned record descriptor with id, revision, timestamps and type-specific metadata; exact conditional shape is in LibraryService._record. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/library/pages/00000000-0000-4000-8000-000000000005/restore HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "expectedRevision": 2
}
```

**Success response example:** This owner-owned page was previously trashed at revision 2; restoring advances its revision.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000005",
  "revision": 3,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00",
  "title": "Ethanol observation",
  "notebookId": "00000000-0000-4000-8000-000000000004",
  "kind": "note",
  "content": {
    "markdown": "Synthetic ethanol note.",
    "ingredients": [],
    "steps": [],
    "latex": "",
    "smiles": "",
    "variables": {}
  },
  "citations": [],
  "deletedAt": null
}
```

**Failure response example:** private library record changed since the expected version; reload and retry.

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "errors": [
    {
      "code": "REVISION_CONFLICT",
      "message": "private library record changed since the expected version; reload and retry",
      "fieldPath": null,
      "retryable": true,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [page_restore](contracts-library.md#page_restore), [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [RestorePage](contracts-library.md#restorepage), [LibraryService.restore_page](contracts-library.md#libraryservicerestore_page).

Source: `services/studio-api/src/studio/api/library.py:165` (`page_restore`).

## POST /api/library/sources/artifact

Retain an accessible workspace artifact in private research Downloads.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** ArchiveArtifact JSON (camelCase aliases and Python field names are accepted; unknown keys rejected). Exact fields, bounds and defaults are in the linked request class.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `data` (required) | JSON body | `ArchiveArtifact` | `required` |

**Response:** Owned record descriptor with id, revision, timestamps and type-specific metadata; exact conditional shape is in LibraryService._record. Default success status: 201. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/library/sources/artifact HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "artifactId": "00000000-0000-4000-8000-000000000015"
}
```

**Success response example:** The accessible example.txt artifact contains the seven-byte example upload, permits local retention and is not revoked/rejected. Rights remain unknown rather than silently becoming training/export permission.

```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000006",
  "revision": 1,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00",
  "title": "example.txt",
  "url": "artifact:00000000-0000-4000-8000-000000000015",
  "sourceUrl": "artifact:00000000-0000-4000-8000-000000000015",
  "mediaType": "text/plain",
  "byteSize": 7,
  "checksum": "13550350a8681c84c861aac2e5b440161c2b33a3e4f302ac680ca5b686de48de",
  "citation": {
    "artifactId": "00000000-0000-4000-8000-000000000015",
    "artifactRevision": 1,
    "artifactChecksum": "13550350a8681c84c861aac2e5b440161c2b33a3e4f302ac680ca5b686de48de",
    "rights": {
      "retrieval": "unknown",
      "extraction": "unknown",
      "training": "unknown",
      "export": "unknown",
      "redistribution": "unknown"
    },
    "retention": {},
    "sourceArtifactIds": [],
    "sourceKind": "workspace_artifact"
  },
  "archiveStatus": "saved",
  "downloadName": "example.txt",
  "originalName": "example.txt",
  "originalDownloadUrl": "/api/library/sources/00000000-0000-4000-8000-000000000006/content?format=original",
  "textDownloadUrl": "/api/library/sources/00000000-0000-4000-8000-000000000006/content?format=text",
  "metadataDownloadUrl": "/api/library/sources/00000000-0000-4000-8000-000000000006/content?format=metadata",
  "downloadDirectory": "/private/example-downloads/00000000-0000-4000-8000-000000000001/00000000-0000-4000-8000-000000000002/00000000-0000-4000-8000-000000000006",
  "extractionStatus": "extracted",
  "deletedAt": null,
  "extractedText": "example\n"
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

**Exact JSON rules and response serialization:** [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [ArchiveArtifact](contracts-library.md#archiveartifact), [source_artifact](contracts-library.md#source_artifact), [LibraryService.archive_download](contracts-library.md#libraryservicearchive_download).

Source: `services/studio-api/src/studio/api/library.py:244` (`source_artifact`).

## POST /api/library/sources/fetch

Fetch and retain a public research source for human review.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** FetchSource JSON (camelCase aliases and Python field names are accepted; unknown keys rejected). Exact fields, bounds and defaults are in the linked request class.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `data` (required) | JSON body | `FetchSource` | `required` |

**Response:** Owned record descriptor with id, revision, timestamps and type-specific metadata; exact conditional shape is in LibraryService._record. Default success status: 201. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/library/sources/fetch HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "url": "https://example.org/source.txt",
  "title": "Example source",
  "citation": {
    "rights": {
      "retrieval": "allowed",
      "extraction": "allowed",
      "training": "allowed",
      "export": "allowed"
    }
  },
  "forceRefresh": false
}
```

**Success response example:** Illustrative public URL serves the synthetic text shown in the source-content example; actual network content/checksum/rights must be reviewed.

```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000006",
  "revision": 1,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00",
  "title": "Example source",
  "url": "https://example.org/source.txt",
  "sourceUrl": "https://example.org/source.txt",
  "mediaType": "text/plain",
  "byteSize": 25,
  "checksum": "7b69d4175ba56dab8ec303d5d064bd699aa5d9abbd7aabedeef68d382fc6a0b4",
  "citation": {
    "rights": {
      "retrieval": "allowed",
      "extraction": "allowed",
      "training": "allowed",
      "export": "allowed"
    }
  },
  "archiveStatus": "saved",
  "downloadName": "source.txt",
  "originalName": "source.txt",
  "originalDownloadUrl": "/api/library/sources/00000000-0000-4000-8000-000000000006/content?format=original",
  "textDownloadUrl": "/api/library/sources/00000000-0000-4000-8000-000000000006/content?format=text",
  "metadataDownloadUrl": "/api/library/sources/00000000-0000-4000-8000-000000000006/content?format=metadata",
  "downloadDirectory": "/private/example-downloads/00000000-0000-4000-8000-000000000001/00000000-0000-4000-8000-000000000002/00000000-0000-4000-8000-000000000006",
  "extractionStatus": "extracted",
  "deletedAt": null,
  "extractedText": "Example research source.\n"
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

**Exact JSON rules and response serialization:** [source_fetch](contracts-library.md#source_fetch), [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [FetchSource](contracts-library.md#fetchsource), [LibraryService.fetch_source](contracts-library.md#libraryservicefetch_source).

Source: `services/studio-api/src/studio/api/library.py:198` (`source_fetch`).

## POST /api/library/sources/upload

Retain an uploaded research file.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** Multipart file and optional title; nonempty original at most 24 MiB. PDF magic detection and supported extraction/media rules apply.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `file` (required) | multipart | `Annotated[UploadFile, File()]` | `required` |
| `title` (optional) | multipart | `str \| None` | `Form(default=None, max_length=500)` |

**Response:** Owned record descriptor with id, revision, timestamps and type-specific metadata; exact conditional shape is in LibraryService._record. Default success status: 201. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/library/sources/upload HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: multipart/form-data; boundary=studio-documentation-boundary

--studio-documentation-boundary
Content-Disposition: form-data; name="title"

Example source
--studio-documentation-boundary
Content-Disposition: form-data; name="file"; filename="source.txt"
Content-Type: text/plain

Example research source.

--studio-documentation-boundary--
```

**Success response example:** Multipart text is illustrative; a real multipart client uses CRLF boundaries. Uploaded source training/export rights initially remain unknown.

```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000006",
  "revision": 1,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "updatedAt": "2026-11-02T00:00:00+00:00",
  "title": "Example source",
  "url": "upload:00000000-0000-4000-8000-000000000021",
  "sourceUrl": "upload:00000000-0000-4000-8000-000000000021",
  "mediaType": "text/plain",
  "byteSize": 25,
  "checksum": "7b69d4175ba56dab8ec303d5d064bd699aa5d9abbd7aabedeef68d382fc6a0b4",
  "citation": {
    "sourceKind": "private_upload",
    "originalName": "source.txt",
    "rights": {
      "retrieval": "allowed",
      "extraction": "allowed",
      "training": "unknown",
      "export": "unknown"
    }
  },
  "archiveStatus": "saved",
  "downloadName": "source.txt",
  "originalName": "source.txt",
  "originalDownloadUrl": "/api/library/sources/00000000-0000-4000-8000-000000000006/content?format=original",
  "textDownloadUrl": "/api/library/sources/00000000-0000-4000-8000-000000000006/content?format=text",
  "metadataDownloadUrl": "/api/library/sources/00000000-0000-4000-8000-000000000006/content?format=metadata",
  "downloadDirectory": "/private/example-downloads/00000000-0000-4000-8000-000000000001/00000000-0000-4000-8000-000000000002/00000000-0000-4000-8000-000000000006",
  "extractionStatus": "extracted",
  "deletedAt": null,
  "extractedText": "Example research source.\n"
}
```

**Failure response example:** upload a nonempty research file up to 24 MiB.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "errors": [
    {
      "code": "VALIDATION",
      "message": "upload a nonempty research file up to 24 MiB",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [Contract](contracts-library.md#contract), [LibraryService._record](contracts-library.md#libraryservice_record), [source_upload](contracts-library.md#source_upload), [LibraryService.archive_download](contracts-library.md#libraryservicearchive_download).

Source: `services/studio-api/src/studio/api/library.py:210` (`source_upload`).
