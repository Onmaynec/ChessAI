"""Legal master-level opening *patterns*, without pretending to import GM games."""
from __future__ import annotations
from pathlib import Path
import pytest

from neural.master_openings import LINES, response
from neural.intelligence import _opening_advice
from neural.agent import START_FEN, apply, legal

ENGINE=next((x for x in [Path('build/chessai'),Path('build/Release/chessai.exe'),Path('build/chessai.exe')] if x.is_file()),None)


@pytest.mark.parametrize('line',LINES,ids=lambda p:p.name)
def test_curated_opening_is_legal_at_every_ply(line):
    if ENGINE is None:pytest.skip('Native C++ bridge needed for complete opening legality test')
    fen=START_FEN
    for index,move in enumerate(line.moves):
        assert move in legal(ENGINE,fen), (line.name,index,move,fen)
        fen=apply(ENGINE,fen,move)


def test_identifies_berlin_from_actual_moves():
    prefix=['e2e4','e7e5','g1f3','b8c6','f1b5']
    hint=response(prefix,['g8f6','a7a6','d7d6'])
    assert hint is not None
    assert hint[0]=='g8f6' and 'берлинская' in hint[1]
    assert _opening_advice(prefix,['g8f6','a7a6'])[0]=='g8f6'


def test_opening_never_forces_illegal_reply():
    prefix=['e2e4','e7e5','g1f3','b8c6','f1b5']
    assert response(prefix,['h7h6']) is None
    # The legacy repertoire may recommend a different *legal* move.
    suggestion,_,_=_opening_advice(prefix,['h7h6'])
    assert suggestion is None or suggestion=='h7h6'
