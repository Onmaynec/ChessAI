"""Optional Qt presentation adapter for the shared controller.

Read-only properties for the next UI migration; no gameplay commands are
exposed. Import this module only in an environment with PySide6 installed.
"""
from PySide6.QtCore import QObject, Property, Signal, Slot
from .ui_controller import VisionUiController
from .board_projection import BoardHistory
from .journal_index import JournalIndex, CATEGORIES

class VisionViewModel(QObject):
    sessionChanged = Signal()
    analysisChanged = Signal()
    journalChanged = Signal()
    boardChanged = Signal()
    boardCellsChanged = Signal()
    journalFilterChanged = Signal()

    def __init__(self, controller: VisionUiController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._session = controller.session
        self._analysis = controller.analysis
        self._journal = JournalIndex()
        self._visible = []
        self._journal_query = ''
        self._journal_category = 'all'
        self._board = BoardHistory()
        self._board_view = self._board.view()
        self._board_cells = self._board_view['cells']

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
        return self._journal.total

    @Property('QVariantMap', notify=boardChanged)
    def boardView(self):
        return self._board_view

    @Property('QVariantList', notify=boardCellsChanged)
    def boardCells(self):
        return self._board_cells

    def _publish_board(self):
        view = self._board.view()
        if view['cells'] != self._board_cells:
            self._board_cells = view['cells']
            self.boardCellsChanged.emit()
        self._board_view = view
        self.boardChanged.emit()

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
        if self._board.index != index:
            self._board.go(index)
            self._publish_board()

    @Slot()
    def flipBoard(self):
        self._board.black = not self._board.black
        self._publish_board()

    @Slot(str)
    def selectCandidate(self, move):
        if move != self._board.selected and self._board.select(move):
            self._publish_board()

    def set_journal(self, events):
        events = list(events)[-600:]
        self._board.replace(e.analysis for e in events)
        self._publish_board()
        self._journal.replace(events)
        self.filterJournal(self._journal_query, self._journal_category, force=True)

    @Property(str, notify=journalFilterChanged)
    def journalQuery(self):
        return self._journal_query

    @Property(str, notify=journalFilterChanged)
    def journalCategory(self):
        return self._journal_category

    @Slot(str, str)
    def filterJournal(self, query, category, force=False):
        category = category if category in CATEGORIES else 'all'
        changed = (query,category) != (self._journal_query,self._journal_category)
        self._journal_query = query
        self._journal_category = category
        if changed:
            self.journalFilterChanged.emit()
        result = self._journal.filter(query,category)
        if force or result != self._visible:
            self._visible = result
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
