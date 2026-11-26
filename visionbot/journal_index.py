"""Bounded, pre-indexed journal projection, independent of GUI toolkit."""
from __future__ import annotations
from collections import deque

CATEGORIES = ('all','analysis','move','error','info')
MAX_ROWS = 600
MAX_TEXT = 8192

class JournalIndex:
    def __init__(self, events=()):
        self._rows = deque(maxlen=MAX_ROWS)
        self._key = None
        self._visible = []
        self.replace(events)

    def replace(self, events):
        self._rows.clear()
        for event in events:
            text = str(event.text)
            if len(text) > MAX_TEXT:
                text = text[:MAX_TEXT-1] + '…'
            row = {'category': event.category, 'text': text}
            self._rows.append((row, text.casefold()))
        self._key = None
        self._visible = []

    @property
    def total(self):
        return len(self._rows)

    def filter(self, query, category):
        q = query.strip().casefold()
        category = category if category in CATEGORIES else 'all'
        key = (q, category)
        if key != self._key:
            self._visible = [row for row, folded in self._rows
                             if (category == 'all' or row['category'] == category)
                             and (not q or q in folded)]
            self._key = key
        return self._visible
