# Administration

Administer the trusted-machine, single-workspace installation using an owner
account. Capability checks protect shared records; private notebooks, research,
learning jobs, and simulations additionally enforce their author's ownership.
Workspace administrator grants do not grant access to another author's private
content. See [privacy](privacy.md) for the boundaries.

## Access and accounts

First-owner setup is one-time. The browser setup form creates the human owner
and then closes; subsequent access uses sign-in. Sessions expire and can be
ended with **Sign out** or the authenticated logout interface.

There is no delivered multi-user account-management screen or general user
provisioning API. Additional principals/grants are service-layer maintenance,
using `studio.auth.setup.grant_capabilities` and the persistence models, with
an explicitly identified workspace and granting owner. Back up first, verify
that scope, and use password prompting rather than embedding passwords in shell
history. Do not improvise direct grant strings or treat this as supported LAN
multi-user hosting.

The defined roles are `owner`, `researcher`, `lab_operator`,
`scientific_reviewer`, `data_steward`, `viewer`, `agent`, and `service`.
`packages/policy/chem_studio_policy/capabilities.py` is authoritative for their
capability sets. Agent-kind principals have approval/service capability ceilings;
forging grant rows does not give an agent human approval authority.

Revoking a grant sets its revocation timestamp; disabling a principal and ending
a session preserve history. These actions are distinct: removing one grant does
not erase that principal's records or credentials. There is no delivered
self-service password-reset flow. Avoid disabling the only verified owner
without a tested access-recovery procedure.

## Processes and background work

The API starts the private agent supervisor and the private learning/simulation
dispatchers. They own durable leases, progress, cancellation, and recovery for
their own job families. A browser tab or open sidebar is not required for work
to continue, but the backend must remain running and the machine awake.

Older generic task runs and their caller-driven reconciliation are a separate
mechanism. Do not apply the older “no scheduler” description to the private
supervisors, or assume their restart behavior applies to every generic run.

On macOS, the optional background service is an explicit host-owner action:

```sh
bash infra/local/background.sh status
bash infra/local/background.sh install
```

The service uses label `com.chemistrystudio.research`, waits for an existing
healthy 8787 service to finish, starts the local PostgreSQL/API runtime, and
writes `.runtime/background/service.log`. It does not keep the computer awake.
It runs against the checkout recorded in its LaunchAgent; after moving a
checkout, uninstall and reinstall from the intended checkout:

```sh
bash infra/local/background.sh uninstall
```

Disable recurring work and this service before a consistent backup or migration.
The desktop app terminates only a backend child it owns; hiding its window,
quitting it, and stopping a separate background backend have different effects.
See [desktop](desktop-macos.md).

## Jobs, admission, and cancellation

Inspect persisted status, events, attempt history, resource budget, and errors
in the relevant task, Agent, Local learning, or simulation surface. A queued or
cancel-requested state is not proof that a process has completed or stopped.

- Generic runs record cancellation requests and explicit terminal outcomes.
  Stale generic run reconciliation remains caller-driven.
- Private agent cancellation stops further agent steps at checkpoints. Existing
  learning/simulation jobs retain their independent controls and checkpoints.
- Private learning cancellation stops its process group; resume behavior depends
  on backend. MLX adapter resume is a warm start, while Transformers can restore
  optimizer checkpoints.
- Simulation cancellation/timeout stops its process group. Resumption uses the
  last completed stage and the original cumulative time allowance.
- Remote worker leases and heartbeats are owner-authenticated; recover missing
  uploaded checkpoints/model mappings before resuming interrupted work.

Private autopilot is off by default. Balanced defaults limit time, document
fetches, training concurrency, and paid spend. Configure actual model token
prices and an explicit paid budget before paid autopilot. Inspect the owner's
usage/reservations rather than assuming each retry starts a fresh allowance.

## Incident response

1. Stop suspicious work and revoke the affected session/grant/principal as
   appropriate. Disable recurring activity if it could continue the incident.
2. For source-content concerns, revoke the source through the quality workflow;
   preserve the cascade report and original provenance.
3. Preserve relevant audit, outbox, job, and process logs privately. Take a
   quiesced backup before repairing state.
4. Run the [recovery checks](recovery.md), inspect the reported item IDs, and
   validate newer private states separately.
5. Recover into clean destinations if integrity is uncertain. Do not downgrade a
   populated schema or delete vault files to make an error disappear.

Audit and outbox data are append-only through application paths, but are not a
cryptographically tamper-proof defense against a database administrator. SSE
uses the outbox ledger; a raw database write does not automatically become a
correct application event.

## Dependencies and verification

Update Python constraints with `pyproject.toml` and regenerate `uv.lock`; update
JavaScript dependencies and `pnpm-lock.yaml` in their owning workspace. Optional
worker requirement locks, Dockerfiles, image tags, licenses, and platform notes
must agree. Preserve isolated optional environments rather than importing heavy
runtime packages into the API process.

After a dependency or runtime change, run checks appropriate to the changed
layer. A broad release verification normally includes:

```sh
make verify-core
make typecheck
make test-integration
make test-security
pnpm --filter studio-web test
pnpm build:web
make test-e2e
```

Install Playwright Chromium before browser tests if needed. Engine, native,
backup, and heavy training/simulation checks have additional prerequisites and
are required only for claims about those lanes. Record missing prerequisites;
a skipped or fixture-only check is not evidence of live scientific capability.
Documentation changes use the [documentation checks](../development/testing-and-docs.md).

## Observability and maintenance

There is no general metrics/tracing exporter configured. Use structured API
logs, application audit/outbox rows, and persisted job events. Preserve logs
with the same privacy controls as research data. The [configuration inventory](configuration.md)
lists file locations. Explicit maintenance backfills are documented in
[recovery](recovery.md); they are not autonomous background cleanups.
