"""CS-0802 contracts — model-load validation request/report shapes.

Pure pydantic + stdlib only: the host service and the isolated runner
share these without importing torch. A ``LoadValidationReport`` is the
honest record of *what was actually checked* — structural compatibility
(base/tokenizer/adapter binding), artifact checksums, safetensors
integrity, optional real load + parity inside the pinned container, and
which mode produced the verdict.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


# Serving formats the registry may declare. ``peft-adapter`` is the raw
# trained pair; ``serving-bundle-v1`` is the canonical derived artifact
# (conversion) with its own checksum + parity evaluation (§17.5).
SERVING_FORMATS = ("peft-adapter", "serving-bundle-v1")
ADAPTER_METHODS = ("lora",)
TOKENIZER_KINDS = ("char-v1",)


class BaseIdentity(StrictModel):
    """Registered base-model identity (§17.5 registry record)."""

    base_model_id: str
    architecture: str
    init_seed: int
    base_sha256: str
    license_id: str
    parameter_count: int | None = None


class TokenizerIdentity(StrictModel):
    kind: str
    sha256: str


class AdapterBinding(StrictModel):
    """What the adapter was trained against — recorded at training
    time by CS-0801 (SftOutcome base/tokenizer hashes + architecture
    from the persisted resolved config)."""

    base_sha256: str
    tokenizer_sha256: str
    architecture: str


class AdapterIdentity(StrictModel):
    artifact_id: str | None = None
    sha256: str
    method: str
    config: dict[str, Any] = Field(default_factory=dict)
    base_binding: AdapterBinding


class LoadRequest(StrictModel):
    """What the isolated validator receives (request.json)."""

    schema_name: Literal["model_load_request"] = "model_load_request"
    schema_version: Literal[1] = 1
    base: BaseIdentity
    tokenizer: TokenizerIdentity
    adapter: AdapterIdentity
    serving_format: str
    # file names the host injected alongside request.json.
    files: list[str] = Field(default_factory=list)
    bundle_manifest: dict[str, Any] | None = None


class CompatibilityCheck(StrictModel):
    name: str
    ok: bool
    detail: str = ""


class ParityReport(StrictModel):
    """Conversion parity evaluation — a derived artifact must prove it
    carries the same weights/hashes as the registered pair."""

    evaluated: bool = False
    ok: bool = False
    mode: str = "none"  # stdlib | isolated | none
    checks: list[CompatibilityCheck] = Field(default_factory=list)
    detail: str = ""


class LoadValidationReport(StrictModel):
    """Serving-time compatibility verdict (AT-0802-1). ``compatible``
    only when every *required* check passed; ``mode`` records how the
    verdict was produced — never claims an isolated load that did not
    run."""

    status: Literal["compatible", "incompatible"]
    mode: Literal["stdlib", "isolated", "stdlib+isolated"]
    load_verified: bool = False
    checks: list[CompatibilityCheck] = Field(default_factory=list)
    parity: ParityReport | None = None
    isolation: dict[str, Any] = Field(default_factory=dict)
    detail: str = ""

    def digest(self) -> str:
        return sha256_bytes(canonical_json(self.model_dump(mode="json")).encode("utf-8"))


__all__ = [
    "ADAPTER_METHODS",
    "SERVING_FORMATS",
    "TOKENIZER_KINDS",
    "AdapterBinding",
    "AdapterIdentity",
    "BaseIdentity",
    "CompatibilityCheck",
    "LoadRequest",
    "LoadValidationReport",
    "ParityReport",
    "StrictModel",
    "TokenizerIdentity",
    "canonical_json",
    "sha256_bytes",
]
