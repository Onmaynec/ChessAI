import importlib.util
import tempfile
import unittest
from pathlib import Path
from visionbot.qt_preview import fixture_messages, make_controller, replay_messages, MAX_LINE

class ReplayTests(unittest.TestCase):
    def test_empty(self):
        c, events = make_controller()
        self.assertFalse(c.session.active)
        self.assertEqual(c.analysis.fen, '')
        self.assertEqual(events, [])

    def test_fixture(self):
        c, events = make_controller(fixture_messages(), True)
        self.assertEqual(c.session.model, 'QA FIXTURE')
        self.assertFalse(c.session.active)
        self.assertEqual(c.analysis.score, '+32 cp')
        self.assertEqual(c.analysis.depth, 12)
        self.assertEqual(len(events), 4)
        self.assertEqual(events[1].category, 'analysis')

    def test_bounded_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'messages.log'
            path.write_bytes(b'old\n' * 605 + b'last\n')
            result = replay_messages(path)
            self.assertEqual(len(result), 600)
            self.assertEqual(result[-1], 'last')

    def test_oversized_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'messages.log'
            path.write_bytes(b'x'*(MAX_LINE+100) + b'\nafter\n')
            result = replay_messages(path)
            self.assertEqual(len(result), 2)
            self.assertIn('oversized', result[0])
            self.assertEqual(result[1], 'after')

@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 not installed')
class QmlWorkspaceTests(unittest.TestCase):
    def test_workspace_load_and_navigation(self):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        os.environ.setdefault('QT_QUICK_BACKEND', 'software')
        from PySide6.QtGui import QGuiApplication
        from visionbot.qt_preview import create_engine
        app = QGuiApplication.instance() or QGuiApplication([])
        c, events = make_controller(fixture_messages(), True)
        engine, model = create_engine(c, events, 'QA FIXTURE')
        try:
            self.assertEqual(len(engine.rootObjects()), 1)
            window = engine.rootObjects()[0]
            self.assertEqual(window.objectName(), 'visionWorkspace')
            from PySide6.QtCore import QMetaObject, Q_ARG
            for mode in ('compact','expanded','standard'):
                self.assertTrue(QMetaObject.invokeMethod(window,'switchMode',Q_ARG('QVariant',mode)))
                app.processEvents()
                self.assertEqual(window.property('mode'),mode)
            for key in ('metrics','board','analysis','journal'):
                self.assertTrue(QMetaObject.invokeMethod(window,'openOverlay',Q_ARG('QVariant',key)))
                app.processEvents()
                self.assertTrue(any(w.objectName() == 'overlay_'+key and w.isVisible()
                                    for w in app.topLevelWindows()))
            for width in (1200, 800, 560):
                window.setWidth(width)
                for page in range(4):
                    window.setProperty('page', page)
                    app.processEvents()
                    self.assertEqual(window.property('page'), page)
            self.assertEqual(model.historyCount, 2)
            self.assertEqual(model.historyIndex, 1)
            self.assertEqual(model.boardView['turn'], 'Чёрные')
            model.goHistory(0)
            self.assertEqual(model.boardView['move'], 'e2e4')
            model.selectCandidate('d2d4')
            self.assertEqual(model.boardView['arrow']['x1'], 3)
            model.flipBoard()
            self.assertEqual(model.boardView['cells'][0]['square'], 'h1')
            model.filterJournal('синтетический', 'all')
            self.assertEqual(len(model.journal), 0)
            model.filterJournal('', 'analysis')
            self.assertEqual(len(model.journal), 2)
            self.assertEqual(model.journalTotal, 4)
            self.assertEqual(model.journalCategory, 'analysis')
            self.assertEqual(model.journalQuery, '')
        finally:
            for window in engine.rootObjects():
                window.close()
            app.processEvents()

if __name__ == '__main__':
    unittest.main()
