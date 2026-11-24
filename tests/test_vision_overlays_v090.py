import unittest
from visionbot.analysis_view import arrows,line_moves,report_sections,square_xy,geometry_parts

class OverlayAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.event={'move':'e2e4','fen':'8/8/8/8/8/8/4P3/8 w - - 0 1',
                    'details':{'mode':'neural_plus_cpp_search','engine_cp':25,'best_engine_cp':30,
                               'illustrative_line':['e2e4','e7e5','g1f3'],
                               'candidates':[{'move':'e2e4'},{'move':'d2d4'},{'move':'bad'}]}}

    def test_arrows_are_unique_and_selected_last(self):
        self.assertEqual(arrows(self.event),[('d2d4','alternative'),('e2e4','chosen')])
        self.assertEqual(arrows(self.event,False),[('e2e4','chosen')])

    def test_line_must_match_selected_and_stop_on_invalid(self):
        self.assertEqual(line_moves(self.event),['e2e4','e7e5','g1f3'])
        self.event['details']['illustrative_line']=['a2a3','e7e5']
        self.assertEqual(line_moves(self.event),['e2e4'])
        self.event['details']['illustrative_line']=['e2e4','bad','g1f3']
        self.assertEqual(line_moves(self.event),['e2e4'])

    def test_orientation(self):
        self.assertEqual(square_xy('a8'),(0,0))
        self.assertEqual(square_xy('a8',True),(7,7))
        self.assertEqual(square_xy('h1'),(7,7))

    def test_no_invented_opponent_mistakes(self):
        rows=dict(report_sections(self.event))
        self.assertIn('Не классифицированы',rows['Ошибки соперника'])
        self.assertIn('25',rows['Позиция'])
        self.assertEqual(report_sections(None)[0][1],'—')

    def test_geometry(self):
        self.assertEqual(geometry_parts('360x425+40-20'),(360,425,40,-20))
        self.assertIsNone(geometry_parts('bad'))

if __name__=='__main__':unittest.main()
