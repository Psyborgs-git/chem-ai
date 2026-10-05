"""CS-0802 unit tests — model-load contracts + stdlib verification.

Pure-stdlib: no torch, no docker. The same verify module runs inside
the pinned container, so these exercise the exact structural rules a
serving request enforces (AT-0802-1).
"""

from __future__ import annotations

import json
import struct

import pytest
from workers.inference.model_loading.contracts import (
    AdapterBinding,
    AdapterIdentity,
    BaseIdentity,
    LoadRequest,
    TokenizerIdentity,
    canonical_json,
    sha256_bytes,
)
from workers.inference.model_loading.verify import (
    BUNDLE_FORMAT,
    build_bundle,
    bundle_adapter_bytes,
    bundle_parity,
    checksum_check,
    parse_bundle,
    safetensors_check,
    safetensors_header,
    structural_checks,
    validate_structural,
)


def _safetensors(payload: bytes = b"\x00" * 4) -> bytes:
    header = json.dumps(
        {"w": {"dtype": "F32", "shape": [1], "data_offsets": [0, len(payload)]}}
    ).encode()
    return struct.pack("<Q", len(header)) + header + payload


def _base() -> BaseIdentity:
    return BaseIdentity(
        base_model_id="pico-gpt-char-v1",
        architecture="pico-gpt-v1",
        init_seed=0,
        base_sha256="a" * 64,
        license_id="fixture-internal",
    )


def _tokenizer() -> TokenizerIdentity:
    return TokenizerIdentity(kind="char-v1", sha256="b" * 64)


def _adapter(*, base_sha: str = "a" * 64, tok_sha: str = "b" * 64) -> AdapterIdentity:
    return AdapterIdentity(
        sha256="d" * 64,
        method="lora",
        config={"rank": 8},
        base_binding=AdapterBinding(
            base_sha256=base_sha,
            tokenizer_sha256=tok_sha,
            architecture="pico-gpt-v1",
        ),
    )


class TestSafetensorsHeader:
    def test_parses_valid_header(self) -> None:
        header = safetensors_header(_safetensors())
        assert header["w"]["dtype"] == "F32"
        assert header["w"]["shape"] == [1]

    def test_rejects_truncated(self) -> None:
        with pytest.raises(ValueError):
            safetensors_header(b"\x01\x02")

    def test_rejects_garbage_header(self) -> None:
        bad = struct.pack("<Q", 10) + b"not-json!!" + b"xxxx"
        with pytest.raises(ValueError):
            safetensors_header(bad)

    def test_check_flags_missing_tensors(self) -> None:
        header = json.dumps({"__metadata__": {}}).encode()
        blob = struct.pack("<Q", len(header)) + header
        assert not safetensors_check("a", blob).ok


class TestStructuralChecks:
    def test_matching_binding_passes(self) -> None:
        checks = structural_checks(_base(), _tokenizer(), _adapter())
        assert all(c.ok for c in checks)

    def test_wrong_base_hash_fails(self) -> None:
        checks = structural_checks(_base(), _tokenizer(), _adapter(base_sha="f" * 64))
        failed = {c.name for c in checks if not c.ok}
        assert "adapter_base_hash" in failed

    def test_wrong_tokenizer_hash_fails(self) -> None:
        checks = structural_checks(_base(), _tokenizer(), _adapter(tok_sha="e" * 64))
        failed = {c.name for c in checks if not c.ok}
        assert "adapter_tokenizer_hash" in failed

    def test_unknown_method_fails(self) -> None:
        adapter = _adapter().model_copy(update={"method": "unknown-adapter"})
        failed = {c.name for c in structural_checks(_base(), _tokenizer(), adapter) if not c.ok}
        assert "adapter_method_known" in failed


class TestChecksum:
    def test_checksum_roundtrip(self) -> None:
        data = b"weights"
        ok = checksum_check("adapter", sha256_bytes(data), data)
        assert ok.ok
        bad = checksum_check("adapter", "0" * 64, data)
        assert not bad.ok


class TestBundle:
    def test_roundtrip_and_parity(self) -> None:
        adapter_bytes = _safetensors()
        adapter = _adapter().model_copy(update={"sha256": sha256_bytes(adapter_bytes)})
        blob = build_bundle(
            release_id="r1",
            base=_base(),
            tokenizer=_tokenizer(),
            adapter=adapter,
            adapter_bytes=adapter_bytes,
            conversion_steps=[{"step": "embed"}],
        )
        doc = parse_bundle(blob)
        assert doc["schema"] == BUNDLE_FORMAT
        assert bundle_adapter_bytes(doc) == adapter_bytes
        parity = bundle_parity(blob, base=_base(), tokenizer=_tokenizer(), adapter=adapter)
        assert parity.ok
        assert all(c.ok for c in parity.checks)

    def test_parity_fails_on_wrong_declared_adapter(self) -> None:
        adapter_bytes = _safetensors()
        adapter = _adapter()  # declared sha doesn't match payload
        blob = build_bundle(
            release_id="r1",
            base=_base(),
            tokenizer=_tokenizer(),
            adapter=adapter,
            adapter_bytes=adapter_bytes,
            conversion_steps=[],
        )
        parity = bundle_parity(blob, base=_base(), tokenizer=_tokenizer(), adapter=adapter)
        assert not parity.ok

    def test_parity_fails_on_tampered_blob(self) -> None:
        adapter_bytes = _safetensors()
        adapter = _adapter().model_copy(update={"sha256": sha256_bytes(adapter_bytes)})
        blob = build_bundle(
            release_id="r1",
            base=_base(),
            tokenizer=_tokenizer(),
            adapter=adapter,
            adapter_bytes=adapter_bytes,
            conversion_steps=[],
        )
        tampered = blob[:-20] + b"0" * 20
        parity = bundle_parity(tampered, base=_base(), tokenizer=_tokenizer(), adapter=adapter)
        assert not parity.ok


class TestValidateStructural:
    def test_compatible_end_to_end(self) -> None:
        adapter_bytes = _safetensors()
        adapter = _adapter().model_copy(update={"sha256": sha256_bytes(adapter_bytes)})
        report = validate_structural(
            base=_base(),
            tokenizer=_tokenizer(),
            adapter=adapter,
            serving_format="peft-adapter",
            adapter_bytes=adapter_bytes,
        )
        assert report.status == "compatible"
        assert report.mode == "stdlib"
        assert not report.load_verified  # honest — no isolated load ran

    def test_incompatible_pair_rejected(self) -> None:
        adapter_bytes = _safetensors()
        adapter = _adapter(base_sha="f" * 64).model_copy(
            update={"sha256": sha256_bytes(adapter_bytes)}
        )
        report = validate_structural(
            base=_base(),
            tokenizer=_tokenizer(),
            adapter=adapter,
            serving_format="peft-adapter",
            adapter_bytes=adapter_bytes,
        )
        assert report.status == "incompatible"

    def test_request_contract_roundtrip(self) -> None:
        request = LoadRequest(
            base=_base(),
            tokenizer=_tokenizer(),
            adapter=_adapter(),
            serving_format="peft-adapter",
        )
        doc = json.loads(canonical_json(request.model_dump(mode="json")))
        reparsed = LoadRequest.model_validate(doc)
        assert reparsed == request
