"""CS-0802 engine tests — REAL isolated model load inside the pinned
``chem-studio-model-load`` container.

AT-0802-1 (isolated half): the full torch/peft path runs inside
``--network none`` isolation — base reconstructed from
(architecture, init_seed), tokenizer re-digested, adapter state dict
actually applied, probe forward pass digested. A binding that doesn't
match what training measured is REJECTED by the same checks a serving
request runs. Every test SKIPS explicitly when the image is absent —
absence is reported, never faked.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from workers.common.executor import ContainerBackend, ExecLimits
from workers.inference.model_loading.contracts import (
    AdapterBinding,
    AdapterIdentity,
    BaseIdentity,
    LoadRequest,
    TokenizerIdentity,
)
from workers.inference.model_loading.runtime import IMAGE, ModelLoadRuntime, available

pytestmark = pytest.mark.engine

_LIMITS = ExecLimits(
    wall_seconds=300,
    cpu_seconds=240,
    memory_bytes=2 * 1024**3,
    max_processes=64,
    output_bytes=2 * 1024**2,
    file_bytes=256 * 1024**2,
)

# Builds a REAL PicoGPT + LoRA adapter inside the image, persists the
# adapter state dict the same way the CS-0801 trainer does, and prints
# the measured digests the registry would record.
_BUILD_HELPER = r"""
import hashlib, json
from pathlib import Path
import torch
from peft import LoraConfig, get_peft_model, get_peft_model_state_dict
from safetensors.torch import save_file

from engine_adapter_sft.pico import CharTokenizer, PicoGPT, state_dict_sha256
from engine_adapter_sft.contracts import BASE_ARCHITECTURES

torch.manual_seed(0)
arch = BASE_ARCHITECTURES["pico-gpt-v1"]
model = PicoGPT(
    vocab_size=arch["vocab_size"],
    n_embd=arch["n_embd"],
    n_head=arch["n_head"],
    n_layer=arch["n_layer"],
    block_size=arch["block_size"],
    tie_weights=arch["tie_weights"],
)
base_sha = state_dict_sha256(model, sorted(n for n, _ in model.named_parameters()))
lora = LoraConfig(
    r=8,
    lora_alpha=16,
    lora_dropout=0.0,
    target_modules=["c_attn", "c_proj"],
    inference_mode=False,
)
peft_model = get_peft_model(model, lora)
state = get_peft_model_state_dict(peft_model, adapter_name="default")
out = Path("adapter.safetensors")
save_file(state, str(out))
out.chmod(0o644)
adapter_sha = hashlib.sha256(out.read_bytes()).hexdigest()
print(json.dumps({
    "base_sha256": base_sha,
    "tokenizer_sha256": CharTokenizer().digest(),
    "adapter_sha256": adapter_sha,
}))
"""


def _materialize() -> dict[str, object]:
    """Run the builder inside the container; return the measured
    digests + real adapter bytes from the scratch mount."""
    backend = ContainerBackend(IMAGE)
    result = backend.run(
        ["python", "-c", _BUILD_HELPER],
        inputs={},
        limits=_LIMITS,
        cancel=threading.Event(),
    )
    assert result.exit_code == 0, result.stderr or result.stdout
    doc = result.json_stdout()
    assert doc is not None
    adapter = Path(result.scratch_dir) / "adapter.safetensors"
    assert adapter.is_file()
    doc["adapter_bytes"] = adapter.read_bytes()
    import shutil

    shutil.rmtree(result.scratch_dir, ignore_errors=True)
    return doc


def _request(digests: dict[str, object], **kw: object) -> LoadRequest:
    return LoadRequest(
        base=BaseIdentity(
            base_model_id="pico-gpt-char-v1",
            architecture="pico-gpt-v1",
            init_seed=0,
            base_sha256=str(digests["base_sha256"]),
            license_id="fixture-internal",
        ),
        tokenizer=TokenizerIdentity(
            kind="char-v1", sha256=str(digests["tokenizer_sha256"])
        ),
        adapter=AdapterIdentity(
            sha256=str(digests["adapter_sha256"]),
            method="lora",
            config={
                "rank": 8,
                "alpha": 16,
                "dropout": 0.0,
                "target_modules": ["c_attn", "c_proj"],
            },
            base_binding=AdapterBinding(
                base_sha256=str(kw.get("bind_base", digests["base_sha256"])),
                tokenizer_sha256=str(kw.get("bind_tok", digests["tokenizer_sha256"])),
                architecture="pico-gpt-v1",
            ),
        ),
        serving_format="peft-adapter",
    )


@pytest.fixture(scope="module")
def materialized() -> dict[str, object]:
    if not available():
        pytest.skip(f"{IMAGE} not installed — isolated load layer untested")
    return _materialize()


class TestIsolatedLoad:
    def test_registered_pair_loads_and_verifies(
        self, materialized: dict[str, object]
    ) -> None:
        """A real adapter bound to the base/tokenizer it was built
        against passes structural + isolated validation end-to-end."""
        report = ModelLoadRuntime().validate(
            _request(materialized),
            adapter_bytes=materialized["adapter_bytes"],  # type: ignore[arg-type]
        )
        assert report.status == "compatible", report.detail
        assert report.mode == "stdlib+isolated"
        assert report.load_verified
        ok = {c.name: c.ok for c in report.checks}
        assert ok.get("isolated_base_sha256") is True
        assert ok.get("isolated_tokenizer_sha256") is True
        assert ok.get("isolated_load") is True

    def test_adapter_bound_to_wrong_base_rejected(
        self, materialized: dict[str, object]
    ) -> None:
        """AT-0802-1: adapter recorded against a different base is
        rejected — structurally and inside the runtime."""
        report = ModelLoadRuntime().validate(
            _request(materialized, bind_base="f" * 64),
            adapter_bytes=materialized["adapter_bytes"],  # type: ignore[arg-type]
        )
        assert report.status == "incompatible"
        failed = {c.name for c in report.checks if not c.ok}
        assert "adapter_base_hash" in failed

    def test_adapter_bound_to_wrong_tokenizer_rejected(
        self, materialized: dict[str, object]
    ) -> None:
        report = ModelLoadRuntime().validate(
            _request(materialized, bind_tok="e" * 64),
            adapter_bytes=materialized["adapter_bytes"],  # type: ignore[arg-type]
        )
        assert report.status == "incompatible"

    def test_bundle_parity_executed_isolated(
        self, materialized: dict[str, object]
    ) -> None:
        """A derived serving-bundle loads to an IDENTICAL probe digest
        — parity is executed, not declared."""
        from workers.inference.model_loading.verify import (
            build_bundle,
            bundle_adapter_bytes,
            parse_bundle,
        )

        request = _request(materialized)
        adapter_bytes = materialized["adapter_bytes"]
        assert isinstance(adapter_bytes, bytes)
        bundle = build_bundle(
            release_id="r1",
            base=request.base,
            tokenizer=request.tokenizer,
            adapter=request.adapter,
            adapter_bytes=adapter_bytes,
            conversion_steps=[{"step": "embed-adapter", "tool": "stdlib-1"}],
        )
        doc = parse_bundle(bundle)
        assert bundle_adapter_bytes(doc) == adapter_bytes
        request = request.model_copy(
            update={"serving_format": "serving-bundle-v1"}
        )
        report = ModelLoadRuntime().validate(
            request, adapter_bytes=adapter_bytes, bundle_bytes=bundle
        )
        assert report.status == "compatible", report.detail
        assert report.parity is not None and report.parity.ok
        iso = [c for c in report.parity.checks if c.name == "isolated_parity"]
        assert iso and iso[0].ok
        assert report.parity.mode == "stdlib+isolated"
