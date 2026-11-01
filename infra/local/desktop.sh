#!/usr/bin/env bash
# Build or open the native app without installing tools outside this workspace.
set -euo pipefail
studio_repo="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$studio_repo"
export PATH="$studio_repo/.runtime/bin:$HOME/.cargo/bin:$PATH"
export CARGO_HOME="$studio_repo/.runtime/cargo"
export CARGO_INCREMENTAL=0
export CARGO_PROFILE_RELEASE_DEBUG=false
export CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-4}"
studio_target="${CARGO_TARGET_DIR:-$studio_repo/apps/studio-web/src-tauri/target}"
studio_app="$studio_target/release/bundle/macos/Chemistry Studio.app"
case "${1:-build}" in
  build)
    # Avoid Finder Automation permission for cosmetic DMG window positioning.
    # The installer still contains the signed app and Applications shortcut.
    CI=true pnpm --filter studio-web exec tauri build --bundles app,dmg --ci
    ;;
  open)
    if [[ ! -d "$studio_app" ]]; then
      echo "Build the native app first with pnpm build:desktop." >&2
      exit 1
    fi
    open "$studio_app"
    ;;
  test)
    cargo test --release --manifest-path apps/studio-web/src-tauri/Cargo.toml
    ;;
  *)
    echo "Usage: pnpm build:desktop | pnpm open:desktop | pnpm test:desktop" >&2
    exit 2
    ;;
esac
