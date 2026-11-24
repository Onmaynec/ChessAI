"""Conservative, screenshot-only pawn promotion support for computer-bot games.

Underpromotions are never guessed. The last-rank piece must be visually
identified before the pending legal C++ move can be committed. No DOM/API use.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .recognizer import cell, tiles, occupancy_ratio

PROMOTION_TYPES = 'qrbn'


@dataclass(frozen=True)
class PromotionIdentification:
    kind: str | None
    score: float
    margin: float
    reason: str


def is_promotion(move: str) -> bool:
    return len(move) == 5 and move[4].lower() in PROMOTION_TYPES


def promotion_square(move: str) -> str:
    if not is_promotion(move):
        raise ValueError('Not a promotion UCI move')
    return move[2:4]


def _match_piece(tile: np.ndarray, side: str, *, bank=None,
                 minimum: float = .76, gap: float = .045) -> PromotionIdentification:
    from .position_import import mask_tile, load_bank, dice
    if min(tile.shape[:2]) < 24 or occupancy_ratio(tile) < .105:
        return PromotionIdentification(None, 0, 0, 'No visible promoted piece')
    samples = load_bank() if bank is None else bank
    mask = mask_tile(tile)
    scores = []
    for k in PROMOTION_TYPES:
        piece = k.upper() if side == 'white' else k
        scores.append((max(dice(mask, sample) for sample in samples[piece]), k))
    scores.sort(reverse=True)
    best, kind = scores[0]
    margin = best - scores[1][0]
    if best < minimum or margin < gap:
        return PromotionIdentification(None, best, margin,
            f'Promoted piece unclear: best {kind} {best:.3f}, margin {margin:.3f}')
    return PromotionIdentification(kind, best, margin, 'Promotion piece visually confirmed')


def identify_promoted_piece(observation, square: str, side: str, *, bank=None,
                            minimum: float = .76, gap: float = .045) -> PromotionIdentification:
    """Identify q/r/b/n at the destination, independent of last-move highlights.

    `observation` may be an 8x8 frame or VisionRecognizer's raw-tile carrier.
    Reject missing evidence and unrecognized badge/overlay cases.
    """
    if side not in ('white', 'black'):
        raise ValueError('side must be white or black')
    r, c = cell(square)
    raw = getattr(observation, 'raw_tiles', None)
    if raw is None:
        return PromotionIdentification(None, 0, 0, 'No raw image to verify promoted kind')
    from .recognizer import piece_side
    sides = getattr(observation, 'sides', None)
    observed_side = sides[r][c] if sides is not None else piece_side(raw[r][c])
    if observed_side != (1 if side == 'white' else -1):
        return PromotionIdentification(None, 0, 0,
                                       'Promoted piece color not confirmed')
    return _match_piece(raw[r][c], side, bank=bank, minimum=minimum, gap=gap)


def resolve_promotion_variants(observation, moves: Sequence[str], side: str):
    """Return one visually confirmed legal promotion variant, else None.

    Used only when legal candidates share the SAME source and destination.
    No inference from the common occupancy of all 4 promoted piece types.
    """
    candidates = list(dict.fromkeys(moves))
    if not candidates or not all(is_promotion(m) for m in candidates):
        return None
    if len({m[:4] for m in candidates}) != 1:
        return None
    found = identify_promoted_piece(observation, candidates[0][2:4], side)
    if found.kind is None:
        return None
    hit = [m for m in candidates if m[4].lower() == found.kind]
    return hit[0] if len(hit) == 1 else None


def promotion_picker_choices(before: np.ndarray, after: np.ndarray, color: str,
                             target: str, side: str, *, bank=None) -> dict[str, tuple[int,int]]:
    """Look for four distinct promotion icons overlaying the destination file.

    Return *board-relative* (row,col) square centers; caller converts to clicks.
    A popup cannot be inferred from position alone: four distinct icons AND
    changes from the pre-click frame are required to avoid clicking the board.
    """
    from .recognizer import orient_rc
    if before.shape != after.shape or color not in ('white', 'black'):
        return {}
    sr, sc = cell(target)
    vr, vc = orient_rc(sr, sc, color)
    direction = 1 if vr == 0 else -1 if vr == 7 else 0
    if not direction:
        return {}
    old = tiles(before, color)
    current = tiles(after, color)
    result = {}
    for offset in range(4):
        row = sr + offset * (1 if color == 'white' else -1) * direction
        if not (0 <= row < 8):
            return {}
        # Compare SAME chess-coordinate tile before/after the popup.
        orig, tile = old[row][sc], current[row][sc]
        changed = np.mean(np.abs(orig.astype(np.float32)-tile.astype(np.float32)))
        if changed < 8.0:
            return {}  # Not a four-icon UI; avoid accidental board clicks.
        guess = _match_piece(tile, side, bank=bank, minimum=.70, gap=.035)
        if guess.kind is None or guess.kind in result:
            return {}
        result[guess.kind] = (row, sc)
    return result if set(result) == set(PROMOTION_TYPES) else {}
