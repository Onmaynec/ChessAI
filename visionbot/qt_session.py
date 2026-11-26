"""Native Qt host for explicitly authorized computer-only tests.

The existing worker handles vision, recovery and move confirmation. Qt owns
only presentation, capture selection and session lifecycle. No Tk is loaded.
"""
from __future__ import annotations
import ctypes
import json
import sys
import threading
from collections import deque
from pathlib import Path
from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer
from PySide6.QtGui import QGuiApplication, QWindow
from .run_catalog import checkpoint_path, engine_path
from .ui_state import SessionSnapshot
from .telemetry import rectangles_overlap, rotate_and_append

def native_window_rect(window):
    """Return physical Windows bounds, or fail closed."""
    if sys.platform != 'win32':
        raise RuntimeError('Native Vision sessions require Windows')
    from ctypes import wintypes
    api = ctypes.WinDLL('user32',use_last_error=True)
    api.GetWindowRect.argtypes = [wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    api.GetWindowRect.restype = wintypes.BOOL
    api.GetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    api.GetAwarenessFromDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    api.GetAwarenessFromDpiAwarenessContext.restype = ctypes.c_int
    if api.GetAwarenessFromDpiAwarenessContext(api.GetThreadDpiAwarenessContext()) != 2:
        raise RuntimeError('Per-monitor DPI awareness is required for safe capture')
    rect = wintypes.RECT()
    if not api.GetWindowRect(int(window.winId()),ctypes.byref(rect)):
        raise OSError('Cannot read native window bounds')
    return rect.left,rect.top,rect.right-rect.left,rect.bottom-rect.top

def valid_region(rect, width, height):
    return (isinstance(rect,(tuple,list)) and len(rect)==3
            and all(type(v) is int for v in rect)
            and rect[0]>=0 and rect[1]>=0 and rect[2]>=320
            and rect[0]+rect[2]<=width and rect[1]+rect[2]<=height)

class QtSession(QObject):
    changed = Signal()

    def __init__(self, root, controller, model, catalog, parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self.controller = controller
        self.model = model
        self.catalog = catalog
        self.path = self.root/'config'/'vision_bot.json'
        self._rect = None
        self._side = 'white'
        self._status = 'Ожидание настройки'
        self._busy = False
        self._worker = None
        self._stop = threading.Event()
        self._journal = deque(maxlen=600)
        self._log_path = None
        self._screen = None
        try:
            cfg = json.loads(self.path.read_text(encoding='utf-8'))
            rect = cfg.get('rect')
            if isinstance(rect,list) and len(rect)==3 and all(type(x) is int for x in rect):
                self._rect = tuple(rect)
            if cfg.get('color') in ('white','black'):
                self._side = cfg['color']
        except (OSError,ValueError,TypeError,AttributeError):
            pass
        self.timer = QTimer(self)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self.pump)
        self.timer.start()

    @Property(bool,notify=changed)
    def active(self):
        return self._worker is not None and self._worker.is_alive()

    @Property(bool,notify=changed)
    def busy(self):
        return self._busy or self.active

    @Property(str,notify=changed)
    def region(self):
        return f'{self._rect[0]}, {self._rect[1]} · {self._rect[2]} × {self._rect[2]} px' if self._rect else 'Не выбрана'

    @Property(str,notify=changed)
    def side(self):
        return self._side

    @Property(str,notify=changed)
    def status(self):
        return self._status

    def _notice(self, message):
        self._status = str(message)
        self.changed.emit()

    @Slot(str)
    def setSide(self, side):
        if not self.busy and side in ('white','black'):
            self._side = side
            self.changed.emit()

    def _save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp = self.path.with_suffix('.qt.tmp')
        tmp.write_text(json.dumps({'rect':self._rect,'color':self._side},indent=2),encoding='utf-8')
        tmp.replace(self.path)

    @Slot()
    def calibrate(self):
        if self.busy:
            return
        if sys.platform != 'win32':
            self._notice('Калибровка доступна на Windows')
            return
        self._busy=True
        self.changed.emit()
        windows = [w for w in QGuiApplication.topLevelWindows() if w.isVisible()]
        for w in windows:
            w.hide()
        def capture():
            try:
                from .qt_calibration import select_region
                from .autoplay import Screen
                screen=Screen()
                try:
                    frame=screen.full()
                finally:
                    screen.close()
                rect=select_region(frame)
                if rect is not None:
                    old=self._rect
                    self._rect=rect
                    try:
                        self._save()
                    except OSError:
                        self._rect=old
                        raise
                    self._notice('Область сохранена')
                else:
                    self._notice('Калибровка отменена')
            except Exception as exc:
                self._notice(exc)
            finally:
                for w in windows:
                    w.show()
                self._busy=False
                self.changed.emit()
        QTimer.singleShot(650,capture)

    def _safe_windows(self):
        if not self._screen or not self._rect:
            return False
        left,top,_,_=self._screen
        x,y,s=self._rect
        board=(left+x,top+y,s,s)
        for window in QGuiApplication.topLevelWindows():
            if window.isVisible() and window.visibility() != QWindow.Visibility.Minimized:
                if rectangles_overlap(native_window_rect(window),board):
                    return False
        return True

    @Slot(bool,bool)
    def start(self, authorized, resume):
        if self.busy:
            return
        if not authorized:
            self._notice('Нужно подтвердить разрешённый тест против компьютерного бота')
            return
        if sys.platform != 'win32':
            self._notice('Vision-сессия доступна только на Windows')
            return
        try:
            from .autoplay import Screen, VisionAutoplay
            from .external_session import computer_title
            from .focus import find_browser, activate_browser
            engine=engine_path(self.root)
            checkpoint=checkpoint_path(self.root,self.catalog.selectedRun,self.catalog.selectedModel)
            if not engine.is_file():
                raise FileNotFoundError(engine)
            probe=Screen()
            try:
                mon=probe.monitor
                self._screen=tuple(mon[k] for k in ('left','top','width','height'))
            finally:
                probe.close()
            if not valid_region(self._rect,*self._screen[2:]):
                raise ValueError('Выберите область доски заново')
            if not self._safe_windows():
                raise ValueError('Переместите все окна Vision Bot за пределы доски')
            browser=find_browser()
            if not computer_title(browser.title):
                raise ValueError('Требуется окно разрешённой компьютерной игры; игры с людьми запрещены')
            self._save()
            run=self.root/'runs'/self.catalog.selectedRun
            self._log_path=run/'vision_logs'/'vision_current.log'
            self._stop.clear()
            self._journal.clear()
            self.controller.reset_analysis()
            self.model.set_journal([])
            self.model.refresh()
            activate_browser(browser)
            worker=VisionAutoplay(engine,checkpoint,run,self._side,self._rect,
                                  self.controller.submit,self._stop,
                                  expected_hwnd=browser.hwnd,browser_window=browser,
                                  resume=resume,analysis_level='deep',computer_only=True)
            def execute():
                if not self._stop.wait(.6):
                    try:
                        worker.run()
                    except Exception as exc:
                        self.controller.submit('ОШИБКА: '+str(exc))
            self._worker=threading.Thread(target=execute,name='VisionQtWorker',daemon=False)
            self._worker.start()
            self._notice('Запущен разрешённый тест · ESC — остановка')
        except Exception as exc:
            self._notice(exc)

    @Slot()
    def stop(self):
        if self.active and not self._stop.is_set():
            self._stop.set()
            self._notice('Остановка…')

    @Slot()
    def pump(self):
        if self.active:
            try:
                if not self._safe_windows():
                    self.stop()
            except (OSError,RuntimeError):
                self.stop()
        batch=list(self.controller.drain())
        if batch:
            self._journal.extend(batch)
            self.model.set_journal(self._journal)
            for event in batch:
                if self._log_path:
                    try:
                        rotate_and_append(self._log_path,event.disk_line)
                    except OSError:
                        pass
        if self._worker is not None and not self.active:
            self._worker=None
            self._notice('Сессия остановлена')
        snapshot=SessionSnapshot(active=self.active,stopping=self._stop.is_set(),
            region=self._rect, engine_available=self.catalog.engineAvailable,
            model_available=self.catalog.modelAvailable, model=self.catalog.selectedModel,side=self._side)
        self.controller.update_session(snapshot)
        self.model.refresh()
