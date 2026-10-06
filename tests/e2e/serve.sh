#!/usr/bin/env bash
# Backend for browser journeys: isolated `studio_e2e` database on the
# dev postgres container + uvicorn on 8790. Does NOT touch the dev DB.
set -euo pipefail
cd "$(dirname "$0")/../.."

DB_URL="postgresql+psycopg://studio:studio@127.0.0.1:54329/studio_e2e"

docker compose -f infra/local/compose.yaml up -d postgres >/dev/null
# First-boot race: the postgres image's temp initdb server also answers
# socket-local pg_isready/psql before the real postmaster starts. Probe
# the container's own TCP listener instead — only the real postmaster
# binds it, so this readiness check cannot pass early.
for i in $(seq 1 60); do
  if docker exec chem-studio-postgres pg_isready -h 127.0.0.1 -p 5432 -U studio -d studio >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

docker exec chem-studio-postgres psql -U studio -d studio -tc \
  "SELECT 1 FROM pg_database WHERE datname='studio_e2e'" | grep -q 1 \
  || docker exec chem-studio-postgres psql -U studio -d studio \
       -c "CREATE DATABASE studio_e2e" >/dev/null

STUDIO_DATABASE_URL="$DB_URL" uv run alembic \
  -c services/studio-api/migrations/alembic.ini upgrade head >/dev/null

# fresh world per run — deterministic e2e
STUDIO_DATABASE_URL="$DB_URL" uv run python - <<'PY'
import os
from sqlalchemy import create_engine, text
engine = create_engine(os.environ["STUDIO_DATABASE_URL"])
with engine.begin() as conn:
    for tbl in conn.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' "
        "AND tablename != 'alembic_version'"
    )):
        conn.execute(text(f'TRUNCATE "{tbl[0]}" CASCADE'))
PY

# browser origin is the vite preview on 4173; direct API calls use 8790
export STUDIO_ALLOWED_ORIGINS="http://127.0.0.1:4173,http://127.0.0.1:8790,http://localhost:4173"
# short stream bound so reconnect/resume cycles happen within the test
# budget — a real disconnect is exercised, not emulated timing luck
export STUDIO_EVENT_MAX_SECONDS=2
exec env STUDIO_DATABASE_URL="$DB_URL" uv run uvicorn \
  "studio.api.app:create_app" --factory --host 127.0.0.1 --port 8790
