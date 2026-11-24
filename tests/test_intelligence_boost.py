"""0.7.1 tactical guard and safe teacher-candidate tests."""
from pathlib import Path
import hashlib
import json
import tempfile

import pytest
import torch

from neural.agent import START_FEN
from neural.intelligence import (book_move, evaluate_fens, choose_move,
                                 _loop_penalty, position_id, SearchUnavailable)
from neural.model import ChessNet
from neural.selfplay import ChessBridge
from neural.skill_boost import tune
from neural.checkpoint import load_model

ENGINE = next((p for p in (Path('build/chessai'),Path('build/Release/chessai.exe'),
                             Path('build/chessai.exe'),Path('chessai_temp')) if p.is_file()),None)


def test_opening_repertoire_does_not_force_illegal_moves():
    assert book_move([], ['e2e4','d2d4'])=='e2e4'
    assert book_move(['e2e4'], ['e7e5','c7c5'])=='e7e5'
    assert book_move(['e2e4','c7c5'], ['g1f3','b1c3'])=='g1f3'
    assert book_move(['e2e4','e7e5'], ['g1f3','g1h3'])=='g1f3'
    assert book_move(['e2e4','e7e5'], ['a2a3']) is None


def test_repetition_disincentive_for_exact_backtrack_and_repeat():
    f = START_FEN
    assert _loop_penalty('a2a1',f,['a1a2'],[]) >= 105
    assert _loop_penalty('a2a1',f,['a1a2'],[f]) >= 365
    with_count = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 12 9'
    assert position_id(f)==position_id(with_count)


def test_uci_batch_validates_positions_and_returns_one_score_per_fen():
    if ENGINE is None: pytest.skip('Build C++ core first')
    scores=evaluate_fens(ENGINE,[START_FEN,START_FEN],depth=2)
    assert len(scores)==2
    assert all(s.move is not None for s in scores)
    assert scores[0].score_cp==scores[1].score_cp
    with pytest.raises(ValueError):
        evaluate_fens(ENGINE,[START_FEN+'\nquit'],depth=2)


def test_mate_in_one_is_not_dropped_by_untrained_policy():
    if ENGINE is None: pytest.skip('Build C++ core first')
    fen='7k/6pp/5K2/8/8/8/8/6Q1 w - - 0 1'
    model=ChessNet(16,1).eval()
    with ChessBridge(ENGINE) as bridge:
        state=bridge.new(444,fen)
        move, value, details = choose_move(model,state,bridge,ENGINE,
                                           history_fens=[fen],depth=3)
        child=bridge.step(444,move)
    assert move=='g1g7', (move,details)
    assert child['finished'] and child['result']=='1-0'


def test_candidate_boost_does_not_overwrite_source():
    if ENGINE is None: pytest.skip('Build C++ core first')
    with tempfile.TemporaryDirectory() as td:
        run=Path(td);(run/'checkpoints').mkdir()
        model=ChessNet(16,1)
        source=run/'checkpoints'/'latest.pt'
        torch.save({'model':model.state_dict(),'config':model.config,
                    'feature_version':'planes19_actions73_v1','iteration':1018,
                    'optimizer':{'fake':'unchanged'}}, source)
        before=hashlib.sha256(source.read_bytes()).hexdigest()
        report=tune(engine=ENGINE,run=run,samples=28,depth=2,epochs=2,batch_size=8,
                    lr=1e-4,device='cpu')
        assert hashlib.sha256(source.read_bytes()).hexdigest()==before
        assert (run/'checkpoints'/'latest.pt').is_file()
        if report.get('candidate_written'):
            candidate=run/'checkpoints'/'skillboost.pt'
            assert candidate.is_file()
            booster=load_model(candidate)
            raw=torch.load(candidate,weights_only=True)
            assert raw['candidate_only'] is True and raw['optimizer'] is None
            assert raw['iteration']==1018
            assert (run/'skillboost_report.json').exists()
        else:
            assert report['status']=='rejected_no_holdout_improvement'
