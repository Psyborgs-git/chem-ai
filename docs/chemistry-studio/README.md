# Chemistry Studio — implementation handoff package v1.0.1

Prepared 5 October 2026. This is a detailed implementation specification and agent kickoff, not a delivered application or a scientific validation claim.

## Start here

**This is the handoff package's README, not the application's repository README.** In v1.0.1, it is at the top level of the ZIP beside `CHEMISTRY_STUDIO_KICKOFF.md` and `CHEMISTRY_STUDIO_HANDOFF.md`.

Extract **all** ZIP contents into a dedicated folder, preferably `docs/chemistry-studio/` inside the authorized implementation repository. Do not extract the pack over the repository root and overwrite an existing application README. All source-pack paths in the kickoff are relative to this dedicated folder.

The original v1 ZIP also contains this README, but under `chemistry_studio_handoff/README.md`. Its individually linked Word/Markdown downloads were not the full package. The three main Markdown documents alone omit required planning registers, contracts, fixtures, and validation files; do not silently reconstruct those inputs from prose.

If the agent already began implementation, preserve its work and reconcile the source-pack update instead of restarting. This v1.0.1 patch changes packaging and entry-point instructions only; it does not change product scope, implementation tickets, contracts, or acceptance cases.

Give the coding agent **the whole package** and the contents of `CHEMISTRY_STUDIO_KICKOFF.md`. It should audit the real working directory and begin `CS-0001`, then follow the ticket dependency graph. No repository, hardware, model, cloud account, or laboratory configuration is assumed.

For a human reader, start with the Word reading copy or `CHEMISTRY_STUDIO_HANDOFF.md`. Read `WORK_PACKAGES.md` for the implementation-level ticket details. The Markdown and JSON remain canonical; regenerate the Word copy after substantive edits.

## Included

- `CHEMISTRY_STUDIO_HANDOFF.md`: full 30-section architecture, data model, invariants, APIs, engine integration, learning, privacy, security, UX, execution and release specification.
- `CHEMISTRY_STUDIO_KICKOFF.md`: paste-ready controller instructions.
- `WORK_PACKAGES.md`: 52 tickets across 12 phases, with dependencies, owner, allowed write scope, steps and acceptance cases.
- `planning/`: locked decisions, engineering defaults, unresolved inputs, integrations, official sources, requirement traceability, execution graph, 156 acceptance cases, and a logical map of 23 screens / 30 atomic components.
- `contracts/`: strict initial JSON Schema DTOs and schemas for execution, design and tests. Domain invariants supplement structural schemas.
- `fixtures/`: 13 valid and 7 intentionally invalid synthetic examples. These are not real formulations or executable scientific procedures.
- `scripts/validate_pack.py`: offline specification consistency validator, with a generated report in `planning/pack-validation-report.json`.
- `manifest.sha256.json`: packaged-file checksums, excluding the manifest itself.

## Validate the specification

Run from the extracted package root using Python 3.10 or later:

```sh
python -m venv .venv-validation
# Linux/macOS:
. .venv-validation/bin/activate
# Windows PowerShell instead:
# .venv-validation\Scripts\Activate.ps1
python -m pip install -r requirements-validation.txt
python scripts/validate_pack.py --report planning/pack-validation-report.json
```

Installing the validator dependency may use the network; running the validator itself does not. Use an approved local package mirror/wheelhouse where required. The application agent must separately verify/pin the versions used for its own environments.

The validator checks schema validity, identifier uniqueness, cross-references, ticket graph cycles, phase membership, and selected semantic fixture constraints. A passing result proves only the stated specification checks. It does not test the future API/UI/database, guarantee complete scientific schemas, execute a chemistry engine, train a model, authorize an export, or prove laboratory results.

## Canonical placement in an implementation repository

Preserve the source pack in `docs/chemistry-studio/` or a documented equivalent. App paths in the handoff are proposed; audit before mapping them to actual code. Nominate a single canonical location for implemented schemas, with generated/checksummed mirrors if needed. Keep every changed contract and its fixtures/tests synchronized.

Maintain execution evidence separately under `docs/execution/`. Do not overwrite the original evidence status to make the package appear already implemented. Screens have no Figma IDs or actual code paths because neither has been created or inspected for this project.

## Unknowns and release boundaries

The 16 unresolved-input entries remain unknown. They block only the relevant live training, experiment, deployment or cloud action. Core recordkeeping and deterministic software tests can proceed with synthetic fixtures. The first useful release covers the end-to-end pilot workflow through P05; later phases remain required roadmap work unless explicitly deferred by the owner. Every real experiment and cloud transfer retains its own approval requirements.
