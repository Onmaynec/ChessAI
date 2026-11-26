"""Toolkit-independent, immutable UI snapshots. No engine or GUI dependencies."""
from __future__ import annotations
from dataclasses import dataclass
from .presentation_rules import session_state

@dataclass(frozen=True)
class SessionSnapshot:
    active: bool = False
    stopping: bool = False
    had_worker: bool = False
    region: tuple[int, int, int] | None = None
    engine_available: bool = False
    model_available: bool = False
    consent: bool = False
    model: str = ''
    side: str = 'white'

    @property
    def phase(self) -> str:
        return session_state(self.active, self.stopping, self.had_worker,
                             self.region is not None, self.engine_available,
                             self.model_available, self.consent)

@dataclass(frozen=True)
class AnalysisSnapshot:
    fen: str = ''
    move: str = ''
    score: str = '—'
    depth: int | None = None
    reply: str = ''
    seconds: float | None = None

    @classmethod
    def from_event(cls, event: dict) -> AnalysisSnapshot:
        details = event['details']
        cp = details.get('engine_cp')
        uci = details.get('uci_score')
        score = '—'
        if type(cp) is int:
            score = f'{cp:+d} cp'
        elif isinstance(uci, dict) and type(uci.get('value')) is int:
            if uci.get('kind') == 'mate':
                score = f"M{uci['value']}"
            elif uci.get('kind') == 'cp':
                score = f"{uci['value']:+d} cp"
        depth = details.get('search_depth')
        seconds = details.get('search_time_s')
        return cls(str(event.get('fen') or ''), str(event.get('move') or ''), score,
                   depth if type(depth) is int and depth >= 0 else None,
                   str(details.get('expected_reply') or ''),
                   float(seconds) if type(seconds) in (float, int) and seconds >= 0 else None)
