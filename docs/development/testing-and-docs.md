# Testing and documentation

Verify the behavior changed, then run the appropriate repository gates. Keep optional runtime, real-provider, physical-laboratory and native-launch evidence separate from deterministic unit/fixture results. A skipped prerequisite is not a passing execution test.

## Prepare the test profile

The full unit, integration and browser suites exercise actual RDKit structure validators, dataset imports and calculation workflows. Install the locked engine extra, including its NumPy dependency, then retain that explicit profile for subsequent `uv run` commands:

```sh
uv sync --python 3.12 --group dev --extra engines --frozen
export UV_NO_SYNC=1
```

CI selects this profile for those three suites. Its type and contract jobs also check the core environment. A core app installation can still run without RDKit and reports unavailable calculations; installing the test profile does not install model weights or qualify a scientific result.

## Choose the verification layer

| Check | Command | What it establishes |
| --- | --- | --- |
| Python style | `make lint` | Ruff checks on first-party source |
| Python and web types | `make typecheck` | Strict mypy plus generated Relay/TypeScript compilation |
| Contract consistency | `make contracts-check` | Handoff/fixtures, GraphQL export, Relay boundary and JSON-schema mirror checks |
| Backend unit | `make test-unit` | Service unit cases without a database |
| Backend integration | `make test-integration` | PostgreSQL-backed service behavior with its test prerequisites |
| Authorization/security | `make test-security` | Capability, scope and hostile-input boundaries |
| Web unit | `pnpm test:web` | Frontend interactions, state and rendering |
| Production web build | `pnpm build:web` | Relay generation, TypeScript and bundled assets |
| Browser journeys | `make test-e2e` | Real API/browser workflows on the isolated e2e database |
| Dev web exposure | `make test-dev-server` | Denial of private runtime/vault/environment file URLs |
| Optional engines | `make test-engines` | Actual configured engine contracts; unavailable prerequisites fail explicitly |
| Native Rust | `pnpm test:desktop` | Native runtime/download boundary unit tests |
| Native launch | `pnpm smoke:desktop` | Actual Mac boot handoff and backend process ownership |
| Generated help/reference | `make docs-check` | Reference freshness and registered article/link/anchor validity |

`make verify-core` combines lint, contract and unit checks. `make eval-smoke` uses non-scientific fixture evaluation. `make train-smoke` needs the declared training/hardware prerequisites. Inspect the target and current tests before claiming a command covers a newly added feature.

## Run a focused test

For backend logic, target the actual owning test and marker. For example:

```sh
.venv/bin/python -m pytest services/studio-api/tests/unit/test_agent_tool_registry.py -q
```

For a frontend interaction:

```sh
pnpm relay
pnpm --filter studio-web exec vitest run src/features/tasks/TaskOverview.test.tsx
```

Prefer tests that distinguish the required behavior: a failed save must retain new edits, a stale revision must fail without overwriting, an uncertain retry must not launch another run, or an agent must be denied a human review action. A snapshot that merely repeats the implementation does not establish those properties.

After focused tests pass, run the relevant shared type/build/contract gates. Repeat broader suites only when changes, failures or unresolved concerns justify it. Do not report an unrelated historical run as evidence for the current working tree.

## Use disposable databases

Backend integration and browser tests create or target dedicated test state. The e2e setup uses `studio_e2e`, not the development `studio` database. Confirm `STUDIO_DATABASE_URL`, test fixture configuration and container targets before running any reset/migration exercise.

Migration tests should cover a fresh database plus existing records. Concurrency tests need the actual PostgreSQL transaction/locking behavior. Include cross-workspace and cross-owner identifiers instead of assuming a successful happy-path request proves scope isolation.

Never use real provider credentials, private notebook content or production scientific records in test fixtures or screenshots. Mock protocol endpoints can verify function-call/Responses behavior without establishing a hosted model's scientific quality.

## Browser and native verification

`tests/e2e/playwright.config.ts` starts the isolated API on port 8790 and a production preview on 4173. It retains traces/screenshots for failures. `STUDIO_BROWSER_EXECUTABLE_PATH` can select an installed browser executable; otherwise provision Playwright's required browser through the normal toolchain.

Exercise direct links, refresh/back, keyboard/focus behavior, loading, forbidden/unavailable state and the meaningful failed mutation. Check mobile width, light/dark theme and reduced motion when layout/animation changes.

For native work, run focused Rust/backend/frontend checks, rebuild, quit any app using the dedicated desktop port, then run `pnpm smoke:desktop`. The smoke intentionally checks owned-process cleanup and separately owned backend reuse. It does not create user research records or qualify public signing/notarization.

## Documentation sources and routes

Current manuals live under `docs/usage/`, `docs/development/` and `docs/operations/`. Generated exhaustive API/configuration/command reference lives under `docs/reference/`. The index for those generated pages is [Reference](../reference/README.md).

`docs/help-manifest.json` is the explicit article registry. It contains `version: 1` and an `articles` array. Every article entry has:

| Field | Meaning |
| --- | --- |
| `section` | `usage`, `development`, `operations` or `reference` |
| `slug` | Stable lowercase-dashed route identifier |
| `title` | Navigation and search title |
| `summary` | Short factual description of the article |
| `source` | Repository-relative Markdown path |
| `order` | Unique ordering value within its section |

An article's route is `/help/:section/:slug`. Keep published slugs stable. A source path can change only with the registry and incoming links updated together. Help is read-only and authenticated; it does not save notebook content or expose a new public API.

## Add or edit an article

1. Edit the canonical Markdown file, or create it in the appropriate manual directory.
2. Use exactly one H1 describing the page, followed by simple meaningful headings.
3. Add/update the manifest title, summary, source, stable slug and section order.
4. Link to other registered articles with relative Markdown paths. Use code spans for repository source paths that are not registered articles.
5. Update behavior-level examples from actual forms, commands and service contracts. Label synthetic examples and avoid real paths containing secrets, account identifiers or credential values.
6. Run article validation and inspect the rendered page, links, search result and headings in the app.

V1 handbook pages do not contain raw HTML or embedded images. Tables and fenced code are supported. Do not add remote image requests for screenshots or decorative assets. The notebook renderer remains a separate private-content boundary.

Heading IDs use lowercase text, strip characters other than letters/digits/underscores/whitespace/hyphens, and turn spaces into hyphens. Repeated headings receive `-1`, `-2` and later suffixes. Validate fragment links with the shared parser rather than assuming GitHub's punctuation behavior is identical.

Use a relative article link such as `[Agent and providers](../usage/agent-and-providers.md)` or a checked heading fragment. Avoid linking source `.py`/`.tsx` files as if Help could render them. Ordinary app routes and source paths can be shown in code spans when the reader should navigate or inspect them manually.

## Regenerate exhaustive reference

The reference exporter reads source/schema and reviewed metadata without starting the API, connecting to the database or resolving runtime secret values. It inventories REST handlers/contracts, GraphQL operations/types, commands and environment settings. Generated files are not hand-edited.

For API/schema/configuration changes, update the owning implementation and any reviewed reference metadata, then:

```sh
make docs-generate
make docs-check
```

For prose/article-only changes:

```sh
pnpm docs:check
```

`pnpm docs:check` checks article assets, registration and links; it does not replace exhaustive backend-reference freshness checks. `make docs-check` is the combined gate. The Make documentation commands use the installed uv environment without synchronizing away optional local profiles.

Review generated diffs for missing endpoints, unresolved assembly, private defaults and leaked local values. A newly read environment option needs reviewed purpose/default/sensitivity information. No exporter should import an application that starts background workers merely to discover documentation.

## Keep current guidance separate from historical evidence

Current usage articles should describe controls that exist now, with actual labels and save/review rules. Do not copy old statements such as console-only project creation or missing routes after those features have shipped. Historical walkthroughs, experiment reports and ticket artifacts remain dated evidence, not current user instructions.

When a feature needs a provider, model, hardware, stock, method, license or lab operator, state that prerequisite where the user needs it. Distinguish unavailable software, blocked admission, running work, a completed computation, independent evaluation and human scientific approval.

Before reporting completion, check that new articles are reachable from the signed-in navigation, local search finds both guides and exhaustive references, internal links/fragments work, and long tables/code remain readable at narrow widths.
