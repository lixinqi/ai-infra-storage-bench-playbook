"""Minimal decoder-only model used as a corpus sample.

The model is small enough to run on a single CPU core or on the meta device.
It exists so that the collection recipe has one end-to-end example: configuration
parsing, structural fingerprint, and a forward pass that works without weights.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import torch
from torch import nn


@dataclass
class TinyConfig:
    num_hidden_layers: int = 2
    hidden_size: int = 64
    num_attention_heads: int = 4
    num_key_value_heads: int = 2
    intermediate_size: int = 128
    vocab_size: int = 256
    max_position_embeddings: int = 128

    @classmethod
    def from_file(cls, path: str | Path) -> "TinyConfig":
        with Path(path).open(encoding="utf-8") as handle:
            raw = json.load(handle)
        fields = {name: raw[name] for name in cls.__dataclass_fields__ if name in raw}
        return cls(**fields)


class TinyAttention(nn.Module):
    """Grouped-query attention: queries use all heads, keys and values use fewer."""

    def __init__(self, config: TinyConfig) -> None:
        super().__init__()
        if config.hidden_size % config.num_attention_heads != 0:
            raise ValueError("hidden_size must be divisible by num_attention_heads")
        if config.num_attention_heads % config.num_key_value_heads != 0:
            raise ValueError("num_attention_heads must be divisible by num_key_value_heads")
        self.num_heads = config.num_attention_heads
        self.num_kv_heads = config.num_key_value_heads
        self.head_dim = config.hidden_size // config.num_attention_heads
        self.q_proj = nn.Linear(config.hidden_size, self.num_heads * self.head_dim, bias=False)
        self.k_proj = nn.Linear(config.hidden_size, self.num_kv_heads * self.head_dim, bias=False)
        self.v_proj = nn.Linear(config.hidden_size, self.num_kv_heads * self.head_dim, bias=False)
        self.o_proj = nn.Linear(config.hidden_size, config.hidden_size, bias=False)

    def _reshape(self, tensor: torch.Tensor, heads: int) -> torch.Tensor:
        batch, sequence, _ = tensor.shape
        tensor = tensor.view(batch, sequence, heads, self.head_dim)
        return tensor.transpose(1, 2)

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        batch, sequence, hidden = hidden_states.shape
        query = self._reshape(self.q_proj(hidden_states), self.num_heads)
        key = self._reshape(self.k_proj(hidden_states), self.num_kv_heads)
        value = self._reshape(self.v_proj(hidden_states), self.num_kv_heads)

        repeats = self.num_heads // self.num_kv_heads
        key = key.repeat_interleave(repeats, dim=1)
        value = value.repeat_interleave(repeats, dim=1)

        scores = torch.matmul(query, key.transpose(-1, -2)) / (self.head_dim ** 0.5)
        weights = torch.softmax(scores, dim=-1)
        attended = torch.matmul(weights, value)
        attended = attended.transpose(1, 2).reshape(batch, sequence, hidden)
        return self.o_proj(attended)


class TinyMLP(nn.Module):
    def __init__(self, config: TinyConfig) -> None:
        super().__init__()
        self.up = nn.Linear(config.hidden_size, config.intermediate_size, bias=False)
        self.down = nn.Linear(config.intermediate_size, config.hidden_size, bias=False)
        self.act = nn.GELU()

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        return self.down(self.act(self.up(hidden_states)))


class TinyBlock(nn.Module):
    def __init__(self, config: TinyConfig) -> None:
        super().__init__()
        self.attn = TinyAttention(config)
        self.mlp = TinyMLP(config)
        self.norm1 = nn.LayerNorm(config.hidden_size)
        self.norm2 = nn.LayerNorm(config.hidden_size)

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        hidden_states = hidden_states + self.attn(self.norm1(hidden_states))
        return hidden_states + self.mlp(self.norm2(hidden_states))


class TinyForCausalLM(nn.Module):
    def __init__(self, config: TinyConfig) -> None:
        super().__init__()
        self.embed = nn.Embedding(config.vocab_size, config.hidden_size)
        self.blocks = nn.ModuleList([TinyBlock(config) for _ in range(config.num_hidden_layers)])
        self.norm = nn.LayerNorm(config.hidden_size)
        self.lm_head = nn.Linear(config.hidden_size, config.vocab_size, bias=False)

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        hidden_states = self.embed(input_ids)
        for block in self.blocks:
            hidden_states = block(hidden_states)
        return self.lm_head(self.norm(hidden_states))


def build(config: TinyConfig, device: str | torch.device = "meta") -> TinyForCausalLM:
    model = TinyForCausalLM(config).to(torch.device(device))
    return model.eval()


if __name__ == "__main__":
    config_path = Path(__file__).with_name("config.json")
    config = TinyConfig.from_file(config_path)
    for device in ("meta", "cpu"):
        model = build(config, device=device)
        tokens = torch.zeros((1, 8), dtype=torch.long, device=device)
        with torch.no_grad():
            logits = model(tokens)
        print({"device": device, "logits_shape": tuple(logits.shape)})
