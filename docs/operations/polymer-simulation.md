# Atomistic polymer simulation pilots

The private simulation workspace targets RadonPy 0.2.11, GAFF2, Gasteiger
charges and native ARM64 LAMMPS 22 July 2025 Update 4. Check its capability probe
on the current machine before creating work. These are amorphous,
finite-chain all-atom computational pilots. Their output does not establish
silk equivalence, fabric hand, drape, tensile properties or experimental results.

## Isolated runtime

```sh
uv run python -m venv .runtime/simulation-radonpy
.runtime/simulation-radonpy/bin/python -m pip install -r workers/simulation/requirements.lock
```

The API discovers this interpreter automatically. `STUDIO_SIMULATION_PYTHON`
selects another administrator-configured interpreter, and `STUDIO_LAMMPS_EXEC`
selects a trusted native LAMMPS executable. Optional scientific dependencies stay
outside the API environment. The worker receives a restricted environment with
no API keys or session credentials.

The pinned PyPI LAMMPS wheel requires MPICH; the lock includes MPICH 5.0.2.
Native probes and execution bound hwloc processor discovery to a synthetic
one-package, two-core topology. This avoids a verified macOS hwloc discovery
loop and allocates two OpenMP threads to a single MPI process. It changes CPU
topology discovery, not molecular coordinates or simulation measurements.

## Inputs and procedure

`POST /api/simulations/jobs` accepts a name, repeat-unit PSMILES, explicit head
and tail end caps, repeat count, chain count, two distinct seeds, bounded wall
clock and optional `campaignId`. The default PET control is:

```json
{
  "name": "PET amorphous control",
  "repeatSmiles": "*OCCOC(=O)c1ccc(C(=O)*)cc1",
  "headCapSmiles": "*C",
  "tailCapSmiles": "*OC",
  "repeats": 8,
  "chains": 4,
  "seeds": [1729, 1733],
  "maxAtoms": 2000,
  "protocolScale": 0.01,
  "samplingSteps": 50000,
  "maxWallSeconds": 1800
}
```

The first and second attachment atoms in the submitted repeat orientation map
to the head and tail caps. The example uses methoxy/methyl-ester capped PET.
The repeat's canonical identity is recorded separately; canonicalization does
not silently swap end-cap meaning. The older `endCapSmiles` field explicitly
applies the same cap to both ends. Different repeat orientations or chemistries
require appropriate explicit caps.

The worker embeds and assembles hydrogen-complete chains, rejects cells above
2,000 atoms, assigns every GAFF2 interaction and finite Gasteiger atomic charge,
and verifies charge sums. Failed assignment blocks execution; there is no
zero-charge or alternative-force-field fallback.

The protocol uses RadonPy's packing stage, all seven triplets of the Larsen
21-step compression/decompression schedule, and NPT sampling at 300 K and 1 atm.
The recorded maximum annealing temperature is 600 K and compression pressure is
50,000 atm. `protocolScale` uniformly scales packing/compression step counts;
the default 0.01 is deliberately a shortened pilot. Sampling uses a 1 fs time
step, so the default 50,000 steps represent 50 ps per seed.

Raw thermo rows drive diagnostics. LAMMPS warnings are retained in original logs
and skipped only when extracting numeric rows for RadonPy analysis. Numeric
stability and RadonPy convergence are separate fields. A shortened pilot is
always ineligible for training labels, even if its short-window convergence
check passes. Eligibility additionally requires the full unscaled protocol,
at least 5 ns of final sampling, successful checks and both independent seeds.
No automatic scientific approval or experimental label is created.

## Durable execution and outputs

The authenticated owner alone can list/read jobs, cancel/resume them, or download
`/api/simulations/jobs/{id}/artifacts/{name}`. Workspace administrator grants do
not widen this owner scope. `GET /api/simulations/capabilities` reports the real
runtime and version probe; no fixture result substitutes for missing software.

Jobs persist states, attempts, events, `startedAt`, `finishedAt`, cumulative
`elapsedSeconds`, input digest and results. Campaign admission shares the
research workflow's compute ledger. Local dispatch checks the shared heavy-job
lock used by training. A job's original total wall-clock cap includes resumed
attempts; it does not reset on resume.

Raw LAMMPS inputs, force-field reports, thermo logs, XTC/dump trajectories,
binary restarts, stage JSON molecule checkpoints and analysis files remain in
the owner's vault. Cancellation and timeout stop the whole process group.
Completed stages and seeds can be resumed; an interrupted stage starts again
from the last completed stage, rather than claiming a bit-exact binary restart.
An API lease watchdog stops orphaned workers after a backend crash. Insufficient
storage blocks new work or stops a running job without evicting old artifacts.

## Verification and recovery

Use the capability probe and actual job events to confirm runtime availability,
versions, parameterization, convergence, and eligibility. Historical native PET
pilot artifacts under `.runtime/simulation-smoke-pet-capped/` demonstrate execution
on their recorded inputs; they do not establish current runtime readiness,
material quality, convergence, or an eligible training label.

Unit tests cover input bounds, neutral structures, end-cap orientation, and
thermo warning parsing. Integration tests cover owner isolation, artifact paths,
heavy-job exclusion, cancellation, and stage-checkpoint resumption. The optional
real MD check requires the isolated runtime and performs actual compute:

```sh
STUDIO_SIMULATION_REAL_TEST=1 .venv/bin/python -m pytest \
  services/studio-api/tests/integration/test_simulations.py
```

The owning runtime contract is `workers/simulation/requirements.lock` and
`workers/simulation`; backend behavior is under `studio.domain.simulations`.
Keep raw logs and method/parameter provenance when reviewing outputs. Do not
replace a blocked force-field assignment with invented charges or constants.

All job files are under the active vault's workspace/simulations/owner/job tree.
They are included by a full vault backup when paired consistently with the DB.
Quiesce workers before copying; preserve completed stage files for resume.
See [backup and restore](backup-restore.md), [recovery](recovery.md), and the
[usage guide](../usage/simulations-and-calculations.md).
