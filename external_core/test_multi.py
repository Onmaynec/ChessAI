import unittest
from external_core.multi_gui import expand
from external_core.uci import START_FEN
from external_core.match import ENGINES

class MultiTests(unittest.TestCase):
    def test_start(self):
        b=expand(START_FEN)
        self.assertEqual(len(b),64)
        self.assertEqual(b[:8],list('rnbqkbnr'))
        self.assertEqual(b[-8:],list('RNBQKBNR'))
    def test_invalid(self):
        with self.assertRaises(ValueError):expand('8/8 w - - 0 1')
    def test_players(self):
        self.assertEqual(len(set(ENGINES)),5)
if __name__=='__main__':unittest.main()
