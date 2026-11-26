"""UI-side event boundary. Producers submit; the owning GUI thread drains.

No browser, engine, widgets or Qt dependencies. The existing worker and
authorization checks remain in the legacy host until a separately tested migration.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import queue
import time
from typing import Iterator
from .telemetry import PREFIX, read_event, formatted_analysis
from .ui_state import AnalysisSnapshot, SessionSnapshot

@dataclass(frozen=True)
class UiEvent:
    category: str
    text: str
    disk_line: str
    analysis: dict | None = None
    lines: tuple[str, ...] = ()

def decode_message(raw: object) -> UiEvent:
    text = str(raw)
    stamp = datetime.now().strftime('%H:%M:%S')
    if text.startswith(PREFIX):
        try:
            event = read_event(text)
            if event is None:
                raise ValueError('missing analysis event')
            lines = tuple(formatted_analysis(event))
            AnalysisSnapshot.from_event(event)
            when = str(event.get('when') or stamp)
            return UiEvent('analysis', ' | '.join(lines[:2]),
                           when+' [ANALYSIS] '+' | '.join(lines), event, lines)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
            message = 'Invalid analysis telemetry: '+str(exc)
            return UiEvent('error', message, f'[{stamp}] {message}')
    category = ('error' if any(x in text.upper() for x in ('ОСТАНОВКА','ОШИБКА','ВНИМАНИЕ'))
                else 'move' if ('Ход ' in text or 'подтверждён' in text) else 'info')
    return UiEvent(category, text, f'[{stamp}] {text}')

class VisionUiController:
    def __init__(self):
        self._queue = queue.Queue()
        self.session = SessionSnapshot()
        self.analysis = AnalysisSnapshot()

    def submit(self, raw: object) -> None:
        self._queue.put(raw)

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    def update_session(self, snapshot: SessionSnapshot) -> bool:
        if snapshot == self.session:
            return False
        self.session = snapshot
        return True

    def reset_analysis(self) -> None:
        self.analysis = AnalysisSnapshot()

    def drain(self, limit: int = 24, budget: float = .008, *,
              clock=time.monotonic) -> Iterator[UiEvent]:
        """Yield incrementally so rendering time counts against the budget."""
        deadline = clock() + max(0., budget)
        for _ in range(max(0, limit)):
            if clock() >= deadline:
                break
            try:
                raw = self._queue.get_nowait()
            except queue.Empty:
                break
            event = decode_message(raw)
            if event.analysis is not None:
                self.analysis = AnalysisSnapshot.from_event(event.analysis)
            yield event
