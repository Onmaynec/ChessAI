import unittest
from visionbot.presentation_rules import preview_layout, form_columns, session_state, short_text, settled_preview_layout, stable_form_columns, PreviewLayout

class PresentationRulesTests(unittest.TestCase):
    def test_preview_bounds(self):
        for width in (0, 120, 300, 419, 420, 580, 1400):
            with self.subTest(width=width):
                layout = preview_layout(width)
                self.assertGreaterEqual(layout.size, 80)
                self.assertLessEqual(layout.size, 360)
                self.assertEqual(layout.stacked, width < 420)
        self.assertEqual(preview_layout(300).size, 280)
        self.assertEqual(preview_layout(580).size, 360)

    def test_form_breakpoint(self):
        self.assertEqual(form_columns(389), 1)
        self.assertEqual(form_columns(390), 2)

    def test_settled_preview_bounds_and_idempotence(self):
        for width in range(2200):
            plan = settled_preview_layout(width)
            self.assertTrue(80 <= plan.size <= 440)
            self.assertEqual(plan, settled_preview_layout(width, plan))

    def test_preview_hysteresis(self):
        for width in range(440,480):
            self.assertTrue(settled_preview_layout(width,PreviewLayout(True,400)).stacked)
            self.assertFalse(settled_preview_layout(width,PreviewLayout(False,280)).stacked)

    def test_form_hysteresis(self):
        for width in range(370,410):
            self.assertEqual(stable_form_columns(width,1),1)
            self.assertEqual(stable_form_columns(width,2),2)
        self.assertEqual(stable_form_columns(410,1),2)
        self.assertEqual(stable_form_columns(369,2),1)

    def test_session_state_priority(self):
        self.assertEqual(session_state(True, True, True, True, True, True, True), 'stopping')
        self.assertEqual(session_state(True, False, False, False, False, False, False), 'active')
        self.assertEqual(session_state(False, False, True, True, True, True, True), 'stopped')
        self.assertEqual(session_state(False, False, False, True, True, True, True), 'ready')
        for missing in range(4):
            conditions = [True] * 4
            conditions[missing] = False
            self.assertEqual(session_state(False, False, False, *conditions), 'setup')

    def test_short_text(self):
        self.assertEqual(short_text('a\n b'), 'a b')
        self.assertEqual(short_text('abcdefgh', 5), 'abcd…')
        self.assertEqual(short_text(''), '')

if __name__ == '__main__':
    unittest.main()
