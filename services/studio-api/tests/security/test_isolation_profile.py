"""CS-0403 security test — the protected profile denies and records.

AT-0403-1  a process attempts home-directory access or network egress
           in the protected profile → access is denied and recorded.

Two honest paths:

* Container backend (preferred): kernel-level `--network none` plus a
  read-only root filesystem — both probes are *physically* denied.
* Subprocess backend (fallback): HOME/TMPDIR are redirected into
  scratch (the real home is unreachable as a *path*), while network
  egress is NOT denied — the profile reports `network_denied: False`
  rather than claiming a control it cannot apply (§13.3). A run that
  requires network denial under this backend is refused up front.
"""

from __future__ import annotations

import socket
import sys
import threading
import time

import pytest
from workers.common.executor import (
    ContainerBackend,
    ExecLimits,
    SubprocessBackend,
)

pytestmark = pytest.mark.security

PROBE = r"""
import json, os, socket, sys
out = {"home_env": os.environ.get("HOME", "")}
try:
    # The user's real home: outside scratch by construction.
    open(os.path.expanduser("~/.ssh/id_rsa")).read()
    out["home_secret"] = "read"
except Exception as e:
    out["home_secret"] = "denied:" + type(e).__name__
try:
    out["home_write"] = "wrote" if open("/work/_probe", "w") else "?"
    out["home_write"] = "wrote"
except Exception as e:
    out["home_write"] = "denied:" + type(e).__name__
try:
    out["etc_write"] = "wrote" if open("/etc/_probe", "w") else "?"
    out["etc_write"] = "wrote"
except Exception as e:
    out["etc_write"] = "denied:" + type(e).__name__
try:
    s = socket.create_connection(("127.0.0.1", PROBE_PORT), timeout=2)
    s.close()
    out["network"] = "connected"
except Exception as e:
    out["network"] = "denied:" + type(e).__name__
print(json.dumps(out))
"""


def _listener() -> tuple[int, socket.socket]:
    """A live local listener — 'connected' would mean egress worked."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    return srv.getsockname()[1], srv


def _run_probe(backend, port: int):
    script = PROBE.replace("PROBE_PORT", str(port))
    return backend.run(
        [sys.executable, "-c", script]
        if not isinstance(backend, ContainerBackend)
        else ["python", "-c", script],
        inputs={},
        limits=ExecLimits(wall_seconds=30),
    )


def test_container_profile_denies_and_records() -> None:
    """Real enforcement: network is kernel-denied, the host filesystem
    (including any home) is not even mounted — the probe records the
    denials."""
    if not ContainerBackend.available():
        pytest.skip("container backend unavailable on this host")
    port, srv = _listener()

    def _accept() -> None:
        try:
            srv.accept()[0].close()
        except (OSError, IndexError):
            pass

    threading.Thread(target=_accept, daemon=True).start()
    backend = ContainerBackend()
    assert backend.profile.enforces("network_denied")
    assert backend.profile.enforces("filesystem_read_only")
    assert backend.profile.enforces("home_isolated")
    res = _run_probe(backend, port)
    srv.close()
    probe = res.json_stdout()
    assert probe is not None, res.stderr[-400:]
    assert probe["network"].startswith("denied"), probe
    assert probe["home_secret"].startswith("denied"), probe
    assert probe["etc_write"].startswith("denied"), probe
    assert probe["home_env"] == "/work"  # HOME is the scratch mount


def test_subprocess_profile_is_honest_about_network() -> None:
    """The subprocess backend CANNOT deny egress — it reports the gap,
    scrubs the environment, and still confines HOME to scratch. What it
    cannot enforce it never claims."""
    backend = SubprocessBackend()
    assert backend.profile.enforces("network_denied") is False
    assert backend.profile.enforces("env_scrubbed") is True
    port, srv = _listener()
    accepted: list[bool] = []

    def accept() -> None:
        try:
            srv.accept()[0].close()
            accepted.append(True)
        except OSError:
            pass

    threading.Thread(target=accept, daemon=True).start()
    res = _run_probe(backend, port)
    time.sleep(0.2)
    srv.close()
    probe = res.json_stdout()
    assert probe is not None, res.stderr[-400:]
    # HOME resolves inside scratch — the real home is unreachable by path.
    assert "run-" in probe["home_env"]
    assert probe["home_secret"].startswith("denied")  # FileNotFoundError
    # Egress is *not* claimed: the connect genuinely succeeds, and the
    # profile says so — nothing asserts a control that is absent.
    assert probe["network"] == "connected" or accepted


def test_subprocess_env_scrub_removes_credentials() -> None:
    """No inherited environment leaks into the child — credentials and
    proxy variables the parent holds are never forwarded."""
    backend = SubprocessBackend()
    res = backend.run(
        [
            sys.executable,
            "-c",
            "import json,os;print(json.dumps({'env': sorted(os.environ.keys())}))",
        ],
        inputs={},
        limits=ExecLimits(wall_seconds=15),
    )
    out = res.json_stdout()
    assert out is not None
    keys = out["env"]
    leaked = [
        k
        for k in keys
        if any(t in k.upper() for t in ("KEY", "SECRET", "TOKEN", "PROXY", "AWS", "SSH", "HOME_"))
    ]
    assert leaked == []
    # __CF_USER_TEXT_ENCODING is injected by macOS into every process —
    # a platform encoding hint, not a credential.
    assert set(keys) <= {
        "HOME",
        "TMPDIR",
        "PATH",
        "LC_ALL",
        "PYTHONDONTWRITEBYTECODE",
        "__CF_USER_TEXT_ENCODING",
    }
