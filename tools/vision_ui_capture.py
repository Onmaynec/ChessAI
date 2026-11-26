"""Capture real Vision UI client areas on Windows. Never launches gameplay.

Run from the repository root: python -m tools.vision_ui_capture --fixture
Keep the foreground window unobstructed during capture. Fixture data is labeled.
"""
from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/vision-ui'))
    parser.add_argument('--sizes', nargs='+', default=['1280x800', '900x650', '560x600', '420x440'])
    parser.add_argument('--fixture', action='store_true', help='Use explicitly labeled local QA position/log entries')
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('This capture utility requires a visible Windows desktop.')
    import ctypes
    try: ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError): pass
    import customtkinter as ctk
    from PIL import ImageGrab
    from visionbot.gui import App

    class ReviewApp(App):
        def launch(self, *args, **kwargs):
            self.add_view_log('info', 'QA: launch disabled')
        def calibrate(self):
            self.add_view_log('info', 'QA: capture calibration disabled')
        def poll_shortcuts(self):
            pass
        def save_workspace_settings(self):
            pass
        def refresh_workspace(self):
            super().refresh_workspace()
            self.state_text.set('QA FIXTURE' if args.fixture else 'QA / IDLE')

    ctk.set_appearance_mode('dark')
    root = ctk.CTk()
    app = ReviewApp(root)
    app.rect = None
    root.attributes('-alpha', 1.0)
    root.attributes('-topmost', True)
    args.output.mkdir(parents=True, exist_ok=True)
    if args.fixture:
        app.set_fen('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')
        for i in range(40):
            app.add_view_log(('info', 'analysis', 'error')[i % 3], f'QA FIXTURE | event {i+1:02d}')
    def settle(seconds=.65):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            root.update()
            time.sleep(.015)
    def capture(name):
        root.lift()
        settle()
        x, y = root.winfo_rootx(), root.winfo_rooty()
        w, h = root.winfo_width(), root.winfo_height()
        image = ImageGrab.grab(bbox=(x, y, x+w, y+h), all_screens=True)
        target = args.output / f'{name}_{w}x{h}.png'
        image.save(target)
        print(target)
    try:
        settle()
        for requested in args.sizes:
            width, height = map(int, requested.lower().split('x'))
            scale = app.window_scale()
            if (width*scale+40 > root.winfo_screenwidth() or
                    height*scale+70 > root.winfo_screenheight()):
                print(f'SKIP {requested}: current screen/DPI cannot contain window')
                continue
            root.geometry(f'{width}x{height}+10+10')
            settle()
            for page in ('home', 'vision', 'analysis', 'log', 'settings'):
                app.navigate(page)
                capture(f'{requested}_{page}')
        app.toggle_overlay()
        if app.compact:
            root.attributes('-alpha', 1.0)
            capture('compact')
        else:
            print('SKIP compact: window did not fit')
    finally:
        root.destroy()

if __name__ == '__main__':
    main()
