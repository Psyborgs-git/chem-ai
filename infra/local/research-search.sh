#!/usr/bin/env bash
# Optional app-local web search. No API key or remote account is required.
set -euo pipefail
umask 077
studio_repo="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$studio_repo"
case "${1:-start}" in
  start)
    mkdir -p .runtime/research-search
    if [[ ! -f .runtime/research-search/settings.yml ]]; then
      .venv/bin/python - <<'PY'
from pathlib import Path
import secrets
path = Path('.runtime/research-search/settings.yml')
path.write_text('use_default_settings: true\nserver:\n  port: 8080\n  bind_address: "0.0.0.0"\n  secret_key: "' + secrets.token_hex(32) + '"\n  limiter: false\n  image_proxy: false\nsearch:\n  formats: [html, json]\n')
path.chmod(0o600)
PY
    fi
    docker compose -f infra/local/compose.yaml --profile research up -d research-search
    ;;
  stop)
    docker compose -f infra/local/compose.yaml --profile research stop research-search
    ;;
  status)
    docker compose -f infra/local/compose.yaml --profile research ps research-search
    ;;
  *)
    echo "Usage: bash infra/local/research-search.sh start|stop|status" >&2
    exit 2
    ;;
esac
