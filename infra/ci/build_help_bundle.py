"""Hatch wheel hook: package precisely the canonical Help manifest allowlist."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        root = Path(self.root).resolve()
        sys.path.insert(0, str(root / "services/studio-api/src"))
        try:
            from studio.application.studio_docs import documentation_bundle_files

            build_data.setdefault("force_include", {}).update(documentation_bundle_files(root))
        finally:
            sys.path.pop(0)
