import json
import os
from pathlib import Path
import random
import tempfile
import unittest
from neural.tactical_learning import stratify,move_metrics,aggregate,hard_weight,selection_key,atomic_json,experiment_lock
from neural.tactical_data import sparse_fen
from neural.tactics import board

class OverhaulTests(unittest.TestCase):
    def test_stratification_exact_and_repeatable(self):
        rows=[{'category':k,'id':i} for k,n in [('fork',50),('pin',8),('mate1',12)] for i in range(n)]
        a=stratify(rows,14,931)
        self.assertEqual(a,stratify(rows,14,931))
        val=[r for r in a if r['split']=='validation']
        self.assertEqual(len(val),14)
        self.assertEqual({r['category'] for r in val},{'fork','pin','mate1'})
        self.assertEqual(len(a),len(rows))
        self.assertTrue(all('split' not in r for r in rows))

    def test_stratification_singletons(self):
        rows=[{'category':str(i),'id':i} for i in range(10)]
        self.assertEqual(sum(r['split']=='validation' for r in stratify(rows,4,1)),4)

    def test_rank_and_multi_target_mass(self):
        m=move_metrics([('a',.4),('b',.3),('c',.2),('d',.1)],['b','d'])
        self.assertEqual(m['top1'],0)
        self.assertEqual(m['top3'],1)
        self.assertEqual(m['mrr'],.5)
        self.assertAlmostEqual(m['target_mass'],.4)
        self.assertEqual(aggregate([m,m])['correct'],0)

    def test_weight_and_selection(self):
        easy=move_metrics([('a',.9),('b',.1)],['a'])
        hard=move_metrics([('a',.9),('b',.1)],['b'])
        self.assertGreater(hard_weight(hard,10,10),hard_weight(easy,10,10))
        self.assertGreaterEqual(hard_weight(easy,100000,1),.5)
        self.assertLessEqual(hard_weight(hard,1,10000),4)
        self.assertGreater(selection_key(easy),selection_key(hard))

    def test_atomic_state_and_lock(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            with experiment_lock(p):
                atomic_json(p/'state.json',{'epoch':1})
                with self.assertRaises(OSError):
                    with experiment_lock(p):pass
            with experiment_lock(p):
                atomic_json(p/'state.json',{'epoch':2})
            self.assertEqual(json.loads((p/'state.json').read_text())['epoch'],2)

    def test_sparse_extra(self):
        rng=random.Random(931)
        fens=[f for _ in range(100) if (f:=sparse_fen(rng,extra=True))]
        self.assertTrue(fens)
        self.assertTrue(all(sum(x!='.' for x in board(f))>=5 for f in fens))

    @unittest.skipUnless(os.environ.get('CHESSAI_TACTICAL_TEST_ENGINE'),'Set engine for integration smoke')
    def test_train_resume_smoke(self):
        import torch
        from neural.agent import START_FEN
        from neural.selfplay import ChessBridge
        from neural.model import ChessNet
        from neural.encoding import FEATURE_VERSION
        from neural.tactical_data import hash_file
        from neural.tactical_train import train
        engine=Path(os.environ['CHESSAI_TACTICAL_TEST_ENGINE'])
        with tempfile.TemporaryDirectory(prefix='tactical-smoke-') as td:
            p=Path(td);model=ChessNet(8,1)
            src=p/'source.pt';torch.save({'model':model.state_dict(),'config':model.config,'feature_version':FEATURE_VERSION},src)
            before=hash_file(src)
            rows=[]
            with ChessBridge(engine) as bridge:
                for i,move in enumerate(('e2e4','d2d4','g1f3','c2c4','a2a4','h2h4')):
                    bridge.new(931001,START_FEN);s=bridge.step(931001,move)
                    rows.append({'fen':s['fen'],'legal':s['legal_moves'],'accepted':[s['legal_moves'][0]],
                                 'source':f'smoke:{i}','category':'smoke','split':'train' if i<4 else 'validation'})
            ds=p/'dataset.jsonl';ds.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
            atomic_json(p/'dataset_meta.json',{'schema':'tactical_data_v2','complete':True,'dataset_sha256':hash_file(ds),'engine_sha256':hash_file(engine)})
            out=p/'train';out.mkdir()
            train(src,ds,out,engine,1,2,1e-4,'cpu',931,2,False)
            r=json.loads((out/'training_report.json').read_text())
            self.assertEqual(r['status'],'complete');self.assertEqual(r['optimizer_steps'],2)
            train(src,ds,out,engine,1,2,1e-4,'cpu',931,2,True)
            self.assertEqual(json.loads((out/'training_report.json').read_text())['optimizer_steps'],2)
            self.assertEqual(hash_file(src),before)

if __name__=='__main__':unittest.main()
