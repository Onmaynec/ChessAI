"""Regression: v0.7.1.1 stopped after Qxd8 Rxd8 in the user's game.

Every accepted move is constrained to a legal C++ reply; never guess on an
ambiguous screenshot. Runs without a browser, GPU or saved checkpoint.
"""
from __future__ import annotations

from threading import Event
from types import SimpleNamespace
from pathlib import Path

import cv2
import numpy as np
import pytest

from visionbot.recognizer import VisionRecognizer, ObservedTiles, START, board_after
from visionbot.autoplay import VisionAutoplay
from botlab.session import parse_board


# Original 17...Qd8 position on Nov 23 2026; screenshot after 18.Qxd8 Rxd8.
PRE_CAPTURE = '2rq2k1/p4ppp/3Q1n2/4P1N1/2p3b1/8/PP1P1PPP/R1B2RK1'


def render(board, color='white', size=640):
    frame = np.zeros((size,size,3), dtype=np.uint8)
    step = size // 8
    for r in range(8):
        for c in range(8):
            vr, vc = (r, c) if color == 'white' else (7-r,7-c)
            bg = (82,149,115) if (r+c)%2 else (208,236,235)
            cv2.rectangle(frame,(vc*step,vr*step),((vc+1)*step,(vr+1)*step),bg,-1)
            piece = board[r][c]
            if piece != '.':
                shade=(88,89,91) if piece.islower() else (249,249,249)
                outline=(220,220,220) if piece.islower() else (30,30,30)
                label=piece.upper()
                (w,h),_ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1.5, 3)
                x=vc*step+(step-w)//2;y=vr*step+(step+h)//2
                cv2.putText(frame,label,(x,y),cv2.FONT_HERSHEY_SIMPLEX,1.5,outline,9,cv2.LINE_AA)
                cv2.putText(frame,label,(x,y),cv2.FONT_HERSHEY_SIMPLEX,1.5,shade,6,cv2.LINE_AA)
    return frame


@pytest.mark.parametrize('orientation',['white','black'])
def test_queen_capture_then_rook_recapture_same_destination(orientation):
    old=parse_board(PRE_CAPTURE)
    after=board_after(board_after(old,'d6d8'),'c8d8')
    recognizer=VisionRecognizer.__new__(VisionRecognizer)
    recognizer.color=orientation
    obs=recognizer.observe(render(after,orientation))
    assert obs.sides[0][3] == -1  # rook on d8 is BLACK
    assert obs.sides[7][2] == 1   # bishop on c1 is WHITE
    result=recognizer.detect_immediate_reply(obs,old,'d6d8',['c8d8','c8c1','a7a6','g8h8'])
    assert result.move == 'c8d8', result


def test_ambiguous_occupancy_without_colors_stops_safely():
    old=parse_board(PRE_CAPTURE)
    after=board_after(board_after(old,'d6d8'),'c8d8')
    obs=SimpleNamespace(occupied=[[p!='.' for p in row] for row in after])
    result=VisionRecognizer.__new__(VisionRecognizer).detect_immediate_reply(
        obs,old,'d6d8',['c8d8','c8c1'])
    assert result.move is None
    assert 'colors' in result.reason


def test_unchanged_position_never_confirms_unclicked_move():
    old=parse_board(PRE_CAPTURE)
    obs=SimpleNamespace(occupied=[[p!='.' for p in row] for row in old])
    result=VisionRecognizer.__new__(VisionRecognizer).detect_immediate_reply(
        obs,old,'d6d8',['c8d8','c8c1'])
    assert result.move is None
    assert 'unchanged' in result.reason.lower()


@pytest.mark.parametrize('orientation',['white','black'])
def test_single_capture_confirmed_by_piece_color(orientation):
    old=parse_board(PRE_CAPTURE)
    after=board_after(old,'d6d8')
    # Real detector uses starting-position exemplar shapes as a fallback;
    # here fail loudly if it needed a silhouette for this capture.
    recognizer=VisionRecognizer.__new__(VisionRecognizer)
    recognizer.color=orientation
    recognizer.score=lambda *_: (_ for _ in ()).throw(AssertionError('No shape fallback'))
    observed=recognizer.observe(render(after,orientation))
    result=recognizer.detect(observed,old,['d6d8'])
    assert result.move=='d6d8', result


def test_opponent_capture_detected_without_occupancy_destination_change():
    old=board_after(parse_board(PRE_CAPTURE),'d6d8')
    after=board_after(old,'c8d8')
    recognizer=VisionRecognizer.__new__(VisionRecognizer)
    recognizer.color='white'
    recognizer.score=lambda *_: (_ for _ in ()).throw(AssertionError('No shape fallback'))
    result=recognizer.detect(recognizer.observe(render(after)),old,['c8d8','c8c1'])
    assert result.move == 'c8d8', result


def test_shadow_game_has_no_side_effects_on_main_session(tmp_path):
    events=[]
    class Bridge:
        def new(self,id,fen):
            events.append(('new',id,fen))
        def step(self,id,m):
            events.append(('step',id,m))
            return {'legal_moves':['c8d8','c8c1']}
        def drop(self,id): events.append(('drop',id))
    sess=SimpleNamespace(bridge=Bridge(),state={'fen':PRE_CAPTURE+' w - - 0 18'})
    bot=VisionAutoplay(Path('dummy'),Path('dummy'),tmp_path,'white',(0,0,640),lambda *_:None,Event())
    replies=bot._preview_opponent_replies(sess,'d6d8')
    assert replies==['c8d8','c8c1']
    assert [x[1] for x in events]==[445,445,445]
    assert ('step',445,'d6d8') in events


def test_rapid_reply_updates_session_in_correct_order(monkeypatch,tmp_path):
    import visionbot.autoplay as auto
    from botlab.session import parse_board
    events=[]
    logs=[]
    old=PRE_CAPTURE+' w - - 0 18'
    class FakeScreen:
        def grab(self,rect):return render(parse_board(START))
    class FakeSess:
        def __init__(self,*args,**kwargs):
            self.state={'fen':old,'finished':False,'legal_moves':['d6d8']}
            self.pending=None
            self.checkpoint=Path('dummy.pt')
        def ai_turn(self):return len(events)==0
        def propose(self):self.pending='d6d8';return 'd6d8',0.1
        def confirm_ai(self):
            assert self.pending=='d6d8'
            events.append('d6d8')
            self.pending=None
        def opponent_move(self,m):
            assert m=='c8d8'
            events.append(m)
            self.state['finished']=True
        def report(self,*args,**kwargs):return {'result_for_ai':'unfinished'}
        def close(self):pass
    monkeypatch.setattr(auto,'click_move',lambda *args,**kwargs:None)
    monkeypatch.setattr(auto,'save_progress',lambda *args,**kwargs:None)
    monkeypatch.setattr(auto.VisionAutoplay,'_preview_opponent_replies',lambda *args:['c8d8','c8c1'])
    monkeypatch.setattr(auto.VisionAutoplay,'_wait_own_or_immediate_reply',lambda *args:(args[3], 'c8d8'))
    bot=VisionAutoplay(Path('engine'),Path('model'),tmp_path,'white',(0,0,640),
                       logs.append,Event(),screen=FakeScreen(),session_factory=FakeSess)
    # Capture fake initial board is standard, but original session uses middle FEN.
    bot.run()
    assert events==['d6d8','c8d8'], logs
    assert bot.move_count==2
