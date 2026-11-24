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


def _opening_advice(history_moves: list[str], legal: list[str], *, repertoire: str='standard') -> tuple[str | None, str | None, str | None]:
    """Match real move prefixes, never manufacture a GM move attribution."""
    if repertoire == 'phantom':
        from .phantom_opening import match
        hit=match(history_moves,legal)
        if hit:
            return hit
    # Prefer a more specific professional-theory line once the first few
    # moves have identified the opponent's actual opening choice.
    if len(history_moves) >= 4:
        from .master_openings import response as classical_response
        hit=classical_response(history_moves,legal)
        if hit:
            return hit
    try:
        from .opening_repertoire_v2 import response
        hit = response(history_moves, legal)
        if hit:
            return hit[0],hit[1],None
    except ImportError:
        pass
    move = book_move(history_moves, legal)
    return move, 'Классическая дебютная схема' if move else None, None


def _forcing_move(fen: str, move: str) -> bool:
    """Ensure captures/promotions aren't hidden by a shallow ranking cutoff."""
    target = _square_piece(fen, move[2:4])
    moving = _square_piece(fen, move[:2])
    return (len(move) == 5 or target != '.' or
            (moving.lower() == 'p' and move[0] != move[2]))


def _illustrative_line(engine: Path, after_fen: str, first_move: str,
                       first_reply: str | None, *, max_depth: int = 3) -> list[str]:
    """Short plausible continuation, not an alpha-beta principal variation."""
    result = [first_move]
    if not first_reply:
        return result
    result.append(first_reply)
    try:
        from .agent import apply as apply_move
        after_reply = apply_move(engine, after_fen, first_reply)
        next_answer = evaluate_fens(engine, [after_reply], depth=max_depth, timeout=4)
        if next_answer and next_answer[0].move:
            result.append(next_answer[0].move)
    except (RuntimeError, SearchUnavailable, ValueError, OSError):
        pass
    return result


def _trap_on_recapture(engine: Path, child: dict, selected_move: str,
                       best_reply: str | None, backed_cp: int) -> list[dict]:
    """Find *possible* bait captures refuted by a shallow continuation.

    Never force the bait: the main choice must already survive deeper best
    defence. Small positive shallow estimates are not evidence of a trap.
    """
    from .agent import apply as apply_move
    capture_targets = [m for m in child.get('legal_moves',[])
                       if m[2:4] == selected_move[2:4] and m != best_reply]
    if not capture_targets or backed_cp < -100:
        return []
    replies = capture_targets[:3]
    try:
        after = [apply_move(engine,child['fen'],m) for m in replies]
        evaluations = evaluate_fens(engine,after,depth=3,timeout=5)
    except (OSError,RuntimeError,SearchUnavailable,ValueError):
        return []
    return [{'bait':m,'punishment_cp':ans.score_cp}
            for m,ans in zip(replies,evaluations)
            if ans.score_cp >= backed_cp+180]


def _motifs(fen: str, move: str, search_cp: int, alternative_cp: int | None,
            opening: str | None) -> list[str]:
    motifs: list[str] = []
    if opening:
        motifs.append('Дебютная подготовка: ' + opening)
    if len(move) == 5:
        motifs.append('Превращение пешки')
    elif _square_piece(fen, move[2:4]) != '.':
        motifs.append('Тактический размен / взятие')
    if move in ('e1g1','e1c1','e8g8','e8c8'):
        motifs.append('Безопасность короля: рокировка')
    if alternative_cp is not None and search_cp-alternative_cp >= 180:
        motifs.append('Критический тактический выбор: другие ходы теряют оценку')
    if not motifs:
        motifs.append('Позиционная игра и проверка ответов соперника')
    return motifs


def choose_move(model, state: dict, bridge, engine: Path, *,
                history_moves: list[str] | None = None,
                history_fens: list[str] | None = None,
                depth: int = 4, deep_depth: int | None = None,
                shortlist: int = 4, deep_timeout: float = 22.0,
                style: str = 'balanced', repertoire: str = 'standard') -> tuple[str, float, dict]:
    """Conservative two-stage hybrid search, policy-weighted among safe moves.

    Default remains v0.7.1-compatible. When deep_depth=6 and depth=3, every
    move gets a 4-ply screen; selected moves receive up to 7 plies including
    the root move. A timeout falls back to the *evaluated shallow search*.
    This strengthens inference, it does not secretly train or replace weights.
    """
    from time import perf_counter
    started = perf_counter()
    if repertoire not in ('standard','phantom'):
        raise ValueError('Unknown opening repertoire')
    if style not in ('balanced','aggressive','defender'):
        raise ValueError('Unknown chess agent style')
    if state.get('finished') or not state.get('legal_moves'):
        raise ValueError('No moves from a finished position')
    if not 1 <= depth <= 6 or deep_depth is not None and not 1 <= deep_depth <= 6:
        raise ValueError('Search depth must be 1..6')
    if not 1 <= shortlist <= 12:
        raise ValueError('shortlist must be 1..12')
    history_moves = history_moves or []
    history_fens = history_fens or [state['fen']]
    legal = list(state['legal_moves'])
    neural_order, value = rank(model, state['fen'], legal)
    priors = dict(neural_order)
    preferred, opening_name, opening_plan = _opening_advice(history_moves, legal, repertoire=repertoire) if len(history_moves)<52 else (None,None,None)
    temp_id = 999999  # Live game 444, reply preview 445, attach probe 447.
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
    active = [m for m in legal if not children[m]['finished']]
    try:
        try:
            analysis = evaluate_fens(engine, [children[m]['fen'] for m in active],
                                     depth=depth, timeout=25)
            actual_depth = depth
        except SearchUnavailable:
            actual_depth = 2
            analysis = evaluate_fens(engine, [children[m]['fen'] for m in active],
                                     depth=2, timeout=25)
    except SearchUnavailable as exc:
        ranking = []
        for move, prob in neural_order:
            penalty = _loop_penalty(move,children[move]['fen'],history_moves,history_fens)
            q = math.log(max(prob,1e-12))*15-penalty
            if move == preferred:q+=40
            q+=_opening_score(move,state['fen'],len(history_moves))
            ranking.append((q,move))
        ranking.sort(reverse=True)
        return ranking[0][1], value, {
            'mode':'neural_fallback', 'agent_style':style, 'repertoire':repertoire, 'reason':str(exc), 'opening':preferred,
            'opening_name':opening_name, 'opening_plan':opening_plan, 'search_depth':0, 'top':ranking[:4],
            'search_time_s':round(perf_counter()-started,3)}

    scores = {}
    answers = {}
    itr = iter(analysis)
    for move in legal:
        child = children[move]
        if child['finished']:
            scores[move] = _terminal_score(child,state['fen'].split()[1])
            answers[move] = None
        else:
            result = next(itr)
            scores[move] = -result.score_cp
            answers[move] = result.move
    shallow_scores = dict(scores)
    deep_used = False
    deep_reason = None
    deep_moves: list[str] = []
    if deep_depth is not None and deep_depth > actual_depth and active:
        # Include top shallow candidates and any forcing lines within reach.
        promising = sorted(legal,key=lambda m:(-shallow_scores[m],-priors[m],m))
        selected = promising[:shortlist]
        forcing = [m for m in promising if _forcing_move(state['fen'],m)
                   and shallow_scores[m] >= max(shallow_scores.values())-170]
        for m in forcing:
            if m not in selected and len(selected)<shortlist+2:
                selected.append(m)
        if preferred in active and preferred not in selected and len(selected)<shortlist+2:
            selected.append(preferred)
        deep_moves = [m for m in selected if m in active]
        if deep_moves:
            try:
                # Bounded full second pass. On timeout keep the validated
                # shallower results rather than guessing neural-only.
                results = evaluate_fens(engine,[children[m]['fen'] for m in deep_moves],
                                        depth=deep_depth,timeout=deep_timeout)
                for m,result in zip(deep_moves,results):
                    scores[m] = -result.score_cp
                    answers[m] = result.move
                deep_used = True
            except SearchUnavailable as exc:
                deep_reason = str(exc)
    # The deeper search scores are comparable only within the deep group.
    # If that group succeeded, other moves remain unverified at deep depth;
    # do not accidentally mix horizon-dependent evaluations.
    ranked_moves = list(dict.fromkeys(deep_moves + [m for m in legal if children[m]['finished']])) if deep_used else legal
    best_cp = max(scores[m] for m in ranked_moves)
    tactical_band = (90 if style=='aggressive' else 35 if style=='defender' else 70) if best_cp < 15000 else 0
    max_prob = max(priors.values())
    choices = []
    for move in ranked_moves:
        cp = scores[move]
        # Opt-in opening study receives some room for a quiet positional move.
        # Never preserve it over a forced mate or a large tactical deficit.
        phantom_tolerance = (repertoire=='phantom' and move==preferred
                             and best_cp<15000 and cp>=best_cp-125)
        if cp < best_cp - tactical_band and not phantom_tolerance:
            continue
        prior = max(-42,int(12*math.log(max(priors[move],1e-12)/max_prob)))
        # Opt-in Phantom follows the prepared line among tactically comparable moves.
        # Tactical-band pruning above still rejects genuinely bad book moves.
        opening = (160 if repertoire=='phantom' else 34) if move == preferred else 0
        principles = _opening_score(move,state['fen'],len(history_moves))
        loop = _loop_penalty(move,children[move]['fen'],history_moves,history_fens)
        # Style only breaks ties between engine-verified candidates. Never
        # permit a tactical blunder solely to make the agent "aggressive".
        style_bonus=0
        if style=='aggressive':
            style_bonus=22 if _forcing_move(state['fen'],move) else 0
            if move==preferred:style_bonus+=9
        elif style=='defender':
            style_bonus=7 if move==preferred else 0
            # Prefer a measured evaluation edge over speculative activity.
            style_bonus+=min(14,max(0,cp-(best_cp-35))//3)
        quality = cp + prior + opening + principles-loop + style_bonus
        choices.append((quality,cp,priors[move],move,loop))
    choices.sort(key=lambda x:(-x[0],-x[1],-x[2],x[3]))
    chosen = choices[0]
    selected_move = chosen[3]
    other_values = [scores[m] for m in ranked_moves if m != selected_move]
    reply = answers[selected_move]
    line = _illustrative_line(engine,children[selected_move]['fen'],selected_move,reply)
    traps = (_trap_on_recapture(engine,children[selected_move],selected_move,reply,chosen[1])
             if deep_used else [])
    candidates = sorted(ranked_moves,key=lambda m:(-scores[m],-priors[m],m))[:6]
    reported_depth = (deep_depth if deep_used else actual_depth)+1
    return selected_move, value, {
        'mode':'neural_plus_cpp_search',
        'agent_style':style,
        'repertoire':repertoire,
        'opening':preferred,'opening_name':opening_name if selected_move==preferred else None,
        'opening_plan':opening_plan if selected_move==preferred else None,
        'search_depth':reported_depth,'shallow_depth':actual_depth+1,
        'deep_search':deep_used,'deep_warning':deep_reason,
        'evaluated_moves':len(legal), 'deep_evaluated_moves':len(deep_moves) if deep_used else 0,
        'engine_cp':chosen[1],'best_engine_cp':best_cp,
        'repetition_penalty_cp':chosen[4],
        'value':value, 'policy':round(priors[selected_move],5),
        'expected_reply':reply, 'illustrative_line':line,
        'motifs':_motifs(state['fen'],selected_move,chosen[1],max(other_values) if other_values else None,
                         opening_name if selected_move==preferred else None)
                  + (['Возможная ловушка при ошибочном взятии — НЕ форсированная комбинация'] if traps else []),
        'possible_traps':traps,
        'search_time_s':round(perf_counter()-started,3),
        'candidates':[{'move':m,'cp':scores[m], 'policy':round(priors[m],5),
                       'expected_reply':answers[m], 'forcing':_forcing_move(state['fen'],m)}
                      for m in candidates],
    }
