# BayBE adapter v1 (CS-0603)

BayBE **0.15.0**, Apache-2.0. `requirements.lock` under `workers/optimization`
pins the tested CPU runtime; core never imports BayBE, pandas, or torch.

Supported mappings:

| Studio definition | BayBE 0.15.0 API |
| --- | --- |
| Continuous numerical bounds | `NumericalContinuousParameter` |
| Explicit numerical values | `NumericalDiscreteParameter(tolerance=0)` |
| Explicit categorical membership | `CategoricalParameter(encoding="OHE")` |
| Maximize/minimize | modern `NumericalTarget(minimize=...)` + `SingleTargetObjective` |
| Match with reviewed cutoffs | `NumericalTarget.match_triangular` |
| Pointwise continuous linear constraints | `ContinuousLinearConstraint(interpoint=False)` |
| Discrete linear constraints/mixtures | bounded exact decimal enumeration → `SearchSpace.from_dataframe` |
| Continuous as-supplied mass mixtures | explicit linear total equality, independently rechecked |
| Cold start | `RandomRecommender`, explicitly recorded, no invented acquisition/uncertainty |
| After declared measurement count | `TwoPhaseMetaRecommender` → `BotorchRecommender(qLogNoisyExpectedImprovement)` |

Hybrid spaces (even unconstrained), cardinality, interpoint/batch constraints,
multi-target objectives, active-solids/molar/volume mixtures, custom descriptors,
and unknown fields fail closed. No reviewed reparameterization is supplied.
Arbitrary contract-level hard constraints also block campaign creation until a
reviewed mapping exists; the adapter never ignores them.

Independent checks use decimals, exact discrete membership and continuous
absolute distance `1e-6` in declared units for identity. Linear equalities/mixture
totals use absolute tolerance `1e-6`; **no renormalization** occurs. All pending,
observed, cancelled and failed identities remain reserved for that campaign.
Replicates/corrections need an explicit future representation/new version.

Replay is validated JSON: definition digest, seed, request index, pinned software,
recommender config, terminal outcomes with measurement/snapshot hashes, and request
history. Each request reconstructs the campaign and seeds it with `(seed + index)
mod 2^32`. BayBE's `to_json`/`from_json` are deliberately unused: 0.15.0 embeds
pickled dataframes. Replay guarantees are limited to the pinned runtime/hardware,
not cross-platform bitwise scientific reproducibility.

Production execution:

```sh
docker build -f workers/optimization/Dockerfile -t chem-studio-baybe:0.15.0-v1 .
STUDIO_PROFILE_OPTIMIZATION=1 uv run uvicorn studio.api.app:create_app --factory --host 127.0.0.1 --port 8787
uv run --group dev pytest services/studio-api/tests/engines/test_baybe.py -v --timeout 300
```

Build downloads software only; runtime has `--network none`, read-only root,
non-root user, fixed CPU-thread counts, bounded memory/processes/batch/output and
120s timeout. No insecure native production fallback. Engine tests skip explicitly
if the image is absent. Suggestions do not approve or execute an experiment.

Create a campaign through `optimization.create` with a frozen, active task contract
and the reviewed definition. UI accepts JSON (synthetic example:
`fixtures/synthetic/optimization-campaign.json`, **not scientific evidence**).
Targets must match contract metric/method/unit and threshold direction (`gte`→max,
`lte`→min, `between`→matching cutoffs, `eq`→matching cutoff midpoint). Only humans with `review_science`
and `manage_models` can freeze definitions or record lifecycle decisions.

Linking an observation requires an accepted, human-reviewed, applicable numeric
measurement in a frozen task `property_prediction` snapshot with allowed/owned
training rights and no source drift. The reviewed measurement's
`conditions.actual.optimization` must contain `campaignId`, `experimentId`,
`parameters`, and the exact immutable `context`. Missing/censored/failure labels
are not zero; real reviewed zero is valid. Every later request rechecks source
hashes and blocks on corrections/revocations instead of silently refitting.
