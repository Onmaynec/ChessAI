"""Phantom-X23: legal repertoire, safe opt-in and isolated training."""
import os
from pathlib import Path
import pytest

from neural.agent import START_FEN
from neural.phantom_opening import LINES, match, white_examples
from neural.agent_profiles import ALIASES, profile_for_filename
from neural.phantom_trainer import source_checkpoint
from visionbot.autoplay import VisionAutoplay


def engine():
    name=os.environ.get('CHESSAI_TEST_ENGINE')
    if not name or not Path(name).is_file():pytest.skip('Set CHESSAI_TEST_ENGINE to run native legality tests')
    return Path(name)


def test_first_move_and_repertoire_checks():
    assert match([],['g1f3','e2e4'])[0]=='g1f3'
    assert match([],['g1f3'],white=False) is None
    assert match(['g1f3','c7c5'],['b2b3','e2e4']) is None
    assert match(['g1f3','d7d5'],['b2b3','e2e4'])[0]=='b2b3'
    assert match(['g1f3','d7d5'],['e2e4']) is None
    assert match(['g1f3','d7d5','b2b3'],['g8f6']) is None
    assert match([],[],max_ply=0) is None


def test_all_four_variations_are_validated_by_real_cpp():
    from neural.selfplay import ChessBridge
    with ChessBridge(engine()) as bridge:
        for v in LINES:
            state=bridge.new(1701,START_FEN)
            for ply,move in enumerate(v.moves):
                assert move in state['legal_moves'],(v.key,ply,move)
                state=bridge.step(1701,move)
    rows=white_examples(engine())
    assert len(rows)>=30
    assert len({r['fen'] for r in rows})==len(rows)
    assert all(r['best_move'] in r['legal_moves'] for r in rows)


def test_style_selection_and_source_resolution(tmp_path):
    assert 'phantom.pt' in ALIASES
    assert profile_for_filename('phantom.pt').name=='Phantom-X23'
    checkpoint=tmp_path/'checkpoints'/'skillboost_v2.pt'
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b'test')
    assert source_checkpoint(tmp_path).name=='skillboost_v2.pt'
    with pytest.raises(ValueError):source_checkpoint(tmp_path,'../../etc/passwd')


def test_vision_book_is_opt_in_and_preserves_agent_switch_args(tmp_path):
    import threading
    bot=VisionAutoplay(Path('x'),Path('y'),tmp_path,'white',(0,0,400),lambda m:None,
                      threading.Event(),phantom_opening=True,recovery_enabled=False)
    assert bot.phantom_opening is True
    bot.request_agent_switch('phantom.pt')
    assert bot._queued_agent=='phantom.pt'


def test_recovery_journal_keeps_book_choice(tmp_path):
    import numpy as np
    import torch
    from neural.model import ChessNet
    from neural.encoding import FEATURE_VERSION
    from visionbot.recovery import RecoveryStore
    root=tmp_path/'run'
    model=ChessNet(8,1)
    ck=root/'checkpoints'/'latest.pt';ck.parent.mkdir(parents=True)
    torch.save({'model':model.state_dict(),'config':model.config,'feature_version':FEATURE_VERSION},ck)
    store=RecoveryStore(root,'white')
    store.create(ck,np.zeros((400,400,3),dtype=np.uint8),(0,0,400))
    store.set_opening_repertoire('phantom')
    reloaded=RecoveryStore(root,'white').load()
    assert reloaded['opening_repertoire']=='phantom'


def test_real_cpp_opting_in_selects_first_phantom_move(monkeypatch):
    from neural.intelligence import choose_move
    from neural.selfplay import ChessBridge
    from neural import intelligence
    exe=engine()
    monkeypatch.setattr(intelligence,'rank',lambda model,fen,legal: ([(m,1/len(legal)) for m in legal],0.0))
    with ChessBridge(exe) as bridge:
        state=bridge.new(1811,START_FEN)
        move,_,details=choose_move(None,state,bridge,exe,history_moves=[],history_fens=[START_FEN],
                                   repertoire='phantom',depth=4)
        assert move=='g1f3'
        assert details['opening_name'].startswith('Фантом-X23')


def test_illustrative_mate_sequences_still_end_legally():
    from neural.selfplay import ChessBridge
    with ChessBridge(engine()) as bridge:
        for variation in LINES[:2]:
            state=bridge.new(1851,START_FEN)
            for move in variation.moves:
                state=bridge.step(1851,move)
            assert state['finished'] is True
            assert state['result']=='1-0'
