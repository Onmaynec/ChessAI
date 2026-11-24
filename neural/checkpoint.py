"""Versioned model checkpoint I/O."""
from __future__ import annotations

from pathlib import Path

import torch

from .encoding import FEATURE_VERSION
from .model import ChessNet


def load_model(path: str | Path, device: torch.device | str = "cpu") -> ChessNet:
    # weights_only=True blocks arbitrary Python object deserialization.
    state = torch.load(str(path), map_location="cpu", weights_only=True)
    if state.get("feature_version") != FEATURE_VERSION:
        raise ValueError("Checkpoint is incompatible with the current board/action encoding")
    model = ChessNet(**state["config"])
    model.load_state_dict(state["model"])
    return model.to(device).eval()
