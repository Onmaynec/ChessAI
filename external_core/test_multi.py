import unittest
from external_core.multi_gui import expand
from external_core.uci import START_FEN
from external_core.match import ENGINES

class MultiTests(unittest.TestCase):
    def test_start(self):
        b=expand(START_FEN)
        self.assertEqual(len(b),64)
        self.assertEqual(b[:8],list('rnbqkbnr'))
        self.assertEqual(b[-8:],list('RNBQKBNR'))
    def test_invalid(self):
        with self.assertRaises(ValueError):expand('8/8 w - - 0 1')
    def test_players(self):
        self.assertEqual(len(set(ENGINES)),5)
    def test_local_match(self):
        import json,queue,tempfile,threading
        from pathlib import Path
        from unittest.mock import patch
        from external_core import match
        class FakeBridge:
            def __init__(self,core):pass
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def new(self,fen):return {'fen':fen,'finished':False,'legal_moves':['e2e4']}
            def step(self,m):
                assert m=='e2e4'
                return {'fen':'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1','finished':True,'legal_moves':[],'result':'1/2-1/2','reason':'fake_terminal'}
        class FakePlayer:
            def __init__(self,spec,core,stack):
                self.kind='Fake';self.identity=spec
            def move(self,state,initial,moves,fens,stop):
                return {'bestmove':'e2e4','engine':'Fake'}
        with tempfile.TemporaryDirectory() as td:
            events=queue.Queue()
            with patch.object(match,'DEST',Path(td)),patch.object(match,'Bridge',FakeBridge),patch.object(match,'Player',FakePlayer):
                match.play(Path('unused'),{'w':{'kind':'Fake'},'b':{'kind':'Fake'}},START_FEN,10,queue.Queue(),events,threading.Event())
            reports=list(Path(td).rglob('match_*.json'))
            self.assertEqual(len(reports),1)
            data=json.loads(reports[0].read_text())
            self.assertEqual(data['status'],'complete')
            self.assertEqual(data['moves'][0]['uci'],'e2e4')
            self.assertEqual(data['result'],'1/2-1/2')
if __name__=='__main__':unittest.main()
