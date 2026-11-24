"""Phantom-X23: strictly legal *illustrative* white repertoire.

This is a local study book, not a forced win or grandmaster data.
Every entry is a UCI sequence validated by the project's chess core.
No board data is captured from websites and no checkpoint is touched.
"""
from __future__ import annotations
from dataclasses import dataclass

START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
_MAIN = ('g1f3 d7d5 b2b3 g8f6 c1b2 e7e6 e2e3 f8e7 g2g3 e8g8 '
         'f1g2 c7c5 e1g1 b8c6 d2d3 b7b6 b1d2 c8b7 d1e2 d8c7 '
         'e3e4 f8d8 e4e5 f6d7 f1e1 a8c8 h2h4 a7a6 d2f1 '
         'b6b5 f1h2 a6a5 f3g5 d7f8 e2h5 e7g5 h4g5 c7e7 '
         'h2g4 f8g6 g2f3 b5b4 g1g2 a5a4 e1h1').split()

@dataclass(frozen=True)
class Variation:
    key: str
    name: str
    plan: str
    moves: tuple[str, ...]

LINES: tuple[Variation,...] = (
    Variation('mate_h7','Фантом-X23: закрытое f8',
              'Двойное фианкетто → e4/e5 → h4, Qh5, Bf3, Kg2, Rh1; мат только при ошибке ...Qf8.',
              tuple(_MAIN+' e7f8 h5h7'.split())),
    Variation('mate_h8','Фантом-X23: вскрытие h-линии',
              'Открыть h-вертикаль и давить на h7; Qh8# только если соперник ошибся ...hxg6.',
              tuple(_MAIN+' g6f8 g5g6 h7g6 h5h8'.split())),
    Variation('defence_c4','Фантом-X23: чёрные защищаются ...c4',
              'После ...c4 король может уйти на f8: нельзя автоматически считать атаку матовой.',
              tuple(_MAIN+' c5c4 h5h7 g8f8'.split())),
    Variation('fianchetto','Фантом-X23: против ...g6',
              'Против фианкетто — позиционная игра и контроль d5; не пытаться механически играть Qh5.',
              tuple('g1f3 g8f6 b2b3 g7g6 c1b2 f8g7 g2g3 e8g8 '
                    'f1g2 d7d6 e1g1 e7e5 d2d3 b8c6 b1d2 f8e8 '
                    'e2e4 d6d5 e4d5 f6d5 f1e1 a7a5 d2c4 f7f6 '
                    'a2a4 c8g4 h2h3 g4e6 d1d2 d8d7 g1h2'.split())),
)


def match(history: list[str] | tuple[str,...], legal_moves: list[str] | tuple[str,...],
          *, white: bool=True, max_ply: int=52) -> tuple[str,str,str] | None:
    """Exact prefix only: never guess book moves after an unexpected reply.

    No lookup by occupancy alone: that could fabricate castling rights or
    silently transplant a move into a position reached by another history.
    """
    if not white or len(history)>=max_ply or len(history)%2:
        return None
    prior=tuple(history)
    legal=set(legal_moves)
    for variation in LINES:
        if len(prior)<len(variation.moves) and variation.moves[:len(prior)]==prior:
            move=variation.moves[len(prior)]
            if move in legal:
                return move,variation.name,variation.plan
    return None


def white_examples(engine):
    """Yield unique, engine-verified opening positions with a white target.

    These are highly correlated positions from four examples; do not mistake
    a train/validation split for independent Elo/strength evidence.
    """
    from .selfplay import ChessBridge
    collected={}
    with ChessBridge(engine) as bridge:
        for variation in LINES:
            state=bridge.new(871,START_FEN)
            for ply,move in enumerate(variation.moves):
                if state.get('finished') or move not in state['legal_moves']:
                    raise ValueError(f'Invalid Phantom line {variation.key} at ply {ply+1}: {move}')
                if ply%2==0:
                    saved=collected.get(state['fen'])
                    if saved and saved['best_move']!=move:
                        raise ValueError('Conflicting move labels for the same board: '+state['fen'])
                    if not saved:
                        collected[state['fen']]={'fen':state['fen'],'legal_moves':state['legal_moves'],
                                                 'best_move':move,'variation':variation.key,'ply':ply}
                state=bridge.step(871,move)
    return list(collected.values())
