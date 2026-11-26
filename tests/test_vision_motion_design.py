import tempfile
import unittest
from pathlib import Path
from visionbot.design import MOTION, TYPE_SCALE, motion_duration
from visionbot.workspace_preferences import WorkspacePreferences, clean

class MotionDesignTests(unittest.TestCase):
    def test_motion_roles(self):
        self.assertEqual(set(MOTION), {'fast','normal','page'})
        self.assertLess(MOTION['fast'], MOTION['normal'])
        self.assertLess(MOTION['normal'], MOTION['page'])
        for key, value in MOTION.items():
            self.assertEqual(motion_duration(key), value)
            self.assertEqual(motion_duration(key, True), 0)

    def test_typography_hierarchy(self):
        self.assertLess(TYPE_SCALE['caption'], TYPE_SCALE['body'])
        self.assertLess(TYPE_SCALE['body'], TYPE_SCALE['section'])
        self.assertLess(TYPE_SCALE['section'], TYPE_SCALE['heading'])
        self.assertLess(TYPE_SCALE['heading'], TYPE_SCALE['metric'])

    def test_legacy_preferences(self):
        p = WorkspacePreferences()
        self.assertFalse(p.data.get('reduced_motion', False))
        self.assertNotIn('reduced_motion', clean({'reduced_motion': 1}))
        self.assertFalse(p.set_reduced_motion('true'))

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'workspace.json'
            p = WorkspacePreferences(path)
            p.set_mode('expanded')
            p.set_topmost('board', True)
            self.assertTrue(p.set_reduced_motion(True))
            p.save()
            loaded = WorkspacePreferences(path)
            self.assertTrue(loaded.data['reduced_motion'])
            self.assertEqual(loaded.data['mode'], 'expanded')
            self.assertTrue(loaded.data['topmost']['board'])
            self.assertTrue(loaded.set_reduced_motion(False))
            loaded.save()
            self.assertIs(WorkspacePreferences(path).data['reduced_motion'], False)

if __name__ == '__main__':
    unittest.main()
