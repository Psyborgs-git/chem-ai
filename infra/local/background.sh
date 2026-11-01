#!/usr/bin/env bash
# Opt-in macOS service: research/training survive closing the desktop UI.
set -euo pipefail
umask 077
studio_repo="$(cd "$(dirname "$0")/../.." && pwd)"
studio_label="com.chemistrystudio.research"
studio_plist="$HOME/Library/LaunchAgents/$studio_label.plist"
case "${1:-status}" in
  install)
    mkdir -p "$HOME/Library/LaunchAgents" "$studio_repo/.runtime/background"
    "$studio_repo/.venv/bin/python" - "$studio_repo" "$studio_plist" "$studio_label" <<'PY'
import plistlib
import sys
from pathlib import Path
root, destination, label = sys.argv[1:]
config = {'Label': label, 'ProgramArguments': ['/bin/bash', str(Path(root) / 'infra/local/background.sh'), 'run'], 'WorkingDirectory': root, 'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 30, 'StandardOutPath': str(Path(root) / '.runtime/background/service.log'), 'StandardErrorPath': str(Path(root) / '.runtime/background/service.log')}
target = Path(destination)
target.write_bytes(plistlib.dumps(config))
target.chmod(0o600)
PY
    launchctl bootstrap "gui/$(id -u)" "$studio_plist"
    ;;
  uninstall)
    launchctl bootout "gui/$(id -u)/$studio_label" 2>/dev/null || true
    rm -f "$studio_plist"
    ;;
  status)
    launchctl print "gui/$(id -u)/$studio_label" 2>/dev/null || {
      echo "Background research service is not installed."
      exit 0
    }
    ;;
  run)
    cd "$studio_repo"
    export PATH="$studio_repo/.runtime/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
    export STUDIO_VAULT_ROOT="${STUDIO_VAULT_ROOT:-$studio_repo/.runtime/vault}"
    export STUDIO_SEARXNG_URL="${STUDIO_SEARXNG_URL:-http://127.0.0.1:8088}"
    export STUDIO_DESKTOP_FRONTEND_DIR="$studio_repo/apps/studio-web/dist"
    # Let an existing foreground runtime finish; never replace a listening service.
    while /usr/bin/curl --silent --fail --max-time 2 http://127.0.0.1:8787/healthz >/dev/null 2>&1; do
      sleep 10
    done
    docker compose -f infra/local/compose.yaml up -d postgres
    "$studio_repo/.venv/bin/alembic" -c services/studio-api/migrations/alembic.ini upgrade head
    exec "$studio_repo/.venv/bin/uvicorn" studio.api.app:create_app --factory --host 127.0.0.1 --port 8787
    ;;
  *)
    echo "Usage: bash infra/local/background.sh install|uninstall|status|run" >&2
    exit 2
    ;;
esac
