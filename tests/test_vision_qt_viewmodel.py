"""Optional Qt/QML binding smoke test; no window, no engine or external session."""
import importlib.util
import unittest

@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 not installed')
class QtViewModelTests(unittest.TestCase):
    def test_qml_properties_and_notifications(self):
        from PySide6.QtCore import QCoreApplication, QUrl
        from PySide6.QtQml import QQmlEngine, QQmlComponent
        from visionbot.ui_controller import VisionUiController
        from visionbot.ui_state import SessionSnapshot
        from visionbot.telemetry import analysis_event
        from visionbot.qt_viewmodel import VisionViewModel

        app = QCoreApplication.instance() or QCoreApplication([])
        controller = VisionUiController()
        model = VisionViewModel(controller)
        engine = QQmlEngine()
        engine.rootContext().setContextProperty('visionModel', model)
        component = QQmlComponent(engine)
        component.setData(b'import QtQml; QtObject { property string phase: visionModel.phase; property string score: visionModel.score }', QUrl())
        obj = component.create()
        self.assertIsNotNone(obj, '\n'.join(e.toString() for e in component.errors()))
        self.assertEqual(obj.property('phase'), 'setup')
        self.assertEqual(obj.property('score'), '—')
        controller.update_session(SessionSnapshot(active=True))
        controller.submit(analysis_event({'mode':'external_uci','uci_score':{'kind':'cp','value':19}},
                          move='e2e4',fen='',ply=0,value=0.))
        list(controller.drain(24, 1))
        model.refresh()
        app.processEvents()
        self.assertEqual(obj.property('phase'), 'active')
        self.assertEqual(obj.property('score'), '+19 cp')
        controller.reset_analysis()
        model.refresh()
        self.assertEqual(obj.property('score'), '—')

if __name__ == '__main__':
    unittest.main()
