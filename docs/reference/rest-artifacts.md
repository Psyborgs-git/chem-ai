# Artifact transfer API

Size-checked staging, streaming upload, digest verification, finalization and scoped downloads.

[Shared authentication, errors and transport](rest-overview.md). Examples use synthetic values; replace resource IDs with records from your workspace.

## GET /api/artifacts/{artifact_id}

Read scoped artifact metadata.

**Access:** Authenticated principal; ArtifactService verifies capability, workspace and access scope.

**Request:** artifact_id path UUID; no body.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `artifact_id` (required) | path | `uuid.UUID` | `required` |

**Response:** Artifact state, digest, media type, byte size, review state and provenance metadata. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/artifacts/00000000-0000-4000-8000-000000000015 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** The principal has read_project for this artifact scope; field values show one synthetic newly committed artifact.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "artifactId": "00000000-0000-4000-8000-000000000015",
  "mediaType": "text/plain",
  "byteSize": 8,
  "checksumSha256": "13550350a8681c84c861aac2e5b440161c2b33a3e4f302ac680ca5b686de48de",
  "uploadState": "committed",
  "reviewState": "quarantined",
  "classification": "confidential",
  "rights": {
    "retrieval": "unknown",
    "extraction": "unknown",
    "training": "unknown",
    "export": "unknown",
    "redistribution": "unknown"
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

**Exact JSON rules and response serialization:** [artifact_metadata](contracts-artifacts.md#artifact_metadata).

Source: `services/studio-api/src/studio/api/transfers/routes.py:156` (`artifact_metadata`).

## GET /api/artifacts/{artifact_id}/content

Stream a permitted committed artifact.

**Access:** Authenticated principal; ArtifactService verifies capability, workspace and access scope.

**Request:** artifact_id path UUID; no body.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `artifact_id` (required) | path | `uuid.UUID` | `required` |

**Response:** Binary streaming content with content type and download headers, not JSON. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/artifacts/00000000-0000-4000-8000-000000000015/content HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** The committed artifact is permitted for this principal; successful metadata access alone does not establish download/reuse rights.

```http
HTTP/1.1 200 OK
Content-Type: text/plain
Content-Disposition: attachment; filename="artifact-00000000-0000-4000-8000-000000000015"
X-Content-SHA256: 13550350a8681c84c861aac2e5b440161c2b33a3e4f302ac680ca5b686de48de
Cache-Control: private, no-store

example

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

**Exact JSON rules and response serialization:** [download_content](contracts-artifacts.md#download_content).

Source: `services/studio-api/src/studio/api/transfers/routes.py:131` (`download_content`).

## POST /api/artifacts/uploads

Create a scoped artifact upload staging record.

**Access:** Authenticated principal; ArtifactService verifies capability, workspace and access scope.

**Request:** JSON original_name, media_type, optional declared_size, declared_checksum and access_scope.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `body` (required) | JSON body | `InitiateUploadRequest` | `required` |

**Response:** artifactId, uploadState and maxBytes. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/artifacts/uploads HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "original_name": "example.txt",
  "media_type": "text/plain",
  "declared_size": 8,
  "declared_checksum": "13550350a8681c84c861aac2e5b440161c2b33a3e4f302ac680ca5b686de48de"
}
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "artifactId": "00000000-0000-4000-8000-000000000015",
  "uploadState": "receiving",
  "maxBytes": 536870912
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

**Exact JSON rules and response serialization:** [initiate_upload](contracts-artifacts.md#initiate_upload), [InitiateUploadRequest](contracts-artifacts.md#initiateuploadrequest).

Source: `services/studio-api/src/studio/api/transfers/routes.py:56` (`initiate_upload`).

## POST /api/artifacts/uploads/{artifact_id}/abort

Abort a staged artifact upload.

**Access:** Authenticated principal; ArtifactService verifies capability, workspace and access scope.

**Request:** artifact_id path UUID; no body.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `artifact_id` (required) | path | `uuid.UUID` | `required` |

**Response:** Artifact upload state; partial bytes are discarded according to vault staging behavior. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/artifacts/uploads/00000000-0000-4000-8000-000000000015/abort HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** An accessible staged upload is aborted; bytes are not promoted to committed content.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "artifactId": "00000000-0000-4000-8000-000000000015",
  "uploadState": "aborted"
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

**Exact JSON rules and response serialization:** [abort_upload](contracts-artifacts.md#abort_upload).

Source: `services/studio-api/src/studio/api/transfers/routes.py:121` (`abort_upload`).

## POST /api/artifacts/uploads/{artifact_id}/finish

Verify the final checksum/size and commit an artifact.

**Access:** Authenticated principal; ArtifactService verifies capability, workspace and access scope.

**Request:** Optional JSON checksum; declared checksums and archive limits are also validated.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `artifact_id` (required) | path | `uuid.UUID` | `required` |
| `body` (optional) | JSON body | `FinishUploadRequest \| None` | `None` |

**Response:** artifactId, uploadState, checksumSha256, byteSize and reviewState; rejected/aborted markers persist on validation failure. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/artifacts/uploads/00000000-0000-4000-8000-000000000015/finish HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "checksum": "13550350a8681c84c861aac2e5b440161c2b33a3e4f302ac680ca5b686de48de"
}
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "artifactId": "00000000-0000-4000-8000-000000000015",
  "uploadState": "committed",
  "checksumSha256": "13550350a8681c84c861aac2e5b440161c2b33a3e4f302ac680ca5b686de48de",
  "byteSize": 8,
  "reviewState": "quarantined"
}
```

**Failure response example:** uploaded bytes do not match the declared checksum.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "errors": [
    {
      "code": "VALIDATION",
      "message": "uploaded bytes do not match the declared checksum",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [finish_upload](contracts-artifacts.md#finish_upload), [FinishUploadRequest](contracts-artifacts.md#finishuploadrequest).

Source: `services/studio-api/src/studio/api/transfers/routes.py:96` (`finish_upload`).

## PUT /api/artifacts/uploads/{artifact_id}/content

Append raw request-body bytes to an upload staging file.

**Access:** Authenticated principal; ArtifactService verifies capability, workspace and access scope.

**Request:** Raw bytes; artifact_id identifies a permitted upload. Chunks append rather than replace.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `artifact_id` (required) | path | `uuid.UUID` | `required` |

**Response:** bytesReceived total. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
PUT /api/artifacts/uploads/00000000-0000-4000-8000-000000000015/content HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/octet-stream

example

```

**Success response example:** The example appends seven bytes to an initially empty staged upload. Repeating the request appends bytes; it is not a replacement upload.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "bytesReceived": 8
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

**Exact JSON rules and response serialization:** [stream_content](contracts-artifacts.md#stream_content).

Source: `services/studio-api/src/studio/api/transfers/routes.py:77` (`stream_content`).
