"""Isolated execution backends (§13.3, §13.5).

Two backends share one contract:

* ``ContainerBackend`` (preferred): ``docker run --network none
  --read-only`` with only the per-run scratch mounted writable —
  kernel-level network denial and filesystem isolation. Cancellation
  is ``docker kill`` + ``docker rm -f``: the container's whole process
  tree dies with it.
* ``SubprocessBackend`` (fallback): scrubbed environment, HOME/TMPDIR
  redirected into scratch, POSIX rlimits, killable process group. It
  CANNOT deny network at the OS level on this platform — the profile
  says so, and a run that requires network denial is refused rather
  than executed unprotected (§13.3).

Every result records the isolation profile that was *actually*
enforced; a control the backend cannot apply is reported absent,
never claimed.
"""

from __future__ import annotations

import json
import os
import resource
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ExecLimits:
    wall_seconds: float = 60.0
    cpu_seconds: int = 30
    memory_bytes: int = 512 * 1024 * 1024
    output_bytes: int = 1024 * 1024  # captured stdout+stderr cap
    file_bytes: int = 64 * 1024 * 1024  # largest single scratch file
    max_processes: int = 64
    grace_seconds: float = 2.0


@dataclass
class IsolationProfile:
    """What the backend actually enforces — reported, not assumed."""

    backend: str
    # Values are bool, or a per-dimension map (e.g. rlimits reports
    # exactly which limits the platform honors).
    enforced: dict[str, object]
    notes: str = ""

    def enforces(self, control: str) -> bool:
        return bool(self.enforced.get(control, False))


@dataclass
class ExecResult:
    exit_code: int | None
    timed_out: bool
    cancelled: bool
    wall_seconds: float
    stdout: str
    stderr: str
    truncated: bool
    profile: IsolationProfile
    scratch_dir: str = ""
    scratch_files: list[str] = field(default_factory=list)
    tree_exited: bool = True  # False if any child survived the kill

    def json_stdout(self) -> dict[str, Any] | None:
        try:
            value = json.loads(self.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return None
        return value if isinstance(value, dict) else None


class ExecutionBackend(Protocol):
    profile: IsolationProfile

    def run(
        self,
        argv: list[str],
        *,
        inputs: dict[str, bytes],
        limits: ExecLimits,
        cancel: threading.Event | None = None,
    ) -> ExecResult: ...


def _scrubbed_env(scratch: str) -> dict[str, str]:
    """Minimal environment — nothing inherited, no credentials, no
    proxy variables, HOME and TMPDIR confined to scratch (§13.3)."""
    return {
        "HOME": scratch,
        "TMPDIR": scratch,
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LC_ALL": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _write_inputs(scratch: str, inputs: dict[str, bytes]) -> None:
    for name, data in inputs.items():
        # Allowlisted relative names only — a path escape is refused.
        if name != os.path.basename(name) or name in {".", ".."}:
            raise ValueError(f"unsafe input name: {name!r}")
        with open(os.path.join(scratch, name), "wb") as f:
            f.write(data)


def _scratch_listing(scratch: str) -> list[str]:
    return sorted(p for p in os.listdir(scratch) if os.path.isfile(os.path.join(scratch, p)))


_RLIMITS = {
    "cpu": resource.RLIMIT_CPU,
    "memory": resource.RLIMIT_AS,
    "file": resource.RLIMIT_FSIZE,
    # RLIMIT_NPROC is deliberately absent: it caps processes per-UID,
    # not per-tree — on a shared-UID host it cannot bound one run and
    # would only produce spurious fork failures. Per-tree process
    # limits are the container backend's --pids-limit.
}


def _rlimit_supported(lim: int, value: int) -> bool:
    """Probe whether this platform accepts the limit, then restore —
    a control the OS refuses is reported, not silently skipped."""
    soft, hard = resource.getrlimit(lim)
    try:
        resource.setrlimit(lim, (value, hard))
        resource.setrlimit(lim, (soft, hard))
        return True
    except (ValueError, OSError):
        try:
            resource.setrlimit(lim, (soft, hard))
        except (ValueError, OSError):
            pass
        return False


class SubprocessBackend:
    """POSIX subprocess profile: env scrub, HOME redirect, rlimits,
    group kill. Honest boundary: no network deny, no chroot."""

    name = "restricted-subprocess"

    def __init__(self, scratch_root: str | None = None) -> None:
        self.scratch_root = scratch_root
        # Probe each rlimit once — macOS accepts FSIZE/NPROC/CPU but
        # refuses RLIMIT_AS; the profile reports exactly what applied.
        self._limits_ok = {name: _rlimit_supported(lim, 1024) for name, lim in _RLIMITS.items()}
        self.profile = IsolationProfile(
            backend=self.name,
            enforced={
                "argv_only_no_shell": True,
                "env_scrubbed": True,
                "home_isolated": True,  # HOME/TMPDIR point at scratch
                "rlimits": dict(self._limits_ok),
                "process_tree_kill": True,
                "network_denied": False,  # not enforceable here — stated
                "filesystem_read_only": False,
            },
            notes=(
                "Network egress and arbitrary filesystem reads are NOT "
                "denied at the OS level by this backend. Runs requiring "
                "those controls must use the container backend or be "
                "reported blocked."
            ),
        )

    def _apply_limits(self, limits: ExecLimits) -> None:  # preexec_fn
        wanted = {
            "cpu": limits.cpu_seconds,
            "memory": limits.memory_bytes,
            "file": limits.file_bytes,
        }
        for name, value in wanted.items():
            if not self._limits_ok.get(name):
                continue  # platform refused — reported in the profile
            try:
                resource.setrlimit(_RLIMITS[name], (value, value))
            except (ValueError, OSError):
                pass

    def run(
        self,
        argv: list[str],
        *,
        inputs: dict[str, bytes],
        limits: ExecLimits,
        cancel: threading.Event | None = None,
    ) -> ExecResult:
        scratch = tempfile.mkdtemp(prefix="run-", dir=self.scratch_root)
        _write_inputs(scratch, inputs)
        proc = subprocess.Popen(  # noqa: S603 — argv list, never a shell
            argv,
            executable=argv[0],
            env=_scrubbed_env(scratch),
            cwd=scratch,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=lambda: self._apply_limits(limits),
        )
        deadline = time.monotonic() + limits.wall_seconds
        cancelled = timed_out = False
        while True:
            code = proc.poll()
            if code is not None:
                break
            if cancel is not None and cancel.is_set():
                cancelled = True
                self._kill_tree(proc, limits.grace_seconds)
                break
            if time.monotonic() > deadline:
                timed_out = True
                self._kill_tree(proc, limits.grace_seconds)
                break
            time.sleep(0.05)
        try:
            out, err = proc.communicate(timeout=limits.grace_seconds + 5)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            proc.kill()
            out, err = proc.communicate()
        truncated = False
        if len(out) > limits.output_bytes:
            out, truncated = out[: limits.output_bytes], True
        if len(err) > limits.output_bytes:
            err, truncated = err[: limits.output_bytes], True
        tree_exited = self._tree_exited(proc)
        return ExecResult(
            exit_code=proc.returncode,
            timed_out=timed_out,
            cancelled=cancelled,
            wall_seconds=time.monotonic() - (deadline - limits.wall_seconds),
            stdout=out.decode("utf-8", "replace"),
            stderr=err.decode("utf-8", "replace"),
            truncated=truncated,
            profile=self.profile,
            scratch_dir=scratch,
            scratch_files=_scratch_listing(scratch),
            tree_exited=tree_exited,
        )

    def _kill_tree(self, proc: subprocess.Popen[bytes], grace: float) -> None:
        """Kill the whole group (start_new_session made the child the
        group leader — every descendant shares its pgid)."""
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                proc.wait(timeout=grace)
            except subprocess.TimeoutExpired:  # pragma: no cover
                pass

    @staticmethod
    def _tree_exited(proc: subprocess.Popen[bytes]) -> bool:
        """Best-effort check that no group member survived."""
        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            return True
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        return False


class ContainerBackend:
    """Docker isolation: ``--network none --read-only`` with only the
    scratch dir mounted — real kernel-level denial, not a marker."""

    name = "container"

    def __init__(
        self,
        image: str = "python:3.12-slim",
        scratch_root: str | None = None,
        docker: str | None = None,
    ) -> None:
        self.image = image
        self.scratch_root = scratch_root or tempfile.gettempdir()
        self.docker = docker or shutil.which("docker") or "docker"
        self.profile = IsolationProfile(
            backend=self.name,
            enforced={
                "argv_only_no_shell": True,
                "env_scrubbed": True,
                "home_isolated": True,
                "rlimits": True,  # --memory/--cpus/--pids-limit
                "process_tree_kill": True,  # docker kill removes the container
                "network_denied": True,  # --network none
                "filesystem_read_only": True,
            },
            notes=f"image={image}; scratch bind-mounted as the only writable path",
        )

    @staticmethod
    def available(image: str = "python:3.12-slim") -> bool:
        docker = shutil.which("docker")
        if not docker:
            return False
        try:
            out = subprocess.run(  # noqa: S603 — resolved docker CLI, fixed argv
                [docker, "image", "inspect", image],
                capture_output=True,
                timeout=10,
                check=False,
            )
            return out.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def run(
        self,
        argv: list[str],
        *,
        inputs: dict[str, bytes],
        limits: ExecLimits,
        cancel: threading.Event | None = None,
    ) -> ExecResult:
        scratch = tempfile.mkdtemp(prefix="run-", dir=self.scratch_root)
        # The container runs as an unprivileged uid; the bind mount
        # must be writable by it — world-writable scratch only.
        os.chmod(scratch, 0o777)  # noqa: S103
        _write_inputs(scratch, inputs)
        name = f"run-{uuid.uuid4().hex[:12]}"
        mem = max(limits.memory_bytes // (1024 * 1024), 16)
        cmd = [
            self.docker,
            "run",
            "--name",
            name,
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=16m",  # noqa: S108 — container tmpfs flag
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            f"{mem}m",
            "--pids-limit",
            str(limits.max_processes),
            "--user",
            "65534:65534",
            "--env",
            "HOME=/work",
            "--env",
            "TMPDIR=/tmp",
            "-v",
            f"{scratch}:/work:rw",
            "-w",
            "/work",
            "--stop-timeout",
            str(int(limits.grace_seconds)),
            self.image,
            *argv,
        ]
        proc = subprocess.Popen(  # noqa: S603 — argv list, never a shell
            cmd,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + limits.wall_seconds
        cancelled = timed_out = False
        while True:
            if proc.poll() is not None:
                break
            if cancel is not None and cancel.is_set():
                cancelled = True
                self._kill(name)
                break
            if time.monotonic() > deadline:
                timed_out = True
                self._kill(name)
                break
            time.sleep(0.1)
        try:
            out, err = proc.communicate(timeout=limits.grace_seconds + 30)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()
            out, err = proc.communicate()
        self._rm(name)
        truncated = False
        if len(out) > limits.output_bytes:
            out, truncated = out[: limits.output_bytes], True
        if len(err) > limits.output_bytes:
            err, truncated = err[: limits.output_bytes], True
        return ExecResult(
            exit_code=proc.returncode,
            timed_out=timed_out,
            cancelled=cancelled,
            wall_seconds=time.monotonic() - (deadline - limits.wall_seconds),
            stdout=out.decode("utf-8", "replace"),
            stderr=err.decode("utf-8", "replace"),
            truncated=truncated,
            profile=self.profile,
            scratch_dir=scratch,
            scratch_files=_scratch_listing(scratch),
            tree_exited=True,  # container removal destroys the tree
        )

    def _kill(self, name: str) -> None:
        subprocess.run(  # noqa: S603 — resolved docker CLI, fixed argv
            [self.docker, "kill", name], capture_output=True, timeout=30, check=False
        )
        self._rm(name)

    def _rm(self, name: str) -> None:
        subprocess.run(  # noqa: S603 — resolved docker CLI, fixed argv
            [self.docker, "rm", "-f", name],
            capture_output=True,
            timeout=30,
            check=False,
        )


def default_backend(*, image: str = "python:3.12-slim") -> ExecutionBackend:
    """Prefer the container backend when a local image exists; fall
    back to the subprocess profile and let the caller read
    ``profile.enforced`` for what is actually protected."""
    if ContainerBackend.available(image):
        return ContainerBackend(image=image)
    return SubprocessBackend()
