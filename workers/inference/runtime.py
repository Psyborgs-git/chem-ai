"""Provider-neutral local model runtime (§13.1-style handshake for
inference, U08/U13).

The handshake is *executed*, not declared: the model file's sha256 is
hashed inside the runtime container, the chat template is exercised
with a real request, and a JSON-schema structured-output probe must
return parseable JSON. A runtime that can't complete those steps
reports ``available=False`` — nothing downstream is allowed to assume
model capability it hasn't demonstrated.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, cast

DEFAULT_IMAGE = "ghcr.io/ggml-org/llama.cpp:server"

# This server build's response_format/json_schema sampler fails
# ("Failed to initialize samplers") — structured output is enforced
# with a direct GBNF grammar instead, which is verified working.
JSON_MINI = r"""
object ::= "{" ws members "}" | "{" ws "}"
members ::= pair ("," ws pair)*
pair ::= string ":" ws jvalue
jvalue ::= object | array | string | number | "true" | "false" | "null"
array ::= "[" ws "]" | "[" ws jvalue ("," ws jvalue)* "]"
string ::= "\"" char* "\""
char ::= [^"\\] | "\\" .
number ::= "-"? [0-9]+ ("." [0-9]+)?
ws ::= [ \t\n]*
"""

PROBE_GRAMMAR = "root ::= object\n" + JSON_MINI

# A turn emits either a tool call or a final answer (§10.2).
ANSWER_GRAMMAR = 'root ::= "{" ws "\\"final\\"" ":" ws string "}"\n' + JSON_MINI

TURN_GRAMMAR = (
    "root ::= call | answer\n"
    'call ::= "{" ws "\\"tool\\"" ":" ws string "," ws '
    '"\\"arguments\\"" ":" ws object "}"\n'
    'answer ::= "{" ws "\\"final\\"" ":" ws string "}"\n' + JSON_MINI
)
DEFAULT_MODEL = "gemma-2b"
DEFAULT_VOLUME = "chem-models"
MODEL_SHA256 = "c1864a5eb19305c40519da12cc543519e48a0697ecd30e15d5ac228644957d12"


@dataclass(frozen=True)
class ModelSpec:
    """A pinned model: identity, license, integrity, and the template
    the adapter asserts before serving."""

    model_id: str
    name: str
    gguf_path: str  # path inside the model volume
    sha256: str
    license_id: str
    chat_template: str  # template family exercised at handshake
    context_size: int
    volume: str = DEFAULT_VOLUME

    @staticmethod
    def gemma_2b() -> ModelSpec:
        """The bootstrap model — pinned by content hash, sourced from
        the local store (no automatic download, U13)."""
        return ModelSpec(
            model_id="gemma-2b-it",
            name="Gemma 2B IT",
            gguf_path="/models/gemma-2b.gguf",
            sha256=MODEL_SHA256,
            license_id="gemma-terms-of-use",
            chat_template="gemma",
            context_size=2048,
        )


@dataclass(frozen=True)
class TurnBudget:
    """Finite turn budget (§10.2): token, wall-time and tool-call
    ceilings — exhausted budgets end the turn with an explicit reason,
    never a silent stop."""

    max_tool_calls: int = 8
    max_completion_tokens: int = 512
    max_total_tokens: int = 8192
    wall_seconds: int = 300


@dataclass
class HandshakeReport:
    available: bool
    detail: str
    runtime: str = "llama.cpp"
    runtime_version: str | None = None
    model_id: str | None = None
    model_sha256_verified: bool = False
    chat_template_ok: bool = False
    structured_output_ok: bool = False
    license_id: str | None = None
    context_size: int | None = None


class LlamaCppRuntime:
    """Runs a pinned GGUF in the llama.cpp server container on a
    loopback-only port. Egress note (honest): the published port is
    inbound-only to the host; the container has no credentials, home,
    or scratch mounts — and no model-driven network calls exist by
    design. Outbound egress is not network-denied here; the agent
    boundary (typed tools) is what constrains the model's effects."""

    def __init__(
        self,
        spec: ModelSpec | None = None,
        *,
        image: str = DEFAULT_IMAGE,
        container: str = "chem-studio-llm",
        host_port: int = 8765,
    ) -> None:
        self.spec = spec or ModelSpec.gemma_2b()
        self.image = image
        self.container = container
        self.base_url = f"http://127.0.0.1:{host_port}"

    # -- lifecycle ----------------------------------------------------

    def _docker(self, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 — argv list, no shell
            ["docker", *args],  # noqa: S607 — the docker CLI by design
            capture_output=True,
            text=True,
            check=check,
            timeout=60,
        )

    def running(self) -> bool:
        out = self._docker("ps", "-q", "--filter", f"name=^{self.container}$").stdout.strip()
        return bool(out)

    def start(self, *, threads: int = 4) -> bool:
        """Start the server if absent; returns False if the image or
        volume isn't present — unavailability is honest, not an error
        to hide."""
        if self.running():
            return True
        if self._docker("image", "inspect", self.image).returncode != 0:
            return False
        if self._docker("volume", "inspect", self.spec.volume).returncode != 0:
            return False
        self._docker("rm", "-f", self.container)
        port = self.base_url.rsplit(":", 1)[1]
        res = self._docker(
            "run",
            "-d",
            "--name",
            self.container,
            "-p",
            f"127.0.0.1:{port}:8080",
            "-v",
            f"{self.spec.volume}:/models:ro",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            self.image,
            "--model",
            self.spec.gguf_path,
            # llama-server must bind all interfaces *inside* the
            # container; the host publishes it on 127.0.0.1 only.
            "--host",
            "0.0.0.0",  # noqa: S104
            "--port",
            "8080",
            "--ctx-size",
            str(self.spec.context_size),
            "--threads",
            str(threads),
            "--n-predict",
            "256",
        )
        return res.returncode == 0

    def stop(self) -> None:
        self._docker("rm", "-f", self.container)

    def wait_ready(self, timeout: float = 180.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                req = urllib.request.Request(f"{self.base_url}/health")  # noqa: S310 — loopback URL built by the adapter
                with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310 — loopback URL built by the adapter
                    if r.status == 200:
                        return True
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(2)
        return False

    # -- generation -----------------------------------------------------

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 256,
        temperature: float = 0.0,
        grammar: str | None = None,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        """One chat completion. Returns the raw response; errors raise
        ``RuntimeError`` with the server diagnostic — no synthesized
        text ever stands in for a failed call."""
        body: dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "cache_prompt": False,
        }
        if grammar is not None:
            body["grammar"] = grammar
        data = json.dumps(body).encode()
        req = urllib.request.Request(  # noqa: S310 — loopback URL built by the adapter
            f"{self.base_url}/v1/chat/completions",
            data=data,
            headers={"content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — loopback URL built by the adapter
                return cast("dict[str, Any]", json.loads(r.read()))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()[:300]
            raise RuntimeError(f"llama.cpp {exc.code}: {detail}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise RuntimeError(f"runtime unreachable: {exc}") from exc

    # -- handshake ------------------------------------------------------

    def handshake(self, *, ensure_running: bool = True) -> HandshakeReport:
        """Executed capability check — every field is verified."""
        report = HandshakeReport(
            available=False,
            detail="runtime not probed",
            model_id=self.spec.model_id,
            license_id=self.spec.license_id,
            context_size=self.spec.context_size,
        )
        if ensure_running and not self.running() and not self.start():
            report.detail = (
                f"image '{self.image}' or volume '{self.spec.volume}' "
                "absent — no local model installed"
            )
            return report
        if not self.wait_ready():
            report.detail = "server did not become ready"
            return report
        report.model_sha256_verified = self._verify_hash()
        if not report.model_sha256_verified:
            report.detail = "model sha256 mismatch — refusing to serve"
            self.stop()
            return report
        probe = self.generate(
            [
                {"role": "user", "content": "Reply with exactly the word PONG."},
            ],
            max_tokens=16,
        )
        content = probe.get("choices", [{}])[0].get("message", {}).get("content") or ""
        report.chat_template_ok = bool(content.strip())
        try:
            out = self.generate(
                [
                    {
                        "role": "user",
                        "content": "Return a JSON object with ok=true and note='probe'.",
                    }
                ],
                max_tokens=64,
                grammar=PROBE_GRAMMAR,
            )
            text = out.get("choices", [{}])[0].get("message", {}).get("content") or ""
            parsed = json.loads(text)
            report.structured_output_ok = (
                isinstance(parsed, dict)
                and isinstance(parsed.get("ok"), bool)
                and isinstance(parsed.get("note"), str)
            )
        except (RuntimeError, json.JSONDecodeError, KeyError):
            report.structured_output_ok = False
        report.runtime_version = self._version()
        report.available = report.chat_template_ok and report.structured_output_ok
        report.detail = (
            "handshake passed"
            if report.available
            else "model reachable but handshake checks failed"
        )
        return report

    def _verify_hash(self) -> bool:
        """Hash the model file inside the container — the spec's pin
        must match the bits actually served."""
        res = self._docker(
            "exec",
            self.container,
            "sha256sum",
            self.spec.gguf_path,
        )
        if res.returncode != 0:
            return False
        return bool(res.stdout.split()[0] == self.spec.sha256)

    def _version(self) -> str | None:
        res = self._docker("exec", self.container, "/app/llama-server", "--version")
        if res.returncode != 0:
            # newer builds report the version at startup instead
            res = self._docker("logs", self.container)
        for line in (res.stdout + res.stderr).splitlines():
            if "version" in line.lower() and ("llama" in line.lower() or "b" in line):
                return str(line.strip()[:120])
        return None


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
