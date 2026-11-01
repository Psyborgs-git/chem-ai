# Workers, scientific engines and model runtimes

Scientific work crosses several execution lanes. Match the new capability to its existing lane before adding another runner. Each lane needs real readiness probes, typed inputs/outputs, bounded resources, durable provenance and a clear statement of what the result means.

## Choose the owning lane

| Lane | Implementation |
| --- | --- |
| General run admission/execution | `studio/domain/runs/` plus `workers/common/` |
| Task agent turns | `studio/application/agent_tools/` and inference runtime |
| Private app-wide Agent | `studio/domain/agent_workspace/` |
| Private learning | `studio/domain/learning/workspace_runtime/` and `workers/training/workspace_worker.py` |
| Polymer simulation | `studio/domain/simulations/` and `workers/simulation/radonpy_worker.py` |
| Chemistry/optimization adapters | `packages/engine-adapters/`, corresponding `workers/chemistry/` or `workers/optimization/` |

The private learning workspace and older reviewed training/model-release services are separate workflows. Preserve their distinct owner scope, job records and human promotion gates.

## Keep optional dependencies isolated

The API's core environment must start without RDKit, GPU libraries, a model or a simulation runtime. Keep optional imports lazy and install heavy dependencies in the declared extra, pinned image or isolated interpreter environment.

For private learning, a backend-specific interpreter override takes precedence over `STUDIO_TRAINING_PYTHON`, then automatic discovery. Known isolated directories include `.runtime/learning-mlx`, `.runtime/learning-science`, `.runtime/learning-transformers` and `.runtime/learning-reinvent`. Simulation uses `.runtime/simulation-radonpy` or `STUDIO_SIMULATION_PYTHON`.

Probe the actual interpreter, dependencies, versions and usable device. An importable MLX package without Metal access is not a ready MLX runtime. A registered model directory without compatible verified files is not a ready model. Do not replace missing native results with fixtures.

Use the checked-in per-runtime requirements locks and image definitions. Changes to runtime packages must update the actual lock/image, compatibility probe, documentation and focused engine tests together.

## Implement an adapter contract

Use the nearest adapter's typed contract, fixed method/version identity and safe error conventions. Validate structures, charge, multiplicity, unit/basis, source rights and other required parameters before launching expensive work. Fail with `ENGINE_UNAVAILABLE` or the appropriate unsupported-input/nonconvergence error when prerequisites are not met.

Record input checksums, method/version, actual executable/image, parameters, resource envelope, execution profile, timestamps, outputs and interpretation limits. A successful process exit is not numerical convergence, and convergence is not experimental validation.

Preserve scientific distinctions. Analytical similarity is scoped to method/x-unit/range and is not composition/identity evidence. Property applicability is not calibrated uncertainty. A generated molecule or a force-field simulation is not a measured material property.

## Use the actual isolation profile

`workers/common/executor.py` defines container and subprocess execution backends. The restricted container profile uses no network, a read-only root filesystem, non-root execution, bounded resources and scratch-only writes. Missing images leave that lane unavailable.

The reduced development subprocess profile scrubs environment, redirects HOME/TMPDIR into scratch, uses process groups and supported POSIX limits. It does not enforce OS-level network denial. A run requiring a control that the backend cannot enforce must be blocked, not quietly downgraded.

Profiles in `infra/local/worker-profiles/` declare those limits. Record controls actually enforced on the current platform. Never claim container isolation for a local subprocess.

## Bound subprocess and job lifecycle

Use allowlisted argument arrays, private per-job scratch, validated member names and explicit wall/CPU/memory/output/file/process bounds. Do not use shell interpolation for user content. Avoid inheriting provider keys, session tokens, proxy variables or arbitrary environment values into training/science processes.

Cancellation and timeout must stop the whole process group or container and wait for termination confirmation. Persist the requested stop separately from confirmed termination. Worker leases/watchdogs must stop or recover orphan work when the backend disappears.

Resume only from supported persisted checkpoints. Keep cumulative wall-time/budget accounting across attempts. An MLX warm start has fresh optimizer state; an interrupted simulation stage restarts from its last completed stage. Describe those limits explicitly.

Preserve completed artifacts on a cancelled/failed job. Verify checksums and artifact path boundaries on both local and remote transfer. Storage checks should prevent new work or stop safely rather than deleting retained user artifacts.

## Extend private learning

Add a track to the service's validation, capability/preflight report, runtime execution, model compatibility, result registration, UI selection and independent evaluation together. Preflight and job creation must apply the same admission rules.

Dataset imports preserve data kind, rights, provenance, rejected rows and grouping. Training must not consume held-out final examples. Evaluate base and candidate against the same final prompts/labels without exposing expected answers to generation requests. Keep exact model, dataset and evaluation identity bound to activation.

Tool-using assistant datasets must preserve complete calls/results and validate the protocol. Property fits retain one property/unit/method/condition scope. Do not silently coerce structure-only rows into labelled data or mix incompatible measurement contexts.

Catalog download jobs pin immutable revisions and hashes, retain licenses, and run remote code disabled. Native workers receive first-party source paths without importing API site-packages into isolated runtimes.

## Use a self-hosted learning worker

The worker host installs the repository plus compatible optional dependencies and connects outward to the authorized API. A documented worker command is:

```sh
python -m workers.training.workspace_worker \
  --api https://studio.example \
  --backends transformers,chemprop \
  --work-dir /private/training
```

`studio.example` is a synthetic deployment placeholder, not a provisioned remote service. The default Studio deployment is loopback-only; remote access requires its own correctly secured authorized deployment.

Provision `STUDIO_WORKER_TOKEN` through that host's secret management. Do not put it on a command line or into a trainer environment. Jobs choose `config.executionTarget="remote"`. Imported models need an explicit worker-local `--model MODEL_ID=/local/model/path` mapping; server model paths are not transferred.

Preserve owner authentication, lease/job binding, heartbeat, cancellation, bounded ZIP extraction and 256 MiB transfer limits. Worker loss expires its lease after two minutes. See [Learning workspace operations](../operations/learning-workspace.md) for the full protocol.

## Extend research workflows and simulations

Campaign resources are linked and owner-private. Tool access is constrained to the workflow's allowed/linked sources, pages, datasets, models and jobs. Keep compute/inference ledgers and free-space reservations across retries. Agent tools cannot increase the saved campaign's limits.

Polymer simulation requires actual chain construction, force-field/charge assignment, method/protocol checks, two independent seeds and raw artifact retention. Do not make a short pilot eligible for training labels by omitting a convergence flag. See [Polymer simulation operations](../operations/polymer-simulation.md).

## Add or change an agent tool

Use the schema-described closed registry belonging to the task or private Agent lane. Validate tool names, arguments, current principal, owner/task/workflow scope, source rights and returned identifiers. Treat tool text and prior conversation as untrusted data.

Do not expose arbitrary shell, raw GraphQL, credential settings, human scientific approval, model activation or task closure as tools. Bounded model/tool attempts, safe errors and cancellation/checkpoint behavior belong in the same change.

## Validate with real and unavailable cases

Unit-test parsing/validation/limits separately from optional engine execution. Integration-test owner/lease boundaries, deduplication, concurrent heavy-job admission, timeout, cancellation, artifact transfer and restart/resume. Include missing executable/image, unsupported version, unavailable device and nonconvergence.

Run a small real engine case when prerequisites exist, and retain actual outputs and method provenance. Report optional hardware/runtime tests as unavailable when they cannot run; fixture scoring proves software contracts, not scientific quality. See [Testing and documentation](testing-and-docs.md).
