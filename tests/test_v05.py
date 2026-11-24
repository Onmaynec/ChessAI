"""v0.5 tests: seeded paired openings, league PPO integrity, non-destructive upgrade."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import torch

from neural.model import ChessNet
from neural.model_guard import screening
from neural.tournament import checkpoints_for
from neural.openings import open_position
from neural.selfplay import START_FEN, ChessBridge, evaluate, rollout
from tools.migrate_current import migrate, hash_file

ROOT=Path(__file__).resolve().parents[1]
ENGINE=next((p for p in (ROOT/'build/Release/chessai.exe',ROOT/'build/chessai.exe',ROOT/'build/chessai') if p.exists()),None)


@unittest.skipIf(ENGINE is None,'Build the C++ engine first')
class OpeningTests(unittest.TestCase):
    def test_opening_seed_is_reproducible_and_legal(self):
        with ChessBridge(ENGINE) as bridge:
            one, line1=open_position(bridge,10,START_FEN,2026,0,8)
            two, line2=open_position(bridge,11,START_FEN,2026,0,8)
            self.assertEqual(one['fen'],two['fen'])
            self.assertEqual(line1,line2)
            self.assertEqual(len(line1),8)
            self.assertFalse(one['finished'])
            bridge.drop(10);bridge.drop(11)

    def test_diverse_paired_evaluation_counts_unique_trajectories(self):
        torch.set_num_threads(2)
        torch.manual_seed(10)
        a=ChessNet(8,1).eval()
        b=ChessNet(8,1).eval()
        stats, games=evaluate(a,b,ENGINE,12,80,torch.device('cpu'),START_FEN,50000,
                              opening_plies=8,seed=123456)
        self.assertEqual(stats['opening_pairs'],6)
        self.assertEqual(stats['played'],12)
        self.assertGreaterEqual(stats['unique_opening_positions'],3)
        self.assertGreaterEqual(stats['unique_sequences'],6)
        for x,y in zip(games[::2],games[1::2]):
            self.assertEqual(x['start_fen'],y['start_fen'])
            self.assertEqual(x['opening_plies'],y['opening_plies'])
            self.assertEqual(x['neural_color'],'white')
            self.assertEqual(y['neural_color'],'black')
            self.assertEqual(len(x['fens']),len(x['moves'])+1)
        self.assertEqual(sum(stats[k] for k in ('wins','draws','losses','unfinished')),12)

    def test_league_records_only_current_policy_actions(self):
        torch.set_num_threads(2)
        current=ChessNet(8,1).eval()
        frozen=ChessNet(8,1).eval()
        games=rollout(current,ENGINE,games=2,parallel=2,max_plies=25,temperature=1.0,
                      start_fen=START_FEN,device=torch.device('cpu'),id_start=1000,
                      opening_plies=4,opening_seed=7,
                      opponent=frozen,league_fraction=1.0)
        self.assertEqual(len(games),2)
        for g in games:
            self.assertEqual(g.mode,'league')
            self.assertLess(len(g.experience),len(g.moves))
            self.assertTrue(all(x['side']==g.learning_color for x in g.experience))
            self.assertEqual(len(g.fens),len(g.moves)+1)


class ModelGuardTests(unittest.TestCase):
    def test_rejects_repeated_positions_and_unfinished(self):
        base={'opening_pairs':8,'completed_pairs':8,'unique_opening_positions':1,
              'completed':16,'score':1.0}
        self.assertFalse(screening(base)['promote'])
        base['unique_opening_positions']=8
        self.assertTrue(screening(base)['promote'])
        base['completed_pairs']=2
        self.assertFalse(screening(base)['promote'])


class CurrentMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.old=root/'ChessAI-v0.3.0'   # renamed folder still contains newer code
        self.new=root/'ChessAI-v0.5.0'
        for p in (self.old,self.new):
            (p/'neural').mkdir(parents=True)
            (p/'neural/selfplay.py').write_text('code')
            (p/'runs').mkdir()
        (self.old/'VERSION').write_text('0.4.1')
        (self.new/'VERSION').write_text('0.7.0')
        run=self.old/'runs'/'run_testing'
        (run/'checkpoints').mkdir(parents=True)
        (run/'checkpoints/latest.pt').write_bytes(b'checkpoint'*100)
        (run/'run_metadata.json').write_text('{"version":"0.4.0"}')
        (run/'run_state.json').write_text('{"status":"completed","iteration":170}')
        (run/'metrics.jsonl').write_text('{"iteration":170}\n')

    def test_verified_copy_and_preserved_source_and_retries(self):
        old=self.old/'runs/run_testing/checkpoints/latest.pt'
        original=hash_file(old)
        check=migrate(self.old,self.new,dry_run=True)
        self.assertGreaterEqual(check['copy_count'],4)
        self.assertFalse((self.new/'runs/run_testing').exists())
        copy=migrate(self.old,self.new)
        self.assertEqual(copy['copied'],check['copy_count'])
        self.assertEqual(hash_file(old),original)
        self.assertEqual(hash_file(self.new/'runs/run_testing/checkpoints/latest.pt'),original)
        self.assertEqual(migrate(self.old,self.new)['copied'],0)

    def test_rejects_conflict_and_running_source(self):
        old=self.old/'runs/run_testing/checkpoints/latest.pt'
        target=self.new/'runs/run_testing/checkpoints/latest.pt'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError,'Conflicting'):
            migrate(self.old,self.new)
        target.unlink()
        (self.old/'runs/run_testing/run_state.json').write_text('{"status":"running"}')
        with self.assertRaisesRegex(ValueError,'still marked running'):
            migrate(self.old,self.new)
        self.assertTrue(migrate(self.old,self.new,dry_run=True,allow_interrupted=True)['dry_run'])

class HistoricalTournamentTests(unittest.TestCase):
    def test_checkpoint_selection_order_and_no_duplicate_latest(self):
        with tempfile.TemporaryDirectory() as name:
            run=Path(name)
            folder=run/'checkpoints'
            folder.mkdir()
            for iteration in (5,10,20):
                (folder/f'iteration_{iteration:05}.pt').write_bytes(b'archive')
            torch.save({'iteration':20,'config':{'channels':8,'blocks':1}},folder/'latest.pt')
            result=checkpoints_for(run,2)
            self.assertEqual([it for it,_ in result],[10,20])
            self.assertEqual(result[-1][1].name,'latest.pt')


class DashboardV05Tests(unittest.TestCase):
    def test_health_version_and_even_evaluation_validation(self):
        from fastapi.testclient import TestClient
        from dashboard.server import app
        with TestClient(app) as client:
            d=client.get('/api/health').json()
            self.assertEqual(d['version'],'0.7.0')
            self.assertEqual(client.get('/').status_code,200)
            self.assertEqual(client.get('/api/evaluations/no_such_run').status_code,404)
            self.assertEqual(client.post('/api/evaluation/no_such_run',json={'games':9}).status_code,404)

if __name__=='__main__':unittest.main()
