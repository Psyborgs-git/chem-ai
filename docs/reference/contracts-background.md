# Background service API — JSON contract details

These excerpts are generated from the implementation without importing it. They specify accepted fields, conditional validation, defaults and response construction for flexible JSON interfaces. They complement the endpoint prose; implementation expressions refer to the named source service rather than a live execution.

## BackgroundChange

Source: `services/studio-api/src/studio/api/background.py:BackgroundChange`.

```python
class BackgroundChange(BaseModel):
    action: Literal["install", "uninstall"]
```

## background_change

Source: `services/studio-api/src/studio/api/background.py:background_change`.

```python
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
```

## background_status

Source: `services/studio-api/src/studio/api/background.py:background_status`.

```python
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
```
