import unittest
from concurrent.futures import ThreadPoolExecutor
from visionbot.telemetry import analysis_event, PREFIX
from visionbot.ui_controller import VisionUiController, decode_message
from visionbot.ui_state import AnalysisSnapshot, SessionSnapshot

class ControllerTests(unittest.TestCase):
    def test_fifo_and_limit(self):
        c = VisionUiController()
        for i in range(30):
            c.submit(str(i))
        self.assertEqual([e.text for e in c.drain(5, 1)], list(map(str, range(5))))
        self.assertEqual(c.pending, 25)
        self.assertEqual(len(list(c.drain(100, 1))), 25)
        self.assertEqual(c.pending, 0)

    def test_budget_includes_consumer(self):
        c = VisionUiController()
        c.submit('a')
        c.submit('b')
        now = [0.]
        events = c.drain(10, .01, clock=lambda: now[0])
        self.assertEqual(next(events).text, 'a')
        now[0] = .02
        self.assertEqual(list(events), [])
        self.assertEqual(c.pending, 1)

    def test_concurrent_producers(self):
        c = VisionUiController()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(c.submit, map(str, range(100))))
        self.assertEqual({e.text for e in c.drain(100, 2)}, set(map(str, range(100))))

    def test_message_types(self):
        self.assertEqual(decode_message('ВНИМАНИЕ: test').category, 'error')
        self.assertEqual(decode_message('Ход e2e4').category, 'move')
        self.assertEqual(decode_message('hello').category, 'info')
        self.assertEqual(decode_message(PREFIX+'{bad').category, 'error')

    def test_analysis_and_reset(self):
        c = VisionUiController()
        c.submit(analysis_event({'mode':'external_uci','uci_score':{'kind':'cp','value':34},
                                 'search_depth':8,'search_time_s':.1},
                                move='e2e4',fen='8/8/8/8/8/8/8/8 w - - 0 1',ply=0,value=0.))
        event, = list(c.drain(10, 1))
        self.assertEqual(event.category, 'analysis')
        self.assertEqual(c.analysis.score, '+34 cp')
        self.assertEqual(c.analysis.depth, 8)
        self.assertEqual(c.analysis.move, 'e2e4')
        c.reset_analysis()
        self.assertEqual(c.analysis, AnalysisSnapshot())

    def test_score_missing_and_mate(self):
        self.assertEqual(AnalysisSnapshot.from_event({'details':{}}).score, '—')
        self.assertEqual(AnalysisSnapshot.from_event({'details':{'uci_score':{'kind':'mate','value':-2}}}).score, 'M-2')

    def test_session_update_is_idempotent(self):
        c = VisionUiController()
        self.assertFalse(c.update_session(SessionSnapshot()))
        s = SessionSnapshot(active=True, model='latest.pt')
        self.assertTrue(c.update_session(s))
        self.assertFalse(c.update_session(s))
        self.assertEqual(c.session.phase, 'active')

if __name__ == '__main__':
    unittest.main()
