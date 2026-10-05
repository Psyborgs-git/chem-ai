"""pico-GPT — a tiny locally-constructed base model for SFT (§17.4).

U08 (hardware) and U13 (base model/license) are unknown, so the pinned
trainer ships a deterministic ~1M-parameter decoder-only transformer it
constructs from a seed — CPU-compatible, no download, license
``fixture-internal`` (vault-scoped, never a scientific model). This
module only runs inside the pinned worker image; importing it on the
host without torch raises ImportError, which is honest.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import torch
import torch.nn as nn
import torch.nn.functional as F

# 95 printable ASCII + newline = 96 ids; '\x00' is never in the charset.
CHARSET = [chr(c) for c in range(32, 127)] + ["\n"]
PAD_CHAR = " "
UNK_CHAR = "?"


class CharTokenizer:
    """Deterministic char-level tokenizer (no external files)."""

    def __init__(self, charset: list[str] | None = None) -> None:
        self.charset = charset or CHARSET
        self.stoi = {c: i for i, c in enumerate(self.charset)}
        self.itos = {i: c for c, i in self.stoi.items()}

    @property
    def vocab_size(self) -> int:
        return len(self.charset)

    @property
    def pad_id(self) -> int:
        return self.stoi[PAD_CHAR]

    def encode(self, text: str) -> list[int]:
        unk = self.stoi[UNK_CHAR]
        return [self.stoi.get(c, unk) for c in text]

    def decode(self, ids: list[int]) -> str:
        return "".join(self.itos.get(i, UNK_CHAR) for i in ids)

    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.charset, ensure_ascii=True).encode("utf-8")
        ).hexdigest()


class CausalSelfAttention(nn.Module):  # type: ignore[misc]
    def __init__(self, n_embd: int, n_head: int, block_size: int) -> None:
        super().__init__()
        if n_embd % n_head != 0:
            raise ValueError("n_embd must be divisible by n_head")
        self.n_head = n_head
        self.c_attn = nn.Linear(n_embd, 3 * n_embd)
        self.c_proj = nn.Linear(n_embd, n_embd)
        self.register_buffer(
            "mask",
            torch.tril(torch.ones(block_size, block_size)).view(1, 1, block_size, block_size),
            persistent=False,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, T, C = x.shape
        q, k, v = self.c_attn(x).split(C, dim=2)
        head = C // self.n_head
        q = q.view(B, T, self.n_head, head).transpose(1, 2)
        k = k.view(B, T, self.n_head, head).transpose(1, 2)
        v = v.view(B, T, self.n_head, head).transpose(1, 2)
        att = (q @ k.transpose(-2, -1)) / math.sqrt(head)
        att = att.masked_fill(self.mask[:, :, :T, :T] == 0, float("-inf"))
        att = F.softmax(att, dim=-1)
        y = att @ v
        y = y.transpose(1, 2).contiguous().view(B, T, C)
        return self.c_proj(y)


class MLP(nn.Module):  # type: ignore[misc]
    def __init__(self, n_embd: int) -> None:
        super().__init__()
        self.c_fc = nn.Linear(n_embd, 4 * n_embd)
        self.c_proj = nn.Linear(4 * n_embd, n_embd)
        self.act = nn.GELU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.c_proj(self.act(self.c_fc(x)))


class Block(nn.Module):  # type: ignore[misc]
    def __init__(self, n_embd: int, n_head: int, block_size: int) -> None:
        super().__init__()
        self.ln_1 = nn.LayerNorm(n_embd)
        self.attn = CausalSelfAttention(n_embd, n_head, block_size)
        self.ln_2 = nn.LayerNorm(n_embd)
        self.mlp = MLP(n_embd)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.attn(self.ln_1(x))
        return x + self.mlp(self.ln_2(x))


class _Config(dict[str, Any]):
    """dict + attribute access — satisfies peft's HF-style config probes
    (`config.model_type`, `"_name_or_path" in config`, `config.get(...)`)."""

    def __getattr__(self, name: str) -> object:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


class PicoGPT(nn.Module):  # type: ignore[misc]
    """~0.86M-parameter GPT at pico-gpt-v1 default dims — real weights,
    real training, honest fixture capability."""

    def __init__(
        self,
        *,
        vocab_size: int,
        n_embd: int,
        n_head: int,
        n_layer: int,
        block_size: int,
        tie_weights: bool = True,
    ) -> None:
        super().__init__()
        self.block_size = block_size
        # peft's CAUSAL_LM wrapper probes `base_model.config.model_type`.
        self.config = _Config(
            model_type="pico-gpt",
            vocab_size=vocab_size,
            n_embd=n_embd,
            n_head=n_head,
            n_layer=n_layer,
            block_size=block_size,
        )
        self.wte = nn.Embedding(vocab_size, n_embd)
        self.wpe = nn.Embedding(block_size, n_embd)
        self.blocks = nn.ModuleList(Block(n_embd, n_head, block_size) for _ in range(n_layer))
        self.ln_f = nn.LayerNorm(n_embd)
        self.lm_head = nn.Linear(n_embd, vocab_size, bias=False)
        if tie_weights:
            self.lm_head.weight = self.wte.weight
        self.apply(self._init_weights)

    @staticmethod
    def _init_weights(module: nn.Module) -> None:
        if isinstance(module, nn.Linear):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def prepare_inputs_for_generation(
        self, input_ids: torch.Tensor, **_: object
    ) -> dict[str, torch.Tensor]:
        # peft's CAUSAL_LM wrapper requires this method to exist; the
        # trainer never auto-regresses.
        return {"input_ids": input_ids}

    def forward(
        self,
        input_ids: torch.Tensor | None = None,
        labels: torch.Tensor | None = None,
        idx: torch.Tensor | None = None,
        targets: torch.Tensor | None = None,
        **_: object,
    ) -> tuple[torch.Tensor, torch.Tensor | None]:
        idx = idx if idx is not None else input_ids
        targets = targets if targets is not None else labels
        if idx is None:
            raise ValueError("input_ids or labels required")
        _B, T = idx.shape
        if T > self.block_size:
            raise ValueError(f"sequence length {T} exceeds block {self.block_size}")
        pos = torch.arange(0, T, dtype=torch.long, device=idx.device)
        x = self.wte(idx) + self.wpe(pos)
        for block in self.blocks:
            x = block(x)
        logits = self.lm_head(self.ln_f(x))
        loss = None
        if targets is not None:
            # Causal shift: position t predicts token t+1; -100 positions
            # carry no loss (masked context / padding).
            loss = F.cross_entropy(
                logits[:, :-1, :].reshape(-1, logits.size(-1)),
                targets[:, 1:].reshape(-1),
                ignore_index=-100,
            )
        return logits, loss


def state_dict_sha256(model: torch.nn.Module, names: list[str]) -> str:
    """Deterministic hash over selected parameter tensors."""
    h = hashlib.sha256()
    params = dict(model.named_parameters())
    for name in sorted(names):
        tensor = params[name].detach().cpu().contiguous()
        h.update(name.encode("utf-8"))
        h.update(tensor.numpy().tobytes())
    return h.hexdigest()
