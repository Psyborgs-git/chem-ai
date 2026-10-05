# Chemprop engine adapter (CS-0604)

A narrow, versioned adapter over Chemprop 2.3.1 for molecular-property
regression. The adapter runs **only** inside the pinned, network-denied
worker image (`workers/optimization/property_models/chemprop/`); torch,
lightning and chemprop are never imported by the core profile.

## What it is

- `TrainSpec` → a directed message-passing (`mpnn-dmpnn`) regression
  **ensemble** trained on exactly the rows supplied. Splitting is the
  caller's job (`domain/learning/splits.py`); the engine never
  re-splits and held-out labels cannot enter the contract
  (`PredictRow` has no label field).
- `PredictSpec` → per-row ensemble predictions (member values + mean +
  variance). `model_digest` binds predictions to the exact artifact set
  and train spec; a mismatched or corrupted artifact is refused.
- `pretrained: false` on every result — a Chemprop fit is a different
  representation trained on the caller's data, **not** a pretrained
  predictor for the user's chemistry (§15.3).

## What it deliberately refuses

- Classification, multi-target, reaction/multicomponent models,
  hyperparameter search, pretrained-model loading — all outside the
  declared contract and rejected by validation (`extra="forbid"` +
  literal pins).
- Any output that fails independent checks: wrong row ids, non-finite
  values, wrong member counts (`validate_predictions`).

## Error contract

Errors surface as `{"error": <code>, "message": <msg>}` with exit 2 —
`ENGINE_UNAVAILABLE` (missing/wrong engine or artifact) or
`ENGINE_UNSUPPORTED_INPUT` (contract violations, unloadable artifacts).
Tracebacks and recipe data never leave the container.
