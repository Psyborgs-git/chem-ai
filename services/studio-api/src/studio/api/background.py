"""Explicit host-owner controls for the optional fixed macOS background service."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from studio.api.deps import Ctx
from studio.errors import DomainError, ErrorCode

background_router = APIRouter(prefix="/api/agent-workspace/background", tags=["background"])
_LABEL = "com.chemistrystudio.research"


class BackgroundChange(BaseModel):
    action: Literal["install", "uninstall"]


def _require_host_owner(ctx: Ctx) -> None:
    # Workspace membership alone must not authorize changes to the OS service.
    from studio.domain.inference.providers import ProviderService

    ProviderService(ctx.session, ctx)._admin()


@background_router.get("")
def background_status(ctx: Ctx) -> dict[str, bool | str]:
    _require_host_owner(ctx)
    supported = platform.system() == "Darwin"
    if not supported:
        return {"supported": False, "installed": False, "running": False}
    plist = Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"
    result = subprocess.run(  # noqa: S603 - fixed executable and service label
        ["/bin/launchctl", "print", f"gui/{os.getuid()}/{_LABEL}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=5,
    )
    return {"supported": True, "installed": plist.is_file(), "running": result.returncode == 0}


@background_router.post("")
def background_change(data: BackgroundChange, ctx: Ctx) -> dict[str, bool | str]:
    _require_host_owner(ctx)
    if platform.system() != "Darwin":
        raise DomainError(ErrorCode.ENGINE_UNAVAILABLE, "macOS background service is unavailable")
    script = Path(__file__).resolve().parents[5] / "infra" / "local" / "background.sh"
    if not script.is_file():
        raise DomainError(ErrorCode.ENGINE_UNAVAILABLE, "background launcher is not installed")
    result = subprocess.run(  # noqa: S603 - fixed local script, enum action; no shell input
        ["/bin/bash", str(script), data.action],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=20,
    )
    if result.returncode:
        raise DomainError(ErrorCode.RESOURCE_UNAVAILABLE, "background service change failed")
    return background_status(ctx)
