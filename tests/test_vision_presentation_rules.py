import unittest
from visionbot.presentation_rules import preview_layout, form_columns, session_state, short_text

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
