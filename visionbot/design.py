"""Vision UI semantic design tokens shared by the desktop and overlays.

Keep functional states distinguishable from visual selection. No engine imports.
"""
BG = '#000000'
PANEL = '#080808'
FIELD = '#141414'
BORDER = '#292929'
TEXT = '#ffffff'
MUTED = '#b3b3b3'
DIM = '#808080'
ACCENT = '#ffffff'
ACCENT_TEXT = '#000000'
HOVER = '#dedede'
SURFACE_HOVER = '#1a1a1a'
ACTIVE = '#242424'
TRACK = '#404040'
GREEN = '#70d6a0'
RED = '#ff8585'
WARNING = '#e9b963'
BOARD_LIGHT = '#c8c8c8'
BOARD_DARK = '#727272'
STOP_BG = '#2b1414'
STOP_HOVER = '#402020'
STOP_BORDER = '#663636'
FONT = 'Segoe UI'
MONO = 'Consolas'
SPACE = (4, 8, 12, 16, 20, 24, 32, 40, 48, 64)
RADIUS = 6
CONTROL_HEIGHT = 34

def button_style(primary=False):
    return dict(fg_color=ACCENT if primary else FIELD,
                hover_color=HOVER if primary else SURFACE_HOVER,
                text_color=ACCENT_TEXT if primary else TEXT,
                text_color_disabled=DIM,
                border_width=0 if primary else 1, border_color=BORDER,
                corner_radius=RADIUS, height=CONTROL_HEIGHT,
                font=(FONT, 13, 'bold' if primary else 'normal'))
