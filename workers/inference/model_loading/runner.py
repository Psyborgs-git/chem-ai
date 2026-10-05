"""In-container model load validator (CS-0802).

Runs inside the pinned ``chem-studio-model-load`` image (torch CPU +
peft + safetensors, ``--network none``, read-only root). Reads
``request.json`` plus the declared artifact files, then performs a REAL
load: the base is reconstructed from its registered (architecture,
init_seed), the adapter bytes are parsed and applied, and a fixed probe
forward pass produces an output digest. For a converted serving bundle
the payload is loaded through the bundle path and its probe output must
be identical — that is the parity evaluation, executed, not declared.

stdout carries exactly one JSON document — the ``LoadValidationReport``
payload plus ``probe`` digests. Errors are sanitized ``{code,message}``
pairs; tracebacks never leave the container (artifact bytes are
confidential, §17.5).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from workers.inference.model_loading.contracts import (
    CompatibilityCheck,
    LoadRequest,
    LoadValidationReport,
)
from workers.inference.model_loading.verify import (
    bundle_adapter_bytes,
    parse_bundle,
    validate_structural,
)

_MAX_REQUEST = 4 * 1024 * 1024

# Fixed probe input — deterministic across loads; the output digest is
# what parity compares. Never derived from dataset bytes.
_PROBE_IDS = list(range(0, 48))


def _fail(code: str, message: str) -> None:
    print(json.dumps({"error": {"code": code, "message": message}}))
    sys.exit(2)


def _load_adapter_weights(adapter_bytes: bytes) -> Any:
    import tempfile

    from safetensors.torch import load_file

    # safetensors' torch loader wants a path — the scratch dir is the
    # only writable mount; keep the temp file there.
    with tempfile.NamedTemporaryFile(
        suffix=".safetensors", dir=".", delete=False
    ) as tmp:
        tmp.write(adapter_bytes)
        tmp_path = tmp.name
    try:
        return load_file(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _build_model(
    request: LoadRequest, adapter_bytes: bytes
) -> tuple[Any, str, list[CompatibilityCheck]]:
    """Reconstruct base+adapter inside the container and load the real
    weights. Returns (model, base_sha256_measured, extra_checks)."""
    import torch
    from peft import LoraConfig, get_peft_model, set_peft_model_state_dict

    from engine_adapter_sft.contracts import BASE_ARCHITECTURES
    from engine_adapter_sft.pico import PicoGPT, state_dict_sha256

    checks: list[CompatibilityCheck] = []
    base = request.base
    arch = BASE_ARCHITECTURES.get(base.architecture)
    if arch is None:
        raise ValueError(f"unknown architecture {base.architecture!r}")
    torch.manual_seed(int(base.init_seed))
    model = PicoGPT(
        vocab_size=int(arch["vocab_size"]),
        n_embd=int(arch["n_embd"]),
        n_head=int(arch["n_head"]),
        n_layer=int(arch["n_layer"]),
        block_size=int(arch["block_size"]),
        tie_weights=bool(arch["tie_weights"]),
    )
    measured = state_dict_sha256(model, sorted(n for n, _ in model.named_parameters()))
    checks.append(
        CompatibilityCheck(
            name="isolated_base_sha256",
            ok=measured == base.base_sha256,
            detail=(
                "reconstructed base matches registered hash"
                if measured == base.base_sha256
                else f"reconstructed base sha {measured[:12]}… != registered"
            ),
        )
    )
    cfg = request.adapter.config or {}
    lora = LoraConfig(
        r=int(cfg.get("rank", 8)),
        lora_alpha=int(cfg.get("alpha", 16)),
        lora_dropout=float(cfg.get("dropout", 0.0)),
        target_modules=list(cfg.get("target_modules") or ["c_attn", "c_proj"]),
        bias="none",
        task_type="CAUSAL_LM",
    )
    peft_model = get_peft_model(model, lora)
    adapter_state = _load_adapter_weights(adapter_bytes)
    set_peft_model_state_dict(peft_model, adapter_state, adapter_name="default")
    peft_model.eval()
    return peft_model, measured, checks


def _probe_digest(model: Any, request: LoadRequest) -> str:
    """Deterministic forward probe — the digest proves the loaded
    weights actually run, not merely parsed."""
    import torch

    from engine_adapter_sft.contracts import BASE_ARCHITECTURES
    from workers.inference.model_loading.contracts import sha256_bytes

    arch = BASE_ARCHITECTURES[request.base.architecture]
    ids = _PROBE_IDS[: int(arch["block_size"])]
    with torch.no_grad():
        logits, _ = model(input_ids=torch.tensor([ids], dtype=torch.long))
    return sha256_bytes(logits.float().numpy().tobytes())


def run(request: LoadRequest, workdir: Path) -> LoadValidationReport:
    adapter_path = workdir / "adapter.safetensors"
    adapter_bytes = adapter_path.read_bytes() if adapter_path.is_file() else None
    bundle_path = workdir / "bundle.json"
    bundle_bytes = bundle_path.read_bytes() if bundle_path.is_file() else None

    report = validate_structural(
        base=request.base,
        tokenizer=request.tokenizer,
        adapter=request.adapter,
        serving_format=request.serving_format,
        adapter_bytes=adapter_bytes,
    )
    checks = list(report.checks)

    # tokenizer digest recomputed inside the container
    from engine_adapter_sft.pico import CharTokenizer

    tok_measured = CharTokenizer().digest()
    checks.append(
        CompatibilityCheck(
            name="isolated_tokenizer_sha256",
            ok=tok_measured == request.tokenizer.sha256,
            detail=(
                "tokenizer digest verified in runtime"
                if tok_measured == request.tokenizer.sha256
                else "tokenizer digest mismatch in runtime"
            ),
        )
    )

    load_ok = False
    probe_digest: str | None = None
    if adapter_bytes is not None and all(c.ok for c in checks):
        try:
            model, _base_sha, extra = _build_model(request, adapter_bytes)
            checks.extend(extra)
            if all(c.ok for c in checks):
                probe_digest = _probe_digest(model, request)
                load_ok = True
                checks.append(
                    CompatibilityCheck(
                        name="isolated_load",
                        ok=True,
                        detail=f"base+adapter loaded; probe digest {probe_digest[:12]}…",
                    )
                )
        except Exception as exc:  # sanitized below — no internals leak
            checks.append(
                CompatibilityCheck(
                    name="isolated_load",
                    ok=False,
                    detail=f"load failed: {type(exc).__name__}",
                )
            )

    parity = report.parity
    if bundle_bytes is not None:
        from workers.inference.model_loading.verify import bundle_parity

        parity = bundle_parity(
            bundle_bytes, base=request.base, tokenizer=request.tokenizer, adapter=request.adapter
        )
        iso_checks: list[CompatibilityCheck] = []
        if load_ok and parity.ok:
            try:
                doc = parse_bundle(bundle_bytes)
                payload = bundle_adapter_bytes(doc)
                bundle_model, _s, extra = _build_model(request, payload)
                iso_checks.extend(extra)
                bundle_probe = _probe_digest(bundle_model, request)
                iso_checks.append(
                    CompatibilityCheck(
                        name="isolated_parity",
                        ok=bundle_probe == probe_digest,
                        detail=(
                            "bundle payload produces identical probe output"
                            if bundle_probe == probe_digest
                            else "bundle probe output differs — parity failed"
                        ),
                    )
                )
            except Exception as exc:
                iso_checks.append(
                    CompatibilityCheck(
                        name="isolated_parity",
                        ok=False,
                        detail=f"bundle load failed: {type(exc).__name__}",
                    )
                )
        parity = parity.model_copy(
            update={
                "mode": "stdlib+isolated" if iso_checks else "stdlib",
                "checks": [*parity.checks, *iso_checks],
                "ok": parity.ok and all(c.ok for c in iso_checks),
            }
        )

    ok = all(c.ok for c in checks) and (parity.ok if parity is not None else True)
    return LoadValidationReport(
        status="compatible" if ok else "incompatible",
        mode="stdlib+isolated" if load_ok else "stdlib",
        load_verified=load_ok,
        checks=checks,
        parity=parity,
        detail=(
            "isolated load + structural validation passed"
            if ok and load_ok
            else ("structural validation passed (no load)" if ok else "validation failed")
        ),
    )


if __name__ == "__main__":
    try:
        os.umask(0o022)
        with open("request.json", "rb") as f:
            raw = f.read(_MAX_REQUEST + 1)
        if len(raw) > _MAX_REQUEST:
            raise ValueError("request too large")
        request = LoadRequest.model_validate(json.loads(raw))
        result = run(request, Path.cwd())
        print(json.dumps(result.model_dump(mode="json")))
    except Exception:
        # Sanitized: artifact contents and internals never leave the
        # container — the caller gets a code, not a traceback.
        print(
            json.dumps(
                {
                    "error": {
                        "code": "ENGINE_UNSUPPORTED_INPUT",
                        "message": "model load validation could not process the declared inputs",
                    }
                }
            )
        )
        sys.exit(2)
