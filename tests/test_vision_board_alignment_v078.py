"""Chess AI Vision v0.7.8: screen checkerboard alignment, no browser dependency."""
import unittest

import numpy as np

from visionbot.board_alignment import BoardAlignmentError, refine_board_rect


LIGHT = (208,236,235)  # BGR from a standard green Chess.com board
DARK = (82,149,115)


def make_screen(x=117, y=109, size=800, width=1300, height=1200):
    screen=np.full((height,width,3),(34,37,38),dtype=np.uint8)
    for row in range(8):
        for col in range(8):
            screen[y+row*size//8:y+(row+1)*size//8,
                   x+col*size//8:x+(col+1)*size//8] = (LIGHT if (row+col)%2 == 0 else DARK)
    # Add a few solid-color piece-like blobs so profile gaps are exercised.
    import cv2
    for r,c in [(0,0),(2,2),(5,4),(6,1)]:
        cv2.circle(screen,(x+int((c+.5)*size/8),y+int((r+.5)*size/8)),
                   size//28,(30,30,30),-1)
    # Last-move tinted square must not derail border detection.
    screen[y+2*size//8:y+3*size//8,x+4*size//8:x+5*size//8] = (80,211,219)
    return screen


class TestAutoBoardAlignment(unittest.TestCase):
    def test_corrects_shift_and_scale(self):
        screen=make_screen()
        rect, details=refine_board_rect(screen,(109,102,815))
        self.assertEqual(rect,(117,109,800))
        self.assertEqual(details['shift_x'],8)
        self.assertEqual(details['shift_y'],7)
        self.assertEqual(details['delta_size'],-15)

    def test_keeps_exact_rect(self):
        screen=make_screen()
        rect,_=refine_board_rect(screen,(117,109,800))
        self.assertEqual(rect,(117,109,800))

    def test_requires_visible_checkerboard(self):
        screen=np.full((1200,1300,3),(34,37,38),dtype=np.uint8)
        with self.assertRaises(BoardAlignmentError):
            refine_board_rect(screen,(117,109,800))

    def test_does_not_jump_to_distant_board(self):
        screen=make_screen()
        with self.assertRaises(BoardAlignmentError):
            refine_board_rect(screen,(180,109,800))

    def test_supports_lower_alignment_offset(self):
        screen=make_screen(11,9,920,width=1400,height=1100)
        rect,details=refine_board_rect(screen,(11,9,927))
        self.assertEqual(rect,(11,9,920))
        self.assertEqual(details['delta_size'],-7)


if __name__=='__main__':
    unittest.main()
