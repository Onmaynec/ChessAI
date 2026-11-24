import unittest
from neural.intelligence import parse_uci_answers, SearchUnavailable

class UciParserTests(unittest.TestCase):
    def test_new_and_old(self):
        text='info depth 2 score cp 20 nodes 130 time 3 nps 43333 qnodes 100 tthits 1 pv e2e4 e7e5\nbestmove e2e4\ninfo depth 2 score cp -3 nodes 200\nbestmove d2d4\n'
        a,b=parse_uci_answers(text,2,2)
        self.assertEqual(a.pv,('e2e4','e7e5'))
        self.assertEqual((a.nodes,a.qnodes,a.tt_hits,a.elapsed_ms),(130,100,1,3))
        self.assertEqual(b.pv,())
        self.assertIsNone(b.qnodes)

    def test_truncated_search_not_comparable(self):
        with self.assertRaises(SearchUnavailable):
            parse_uci_answers('info depth 1 score cp 30\nbestmove e2e4\n',1,4)

    def test_proven_mate_can_finish_early(self):
        a,=parse_uci_answers('info depth 1 score cp 29999 pv g6g7\nbestmove g6g7\n',1,4)
        self.assertEqual(a.depth,1)

    def test_terminal_and_pv_validation(self):
        a,=parse_uci_answers('info depth 0 score cp -30000\nbestmove 0000\n',1,3)
        self.assertIsNone(a.move)
        with self.assertRaises(SearchUnavailable):
            parse_uci_answers('info depth 3 score cp 20 pv e2e4 e7e5\nbestmove d2d4\n',1,3)
        with self.assertRaises(SearchUnavailable):
            parse_uci_answers('bestmove e2e4\n',1,3)

if __name__=='__main__':unittest.main()
