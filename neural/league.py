"""Bounded historical self-play opponents. Never changes saved checkpoints."""
from __future__ import annotations
from pathlib import Path

from .checkpoint import load_model


def league_sources(run: Path, limit: int = 4) -> list[Path]:
    """Best plus a spread of historical snapshots; exclude mutable latest.pt."""
    if not 1 <= limit <= 16:
        raise ValueError('league pool limit must be between 1 and 16')
    folder = run / 'checkpoints'
    result = []
    best = folder / 'best.pt'
    if best.is_file():
        result.append(best)
    archives = sorted(folder.glob('iteration_[0-9][0-9][0-9][0-9][0-9].pt'))
    remaining = limit - len(result)
    if remaining and archives:
        # Evenly sample old / middle / recent checkpoints rather than only
        # the last few. Preserve distinct paths and deterministic ordering.
        indexes = ([len(archives)-1] if remaining == 1 else
                   [round(i * (len(archives)-1) / (remaining-1)) for i in range(remaining)])
        for index in indexes:
            file = archives[index]
            if file not in result:
                result.append(file)
    return result[:limit]


def load_league(run: Path, device, limit: int, model_config: dict):
    loaded = []
    for path in league_sources(run,limit):
        try:
            net = load_model(path, device)
            if net.config == model_config:
                net.eval()
                loaded.append((path.name, net))
        except (OSError, KeyError, ValueError, RuntimeError):
            # Invalid historic snapshots are excluded, never removed.
            continue
    return loaded
