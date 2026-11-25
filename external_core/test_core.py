import io,sys,tempfile,unittest,zipfile
from pathlib import Path
from external_core.install import safe_extract
from external_core.uci import UCI,START_FEN,ProtocolError

class ExternalTests(unittest.TestCase):
    def test_zip(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);buf=io.BytesIO()
            with zipfile.ZipFile(buf,'w') as z:z.writestr('engine/test.txt','hello')
            with zipfile.ZipFile(buf) as z:safe_extract(z,p)
            self.assertEqual((p/'engine/test.txt').read_text(),'hello')
            for bad in ('../escape','C:/escape','foo/../../escape'):
                buf=io.BytesIO()
                with zipfile.ZipFile(buf,'w') as z:z.writestr(bad,'bad')
                with zipfile.ZipFile(buf) as z:
                    with self.assertRaises(ValueError):safe_extract(z,p)
    def test_uci(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'fake.py'
            f.write_text("import sys\nfor l in sys.stdin:\n l=l.strip()\n if l=='uci':print('id name Fake\\noption name MultiPV type spin default 1 min 1 max 5\\nuciok',flush=True)\n elif l=='isready':print('readyok',flush=True)\n elif l.startswith('go '):print('info depth 4 score cp 17 nodes 20 pv e2e4 e7e5\\nbestmove e2e4',flush=True)\n elif l=='quit':break\n")
            with UCI(sys.executable,('-u',str(f))) as e:
                result=e.analyse(START_FEN,['e2e4','d2d4'],movetime=50)
                self.assertEqual(result['bestmove'],'e2e4');self.assertEqual(result['lines'][0]['score']['value'],17)
                with self.assertRaises(ProtocolError):e.analyse(START_FEN,['d2d4'],movetime=50)
    def test_input(self):
        self.assertTrue(START_FEN.endswith('0 1'))

if __name__=='__main__':unittest.main()
