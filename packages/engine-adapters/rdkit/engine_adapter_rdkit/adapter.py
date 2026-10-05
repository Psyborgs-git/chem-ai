"""RDKit adapter over the isolated execution backends (§13.1).

``describe`` ships the worker script + input into scratch, executes in
the backend's profile, and parses the typed result. The exact engine
version comes from the worker's own report — the adapter never
fabricates a version or a descriptor (AT-0404-1/2).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from workers.common.executor import (
    ContainerBackend,
    ExecLimits,
    ExecutionBackend,
    SubprocessBackend,
)

ADAPTER_VERSION = "rdkit-adapter/v1"
IMAGE = "chem-studio-rdkit:2026.3.6"
WORKER = str(Path(__file__).with_name("worker.py"))

MAX_INPUT_CHARS = 8192


@dataclass
class EngineInfo:
    engine_id: str
    available: bool
    version: str | None
    adapter_version: str
    methods: list[str]
    detail: str = ""


@dataclass
class StructuralResult:
    """A successful structural check — evidence class ``descriptor``,
    not lab proof (§12.1)."""

    ok: bool
    canonical_smiles: str | None = None
    inchi_key: str | None = None
    formula: str | None = None
    descriptors: dict[str, Any] = field(default_factory=dict)
    engine_id: str = "rdkit"
    engine_version: str | None = None
    adapter_version: str = ADAPTER_VERSION
    method: str = "rdkit-descriptors/v1"
    evidence_type: str = "descriptor"


@dataclass
class EngineError:
    code: str
    message: str
    stage: str
    engine_id: str = "rdkit"
    adapter_version: str = ADAPTER_VERSION


class RDKitAdapter:
    """§13.1 contract: capability discovery, input validation,
    submission, status, cancellation (backend-owned), typed parsing."""

    def __init__(self, backend: ExecutionBackend | None = None) -> None:
        self._backend = backend

    def capability(self) -> EngineInfo:
        """Available only when a real rdkit image exists locally —
        never simulated."""
        if ContainerBackend.available(IMAGE):
            return EngineInfo(
                engine_id="rdkit",
                available=True,
                version=self._version_probe(),
                adapter_version=ADAPTER_VERSION,
                methods=["rdkit-descriptors/v1"],
                detail=f"container image {IMAGE}",
            )
        if self._native_available():
            return EngineInfo(
                engine_id="rdkit",
                available=True,
                version=self._native_version(),
                adapter_version=ADAPTER_VERSION,
                methods=["rdkit-descriptors/v1"],
                detail="native rdkit (restricted-subprocess profile)",
            )
        return EngineInfo(
            engine_id="rdkit",
            available=False,
            version=None,
            adapter_version=ADAPTER_VERSION,
            methods=["rdkit-descriptors/v1"],
            detail=f"image {IMAGE} not present; host has no native rdkit wheel",
        )

    def describe(
        self,
        *,
        smiles: str | None = None,
        molfile: str | None = None,
        cancel: Any = None,
    ) -> StructuralResult | EngineError:
        """Parse + sanitize + describe a structure.

        Failures are typed (EMPTY_INPUT / PARSE_FAILED /
        SANITIZE_FAILED / ENGINE_UNSUPPORTED_INPUT / INTERNAL /
        ENGINE_UNAVAILABLE) — a missing descriptor is never invented.
        """
        backend = self._backend
        if backend is None:
            backend = self._default_backend()
            if backend is None:
                return EngineError(
                    code="ENGINE_UNAVAILABLE",
                    message=(
                        f"container image {IMAGE} not present and no "
                        "native rdkit on this host (platform matrix)"
                    ),
                    stage="init",
                )
        payload: dict[str, Any] = {}
        if smiles is not None:
            payload["smiles"] = smiles
        if molfile is not None:
            payload["molfile"] = molfile
        inputs = {
            "worker.py": Path(WORKER).read_bytes(),
            "input.json": json.dumps(payload).encode(),
        }
        res = backend.run(
            # The image's ENTRYPOINT is python — argv omits it.
            ["worker.py", "input.json"]
            if isinstance(backend, ContainerBackend)
            else [self._python(), "worker.py", "input.json"],
            inputs=inputs,
            limits=ExecLimits(wall_seconds=60, cpu_seconds=30),
            cancel=cancel,
        )
        out = res.json_stdout()
        if out is None:
            return EngineError(
                code="INTERNAL",
                message=f"worker produced no typed result: {res.stderr[-300:]}",
                stage="describe",
            )
        if not out.get("ok"):
            err = out.get("error") or {}
            return EngineError(
                code=err.get("code", "INTERNAL"),
                message=err.get("message", "unknown engine failure"),
                stage=err.get("stage", "describe"),
            )
        structure = out["structure"]
        return StructuralResult(
            ok=True,
            canonical_smiles=structure["canonical_smiles"],
            inchi_key=structure.get("inchi_key"),
            formula=structure.get("formula"),
            descriptors=out["descriptors"],
            engine_version=out["engine"]["version"],
            method=out.get("method", "rdkit-descriptors/v1"),
        )

    def _version_probe(self) -> str | None:
        """Ask the image for its real version — the recorded version is
        always the engine's own report."""
        backend = ContainerBackend(image=IMAGE)
        probe = (
            "from rdkit import rdBase; import json; print(json.dumps({'v': rdBase.rdkitVersion}))"
        )
        res = backend.run(
            ["-c", probe],
            inputs={},
            limits=ExecLimits(wall_seconds=30, cpu_seconds=10),
        )
        out = res.json_stdout()
        return out["v"] if out and "v" in out else None

    @staticmethod
    def _native_available() -> bool:
        try:
            import rdkit  # noqa: F401
        except ImportError:
            return False
        return True

    @staticmethod
    def _native_version() -> str | None:
        try:
            from rdkit import rdBase

            return str(rdBase.rdkitVersion)
        except ImportError:
            return None

    def _default_backend(self) -> ExecutionBackend | None:
        """Container first (strong profile), native restricted
        subprocess second — whichever is real on this host."""
        if ContainerBackend.available(IMAGE):
            return ContainerBackend(image=IMAGE)
        if self._native_available():
            return SubprocessBackend()
        return None

    @staticmethod
    def _python() -> str:
        import sys

        return sys.executable
