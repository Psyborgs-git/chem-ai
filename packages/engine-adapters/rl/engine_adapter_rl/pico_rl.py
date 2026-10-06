"""pico-RL — a tiny locally-constructed causal LM policy (§19.4, CS-0902).

Same pico-class transformer as CS-0801's base, expressed as a real
``transformers.PreTrainedModel`` so the pinned TRL ``GRPOTrainer`` can
own the optimizer/loss/checkpoint machinery:

- ``config.get_text_config()`` — TRL probes this for pad id and logit
  scaling attributes;
- ``.base_model`` — the backbone TRL calls for hidden states
  (``outputs.last_hidden_state``) before projecting through
  ``get_output_embeddings()`` itself;
- ``prepare_inputs_for_generation`` — required by peft's CAUSAL_LM
  wrapper.

The tokenizer is a deterministic 96-char ``PreTrainedTokenizer``
(printable ASCII + newline) — no external files, digest-stable.

This module only runs inside the pinned worker image; importing it on
the host without torch raises ImportError, which is honest.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from typing import Any, ClassVar

import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import GenerationMixin, PretrainedConfig, PreTrainedModel
from transformers.modeling_outputs import CausalLMOutput
from transformers.tokenization_utils import PreTrainedTokenizer

# 95 printable ASCII + newline = 96 ids; '\x00' is never in the charset.
CHARSET = [chr(c) for c in range(32, 127)] + ["\n"]
PAD_CHAR = " "
UNK_CHAR = "?"
EOS_CHAR = "\n"


class PicoRlTokenizer(PreTrainedTokenizer):  # type: ignore[misc]
    """Char-level tokenizer over CHARSET — deterministic, file-free."""

    def __init__(self, **kwargs: Any) -> None:
        self._stoi = {c: i for i, c in enumerate(CHARSET)}
        self._itos = {i: c for c, i in self._stoi.items()}
        super().__init__(pad_token=PAD_CHAR, eos_token=EOS_CHAR, unk_token=UNK_CHAR, **kwargs)

    @property
    def vocab_size(self) -> int:
        return len(CHARSET)

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(CHARSET, ensure_ascii=True).encode("utf-8")).hexdigest()

    def _tokenize(self, text: str, **kwargs: Any) -> list[str]:
        return list(text)

    def _convert_token_to_id(self, token: str) -> int:
        return self._stoi.get(token, self._stoi[UNK_CHAR])

    def _convert_id_to_token(self, index: int) -> str:
        return self._itos.get(index, UNK_CHAR)

    def convert_tokens_to_string(self, tokens: list[str]) -> str:
        return "".join(tokens)

    def get_vocab(self) -> dict[str, int]:
        return dict(self._stoi)

    def save_vocabulary(
        self, save_directory: str, filename_prefix: str | None = None
    ) -> tuple[str]:
        path = os.path.join(save_directory, (filename_prefix or "") + "pico_vocab.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(CHARSET, f, ensure_ascii=True)
        return (path,)


class PicoRLConfig(PretrainedConfig):  # type: ignore[misc]
    """Config for the fixture RL policy — mirrors the pico arch dims."""

    model_type = "pico-rl"

    def __init__(
        self,
        *,
        vocab_size: int = 96,
        n_embd: int = 128,
        n_head: int = 4,
        n_layer: int = 4,
        block_size: int = 1024,
        tie_word_embeddings: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.vocab_size = vocab_size
        self.n_embd = n_embd
        self.n_head = n_head
        self.n_layer = n_layer
        self.block_size = block_size
        self.tie_word_embeddings = tie_word_embeddings

    def get_text_config(self, decoder: bool = False) -> PicoRLConfig:
        return self


class CausalSelfAttention(nn.Module):  # type: ignore[misc]
    def __init__(self, config: PicoRLConfig) -> None:
        super().__init__()
        if config.n_embd % config.n_head != 0:
            raise ValueError("n_embd must be divisible by n_head")
        self.n_head = config.n_head
        self.c_attn = nn.Linear(config.n_embd, 3 * config.n_embd)
        self.c_proj = nn.Linear(config.n_embd, config.n_embd)
        self.register_buffer(
            "mask",
            torch.tril(torch.ones(config.block_size, config.block_size)).view(
                1, 1, config.block_size, config.block_size
            ),
            persistent=False,
        )

    def forward(self, x: torch.Tensor, attention_mask: torch.Tensor | None) -> torch.Tensor:
        B, T, C = x.shape
        q, k, v = self.c_attn(x).split(C, dim=2)
        head = C // self.n_head
        q = q.view(B, T, self.n_head, head).transpose(1, 2)
        k = k.view(B, T, self.n_head, head).transpose(1, 2)
        v = v.view(B, T, self.n_head, head).transpose(1, 2)
        att = (q @ k.transpose(-2, -1)) / math.sqrt(head)
        att = att.masked_fill(self.mask[:, :, :T, :T] == 0, float("-inf"))
        if attention_mask is not None:
            # (B, 1, 1, T) key padding mask — padded keys never attend.
            att = att.masked_fill(attention_mask[:, None, None, :] == 0, float("-inf"))
        # A fully masked query row (a padded position whose causal
        # window covers only padding) softmaxes to NaN — zero it so the
        # forward stays finite; those rows are masked in the loss.
        att = torch.nan_to_num(F.softmax(att, dim=-1), nan=0.0)
        y = att @ v
        y = y.transpose(1, 2).contiguous().view(B, T, C)
        return self.c_proj(y)


class MLP(nn.Module):  # type: ignore[misc]
    def __init__(self, config: PicoRLConfig) -> None:
        super().__init__()
        self.c_fc = nn.Linear(config.n_embd, 4 * config.n_embd)
        self.c_proj = nn.Linear(4 * config.n_embd, config.n_embd)
        self.act = nn.GELU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.c_proj(self.act(self.c_fc(x)))


class Block(nn.Module):  # type: ignore[misc]
    def __init__(self, config: PicoRLConfig) -> None:
        super().__init__()
        self.ln_1 = nn.LayerNorm(config.n_embd)
        self.attn = CausalSelfAttention(config)
        self.ln_2 = nn.LayerNorm(config.n_embd)
        self.mlp = MLP(config)

    def forward(self, x: torch.Tensor, attention_mask: torch.Tensor | None) -> torch.Tensor:
        x = x + self.attn(self.ln_1(x), attention_mask)
        return x + self.mlp(self.ln_2(x))


class PicoRLBackbone(nn.Module):  # type: ignore[misc]
    """Embeddings + blocks — the part TRL calls ``.base_model`` on.
    Returns an object exposing ``last_hidden_state``."""

    def __init__(self, config: PicoRLConfig) -> None:
        super().__init__()
        self.block_size = config.block_size
        self.wte = nn.Embedding(config.vocab_size, config.n_embd)
        self.wpe = nn.Embedding(config.block_size, config.n_embd)
        self.blocks = nn.ModuleList(Block(config) for _ in range(config.n_layer))
        self.ln_f = nn.LayerNorm(config.n_embd)
        self.apply(_init_weights)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor | None = None,
        **_: Any,
    ) -> Any:
        _B, T = input_ids.shape
        if T > self.block_size:
            raise ValueError(f"sequence length {T} exceeds block {self.block_size}")
        pos = torch.arange(0, T, dtype=torch.long, device=input_ids.device)
        x = self.wte(input_ids) + self.wpe(pos)
        for block in self.blocks:
            x = block(x, attention_mask)
        hidden = self.ln_f(x)
        return type("PicoOutput", (), {"last_hidden_state": hidden})()


class PicoRLForCausalLM(PreTrainedModel, GenerationMixin):  # type: ignore[misc]
    """~1.2M-parameter causal LM at pico-rl-v1 default dims — real
    weights, real gradients, honest fixture capability.

    ``base_model_prefix = "transformer"`` so ``model.base_model``
    (the ``PreTrainedModel`` property) resolves to the backbone — the
    attribute TRL's recompute path calls for ``last_hidden_state`` and
    the one peft wraps for adapter injection."""

    config_class = PicoRLConfig
    base_model_prefix = "transformer"
    _tied_weights_keys: ClassVar[list[str]] = []

    def __init__(self, config: PicoRLConfig) -> None:
        super().__init__(config)
        self.transformer = PicoRLBackbone(config)
        self.lm_head = nn.Linear(config.n_embd, config.vocab_size, bias=False)
        if config.tie_word_embeddings:
            self.lm_head.weight = self.transformer.wte.weight

    def get_input_embeddings(self) -> nn.Module:
        return self.transformer.wte

    def get_output_embeddings(self) -> nn.Module:
        return self.lm_head

    def prepare_inputs_for_generation(
        self, input_ids: torch.Tensor, **_: Any
    ) -> dict[str, torch.Tensor]:
        # peft's CAUSAL_LM wrapper requires this method; generation is
        # never used — rollouts come from the bounded driver.
        return {"input_ids": input_ids}

    def forward(
        self,
        input_ids: torch.Tensor | None = None,
        attention_mask: torch.Tensor | None = None,
        labels: torch.Tensor | None = None,
        **_: Any,
    ) -> CausalLMOutput:
        outputs = self.transformer(input_ids=input_ids, attention_mask=attention_mask)
        logits = self.lm_head(outputs.last_hidden_state)
        loss = None
        if labels is not None:
            loss = F.cross_entropy(
                logits[:, :-1, :].reshape(-1, logits.size(-1)),
                labels[:, 1:].reshape(-1),
                ignore_index=-100,
            )
        return CausalLMOutput(logits=logits, loss=loss)


def _init_weights(module: nn.Module) -> None:
    if isinstance(module, nn.Linear):
        nn.init.normal_(module.weight, mean=0.0, std=0.02)
        if module.bias is not None:
            nn.init.zeros_(module.bias)
    elif isinstance(module, nn.Embedding):
        nn.init.normal_(module.weight, mean=0.0, std=0.02)


def state_dict_sha256(model: torch.nn.Module, names: list[str]) -> str:
    """Deterministic hash over selected parameter tensors."""
    h = hashlib.sha256()
    params = dict(model.named_parameters())
    for name in sorted(names):
        tensor = params[name].detach().cpu().contiguous()
        h.update(name.encode("utf-8"))
        h.update(tensor.numpy().tobytes())
    return h.hexdigest()
