"""Reproducible, engine-validated opening positions for diverse paired evaluation.

No third-party chess service or human game accounts are involved.
The core remains the exclusive authority for move legality.
"""
from __future__ import annotations

import random

# Short standard opening families. Each UCI move is checked against the C++ core.
OPENING_LINES = (
    (),
    ('e2e4','e7e5','g1f3','b8c6','f1b5','a7a6'),
    ('e2e4','c7c5','g1f3','d7d6','d2d4','c5d4'),
    ('e2e4','e7e6','d2d4','d7d5','b1c3','g8f6'),
    ('e2e4','c7c6','d2d4','d7d5','b1c3','d5e4'),
    ('d2d4','d7d5','c2c4','e7e6','b1c3','g8f6'),
    ('d2d4','g8f6','c2c4','g7g6','b1c3','f8g7'),
    ('d2d4','d7d5','c2c4','c7c6','g1f3','g8f6'),
    ('c2c4','e7e5','b1c3','g8f6','g2g3','d7d5'),
    ('g1f3','d7d5','g2g3','g8f6','f1g2','c7c6'),
    ('e2e4','e7e5','g1f3','g8f6','f3e5','d7d6'),
    ('e2e4','d7d5','e4d5','d8d5','b1c3','d5d8'),
)


def open_position(bridge, gid: int, origin: str, seed: int, ordinal: int,
                  opening_plies: int = 6):
    """Return (state, opening moves) with deterministic variation.

    Caller owns the bridge game and must eventually drop it. All applied moves
    are validated by ChessBridge. One opening is chosen per *pair*, not game.
    """
    state = bridge.new(gid, origin)
    moves: list[str] = []
    if opening_plies <= 0 or state['finished']:
        return state, moves
    rng = random.Random((seed & 0xffffffff) ^ (ordinal * 0x9e3779b1))
    # For arbitrary non-starting FEN, only random legal continuations are used.
    prefix = OPENING_LINES[rng.randrange(len(OPENING_LINES))] if origin.split()[0] == 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR' else ()
    for ply in range(opening_plies):
        legal = state['legal_moves']
        if state['finished'] or not legal:
            break
        planned = prefix[ply] if ply < len(prefix) else None
        move = planned if planned in legal else rng.choice(legal)
        state = bridge.step(gid, move)
        moves.append(move)
    return state, moves
