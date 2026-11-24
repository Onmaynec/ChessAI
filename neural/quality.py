"""Chess AI quality diagnostics: rule-preserving repetition heuristics and color audit.

No artificial chess results are generated here. Repetition discouragement is only
an optional small policy-logit adjustment during *training rollout*; outcome
labels always come from the C++ engine. The gate also remains off in Evaluation.
"""
from __future__ import annotations
from collections import Counter


def position_signature(fen: str) -> str:
    """Diagnostic FEN signature. May over-distinguish non-capturable EP squares."""
    parts = fen.split()
    if len(parts) < 4:
        raise ValueError('FEN must have board, side, castling and en passant fields')
    return ' '.join(parts[:4])


def repeated_positions(fens: list[str]) -> int:
    """Count visits after first appearance (not an assertion of a legal draw)."""
    counts = Counter(position_signature(f) for f in fens)
    return sum(n - 1 for n in counts.values() if n > 1)


def reversible_move_candidates(history: list[str], legal_moves: list[str]) -> list[str]:
    """Moves undoing the actor's move two plies ago; no move is excluded.

    This is a conservative *cycle-risk heuristic*, not proof of repetition.
    The opposite side might have changed the position since then.
    """
    if len(history) < 2:
        return []
    previous = history[-2]
    if len(previous) != 4:
        return []  # promotions cannot be reversed
    backward = previous[2:] + previous[:2]
    return [backward] if backward in legal_moves else []


def reason_breakdown(games) -> dict[str, int]:
    return dict(sorted(Counter(g.reason for g in games).items()))


def swap_colors_rotate_fen(fen: str) -> str:
    """180° board rotation + color swap, for auditing perspective asymmetry.

    Synthetic FEN is for neural encoding/audit only, not chess-engine castling.
    This is an involution and changes the side to move, keeping the same
    player's perspective under rotated colors.
    """
    parts = fen.split()
    if len(parts) != 6:
        raise ValueError('Expected complete FEN')
    board, side, rights, ep, half, full = parts
    ranks = board.split('/')
    if len(ranks) != 8:
        raise ValueError('Invalid board rows')
    rows = []
    for rank in ranks:
        chars = []
        for ch in rank:
            if ch.isdigit():
                chars.extend('.' * int(ch))
            else:
                chars.append(ch)
        if len(chars) != 8:
            raise ValueError('Invalid FEN rank width')
        rows.append(chars)
    flipped = [[ch.swapcase() if ch != '.' else '.' for ch in reversed(row)]
               for row in reversed(rows)]
    output = []
    for row in flipped:
        result, blanks = '', 0
        for ch in row:
            if ch == '.':
                blanks += 1
            else:
                if blanks:
                    result += str(blanks)
                    blanks = 0
                result += ch
        if blanks:
            result += str(blanks)
        output.append(result)
    mapping = {'K':'q', 'Q':'k', 'k':'Q', 'q':'K'}
    swapped = ''.join(c for c in 'KQkq' if c in {mapping[x] for x in rights if x != '-'}) or '-'
    rotated_ep = ('-' if ep == '-' else 'abcdefgh'[7 - 'abcdefgh'.index(ep[0])] + str(9-int(ep[1])))
    flipped_side = 'b' if side == 'w' else 'w'
    return f"{'/'.join(output)} {flipped_side} {swapped} {rotated_ep} {half} {full}"
