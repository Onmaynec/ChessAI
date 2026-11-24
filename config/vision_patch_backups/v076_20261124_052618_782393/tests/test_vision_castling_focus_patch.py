"""Vision v0.7.1 regression: castling, foreground handoff, checkpoint isolation."""
from __future__ import annotations

from pathlib import Path
from threading import Event
from types import SimpleNamespace

import numpy as np
import pytest

from botlab.session import parse_board
from visionbot.recognizer import START, ObservedTiles, VisionRecognizer, board_after
from visionbot.focus import Window
from visionbot import gui


def as_obs(board):
    occupied = [[p != '.' for p in row] for row in board]
    blank = [[np.zeros((48, 48), dtype=np.float32) for _ in range(8)] for _ in range(8)]
    return ObservedTiles(blank, occupied, [[float(x) for x in row] for row in occupied])


def detect_occupancy(observation, old, candidates):
    recognizer = VisionRecognizer.__new__(VisionRecognizer)
    # Fail rather than use color/shape matching as an accidental workaround.
    recognizer.score = lambda *_args: (_ for _ in ()).throw(AssertionError('unexpected fallback'))
    return recognizer.detect(observation, old, candidates)


@pytest.mark.parametrize('castle,other,rook', [
    ('e1g1', 'e1f1', 'h1f1'),
    ('e1c1', 'e1d1', 'a1d1'),
    ('e8g8', 'e8f8', 'h8f8'),
    ('e8c8', 'e8d8', 'a8d8'),
])
def test_castle_has_priority_over_partial_rook_or_king_move(castle, other, rook):
    # Full board is unambiguous; matching only a source/destination was not.
    old = parse_board('r3k2r/8/8/8/8/8/8/R3K2R')
    after = board_after(old, castle)
    result = detect_occupancy(as_obs(after), old, [castle, other, rook])
    assert result.move == castle, result
    assert 'full-board' in result.reason


def test_black_orientation_castle_from_actual_chesscom_snapshot_occupancy():
    # Screenshot from the reporter, Nov 23 2026, black's perspective.
    # The 64 squares are in normal chess orientation after reversing screen.
    # No original image is redistributed in the patch.
    after_occupancy = [
        'XXX.X..X',  # rank 8, black rooks / pieces
        'XX..XXXX',  # rank 7
        '..X..X..',  # rank 6
        '...XX...',  # rank 5
        '...X....',  # rank 4
        '...X....',  # rank 3
        'XX.XXXXX',  # rank 2
        'XX...XX.',  # rank 1; white king g1, rook f1
    ]
    after = [[('P' if char == 'X' else '.') for char in row] for row in after_occupancy]
    old = [row[:] for row in after]
    old[7][6] = '.'   # g1 empty before castle
    old[7][5] = '.'   # f1 empty before castle
    old[7][4] = 'K'   # e1 king before castle
    old[7][7] = 'R'   # h1 rook before castle
    result = detect_occupancy(as_obs(after), old, ['e1g1', 'e1f1', 'h1f1'])
    assert result.move == 'e1g1', result


def test_castling_followed_by_quick_other_side_move():
    old = parse_board('r3k2r/1p6/8/8/8/8/8/R3K2R')
    after_castle = board_after(old, 'e1g1')
    after_reply = board_after(after_castle, 'b7b6')
    result = detect_occupancy(as_obs(after_reply), old, ['e1g1', 'e1f1', 'h1f1'])
    assert result.move == 'e1g1', result
    assert 'reply' in result.reason


def test_unchanged_screen_not_assumed_castling():
    old = parse_board('r3k2r/8/8/8/8/8/8/R3K2R')
    assert detect_occupancy(as_obs(old), old, ['e1g1', 'e1f1']).move is None


def test_focus_handoff_launches_correct_window_for_both_colors(monkeypatch, tmp_path):
    events = []
    selected = Window(531, 'Play Computer - Chess.com - Microsoft Edge', 'msedge.exe')
    monkeypatch.setattr(gui, 'find_browser', lambda: selected)
    monkeypatch.setattr(gui, 'activate_browser', lambda win: events.append(('activate', win.hwnd)))
    monkeypatch.setattr('time.sleep', lambda *_args: None)

    class FakeThread:
        def __init__(self, *, target, name, daemon):
            self.target = target
        def start(self):
            self.target()
        def is_alive(self):
            return False

    class FakeAutoplay:
        def __init__(self, *args, expected_hwnd=None, **kwargs):
            events.append(('bot', expected_hwnd, args[3]))
        def run(self):
            events.append(('run',))

    monkeypatch.setattr(gui.threading, 'Thread', FakeThread)
    monkeypatch.setattr(gui, 'VisionAutoplay', FakeAutoplay)

    class Var:
        def __init__(self, v): self.v = v
        def get(self): return self.v

    class Root:
        def iconify(self): events.append(('minimize',))
        def deiconify(self): events.append(('restore',))

    root = tmp_path
    (root / 'checkpoints').mkdir()
    (root / 'checkpoints' / 'latest.pt').write_bytes(b'test-only')
    (root / 'engine.exe').write_bytes(b'test-only')
    (root / 'config').mkdir()

    for color in ('white', 'black'):
        app = gui.App.__new__(gui.App)
        app.worker = None
        app.consent = Var(True)
        app.train = Var(False)
        app.rect = (100, 100, 640)
        app.checkpoint = Var('latest.pt')
        app.engine = root / 'engine.exe'
        app.run = root
        app.ev = Event()
        app.color = Var(color)
        app.path = root / 'config' / 'vision_bot.json'
        app.root = Root()
        app.logline = lambda msg: None
        app.launch()
        assert events[-3:] == [('activate', 531), ('bot', 531, color), ('run',)]
        assert ('minimize',) not in events


def test_focus_activation_failure_does_not_click(monkeypatch, tmp_path):
    events = []
    monkeypatch.setattr(gui, 'find_browser', lambda: Window(78, 'Chess.com', 'msedge.exe'))
    def fail(_target): raise RuntimeError('Windows denied focus')
    monkeypatch.setattr(gui, 'activate_browser', fail)
    monkeypatch.setattr(gui.messagebox, 'showerror', lambda *args: events.append(('error', args[0])))
    class Var:
        def __init__(self,v): self.v=v
        def get(self):return self.v
    class Root:
        def iconify(self):events.append(('minimize',))
        def deiconify(self):events.append(('restore',))
    (tmp_path / 'checkpoints').mkdir()
    (tmp_path / 'checkpoints' / 'latest.pt').write_bytes(b'fake')
    (tmp_path / 'engine.exe').write_bytes(b'fake')
    app=gui.App.__new__(gui.App)
    app.worker=None;app.consent=Var(True);app.train=Var(False);app.rect=(100,100,640)
    app.checkpoint=Var('latest.pt');app.engine=tmp_path/'engine.exe';app.run=tmp_path
    app.ev=Event();app.color=Var('white');app.path=tmp_path/'vision_bot.json'
    app.root=Root();app.logline=lambda *_args:None
    app.launch()
    assert events==[('restore',),('error','Не удалось активировать Chess.com')]
    assert app.worker is None
