"""Optional Qt presentation adapter for the shared controller.

Read-only properties for the next UI migration; no gameplay commands are
exposed. Import this module only in an environment with PySide6 installed.
"""
from PySide6.QtCore import QObject, Property, Signal, Slot
from .ui_controller import VisionUiController
from .board_projection import BoardHistory

class VisionViewModel(QObject):
    sessionChanged = Signal()
    analysisChanged = Signal()
    journalChanged = Signal()
    boardChanged = Signal()

    def __init__(self, controller: VisionUiController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._session = controller.session
        self._analysis = controller.analysis
        self._journal = []
        self._visible = []
        self._board = BoardHistory()

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

    @Property('QVariantMap', notify=boardChanged)
    def boardView(self):
        return self._board.view()

    @Property(int, notify=boardChanged)
    def historyCount(self):
        return len(self._board.frames)

    @Property(int, notify=boardChanged)
    def historyIndex(self):
        return self._board.index

    @Property(bool, notify=boardChanged)
    def blackOrientation(self):
        return self._board.black

    @Slot(int)
    def goHistory(self, index):
        self._board.go(index)
        self.boardChanged.emit()

    @Slot()
    def flipBoard(self):
        self._board.black = not self._board.black
        self.boardChanged.emit()

    @Slot(str)
    def selectCandidate(self, move):
        if self._board.select(move):
            self.boardChanged.emit()

    def set_journal(self, events):
        events = list(events)[-600:]
        self._board.replace(e.analysis for e in events)
        self.boardChanged.emit()
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
