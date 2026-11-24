"""Stable v1 chess position and AlphaZero-style action encoding.

Input: 19 x 8 x 8 (white a1 is [0,0]); Black is NOT rotated.
Output policy: 73 x 8 x 8, with index plane * 64 + origin_square.
Never change these encodings without creating a new feature_version.
"""
from __future__ import annotations

import numpy as np

FEATURE_VERSION = "planes19_actions73_v1"
INPUT_CHANNELS = 19
POLICY_SIZE = 73 * 64
PIECES = "PNBRQKpnbrqk"
# delta file, delta rank; rank 0 is first rank (a1 at square 0)
RAYS = ((0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1))
KNIGHTS = ((1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2))
UNDERPROMOTIONS = "nbr"


def _sq(square: str) -> int:
    if len(square) != 2 or square[0] not in "abcdefgh" or square[1] not in "12345678":
        raise ValueError(f"Invalid square: {square!r}")
    return (int(square[1]) - 1) * 8 + ord(square[0]) - ord("a")


def encode_move(move: str) -> int:
    """Map a UCI move (including promotions) to one policy logit."""
    if len(move) not in (4, 5):
        raise ValueError(f"Invalid UCI move: {move!r}")
    origin, destination = _sq(move[:2]), _sq(move[2:4])
    dx, dy = destination % 8 - origin % 8, destination // 8 - origin // 8
    suffix = move[4:]  # queen promotions use normal sliding movement
    if suffix and suffix not in "qnbr":
        raise ValueError(f"Invalid promotion suffix in {move!r}")
    if suffix and suffix in UNDERPROMOTIONS:
        if abs(dy) != 1 or dx not in (-1, 0, 1):
            raise ValueError(f"Invalid underpromotion trajectory: {move!r}")
        plane = 64 + UNDERPROMOTIONS.index(suffix) * 3 + (dx + 1)
    elif (dx, dy) in KNIGHTS:
        plane = 56 + KNIGHTS.index((dx, dy))
    else:
        distance = max(abs(dx), abs(dy))
        if not (1 <= distance <= 7) or not (dx == 0 or dy == 0 or abs(dx) == abs(dy)):
            raise ValueError(f"Invalid move geometry: {move!r}")
        step = ((dx > 0) - (dx < 0), (dy > 0) - (dy < 0))
        plane = RAYS.index(step) * 7 + (distance - 1)
    return plane * 64 + origin


def encode_fen(fen: str) -> np.ndarray:
    """Encode strict six-field FEN. Board legality is checked by C++ exporter."""
    parts = fen.split()
    if len(parts) != 6:
        raise ValueError("FEN must have six fields")
    board, turn, castles, ep, halfmove, _ = parts
    if turn not in ("w", "b"):
        raise ValueError("Invalid turn")
    planes = np.zeros((INPUT_CHANNELS, 8, 8), dtype=np.float32)
    ranks = board.split("/")
    if len(ranks) != 8:
        raise ValueError("Invalid FEN rows")
    for visual_rank, text in enumerate(ranks):
        col = 0
        for char in text:
            if char in "12345678":
                col += int(char)
            elif char in PIECES:
                if col > 7:
                    raise ValueError("Invalid FEN rank width")
                planes[PIECES.index(char), 7 - visual_rank, col] = 1.0
                col += 1
            else:
                raise ValueError("Invalid FEN piece")
        if col != 8:
            raise ValueError("Invalid FEN rank width")
    planes[12].fill(1.0 if turn == "w" else 0.0)
    if castles != "-":
        for c in castles:
            if c not in "KQkq":
                raise ValueError("Invalid castling rights")
            planes[13 + "KQkq".index(c)].fill(1.0)
    if ep != "-":
        location = _sq(ep)
        planes[17, location // 8, location % 8] = 1.0
    try:
        half = int(halfmove)
    except ValueError as exc:
        raise ValueError("Invalid halfmove clock") from exc
    if half < 0:
        raise ValueError("Negative halfmove clock")
    planes[18].fill(min(half, 100) / 100.0)
    return planes


def score_to_value(score_cp: int, scale_cp: float = 600.0) -> float:
    """Turn a teacher's side-to-move centipawn assessment into [-1,1]."""
    return float(np.tanh(float(score_cp) / scale_cp))
