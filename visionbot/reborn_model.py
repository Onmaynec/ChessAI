"""Qt-native session preparation and local telemetry workspace.

No Tk imports. Native session execution is delegated to QtSession.
"""
from pathlib import Path
from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
from .run_catalog import discover_runs, checkpoint_path, engine_path
from .qt_preview import replay_messages, make_controller
from .ui_state import SessionSnapshot

class RebornModel(QObject):
    changed = Signal()

    def __init__(self, root, controller, viewmodel, parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self.controller = controller
        self.viewmodel = viewmodel
        self._runs = []
        self._run = ''
        self._model = ''
        self._source = 'LOCAL / IDLE'
        self._message = ''
        self.refreshRuns()

    @Property('QVariantList', notify=changed)
    def runs(self):
        return [r['id'] for r in self._runs]

    @Property(str, notify=changed)
    def selectedRun(self):
        return self._run

    @Property(str, notify=changed)
    def selectedModel(self):
        return self._model

    @Property('QVariantList', notify=changed)
    def models(self):
        return next((r['models'] for r in self._runs if r['id']==self._run),[])

    @Property(str, notify=changed)
    def source(self):
        return self._source

    @Property(str, notify=changed)
    def message(self):
        return self._message

    @Property(bool, notify=changed)
    def engineAvailable(self):
        return engine_path(self.root).is_file()

    @Property(bool, notify=changed)
    def modelAvailable(self):
        try:
            checkpoint_path(self.root,self._run,self._model)
            return True
        except (ValueError,OSError):
            return False

    @Slot()
    def refreshRuns(self):
        try:
            self._runs = discover_runs(self.root)
            if self._run not in self.runs:
                self._run = self.runs[0] if self.runs else ''
            if self._model not in self.models:
                self._model = 'latest.pt' if 'latest.pt' in self.models else self.models[0] if self.models else ''
            self._message = '' if self._runs else 'Нет локальных checkpoint. Перенесите папку runs из прежней установки.'
        except OSError as exc:
            self._message = str(exc)
        self.changed.emit()

    @Slot(str)
    def selectRun(self, name):
        if name in self.runs:
            self._run = name
            self._model = 'latest.pt' if 'latest.pt' in self.models else self.models[0] if self.models else ''
            self.changed.emit()

    @Slot(str)
    def selectModel(self, name):
        if name in self.models:
            self._model = name
            self.changed.emit()

    @Slot(QUrl)
    def importReplay(self, url):
        if not url.isLocalFile():
            self._message = 'Выберите локальный файл.'
            self.changed.emit()
            return
        try:
            path = Path(url.toLocalFile())
            replay, journal = make_controller(replay_messages(path))
            self.controller.reset_analysis()
            self.controller.analysis = replay.analysis
            self.controller.update_session(SessionSnapshot())
            self.viewmodel.set_journal(journal)
            self.viewmodel.refresh()
            self._source = 'LOCAL REPLAY: '+path.name
            self._message = f'Загружено записей: {len(journal)}'
        except (OSError,ValueError) as exc:
            self._message = str(exc)
        self.changed.emit()

    @Slot()
    def clearReplay(self):
        self.controller.reset_analysis()
        self.viewmodel.set_journal([])
        self.viewmodel.refresh()
        self._source = 'LOCAL / IDLE'
        self._message = ''
        self.changed.emit()
