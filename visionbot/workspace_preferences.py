"""Toolkit-independent workspace preferences and monitor-safe geometry."""
from __future__ import annotations
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

MODES = ('compact', 'standard', 'expanded')
PANELS = ('metrics', 'board', 'analysis', 'journal')
DEFAULT_SIZE = {'compact': (360, 300), 'standard': (1040, 720), 'expanded': (1440, 900),
                'metrics': (360, 300), 'board': (460, 620), 'analysis': (440, 500), 'journal': (560, 480)}
MIN_SIZE = {'compact': (320, 260), 'standard': (560, 480), 'expanded': (560, 480),
            'metrics': (300, 240), 'board': (320, 340), 'analysis': (320, 260), 'journal': (320, 260)}

def valid_rect(value):
    return (isinstance(value, (list, tuple)) and len(value) == 4
            and all(type(n) is int for n in value)
            and 0 < value[2] <= 32768 and 0 < value[3] <= 32768)

def fit_rect(value, screens, key):
    """Fit a client rectangle to the best intersecting available screen.

    Coordinates may be negative. Leave room for native window decorations.
    """
    screens = [tuple(s) for s in screens if valid_rect(s)]
    if not screens:
        screens = [(0, 0, 1280, 720)]
    if not valid_rect(value):
        x,y,w,h = screens[0]
        dw,dh = DEFAULT_SIZE[key]
        value = (x+(w-dw)//2, y+(h-dh)//2, dw, dh)
    x,y,w,h = value
    def overlap(s):
        a,b,c,d = s
        return max(0,min(x+w,a+c)-max(x,a))*max(0,min(y+h,b+d)-max(y,b))
    a,b,c,d = max(screens,key=overlap)
    minw,minh = MIN_SIZE[key]
    # The actual desktop may be smaller than the application's preferred minimum.
    maxw,maxh = max(1,c-24),max(1,d-64)
    w = min(max(w,minw),maxw)
    h = min(max(h,minh),maxh)
    x = max(a+8,min(x,a+c-w-8))
    y = max(b+32,min(y,b+d-h-8))
    return [x,y,w,h]

def clean(data):
    data = data if isinstance(data,dict) else {}
    result = {'mode': 'standard', 'windows': {}, 'topmost': {}}
    if data.get('mode') in MODES:
        result['mode'] = data['mode']
    windows = data.get('windows')
    if isinstance(windows,dict):
        for key in (*MODES,*PANELS):
            if valid_rect(windows.get(key)):
                result['windows'][key] = list(windows[key])
    pins = data.get('topmost')
    if isinstance(pins,dict):
        for key in ('main',*PANELS):
            if type(pins.get(key)) is bool:
                result['topmost'][key] = pins[key]
    return result

class WorkspacePreferences:
    def __init__(self,path: Path | None = None):
        self.path = path
        self.data = clean(None)
        if path is not None:
            try:
                self.data = clean(json.loads(path.read_text(encoding='utf-8')))
            except (OSError,ValueError,UnicodeError):
                pass

    def save(self):
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp = None
        try:
            with NamedTemporaryFile(mode='w',encoding='utf-8',dir=self.path.parent,
                                    prefix='.vision-qt-',delete=False) as f:
                tmp = Path(f.name)
                json.dump(self.data,f,indent=2)
            os.replace(tmp,self.path)
        finally:
            if tmp is not None and tmp.exists():
                tmp.unlink()

    def geometry(self,key,screens):
        return fit_rect(self.data['windows'].get(key),screens,key)

    def record(self,key,rect):
        if key in (*MODES,*PANELS) and valid_rect(rect):
            self.data['windows'][key] = list(rect)
            return True
        return False

    def set_mode(self,mode):
        if mode in MODES:
            self.data['mode'] = mode
            return True
        return False

    def set_topmost(self,key,value):
        if key in ('main',*PANELS) and type(value) is bool:
            self.data['topmost'][key] = value
            return True
        return False
