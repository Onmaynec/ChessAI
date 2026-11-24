"""Compact policy/value residual CNN that trains on CPU and on CUDA GPUs."""
from __future__ import annotations

import torch
from torch import nn
from .encoding import INPUT_CHANNELS, POLICY_SIZE


class ResidualBlock(nn.Module):
    def __init__(self, channels: int):
        super().__init__()
        self.layer1 = nn.Conv2d(channels, channels, 3, padding=1, bias=False)
        self.norm1 = nn.BatchNorm2d(channels)
        self.layer2 = nn.Conv2d(channels, channels, 3, padding=1, bias=False)
        self.norm2 = nn.BatchNorm2d(channels)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        shortcut = x
        x = self.relu(self.norm1(self.layer1(x)))
        x = self.norm2(self.layer2(x))
        return self.relu(x + shortcut)


class ChessNet(nn.Module):
    def __init__(self, channels: int = 48, blocks: int = 3):
        super().__init__()
        if channels < 8 or blocks < 1 or blocks > 32:
            raise ValueError("Bad network size")
        self.config = {"channels": channels, "blocks": blocks}
        self.stem = nn.Sequential(
            nn.Conv2d(INPUT_CHANNELS, channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(channels), nn.ReLU(inplace=True)
        )
        self.body = nn.Sequential(*(ResidualBlock(channels) for _ in range(blocks)))
        self.policy = nn.Conv2d(channels, 73, kernel_size=1)
        self.value = nn.Sequential(
            nn.Conv2d(channels, 16, kernel_size=1),
            nn.ReLU(inplace=True),
            nn.Flatten(),
            nn.Linear(16 * 8 * 8, 64), nn.ReLU(inplace=True),
            nn.Linear(64, 1), nn.Tanh()
        )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.body(self.stem(x))
        return self.policy(h).reshape(-1, POLICY_SIZE), self.value(h).squeeze(-1)
