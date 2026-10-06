# Dependency and profile lock record

Recorded 2026-10-05. Machine-readable pins live in `uv.lock` and
`pnpm-lock.yaml`; this file records the *verified* choices, licenses,
platform notes and evidence links (handoff §30 source IDs in brackets).

## Reference environment

CI reference: Linux x86-64 (handoff §4.3). Development host this
session: macOS 13.7.8 x86_64 (4 CPU / 8 GiB) — differences recorded per
row below.

## Core profile (installed by `uv sync --group dev`, resolved 2026-10-05)

| Package | Locked | License | Purpose | Platform notes |
|---|---|---|---|---|
| Python | 3.12.13 | PSF | runtime | chosen over 3.14 for science-dep compat (E07); `requires-python >=3.12,<3.13` |
| fastapi | 0.142.2 | MIT | ASGI host | pure python, all OS |
| uvicorn[standard] | 0.54.0 | BSD-3 | ASGI server | uvloop wheels ok on macOS/Linux x86_64 |
| strawberry-graphql | 0.330.3 | MIT | GraphQL [S04] | Relay helpers verified against 0.330 API |
| pydantic | 2.13.5 | MIT | DTOs | v2 API only |
| sqlalchemy | 2.1.3 | MIT | ORM | 2.x style only |
| alembic | 1.20.0 | MIT | migrations | |
| psycopg[binary] | 3.3.6 | LGPL-3.0-only | PG driver (sync) | unmodified library use; binary wheel avoids local toolchain |
| procrastinate | 3.10.0 | MIT | PG-backed queue [S05] | used from P04; schema deferred until then |
| pint | 0.26.1 | BSD-3 | units (§6.1 whitelist) | requires ≥3.12 — matches core pin |
| jsonschema | 4.26.0 | MIT | contract checks | |
| python-multipart | 0.0.32 | Apache-2.0 | upload transport | transfer endpoints only |
| argon2-cffi | 25.1.0 | MIT | owner password hashing | argon2id default params |
| structlog | 26.1.0 | MIT/Apache-2.0 | redactable logs | |
| **dev** pytest | 9.1.1 | MIT | tests | |
| **dev** httpx | 0.28.1 | BSD-3 | API test transport | starlette TestClient warns → use `httpx2`/starlette client in tests (noted) |
| **dev** testcontainers[postgres] | 4.15.0 | Apache-2.0 | disposable PG for tests | requires Docker daemon |
| **dev** mypy | 2.4.0 | MIT | typecheck | strict mode |
| **dev** ruff | 0.16.10 | MIT | lint | |

## Optional profiles (resolved in `uv.lock`, NOT installed by default)

| Profile | Packages (locked) | License | Status on this host |
|---|---|---|---|
| `engines` | rdkit 2026.3.6 [S01/S02] | BSD-3 | **unavailable natively**: rdkit ships macOS arm64 + manylinux/win x86_64 wheels only — no macOS x86_64 wheel. Run under Docker `linux/amd64` or CI (Linux x86_64). Honest `unavailable` reported by capability probe (AT-0003-2). |
| `local_ai` | llama-cpp-python 0.3.36 [S21] | MIT | installable; live use blocked on U08 (no GPU, 8 GiB RAM) and U13 (no licensed model selected). Bootstrap never downloads models. |
| `optimization` | baybe 0.15.0 [S09], chemprop 2.3.1 [S10] | Apache-2.0 / MIT | heavy (torch transitive); deferred to P06 |
| `quantum` | qcengine 0.51.0, qcelemental 0.51.2 [S06] | BSD-3 | xtb ships via conda-forge inside `chem-studio-qcengine:0.51.0-v1` (xtb 6.7.1 + xtb-python 22.1, CS-0701) — verified against the documented water/GFN2-xTB reference; psi4 not installed — probe reports `not_installed` |
| `materials` | thermo 0.6.1 (chemicals 1.5.2, fluids 1.3.1, scipy 1.18.1, pandas 3.0.6, numpy 2.5.3) | MIT | ships as pip wheels inside `chem-studio-materials:0.6.1-v1` (CS-0702) — UNIFAC-LLE miscibility screen verified against documented water+1-butanol / water+ethanol behavior; adapter fails closed on any other version |
| `training` | torch 2.14.1, peft 0.21.2 [S13], trl 1.14.1 [S14] | BSD-3 / Apache-2.0 / MIT | deferred to P08/P09; blocked on U08/U13/U14 |
| `design` | reinvent 4.8 (`git+https://github.com/MolecularAI/REINVENT4.git@80a8d21` = tag v4.8, dist reports 4.8.24), torch 2.12.0, rdkit 2026.3.6 [S22] | Apache-2.0 (code + prior) | ships inside `chem-studio-reinvent:4.8-v1` (CS-0903) — not on PyPI, pinned to the v4.8 commit; licensed prior `reinvent_pubchem.prior` (Zenodo 20701824, Apache-2.0, sha256 fe8cd167…9ef3) baked in at build time; container runs with `--network none` |
| `synthesis` | aizynthfinder 4.4.1, onnxruntime 1.30.0, rdkit 2023.9.6 | MIT (code) / CC-BY-4.0 (USPTO assets) / MIT (ZINC stock) | ships inside `chem-studio-aizynthfinder:4.4.1-v1` (CS-0903) — USPTO expansion+filter ONNX (Zenodo 7797465), templates (Zenodo 7341155), ZINC stock hdf5 (figshare 23086469) baked in with sha256-verified build gate; no host-side extras — heavy deps stay container-only |

## Frontend (pnpm workspace, resolved 2026-10-05)

| Package | Locked | License | Purpose |
|---|---|---|---|
| react / react-dom | 19.3.0 | MIT | UI |
| react-relay + relay-runtime | 21.0.1 | MIT | single server-state cache [S03] |
| relay-compiler | 21.0.1 | MIT | codegen/drift checks |
| vite | 8.3.2 | MIT | dev server/build |
| typescript | 7.0.2 | Apache-2.0 | typecheck |
| vitest | 5.0.3 | MIT | component tests |
| @vitejs/plugin-react | 6.1.1 | MIT | build |

## Infrastructure images

| Image | Tag | License | Note |
|---|---|---|---|
| postgres | 16.10-alpine | PostgreSQL License | dev/test only; loopback port 54329; `infra/local/compose.yaml` |

## Rights / license gates (AT-0002-2)

- No model weights, datasets, or licenses are accepted by bootstrap —
  `make bootstrap` installs only the packages above.
- Any future model/engine requiring license acceptance is added only
  after an authorized review records it here with source + date.
- psql driver note: psycopg3 is LGPL-3.0; used unmodified as a library.
  If static redistribution becomes relevant, re-review licensing.
