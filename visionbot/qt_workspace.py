"""Qt adapter for preview-only workspace geometry and preferences."""
from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtGui import QGuiApplication
from .workspace_preferences import WorkspacePreferences, MODES, PANELS

class WorkspaceModel(QObject):
    errorChanged = Signal()
    motionChanged = Signal()

    def __init__(self, path=None, parent=None):
        super().__init__(parent)
        self.preferences = WorkspacePreferences(path)
        self._error = ''

    @Property(str, notify=errorChanged)
    def error(self):
        return self._error

    def _save(self):
        try:
            self.preferences.save()
            error = ''
        except OSError as exc:
            error = str(exc)
        if error != self._error:
            self._error = error
            self.errorChanged.emit()

    @Property(bool, notify=motionChanged)
    def reducedMotion(self):
        return self.preferences.data.get('reduced_motion', False)

    @Slot(bool)
    def setReducedMotion(self, value):
        if value != self.reducedMotion and self.preferences.set_reduced_motion(value):
            self.motionChanged.emit()
            self._save()

    @Slot(result=str)
    def initialMode(self):
        return self.preferences.data['mode']

    @Slot(str, result='QVariantList')
    def geometry(self, key):
        if key not in (*MODES,*PANELS):
            return []
        app = QGuiApplication.instance()
        screens = app.screens()
        primary = app.primaryScreen()
        if primary is not None:
            screens = [primary] + [s for s in screens if s != primary]
        rects = []
        for screen in screens:
            rect = screen.availableGeometry()
            rects.append((rect.x(),rect.y(),rect.width(),rect.height()))
        return self.preferences.geometry(key,rects)

    @Slot(str,int,int,int,int)
    def record(self,key,x,y,w,h):
        if self.preferences.record(key,(x,y,w,h)):
            self._save()

    @Slot(str)
    def setMode(self,mode):
        if self.preferences.set_mode(mode):
            self._save()

    @Slot(str,result=bool)
    def pinned(self,key):
        return self.preferences.data['topmost'].get(key,False)

    @Slot(str,bool)
    def setPinned(self,key,value):
        if self.preferences.set_topmost(key,value):
            self._save()
