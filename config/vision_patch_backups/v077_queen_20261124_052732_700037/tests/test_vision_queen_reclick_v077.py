"""No-blind-retry checks for Chess AI Vision Bot queen promotion."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np
import pytest

from visionbot import autoplay, promotion, recognizer


def _rig(monkeypatch, findings, popup=None):
    """Inject screenshot/classifier and mouse; no desktop access or dependencies."""
    clicks=[]
    logs=[]
    keyboard=[]
    fake=SimpleNamespace(
        click=lambda x,y: clicks.append((x,y)),
        keyDown=lambda key: keyboard.append(('down',key)),
        keyUp=lambda key: keyboard.append(('up',key)),
    )
    monkeypatch.setitem(sys.modules,'pyautogui',fake)
    monkeypatch.setattr(autoplay,'check_computer_browser_focus',lambda hwnd:None)
    monkeypatch.setattr(recognizer,'tiles',lambda image,color:[[image]])
    monkeypatch.setattr(promotion,'promotion_picker_choices',
                        popup or (lambda *args,**kwargs:{}))
    results=iter(findings)
    monkeypatch.setattr(promotion,'identify_promoted_piece',
                        lambda *args,**kwargs: SimpleNamespace(kind=next(results)))
    screen=SimpleNamespace(
        grab=lambda rect: np.zeros((640,640,3),dtype=np.uint8),
        pixel=lambda x,y: (x,y),
    )
    return screen,fake,clicks,keyboard,logs


@pytest.mark.parametrize('move,color',[
    ('a7a8q','white'),
    ('b2b1q','black'),
    ('g7h8q','white'),  # capture + promotion
    ('g2h1q','black'),
])
def test_queen_promotion_reclicks_same_destination_once(monkeypatch,move,color):
    screen,fake,clicks,keys,logs=_rig(monkeypatch,[None,'q'])
    result=autoplay.click_move(move,(15,25,640),color,screen,
        clicker=fake.click,sleep=lambda _:None,report=logs.append)
    assert result=='queen_reclick'
    assert len(clicks)==3
    assert clicks[1]==clicks[2]==autoplay.move_points(move,(15,25,640),color)[1]
    assert any('Ферзь подтверждён' in x for x in logs)
    assert keys==[]


def test_autoqueen_does_not_send_unnecessary_third_click(monkeypatch):
    screen,fake,clicks,keys,logs=_rig(monkeypatch,['q'])
    assert autoplay.click_move('b2b1q',(0,0,640),'black',screen,
        clicker=fake.click,sleep=lambda _:None,report=logs.append)=='automatic'
    assert len(clicks)==2
    assert 'лишний клик не нужен' in '\n'.join(logs)


def test_recognized_menu_queen_item_used_with_one_extra_click(monkeypatch):
    def popup(before,current,color,target,side):
        return {'q':(0,0),'r':(1,0),'b':(2,0),'n':(3,0)}
    screen,fake,clicks,keys,logs=_rig(monkeypatch,[None,'q'],popup)
    assert autoplay.click_move('a7a8q',(0,0,640),'white',screen,
        clicker=fake.click,sleep=lambda _:None)=='queen_reclick'
    assert clicks[-1]==(40,40)
    assert len(clicks)==3


def test_wrong_piece_does_not_reclick(monkeypatch):
    screen,fake,clicks,_,_=_rig(monkeypatch,['n'])
    with pytest.raises(RuntimeError,match='не выбранная фигура'):
        autoplay.click_move('b2b1q',(0,0,640),'black',screen,
            clicker=fake.click,sleep=lambda _:None)
    assert len(clicks)==2


def test_ordinary_move_only_two_clicks(monkeypatch):
    screen,fake,clicks,keys,_=_rig(monkeypatch,[])
    assert autoplay.click_move('b2b3',(0,0,640),'black',screen,
        clicker=fake.click,sleep=lambda _:None)=='ordinary'
    assert len(clicks)==2
    assert keys==[]


def test_underpromotion_keeps_existing_picker_logic(monkeypatch):
    screen,fake,clicks,keys,_=_rig(monkeypatch,[],
        lambda *args,**kwargs:{'q':(0,0),'r':(1,0),'b':(2,0),'n':(3,0)})
    assert autoplay.click_move('a7a8n',(0,0,640),'white',screen,
        clicker=fake.click,sleep=lambda _:None)=='picker'
    assert len(clicks)==3
    assert keys==[('down','alt'),('up','alt')]
