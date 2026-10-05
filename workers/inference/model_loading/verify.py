"""Stdlib-only model verification (CS-0802).

The structural half of compatibility validation needs no torch: a
safetensors file header is length-prefixed JSON, the adapter's recorded
base/tokenizer binding is plain data, and every artifact checksum is
sha256. This module is importable on the host AND inside the pinned
container — identical logic, never a weaker substitute.

``serving-bundle-v1`` is the derived conversion format: a canonical
JSON document embedding the base/tokenizer/adapter identities plus the
adapter payload (base64). Its own checksum is registered, and parity is
evaluated by re-parsing it — embedded digests must equal the registry's
and the payload must re-hash to the adapter sha256 (§17.5).
"""

from __future__ import annotations

import base64
import binascii
import json
import struct
from typing import Any

from workers.inference.model_loading.contracts import (
    ADAPTER_METHODS,
    SERVING_FORMATS,
    TOKENIZER_KINDS,
    AdapterIdentity,
    BaseIdentity,
    CompatibilityCheck,
    LoadValidationReport,
    ParityReport,
    TokenizerIdentity,
    canonical_json,
    sha256_bytes,
)

BUNDLE_FORMAT = "serving-bundle-v1"

_MAX_SAFETENSORS_HEADER = 64 * 1024**2


def safetensors_header(data: bytes) -> dict[str, Any]:
    """Parse a safetensors header — the first 8 bytes are a little-endian
    u64 header length followed by JSON. Raises ValueError on malformed
    input; callers convert that into a failed check, never a crash."""
    if len(data) < 8:
        raise ValueError("truncated safetensors file")
    (header_len,) = struct.unpack("<Q", data[:8])
    if header_len <= 0 or header_len > _MAX_SAFETENSORS_HEADER:
        raise ValueError(f"implausible safetensors header length {header_len}")
    if len(data) < 8 + header_len:
        raise ValueError("safetensors file shorter than its header")
    header = json.loads(data[8 : 8 + header_len].decode("utf-8"))
    if not isinstance(header, dict):
        raise ValueError("safetensors header is not a JSON object")
    return header


def structural_checks(
    base: BaseIdentity, tokenizer: TokenizerIdentity, adapter: AdapterIdentity
) -> list[CompatibilityCheck]:
    """The AT-0802-1 structural checks: the adapter's recorded training
    binding must name exactly this base + tokenizer + architecture."""
    binding = adapter.base_binding
    checks = [
        CompatibilityCheck(
            name="adapter_base_hash",
            ok=binding.base_sha256 == base.base_sha256,
            detail=(
                "adapter trained on declared base"
                if binding.base_sha256 == base.base_sha256
                else f"adapter bound to base {binding.base_sha256[:12]}… "
                f"but registered base is {base.base_sha256[:12]}…"
            ),
        ),
        CompatibilityCheck(
            name="adapter_tokenizer_hash",
            ok=binding.tokenizer_sha256 == tokenizer.sha256,
            detail=(
                "adapter trained with declared tokenizer"
                if binding.tokenizer_sha256 == tokenizer.sha256
                else "adapter bound to a different tokenizer digest"
            ),
        ),
        CompatibilityCheck(
            name="architecture_match",
            ok=binding.architecture == base.architecture,
            detail=(
                f"architectures agree ({base.architecture})"
                if binding.architecture == base.architecture
                else f"adapter bound to {binding.architecture}, "
                f"registered base is {base.architecture}"
            ),
        ),
        CompatibilityCheck(
            name="adapter_method_known",
            ok=adapter.method in ADAPTER_METHODS,
            detail=f"method={adapter.method}",
        ),
        CompatibilityCheck(
            name="tokenizer_kind_known",
            ok=tokenizer.kind in TOKENIZER_KINDS,
            detail=f"kind={tokenizer.kind}",
        ),
    ]
    return checks


def checksum_check(name: str, expected_sha256: str, data: bytes) -> CompatibilityCheck:
    actual = sha256_bytes(data)
    return CompatibilityCheck(
        name=name,
        ok=actual == expected_sha256,
        detail=(
            f"{name} sha256 verified"
            if actual == expected_sha256
            else f"{name} sha256 {actual[:12]}… != declared {expected_sha256[:12]}…"
        ),
    )


def safetensors_check(name: str, data: bytes) -> CompatibilityCheck:
    try:
        header = safetensors_header(data)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return CompatibilityCheck(
            name=name, ok=False, detail=f"malformed safetensors: {exc}"
        )
    tensors = [k for k in header if k != "__metadata__"]
    return CompatibilityCheck(
        name=name,
        ok=bool(tensors),
        detail=f"{len(tensors)} tensors declared",
    )


# ------------------------------------------------------------------ bundle


def build_bundle(
    *,
    release_id: str,
    base: BaseIdentity,
    tokenizer: TokenizerIdentity,
    adapter: AdapterIdentity,
    adapter_bytes: bytes,
    conversion_steps: list[dict[str, Any]],
) -> bytes:
    """Derive the ``serving-bundle-v1`` conversion artifact — canonical
    JSON so its sha256 is stable; the adapter payload is embedded so the
    bundle is self-contained for the isolated loader."""
    manifest = {
        "schema": BUNDLE_FORMAT,
        "releaseId": release_id,
        "base": base.model_dump(mode="json"),
        "tokenizer": tokenizer.model_dump(mode="json"),
        "adapter": adapter.model_dump(mode="json"),
        "conversionSteps": conversion_steps,
        "payloadSha256": sha256_bytes(adapter_bytes),
        "payloadB64": base64.b64encode(adapter_bytes).decode("ascii"),
    }
    return canonical_json(manifest).encode("utf-8")


def parse_bundle(data: bytes) -> dict[str, Any]:
    doc = json.loads(data.decode("utf-8"))
    if not isinstance(doc, dict) or doc.get("schema") != BUNDLE_FORMAT:
        raise ValueError("not a serving-bundle-v1 document")
    payload = doc.get("payloadB64")
    if not isinstance(payload, str):
        raise ValueError("bundle missing payloadB64")
    return doc


def bundle_adapter_bytes(doc: dict[str, Any]) -> bytes:
    return base64.b64decode(doc["payloadB64"].encode("ascii"))


def bundle_parity(
    bundle_bytes: bytes,
    *,
    base: BaseIdentity,
    tokenizer: TokenizerIdentity,
    adapter: AdapterIdentity,
) -> ParityReport:
    """Parity evaluation for a derived conversion artifact: the bundle's
    embedded identities must equal the registered ones and its payload
    must re-hash to the registered adapter sha256."""
    checks: list[CompatibilityCheck] = []
    try:
        doc = parse_bundle(bundle_bytes)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error) as exc:
        return ParityReport(
            evaluated=True,
            ok=False,
            mode="stdlib",
            checks=[CompatibilityCheck(name="bundle_parse", ok=False, detail=str(exc))],
            detail="conversion artifact unreadable",
        )
    embedded_base = doc.get("base") or {}
    embedded_tok = doc.get("tokenizer") or {}
    embedded_adapter = doc.get("adapter") or {}
    checks.append(
        CompatibilityCheck(
            name="bundle_base_digest",
            ok=embedded_base.get("base_sha256") == base.base_sha256,
            detail="bundle base digest parity",
        )
    )
    checks.append(
        CompatibilityCheck(
            name="bundle_tokenizer_digest",
            ok=embedded_tok.get("sha256") == tokenizer.sha256,
            detail="bundle tokenizer digest parity",
        )
    )
    checks.append(
        CompatibilityCheck(
            name="bundle_adapter_digest",
            ok=embedded_adapter.get("sha256") == adapter.sha256,
            detail="bundle adapter digest parity",
        )
    )
    try:
        payload = bundle_adapter_bytes(doc)
    except (binascii.Error, KeyError) as exc:
        payload = b""
        checks.append(
            CompatibilityCheck(name="bundle_payload", ok=False, detail=f"payload unreadable: {exc}")
        )
    if payload:
        checks.append(checksum_check("bundle_payload_sha256", adapter.sha256, payload))
        checks.append(
            CompatibilityCheck(
                name="bundle_declared_payload",
                ok=doc.get("payloadSha256") == sha256_bytes(payload),
                detail="payload sha matches bundle's own manifest",
            )
        )
    ok = all(c.ok for c in checks)
    return ParityReport(
        evaluated=True,
        ok=ok,
        mode="stdlib",
        checks=checks,
        detail="parity verified" if ok else "parity failed",
    )


# ------------------------------------------------------------------ report


def validate_structural(
    *,
    base: BaseIdentity,
    tokenizer: TokenizerIdentity,
    adapter: AdapterIdentity,
    serving_format: str,
    adapter_bytes: bytes | None = None,
    conversions: list[dict[str, Any]] | None = None,
    conversion_blobs: dict[str, bytes] | None = None,
) -> LoadValidationReport:
    """Full stdlib validation — structural binding + checksums +
    safetensors integrity + conversion parity. No model is loaded here;
    ``load_verified`` stays False until the isolated runner proves it."""
    checks = structural_checks(base, tokenizer, adapter)
    checks.append(
        CompatibilityCheck(
            name="serving_format_known",
            ok=serving_format in SERVING_FORMATS,
            detail=f"format={serving_format}",
        )
    )
    if adapter_bytes is not None:
        checks.append(checksum_check("adapter_checksum", adapter.sha256, adapter_bytes))
        checks.append(safetensors_check("adapter_safetensors", adapter_bytes))
    parity: ParityReport | None = None
    for conversion in conversions or []:
        blob = (conversion_blobs or {}).get(str(conversion.get("artifactId") or ""))
        if blob is None:
            sub = ParityReport(
                evaluated=True,
                ok=False,
                mode="stdlib",
                checks=[
                    CompatibilityCheck(
                        name="conversion_artifact", ok=False, detail="artifact bytes missing"
                    )
                ],
                detail="conversion artifact missing",
            )
        else:
            expected = str(conversion.get("checksum") or "")
            sum_ok = checksum_check("conversion_checksum", expected, blob)
            sub = bundle_parity(blob, base=base, tokenizer=tokenizer, adapter=adapter)
            sub = ParityReport(
                evaluated=True,
                ok=sum_ok.ok and sub.ok,
                mode=sub.mode,
                checks=[sum_ok, *sub.checks],
                detail=sub.detail,
            )
        parity = sub if parity is None else ParityReport(
            evaluated=True,
            ok=parity.ok and sub.ok,
            mode="stdlib",
            checks=[*parity.checks, *sub.checks],
            detail="all conversions parity-checked" if parity.ok and sub.ok else "parity failed",
        )
    ok = all(c.ok for c in checks) and (parity.ok if parity is not None else True)
    return LoadValidationReport(
        status="compatible" if ok else "incompatible",
        mode="stdlib",
        load_verified=False,
        checks=checks,
        parity=parity,
        detail="structural validation passed" if ok else "structural validation failed",
    )
