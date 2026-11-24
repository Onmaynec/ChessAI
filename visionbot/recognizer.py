"""Detect legal chess moves by comparing screen observations with a known game state.

The reference is an image of the *starting board*, not an online database.
No OCR, DOM access or chess-site HTTP requests are used. Failed/ambiguous
recognition must stop play, never guess and click.
"""
from __future__ import annotations

from dataclasses import dataclass
import cv2
import numpy as np

from botlab.session import parse_board

FILES = 'abcdefgh'
START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR'


def cell(s: str) -> tuple[int, int]:
    return 8-int(s[1]), FILES.index(s[0])


def board_after(board: list[list[str]], move: str) -> list[list[str]]:
    """Only called on moves already verified legal by the C++ bridge.

    Handles promotions, castling, en passant, captures. Internal side-to-move
    is guaranteed by bridge's legal-move list.
    """
    r1,c1=cell(move[:2]);r2,c2=cell(move[2:4]); piece=board[r1][c1]
    if piece=='.':
        raise ValueError('Empty source square')
    out=[row[:] for row in board]
    if piece.lower()=='p' and c1!=c2 and out[r2][c2]=='.':
        out[r1][c2]='.'  # en passant
    out[r1][c1]='.'
    if len(move)==5:
        if move[4].lower() not in 'qrbn':raise ValueError('Invalid promotion')
        piece=move[4].upper() if piece.isupper() else move[4].lower()
    out[r2][c2]=piece
    if piece.lower()=='k' and abs(c2-c1)==2:
        if c2>c1:  # kingside
            out[r1][5],out[r1][7]=out[r1][7],'.'
        else:
            out[r1][3],out[r1][0]=out[r1][0],'.'
    return out


def orient_rc(r:int,c:int,color:str)->tuple[int,int]:
    return (r,c) if color=='white' else (7-r,7-c)


def tiles(frame: np.ndarray,color:str)->list[list[np.ndarray]]:
    """Input a calibrated square BGR image, output chess-oriented tile images."""
    h,w=frame.shape[:2]
    if abs(w-h)>2:raise ValueError('Board area must be square')
    out=[]
    for r in range(8):
        row=[]
        for c in range(8):
            vr,vc=orient_rc(r,c,color)
            y0=int(round(vr*h/8));y1=int(round((vr+1)*h/8))
            x0=int(round(vc*w/8));x1=int(round((vc+1)*w/8))
            # Avoid rank/file labels, move indicators and square borders.
            dy=max(1,int((y1-y0)*0.09));dx=max(1,int((x1-x0)*0.09))
            row.append(frame[y0+dy:y1-dy,x0+dx:x1-dx])
        out.append(row)
    return out


def feature(tile:np.ndarray)->np.ndarray:
    small=cv2.resize(tile,(48,48),interpolation=cv2.INTER_AREA)
    gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY) if len(small.shape)==3 else small
    # Chess.com highlights change the background color, not piece silhouette.
    e=cv2.Canny(gray,65,135)
    return cv2.dilate(e,np.ones((2,2),np.uint8)).astype(np.float32)/255


def similarity(a:np.ndarray,b:np.ndarray)->float:
    """Smoothed foreground-edge overlap, 0..1, independent of square tint."""
    x=cv2.GaussianBlur(a,(3,3),0.8);y=cv2.GaussianBlur(b,(3,3),0.8)
    a0=float(x.sum());b0=float(y.sum())
    if a0<3 and b0<3:return 1.0
    if min(a0,b0)<3:return 0.0
    # Soft Dice. An offset of a few pixels reduces the score, not eliminates it.
    return float((2*(x*y).sum())/(float((x*x).sum()+(y*y).sum())+1e-6))


def occupancy_ratio(tile: np.ndarray) -> float:
    """Detect flat-theme chess pieces against per-square background.

    Uses tile's four inner corners to infer its background (including yellow
    last-move highlights), then scores non-background pixels in the center.
    """
    h, w = tile.shape[:2]
    if h < 16 or w < 16:
        raise ValueError('Board tile is too small for reliable occupancy detection')
    patches = []
    radius = max(2, min(h, w) // 24)
    for cy, cx in ((.17, .17), (.17, .83), (.83, .17), (.83, .83)):
        yy, xx = int(h * cy), int(w * cx)
        patches.append(tile[yy-radius:yy+radius, xx-radius:xx+radius, :3].reshape(-1, 3))
    bg = np.median(np.concatenate(patches), axis=0)
    center = tile[int(h*.23):int(h*.77), int(w*.23):int(w*.77), :3]
    distance = np.linalg.norm(center.astype(np.float32) - bg.astype(np.float32), axis=2)
    return float(np.mean(distance > 40.0))


def piece_side(tile: np.ndarray) -> int:
    """Detect piece ownership from neutral foreground colors on standard theme.

    Return +1 white, -1 black, 0 uncertain. Calibrate local background from
    the tile itself so green/yellow move highlights cannot resemble pieces.
    This deliberately does NOT attempt to identify the kind of piece.
    """
    h, w = tile.shape[:2]
    if min(h, w) < 16:
        return 0
    radius = max(2, min(h, w) // 24)
    patches = []
    for cy, cx in ((.17, .17), (.17, .83), (.83, .17), (.83, .83)):
        yy, xx = int(h * cy), int(w * cx)
        patches.append(tile[yy-radius:yy+radius, xx-radius:xx+radius, :3].reshape(-1, 3))
    bg = np.median(np.concatenate(patches), axis=0)
    center = tile[int(h*.23):int(h*.77), int(w*.23):int(w*.77), :3]
    mask = np.linalg.norm(center.astype(np.float32) - bg.astype(np.float32), axis=2) > 40
    pixels = center[mask]
    if pixels.shape[0] < 25:
        return 0
    lowest, highest = pixels.min(axis=1), pixels.max(axis=1)
    neutral = highest - lowest < 55
    light = float(np.mean(neutral & (lowest >= 190)))
    dark = float(np.mean(neutral & (highest <= 130)))
    if light >= .42 and light - dark >= .25:
        return 1
    if dark >= .42 and dark - light >= .25:
        return -1
    return 0


class ObservedTiles(list):
    """Edge features, occupancy, and conservative piece-color evidence."""
    def __init__(self, features, occupied, ratios, sides=None, raw_tiles=None):
        super().__init__(features)
        self.occupied = occupied
        self.ratios = ratios
        self.sides = sides
        self.raw_tiles = raw_tiles


def occupancy_grid(frame: np.ndarray, color: str, *, threshold: float = .105):
    parts = tiles(frame, color)
    ratios = [[occupancy_ratio(tile) for tile in row] for row in parts]
    occupied = [[ratio >= threshold for ratio in row] for row in ratios]
    return occupied, ratios


@dataclass(frozen=True)
class Match:
    move:str|None
    gain:float
    margin:float
    reason:str


class VisionRecognizer:
    """Infer opponent's next move only from C++ legal candidates and screen.

    Requires calibration at the exact standard starting position. Never
    invents a move when two candidate positions look similar.
    """
    def __init__(self, initial_bgr:np.ndarray, color:str, *, initial_fen: str = None):
        if color not in ('white','black'):raise ValueError('invalid orientation')
        if min(initial_bgr.shape[:2])<320:raise ValueError('Board too small (<320 px)')
        self.color=color
        self.exemplars:dict[str,list[np.ndarray]]={}
        initial=tiles(initial_bgr,color)
        board=parse_board(initial_fen.split()[0] if initial_fen else START)
        for r in range(8):
            for c in range(8):
                p=board[r][c]
                self.exemplars.setdefault(p,[]).append(feature(initial[r][c]))
        # Imported positions can have zero pawns, queens, or other categories.
        # Use the packaged standard-style template bank as backup exemplars.
        if initial_fen is not None:
            from .position_import import load_bank
            for p, templates in load_bank().items():
                if not self.exemplars.get(p):
                    # The edge-based move verifier requires actual edge features.
                    from .position_import import silhouette_to_edge
                    self.exemplars[p] = [silhouette_to_edge(x) for x in templates]
        else:
            # Original starting-board visual sanity check remains unchanged.
            pawns=self.exemplars['P']+self.exemplars['p']
            empties=self.exemplars['.']
            if np.median([max(similarity(p,x) for x in pawns) for p in empties])>0.75:
                raise ValueError('Starting position not recognized; reopen the initial board')
        self.cache={}
        actual, ratios = occupancy_grid(initial_bgr, color)
        wrong = [f'{FILES[c]}{8-r}' for r in range(8) for c in range(8)
                 if actual[r][c] != (board[r][c] != '.')]
        if wrong:
            raise ValueError('Распознанная доска расходится с FEN ('+', '.join(wrong[:6])+'). '
                             'Проверь область доски.')
        # Fail safely on a patterned theme or a misaligned board, rather than
        # learning malformed piece silhouettes from an active game position.
        empty_ratios = [ratios[r][c] for r in range(8) for c in range(8) if board[r][c] == '.']
        filled_ratios = [ratios[r][c] for r in range(8) for c in range(8) if board[r][c] != '.']
        if max(empty_ratios) >= .105 or min(filled_ratios) < .105:
            raise ValueError('Не получается различить пустые и занятые клетки. '
                             'Выбери стандартный стиль Chess.com и уточни область доски.')

    def observe(self,frame:np.ndarray)->ObservedTiles:
        parts=tiles(frame,self.color)
        ratios=[[occupancy_ratio(tile) for tile in row] for row in parts]
        occupied=[[ratio >= .105 for ratio in row] for row in ratios]
        sides = [[piece_side(tile) if occupied[r][c] else 0
                  for c, tile in enumerate(row)] for r, row in enumerate(parts)]
        return ObservedTiles([[feature(x) for x in row] for row in parts],occupied,ratios,sides,parts)

    def score(self,observed:np.ndarray,piece:str)->float:
        return max(similarity(observed,p) for p in self.exemplars[piece])

    def detect_immediate_reply(self, obs: ObservedTiles, old: list[list[str]],
                               our_move: str, legal_replies: list[str]) -> Match:
        """Recognize two completed plies from one screenshot, without guessing.

        A fast recapture such as Qxd8 Rxd8 changes only two occupied squares
        relative to the *pre-capture* board. The one-move recognizer cannot
        reliably confirm Qxd8 because its destination was occupied both before
        and after. We compare complete 64-square occupancies for every LEGAL
        opponent reply after the already chosen AI move. Accept only one exact
        result and never infer a reply from source-square changes alone.
        """
        grid = getattr(obs, 'occupied', None)
        if grid is None:
            return Match(None, 0.0, 0.0, 'Fast-reply recognition needs board occupancy')
        actual = np.asarray(grid, dtype=np.bool_)
        if actual.shape != (8, 8):
            raise ValueError('Expected 8x8 board occupancy')
        old_grid = np.asarray([[p != '.' for p in row] for row in old], dtype=np.bool_)
        if np.array_equal(actual, old_grid):
            return Match(None, 0.0, 0.0, 'Position unchanged')
        try:
            after_own = board_after(old, our_move)
        except ValueError:
            return Match(None, 0.0, 0.0, 'Invalid pending move')
        # The pending move must have changed the board in a way that remains
        # observable. Do not assume a click succeeded solely because time passed.
        own_source = cell(our_move[:2])
        if actual[own_source] or old_grid[own_source] == False:
            return Match(None, 0.0, 0.0, 'Own source still occupied or absent')
        exact=[]
        for reply in legal_replies:
            try:
                after_reply=board_after(after_own, reply)
            except (ValueError, IndexError):
                continue
            predicted=np.asarray([[p != '.' for p in row] for row in after_reply], dtype=np.bool_)
            if np.array_equal(actual, predicted):
                exact.append((reply, after_reply))
        if len(exact)==1:
            return Match(exact[0][0], 1.0, 1.0, 'Confirmed own move + immediate legal reply by full-board occupancy')
        if len(exact)>1:
            from .promotion import resolve_promotion_variants
            # Identify the side from the actual candidate's destination piece.
            promotion_options = [reply for reply, _ in exact]
            if all(len(reply) == 5 for reply in promotion_options):
                dest_r, dest_c = cell(promotion_options[0][2:4])
                promoted_piece = exact[0][1][dest_r][dest_c]
                choice = resolve_promotion_variants(obs, promotion_options,
                            'white' if promoted_piece.isupper() else 'black')
                if choice is not None:
                    return Match(choice, 1.0, 1.0, 'Fast promoted reply visually confirmed')
            # Qxd8 Rxd8 and Qxd8 Rc1 may have IDENTICAL occupancy: in both
            # cases the black rook vacates c8 while d8/c1 stay occupied. Use
            # a high-confidence WHITE vs BLACK piece-color test on precisely
            # the squares on which those legal replies differ. Unknown means
            # stop, never guess.
            observed_sides = getattr(obs, 'sides', None)
            if observed_sides is None:
                return Match(None, 0.0, 0.0, 'Multiple legal replies have identical occupancy; piece colors unavailable')
            disagreements = []
            for r in range(8):
                for c in range(8):
                    possibilities = {1 if board[r][c].isupper() else -1
                                     for _, board in exact if board[r][c] != '.'}
                    if len(possibilities) > 1 and observed_sides[r][c] != 0:
                        disagreements.append((r, c, observed_sides[r][c]))
            if not disagreements:
                return Match(None, 0.0, 0.0, 'Identical occupancy and no reliable color evidence')
            verified = []
            for reply, board in exact:
                if all((1 if board[r][c].isupper() else -1) == color
                       for r, c, color in disagreements):
                    verified.append(reply)
            if len(verified) == 1:
                return Match(verified[0], 1.0, 1.0,
                             'Confirmed own capture + fast reply by occupancy and piece colors')
            return Match(None, 0.0, 0.0, 'Conflicting or inconclusive piece-color evidence')
        return Match(None, 0.0, 0.0, 'No exact two-ply board match')


    def detect(self,obs:list[list[np.ndarray]],old:list[list[str]],legal_moves:list[str],
               *,min_gain:float=0.24,min_margin:float=0.08)->Match:
        if not legal_moves:return Match(None,0,0,'No legal moves')
        observed_occupancy=getattr(obs,'occupied',None)
        if observed_occupancy is not None:
            # Match ALL 64 squares before accepting a move. Previous releases
            # checked only the candidate's changed squares: after O-O, e1f1
            # (king step) and h1f1 (rook step) also appeared to fit, making
            # castling impossible to confirm reliably.
            observed_grid=np.asarray(observed_occupancy,dtype=np.bool_)
            old_grid=np.asarray([[piece!='.' for piece in row] for row in old],dtype=np.bool_)
            if observed_grid.shape != (8,8):
                raise ValueError('Expected 8x8 board occupancy')
            if np.array_equal(observed_grid,old_grid):
                return Match(None,0.0,0.0,'Position unchanged')
            old_errors=int(np.count_nonzero(observed_grid!=old_grid))
            occupancy_matches=[]
            for move in legal_moves:
                after=board_after(old,move)
                expected=np.asarray([[piece!='.' for piece in row] for row in after],dtype=np.bool_)
                changed=old_grid!=expected
                count=int(np.count_nonzero(changed))
                # A capture may not vacate two squares (one square changes
                # occupancy); promotion variants have identical occupancy.
                # Those positions need the piece-shape fallback below.
                if count < 1 or not np.all(observed_grid[changed] == expected[changed]):
                    continue
                # Single occupancy change occurs in an ordinary capture:
                # source empties, destination remains occupied. Do not
                # confirm unless destination is recognizably OUR color.
                if count == 1:
                    if len(move) < 4:
                        continue
                    r1, c1 = cell(move[:2]); r2, c2 = cell(move[2:4])
                    sides = getattr(obs, 'sides', None)
                    old_target, new_target = old[r2][c2], after[r2][c2]
                    if (not sides or old_target == '.' or new_target == '.'
                            or old_target.isupper() == new_target.isupper()
                            or sides[r2][c2] != (1 if new_target.isupper() else -1)):
                        continue
                errors=int(np.count_nonzero(observed_grid!=expected))
                occupancy_matches.append((errors,-count,move))
            occupancy_matches.sort()
            exact=[candidate for candidate in occupancy_matches if candidate[0]==0]
            if len(exact)==1:
                move=exact[0][2]
                if len(move)==5:
                    from .promotion import resolve_promotion_variants
                    r,c=cell(move[2:4]); after=board_after(old,move)
                    promoted=after[r][c]
                    confirmed=resolve_promotion_variants(obs,[move], 'white' if promoted.isupper() else 'black')
                    if confirmed!=move:
                        return Match(None,0.0,0.0,'Promotion piece not visually confirmed')
                return Match(move,1.0,1.0,'Confirmed by full-board occupancy')
            if len(exact)>1:
                from .promotion import resolve_promotion_variants
                candidates=[m[2] for m in exact]
                if all(len(m)==5 for m in candidates):
                    r,c=cell(candidates[0][2:4]); piece=board_after(old,candidates[0])[r][c]
                    promoted=resolve_promotion_variants(obs,candidates, 'white' if piece.isupper() else 'black')
                    if promoted is not None:
                        return Match(promoted,1.0,1.0,'Promotion piece visually identified')
                return Match(None,0.0,0.0,'Ambiguous full-board occupancy (promotion or overlap)')
            # The opponent may respond before our own move is verified. In
            # that case the predicted board differs by the opponent's TWO
            # changed squares. Permit this only with a unique, well-separated
            # match and positive evidence relative to the original position.
            if occupancy_matches:
                best=occupancy_matches[0]
                next_errors=occupancy_matches[1][0] if len(occupancy_matches)>1 else 65
                if (best[0]<=2 and old_errors-best[0]>=2
                        and next_errors-best[0]>=2):
                    return Match(best[2],1.0,1.0,'Confirmed despite fast opponent reply')
            # Ambiguous occupancy is not evidence that a candidate happened.
            # Piece silhouettes provide a second conservative observation.
        candidates=[]
        # A single common source square cannot by itself trigger acceptance:
        # require positive evidence also on the destination/captured piece.
        for move in legal_moves:
            after=board_after(old,move)
            changes=[(r,c) for r in range(8) for c in range(8) if after[r][c]!=old[r][c]]
            if not changes:continue
            gains=[self.score(obs[r][c],after[r][c])-self.score(obs[r][c],old[r][c]) for r,c in changes]
            # Emphasize the weakest changed square, discouraging a move with
            # correct source but wrong destination.
            gain=0.65*(sum(gains)/len(gains))+0.35*min(gains)
            candidates.append((gain,move,tuple(gains)))
        if not candidates:return Match(None,0,0,'No candidate')
        if any(len(m)==5 for _gain,m,_details in candidates):
            return Match(None,0,0,'Promotion variants require verified piece type')
        candidates.sort(reverse=True)
        gain,move,details=candidates[0]
        margin=gain-(candidates[1][0] if len(candidates)>1 else 0.0)
        if gain<min_gain:return Match(None,gain,margin,'Position unchanged or unclear')
        if min(details)<-0.04:return Match(None,gain,margin,'Contradictory screen evidence')
        if margin<min_margin:return Match(None,gain,margin,'Ambiguous move; waiting')
        return Match(move,gain,margin,'Recognized')


def screenshot_board(bgr:np.ndarray, rect:tuple[int,int,int,int])->np.ndarray:
    x,y,s,_=rect
    if x<0 or y<0 or s<320 or x+s>bgr.shape[1] or y+s>bgr.shape[0]:
        raise ValueError('Invalid board rectangle')
    return bgr[y:y+s,x:x+s].copy()
