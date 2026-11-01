# Polymer simulation API — JSON contract details

These excerpts are generated from the implementation without importing it. They specify accepted fields, conditional validation, defaults and response construction for flexible JSON interfaces. They complement the endpoint prose; implementation expressions refer to the named source service rather than a live execution.

## artifact

Source: `services/studio-api/src/studio/api/simulations.py:artifact`.

```python
@router.get("/jobs/{identifier}/artifacts/{name:path}")
def artifact(identifier: str, name: str, request: Request, db: DbSession, ctx: Ctx) -> FileResponse:
    path = _service(request, db, ctx).artifact_path(identifier, name)
    return FileResponse(path, media_type="application/octet-stream", filename=path.name)
```

## cancel

Source: `services/studio-api/src/studio/api/simulations.py:cancel`.

```python
@router.post("/jobs/{identifier}/cancel")
def cancel(identifier: str, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = _service(request, db, ctx).cancel_job(identifier)
    db.commit()
    return result
```

## capabilities

Source: `services/studio-api/src/studio/api/simulations.py:capabilities`.

```python
@router.get("/capabilities")
def capabilities(request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return _service(request, db, ctx).capabilities()
```

## create_job

Source: `services/studio-api/src/studio/api/simulations.py:create_job`.

```python
@router.post("/jobs")
def create_job(
    payload: dict[str, Any], request: Request, db: DbSession, ctx: Ctx
) -> dict[str, Any]:
    result = _service(request, db, ctx).create_job(payload)
    db.commit()
    return result
```

## job

Source: `services/studio-api/src/studio/api/simulations.py:job`.

```python
@router.get("/jobs/{identifier}")
def job(identifier: str, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    return _service(request, db, ctx).get_job(identifier)
```

## jobs

Source: `services/studio-api/src/studio/api/simulations.py:jobs`.

```python
@router.get("/jobs")
def jobs(
    request: Request, db: DbSession, ctx: Ctx, campaignId: str | None = None
) -> list[dict[str, Any]]:
    return _service(request, db, ctx).list_jobs(campaignId)
```

## resume

Source: `services/studio-api/src/studio/api/simulations.py:resume`.

```python
@router.post("/jobs/{identifier}/resume")
def resume(identifier: str, request: Request, db: DbSession, ctx: Ctx) -> dict[str, Any]:
    result = _service(request, db, ctx).resume_job(identifier)
    db.commit()
    return result
```

## SimulationService._record

Source: `services/studio-api/src/studio/domain/simulations/service.py:SimulationService._record`.

```python
    def _record(self, job: SimulationJob) -> dict[str, Any]:
        directory = job_directory(self.settings, job)
        artifacts: list[dict[str, Any]] = []
        if directory.exists():
            for path in sorted(directory.rglob("*")):
                if path.is_file() and not path.is_symlink() and len(artifacts) < 500:
                    artifacts.append(
                        {
                            "name": path.relative_to(directory).as_posix(),
                            "bytes": path.stat().st_size,
                        }
                    )
        return {
            "id": str(job.id),
            "name": job.name,
            "state": job.state,
            "config": job.config,
            "result": job.result,
            "events": job.events,
            "error": job.error,
            "attempt": job.attempt,
            "createdAt": job.created_at.isoformat() if job.created_at else None,
            "startedAt": job.started_at.isoformat() if job.started_at else None,
            "finishedAt": job.finished_at.isoformat() if job.finished_at else None,
            "elapsedSeconds": job.elapsed_seconds or 0,
            "artifacts": artifacts,
            "trainingEligible": bool(
                job.state == "completed" and job.result.get("trainingEligible")
            ),
            "cancelRequested": job.cancel_requested,
        }
```

## SimulationService.artifact_path

Source: `services/studio-api/src/studio/domain/simulations/service.py:SimulationService.artifact_path`.

```python
    def artifact_path(self, identifier: str, name: str) -> Path:
        directory = job_directory(self.settings, self._owned(identifier)).resolve()
        path = directory / name
        if (
            not name
            or path.is_symlink()
            or not path.is_file()
            or not path.resolve().is_relative_to(directory)
        ):
            raise DomainError(ErrorCode.NOT_FOUND, "Simulation artifact not found")
        return path
```

## SimulationService.cancel_job

Source: `services/studio-api/src/studio/domain/simulations/service.py:SimulationService.cancel_job`.

```python
    def cancel_job(self, identifier: str) -> dict[str, Any]:
        job = self._owned(identifier)
        if job.state not in TERMINAL:
            job.cancel_requested = True
            if job.state == "queued":
                job.state, job.finished_at = "cancelled", datetime.now(UTC)
            self.db.flush()
        return self._record(job)
```

## SimulationService.capabilities

Source: `services/studio-api/src/studio/domain/simulations/service.py:SimulationService.capabilities`.

```python
    def capabilities(self) -> dict[str, Any]:
        return {
            **runtime_capability(),
            "maxAtoms": 2000,
            "replicates": 2,
            "temperatureK": 300,
            "pressureAtm": 1,
            "forceField": "GAFF2",
            "chargeMethod": "Gasteiger",
            "protocol": "radonpy_eq21_pilot",
            "referenceRepeatSmiles": PET_REPEAT,
        }
```

## SimulationService.create_job

Source: `services/studio-api/src/studio/domain/simulations/service.py:SimulationService.create_job`.

```python
    def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        config = validate_payload(payload)
        if not runtime_capability().get("available"):
            raise DomainError(
                ErrorCode.ENGINE_UNAVAILABLE,
                "RadonPy and the native LAMMPS runtime are unavailable",
            )
        path = self.settings.vault_root
        while not path.exists():
            path = path.parent
        if shutil.disk_usage(path).free < 512 * 1024 * 1024:
            raise DomainError(
                ErrorCode.LOCAL_INFEASIBLE, "Simulation needs at least 512 MiB free storage"
            )
        name = payload.get("name", "Polymer MD pilot")
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise DomainError(
                ErrorCode.VALIDATION, "Simulation name must contain 1 to 200 characters"
            )
        from studio.domain.agent_workspace.workflows import admit_job, record_job

        workflow, seconds = admit_job(self.db, self.ctx, {**payload, **config}, "simulation")
        if workflow:
            config.update({"campaignId": str(workflow.id), "maxWallSeconds": seconds})
        config["inputDigest"] = hashlib.sha256(
            json.dumps(config, sort_keys=True).encode()
        ).hexdigest()
        job = SimulationJob(
            workspace_id=self.ctx.workspace_id,
            owner_id=self.ctx.principal_id,
            name=name.strip(),
            config=config,
            result={},
            events=[],
            state="queued",
        )
        self.db.add(job)
        self.db.flush()
        record_job(self.db, workflow, job.id, "simulation", seconds)
        return self._record(job)
```

## SimulationService.get_job

Source: `services/studio-api/src/studio/domain/simulations/service.py:SimulationService.get_job`.

```python
    def get_job(self, identifier: str) -> dict[str, Any]:
        return self._record(self._owned(identifier))
```

## SimulationService.list_jobs

Source: `services/studio-api/src/studio/domain/simulations/service.py:SimulationService.list_jobs`.

```python
    def list_jobs(self, campaign_id: str | None = None) -> list[dict[str, Any]]:
        rows = self.db.scalars(
            select(SimulationJob)
            .where(
                SimulationJob.workspace_id == self.ctx.workspace_id,
                SimulationJob.owner_id == self.ctx.principal_id,
            )
            .order_by(SimulationJob.created_at.desc())
            .limit(200)
        )
        return [
            self._record(row)
            for row in rows
            if not campaign_id or row.config.get("campaignId") == campaign_id
        ]
```

## SimulationService.resume_job

Source: `services/studio-api/src/studio/domain/simulations/service.py:SimulationService.resume_job`.

```python
    def resume_job(self, identifier: str) -> dict[str, Any]:
        job = self._owned(identifier)
        if job.state not in {"cancelled", "timed_out", "interrupted", "blocked", "failed"}:
            raise DomainError(
                ErrorCode.CONFLICT,
                "Only stopped simulations can resume",
            )
        if job.state == "failed" and not has_stage_checkpoint(self.settings, job):
            raise DomainError(
                ErrorCode.CONFLICT, "Failed simulation has no completed stage checkpoint"
            )
        from studio.domain.agent_workspace.workflows import admit_job, record_job

        workflow, seconds = admit_job(self.db, self.ctx, dict(job.config), "simulation")
        if not runtime_capability().get("available"):
            raise DomainError(ErrorCode.ENGINE_UNAVAILABLE, "Simulation runtime is unavailable")
        if job.elapsed_seconds >= job.config["maxWallSeconds"]:
            raise DomainError(
                ErrorCode.LOCAL_INFEASIBLE, "Simulation exhausted its total compute-time budget"
            )
        if workflow:
            remaining = max(0, job.config["maxWallSeconds"] - job.elapsed_seconds)
            job.config = {
                **job.config,
                "maxWallSeconds": job.elapsed_seconds + min(seconds, remaining),
            }
            record_job(self.db, workflow, job.id, "simulation", min(seconds, int(remaining)))
        job.state, job.error, job.cancel_requested, job.finished_at = "queued", None, False, None
        self.db.flush()
        return self._record(job)
```

## runtime_capability

Source: `services/studio-api/src/studio/domain/simulations/service.py:runtime_capability`.

```python
def runtime_capability() -> dict[str, Any]:
    try:
        result = subprocess.run(  # noqa: S603 — fixed probe in administrator-controlled interpreter
            [
                runtime_python(),
                "-c",
                "from workers.simulation.radonpy_worker import capability; "
                "import json; print(json.dumps(capability()))",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env={
                **{
                    k: os.environ[k]
                    for k in ("PATH", "LANG", "LC_ALL", "TMPDIR")
                    if k in os.environ
                },
                "PYTHONPATH": str(Path(__file__).resolve().parents[6]),
            },
        )
        value = json.loads(result.stdout.strip().splitlines()[-1]) if result.returncode == 0 else {}
        if isinstance(value, dict) and "available" in value:
            return value
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        pass
    return {
        "available": False,
        "backend": "radonpy_lammps",
        "reason": "Install the isolated RadonPy/LAMMPS runtime",
        "execution": "native_cpu",
    }
```

## validate_payload

Source: `services/studio-api/src/studio/domain/simulations/service.py:validate_payload`.

```python
def validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    from rdkit import Chem

    repeat = payload.get("repeatSmiles")
    if not isinstance(repeat, str) or not 1 <= len(repeat) <= 1200:
        raise DomainError(ErrorCode.VALIDATION, "A polymer repeat PSMILES is required")
    mol = Chem.MolFromSmiles(repeat)
    if mol is None or len(Chem.GetMolFrags(mol)) != 1:
        raise DomainError(
            ErrorCode.VALIDATION, "Repeat PSMILES must be a single valid connected structure"
        )
    stars = [atom for atom in mol.GetAtoms() if atom.GetAtomicNum() == 0]
    if len(stars) != 2 or any(a.GetDegree() != 1 for a in stars):
        raise DomainError(
            ErrorCode.VALIDATION,
            "Repeat PSMILES requires exactly two singly connected * attachment atoms",
        )
    if any(a.GetAtomicNum() not in {0, 1, 6, 7, 8, 9, 15, 16, 17, 35} for a in mol.GetAtoms()):
        raise DomainError(
            ErrorCode.ENGINE_UNSUPPORTED_INPUT, "Pilot supports GAFF2 organic elements only"
        )
    if Chem.GetFormalCharge(mol) != 0:
        raise DomainError(ErrorCode.ENGINE_UNSUPPORTED_INPUT, "Pilot requires neutral repeat units")
    caps = {}
    for name, default in (("headCapSmiles", "*C"), ("tailCapSmiles", "*OC")):
        endcap = payload.get(name, payload.get("endCapSmiles", default))
        if not isinstance(endcap, str) or len(endcap) > 100:
            raise DomainError(ErrorCode.VALIDATION, "End cap must be a bounded PSMILES")
        cap = Chem.MolFromSmiles(endcap)
        cap_stars = [a for a in cap.GetAtoms() if a.GetAtomicNum() == 0] if cap else []
        if (
            cap is None
            or len(Chem.GetMolFrags(cap)) != 1
            or len(cap_stars) != 1
            or cap_stars[0].GetDegree() != 1
        ):
            raise DomainError(
                ErrorCode.VALIDATION,
                "End cap requires exactly one singly connected * attachment atom",
            )
        caps[name] = Chem.MolToSmiles(cap)
        if Chem.GetFormalCharge(cap) != 0:
            raise DomainError(ErrorCode.ENGINE_UNSUPPORTED_INPUT, "Pilot requires neutral end caps")
    seeds = payload.get("seeds", [1729, 1733])
    if not isinstance(seeds, list) or len(seeds) != 2 or len(set(str(x) for x in seeds)) != 2:
        raise DomainError(
            ErrorCode.VALIDATION, "Exactly two distinct integer simulation seeds are required"
        )
    seeds = [_integer(seed, "seed", 1, 2_147_483_647) for seed in seeds]
    repeats = _integer(payload.get("repeats", 8), "repeats", 2, 64)
    chains = _integer(payload.get("chains", 4), "chains", 1, 32)
    maximum = _integer(payload.get("maxAtoms", 2000), "maxAtoms", 20, 2000)
    if (mol.GetNumHeavyAtoms() - 2) * repeats * chains > maximum:
        raise DomainError(
            ErrorCode.LOCAL_INFEASIBLE,
            "Requested cell exceeds the atom budget before hydrogens and end caps",
        )
    for name, required in (("temperatureK", 300), ("pressureAtm", 1)):
        if payload.get(name, required) != required:
            raise DomainError(ErrorCode.VALIDATION, "This pilot uses 300 K and 1 atm only")
    scale = payload.get("protocolScale", 0.01)
    if (
        isinstance(scale, bool)
        or not isinstance(scale, (float, int))
        or not math.isfinite(scale)
        or not 0.001 <= scale <= 1
    ):
        raise DomainError(ErrorCode.VALIDATION, "protocolScale must be between 0.001 and 1")
    protocol = payload.get("protocol", "radonpy_eq21_pilot")
    if protocol != "radonpy_eq21_pilot":
        raise DomainError(ErrorCode.VALIDATION, "Unknown simulation protocol")
    return {
        # The first/second attachment atom in the submitted orientation selects
        # the explicit head/tail cap; canonicalization must not swap that meaning.
        "repeatSmiles": repeat.strip(),
        "canonicalRepeatSmiles": Chem.MolToSmiles(mol),
        **caps,
        "repeats": repeats,
        "chains": chains,
        "seeds": seeds,
        "maxAtoms": maximum,
        "temperatureK": 300,
        "pressureAtm": 1,
        "maxTemperatureK": 600,
        "maxPressureAtm": 50000,
        "protocol": protocol,
        "protocolScale": float(scale),
        "samplingSteps": _integer(
            payload.get("samplingSteps", 50000), "samplingSteps", 5000, 5_000_000
        ),
        "maxWallSeconds": _integer(
            payload.get("maxWallSeconds", 1800), "maxWallSeconds", 30, 14400
        ),
        "forceField": "GAFF2",
        "chargeMethod": "Gasteiger",
        "threads": 2,
        "scientificStatus": "computational_pilot_not_experiment",
    }
```
