"""ChessAI Intelligence Guard v0.7.1 — neural-policy plus local tactical search.

Uses the project-owned C++ UCI search to evaluate *every legal candidate*;
ChessNet's policy remains a tie-breaker among tactically comparable moves.
Opening principles and history-dependent repetition penalties are applied after
search. This improves *playing behavior*, not the network's trained weights.

No web data, Stockfish download, chess.com API, checkpoint modifications, or
external network access. Decisions use the frozen model loaded for the game.
"""
from __future__ import annotations

import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .agent import rank

# Small, deliberately transparent opening *guide*. Not evidence that ChessNet
# learned opening theory. The C++ tactical evaluation can reject unsafe moves.
OPENING_LINES: tuple[tuple[str,...], ...] = (
    ('e2e4','e7e5','g1f3','b8c6','f1c4','f8c5','e1g1','g8f6','d2d3','e8g8'),
    ('e2e4','e7e5','g1f3','b8c6','f1b5','a7a6','b5a4','g8f6','e1g1'),
    ('e2e4','c7c5','g1f3','d7d6','d2d4','c5d4','f3d4','g8f6','b1c3'),
    ('e2e4','c7c5','g1f3','b8c6','d2d4','c5d4','f3d4'),
    ('e2e4','e7e6','d2d4','d7d5','b1c3','g8f6','e4e5'),
    ('e2e4','c7c6','d2d4','d7d5','b1c3','d5e4','c3e4'),
    ('e2e4','d7d5','e4d5','d8d5','b1c3','d5d8','d2d4'),
    ('e2e4','g7g6','d2d4','f8g7','g1f3','d7d6'),
    ('e2e4','d7d6','d2d4','g8f6','b1c3','g7g6'),
    ('e2e4','g8f6','e4e5','f6d5','d2d4'),
    ('d2d4','d7d5','c2c4','e7e6','b1c3','g8f6'),
    ('d2d4','g8f6','c2c4','g7g6','b1c3','f8g7'),
    ('d2d4','d7d5','c2c4','c7c6','g1f3','g8f6'),
    ('d2d4','e7e6','c2c4','d7d5','b1c3'),
    ('c2c4','e7e5','b1c3','g8f6','g2g3'),
    ('g1f3','d7d5','g2g3','g8f6','f1g2'),
)

# Prefer the e4–e5/Italian setup when several book lines share a prefix.
# Branches whose opponent reply differs remain available automatically.

# SkillBoost II extended opening repertoire: extra legal branches for both colors.
from .opening_repertoire_v2 import EXTRA_OPENINGS, response as skillboost_v2_response
OPENING_LINES = OPENING_LINES + tuple(item.moves for item in EXTRA_OPENINGS)

def book_move(history: list[str] | tuple[str,...], legal_moves: list[str]) -> str | None:
    prior = tuple(history)
    for line in OPENING_LINES:
        if len(prior) < len(line) and line[:len(prior)] == prior and line[len(prior)] in legal_moves:
            return line[len(prior)]
    return None


@dataclass(frozen=True)
class UciAnswer:
    move: str | None
    score_cp: int
    depth: int


class SearchUnavailable(RuntimeError):
    pass


def evaluate_fens(engine: Path, positions: list[str], *, depth: int = 4,
                  timeout: float = 35.0) -> list[UciAnswer]:
    """Batch searches through the existing compiled C++ UCI executable.

    A *single* subprocess handles all positions serially, avoiding 20-40
    Windows process launches for one chess move. No C++ recompilation needed.
    The reported score is centipawns from the FEN side-to-move perspective.
    """
    if not 1 <= depth <= 6:
        raise ValueError('Search depth must be 1..6')
    if not positions:
        return []
    if len(positions) > 256:
        raise ValueError('Too many positions for one search')
    for fen in positions:
        if '\n' in fen or '\r' in fen or len(fen) > 256:
            raise ValueError('Invalid FEN for UCI evaluation')
    script = 'uci\nisready\n' + ''.join(
        f'position fen {fen}\ngo depth {depth}\n' for fen in positions
    ) + 'quit\n'
    kwargs = {}
    if sys.platform == 'win32':
        kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        result = subprocess.run([str(Path(engine).resolve()), 'uci'], input=script,
                                text=True, capture_output=True, timeout=timeout,
                                check=False, **kwargs)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SearchUnavailable(f'C++ UCI tactical search failed: {exc}') from exc
    if result.returncode:
        raise SearchUnavailable(f'C++ UCI search returned {result.returncode}: {result.stderr[-200:]}')
    answers = []
    depth_seen = 0
    score_seen: int | None = None
    for line in result.stdout.splitlines():
        info = re.search(r'\binfo depth (\d+) score cp (-?\d+)\b', line)
        if info:
            depth_seen, score_seen = int(info.group(1)), int(info.group(2))
        best = re.match(r'^bestmove\s+(\S+)', line)
        if best:
            if score_seen is None:
                raise SearchUnavailable('C++ UCI response had no centipawn score')
            answers.append(UciAnswer(None if best.group(1) == '0000' else best.group(1),
                                     score_seen, depth_seen))
            depth_seen, score_seen = 0, None
    if len(answers) != len(positions):
        raise SearchUnavailable(f'C++ search returned {len(answers)} answers for {len(positions)} positions')
    return answers


def position_id(fen: str) -> str:
    """Board+turn; omit counters, castling/EP to detect back-and-forth loops."""
    fields = fen.split()
    return ' '.join(fields[:2])


def _square_piece(fen: str, sq: str) -> str:
    rank = 8 - int(sq[1])
    file = ord(sq[0]) - ord('a')
    line = fen.split()[0].split('/')[rank]
    expanded = ''.join('.' * int(c) if c.isdigit() else c for c in line)
    return expanded[file]


def _opening_score(move: str, fen: str, ply: int) -> int:
    if ply >= 20:
        return 0
    piece = _square_piece(fen, move[:2]).lower()
    dest = move[2:4]
    # Gentle incentives; tactical evaluation always wins over development.
    if piece in 'pn':
        if piece == 'p' and dest[0] in 'de' and dest[1] in '45':
            return 18
        if piece == 'n':
            return 12 if dest[0] in 'cdef' else -8
    if piece == 'b':
        return 12
    if piece == 'k':
        return 45 if move in ('e1g1','e1c1','e8g8','e8c8') else -45
    if piece == 'q' and ply < 12:
        return -35
    if piece == 'r' and ply < 14:
        return -75
    return 0


def _loop_penalty(move: str, next_fen: str, history_moves: list[str],
                  history_fens: list[str]) -> int:
    # Lose several tempi if a rook/queen/knight is moved out and straight back.
    penalty = 0
    if history_moves and history_moves[-1][:2] == move[2:4] and history_moves[-1][2:4] == move[:2]:
        penalty += 105
    if len(history_moves) >= 2 and history_moves[-2][2:4] == move[:2]:
        penalty += 25
    key = position_id(next_fen)
    previous = [position_id(f) for f in history_fens]
    if key in previous:
        penalty += 170 + min(previous.count(key), 2) * 90
    return penalty


def _terminal_score(child: dict, root_turn: str) -> int:
    if child['result'] == '1/2-1/2':
        return 0
    winner = 'w' if child['result'] == '1-0' else 'b'
    return 30000 if winner == root_turn else -30000


def choose_move(model, state: dict, bridge, engine: Path, *,
                history_moves: list[str] | None = None,
                history_fens: list[str] | None = None,
                depth: int = 4) -> tuple[str, float, dict]:
    """Return (legal UCI, raw NN value, transparent search report).

    Every legal action is searched. The network acts as a tie-breaker among
    near-best tactics. When search fails, return an explicitly labelled
    conservative fallback instead of silently claiming an engine evaluation.
    """
    if state.get('finished') or not state.get('legal_moves'):
        raise ValueError('No moves from a finished position')
    history_moves = history_moves or []
    history_fens = history_fens or [state['fen']]
    legal = state['legal_moves']
    neural_order, value = rank(model, state['fen'], legal)
    priors = dict(neural_order)
    preferred = book_move(history_moves, legal) if len(history_moves) < 20 else None
    v2_opening = skillboost_v2_response(history_moves, legal) if len(history_moves) < 22 else None
    opening_name = v2_opening[1] if v2_opening else None
    if preferred is None and v2_opening:
        preferred = v2_opening[0]
    temp_id = 999999  # The live BotLab session uses 444. This game is transient.
    children = {}
    try:
        for move in legal:
            bridge.new(temp_id, state['fen'])
            children[move] = bridge.step(temp_id, move)
    finally:
        try:
            bridge.drop(temp_id)
        except (RuntimeError, OSError):
            pass
    positions = [children[m]['fen'] for m in legal if not children[m]['finished']]
    try:
        try:
            analysis = evaluate_fens(engine, positions, depth=depth)
            actual_depth = depth
        except SearchUnavailable:
            # Always try a cheaper analysis before returning neural-only.
            actual_depth = 2
            analysis = evaluate_fens(engine, positions, depth=2, timeout=25)
    except SearchUnavailable as exc:
        # Still avoid obvious cycles when the engine is unavailable.
        ranking = []
        for move, prob in neural_order:
            penalty = _loop_penalty(move, children[move]['fen'], history_moves, history_fens)
            rank_value = math.log(max(prob, 1e-12)) * 15 - penalty
            if move == preferred:
                rank_value += 40
            rank_value += _opening_score(move,state['fen'],len(history_moves))
            ranking.append((rank_value, move))
        ranking.sort(reverse=True)
        return ranking[0][1], value, {'mode':'neural_fallback',
                                      'reason':str(exc),'opening':preferred,'opening_name':opening_name,
                                      'search_depth':0,'top':ranking[:4]}

    scores = {}
    itr = iter(analysis)
    for move in legal:
        child = children[move]
        scores[move] = (_terminal_score(child,state['fen'].split()[1])
                        if child['finished'] else -next(itr).score_cp)
    best_cp = max(scores.values())
    # Keep only tactically comparable moves; reward the opening only when safe.
    tactical_band = 70 if best_cp < 15000 else 0
    max_prob = max(priors.values())
    choices = []
    for move in legal:
        cp = scores[move]
        if cp < best_cp - tactical_band:
            continue
        prior = max(-42, int(12 * math.log(max(priors[move],1e-12)/max_prob)))
        opening = 34 if move == preferred else 0
        principles = _opening_score(move,state['fen'],len(history_moves))
        loop = _loop_penalty(move, children[move]['fen'], history_moves, history_fens)
        # If all other moves are much worse, safety takes priority over loops.
        quality = cp + prior + opening + principles - loop
        choices.append((quality, cp, priors[move], move, loop))
    choices.sort(key=lambda item:(-item[0],-item[1],-item[2],item[3]))
    chosen = choices[0]
    return chosen[3], value, {
        'mode':'neural_plus_cpp_search', 'opening':preferred,'opening_name':opening_name,
        'search_depth':actual_depth+1, 'engine_cp':chosen[1],
        'best_engine_cp':best_cp,'repetition_penalty_cp':chosen[4],
        'candidates': [{'move':m,'cp':scores[m], 'policy':round(priors[m],5)}
                       for m in sorted(legal,key=lambda m:(-scores[m],-priors[m],m))[:6]],
    }
