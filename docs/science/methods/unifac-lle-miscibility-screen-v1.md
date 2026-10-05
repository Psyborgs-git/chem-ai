# Method record: `unifac-lle-miscibility-screen/v1`

Status: versioned (v1), CS-0702. This is the single method the materials
adapter exposes; anything outside this record fails closed.

## What it computes (specified endpoint)

**Endpoint:** `equilibrium_miscibility` — for a binary liquid mixture,
whether the two components are fully miscible or phase-separate at a
stated temperature, and (when they separate) the grid-resolution-limited
composition interval of the miscibility gap expressed in mole fraction
of component 0.

The output is a **computed equilibrium proxy**: equilibrium phase
behavior of an idealized binary at rest. It answers "do these two
pure-component liquids share one phase at equilibrium at T?". It does
**not** answer anything about a formulated product.

## Why this method was chosen (justification, §16.3)

The endpoint — equilibrium liquid–liquid miscibility of small molecules —
is what a formulator actually needs before deciding whether a co-solvent
pair can split in storage. The candidate space was:

- **Original UNIFAC (VLE-fitted, Dortmund-style `LUFSG`/`UFIP` tables):**
  predicts activity coefficients fitted to vapor–liquid equilibria. On
  water + 1-butanol at 298.15 K it predicts *complete miscibility* — a
  qualitatively wrong answer for a documented LLE system. Rejected.
- **UNIFAC-LLE (`LLEUFSG`/`LLEUFIP`, Magnussen/Rasmussen/Fredenslund
  1981):** interaction parameters regressed specifically on liquid–liquid
  equilibrium data — the parameterization matches the endpoint. On the
  same system it predicts a phase split with bounds near the documented
  binodal ([0.5, 0.98] in x_water). **Chosen.**
- **LAMMPS molecular dynamics:** defensible for some thermo endpoints but
  requires a force field per component and vastly more budget; choosing
  it here would have meant shipping guessed parameters — prohibited.

Engine: `thermo` 0.6.1 (MIT), pinned in the worker image
`chem-studio-materials:0.6.1-v1` with its full transitive lock
(`workers/chemistry/materials/requirements.lock`).

## Required parameters (input contract)

Per component (exactly two):

- `name` — display label only; carries no chemistry.
- `unifac_groups` — the **complete** UNIFAC-LLE subgroup decomposition:
  `{subgroup_id: count}` with subgroup ids from the shipped LLEUFSG
  table (57 subgroups / 32 main groups). This decomposition IS the
  model's parameter set. A component that cannot be expressed in these
  subgroups — a polymer distribution, a salt, an unknown purchased
  composition — is rejected (`unsupported_input` / blocked
  `insufficient_inputs`), never approximated by a surrogate.

Job-level:

- `conditions.temperature_k` — the evaluation temperature.
- `conditions.nominal_x1` — optional: the caller's nominal mole fraction
  of component 0; used only to mark which side of the gap a recipe sits
  on. The screen always covers the whole composition range.
- `grid_points` — composition-grid resolution (default 801, allowed
  101–4001).
- `resources` — bounded envelope (wall ≤600 s, memory ≤4096 MiB,
  cores ≤4).

**Interaction-parameter coverage is itself a required parameter.** Every
directional main-group pair the evaluation touches must exist in the
shipped LLEUFIP table. thermo *silently zero-fills* missing pairs; the
adapter instead checks coverage host-side (embedded copy of the
published table) and again container-side against the live table, and
raises `MISSING_PARAMETERS`. Missing information is a blocked
capability — never an invented default (AT-0702-1).

## Valid domain

- Binary condensed-liquid mixtures expressible in LLEUFSG subgroups.
- Ambient pressure (the model carries no P-dependence).
- Temperature **278.15–333.15 K** — the band the LLE parameter table was
  regressed on (~5–60 °C). Outside it the request is rejected; the
  method does not extrapolate.
- Not valid for: polymers/oligomer distributions, salts and
  electrolytes, supercritical or near-critical systems, gas-phase
  behavior, ternary+ mixtures, anything requiring kinetics.

## Numerical procedure (sampling/convergence)

For each grid point x over (0, 1): `UNIFAC.from_subgroups` →
`gammas()` → `g_mix(x)/RT = Σ_i x_i ln(x_i γ_i)`. Phase split iff
`g_mix` rises above its **lower convex hull**; miscibility-gap bounds
are the hull contact points. Deterministic — there is no iterative
solver to converge; precision is limited by grid spacing, which is
reported in the manifest (`sampling.gap_bounds_resolution`).

## Model context carried in every result manifest

`model_context` records: model name and parameter table + engine
version; assumptions (isothermal-isobaric liquid, vapor ignored,
temperature-independent a_mn coefficients, exact group decompositions,
equilibrium criterion); boundary conditions (closed binary, at most two
coexisting liquid phases); ensemble (`isothermal_isobaric_two_liquid`);
sampling (uniform grid + hull); convergence (deterministic, grid-limited);
calibration (none — published parameters as shipped, not fitted to task
data).

## What this method does NOT establish (structural, §16.3)

`does_not_establish`: `storage_stability`, `emulsion_stability`,
`kinetic_stability`, `product_performance`. Equilibrium miscibility at
rest does not measure demixing kinetics, droplet coalescence,
surfactant action, oxidation, or shelf life. `MaterialsOutcome` carries
`supports_endpoints` / `does_not_establish` /
`evidence_class="computed_equilibrium_proxy"` as manifest fields, and
`MaterialsService.assess_endpoint` returns a typed
`not_established` verdict for out-of-scope endpoints — the separation
is in the schema, not in a warning sentence (AT-0702-2).

## Benchmark and evidence class

Approved benchmark = documented qualitative LLE behavior, asserted by
the engine test suite:

| System (298.15 K) | Documented behavior | Asserted result |
|---|---|---|
| water + 1-butanol | phase split, binodal ≈ [0.50, 0.98] in x_water | `phase_separated`, gap within regression bounds |
| water + ethanol | fully miscible | `homogeneous` |
| water + methanol | fully miscible | `homogeneous` |
| benzene + n-hexane | fully miscible (similar nonpolar) | `homogeneous` |

This is a **regression lock on documented behavior**, not an
experimental fit and not scientific validation of predictions for new
systems — every outcome is stamped `scientific_status="not_validated"`,
`classification="reference_integration"`. Fixture-only examples are
labeled `fixture_only` in `tests/fixtures/synthetic/materials-lle.json`.

## Limitations

- Group-contribution accuracy only; cannot express chirality, isomers
  beyond the subgroup table, hydrogen-bonding detail, or ions.
- Misses any system needing a subgroup or pair the 1981 table lacks.
- Binary only; real formulations are multicomponent.
- Says nothing about *how fast* phases separate or whether they stay
  separated in a real product.

## Versioning

`v1` = this record + `chem-studio-materials:0.6.1-v1` +
`materials-adapter/v1` + schema `materials_lle_job/v1`. Any change to
method, parameter table, or criterion bumps the method version and the
image tag together.
