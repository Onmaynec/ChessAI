"""Pure layout and display rules for the Vision desktop presentation."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class PreviewLayout:
    stacked: bool
    size: int

def preview_layout(width: float) -> PreviewLayout:
    """Width is the inner preview row in logical pixels, not screen pixels."""
    width = max(0, int(width))
    stacked = width < 420
    available = width - (20 if stacked else 172)
    return PreviewLayout(stacked, max(80, min(360, available)))

def form_columns(width: float) -> int:
    """Two columns only when the actual panel has room for long labels."""
    return 2 if width >= 390 else 1

def session_state(active: bool, stopping: bool, had_worker: bool,
                  region: bool, engine: bool, model: bool, consent: bool) -> str:
    if active:
        return 'stopping' if stopping else 'active'
    if had_worker:
        return 'stopped'
    if region and engine and model and consent:
        return 'ready'
    return 'setup'

def short_text(value: object, maximum: int = 90) -> str:
    text = ' '.join(str(value).split())
    return text if len(text) <= maximum else text[:maximum-1] + '…'
