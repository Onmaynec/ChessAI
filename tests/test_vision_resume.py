"""Regression tests for recovering a live computer-bot match after Vision crash.

All tests use the native legal-move bridge, local synthetic screenshots and a
stub inference callback; no browser/network connection or GPU is required.
"""
from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from botlab.session import BotLabSession, parse_board
from neural.selfplay import ChessBridge
from visionbot.recognizer import VisionRecognizer
from visionbot.recovery import (RecoveryError, RecoveryStore, replay_session,
                                recover_moves, _board_agrees)

ENGINE = Path(os.environ.get('CHESSAI_TEST_ENGINE', '/mnt/data/chess_vision_resume_build/chessai'))


def render(board, color='white', size=640):
    frame = np.zeros((size,size,3), dtype=np.uint8)
    cell = size // 8
    for r in range(8):
        for c in range(8):
            vr,vc = (r,c) if color == 'white' else (7-r,7-c)
            bg = (82,149,115) if (r+c)%2 else (208,236,235)
            cv2.rectangle(frame,(vc*cell,vr*cell),((vc+1)*cell,(vr+1)*cell),bg,-1)
            piece = board[r][c]
            if piece != '.':
                fill = (88,89,91) if piece.islower() else (249,249,249)
                outline = (220,220,220) if piece.islower() else (30,30,30)
                (w,h),_ = cv2.getTextSize(piece.upper(), cv2.FONT_HERSHEY_SIMPLEX,1.5,3)
                x = vc*cell+(cell-w)//2; y=vr*cell+(cell+h)//2
                cv2.putText(frame,piece.upper(),(x,y),cv2.FONT_HERSHEY_SIMPLEX,1.5,outline,9,cv2.LINE_AA)
                cv2.putText(frame,piece.upper(),(x,y),cv2.FONT_HERSHEY_SIMPLEX,1.5,fill,6,cv2.LINE_AA)
    return frame


def board_obs(recognizer, fen):
    return recognizer.observe(render(parse_board(fen), recognizer.color))


@pytest.fixture
def core():
    if not ENGINE.is_file():
        pytest.skip('Native engine not built')
    with ChessBridge(ENGINE) as bridge:
        yield bridge


def new_session(core, checkpoint, color):
    return BotLabSession(ENGINE, checkpoint, color, core=core,
                         predict=lambda state:(state['legal_moves'][0], 0.0))


def advance(sess, moves):
    for move in moves:
        assert move in sess.state['legal_moves'], move
        if sess.ai_turn():
            sess.pending=move
            sess.confirm_ai()
        else:
            sess.opponent_move(move)


@pytest.mark.parametrize('color,played,pending,reply', [
    ('white',['e2e4','e7e5'], 'g1f3', 'b8c6'),
    ('black',['e2e4','e7e5'], None, 'g1f3'),
])
def test_resume_current_board_and_one_or_two_legal_plies(tmp_path, core, color, played, pending, reply):
    weights = tmp_path/'latest.pt'; weights.write_bytes(b'fixed-model-checkpoint')
    store = RecoveryStore(tmp_path,color)
    first = render(parse_board('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'),color)
    store.create(weights,first,(22,44,640))
    s1=new_session(core,store.model_path,color)
    advance(s1,played)
    store.commit(s1)
    last_fen=s1.state['fen']
    if pending:
        store.intent(pending,last_fen)  # crash AFTER mouse click, BEFORE verification
        advance(s1,[pending,reply])
        expected_moves=[pending,reply]
    else:
        advance(s1,[reply])
        expected_moves=[reply]
    target_fen=s1.state['fen']

    # Training updated source checkpoint while game was running.
    weights.write_bytes(b'some-new-model-weights')
    assert store.model_path.read_bytes()==b'fixed-model-checkpoint'

    # Restart engine session and rebuild entire move history from journal.
    data=store.load()
    recognizer=VisionRecognizer(store.first_image(),color)
    s2=new_session(core,store.model_path,color)
    replay_session(s2,data)
    assert s2.state['fen']==last_fen
    observed=board_obs(recognizer,target_fen)
    assert recover_moves(s2,store,observed)==expected_moves
    assert s2.state['fen']==target_fen
    assert store.load()['pending'] is None
    assert store.load()['moves']==s2.history
    assert s2.history==played+expected_moves
    assert s2.history_fens[-1] == target_fen
    s1.close(); s2.close()


def test_restore_without_extra_move_if_screen_matches(tmp_path, core):
    weights=tmp_path/'model.pt';weights.write_bytes(b'checkpoint')
    store=RecoveryStore(tmp_path,'white')
    first=render(parse_board('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'))
    store.create(weights,first,(0,0,640))
    s=new_session(core,store.model_path,'white')
    advance(s,['e2e4','e7e5','g1f3'])
    store.commit(s)
    data=store.load()
    r=new_session(core,store.model_path,'white')
    replay_session(r,data)
    obs=board_obs(VisionRecognizer(store.first_image(),'white'),r.state['fen'])
    assert recover_moves(r,store,obs)==[]
    assert len(r.history)==3
    s.close();r.close()


def test_pending_click_did_not_happen_can_replan(tmp_path, core):
    weights=tmp_path/'model.pt';weights.write_bytes(b'checkpoint')
    store=RecoveryStore(tmp_path,'white')
    store.create(weights,render(parse_board('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')),(0,0,640))
    s=new_session(core,store.model_path,'white')
    store.intent('e2e4',s.state['fen'])
    data=store.load()
    r=new_session(core,store.model_path,'white')
    replay_session(r,data)
    obs=board_obs(VisionRecognizer(store.first_image(),'white'),r.state['fen'])
    assert recover_moves(r,store,obs)==[]
    assert store.load()['pending'] is None
    assert r.history==[]
    s.close();r.close()


def test_screenshot_wrong_game_never_resets_or_clicks(tmp_path, core):
    weights=tmp_path/'model.pt';weights.write_bytes(b'checkpoint')
    store=RecoveryStore(tmp_path,'white')
    store.create(weights,render(parse_board('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')),(0,0,640))
    s=new_session(core,store.model_path,'white')
    advance(s,['e2e4','e7e5','g1f3'])
    store.commit(s)
    before=store.path.read_bytes()
    r=new_session(core,store.model_path,'white')
    replay_session(r,store.load())
    # Another new game has a fresh starting position; cannot continue stored game.
    obs=board_obs(VisionRecognizer(store.first_image(),'white'),
                  'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')
    with pytest.raises(RecoveryError,match='Неоднозначная позиция'):
        recover_moves(r,store,obs)
    assert store.path.read_bytes()==before
    s.close();r.close()


def test_castling_metadata_replayed_not_guessed(tmp_path, core):
    weights=tmp_path/'model.pt';weights.write_bytes(b'checkpoint')
    store=RecoveryStore(tmp_path,'white')
    store.create(weights,render(parse_board('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')),(0,0,640))
    s=new_session(core,store.model_path,'white')
    line=['e2e4','e7e5','g1f3','b8c6','f1c4','g8f6','e1g1']
    advance(s,line)
    store.commit(s)
    assert 'K' not in s.state['fen'].split()[2]
    r=new_session(core,store.model_path,'white')
    replay_session(r,store.load())
    assert r.state['fen']==s.state['fen']
    assert r.state['fen'].split()[2]==s.state['fen'].split()[2]
    assert r.state['fen'].split()[4:] == s.state['fen'].split()[4:]
    s.close();r.close()


def test_corrupt_file_and_explicit_new_game_archive(tmp_path):
    model=tmp_path/'latest.pt';model.write_bytes(b'current-checkpoint')
    frame=render(parse_board('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'))
    store=RecoveryStore(tmp_path,'white')
    original=store.create(model,frame,(0,0,640))
    store.archive()
    archived=store.dir/'archive'/original['session_id']
    assert (archived/'active_white.json').exists()
    assert (archived/'initial_white.png').exists()
    assert (archived/'frozen_white.pt').exists()
    assert not store.exists()
    store.create(model,frame,(0,0,640))
    store.model_path.write_bytes(b'corrupted')
    with pytest.raises(RecoveryError,match='checkpoint'):
        store.load()
    assert model.read_bytes()==b'current-checkpoint'
