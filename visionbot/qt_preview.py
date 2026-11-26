"""Standalone read-only Qt Quick workspace. No automation or worker is started."""
from __future__ import annotations
import argparse
from pathlib import Path
from collections import deque
from .ui_controller import VisionUiController
from .ui_state import SessionSnapshot
from .telemetry import analysis_event

ROOT = Path(__file__).resolve().parents[1]
MAX_LINE = 262144
MAX_EVENTS = 600
MAX_REPLAY_BYTES = 16 * 1024 * 1024

def replay_messages(path: Path) -> list[str]:
    """Read the last 600 bounded UTF-8 lines, at most 16 MiB of input, preserving their order."""
    messages = deque()
    retained = 0
    with path.open('rb') as stream:
        while True:
            line = stream.readline(MAX_LINE + 1)
            if not line:
                break
            if len(line) > MAX_LINE:
                while line and not line.endswith(b'\n'):
                    line = stream.readline(MAX_LINE + 1)
                line = 'ОШИБКА: oversized replay line skipped'.encode('utf-8')
            messages.append(line)
            retained += len(line)
            while len(messages) > MAX_EVENTS or retained > MAX_REPLAY_BYTES:
                retained -= len(messages.popleft())
    return [line.decode('utf-8', errors='replace').rstrip('\r\n') for line in messages]

def fixture_messages() -> list[str]:
    return ['QA FIXTURE: synthetic local preview, no running session',
            analysis_event({'mode':'external_uci','uci_score':{'kind':'cp','value':32},
                            'search_depth':12,'search_time_s':0.24,
                             'illustrative_line':['e2e4','e7e5'],'line_kind':'searched_pv',
                             'candidates':[{'move':'d2d4','cp':20},{'move':'g1f3','cp':12}]},
                           move='e2e4',fen='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
                           ply=0,value=0.),
            analysis_event({'mode':'external_uci','uci_score':{'kind':'cp','value':32},
                            'search_depth':12,'search_time_s':0.24,
                            'illustrative_line':['e7e5','g1f3'],'line_kind':'searched_pv',
                            'candidates':[{'move':'c7c5','cp':25},{'move':'e7e6','cp':10}]},
                           move='e7e5',fen='rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1',
                           ply=1,value=0.),
            'QA FIXTURE: end of sample']

def make_controller(messages=(), fixture=False):
    controller = VisionUiController()
    if fixture:
        controller.update_session(SessionSnapshot(model='QA FIXTURE'))
    journal = []
    for raw in messages:
        controller.submit(raw)
        for event in controller.drain(24, 1):
            journal.append(event)
    return controller, journal

def create_engine(controller, journal, source, preferences_path=None, *, reborn=False):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle
    QQuickStyle.setStyle('Basic')
    from .qt_viewmodel import VisionViewModel
    from .qt_workspace import WorkspaceModel
    from . import design
    engine = QQmlApplicationEngine()
    model = VisionViewModel(controller, engine)
    model.set_journal(journal)
    context = engine.rootContext()
    context.setContextProperty('visionModel', model)
    workspace = WorkspaceModel(preferences_path, engine)
    context.setContextProperty('workspaceModel', workspace)
    context.setContextProperty('sourceLabel', source)
    context.setContextProperty('appVersion', (ROOT/'VERSION').read_text(encoding='utf-8').strip())
    context.setContextProperty('theme', {
        'bg': design.BG, 'panel': design.PANEL, 'field': design.FIELD,
        'border': design.BORDER, 'text': design.TEXT, 'muted': design.MUTED,
        'dim': design.DIM, 'accent': design.ACCENT, 'hover': design.HOVER,
        'active': design.ACTIVE, 'green': design.GREEN, 'red': design.RED,
        'warning': design.WARNING, 'font': design.FONT, 'mono': design.MONO,
        'radius': design.RADIUS, 'typeScale': design.TYPE_SCALE,
        'motion': design.MOTION, 'surfaceHover': design.SURFACE_HOVER,
        'track': design.TRACK,
    })
    if reborn:
        from .reborn_model import RebornModel
        reborn_model = RebornModel(ROOT, controller, model, engine)
        context.setContextProperty('rebornModel', reborn_model)
        from .qt_session import QtSession
        session = QtSession(ROOT, controller, model, reborn_model, engine)
        context.setContextProperty('sessionModel', session)
    entry = 'Reborn.qml' if reborn else 'Main.qml'
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name('qml')/entry)))
    return engine, model

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--fixture', action='store_true')
    group.add_argument('--replay', type=Path, help='Local UTF-8 raw telemetry / text lines; no live connection')
    parser.add_argument('--no-save', action='store_true', help='Use temporary in-memory UI preferences')
    args = parser.parse_args()
    try:
        from PySide6.QtGui import QGuiApplication
    except ImportError:
        parser.exit(2, 'Install optional dependencies: python -m pip install -r requirements-vision-qt.txt\n')
    try:
        messages = fixture_messages() if args.fixture else replay_messages(args.replay) if args.replay else []
    except OSError as exc:
        parser.error(str(exc))
    controller, journal = make_controller(messages, args.fixture)
    source = 'QA FIXTURE' if args.fixture else 'LOCAL REPLAY' if args.replay else 'OFFLINE / IDLE'
    app = QGuiApplication([])
    preferences_path = None if args.no_save or args.fixture else ROOT/'config'/'vision_qt_workspace.json'
    engine, model = create_engine(controller, journal, source, preferences_path)
    if not engine.rootObjects():
        return 1
    return app.exec()

if __name__ == '__main__':
    raise SystemExit(main())
