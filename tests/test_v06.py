"""v0.6 regression tests. Previous-version checkpoints and metrics must survive."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import torch
from neural.encoding import encode_fen
from neural.league import league_sources,load_league
from neural.model import ChessNet
from neural.quality import (position_signature,repeated_positions,reversible_move_candidates,
                            reason_breakdown,swap_colors_rotate_fen)
from neural.selfplay import (START_FEN,ChessBridge,evaluate,ppo_train,rollout,run,parse_args)
from neural.evaluation import main as evaluate_main
from dashboard.analysis import summarize
from tools.audit_color import audit
from tools.migrate_current import hash_file,migrate

ROOT=Path(__file__).resolve().parents[1]
ENGINE=next((p for p in (ROOT/'build/Release/chessai.exe',ROOT/'build/chessai.exe',ROOT/'build/chessai') if p.exists()),None)


class QualityTests(unittest.TestCase):
    def test_swap_colors_rotate_is_involution(self):
        for fen in [START_FEN,
                    'r3k2r/p7/1P6/8/8/6p1/P7/R3K2R w KQkq - 4 38',
                    'rnbqkbnr/pppp1ppp/8/4p3/3P4/8/PPP1PPPP/RNBQKBNR b KQkq d3 0 2']:
            rotated=swap_colors_rotate_fen(fen)
            self.assertEqual(swap_colors_rotate_fen(rotated),fen)
            self.assertEqual(encode_fen(rotated).shape,(19,8,8))
        self.assertEqual(swap_colors_rotate_fen(START_FEN).split()[1],'b')

    def test_repetition_counts_and_heuristic(self):
        fen=START_FEN
        another='rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1'
        self.assertEqual(repeated_positions([fen,another,fen,fen,another]),3)
        self.assertEqual(reversible_move_candidates(['g1f3','g8f6'],['f3g1','e2e4']),['f3g1'])
        self.assertEqual(reversible_move_candidates(['a7a8q','g8f6'],['a8a7']),[])
        self.assertEqual(reversible_move_candidates([],['g1f3']),[])

    def test_legacy_metrics_not_falsely_claimed_0_repetition(self):
        d=summarize([{'iteration':100,'games':40,'results':{'draws':30},'train':{'value_mse':0.1}}])
        self.assertEqual(d['quality']['reason_iterations'],0)
        self.assertIsNone(d['quality']['repetition_fraction'])
        d=summarize([{'iteration':101,'games':10,'results':{'draws':8},
                      'termination_reasons':{'threefold_repetition_claimed':8,'checkmate':2},
                      'position_revisits':21,'train':{'approx_kl':0.004,'clip_fraction':0.03,'early_stopped_kl':True}}])
        self.assertEqual(d['quality']['repetition_fraction'],0.8)
        self.assertEqual(d['quality']['kl_early_stops'],1)
        self.assertEqual(d['quality']['position_revisits'],21)

    def test_ppo_reports_guard_diagnostics_and_preserves_legal_logits(self):
        model=ChessNet(8,1).eval()
        optimizer=torch.optim.AdamW(model.parameters(),lr=0.0001)
        fen=START_FEN
        # One labeled move, deliberately logp-matched to an unmodified initial policy.
        from neural.agent import rank
        moves=['g1f3','e2e4']
        ranked,value=rank(model,fen,moves)
        p=dict(ranked)['g1f3']
        rows=[{'fen':fen,'legal_moves':moves,'move':'g1f3','old_logp':__import__('math').log(p),
               'old_value':value,'outcome_value':1.0,'discouraged_moves':['g1f3']}]*4
        metrics=ppo_train(model,optimizer,rows,torch.device('cpu'),temperature=1,epochs=2,
                          batch_size=2,clip=.2,value_weight=.5,entropy_weight=0,
                          target_kl=.035,repetition_penalty=0.12)
        self.assertGreaterEqual(metrics['updates'],1)
        self.assertIn('approx_kl',metrics)
        self.assertIn('clip_fraction',metrics)
        self.assertLessEqual(metrics['epochs_requested'],2)


@unittest.skipIf(ENGINE is None,'Build chess engine first')
class IntegrationTests(unittest.TestCase):
    def test_multiple_frozen_opponents_never_generate_off_policy_experience(self):
        torch.set_num_threads(2)
        a=ChessNet(8,1).eval()
        b=ChessNet(8,1).eval()
        c=ChessNet(8,1).eval()
        games=rollout(a,ENGINE,games=6,parallel=3,max_plies=20,
                      temperature=1.,start_fen=START_FEN,device=torch.device('cpu'),
                      id_start=9341,opponents=[b,c],league_fraction=1.0,
                      repetition_penalty=.12)
        self.assertEqual(len(games),6)
        self.assertTrue(all(g.mode=='league' for g in games))
        self.assertEqual({g.league_opponent_idx for g in games},{0,1})
        for game in games:
            self.assertEqual(len(game.fens),len(game.moves)+1)
            self.assertTrue(all(row['side']==game.learning_color for row in game.experience))
            self.assertTrue(all(set(row['discouraged_moves']).issubset(row['legal_moves']) for row in game.experience))

    def test_holdout_evaluation_seed_and_reasons(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            torch.manual_seed(5)
            model=ChessNet(8,1)
            ck={'model':model.state_dict(),'config':model.config,'feature_version':'planes19_actions73_v1','iteration':5}
            torch.save(ck,path/'a.pt')
            torch.save(ck,path/'b.pt')
            evaluate_main(['--engine',str(ENGINE),'--checkpoint',str(path/'a.pt'),
                           '--reference',str(path/'b.pt'),'--games','4','--max-plies','40',
                           '--output',str(path/'out.json'),'--suite','holdout'])
            result=json.loads((path/'out.json').read_text())
            self.assertEqual(result['version'],'0.6.0')
            self.assertEqual(result['suite'],'holdout')
            self.assertNotEqual(result['effective_seed'],result['seed'])
            self.assertEqual(sum(result['statistics']['termination_reasons'].values()),4)
            self.assertEqual(result['statistics']['played'],4)

    def test_progress_resume_and_new_quality_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'myrun'
            base=['--engine',str(ENGINE),'--out',str(path),'--iterations','1',
                  '--games-per-iteration','2','--parallel','2','--max-plies','30',
                  '--arena-games','0','--best-every','0','--save-every','1',
                  '--start-fen','8/8/8/8/8/2k5/8/K7 w - - 0 1']
            run(parse_args(base))
            checkpoint=path/'checkpoints/latest.pt'
            before=torch.load(checkpoint,map_location='cpu',weights_only=True)
            self.assertEqual(before['iteration'],1)
            run(parse_args(base+['--resume']))
            after=torch.load(checkpoint,map_location='cpu',weights_only=True)
            self.assertEqual(after['iteration'],2)
            self.assertIn('optimizer',after)
            metrics=[json.loads(x) for x in (path/'metrics.jsonl').read_text().splitlines()]
            self.assertEqual([m['iteration'] for m in metrics],[1,2])
            self.assertIn('termination_reasons',metrics[-1])
            self.assertIn('approx_kl',metrics[-1]['train'])
            self.assertIn('position_revisits',metrics[-1])
            self.assertEqual((path/'checkpoints/iteration_00001.pt').is_file(),True)


class ArchiveMigrationTests(unittest.TestCase):
    def test_multiple_league_snapshots_and_no_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'checkpoints'
            folder.mkdir()
            for i in (10,20,30,40,50):
                (folder/f'iteration_{i:05}.pt').write_bytes(bytes([i]))
            (folder/'best.pt').write_bytes(b'best')
            names=[p.name for p in league_sources(Path(tmp),4)]
            self.assertEqual(len(names),4)
            self.assertEqual(names[0],'best.pt')
            self.assertIn('iteration_00010.pt',names)
            self.assertIn('iteration_00050.pt',names)

    def test_migration_from_renamed_old_v05_is_non_destructive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            old=root/'ChessAI-v0.3.0'
            new=root/'ChessAI-v0.7.0'
            for directory,version in ((old,'0.5.0'),(new,'0.7.0')):
                (directory/'neural').mkdir(parents=True)
                (directory/'runs'/'run_a'/'checkpoints').mkdir(parents=True)
                (directory/'neural/selfplay.py').write_text('ok')
                (directory/'VERSION').write_text(version)
            checkpoint=old/'runs/run_a/checkpoints/latest.pt'
            checkpoint.write_bytes(b'checkpoint-state'*100)
            (old/'runs/run_a/run_state.json').write_text('{"status":"completed","iteration":235}')
            (old/'runs/run_a/run_metadata.json').write_text('{"config":{}}')
            checksum=hash_file(checkpoint)
            report=migrate(old,new)
            self.assertGreater(report['copied'],0)
            self.assertEqual(hash_file(new/'runs/run_a/checkpoints/latest.pt'),checksum)
            self.assertEqual(hash_file(checkpoint),checksum)
            self.assertEqual(migrate(old,new)['copied'],0)


class DashboardQualityTests(unittest.TestCase):
    def test_v06_diagnostics_api_exposes_quality_and_previous_checkpoint(self):
        from fastapi.testclient import TestClient
        from dashboard.server import app
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            run=path/'run_test'
            (run/'checkpoints').mkdir(parents=True)
            (run/'run_metadata.json').write_text(json.dumps({'name':'run_test','config':{'start_fen':START_FEN},'created_at':'2026-11-23'}))
            (run/'run_state.json').write_text(json.dumps({'iteration':235,'status':'completed','device':'cpu'}))
            (run/'metrics.jsonl').write_text(json.dumps({'iteration':235,'games':16,'plies':220,'results':{'draws':14,'white_wins':1,'black_wins':1},'samples':75,
                    'termination_reasons':{'threefold_repetition_claimed':14,'checkmate':2},'position_revisits':15,
                    'train':{'approx_kl':0.001,'clip_fraction':0.012,'grad_norm':0.3,'early_stopped_kl':False}})+'\n')
            (run/'checkpoints/latest.pt').write_bytes(b'unchanged-checkpoint')
            with patch('dashboard.server.RUNS',path):
                with TestClient(app) as client:
                    health=client.get('/api/health').json()
                    self.assertEqual(health['version'],'0.7.0')
                    self.assertEqual(health['runs'],1)
                    result=client.get('/api/analysis',params={'run':'run_test'})
                    self.assertEqual(result.status_code,200)
                    data=result.json()
                    self.assertEqual(data['quality']['repetition_draws'],14)
                    self.assertEqual(data['quality']['last_approx_kl'],0.001)
                    self.assertTrue(data['checkpoint']['exists'])

class MoreQualityTests(unittest.TestCase):
    def test_optional_logit_penalty_does_not_forbid_legal_moves(self):
        from neural.selfplay import sample_moves
        from neural.encoding import POLICY_SIZE
        import numpy as np
        class FlatPolicy(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.p=torch.nn.Parameter(torch.zeros(1))
            def forward(self,x):
                n=x.shape[0]
                return torch.zeros((n,POLICY_SIZE),device=x.device),torch.zeros(n,device=x.device)
        model=FlatPolicy().eval()
        state={'fen':START_FEN,'legal_moves':['g1f3','e2e4']}
        unpenalized=sample_moves(model,[state],torch.device('cpu'),1,False)
        penalized=sample_moves(model,[state],torch.device('cpu'),1,False,
                              discouraged=[['g1f3']],repetition_penalty=0.2)
        self.assertEqual(unpenalized[0][0],'g1f3')
        self.assertEqual(penalized[0][0],'e2e4')
        self.assertGreater(penalized[0][1],0.5)

    def test_holdout_failure_refuses_best_promotion_without_overwriting(self):
        from neural.model_guard import check_and_promote
        from neural.model import ChessNet
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp)
            folder=run/'checkpoints'
            folder.mkdir()
            net=ChessNet(8,1).eval()
            ck={'model':net.state_dict(),'config':net.config,
                'feature_version':'planes19_actions73_v1','iteration':42}
            torch.save(ck,folder/'latest.pt')
            torch.save(ck,folder/'best.pt')
            before=hash_file(folder/'best.pt')
            def win_stats(*args,**kwargs):
                return ({'completed':20,'played':20,'wins':18,'losses':0,'draws':2,'score':.95,
                         'opening_pairs':10,'completed_pairs':10,'unique_opening_positions':10},[])
            def fail_stats(*args,**kwargs):
                return ({'completed':20,'played':20,'wins':1,'losses':12,'draws':7,'score':.225,
                         'opening_pairs':10,'completed_pairs':10,'unique_opening_positions':10},[])
            with patch('neural.model_guard.evaluate',side_effect=[win_stats(),fail_stats()]) as mocked:
                result=check_and_promote(net,run,Path('engine-not-used'),folder/'latest.pt',torch.device('cpu'),
                                         games=20,max_plies=100,seed=5,opening_plies=8)
            self.assertEqual(mocked.call_count,2)
            self.assertFalse(result['decision']['promote'])
            self.assertFalse(result['decision']['holdout_promote'])
            self.assertEqual(hash_file(folder/'best.pt'),before)

if __name__=='__main__':unittest.main()
