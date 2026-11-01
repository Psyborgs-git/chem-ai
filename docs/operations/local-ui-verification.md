# Local setup, UI redesign and RDKit verification

Verified locally on 29 October 2026 (Asia/Kolkata), starting from `c3e5880`.
The working checkout was tested separately from an older checkout, which was
preserved.

## Running the app

The development UI is at <http://127.0.0.1:5173> and the API is at
<http://127.0.0.1:8787/healthz>. PostgreSQL listens on loopback port 54329.
The first owner was created through the actual first-run form. Local login
details are in the ignored, owner-readable `.runtime/local-credentials.json`.

After dependencies are installed, `make dev` starts the database, waits for
readiness, applies migrations, and runs the API and UI. It retains the
installed native RDKit profile and stores the vault in ignored `.runtime/`.
It refuses to start over occupied API/UI ports. Ctrl-C stops its servers.

Qualified runtimes: Python 3.12.16, pnpm 10.18.3, native RDKit 2026.03.6,
Docker 29.9.2. The final browser verification uses Node 24.19.0 and Chromium
143.0.7499.4. The dependency lockfiles were retained.

## UI coverage and repairs

The light research-studio redesign covers setup/sign-in; home/projects;
registry identities, grades, products, formulation/process revisions and
candidates; research/imports/evidence/quality/analysis; manual lab workflows;
compute/runs/fallback/export review; decisions/closeout/reports; and existing
dataset/training/model/evaluation/optimization screens.

Shared navigation, typography, panels, form controls, tables, empty/loading/
error states, dark theme and mobile layouts were updated. Complex technical
payloads remain inspectable under Advanced disclosures. Scientific evidence
classes, version bindings, access checks and human approvals remain explicit.

Confirmed defects repaired:

- Correct draft/paused/active task transitions through the UI.
- Registry selections clear and reset their saved IDs with their labels.
- Task creation guards repeated submission while a save is pending.
- New measurements start blank, require explicit values/units, and preserve zero.
- Replication summaries update after recording changes.
- Explicit input IDs remain associated with their labels and descriptions.
- Mobile navigation is hidden from focus when closed, traps focus when open,
  closes with Escape, and restores the opener's focus.
- Long manual-execution warnings wrap; molecular descriptor values remain
  visible at 390px without page overflow.
- Theme preference persists and ignores invalid cookie values.
- Project titles resolve from the authoritative project node after creation,
  rather than an older cached project list.
- Mobile report grids shrink their tracks so scientific tables scroll inside
  their panels and retain their pinned identity columns.
- Direct Vite file URLs cannot expose ignored runtime data, credentials or
  vault blobs. Direct and raw requests receive HTTP 403; inert URL-import
  modules contain no private payload. Application source still loads normally.

The settled visual audit contains 45 captures: 35 desktop views, six mobile
views and four dark-theme views. Each waited for its route-specific content
and loading states. Findings: zero browser JavaScript errors, zero whole-page
overflow, and zero unsettled views. Additional interaction checks cover the
drawer and actual saved ethanol values on mobile. Four principal text/token
pairs were checked in each theme (eight checks); their contrast ratios range from 5.93:1
to 15.32:1. This is a targeted contrast check, not a claim of complete
accessibility certification.

Evidence: `.runtime/evidence/ui-audit/findings.json`,
`interaction-findings.json`, `contact-1.png` through `contact-5.png`,
and `.runtime/evidence/contrast-check.json`. Original UI captures are
`.runtime/evidence/before-*.png`.

## Actual local experiment

The project **Ethanol • Local validation** and its task were created through
the UI. The new task was started through closeout, then the calculation form
submitted `CCO` to the real installed RDKit adapter.

| Property | Observed result |
|---|---|
| Canonical SMILES | `CCO` |
| Formula | `C2H6O` |
| Molecular weight | `46.069 g/mol` |
| Hydrogen-bond donors / acceptors | `1 / 1` |
| Heavy atoms | `3` |
| InChIKey | `LFQSCWFLJHTTHZ-UHFFFAOYSA-N` |
| Engine / method | `rdkit 2026.03.6` / `rdkit-descriptors/v1` |

Reloading the result retained its input, descriptors and provenance. During
the final calculation the API health request returned successfully in 65ms.
The invalid-valence control `C(C)(C)(C)(C)(C)` produced a persisted
`SANITIZE_FAILED` result, including after reload, with no descriptor cards.
Both browser runs recorded zero JavaScript errors.

The API is `runs.describeStructure`, returning the existing Run type. It
stores an immutable checksum-verified input artifact, uses task-scoped
authorization and idempotency, executes in a threadpool with its own database
sessions, and persists one bounded attempt. Cancellation reaches the actual
worker; timeout, resource denial, engine error and interruption stay distinct.
Interrupted work releases reservations and does not retry automatically.
Closed/cancelled tasks reject new calculations and retain prior results.

These results are computed descriptor evidence. They do not replace a required
laboratory endpoint or establish a validated research outcome. Native macOS
execution records its actual restricted-subprocess controls; unsupported
isolation controls are reported as absent in the saved technical details.

Saved URLs, authoritative result payloads and screenshots are listed in
`.runtime/experiment.json` and `.runtime/evidence/ethanol-result*.png`.
Synthetic UI-audit records are separately named **Synthetic UI audit** and
were not used as the real calculation result.

## Reproducing validation

| Check | Final local result |
|---|---|
| Core backend unit tests | 389 passed |
| Contract and design-map tests | 29 passed |
| Backend integration suite | 444 passed |
| Authorization/security suite | 222 passed; 9 non-security cases deselected |
| Focused structure service and actual RDKit engine suite | 25 passed |
| Frontend component/editor tests | 70 passed |
| Development-server runtime/vault privacy | 3 passed |
| Complete production-build browser suite | 56 passed |
| Python and frontend type checks | Passed; mypy checked 232 source files |
| Lint, schema drift, Relay boundaries and contract mirrors | Passed |

The focused engine/service cases overlap the broader suites and are listed
separately to identify the actual-engine acceptance evidence. The complete
browser run passed all 56 cases against one fixed production build, including
fresh owner setup, the real engine, and improve/match/discover closeout flows.

```bash
export PATH="$PWD/.runtime/bin:$PATH"
export UV_CACHE_DIR="$PWD/.runtime/uv-cache"
export UV_PYTHON_INSTALL_DIR="$PWD/.runtime/python"
export UV_NO_SYNC=1
make verify-core
make typecheck
pnpm --filter studio-web test
pnpm --filter studio-web build
make test-integration
make test-security
.venv/bin/pytest services/studio-api/tests/engines/test_rdkit_adapter.py -m engine
.venv/bin/pytest services/studio-api/tests/integration/test_structure_runs.py -m integration
make test-e2e
make test-dev-server
```

Playwright can use its installed Chromium, or an explicit executable via
`STUDIO_BROWSER_EXECUTABLE_PATH`. The browser suite resets only the disposable
`studio_e2e` database; development data stays in `studio`. Its artifacts and
HTML report are under `test-results/` and `playwright-report/`.

Final check results are recorded in `.runtime/evidence/` log files and the
verification summary JSON. Optional model/GPU/cloud services were not enabled;
their screens were checked in their actual unavailable/empty states. The
production build succeeds and still reports a 500kB chunk-size advisory for
the main bundle; lazy feature loading reduces the initial bundle from about
1.06MB to about 626kB before compression.
