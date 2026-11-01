# Native Mac runtime contract

The native shell serves the production frontend through the local FastAPI
process. Its WebView navigates to `http://127.0.0.1:8788/`; relative auth,
GraphQL, artifact and event URLs therefore share the same origin and the
existing HttpOnly, SameSite=Strict session cookie. No CORS relaxation or
password injection is needed. Browser development on ports 5173/8787 is
independent.

## This machine's prerequisites

The app launcher uses the workspace path captured when the app is built, its
`.venv` Python environment (including
native RDKit), and Docker Desktop's PostgreSQL container. A frontend build is
bundled in the native application. This arrangement makes a directly launchable
app for this Mac; it is not a portable, self-contained Python/database installer.

The persistent database remains the Compose volume `chem-studio-pgdata` and the
artifact vault remains `<workspace>/.runtime/vault`. App exit must only terminate
an API child owned by that app process, never an existing API or PostgreSQL.

## Launch sequence

1. Resolve the bundled `Resources/frontend` resource directory to an absolute path containing
   `index.html` and `assets/`. This is a trusted build output, never the workspace
   root or the artifact vault.
2. If port 8788 is occupied, reuse it only if `GET /api/desktop/runtime` returns
   the identity below with `frontendAvailable: true` and `databaseReady: true`. An unrelated listener
   is an error; do not terminate it.
3. Start Docker Desktop if needed and wait for a successful Docker daemon probe.
   Then, from the workspace, run
   `docker compose -f infra/local/compose.yaml up -d postgres`. Wait until
   `docker exec chem-studio-postgres pg_isready -h 127.0.0.1 -U studio -d studio`
   succeeds. Surface an actionable startup error if Docker cannot start.
4. Run `.venv/bin/alembic -c services/studio-api/migrations/alembic.ini upgrade head`
   from the workspace. A nonzero exit is a startup failure. No migration reset,
   schema drop, owner creation, or database reinitialization is part of launch.
5. Spawn `.venv/bin/uvicorn studio.api.app:create_app --factory --host 127.0.0.1 --port 8788`
   with the working directory and environment below. Capture startup diagnostics
   privately and redact credentials before displaying them.
6. Wait for the child to remain alive, the runtime identity to match, and `GET /`
   to return HTML successfully. Only then navigate the native window to that
   origin. Keep the application's normal setup/sign-in flow.

Required child environment:

| Name | Value |
| --- | --- |
| `STUDIO_BIND_HOST` | `127.0.0.1` |
| `STUDIO_PORT` | `8788` |
| `STUDIO_ALLOWED_ORIGINS` | `http://127.0.0.1:8788,http://localhost:8788` |
| `STUDIO_DESKTOP_FRONTEND_DIR` | Absolute bundled frontend resource directory |
| `STUDIO_VAULT_ROOT` | `<workspace>/.runtime/vault` |

`STUDIO_DATABASE_URL` can retain the existing local deployment override. When
unset, the API and Alembic both use the Compose database on loopback port 54329.
Do not print connection strings or source shell profile files to obtain them.

The desktop identity route is enabled only with the frontend setting:

```json
{"application":"chemistry-studio","desktop":true,"frontendAvailable":true,"databaseReady":true}
```

`/healthz` proves that HTTP responds. `/readyz` describes configured capabilities;
it is not a database/schema connectivity check. Successful migrations and the
PostgreSQL readiness probe are required before presenting the research UI. The
desktop identity also checks database connectivity and the migration-version
table, returning 503 when the database or bundled frontend is unavailable.

## Static-file boundaries

The optional frontend mount comes after all API routes. Unknown `/api`,
`/graphql`, `/healthz` and `/readyz` paths return 404; missing asset files return
404. HTML navigation to extensionless UI routes gets the SPA entry point.
Hidden files, traversal paths and symlinks escaping the frontend directory are
not served. A frontend root overlapping the vault or missing its own built
`index.html` refuses startup. Existing Host/Origin checks remain active, and the
SPA entry point is served with `Cache-Control: no-store`.

Focused verification is in
`services/studio-api/tests/unit/test_desktop_web.py` and
`services/studio-api/tests/integration/test_desktop_auth.py`.
