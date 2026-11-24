"""v0.4 regression tests: migration safety, diagnostics, neural search and recovery."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import torch

from dashboard.analysis import summarize
from neural.model import ChessNet
from neural.search import analyze, terminal_value
from neural.selfplay import ChessBridge, recover_resume_files
from tools.migrate_v03 import migrate, preflight, digest

ROOT=Path(__file__).resolve().parents[1]
ENGINE=next((f for f in [ROOT/'build/Release/chessai.exe',ROOT/'build/chessai.exe',ROOT/'build/chessai'] if f.is_file()),None)

class DiagnosticTests(unittest.TestCase):
    def test_arena_draws_and_uncertainty_and_truncations(self):
        data=summarize([{'iteration':1,'games':4,'plies':30,'samples':10,
            'results':{'white_wins':1,'black_wins':0,'draws':1,'unfinished':2},
            'train':{'value_mse':0.03},
            'arena':{'wins':1,'draws':2,'losses':1,'unfinished':3}}])
        self.assertEqual(data['totals']['games'],4)
        self.assertEqual(data['totals']['finished'],2)
        self.assertEqual(data['arena']['completed'],4)
        self.assertEqual(data['arena']['score'],0.5)
        self.assertEqual(data['arena']['unfinished'],3)
        self.assertEqual(data['completion_rate'],0.5)
        self.assertIsNone(data['arena']['interval95_bounded'])
        self.assertTrue(data['warnings'])

    def test_checkpoint_terminal_score_by_side_to_move(self):
        s={'finished':True,'result':'1-0','fen':'7k/8/8/8/8/8/8/K7 b - - 0 2'}
        self.assertEqual(terminal_value(s),-1.0)
        s['fen']=s['fen'].replace(' b ',' w ')
        self.assertEqual(terminal_value(s),1.0)
        s['result']='1/2-1/2'
        self.assertEqual(terminal_value(s),0.0)

class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base=Path(self.tmp.name)
        self.old=base/'old';self.new=base/'new'
        (self.old/'neural').mkdir(parents=True)
        (self.new/'neural').mkdir(parents=True)
        (self.old/'neural'/'selfplay.py').write_text('original')
        (self.old/'VERSION').write_text('0.3.0')
        (self.new/'VERSION').write_text('0.4.0')
        self.run=self.old/'runs'/'run_test'
        (self.run/'checkpoints').mkdir(parents=True)
        (self.run/'checkpoints'/'latest.pt').write_bytes(b'checkpoint'*500)
        (self.run/'run_metadata.json').write_text('{"version":"0.3.0"}')
        (self.run/'run_state.json').write_text('{"status":"completed","iteration":27}')
        (self.run/'games.jsonl').write_text('{"iteration":27,"result":"1/2-1/2"}\n')
        (self.old/'models').mkdir()
        (self.old/'models'/'custom.pt').write_bytes(b'personal model')

    def test_copy_verifies_progress_and_is_idempotent(self):
        src_hash=digest(self.run/'checkpoints'/'latest.pt')
        preview=migrate(self.old,self.new,dry_run=True)
        self.assertEqual(preview['files_to_copy'],5)
        self.assertFalse((self.new/'runs'/'run_test').exists())
        actual=migrate(self.old,self.new)
        self.assertEqual(actual['copied'],5)
        self.assertEqual(src_hash,digest(self.new/'runs'/'run_test'/'checkpoints'/'latest.pt'))
        self.assertEqual(src_hash,digest(self.run/'checkpoints'/'latest.pt'))
        self.assertEqual(migrate(self.old,self.new)['copied'],0)

    def test_refuses_conflicting_destination_without_overwrite(self):
        dest=self.new/'runs'/'run_test'/'checkpoints'
        dest.mkdir(parents=True)
        (dest/'latest.pt').write_text('NOT THE SAME')
        with self.assertRaisesRegex(ValueError,'different files'):
            migrate(self.old,self.new)
        self.assertEqual((dest/'latest.pt').read_text(),'NOT THE SAME')
        self.assertFalse((self.new/'models'/'custom.pt').exists())

    def test_refuses_running_source_by_default(self):
        (self.run/'run_state.json').write_text('{"status":"running"}')
        with self.assertRaisesRegex(ValueError,'still marked running'):
            preflight(self.old,self.new)
        self.assertTrue(migrate(self.old,self.new,dry_run=True,allow_interrupted=True)['dry_run'])

class RecoveryTests(unittest.TestCase):
    def test_quarantines_uncommitted_games_and_restores_checkpoint_metric(self):
        with tempfile.TemporaryDirectory() as folder:
            run=Path(folder)
            metrics={'iteration':3,'samples':44}
            ck={'iteration':3,'metrics':metrics}
            path=run/'games.jsonl'
            rows=[{'iteration':3,'game_id':1},{'iteration':4,'game_id':2}]
            path.write_text(''.join(json.dumps(x)+'\n' for x in rows))
            out=recover_resume_files(run,ck)
            self.assertEqual(out['games.jsonl'],1)
            self.assertEqual([x['game_id'] for x in map(json.loads,path.read_text().splitlines())],[1])
            self.assertTrue(list((run/'recovery').iterdir()))
            self.assertEqual(json.loads((run/'metrics.jsonl').read_text())['iteration'],3)
            self.assertEqual(recover_resume_files(run,ck),{})

@unittest.skipIf(ENGINE is None,'C++ core must be built')
class NeuralSearchTests(unittest.TestCase):
    def test_search_finds_checkmate_even_with_low_policy_prior(self):
        torch.manual_seed(19)
        model=ChessNet(8,1).eval()
        # White has Qg7#; weak policy may assign low probability, but all root moves are explored.
        fen='7k/8/5KQ1/8/8/8/8/8 w - - 0 1'
        result=analyze(model,ENGINE,fen,depth=2,width=4,device='cpu')
        self.assertEqual(result['best_move'],'g6g7')
        self.assertEqual(result['candidates'][0]['value'],1.0)

    def test_search_never_returns_illegal_action(self):
        torch.manual_seed(9)
        result=analyze(ChessNet(8,1).eval(),ENGINE,depth=1,width=5)
        with ChessBridge(ENGINE) as b:
            legal=b.new(24)['legal_moves']
        self.assertIn(result['best_move'],legal)

if __name__=='__main__':
    unittest.main()
