# Native macOS app (local runtime)

Chemistry Studio's Tauri 2 shell builds a native macOS `.app` and a DMG.
It uses the installed Python environment and Docker database in this checkout.
This first local package is intended for this Mac; it is not a standalone
redistributable Python/database installer.

## Build and open

The checkout needs its existing `.venv` with the core and native RDKit engine
profile, Docker Desktop, Rust and Xcode command-line tools. The app bundle uses
the absolute checkout path recorded at build time. Rebuild after moving the
checkout. No terminal is needed to start the app after it has been built.
On the first Finder launch, macOS asks for access to Documents because this
checkout and its installed Python runtime live there. Choose Allow in that
macOS permission dialog. Startup waits for that decision; the app cannot grant
the permission on your behalf. The bundled usage description explains why.

```sh
export PATH="$PWD/.runtime/bin:$PATH"
pnpm build:desktop
pnpm open:desktop
pnpm test:desktop
pnpm smoke:desktop
```

Artifacts:

- `apps/studio-web/src-tauri/target/release/bundle/macos/Chemistry Studio.app`
- `apps/studio-web/src-tauri/target/release/bundle/dmg/` (DMG installer)

The app uses an ad-hoc signature for this Mac. Public distribution would require
an Apple signing identity, notarization and a separately packaged scientific
runtime. The DMG contains the native app and bundled frontend, not Python or
Docker.

Quit the app before `pnpm smoke:desktop`. The smoke check launches it with a
Finder-like minimal PATH, verifies the actual bundled startup UI's native
handoff, then checks both owned-process cleanup and reuse of a separately owned
backend. It does not create research records or use account credentials. DMG
packaging runs with `CI=true`, avoiding Finder Automation permission for cosmetic
installer-window positioning.

## Startup and ownership

The bundled boot screen displays actual runtime phases and actionable errors.
The shell first checks loopback ports 8788 and 8787 for Chemistry Studio's
desktop identity, the exact build marker embedded in this native binary, a
ready database and its bundled HTML interface. A matching
service is reused and is never stopped by this app. New owned services prefer
the dedicated desktop port 8788, leaving a development service on 8787 intact.
An older desktop backend with a different or absent build marker is left
untouched. The new app starts its own backend on the other available port; it
never loads an older backend's interface merely because its generic health
check passes. Rebuilds track frontend assets, API source and contract changes.

To build without replacing the resources of a currently running source app,
set `CARGO_TARGET_DIR` to a separate workspace directory for build/open/test;
the scripts honor it. The loopback backend's `STUDIO_DESKTOP_BUILD_ID` is fixed
when that process starts, so replacement files cannot update its identity.

Otherwise the shell locates the installed Docker CLI, opens Docker Desktop if
needed, starts the existing `infra/local/compose.yaml` PostgreSQL service on
loopback port 54329, waits for readiness, and applies existing Alembic migrations.
It launches this checkout's `.venv/bin/python -m uvicorn` on an available app
port and serves `Resources/frontend` through the same backend origin. Session
cookies and relative API requests therefore remain same-origin.

Quitting stops only the backend child launched by this app. PostgreSQL and
Docker Desktop continue running, retaining existing research data. An unrelated
server occupying either port is never killed. Runtime output is appended to
`.runtime/desktop/runtime.log`; this folder is outside every served frontend.
Closing the window hides it; clicking the Dock icon reopens it. Quit from the
native app menu or Command-Q to stop an owned backend. The log folder is private
(0700), and the log file is readable and writable by the current user only (0600).

## Native boundary

The boot screen has three fixed native commands: `runtime_status`,
`runtime_retry` and `runtime_open`. They accept no filesystem paths, program
names, arguments or URLs. Each command verifies that it originated in the
bundled asset page. Runtime navigation permits only verified loopback app ports;
web citations open in the system browser. The loopback app receives only the
permission needed to drag its native title bar, with no shell or filesystem
plugin exposed.

Reference: [Tauri Vite integration](https://v2.tauri.app/start/frontend/vite/),
[native commands](https://v2.tauri.app/develop/calling-rust/),
[capabilities](https://v2.tauri.app/security/capabilities/),
[macOS bundles](https://v2.tauri.app/distribute/macos-application-bundle/) and
[DMG packaging](https://v2.tauri.app/distribute/dmg/).

## Local verification

The Apple Silicon build was installed in `~/Applications/Chemistry Studio.app`
and opened to the native sign-in screen. A cold-start smoke check verified the
bundled startup screen's native handoff, database readiness and owned-process
shutdown; a separate check verified reuse of an existing backend. The DMG and
ad-hoc app signature were verified locally.

The native loopback service calculated ethanol (`CCO`) as C2H6O and 46.069 g/mol
with RDKit, retained the same saved result on replay, and returned a failed
result without descriptors for an invalid-valence control. This calculation was
sent through the native app's local service; it was not a physical experiment.

The latest checks include 107 frontend tests, 14 desktop backend tests, 5 Rust
runtime tests, 8 browser journeys, and 3 launch/recovery/reduced-motion visual
checks. Startup screenshot checks use a controlled native bridge; the actual
macOS app's startup handoff and sign-in screen were checked separately. Local
artifacts are under `.runtime/evidence/native/`.
