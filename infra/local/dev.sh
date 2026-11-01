#!/usr/bin/env bash
# Run the installed local development profile, retaining its native RDKit extra.
set -euo pipefail
umask 077
studio_repo="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$studio_repo"
mkdir -p .runtime/vault .runtime/uv-cache .runtime/python
export UV_CACHE_DIR="${UV_CACHE_DIR:-$studio_repo/.runtime/uv-cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$studio_repo/.runtime/python}"
export STUDIO_VAULT_ROOT="${STUDIO_VAULT_ROOT:-$studio_repo/.runtime/vault}"

if [[ ! -x .venv/bin/uvicorn ]]; then
  echo "Install the core + engine profile first: uv sync --python 3.12 --group dev --extra engines --frozen" >&2
  exit 1
fi
if [[ -x .runtime/bin/pnpm ]]; then
  studio_pnpm="$studio_repo/.runtime/bin/pnpm"
else
  studio_pnpm="$(command -v pnpm)"
fi
export PATH="$(dirname "$studio_pnpm"):$PATH"
if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:8787 -iTCP:5173 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "A local server already uses port 8787 or 5173. Check http://127.0.0.1:5173 before starting another instance." >&2
  exit 1
fi
docker compose -f infra/local/compose.yaml up -d postgres
studio_ready=0
for _ in $(seq 1 60); do
  if docker exec chem-studio-postgres pg_isready -h 127.0.0.1 -U studio -d studio >/dev/null 2>&1; then
    studio_ready=1
    break
  fi
  sleep 1
done
if [[ "$studio_ready" != 1 ]]; then
  echo "PostgreSQL did not become ready in 60 seconds." >&2
  exit 1
fi
.venv/bin/alembic -c services/studio-api/migrations/alembic.ini upgrade head
.venv/bin/uvicorn studio.api.app:create_app --factory --host 127.0.0.1 --port 8787 &
studio_api_pid=$!
trap 'kill "$studio_api_pid" 2>/dev/null || true' EXIT INT TERM
studio_api_ready=0
for _ in $(seq 1 30); do
  if ! kill -0 "$studio_api_pid" 2>/dev/null; then
    echo "The API exited before becoming ready; the UI was not started." >&2
    exit 1
  fi
  if curl --silent --fail --max-time 1 http://127.0.0.1:8787/healthz >/dev/null; then
    studio_api_ready=1
    break
  fi
  sleep 1
done
if [[ "$studio_api_ready" != 1 ]]; then
  echo "The API did not become ready in 30 seconds." >&2
  exit 1
fi
"$studio_pnpm" --filter studio-web dev --strictPort
