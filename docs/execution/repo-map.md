# Repository map — proposed paths to actual paths

Handoff §4.4 layout is adopted unchanged. This file is updated whenever
an actual path diverges from the proposed one.

| Proposed (handoff §4.4) | Actual | Status |
|---|---|---|
| `apps/studio-web/src/` | same | created CS-0002/CS-0104 |
| `services/studio-api/src/studio/` | same | created CS-0002/CS-0101 |
| `workers/` | same | created CS-0002 (profiles only; workers later) |
| `packages/contracts/` | same | created CS-0101 (canonical schemas copied from `docs/chemistry-studio/contracts/` via checksum, not manual divergence) |
| `packages/engine-adapters/` | same | placeholder CS-0002; adapters from P04+ |
| `packages/policy/` | same | created CS-0102 |
| `migrations/` | `services/studio-api/migrations/` | **deviation**: Alembic env lives beside the API package that owns it; still single migration authority |
| `infra/local/` `infra/ci/` `infra/cloud/` | same | `infra/local`+`infra/ci` CS-0002/3; `infra/cloud` intentionally absent (disabled) |
| `fixtures/synthetic/` | same | created CS-0003; copies of pack fixtures + generator |
| `tests/` | `services/studio-api/tests/` + `apps/studio-web/tests/` + root `tests/e2e/` | **deviation**: suites live beside their toolchain; root `tests/` reserved for cross-cutting e2e |
| `docs/execution/` | same | created CS-0001 |
| `docs/dependencies.lock.md` | same | created CS-0002 |

Durable controller files at workspace root (per CS-0001 write scope):
`analysis.md`, `plan.md`, `tech-specs.md`, `tasks.md`.
