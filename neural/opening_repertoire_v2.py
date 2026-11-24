"""Curated, short, *illustrative* opening continuations and common responses.

These are opening-principle drills, not a licensed games database nor proof of
professional-level strength. Legality is checked by the local C++ engine before
positions enter training. Never force a book move over a tactical refutation.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Opening:
    name: str
    family: str
    moves: tuple[str, ...]


def op(name: str, family: str, *moves: str) -> Opening:
    return Opening(name, family, moves)


EXTRA_OPENINGS = (
    op('Italian / Giuoco Piano','e4_e5','e2e4','e7e5','g1f3','b8c6','f1c4','f8c5','c2c3','g8f6','d2d4','e5d4'),
    op('Italian / Two Knights','e4_e5','e2e4','e7e5','g1f3','b8c6','f1c4','g8f6','d2d3','f8c5','e1g1'),
    op('Italian / Evans Gambit','e4_e5','e2e4','e7e5','g1f3','b8c6','f1c4','f8c5','b2b4','c5b4','c2c3'),
    op('Scotch Game','e4_e5','e2e4','e7e5','g1f3','b8c6','d2d4','e5d4','f3d4','g8f6'),
    op('Four Knights','e4_e5','e2e4','e7e5','g1f3','b8c6','b1c3','g8f6','f1b5'),
    op('Vienna Game','e4_e5','e2e4','e7e5','b1c3','g8f6','f2f4','d7d5'),
    op('King Gambit declined','e4_e5','e2e4','e7e5','f2f4','f8c5','g1f3','d7d6'),
    op('Petrov defense','e4_e5','e2e4','e7e5','g1f3','g8f6','f3e5','d7d6','e5f3','f6e4'),
    op('Philidor defense','e4_e5','e2e4','e7e5','g1f3','d7d6','d2d4','g8f6','b1c3'),
    op('Sicilian Najdorf setup','sicilian','e2e4','c7c5','g1f3','d7d6','d2d4','c5d4','f3d4','g8f6','b1c3','a7a6'),
    op('Sicilian Dragon setup','sicilian','e2e4','c7c5','g1f3','d7d6','d2d4','c5d4','f3d4','g8f6','b1c3','g7g6'),
    op('Sicilian Sveshnikov setup','sicilian','e2e4','c7c5','g1f3','b8c6','d2d4','c5d4','f3d4','g8f6','b1c3','e7e5'),
    op('Sicilian Alapin','sicilian','e2e4','c7c5','c2c3','d7d5','e4d5','d8d5','d2d4'),
    op('Sicilian closed','sicilian','e2e4','c7c5','b1c3','b8c6','g2g3','g7g6','f1g2','f8g7'),
    op('French advance','french','e2e4','e7e6','d2d4','d7d5','e4e5','c7c5','c2c3'),
    op('French Tarrasch','french','e2e4','e7e6','d2d4','d7d5','b1d2','c7c5'),
    op('French exchange','french','e2e4','e7e6','d2d4','d7d5','e4d5','e6d5','g1f3'),
    op('Caro-Kann advance','caro','e2e4','c7c6','d2d4','d7d5','e4e5','c8f5','g1f3','e7e6'),
    op('Caro-Kann classical','caro','e2e4','c7c6','d2d4','d7d5','b1c3','d5e4','c3e4','c8f5'),
    op('Caro-Kann exchange','caro','e2e4','c7c6','d2d4','d7d5','e4d5','c6d5','g1f3'),
    op('Scandinavian defense','scandinavian','e2e4','d7d5','e4d5','d8d5','b1c3','d5a5','d2d4'),
    op('Pirc defense','modern','e2e4','d7d6','d2d4','g8f6','b1c3','g7g6','g1f3'),
    op('Modern defense','modern','e2e4','g7g6','d2d4','f8g7','b1c3','d7d6'),
    op('Alekhine defense','modern','e2e4','g8f6','e4e5','f6d5','d2d4','d7d6','g1f3'),
    op('Queens Gambit declined','queens_gambit','d2d4','d7d5','c2c4','e7e6','b1c3','g8f6','c1g5'),
    op('Queens Gambit accepted','queens_gambit','d2d4','d7d5','c2c4','d5c4','g1f3','g8f6','e2e3'),
    op('Slav defense','slav','d2d4','d7d5','c2c4','c7c6','g1f3','g8f6','b1c3'),
    op('Semi-Slav defense','slav','d2d4','d7d5','c2c4','c7c6','g1f3','g8f6','b1c3','e7e6'),
    op('Kings Indian defense','indian','d2d4','g8f6','c2c4','g7g6','b1c3','f8g7','e2e4','d7d6'),
    op('Nimzo-Indian defense','indian','d2d4','g8f6','c2c4','e7e6','b1c3','f8b4','e2e3'),
    op('Queens Indian defense','indian','d2d4','g8f6','c2c4','e7e6','g1f3','b7b6','g2g3'),
    op('Grunfeld defense','indian','d2d4','g8f6','c2c4','g7g6','b1c3','d7d5','c4d5','f6d5'),
    op('Benoni defense','indian','d2d4','g8f6','c2c4','c7c5','d4d5','e7e6'),
    op('Dutch defense','dutch','d2d4','f7f5','g2g3','g8f6','f1g2','e7e6'),
    op('London System','london','d2d4','d7d5','c1f4','g8f6','e2e3','e7e6','g1f3'),
    op('London vs Kings Indian','london','d2d4','g8f6','c1f4','g7g6','e2e3','f8g7','g1f3'),
    op('English symmetrical','english','c2c4','c7c5','b1c3','b8c6','g2g3','g7g6'),
    op('English four knights','english','c2c4','e7e5','b1c3','g8f6','g1f3','b8c6'),
    op('Reti opening','reti','g1f3','d7d5','c2c4','e7e6','g2g3','g8f6'),
    op('Reti vs Indian','reti','g1f3','g8f6','c2c4','g7g6','g2g3','f8g7'),
    op('Bird opening','flank','f2f4','d7d5','g1f3','g8f6','e2e3'),
    op('Queens pawn vs Dutch','dutch','d2d4','f7f5','c2c4','g8f6','g2g3'),
)


def response(history: list[str] | tuple[str,...], legal_moves: list[str]) -> tuple[str,str] | None:
    """Return a matching next move and its opening name, or no recommendation.

    Opponent replies are *recognized by the actual complete move sequence*,
    never by a guessed opening from the current board alone.
    """
    prefix=tuple(history)
    legal=set(legal_moves)
    for entry in EXTRA_OPENINGS:
        if len(prefix)<len(entry.moves) and entry.moves[:len(prefix)]==prefix:
            move=entry.moves[len(prefix)]
            if move in legal:
                return move, entry.name
    return None
