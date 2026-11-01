# Calculations and polymer simulations

Calculations and simulations create traceable computational records. They keep their inputs, method, runtime and limitations separate from experimental measurements. Start with a small bounded run and inspect readiness before requesting optional scientific work.

New to structures and SMILES? Begin with [Chemistry basics](chemistry-basics.md) and [A guided first research exercise](guided-first-research.md).

## Explore a molecule from Home

On Home, select **Explore molecule**, then enter a SMILES string in **Molecular structure**. **Try ethanol** supplies `CCO`. Choose **Calculate properties**, then **Open full result** to inspect the saved run.

A working RDKit calculation for ethanol reports formula `C2H6O`, molecular weight about `46.069`, one hydrogen-bond donor, one acceptor and three heavy atoms. These are descriptors of the supplied structure. They are not laboratory observations or proof that a sample has that identity.

When RDKit is unavailable, the interface displays the engine detail and **Check again**. Invalid structures produce a failed run rather than plausible substitute values. If a response cannot be confirmed, retrying the unchanged input checks the same idempotent request instead of launching an accidental duplicate.

## Calculate inside a task

Open **Experiments → Calculations** and **Describe a molecule**. Enter **SMILES structure** or choose **Use ethanol example**, then **Calculate properties**. The saved result retains its engine version, method, input and timing. **Open saved result** opens `/runs/:runId`; **Tools → Run history** shows task runs.

Inputs are immutable checksum-verified artifacts. The descriptor request is bounded to 60 seconds with one attempt and resource admission. Closed/cancelled tasks retain existing results but reject new calculations. Draft criteria do not prevent exploratory calculations.

## Inspect Compute and fallback

Open **More → Compute** for capability and admission state. Profiles, image availability, measured resources and required dimensions determine whether work can run. A queued/requested state is not a completion state.

A fallback review records infeasibility and possible authorized alternatives for a particular run. Missing hardware or a profile prerequisite is reported explicitly. The app does not silently substitute an easier engine and report the requested calculation as successful.

Run cancellation requests and confirmed termination are separate states. Inspect the terminal status and artifacts after a stop request. Do not assume a process tree has stopped merely because the cancel request was acknowledged.

## Optional scientific lanes

| Lane | Purpose and limits |
| --- | --- |
| Quantum | Typed QCEngine/xtb templates with explicit structure/parameters and profile/image checks |
| Materials | Declared thermodynamic methods such as scoped UNIFAC-LLE screening |
| Molecular design | REINVENT proposals from configured compatible/licensed assets |
| Retrosynthesis | AiZynthFinder planning with real configured model/stock prerequisites |
| Reference analysis | Analytical ingest/comparison with scoped similarity, not identity or recipe recovery |
| Optimization | BayBE recommendations bound to contract targets and independently checked constraints |

Some lanes are integration/API/agent capabilities rather than a general-purpose form on every screen. **Tools → Optimization** and **Tools → Reference analysis** appear when the task has those objects. Missing structures, force-field parameters, weights, stock or profiles remain blockers. See [Scientific operations](../operations/scientific.md) and [Model operations](../operations/model-ops.md) for activation and evidence limits.

## Define and run an optimization campaign

Open **Tools → Optimization** on a task that carries the optimization surface. Under **Define the approved search space**, enter parameters with their units and continuous bounds, discrete values or categories. Record the target metric/unit, reviewed method, context, linear constraints and reproducibility seed. The target must match the intended frozen contract metric.

**Advanced: exact campaign definition** accepts the supported exact payload, including mixture totals and additional configuration; it replaces the structured definition. Server validation applies in either form. **Freeze campaign definition** saves the immutable definition used by the campaign.

Set **Recommendation batch (1-16)** and choose **Request suggestions**. The pinned BayBE engine/profile must be ready. Suggestions reserve experiment identities; they do not start laboratory work or approve a plan.

Use **Reviewed measurement Relay ID** when choosing **Link reviewed observation** for a suggestion, or **Cancel suggestion** / **Record failure** with the actual reason. **Frozen property dataset Relay ID** refers to the declared property snapshot, not an arbitrary private-learning dataset ID. Each campaign command checks current revision/idempotency and records its actual state.

Independent constraint checks still apply to proposed candidates. Do not accept an invalid suggestion merely because an optimizer produced it. Feed real reviewed observations through the supported workflow and preserve method/unit/context compatibility.

## Compare analytical reference series

Open **Tools → Reference analysis** on an applicable task. Enter the committed **Raw export artifact id (uuid)** plus the actual series label, X/Y units, sample label/preparation and instrument context. **Ingest spec JSON** provides the exact advanced form when required. Select **Ingest series**.

Supported analytical parsing includes selected JCAMP-DX ASCII tables and two-column CSV-style X/Y exports. Unsupported encodings/formats retain provenance and report unsupported interpretation. The app does not guess a spectrum from an unparseable file.

Choose **Left series**, **Right series**, **Algorithm** and optional X-range bounds, then **Compute scoped similarity**. Read the applied method/version/range and interpretation limits with the number. Different methods or incompatible X units are rejected. Similarity is not evidence that two samples share molecular identity, composition or recipe.

## Request a polymer simulation

The private simulation workspace supports actual bounded amorphous all-atom polymer pilots through authorized research tools and `/api/simulations`. It does not currently have a standalone primary-navigation simulation page. Use a research workflow or authenticated integration and inspect the persisted job/events/artifacts.

Inputs include repeat-unit PSMILES, explicit head and tail end caps, repeat count, chain count, two distinct seeds and bounded wall time. A PET control is documented in [Polymer simulation operations](../operations/polymer-simulation.md). The first and second attachment atoms in the submitted repeat orientation determine head/tail meaning. Canonicalization does not silently swap end caps.

The worker checks complete hydrogenated chains, cell size, assigned GAFF2 interactions and finite Gasteiger charges before integration. A failed assignment blocks the run; zero charges or an alternative force field are not substituted.

## Understand the simulation protocol

The implemented pilot uses RadonPy packing, a Larsen 21-step compression/decompression schedule, and NPT sampling at 300 K and 1 atm. The short pilot scales preparation steps; the default sampling length of 50,000 steps at 1 fs represents 50 ps per seed.

Numeric stability and convergence are different recorded results. A shortened pilot is always ineligible as a training label. Eligibility also requires the full unscaled protocol, at least 5 ns final sampling, successful checks and both seeds. Software eligibility is not automatic scientific approval.

Repeat-unit/amorphous-cell properties cannot determine yarn orientation, fiber cross-section, weave, finishing, tactile hand, drape or fabric lustre. Investigating those endpoints requires separate measured textile work. Do not translate a small stable trajectory into a silk-equivalence claim.

## Resume and retrieve artifacts

Only the owner can read, cancel/resume or download a private simulation job. Jobs persist attempts, events, input digest, cumulative elapsed time and results. Training and simulation share heavy-work admission. Campaign limits apply across retries/resumes.

Outputs include LAMMPS inputs, force-field reports, raw thermo logs, trajectories, restarts, stage/molecule checkpoints and analysis files. Cancellation/timeout stops the process group. Resumption reuses completed seeds/stages; an interrupted stage starts again from the last completed stage, not a claimed bit-exact binary restart.

An API lease watchdog stops orphan workers after a backend crash. Storage exhaustion blocks or stops work without deleting old artifacts. Preserve raw logs and source conditions alongside summary values when reviewing a result.

See [Learning and models](learning-and-models.md) before using any computational data for fitting, and [Workers and engines](../development/workers-and-engines.md) when implementing a new calculation lane.
