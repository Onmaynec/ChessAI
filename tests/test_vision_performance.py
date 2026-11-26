import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from visionbot.journal_index import JournalIndex, MAX_ROWS, MAX_TEXT
from visionbot.workspace_preferences import WorkspacePreferences, clean
from visionbot.qt_preview import replay_messages, MAX_REPLAY_BYTES

def evt(text, category='info'):
    return SimpleNamespace(text=text, category=category)

class PerformanceTests(unittest.TestCase):
    def test_index_and_cache(self):
        index = JournalIndex([evt('Straße'), evt('ERROR', 'error')])
        self.assertEqual(index.filter('STRASSE','all')[0]['text'], 'Straße')
        self.assertIs(index.filter('STRASSE','all'), index.filter(' strasse ','all'))
        self.assertEqual(index.filter('', 'error'), [{'category':'error','text':'ERROR'}])
        index.replace([evt('new')])
        self.assertEqual(index.filter('strasse','all'), [])

    def test_journal_bounds(self):
        index = JournalIndex(evt(str(i)) for i in range(MAX_ROWS+1))
        self.assertEqual(index.total, MAX_ROWS)
        self.assertEqual(index.filter('', 'all')[0]['text'], '1')
        index.replace([evt('x'*(MAX_TEXT+1))])
        self.assertEqual(len(index.filter('', 'all')[0]['text']), MAX_TEXT)
        self.assertTrue(index.filter('', 'all')[0]['text'].endswith('…'))

    def test_replay_byte_cap(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'large.log'
            with path.open('wb') as f:
                for _ in range(100):
                    f.write(b'x'*200000+b'\n')
                f.write(b'last\n')
            rows = replay_messages(path)
            self.assertEqual(rows[-1], 'last')
            self.assertLess(len(rows), 101)
            self.assertLessEqual(sum(len(x)+1 for x in rows), MAX_REPLAY_BYTES)

    def test_scale_validation(self):
        self.assertNotIn('text_scale',clean({'text_scale': True}))
        self.assertNotIn('text_scale',clean({'text_scale': 200}))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'prefs.json'
            p = WorkspacePreferences(path)
            self.assertFalse(p.set_text_scale(110))
            self.assertTrue(p.set_text_scale(130))
            p.set_reduced_motion(True)
            p.save()
            loaded = WorkspacePreferences(path)
            self.assertEqual(loaded.data['text_scale'],130)
            self.assertTrue(loaded.data['reduced_motion'])

if __name__ == '__main__':
    unittest.main()
