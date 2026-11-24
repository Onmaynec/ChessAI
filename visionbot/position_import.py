"""Import an *already playing* computer-bot match from a board screenshot.

Only screen pixels are used. No history, DOM, browser API, OCR or online
training. Every piece must be identified; uncertain positions are rejected.
FEN metadata that is invisible in an image is set conservatively.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .recognizer import tiles, occupancy_ratio, piece_side

FILES = 'abcdefgh'
PIECES = 'PNBRQKpnbrqk'
BANK_PATH = Path(__file__).with_name('chesscom_neo_templates.npz')


class PositionImportError(ValueError):
    pass


def mask_tile(tile: np.ndarray) -> np.ndarray:
    """Foreground binary silhouette normalized to 48x48, theme-independent.

    The four near-corner patches estimate the square background. This keeps
    piece silhouettes stable under Chess.com's yellow move highlights.
    """
    h, w = tile.shape[:2]
    if min(h, w) < 22:
        raise PositionImportError('Слишком маленькая доска для распознавания фигур')
    radius = max(2, min(h,w)//24)
    patches=[]
    for yy, xx in ((.17,.17),(.17,.83),(.83,.17),(.83,.83)):
        y,x=int(h*yy),int(w*xx)
        patches.append(tile[y-radius:y+radius,x-radius:x+radius,:3].reshape(-1,3))
    bg = np.median(np.concatenate(patches), axis=0)
    small=cv2.resize(tile,(48,48),interpolation=cv2.INTER_AREA)
    distance=np.linalg.norm(small.astype(np.float32)-bg.astype(np.float32),axis=2)
    result=(distance>43).astype(np.uint8)
    result[:3,:]=result[-3:,:]=0
    result[:,:3]=result[:,-3:]=0
    return result


def dice(a: np.ndarray, b: np.ndarray) -> float:
    return float(2*np.minimum(a,b).sum()/(float(a.sum()+b.sum())+1.e-6))


@dataclass(frozen=True)
class ImportedPosition:
    fen: str
    placement: str
    side_to_move: str
    min_score: float
    min_margin: float
    highlighted: tuple[str, ...]
    warning: str


def square(r: int,c: int) -> str:
    return FILES[c]+str(8-r)


def load_bank(path: Path= BANK_PATH) -> dict[str,list[np.ndarray]]:
    if not path.is_file():
        raise PositionImportError(f'Нет шаблонов фигур: {path.name}. Проверь установку дополнения.')
    result={p:[] for p in PIECES}
    with np.load(path,allow_pickle=False) as blob:
        for piece in PIECES:
            if piece not in blob:
                raise PositionImportError('Неполный комплект шаблонов шахматных фигур')
            samples=np.asarray(blob[piece],dtype=np.uint8)
            if samples.ndim!=3 or samples.shape[1:]!=(48,48) or len(samples)<1:
                raise PositionImportError(f'Неверный формат шаблонов фигуры {piece}')
            result[piece]=list(samples)
    return result


def placement_for(board: list[list[str]]) -> str:
    rows=[]
    for row in board:
        run=0;parts=[]
        for p in row:
            if p=='.':
                run+=1
            else:
                if run:parts.append(str(run));run=0
                parts.append(p)
        if run:parts.append(str(run))
        rows.append(''.join(parts))
    return '/'.join(rows)


def highlighted_squares(frame: np.ndarray, color: str, *, delta: float=55.0) -> tuple[str,...]:
    """Find standard last-move tinted squares using parity-specific backgrounds."""
    board=tiles(frame,color)
    bg=np.zeros((8,8,3),dtype=np.float32)
    for r in range(8):
        for c in range(8):
            tile=board[r][c]
            h,w=tile.shape[:2]
            # The dominant flat color of the square is reliable even when
            # rank/file labels, piece outlines or square-selection dots sit in
            # one corner. A 5-bit histogram avoids OCR or hardcoded colors.
            pixels=(tile[:,:,:3].reshape(-1,3).astype(np.uint16)>>3)
            packed=(pixels[:,0]<<10)|(pixels[:,1]<<5)|pixels[:,2]
            code=int(np.bincount(packed,minlength=32768).argmax())
            bg[r,c]=np.median(tile[:,:,:3].reshape(-1,3)[packed==code],axis=0)
    med=[]
    for parity in (0,1):
        values=np.array([bg[r,c] for r in range(8) for c in range(8) if ((r+c)&1)==parity])
        med.append(np.median(values,axis=0))
    found=[]
    for r in range(8):
        for c in range(8):
            if np.linalg.norm(bg[r,c]-med[(r+c)&1])>delta:
                found.append(square(r,c))
    return tuple(found)


def classify_board(frame: np.ndarray, color: str, bank=None, *, min_score=.76, min_margin=.025):
    if color not in ('white','black'):
        raise ValueError('Unsupported board orientation')
    if min(frame.shape[:2]) < 320:
        raise PositionImportError('Доска слишком мала: требуется минимум 320 пикселей')
    bank = bank if bank is not None else load_bank()
    pieces=[];scores=[];margins=[]
    for r,row in enumerate(tiles(frame,color)):
        out=[]
        for c,tile in enumerate(row):
            if occupancy_ratio(tile)<.105:
                out.append('.')
                continue
            own=piece_side(tile)
            if own==0:
                raise PositionImportError(f'Не удалось определить цвет фигуры на {square(r,c)}. Уточни выделение доски.')
            current=mask_tile(tile)
            candidates=[]
            for p in PIECES:
                if p.isupper() != (own==1):
                    continue
                s=max(dice(current,ref) for ref in bank[p])
                candidates.append((s,p))
            candidates.sort(reverse=True)
            score,p=candidates[0];margin=score-candidates[1][0]
            if score<min_score or margin<min_margin:
                raise PositionImportError(
                    f'Неоднозначная фигура {square(r,c)}: {p} {score:.2f}, '
                    f'отрыв {margin:.2f}. Клики заблокированы. '
                    'Используй стандартные фигуры Chess.com и точную калибровку.')
            scores.append(score);margins.append(margin);out.append(p)
        pieces.append(out)
    if sum(p=='K' for row in pieces for p in row)!=1 or sum(p=='k' for row in pieces for p in row)!=1:
        raise PositionImportError('Не найдены оба короля — позиция распознана ошибочно')
    if any(p.lower()=='p' for p in pieces[0]+pieces[7]):
        raise PositionImportError('Пешка на 1-й или 8-й горизонтали: неверное распознавание')
    if sum(p!='.' for row in pieces for p in row)>32:
        raise PositionImportError('Более 32 фигур: неверное распознавание')
    return pieces,min(scores or [1.0]),min(margins or [1.0])


def _possible_last_move(src: str, dst: str, piece: str) -> bool:
    sr,sc=8-int(src[1]),FILES.index(src[0]);dr,dc=8-int(dst[1]),FILES.index(dst[0])
    dy,dx=dr-sr,dc-sc
    kind=piece.lower()
    if kind=='p':
        forward=-1 if piece.isupper() else 1
        return (dx==0 and dy in (forward, 2*forward)) or (abs(dx)==1 and dy==forward)
    if kind=='n':return sorted((abs(dx),abs(dy)))==[1,2]
    if kind=='b':return abs(dx)==abs(dy) and dx!=0
    if kind=='r':return (dx==0) != (dy==0)
    if kind=='q':return (dx==0 and dy!=0) or (dy==0 and dx!=0) or (abs(dx)==abs(dy) and dx!=0)
    if kind=='k':return max(abs(dx),abs(dy))==1 or (dy==0 and abs(dx)==2)
    return False


def infer_turn_from_highlights(frame: np.ndarray, color: str, board:list[list[str]]) -> tuple[str|None,tuple[str,...]]:
    marks=highlighted_squares(frame,color)
    if len(marks)<2 or len(marks)>5:
        return None,marks
    last_movers=set()
    for source in marks:
        r,c=8-int(source[1]),FILES.index(source[0])
        if board[r][c]!='.':continue
        for destination in marks:
            r2,c2=8-int(destination[1]),FILES.index(destination[0])
            p=board[r2][c2]
            if p!='.' and _possible_last_move(source,destination,p):
                last_movers.add('w' if p.isupper() else 'b')
    if len(last_movers)!=1:
        return None,marks
    return ('b' if last_movers.pop()=='w' else 'w'),marks


def import_position(frame:np.ndarray,color:str, *, explicit_turn:str|None=None,
                    bank=None) -> ImportedPosition:
    """Import visible piece placement and conservative invisible FEN metadata.

    If last-move highlights aren't uniquely readable, require an explicit
    turn instead of guessing. No possible screenshot proves castling rights,
    en-passant, halfmove clocks or prior repetitions, so they are unset.
    """
    board,score,margin=classify_board(frame,color,bank)
    detected,marks=infer_turn_from_highlights(frame,color,board)
    if explicit_turn is not None and explicit_turn not in ('w','b'):
        raise ValueError('Turn must be w, b or None')
    if explicit_turn is not None and detected is not None and explicit_turn!=detected:
        raise PositionImportError('Очередь хода не совпадает с подсветкой последнего хода')
    turn=explicit_turn or detected
    if turn is None:
        raise PositionImportError('Не определить очередь хода по доске: '
                                  'выбери «Ход белых» или «Ход чёрных» в приложении.')
    placement=placement_for(board)
    fen=f'{placement} {turn} - - 0 1'
    return ImportedPosition(fen,placement,turn,score,margin,marks,
        'Рокировки, en passant, история повторений и часы неизвестны по одному снимку; '
        'для безопасности они не включены. Это ограничение восстановления по изображению.')


def silhouette_to_edge(mask: np.ndarray) -> np.ndarray:
    """Fallback template for missing piece types in a midgame reference."""
    b=(np.asarray(mask,dtype=np.uint8)*255)
    return cv2.dilate(cv2.Canny(b,65,135),np.ones((2,2),np.uint8)).astype(np.float32)/255
