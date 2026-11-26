import unittest
from visionbot.board_projection import parse_fen, projection, move_geometry, score_geometry, BoardHistory, MAX_HISTORY

START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
AFTER = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1'

def event(fen=START, move='e2e4', cp=32):
    return {'fen':fen,'move':move,'details':{'engine_cp':cp,'search_depth':8,
            'candidates':[{'move':'d2d4','cp':20},{'move':'d2d4','cp':19}, {'move':'invalid'}],
            'illustrative_line':[move,'e7e5'],'line_kind':'searched_pv'}}

class BoardProjectionTests(unittest.TestCase):
    def test_fen_and_orientation(self):
        cells = parse_fen(START)
        self.assertEqual(len(cells),64)
        self.assertEqual(sum(bool(x) for x in cells),32)
        self.assertEqual(projection(cells,False)[0],{'square':'a8','piece':'r'})
        self.assertEqual(projection(cells,True)[0],{'square':'h1','piece':'R'})

    def test_invalid_fen(self):
        for value in ('', '9/8/8/8/8/8/8/8 w - - 0 1', START.replace(' w ',' x '), START.replace('PPPPPPPP','7')):
            self.assertEqual(parse_fen(value),())
        self.assertEqual(projection((),False),[])

    def test_move_geometry(self):
        self.assertEqual(move_geometry('e2e4',False),dict(x1=4,y1=6,x2=4,y2=4))
        self.assertEqual(move_geometry('e2e4',True),dict(x1=3,y1=1,x2=3,y2=3))
        self.assertEqual(move_geometry('e7e8q',False),dict(x1=4,y1=1,x2=4,y2=0))
        self.assertEqual(move_geometry('e2e2',False),{})

    def test_evaluation_perspective(self):
        self.assertEqual(score_geometry(event())['value'],32)
        self.assertEqual(score_geometry(event(AFTER,'e7e5'))['value'],-32)
        self.assertEqual(score_geometry(event(cp=5000))['fraction'],1.)
        mate = event(AFTER,'e7e5',None)
        mate['details']['uci_score'] = {'kind':'mate','value':3}
        self.assertEqual(score_geometry(mate),dict(kind='mate',value=-3,fraction=0.))
        self.assertEqual(score_geometry(event(cp=None)),{})

    def test_history_and_candidates(self):
        h = BoardHistory()
        self.assertEqual(h.view()['cells'],[])
        h.replace([event(),event(AFTER,'e7e5')])
        self.assertEqual(h.index,1)
        self.assertEqual(h.view()['turn'],'Чёрные')
        h.go(0)
        self.assertEqual(h.view()['score'],'+32 cp')
        self.assertEqual(len(h.view()['candidates']),1)
        self.assertTrue(h.select('d2d4'))
        self.assertFalse(h.select('a2a4'))
        self.assertEqual(h.view()['arrow']['x1'],3)
        self.assertEqual(h.view()['line'],['e2e4','e7e5'])
        h.black = True
        self.assertEqual(h.view()['cells'][0]['square'],'h1')
        h.go(99)
        self.assertEqual(h.index,1)

    def test_history_limit(self):
        h = BoardHistory()
        h.replace(event() for _ in range(MAX_HISTORY+5))
        self.assertEqual(len(h.frames),MAX_HISTORY)
        self.assertEqual(h.index,MAX_HISTORY-1)

if __name__ == '__main__':
    unittest.main()
