"""Pure UI sizing rules and a bounded native Tk scroll viewport."""
from __future__ import annotations

import tkinter as tk
from .design import TRACK, DIM

def layout_mode(width, height, previous=None):
    # Hysteresis prevents repeated grid changes at a breakpoint.
    wide = width >= (1000 if previous and previous[0] else 1080)
    short = height < (770 if previous and previous[1] else 730)
    return wide, short

def shortcut_edge(left_alt, right_alt, control, one, two, previous):
    pressed = (bool(one), bool(two))
    if not left_alt or right_alt or control or all(pressed):
        return None, pressed
    for index, key in enumerate(pressed):
        if key and not previous[index]:
            return index + 1, pressed
    return None, pressed

class StableStringVar(tk.StringVar):
    """Avoid Tk variable traces and widget redraws for identical values."""
    def set(self, value):
        value = str(value)
        if self.get() != value:
            super().set(value)

class ScrollViewport(tk.Frame):
    """One native canvas; schedule region updates only when geometry changes."""
    def __init__(self, parent, background, scrollbar_class=None):
        super().__init__(parent, bg=background, bd=0, highlightthickness=0)
        self.canvas = tk.Canvas(self, bg=background, bd=0, highlightthickness=0)
        self.scrollbar = (scrollbar_class(self, orientation='vertical', command=self.canvas.yview, width=10,
                                          fg_color=background, button_color=TRACK, button_hover_color=DIM)
                          if scrollbar_class else tk.Scrollbar(self, orient='vertical', command=self.canvas.yview))
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = tk.Frame(self.canvas, bg=background, bd=0, highlightthickness=0)
        self.window = self.canvas.create_window(0, 0, window=self.body, anchor='nw')
        self._width = None
        self._region = None
        self._pending = None
        self._scrollbar_visible = False
        self.canvas.bind('<Configure>', self._resize, add='+')
        self.body.bind('<Configure>', self._schedule_region, add='+')
        self.winfo_toplevel().bind('<MouseWheel>', self._wheel, add='+')

    def _resize(self, event):
        if event.width != self._width:
            self._width = event.width
            self.canvas.itemconfigure(self.window, width=max(1, event.width))
        self._schedule_region()

    def _schedule_region(self, event=None):
        if self._pending is None:
            self._pending = self.after(35, self._update_region)

    def _update_region(self):
        self._pending = None
        region = self.canvas.bbox(self.window)
        if region and region != self._region:
            self._region = region
            self.canvas.configure(scrollregion=region)
        # Reserve scrollbar width permanently to avoid width/height oscillation.
        if not self._scrollbar_visible:
            self.scrollbar.pack(side='right', fill='y', before=self.canvas)
            self._scrollbar_visible = True

    def _wheel(self, event):
        if not self.winfo_ismapped():
            return
        widget = event.widget
        while widget is not None and widget is not self:
            if isinstance(widget, tk.Text):
                return
            widget = getattr(widget, 'master', None)
        if widget is self:
            self.canvas.yview_scroll(-int(event.delta / 120), 'units')
            return 'break'

    def reset_scroll(self):
        self.canvas.yview_moveto(0)

    def destroy(self):
        if self._pending is not None:
            self.after_cancel(self._pending)
            self._pending = None
        super().destroy()
