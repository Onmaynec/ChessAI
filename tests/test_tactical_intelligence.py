import unittest
from neural.tactics import board,attacks,square,pins,canonical,describe,repetition_stats
from neural.tactical_data import sparse_fen
import random

class TacticalTests(unittest.TestCase):
    def test_fork(self):
        before='r3k3/8/4N3/8/8/8/8/6K1 w - - 0 1'
        after='r3k3/2N5/8/8/8/8/8/6K1 b - - 1 1'
        self.assertIn('fork',{x['kind'] for x in describe(before,'e6c7',after)})
    def test_pin(self):
        f='4k3/4q3/8/8/1B6/8/8/4R1K1 w - - 0 1'
        self.assertIn((square('e1'),square('e7'),square('e8')),pins(board(f),'w'))
    def test_canonical(self):
        self.assertEqual(canonical('7k/8/5KQ1/8/8/8/8/8 w - - 0 1'),canonical('8/8/8/8/8/5kq1/8/7K b - - 5 9'))
    def test_pin_capture_alternative(self):
        f='4k3/4q3/8/8/1B6/8/8/4R1K1 w - - 0 1'
        a='4k3/4B3/8/8/8/8/8/4R1K1 b - - 0 1'
        self.assertIn('pin_capture',{t['kind'] for t in describe(f,'b4e7',a)})
    def test_repetition(self):
        self.assertEqual(repetition_stats([{'reason':'threefold_repetition'},{'reason':'checkmate'}])['repetitions'],1)
    def test_sparse(self):
        rng=random.Random(93)
        fens=[sparse_fen(rng) for _ in range(100)]
        for f in filter(None,fens):
            self.assertEqual(len(board(f)),64)
            self.assertEqual(board(f).count('K'),1)
            self.assertEqual(board(f).count('k'),1)
        self.assertTrue(any(fens))

if __name__=='__main__':unittest.main()
