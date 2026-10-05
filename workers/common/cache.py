"""Content-addressed run cache keys (§13.5).

A cache key covers the *full* scientific context: canonical input,
chemical/context representation, engine/model/method/parameter
versions, precision, seed, adapter version, and the policy
applicability version — plus the workspace scope. Changing any
dimension (a temperature, a lot-dependent descriptor, a formula
basis, a policy version) must produce a different key, so an
incompatible old result can never be served (AT-0403-3).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

KEY_VERSION = "run-cache/v1"


def canonical_json(value: Any) -> str:
    """Deterministic serialization — sorted keys, tight separators —
    so a digest is stable regardless of dict ordering."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def build_context(
    *,
    canonical_input: dict[str, Any],
    chemical_context: dict[str, Any],
    engine_id: str,
    engine_version: str,
    adapter_version: str,
    method: str,
    parameters: dict[str, Any],
    precision: str | None,
    seed: int | None,
    policy_version: str,
    scope: str,
) -> dict[str, Any]:
    """The complete address context — every field is part of the key."""
    return {
        "key_version": KEY_VERSION,
        "scope": scope,
        "canonical_input": canonical_input,
        "chemical_context": chemical_context,
        "engine_id": engine_id,
        "engine_version": engine_version,
        "adapter_version": adapter_version,
        "method": method,
        "parameters": parameters,
        "precision": precision,
        "seed": seed,
        "policy_version": policy_version,
    }


def cache_key(context: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(context).encode()).hexdigest()


def lookup_key(**kwargs: Any) -> str:
    """Convenience: build_context + cache_key in one call."""
    return cache_key(build_context(**kwargs))
