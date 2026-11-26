import json
import tempfile
import unittest
from pathlib import Path
from visionbot.workspace_preferences import WorkspacePreferences, clean, fit_rect, valid_rect

class WorkspacePreferenceTests(unittest.TestCase):
    def test_independent_geometry(self):
        p = WorkspacePreferences()
        self.assertTrue(p.record('compact',(30,50,360,300)))
        self.assertTrue(p.record('standard',(100,80,1040,720)))
        self.assertTrue(p.record('board',(-600,80,460,620)))
        self.assertEqual(p.data['windows']['compact'],[30,50,360,300])
        self.assertEqual(p.data['windows']['standard'],[100,80,1040,720])
        self.assertEqual(p.data['windows']['board'],[-600,80,460,620])

    def test_negative_monitor(self):
        screens = [(0,0,1920,1040),(-1280,0,1280,960)]
        self.assertEqual(fit_rect((-1000,80,460,620),screens,'board'),[-1000,80,460,620])

    def test_disconnected_screen(self):
        result = fit_rect((-2200,60,1440,900),[(0,0,1280,720)],'expanded')
        x,y,w,h = result
        self.assertGreaterEqual(x,0)
        self.assertGreaterEqual(y,0)
        self.assertLessEqual(x+w,1280)
        self.assertLessEqual(y+h,720)

    def test_corrupt_and_unknown(self):
        self.assertEqual(clean({'mode':'invalid','windows':{'bad':[0,0,3,3],'board':[0,0,-2,4]},
                                'topmost':{'main':1,'journal':True}}),
                         {'mode':'standard','windows':{},'topmost':{'journal':True}})
        self.assertFalse(valid_rect([True,0,10,10]))
        self.assertFalse(valid_rect([0,0,0,10]))

    def test_persistence_and_pins(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'config'/'preview.json'
            p = WorkspacePreferences(path)
            self.assertTrue(p.set_mode('expanded'))
            self.assertTrue(p.set_topmost('board',True))
            self.assertFalse(p.set_topmost('bad',True))
            self.assertTrue(p.record('journal',(60,70,500,400)))
            p.save()
            loaded = WorkspacePreferences(path)
            self.assertEqual(loaded.data,p.data)
            self.assertEqual(list(path.parent.iterdir()),[path])
            path.write_text('{bad',encoding='utf-8')
            self.assertEqual(WorkspacePreferences(path).data,clean(None))

    def test_small_screen(self):
        x,y,w,h=fit_rect(None,[(0,0,600,420)],'expanded')
        self.assertLessEqual(x+w,600)
        self.assertLessEqual(y+h,420)
        self.assertGreater(w,0)
        self.assertGreater(h,0)

if __name__ == '__main__':
    unittest.main()
