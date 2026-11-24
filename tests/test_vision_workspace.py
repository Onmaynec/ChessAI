"""Display-independent contracts for the new presentation layer."""
from visionbot.workspace import parse_board, clamp_alpha, safe_position
from visionbot.telemetry import rectangles_overlap

def test_fen_preview():
    board=parse_board('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')
    assert board[0][3]=='q' and board[7][3]=='Q'
    assert parse_board('8/8/8') is None
    assert parse_board('9/8/8/8/8/8/8/8') is None

def test_opacity():
    assert clamp_alpha(0)==.55 and clamp_alpha(2)==1
    assert clamp_alpha('bad')==.85

def test_docking():
    board=(200,120,800)
    p=safe_position(board,344,252,1920,1080)
    assert p is not None and not rectangles_overlap((*p,344,252),(200,120,800,800))
    assert safe_position((0,0,1000),344,252,1000,1000) is None
