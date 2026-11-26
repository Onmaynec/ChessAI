import importlib.util
import tempfile
import unittest
from pathlib import Path
from visionbot.run_catalog import discover_runs, checkpoint_path, engine_path

class RunCatalogTests(unittest.TestCase):
    def test_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(discover_runs(Path(tmp)),[])

    def test_real_runs_and_model_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,models in [('run_001',['best.pt']),('run_002',['latest.pt','best.pt']),('empty',[])]:
                folder=root/'runs'/name/'checkpoints'
                folder.mkdir(parents=True)
                for model in models:
                    (folder/model).write_bytes(b'fixture')
            self.assertEqual(discover_runs(root),[{'id':'run_002','models':['best.pt','latest.pt']},{'id':'run_001','models':['best.pt']}])
            self.assertEqual(checkpoint_path(root,'run_002','latest.pt'),root/'runs'/'run_002'/'checkpoints'/'latest.pt')
            self.assertEqual((root/'runs'/'run_002'/'checkpoints'/'latest.pt').read_bytes(),b'fixture')

    def test_invalid_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for run,model in [('../outside','latest.pt'),('run','../latest.pt'),('run','file.json')]:
                with self.assertRaises(ValueError):
                    checkpoint_path(root,run,model)
            with self.assertRaises(FileNotFoundError):
                checkpoint_path(root,'run','latest.pt')

    def test_engine_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertEqual(engine_path(root),root/'build'/'Release'/'chessai.exe')
            engine=root/'build'/'chessai.exe'
            engine.parent.mkdir()
            engine.touch()
            self.assertEqual(engine_path(root),engine)

@unittest.skipUnless(importlib.util.find_spec('PySide6'),'PySide6 not installed')
class QtRebornTests(unittest.TestCase):
    def test_reborn_load_and_authorization_gate(self):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        os.environ.setdefault('QT_QUICK_BACKEND','software')
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QObject
        from visionbot.qt_preview import create_engine,make_controller
        app=QApplication.instance() or QApplication([])
        controller,journal=make_controller()
        engine,model=create_engine(controller,journal,'QT REBORN',reborn=True)
        try:
            self.assertEqual(len(engine.rootObjects()),1)
            window=engine.rootObjects()[0]
            self.assertEqual(window.objectName(),'rebornWorkspace')
            session=engine.rootContext().contextProperty('sessionModel')
            session.start(False,False)
            self.assertFalse(session.active)
            self.assertIn('подтвердить',session.status)
            for width in (1260,1040,620):
                window.resize(width,650)
                for page in range(3):
                    window.setProperty('page',page)
                    app.processEvents()
                    self.assertEqual(window.property('page'),page)
            self.assertIsNotNone(window.findChild(QObject,'modelPicker'))
        finally:
            for window in engine.rootObjects():
                window.close()
            app.processEvents()

if __name__=='__main__':
    unittest.main()
