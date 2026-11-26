import tempfile
import unittest
from pathlib import Path
from tools.vision_qa_manifest import expected_cases, review_manifest

def fixture(directory):
    # Minimal PNG header only: this tests manifest metadata, not image rendering.
    report = {'schema':1,'captures':[],'qml_warnings':[],'errors':[]}
    for key in expected_cases():
        logical = [800,650]
        for w,h in ((1200,800),(800,650),(560,480)):
            if key.endswith(f'-{w}x{h}'):
                logical = [w,h]
        header = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'+b''.join(v.to_bytes(4,'big') for v in logical)
        (directory/(key+'.png')).write_bytes(header)
        report['captures'].append({'case':key,'file':key+'.png','image_size':logical[:],
                                   'logical_size':logical,'sample_colors':10})
    return report

class ManifestTests(unittest.TestCase):
    def test_coverage(self):
        self.assertEqual(len(expected_cases()),30)
        self.assertEqual(len(set(expected_cases())),30)
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            report = fixture(directory)
            self.assertEqual(review_manifest(report,directory),[])

    def test_missing_and_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            report = fixture(directory)
            removed = report['captures'].pop()
            report['captures'].append(report['captures'][0])
            issues = review_manifest(report,directory)
            self.assertTrue(any('duplicate' in i for i in issues))
            self.assertIn(removed['case']+': missing capture',issues)

    def test_invalid_image_and_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            report = fixture(directory)
            row = report['captures'][0]
            (directory/row['file']).write_bytes(b'invalid')
            row['sample_colors'] = 1
            row['logical_size'] = [1,1]
            report['qml_warnings'] = ['binding loop']
            issues = review_manifest(report,directory)
            self.assertTrue(any('invalid PNG' in i for i in issues))
            self.assertTrue(any('uniform frame' in i for i in issues))
            self.assertTrue(any('requested size' in i for i in issues))
            self.assertIn('1 QML warning(s)',issues)

    def test_schema(self):
        self.assertEqual(review_manifest(None,Path('.')),['Unknown report schema'])
        self.assertEqual(review_manifest({'schema':1},Path('.')),['Missing captures'])

if __name__ == '__main__':
    unittest.main()
