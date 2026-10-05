# Baseline audit — Chemistry Studio

Recorded 2026-10-05 (local), before implementation edits. This file is
execution evidence; the specification lives in `docs/chemistry-studio/`.

## Workspace state

- **Workspace root:** `/Users/jainamshah/Documents/GitHub/chem-ai`
- **Version control:** **none.** `git status` exits 128 (`not a git
  repository`). No branch, HEAD, remote, lockfile, or CI config exists.
  This is a **greenfield workspace**, not an existing repository.
- **Pre-existing files before extraction:**
  - `Chemistry_Studio_Implementation_Pack_v1.zip` (232,348 bytes) — the
    handoff package, untouched.
  - `docs/chemistry-studio/README.md` — the v1.0.1 package README,
    pre-staged. **Preserved**: it is newer than the v1.0.0 README inside
    the zip and was deliberately not overwritten.
  - `docs/.DS_Store`, `.DS_Store` — macOS metadata, untouched.
- **Dirty-worktree check (AT-0001-1):** no VCS means no tracked dirty
  state; the only user content present (the zip and the v1.0.1 README)
  is recorded above and remains byte-identical. The pack manifest was
  verified: 44/45 SHA-256 checks pass; the single "mismatch" is
  `README.md`, expected because the workspace holds the v1.0.1 patch
  README while the manifest records v1.0.0's.
- **Greenfield statement (AT-0001-2):** no application code, database,
  tests, or prior implementation exist. No test suite has been run or
  passed. Nothing here is claimed as working software.

## Runtime / hardware audit

| Item | Observed | Note |
|---|---|---|
| OS | macOS 13.7.8 (Darwin 22.6.0), x86_64 | Not the Linux CI reference; per-binary isolation support must be verified per tool. |
| CPU | 4 cores | Constrains heavy job concurrency. |
| RAM | 8 GiB | Constrains local model/training profiles. |
| Disk free | ~9.9 GiB on `/` | Tight; artifacts and DB volumes must be bounded. |
| GPU | none detected (integrated Intel) | `local_ai`/`training` profiles blocked until capability check proves otherwise. |
| Python | 3.14.7 (`/usr/local/bin/python3`) | Too new for several science deps; `uv` used to select per-profile interpreters (validator ran on 3.12.13). |
| uv | 0.11.14 | Dependency/environment manager. |
| Node | v24.19.0; npm; pnpm available | Frontend toolchain. |
| Docker | client+server 28.4.0, daemon running | PostgreSQL for dev/tests runs in a container. |
| make / git | GNU Make 3.81 / git installed | No repo initialized (see above). |
| PostgreSQL | not installed on host | Docker `postgres` image used for dev/tests; recorded in `docs/dependencies.lock.md`. |

## Specification pack validation (AT-0001-3)

Command (run from `docs/chemistry-studio/`, isolated venv
`.venv-validation`, Python 3.12.13, `jsonschema` per
`requirements-validation.txt`):

```
uv pip install --python .venv-validation/bin/python -r requirements-validation.txt
.venv-validation/bin/python scripts/validate_pack.py --report planning/pack-validation-report.json
```

Exit status: **0**. Output:

```
Specification validation: PASS; 52 tickets; 156 acceptance cases; 20/20 fixture expectations matched.
Specification consistency only; no application tests, chemistry engines, training jobs or laboratory experiments executed.
```

This is specification-consistency evidence only — not application
evidence.

## Component classification

| Component | Status | Action |
|---|---|---|
| Handoff package `docs/chemistry-studio/` | existing | preserve; extracted in full this session |
| Application code | absent | new (tickets CS-0101+) |
| Database / migrations | absent | new (CS-0101) |
| Artifact vault | absent | new (CS-0103) |
| GraphQL API / Relay UI | absent | new (CS-0104, CS-0205+) |
| CI | absent | new (CS-0003) |
| Engines (RDKit, BayBE, QCEngine…) | absent | deferred to P04/P06/P07 |
| Local model runtime / training | absent | blocked on U08/U13 until profile checks |
| Cloud export | absent | disabled by design (D08) |

## Path mapping (proposed → actual)

The handoff's proposed layout (§4.4) is adopted verbatim in this
greenfield workspace; see `docs/execution/repo-map.md`. One documented
deviation so far: durable files `analysis.md`, `plan.md`,
`tech-specs.md`, `tasks.md` live at the workspace root per the CS-0001
write scope, not under `docs/`.

## Existing-test status

No project tests exist to run before changes; this is stated here so the
absence is not later misread as a pass.
