#!/usr/bin/env python3
"""Sync canonical contracts into packages/contracts/ (handoff kickoff §1).

One authoritative source directory: ``docs/chemistry-studio/contracts/``.
This script copies the schemas here and writes checksums into
``manifest.json`` — mirrors are generated/checksummed, never hand-edited.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs" / "chemistry-studio" / "contracts"
TARGET = ROOT / "packages" / "contracts"
MANIFEST = TARGET / "manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(check_only: bool = False) -> int:
    manifest = json.loads(MANIFEST.read_text())
    recorded: dict[str, str] = manifest.setdefault("schemas", {})

    problems: list[str] = []
    current: dict[str, str] = {}
    for src in sorted(SOURCE.glob("*.json")):
        digest = sha256(src)
        current[src.name] = digest
        dst = TARGET / src.name
        if check_only:
            if not dst.exists() or sha256(dst) != digest or recorded.get(src.name) != digest:
                problems.append(f"{src.name}: mirror stale or missing")
        else:
            shutil.copy2(src, dst)

    if not check_only:
        manifest["schemas"] = current
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"synced {len(current)} contract files:")
        for name, digest in current.items():
            print(f"  {name}  {digest[:16]}…")
        return 0

    stale_recorded = set(recorded) - set(current)
    for name in stale_recorded:
        problems.append(f"{name}: recorded schema removed from source")
    if problems:
        for p in problems:
            print(f"DRIFT: {p}")
        return 1
    print("contract mirrors in sync (checksum-verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main(check_only="--check" in sys.argv))
