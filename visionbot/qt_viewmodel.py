"""Optional Qt presentation adapter for the shared controller.

Read-only properties for the next UI migration; no gameplay commands are
exposed. Import this module only in an environment with PySide6 installed.
"""
from PySide6.QtCore import QObject, Property, Signal, Slot
from .ui_controller import VisionUiController

class VisionViewModel(QObject):
    sessionChanged = Signal()
    analysisChanged = Signal()

    def __init__(self, controller: VisionUiController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._session = controller.session
        self._analysis = controller.analysis

    @Property(str, notify=sessionChanged)
    def phase(self):
        return self._session.phase

    @Property(str, notify=sessionChanged)
    def model(self):
        return self._session.model

    @Property(bool, notify=sessionChanged)
    def active(self):
        return self._session.active

    @Property(str, notify=analysisChanged)
    def fen(self):
        return self._analysis.fen

    @Property(str, notify=analysisChanged)
    def score(self):
        return self._analysis.score

    @Property(str, notify=analysisChanged)
    def move(self):
        return self._analysis.move

    @Property(str, notify=analysisChanged)
    def depth(self):
        return str(self._analysis.depth) if self._analysis.depth is not None else '—'

    @Slot()
    def refresh(self):
        """Call on the Qt GUI thread after the host updates the controller."""
        if self._session != self.controller.session:
            self._session = self.controller.session
            self.sessionChanged.emit()
        if self._analysis != self.controller.analysis:
            self._analysis = self.controller.analysis
            self.analysisChanged.emit()
