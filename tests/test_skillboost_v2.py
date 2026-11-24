"""SkillBoost v2 invariant and model-safety tests.

Run from installed project: python -m pytest -q tests/test_skillboost_v2.py
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

import pytest
import torch

from neural.checkpoint import load_model
from neural.encoding import FEATURE_VERSION
from neural.model import ChessNet
from neural.opening_repertoire_v2 import EXTRA_OPENINGS, response
from neural.skill_boost_v2 import (opening_positions, train_skillboost_v2,
    classify, split_rows, SkillDataset, source_checkpoint, TACTICAL_SEEDS, teacher_scores)
from neural.selfplay import ChessBridge

ROOT=Path(__file__).resolve().parents[1]
ENGINE=ROOT/'build'/'Release'/'chessai.exe'
if not ENGINE.is_file():ENGINE=ROOT/'build'/'chessai.exe'
if not ENGINE.is_file():ENGINE=ROOT/'build_check'/'chessai'


def test_repertoire_legal_for_both_colors():
    if not ENGINE.is_file():pytest.skip('Compile C++ engine for legal move checks')
    assert len(EXTRA_OPENINGS)>=40
    families={v.family for v in EXTRA_OPENINGS}
    assert {'sicilian','french','caro','indian','queens_gambit'}<=families
    generated=opening_positions(ENGINE,max_counter=90,seed=11)
    assert len(generated)>180
    assert sum(r['category']=='counter' for r in generated)>30
    assert all(r['book_move'] is None or r['book_move'] in r['legal_moves'] for r in generated)
    assert any(r['fen'].split()[1]=='w' for r in generated)
    assert any(r['fen'].split()[1]=='b' for r in generated)


def test_recognizes_opening_and_counter_not_illegal():
    assert response(['e2e4','c7c5'],['g1f3','a2a4']) == ('g1f3','Sicilian Najdorf setup')
    assert response(['e2e4','e7e6','d2d4','d7d5','e4e5'],['c7c5']) == ('c7c5','French advance')
    assert response(['d2d4','g8f6','c2c4','e7e6','b1c3'],['f8b4']) == ('f8b4','Nimzo-Indian defense')
    assert response(['d2d4','g8f6','c2c4','e7e6','b1c3'],['a7a6']) is None
    assert response(['a2a4'],['h7h5']) is None


def test_tactical_seed_positions_are_legal():
    if not ENGINE.is_file():pytest.skip('C++ engine missing')
    with ChessBridge(ENGINE) as bridge:
        for n,fen in TACTICAL_SEEDS:
            s=bridge.new(111,fen)
            assert s['legal_moves'],n


def test_split_by_opening_family_no_leakage():
    rows=[{'fen':str(i),'split_group':'family:'+str(i//4)} for i in range(120)]
    train,valid=split_rows(rows,22)
    assert len(train)+len(valid)==120
    assert {r['split_group'] for r in train}.isdisjoint({r['split_group'] for r in valid})


def test_source_selection_prefers_previous_skillboost():
    with tempfile.TemporaryDirectory() as td:
        run=Path(td);(run/'checkpoints').mkdir()
        (run/'checkpoints'/'latest.pt').write_bytes(b'latest')
        assert source_checkpoint(run,'auto').name=='latest.pt'
        (run/'checkpoints'/'skillboost.pt').write_bytes(b'previous')
        assert source_checkpoint(run,'auto').name=='skillboost.pt'


def test_end_to_end_candidate_and_source_immutability():
    if not ENGINE.is_file():pytest.skip('C++ engine missing')
    with tempfile.TemporaryDirectory() as td:
        run=Path(td);(run/'checkpoints').mkdir()
        net=ChessNet(16,1)
        source=run/'checkpoints'/'skillboost.pt'
        torch.save({'model':net.state_dict(),'config':net.config,
                    'feature_version':FEATURE_VERSION,'iteration':1018,
                    'optimizer':None,'candidate_only':True},source)
        before=hashlib.sha256(source.read_bytes()).hexdigest()
        report=train_skillboost_v2(run=run,engine=ENGINE,source='auto',samples=24,
                teacher_depth=1,branch_depth=1,branches=4,epochs=1,
                batch_size=8,device='cpu',progress=lambda *_:None)
        assert report['source_iteration']==1018
        assert report['source_sha256_at_start']==before
        assert hashlib.sha256(source.read_bytes()).hexdigest()==before
        assert (run/'skillboost_v2'/'teacher_dataset.jsonl.gz').is_file()
        assert (run/'skillboost_v2'/'report.json').is_file()
        assert not (run/'checkpoints'/'latest.pt').exists()
        if report['candidate_written']:
            result=run/'checkpoints'/'skillboost_v2.pt'
            state=torch.load(result,map_location='cpu',weights_only=True)
            assert state['candidate_only'] is True
            assert state['optimizer'] is None
            assert state['iteration']==1018
            load_model(result,'cpu')
            with pytest.raises(FileExistsError):
                train_skillboost_v2(run=run,engine=ENGINE,samples=24,teacher_depth=1,
                    branch_depth=1,branches=4,epochs=1,device='cpu',progress=lambda *_:None)
        # An interrupted supervised run can reuse its gzipped dataset without
        # paying C++ generation costs a second time (if no candidate exists).
        assert (run/'skillboost_v2'/'dataset_generation.json').is_file()


def test_opening_teacher_checks_book_safety():
    if not ENGINE.is_file():pytest.skip('C++ engine missing')
    book=opening_positions(ENGINE,max_counter=0,seed=33)
    selected=[r for r in book if r['category']=='opening'][:6]
    guided=teacher_scores(ENGINE,selected,depth=2)
    assert len(guided)==6
    assert all('book_verified_cp' in r for r in guided)
    assert all(r['best_move'] in r['legal_moves'] for r in guided)
    assert all(r['teacher'].startswith(('chessai_builtin','curated_opening')) for r in guided)

def test_trade_classification_is_capture_based():
    row={'fen':'4k3/8/8/3q4/5N2/8/8/4K3 w - - 0 1',
         'best_move':'f4d5','score_cp':500}
    assert classify(row)=='trade'
