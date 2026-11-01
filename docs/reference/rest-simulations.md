# Polymer simulation API

Owner-private atomistic polymer MD pilot jobs, capability checks, artifacts and checkpoint recovery.

[Shared authentication, errors and transport](rest-overview.md). Examples use synthetic values; replace resource IDs with records from your workspace.

## GET /api/simulations/capabilities

Read the polymer MD pilot runtime and fixed protocol limits.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No body.

**Response:** Runtime availability plus maxAtoms=2000, replicates=2, temperatureK=300, pressureAtm=1, forceField=GAFF2, chargeMethod=Gasteiger, protocol and referenceRepeatSmiles. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/simulations/capabilities HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** The isolated simulation runtime is unavailable; the capability route still succeeds and reports fixed protocol constraints.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "available": false,
  "backend": "radonpy_lammps",
  "reason": "Install the isolated RadonPy/LAMMPS runtime",
  "execution": "native_cpu",
  "maxAtoms": 2000,
  "replicates": 2,
  "temperatureK": 300,
  "pressureAtm": 1,
  "forceField": "GAFF2",
  "chargeMethod": "Gasteiger",
  "protocol": "radonpy_eq21_pilot",
  "referenceRepeatSmiles": "*OCCOC(=O)c1ccc(C(=O)*)cc1"
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

**Exact JSON rules and response serialization:** [capabilities](contracts-simulations.md#capabilities), [SimulationService.capabilities](contracts-simulations.md#simulationservicecapabilities), [runtime_capability](contracts-simulations.md#runtime_capability).

Source: `services/studio-api/src/studio/api/simulations.py:21` (`capabilities`).

## GET /api/simulations/jobs

List owner-private simulation jobs, optionally filtered by campaignId.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No body; identifier is required for one job, campaignId is an optional list filter.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `campaignId` (optional) | query | `str \| None` | `None` |

**Response:** Job id/name/state/config/result/events/error, attempt, timing, artifacts, trainingEligible and cancelRequested. The list endpoint returns an array. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/simulations/jobs?campaignId=00000000-0000-4000-8000-000000000014 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** This owner has no simulations in the selected campaign.

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

**Exact JSON rules and response serialization:** [jobs](contracts-simulations.md#jobs), [SimulationService.list_jobs](contracts-simulations.md#simulationservicelist_jobs), [SimulationService._record](contracts-simulations.md#simulationservice_record).

Source: `services/studio-api/src/studio/api/simulations.py:26` (`jobs`).

## GET /api/simulations/jobs/{identifier}

Read a polymer MD pilot job.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No body; identifier is required for one job, campaignId is an optional list filter.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `identifier` (required) | path | `str` | `required` |

**Response:** Job id/name/state/config/result/events/error, attempt, timing, artifacts, trainingEligible and cancelRequested. The list endpoint returns an array. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/simulations/jobs/00000000-0000-4000-8000-000000000013 HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** Illustrative synthetic response; replace example UUIDs with accessible records returned by this installation. Timestamps and other generated values are examples, not live workspace state.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000013",
  "name": "PET documentation pilot",
  "state": "queued",
  "config": {
    "repeatSmiles": "*OCCOC(=O)c1ccc(C(=O)*)cc1",
    "canonicalRepeatSmiles": "*OCCOC(=O)c1ccc(C(*)=O)cc1",
    "headCapSmiles": "*C",
    "tailCapSmiles": "*OC",
    "repeats": 2,
    "chains": 2,
    "seeds": [
      1729,
      1733
    ],
    "maxAtoms": 2000,
    "temperatureK": 300,
    "pressureAtm": 1,
    "maxTemperatureK": 600,
    "maxPressureAtm": 50000,
    "protocol": "radonpy_eq21_pilot",
    "protocolScale": 0.001,
    "samplingSteps": 5000,
    "maxWallSeconds": 1800,
    "forceField": "GAFF2",
    "chargeMethod": "Gasteiger",
    "threads": 2,
    "scientificStatus": "computational_pilot_not_experiment",
    "inputDigest": "7eaa3ead898825f838939eb01f68d399d453fee738c778aec551507e2240da2f"
  },
  "result": {},
  "events": [],
  "error": null,
  "attempt": 0,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "startedAt": null,
  "finishedAt": null,
  "elapsedSeconds": 0,
  "artifacts": [],
  "trainingEligible": false,
  "cancelRequested": false
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

**Exact JSON rules and response serialization:** [job](contracts-simulations.md#job), [SimulationService.get_job](contracts-simulations.md#simulationserviceget_job), [SimulationService._record](contracts-simulations.md#simulationservice_record).

Source: `services/studio-api/src/studio/api/simulations.py:42` (`job`).

## GET /api/simulations/jobs/{identifier}/artifacts/{name:path}

Download a retained simulation artifact.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** identifier and relative name path parameters; no body.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `identifier` (required) | path | `str` | `required` |
| `name` (required) | path | `str` | `required` |

**Response:** Binary application/octet-stream attachment for an owned job; no arbitrary filesystem access. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
GET /api/simulations/jobs/00000000-0000-4000-8000-000000000013/artifacts/result.json HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** The owned simulation has a retained result.json artifact. Example output is computational pilot metadata.

```http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="result.json"

{"scientificStatus":"computational_pilot_not_experiment","trainingEligible":false}
```

**Failure response example:** Simulation artifact not found.

```http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "Simulation artifact not found",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [artifact](contracts-simulations.md#artifact), [SimulationService.artifact_path](contracts-simulations.md#simulationserviceartifact_path).

Source: `services/studio-api/src/studio/api/simulations.py:61` (`artifact`).

## POST /api/simulations/jobs

Validate and queue a bounded polymer atomistic MD pilot.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** repeatSmiles with exactly two terminal attachment atoms; optional headCapSmiles/tailCapSmiles/endCapSmiles, repeats, chains, two distinct integer seeds, maxAtoms, protocolScale, samplingSteps, maxWallSeconds, name and campaignId. Neutral supported organic structures only; 300 K and 1 atm are fixed.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `payload` (required) | JSON body | `dict[str, Any]` | `required` |

**Response:** Simulation job descriptor; computational_pilot_not_experiment status is preserved. This does not establish an experimental property. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/simulations/jobs HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
Content-Type: application/json

{
  "name": "PET documentation pilot",
  "repeatSmiles": "*OCCOC(=O)c1ccc(C(=O)*)cc1",
  "headCapSmiles": "*C",
  "tailCapSmiles": "*OC",
  "repeats": 2,
  "chains": 2,
  "seeds": [
    1729,
    1733
  ],
  "maxAtoms": 2000,
  "protocolScale": 0.001,
  "samplingSteps": 5000,
  "maxWallSeconds": 1800
}
```

**Success response example:** The optional native simulation runtime is available, storage/admission pass, and this validated small pilot is queued. No simulation or material result is claimed by the acknowledgment.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000013",
  "name": "PET documentation pilot",
  "state": "queued",
  "config": {
    "repeatSmiles": "*OCCOC(=O)c1ccc(C(=O)*)cc1",
    "canonicalRepeatSmiles": "*OCCOC(=O)c1ccc(C(*)=O)cc1",
    "headCapSmiles": "*C",
    "tailCapSmiles": "*OC",
    "repeats": 2,
    "chains": 2,
    "seeds": [
      1729,
      1733
    ],
    "maxAtoms": 2000,
    "temperatureK": 300,
    "pressureAtm": 1,
    "maxTemperatureK": 600,
    "maxPressureAtm": 50000,
    "protocol": "radonpy_eq21_pilot",
    "protocolScale": 0.001,
    "samplingSteps": 5000,
    "maxWallSeconds": 1800,
    "forceField": "GAFF2",
    "chargeMethod": "Gasteiger",
    "threads": 2,
    "scientificStatus": "computational_pilot_not_experiment",
    "inputDigest": "7eaa3ead898825f838939eb01f68d399d453fee738c778aec551507e2240da2f"
  },
  "result": {},
  "events": [],
  "error": null,
  "attempt": 0,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "startedAt": null,
  "finishedAt": null,
  "elapsedSeconds": 0,
  "artifacts": [],
  "trainingEligible": false,
  "cancelRequested": false
}
```

**Failure response example:** RadonPy and the native LAMMPS runtime are unavailable.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "errors": [
    {
      "code": "ENGINE_UNAVAILABLE",
      "message": "RadonPy and the native LAMMPS runtime are unavailable",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [create_job](contracts-simulations.md#create_job), [SimulationService.create_job](contracts-simulations.md#simulationservicecreate_job), [validate_payload](contracts-simulations.md#validate_payload), [SimulationService._record](contracts-simulations.md#simulationservice_record).

Source: `services/studio-api/src/studio/api/simulations.py:33` (`create_job`).

## POST /api/simulations/jobs/{identifier}/cancel

Request polymer MD process-tree cancellation.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No body; identifier is required for one job, campaignId is an optional list filter.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `identifier` (required) | path | `str` | `required` |

**Response:** Job id/name/state/config/result/events/error, attempt, timing, artifacts, trainingEligible and cancelRequested. The list endpoint returns an array. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/simulations/jobs/00000000-0000-4000-8000-000000000013/cancel HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** The job was queued; running jobs first acknowledge cancellation and stop their process group asynchronously.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000013",
  "name": "PET documentation pilot",
  "state": "cancelled",
  "config": {
    "repeatSmiles": "*OCCOC(=O)c1ccc(C(=O)*)cc1",
    "canonicalRepeatSmiles": "*OCCOC(=O)c1ccc(C(*)=O)cc1",
    "headCapSmiles": "*C",
    "tailCapSmiles": "*OC",
    "repeats": 2,
    "chains": 2,
    "seeds": [
      1729,
      1733
    ],
    "maxAtoms": 2000,
    "temperatureK": 300,
    "pressureAtm": 1,
    "maxTemperatureK": 600,
    "maxPressureAtm": 50000,
    "protocol": "radonpy_eq21_pilot",
    "protocolScale": 0.001,
    "samplingSteps": 5000,
    "maxWallSeconds": 1800,
    "forceField": "GAFF2",
    "chargeMethod": "Gasteiger",
    "threads": 2,
    "scientificStatus": "computational_pilot_not_experiment",
    "inputDigest": "7eaa3ead898825f838939eb01f68d399d453fee738c778aec551507e2240da2f"
  },
  "result": {},
  "events": [],
  "error": null,
  "attempt": 0,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "startedAt": null,
  "finishedAt": "2026-11-02T00:00:00+00:00",
  "elapsedSeconds": 0,
  "artifacts": [],
  "trainingEligible": false,
  "cancelRequested": true
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

**Exact JSON rules and response serialization:** [cancel](contracts-simulations.md#cancel), [SimulationService.cancel_job](contracts-simulations.md#simulationservicecancel_job), [SimulationService._record](contracts-simulations.md#simulationservice_record).

Source: `services/studio-api/src/studio/api/simulations.py:47` (`cancel`).

## POST /api/simulations/jobs/{identifier}/resume

Resume a recoverable polymer MD job from completed stage checkpoints.

**Access:** Authenticated principal; private workspace/owner ownership checks apply in the service.

**Request:** No body; identifier is required for one job, campaignId is an optional list filter.

| Parameter | Location | Declared type | Default / constraints |
| --- | --- | --- | --- |
| `identifier` (required) | path | `str` | `required` |

**Response:** Job id/name/state/config/result/events/error, attempt, timing, artifacts, trainingEligible and cancelRequested. The list endpoint returns an array. Default success status: 200. Availability: core.

**Failures:** Authentication/capability failures return UNAUTHENTICATED or FORBIDDEN; inaccessible IDs return NOT_FOUND. Invalid fields or state return typed VALIDATION/CONFLICT errors; see the exact validation excerpts and shared error table.

**Request example:**

```http
POST /api/simulations/jobs/00000000-0000-4000-8000-000000000013/resume HTTP/1.1
Host: 127.0.0.1:8787
Cookie: studio_session=<your-session>
```

**Success response example:** The stopped simulation has a compatible runtime, retained stage state where required, and remaining cumulative wall-clock budget.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "00000000-0000-4000-8000-000000000013",
  "name": "PET documentation pilot",
  "state": "queued",
  "config": {
    "repeatSmiles": "*OCCOC(=O)c1ccc(C(=O)*)cc1",
    "canonicalRepeatSmiles": "*OCCOC(=O)c1ccc(C(*)=O)cc1",
    "headCapSmiles": "*C",
    "tailCapSmiles": "*OC",
    "repeats": 2,
    "chains": 2,
    "seeds": [
      1729,
      1733
    ],
    "maxAtoms": 2000,
    "temperatureK": 300,
    "pressureAtm": 1,
    "maxTemperatureK": 600,
    "maxPressureAtm": 50000,
    "protocol": "radonpy_eq21_pilot",
    "protocolScale": 0.001,
    "samplingSteps": 5000,
    "maxWallSeconds": 1800,
    "forceField": "GAFF2",
    "chargeMethod": "Gasteiger",
    "threads": 2,
    "scientificStatus": "computational_pilot_not_experiment",
    "inputDigest": "7eaa3ead898825f838939eb01f68d399d453fee738c778aec551507e2240da2f"
  },
  "result": {},
  "events": [],
  "error": null,
  "attempt": 0,
  "createdAt": "2026-11-02T00:00:00+00:00",
  "startedAt": null,
  "finishedAt": null,
  "elapsedSeconds": 0,
  "artifacts": [],
  "trainingEligible": false,
  "cancelRequested": false
}
```

**Failure response example:** Only stopped simulations can resume.

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "errors": [
    {
      "code": "CONFLICT",
      "message": "Only stopped simulations can resume",
      "fieldPath": null,
      "retryable": false,
      "safeDetails": {}
    }
  ]
}
```

**Exact JSON rules and response serialization:** [resume](contracts-simulations.md#resume), [SimulationService.resume_job](contracts-simulations.md#simulationserviceresume_job), [SimulationService._record](contracts-simulations.md#simulationservice_record).

Source: `services/studio-api/src/studio/api/simulations.py:54` (`resume`).
