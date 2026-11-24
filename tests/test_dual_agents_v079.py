"""Regression tests for specialized agents, crash recovery, and live switching."""
import hashlib
import json
import threading
from pathlib import Path

import numpy as np
import pytest
import torch

from neural.agent_profiles import ALIASES, get_profile, resolve_source_checkpoints
from neural.checkpoint import load_model
from neural.encoding import FEATURE_VERSION
from neural.model import ChessNet
from neural.agent_specialization import DistillDataset, ensemble_targets
from botlab.session import BotLabSession
from visionbot.autoplay import VisionAutoplay
from visionbot.recovery import RecoveryStore
from dashboard.server import training_health

FEN='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'


def _checkpoint(path:Path,noise=0):
    torch.manual_seed(42+noise)
    model=ChessNet(8,1)
    state={'model':model.state_dict(),'config':model.config,
           'feature_version':FEATURE_VERSION,'iteration':123,'optimizer':None}
    path.parent.mkdir(parents=True,exist_ok=True);torch.save(state,path)
    return path


class Bridge:
    def new(self,game,fen):return {'fen':fen,'legal_moves':['e2e4','d2d4'],'finished':False}
    def step(self,game,move):return {'fen':FEN,'legal_moves':['e2e4'],'finished':False}
    def drop(self,game):pass


def test_profiles_have_different_training_weighting_and_search():
    a=get_profile('aggressive');d=get_profile('defender')
    assert a.filename=='aggressive.pt' and d.filename=='defender.pt'
    assert a.category_weights['attack']>d.category_weights['attack']
    assert d.category_weights['defense']>a.category_weights['defense']
    assert 'skillboost_v2.pt' in ALIASES


def test_three_sources_required_no_silent_fallback(tmp_path):
    root=tmp_path/'run'
    _checkpoint(root/'checkpoints'/'latest.pt')
    with pytest.raises(FileNotFoundError,match='skillboost_v2'):
        resolve_source_checkpoints(root)
    _checkpoint(root/'checkpoints'/'skillboost.pt')
    _checkpoint(root/'checkpoints'/'skillboost_v2.pt')
    paths=resolve_source_checkpoints(root)
    assert len(paths)==3


def test_ensemble_uses_three_policies_and_only_legal_moves(tmp_path):
    root=tmp_path/'run';folder=root/'checkpoints'
    for name,idx in (('latest.pt',0),('skillboost.pt',1),('skillboost_v2.pt',2)):
        _checkpoint(folder/name,idx)
    row={'fen':FEN,'legal_moves':['e2e4','d2d4'],'best_move':'d2d4', 'category':'opening'}
    targets=ensemble_targets([row],resolve_source_checkpoints(root),device='cpu')
    assert len(targets)==1
    assert torch.isclose(targets[0].sum(),torch.tensor(1.0))
    assert targets[0][1]>=0.45
    ds=DistillDataset([row],targets)
    x,mask,prob,label=ds[0]
    assert x.shape==(19,8,8) and int(mask.sum())==2
    assert int((prob>0).sum())==2


def test_live_switch_preserves_board_and_ply_history(tmp_path):
    folder=tmp_path/'run'/'checkpoints'
    latest=_checkpoint(folder/'latest.pt')
    aggressive=_checkpoint(folder/'aggressive.pt',1)
    defender=_checkpoint(folder/'defender.pt',2)
    session=BotLabSession(Path('unused'),latest,'white',core=Bridge(),device='cpu')
    session.history=['e2e4','e7e5']
    session.history_fens=[FEN,FEN,FEN]
    previous_state=session.state
    a=session.switch_agent(aggressive)
    assert session.state is previous_state and session.history==['e2e4','e7e5']
    assert session.agent_profile.name=='Aggressive' and a['plies']==2
    session.switch_agent(defender)
    assert session.agent_profile.name=='Defender'
    assert session.report('computer','unfinished')['agent_changes'][1]['agent']=='defender.pt'
    session.pending='e2e4'
    with pytest.raises(ValueError):session.switch_agent(latest)
    session.close()


def test_recovery_switch_snapshots_are_immutable(tmp_path):
    run=tmp_path/'run'
    latest=_checkpoint(run/'checkpoints'/'latest.pt')
    attacker=_checkpoint(run/'checkpoints'/'aggressive.pt',1)
    store=RecoveryStore(run,'white')
    image=np.zeros((400,400,3),dtype=np.uint8)
    store.create(latest,image,(0,0,400))
    old=store.model_path
    prior_hash=hashlib.sha256(old.read_bytes()).hexdigest()
    store.switch_checkpoint(attacker)
    switched=store.model_path
    assert old!=switched and old.is_file()
    assert hashlib.sha256(old.read_bytes()).hexdigest()==prior_hash
    assert store.data['fen']==FEN and store.data['moves']==[]
    reopened=RecoveryStore(run,'white')
    data=reopened.load()
    assert data['original_checkpoint']=='aggressive.pt'
    assert reopened.model_path==switched
    assert load_model(reopened.model_path,'cpu')


def test_async_agent_request_lands_between_moves(tmp_path):
    bot=VisionAutoplay(Path('x'),Path('y'),tmp_path,'white',(0,0,400),lambda s:None,
                       threading.Event(),recovery_enabled=False)
    bot.request_agent_switch('defender.pt')
    assert bot._queued_agent=='defender.pt'
    with pytest.raises(ValueError):bot.request_agent_switch('../outside.pt')


def test_training_health_explains_stagnation(tmp_path):
    rows=[]
    for i in range(25):
        rows.append({'iteration':i+1,'games':16,
                     'results':{'draws':14,'unfinished':0},
                     'arena':{'score':0.45,'completed':4},
                     'kl_early_stop':i%5!=0})
    p=tmp_path/'metrics.jsonl'
    p.write_text('\n'.join(json.dumps(r) for r in rows),encoding='utf-8')
    result=training_health(tmp_path)
    assert result['draw_share']>0.8
    assert result['kl_early_stop_share']>0.7
    assert result['arena_samples']==25
    assert len(result['warnings'])>=2
