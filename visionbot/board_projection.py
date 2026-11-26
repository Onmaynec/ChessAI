"""Read-only board projection for reported analysis events, not a chess engine."""
from __future__ import annotations
from dataclasses import dataclass
from collections import deque
import re
from .analysis_view import uci, square_xy, line_moves
from .ui_state import AnalysisSnapshot

PIECES = 'KQRBNPkqrbnp'
MAX_HISTORY = 600
FILES = 'abcdefgh'

def parse_fen(fen: str) -> tuple[str, ...]:
    """Validate the board field and turn structurally; no legality claims."""
    fields = fen.split()
    if len(fields) != 6 or fields[1] not in ('w', 'b'):
        return ()
    rows = fields[0].split('/')
    if len(rows) != 8:
        return ()
    cells = []
    for row in rows:
        rank = []
        for char in row:
            if char in PIECES:
                rank.append(char)
            elif char in '12345678':
                rank.extend([''] * int(char))
            else:
                return ()
        if len(rank) != 8:
            return ()
        cells.extend(rank)
    return tuple(cells)

def projection(cells: tuple[str, ...], black: bool) -> list[dict]:
    if len(cells) != 64:
        return []
    result = []
    for i in range(64):
        j = 63-i if black else i
        result.append({'square': FILES[j%8]+str(8-j//8), 'piece': cells[j]})
    return result

def move_geometry(move: str, black: bool) -> dict:
    if not uci(move):
        return {}
    x1,y1 = square_xy(move[:2],black)
    x2,y2 = square_xy(move[2:4],black)
    return dict(x1=x1,y1=y1,x2=x2,y2=y2)

def score_geometry(event: dict) -> dict:
    """White-oriented display of reported side-to-move score, not win probability."""
    fields = str(event.get('fen') or '').split()
    if not parse_fen(str(event.get('fen') or '')):
        return {}
    details = event.get('details', {})
    cp = details.get('engine_cp')
    u = details.get('uci_score')
    sign = 1 if fields[1] == 'w' else -1
    if type(cp) is int:
        value = cp * sign
        return dict(kind='cp', value=value, fraction=.5+max(-800,min(800,value))/1600)
    if isinstance(u,dict) and type(u.get('value')) is int:
        value = u['value'] * sign
        if u.get('kind') == 'cp':
            return dict(kind='cp', value=value, fraction=.5+max(-800,min(800,value))/1600)
        if u.get('kind') == 'mate' and value:
            return dict(kind='mate',value=value,fraction=1. if value>0 else 0.)
    return {}

@dataclass(frozen=True)
class BoardFrame:
    snapshot: AnalysisSnapshot
    cells: tuple[str, ...]
    chosen: str
    candidates: tuple[tuple[str,str], ...]
    line: tuple[str, ...]
    line_label: str
    evaluation: dict

    @classmethod
    def from_event(cls, event: dict):
        snapshot = AnalysisSnapshot.from_event(event)
        cells = parse_fen(snapshot.fen)
        details = event.get('details',{})
        chosen = uci(snapshot.move) or ''
        candidates = []
        seen = set()
        raw = details.get('candidates')
        if isinstance(raw,list):
            for item in raw:
                if not isinstance(item,dict):
                    continue
                move = uci(item.get('move'))
                if not move or move in seen:
                    continue
                seen.add(move)
                cp = item.get('cp')
                candidates.append((move, f'{cp:+d} cp' if type(cp) is int else '—'))
                if len(candidates) == 8:
                    break
        line = tuple(line_moves(event))
        label = ('Основная линия поиска' if details.get('line_kind') == 'searched_pv'
                 else 'Возможное продолжение')
        return cls(snapshot,cells,chosen,tuple(candidates),line,label,score_geometry(event))

class BoardHistory:
    def __init__(self):
        self.frames = deque(maxlen=MAX_HISTORY)
        self.index = -1
        self.black = False
        self.selected = ''

    @property
    def current(self):
        return self.frames[self.index] if 0 <= self.index < len(self.frames) else None

    def replace(self, events):
        self.frames.clear()
        for event in events:
            if event is not None:
                self.frames.append(BoardFrame.from_event(event))
        self.go(len(self.frames)-1)

    def go(self,index):
        self.index = max(0,min(index,len(self.frames)-1)) if self.frames else -1
        self.selected = self.current.chosen if self.current else ''

    def select(self, move):
        frame = self.current
        if frame and move in {frame.chosen, *(m for m,_ in frame.candidates)}:
            self.selected = move
            return True
        return False

    def view(self):
        frame = self.current
        if frame is None:
            return dict(cells=[], arrow={}, evaluation={}, candidates=[], line=[], lineLabel='',
                        fen='', turn='—', move='—', score='—', depth='—', reply='—', seconds='—')
        s = frame.snapshot
        fields = s.fen.split()
        return dict(cells=projection(frame.cells,self.black),
                    arrow=move_geometry(self.selected,self.black) if frame.cells else {},
                    evaluation=frame.evaluation,
                    candidates=[dict(move=m,score=cp) for m,cp in frame.candidates],
                    line=list(frame.line),lineLabel=frame.line_label,fen=s.fen,
                    turn=('Белые' if fields[1]=='w' else 'Чёрные') if frame.cells else '—',
                    move=frame.chosen or '—',score=s.score,depth=str(s.depth) if s.depth is not None else '—',
                    reply=s.reply or '—',seconds=f'{s.seconds:.3f} s' if s.seconds is not None else '—')
