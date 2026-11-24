import json
import math
import os
from pathlib import Path
import random
import tempfile
import unittest
from neural.mastery import quotas,deficits,gap_cp,soft_targets,transform_row,curriculum_indices,eligible_candidate,targeted_fen
from neural.tactics import board,canonical
from neural.mastery_guard import paired_scores,confidence

class MasteryTests(unittest.TestCase):
    def test_quota_allocation(self):
        for n in range(10,1001):
            q=quotas(n);self.assertEqual(sum(q.values()),n);self.assertTrue(all(v>=0 for v in q.values()))
            self.assertEqual(deficits(q,q),dict.fromkeys(q,0))
    def test_soft_and_negative_targets(self):
        r={'legal':['a','b','c'],'accepted':['a'],'teacher_cp':600,'move_scores':{'a':600,'b':550,'c':-500}}
        p,bad,value=soft_targets(r)
        self.assertAlmostEqual(sum(p.values()),1);self.assertGreater(p['a'],p['b']);self.assertGreater(p['b'],p['c'])
        self.assertEqual(bad,['c']);self.assertAlmostEqual(value,math.tanh(1))
        self.assertEqual(gap_cp(29999,29997),160)
        self.assertEqual(gap_cp(29999,100),2000)
        with self.assertRaises(ValueError):soft_targets(dict(r,move_scores={'a':600}))
    def test_symmetry(self):
        r={'fen':'r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1','legal':['e1g1','e1c1'],
           'accepted':['e1g1'],'move_scores':{'e1g1':30,'e1c1':0},'teacher_cp':30}
        a=transform_row(r);self.assertEqual(a['accepted'],['e8g8'])
        self.assertEqual(transform_row(a),r)
        self.assertEqual(canonical(a['fen']),canonical(r['fen']))
        with self.assertRaises(ValueError):transform_row(r,mirror=True)
        q={'fen':'7k/P7/8/8/8/8/8/K7 w - - 0 1','legal':['a7a8q','a7a8n'],'accepted':['a7a8q'],
           'move_scores':{'a7a8q':900,'a7a8n':0},'teacher_cp':900}
        a=transform_row(q,mirror=True)
        self.assertEqual(a['accepted'],['h2h1q'])
        self.assertEqual(transform_row(a,mirror=True),q)
    def test_curriculum(self):
        rows=[{'category':'mate1' if i<10 else 'fork','legal':['a']*i,'source':str(i)} for i in range(30)]
        self.assertLess(len(curriculum_indices(rows,1)),len(rows))
        self.assertEqual(sorted(curriculum_indices(rows,5)),list(range(30)))
    def test_candidate_guard(self):
        b={'top1':.2,'top3':.4,'mrr':.3,'value_mse':.2,'target_nll':3.}
        self.assertTrue(eligible_candidate(dict(b,top1=.3),b))
        self.assertFalse(eligible_candidate(dict(b,top1=.3,top3=.3),b))
        self.assertFalse(eligible_candidate(dict(b,top1=.3,value_mse=.3),b))
    def test_pairing(self):
        rows=[{'a':'old','b':'new','opening':0,'white':'new','result':'1-0','mode':'policy'},
              {'a':'old','b':'new','opening':0,'white':'old','result':'0-1','mode':'policy'}]
        self.assertEqual(paired_scores(rows,'old','new'),[1.])
        self.assertIsNone(confidence([1.]*19))
        self.assertEqual(confidence([1.]*20),[1.,1.])
    def test_proposals(self):
        rng=random.Random(932)
        for cat in quotas(600):
            fens=[f for _ in range(100) if (f:=targeted_fen(rng,cat))]
            self.assertTrue(fens)
            self.assertTrue(all(len(board(f))==64 and board(f).count('K')==board(f).count('k')==1 for f in fens))

    @unittest.skipUnless(os.environ.get('CHESSAI_TACTICAL_TEST_ENGINE'),'Set engine for integration smoke')
    def test_mastery_train_resume(self):
        import torch
        from neural.agent import START_FEN
        from neural.selfplay import ChessBridge
        from neural.model import ChessNet
        from neural.encoding import FEATURE_VERSION
        from neural.tactical_data import hash_file,label
        from neural.tactical_learning import atomic_json
        from neural.tactical_train import train
        engine=Path(os.environ['CHESSAI_TACTICAL_TEST_ENGINE'])
        with tempfile.TemporaryDirectory(prefix='mastery-smoke-') as td:
            p=Path(td);model=ChessNet(8,1);source=p/'source.pt'
            torch.save({'model':model.state_dict(),'config':model.config,'feature_version':FEATURE_VERSION},source)
            h=hash_file(source);rows=[]
            with ChessBridge(engine) as bridge:
                # Actual teacher scores and actual symmetry validation inside trainer.
                for i,move in enumerate(('e2e4','d2d4','g1f3','c2c4','a2a4','h2h4')):
                    bridge.new(932001,START_FEN);s=bridge.step(932001,move)
                    legal=s['legal_moves'];scores={m:0 for m in legal};scores[legal[0]]=300
                    rows.append({'fen':s['fen'],'legal':legal,'accepted':[legal[0]],'move_scores':scores,
                                 'teacher_cp':300,'source':f'smoke:{i}','category':'capture','split':'train' if i<4 else 'validation'})
                pos=bridge.new(932001,'7k/8/5KQ1/8/8/8/8/8 w - - 0 1')
                result=label(bridge,engine,pos,2,mastery=True)
                self.assertEqual(result[1],'mate1');self.assertEqual(set(result[4]),set(pos['legal_moves']))
                self.assertEqual(result[2],29999)
                bridge.new(932001,START_FEN);s=bridge.step(932001,'b2b4')
                replay_row={'fen':s['fen'],'legal':s['legal_moves']}
            ds=p/'dataset.jsonl';ds.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
            atomic_json(p/'dataset_meta.json',{'schema':'tactical_data_v3','complete':True,'dataset_sha256':hash_file(ds),'engine_sha256':hash_file(engine)})
            replay=p/'replay.jsonl';replay.write_text(json.dumps(replay_row)+'\n',encoding='utf-8')
            atomic_json(p/'replay_meta.json',{'sha256':hash_file(replay),'dataset_sha256':hash_file(ds),'engine_sha256':hash_file(engine)})
            out=p/'train';out.mkdir()
            train(source,ds,out,engine,2,2,1e-4,'cpu',932,6,False,replay)
            r=json.loads((out/'training_report.json').read_text())
            self.assertEqual(r['status'],'complete');self.assertEqual(r['optimizer_steps'],4)
            self.assertEqual(r['schema'],'tactical_train_v3')
            self.assertIn('value_mse',r['baseline']['all'])
            self.assertTrue(r['epochs'][1]['augmented_epoch'])
            train(source,ds,out,engine,2,2,1e-4,'cpu',932,6,True,replay)
            self.assertEqual(json.loads((out/'training_report.json').read_text())['optimizer_steps'],4)
            self.assertEqual(hash_file(source),h)

if __name__=='__main__':unittest.main()
