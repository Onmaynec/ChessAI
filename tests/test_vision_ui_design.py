import unittest
from visionbot.design import BG, ACCENT, ACCENT_TEXT, TEXT, button_style
from visionbot.log_model import matches, select_entries, export_text

class VisionDesignTests(unittest.TestCase):
    def test_primary_contrast(self):
        self.assertEqual(BG, '#000000')
        self.assertEqual(button_style(True)['fg_color'], ACCENT)
        self.assertEqual(button_style(True)['text_color'], ACCENT_TEXT)
        self.assertEqual(button_style(False)['text_color'], TEXT)

    def test_search_and_category(self):
        data = [('info', '[12:00:01] Session ready\n'), ('error', '[12:00:02] Ошибка движка\n'),
                ('analysis', '[12:00:03] Engine ready\n')]
        self.assertTrue(matches(data[1], 'error', 'ОШИБКА'))
        self.assertFalse(matches(data[0], 'error', 'ready'))
        self.assertEqual(select_entries(data, 'all', ' READY '), [data[0], data[2]])
        self.assertEqual(export_text(data, 'error'), data[1][1])
        self.assertEqual(export_text(data, 'move'), '')

if __name__ == '__main__':
    unittest.main()
