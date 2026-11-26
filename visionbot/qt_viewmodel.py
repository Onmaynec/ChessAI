"""Optional Qt presentation adapter for the shared controller.

Read-only properties for the next UI migration; no gameplay commands are
exposed. Import this module only in an environment with PySide6 installed.
"""
from PySide6.QtCore import QObject, Property, Signal, Slot
from .ui_controller import VisionUiController

class VisionViewModel(QObject):
    sessionChanged = Signal()
    analysisChanged = Signal()
    journalChanged = Signal()

    def __init__(self, controller: VisionUiController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._session = controller.session
        self._analysis = controller.analysis
        self._journal = []
        self._visible = []

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

    @Property(str, notify=sessionChanged)
    def side(self):
        return self._session.side if self._session.model and self._session.model != 'QA FIXTURE' else '—'

    @Property(str, notify=analysisChanged)
    def reply(self):
        return self._analysis.reply or '—'

    @Property(str, notify=analysisChanged)
    def searchTime(self):
        return f'{self._analysis.seconds:.3f} s' if self._analysis.seconds is not None else '—'

    @Property('QVariantList', notify=journalChanged)
    def journal(self):
        return self._visible

    @Property(int, notify=journalChanged)
    def journalTotal(self):
        return len(self._journal)

    def set_journal(self, events):
        self._journal = [{'category': e.category, 'text': e.text} for e in events][-600:]
        self.filterJournal('', 'all')

    @Slot(str, str)
    def filterJournal(self, query, category):
        q = query.casefold().strip()
        self._visible = [row for row in self._journal
                         if (category == 'all' or row['category'] == category)
                         and (not q or q in row['text'].casefold())]
        self.journalChanged.emit()

    @Slot()
    def refresh(self):
        """Call on the Qt GUI thread after the host updates the controller."""
        if self._session != self.controller.session:
            self._session = self.controller.session
            self.sessionChanged.emit()
        if self._analysis != self.controller.analysis:
            self._analysis = self.controller.analysis
            self.analysisChanged.emit()
