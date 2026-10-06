# Runbook — administration (access, jobs, incidents, dependencies)

Audience: workspace owner (`administer_workspace` capability) on the
loopback single-workspace deployment.

## 1. Access model — read this first

- **One workspace, one owner** (E04): `POST /api/auth/setup` creates
  the owner once and then refuses. The owner role holds every
  capability (§21.1 vocabulary in
  `packages/policy/chem_studio_policy/capabilities.py`).
- **No multi-user UI/API exists.** Additional principals are created
  only through the service layer — in a `uv run python` shell:

```python
# uv run python  (from repo root, STUDIO_DATABASE_URL honored)
from studio.auth.setup import grant_capabilities, hash_password
from studio.config.settings import get_settings
from studio.persistence.engine import make_engine, make_session_factory
from studio.persistence.models import Principal, Workspace

db = make_session_factory(make_engine(get_settings().database_url))()
ws = db.query(Workspace).order_by(Workspace.created_at).first()
p = Principal(workspace_id=ws.id, kind="user", login="analyst",
              display_name="Analyst",
              credential_hash=hash_password("<≥10 chars>"))
db.add(p); db.flush()
grant_capabilities(db, ws.id, p, "researcher", granted_by=owner_id)
db.commit()
```

Roles map to fixed capability sets (`capabilities_for_role`):
`owner`, `researcher`, `lab_operator`, `scientific_reviewer`,
`data_steward`, `viewer`, `agent`, `service`. Grant *roles*, not ad-hoc
capability strings — unknown capability strings never evaluate true
(CS-1101 `TestCapabilityCeilings`).

- **Revocation:** set `PrincipalCapability.revoked_at` (rows stay as
  history; `load_context` excludes them), disable a principal via
  `disabled_at`, end a session via `POST /api/auth/logout` or
  `revoke_session`. Grant revocation is lazy — no cascade required.
- **Agent ceiling:** `approval`/`service`-class capabilities are
  stripped from agent principals at context load — a forged grant row
  does not confer them (CS-1101 verified).

## 2. Jobs, queue and cancellation

- Run lifecycle lives on the `runs` tab + `/compute` (see
  `user.md` §8). Procrastinate bridges to Postgres; attempts execute
  through the §13.3 isolation profiles.
- **Cancel:** `runsRequestCancelMutation` records the request;
  `confirm_cancelled` is the explicit termination marker — never
  trust acknowledgment alone.
- **Reconciliation:** stale `running` rows are reconciled by callers
  (`reconcile` with staleness threshold — CS-0401); there is no
  background scheduler. After an API restart, re-run reconcile before
  trusting run state.
- **Backfills:** `infra/local/resumable_backfill.py` —
  `run`/`status`/`verify` subcommands (checkpointed, idempotent,
  append-only; see `recovery.md` §2 for kill-resume semantics).

## 3. Incident response

1. **Contain:** revoke the session/principal (§1). For suspect source
   content, revoke the artifact — `privacy.md` §3 (the cascade marks
   chunks/records/claims/derived artifacts consistently).
2. **Inspect:** audit rows are append-only in Postgres; the outbox
   table (`outbox_events` + `outbox_deliveries`) is the event ledger —
   nothing published outside it appears in streams.
3. **Preserve evidence:** take a backup before remediation
   (`backup-restore.md`); revoked-state bytes stay recoverable in the
   vault/backups by design.
4. **Verify integrity after the fact:**
   `uv run python infra/local/recovery_check.py --dsn <dsn> --vault <dir>`
   enumerates every missing/broken item (12 checks — alembic head,
   blobs, lineage, digests, approvals, grants, sessions…).
5. **Never** `alembic downgrade` a populated install (`recovery.md` §1).

## 4. Dependency updates

- Python: bump in `pyproject.toml`, `uv lock`, `uv sync --frozen`;
  keep `docs/dependencies.lock.md` notes current (license/platform
  caveats live there).
- JS: `pnpm update` per workspace package, keep `--frozen-lockfile`
  green.
- Engine/worker images: rebuild the pinned Dockerfiles
  (`model-ops.md` §2) and re-run that lane's engine tests — image tags
  are content-versioned (`-vN`), so a new build is a new tag.
- **Verification battery after any dependency change:**

```bash
make verify-core && make typecheck
make test-integration && make test-security
pnpm --filter studio-web test && pnpm --filter studio-web typecheck
pnpm --filter studio-web exec playwright install chromium && make test-e2e
```

- Upstream drift rule (§28): pin tested versions, isolate adapters,
  read official docs — never swap a maintained engine for a homemade
  solver out of convenience.

## 5. Observability

- Structured audit events write to Postgres (sensitive keys dropped at
  any nesting depth — CS-1101 `TestAuditRedaction`); there is no
  metrics/tracing exporter in the core profile.
- SSE streams (`/api/events`) carry message-level events with sequence
  ids; the outbox is authoritative — direct DB writes never stream.

## Failure symptoms

| Symptom | Cause | Recovery |
|---|---|---|
| `workspace already has an owner` on setup | normal — bootstrap is one-time | log in; provision users via §1 |
| Run stuck `running` after API restart | reconcile is caller-driven | run reconcile with staleness threshold (CS-0401) |
| `FORBIDDEN` despite grant row | agent-kind ceiling / revoked_at set | expected behavior — check principal kind + revocation |
| `recovery_check` lists missing items | incomplete restore/sabotage | do not trust the install; restore again or investigate |

## Privacy concerns

- Admin inspection touches all workspace data — the loopback
  deployment assumes a single trusted owner; any multi-tenant need is
  a redesign, not a config change (U07).
- Audit/outbox are append-only without cryptographic tamper-proofing
  (residual R11) — treat DB access as in-threat-model.

## Evidence location

`docs/execution/tickets/CS-0102.md` (principals/capabilities),
`CS-0105.md` (outbox/audit), `CS-0401/0402/0403.md` (runs/admission/
isolation), `CS-1101.md` (adversarial review),
`CS-1102.md` (lifecycle verification).
