"""v0.7.6: live analysis, bounded logs, deep search and no-minimize UI."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from visionbot.telemetry import (
    PREFIX, analysis_event, read_event, formatted_analysis,
    rotate_and_append, position_summary, rectangles_overlap
)
from visionbot.focus import focus_browser_from_panel, Window
from neural.agent import START_FEN
from neural.intelligence import choose_move, SearchUnavailable


def test_analysis_event_roundtrip_displays_real_candidate_values():
    d = {'mode':'neural_plus_cpp_search','search_depth':7, 'shallow_depth':4,
         'deep_search':True, 'deep_evaluated_moves':4, 'evaluated_moves':20,
         'search_time_s':4.123, 'engine_cp':38, 'policy':0.12,
         'expected_reply':'c7c5','opening_name':'Italian / Giuoco Piano',
         'illustrative_line':['e2e4','c7c5','g1f3'],
         'motifs':['Дебютная подготовка'],
         'candidates':[{'move':'e2e4','cp':38,'policy':0.12,'expected_reply':'c7c5'}]}
    raw=analysis_event(d,move='e2e4',fen=START_FEN,ply=0,value=0.03)
    assert raw.startswith(PREFIX)
    packet=read_event(raw)
    lines=formatted_analysis(packet)
    assert any('7 полуходов' in line for line in lines)
    assert any('c7c5' in line for line in lines)
    assert any('e2e4' in line for line in lines)
    assert any('Italian' in line for line in lines)
    assert any('20 ходов' in line for line in lines)
    assert read_event('Ход подтвержден') is None


def test_diagnostic_log_rotates_instead_of_growing(tmp_path):
    path=tmp_path/'vision_logs'/'vision_current.log'
    rotate_and_append(path, 'first'+'x'*80,cap=50)
    rotate_and_append(path, 'second',cap=50)
    assert 'second' in path.read_text(encoding='utf-8')
    assert 'first' in path.with_suffix('.previous.log').read_text(encoding='utf-8')


def test_position_summary_is_from_fen_not_imagined():
    s=position_summary(START_FEN)
    assert 'Материал: белые 39, чёрные 39' in s
    assert 'Очередь: белые' in s
    assert 'Эндшпиль' not in s
    assert 'эндшпиль' in position_summary('7k/8/8/8/8/8/8/K7 b - - 0 1')


def test_focus_is_returned_only_from_our_panel(monkeypatch):
    from visionbot import focus
    browser=Window(42,'Chess.com - Computer','msedge.exe')
    activated=[]
    monkeypatch.setattr(focus,'our_panel_is_foreground',lambda:False)
    monkeypatch.setattr(focus,'activate_browser',lambda b:activated.append(b.hwnd))
    assert not focus_browser_from_panel(browser)
    assert not activated
    monkeypatch.setattr(focus,'our_panel_is_foreground',lambda:True)
    monkeypatch.setattr(focus,'ensure_browser_foreground',lambda hwnd: activated.append(('check',hwnd)))
    assert focus_browser_from_panel(browser)
    assert activated==[42,('check',42)]


def test_docking_does_not_cover_board_or_minimize_window():
    from visionbot.gui import App
    class Root:
        def __init__(self):self.positions=[]
        def update_idletasks(self):pass
        def winfo_width(self):return 565
        def winfo_screenwidth(self):return 1650
        def winfo_screenheight(self):return 920
        def winfo_height(self):return 830
        def geometry(self,g):self.positions.append(g)
    app=App.__new__(App);app.root=Root();app.rect=(222,144,829)
    app.logline=lambda msg:None
    app.place_away_from_board()
    assert app.root.positions==['+1061+90']


def test_deep_search_is_real_and_weights_are_unchanged(tmp_path):
    import torch
    from neural.model import ChessNet
    from neural.selfplay import ChessBridge
    engine=Path('build/chessai')
    if not engine.is_file():pytest.skip('C++ engine required')
    model=ChessNet(16,1).eval()
    original=hashlib.sha256(torch.nn.utils.parameters_to_vector(model.parameters()).detach().numpy().tobytes()).hexdigest()
    with ChessBridge(engine) as bridge:
        state=bridge.new(444,START_FEN)
        move,value,report=choose_move(model,state,bridge,engine,history_fens=[START_FEN],depth=3,
                                      deep_depth=6,shortlist=2,deep_timeout=16)
        assert move in state['legal_moves']
    assert report['mode']=='neural_plus_cpp_search'
    assert report['search_depth']==7, report
    assert report['deep_evaluated_moves']>=2
    assert report['expected_reply'] is not None
    assert len(report['illustrative_line'])>=2
    after=hashlib.sha256(torch.nn.utils.parameters_to_vector(model.parameters()).detach().numpy().tobytes()).hexdigest()
    assert original==after


def test_deep_timeout_keeps_shallow_evaluations(monkeypatch):
    import neural.intelligence as intel
    import torch
    from neural.model import ChessNet
    from neural.selfplay import ChessBridge
    engine=Path('build/chessai')
    if not engine.is_file():pytest.skip('C++ engine required')
    orig=intel.evaluate_fens
    def stub(engine,positions,*,depth=4,timeout=35):
        if depth==6:
            raise SearchUnavailable('simulated controlled timeout')
        return orig(engine,positions,depth=depth,timeout=timeout)
    monkeypatch.setattr(intel,'evaluate_fens',stub)
    with ChessBridge(engine) as bridge:
        state=bridge.new(444,START_FEN)
        move,value,report=intel.choose_move(ChessNet(16,1).eval(),state,bridge,engine,
                                            depth=3,deep_depth=6,shortlist=2)
        assert move in state['legal_moves']
        assert report['deep_search'] is False
        assert 'simulated controlled timeout' in report['deep_warning']
        assert report['search_depth']==4


def test_topmost_panel_cannot_cover_calibrated_board():
    assert rectangles_overlap((700,100,600,700),(200,150,800,800))
    assert not rectangles_overlap((1020,100,560,750),(200,150,800,800))
    assert not rectangles_overlap((1000,100,560,750),(200,150,800,800))  # touching edge
