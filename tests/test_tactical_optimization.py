import json
import os
import tempfile
from pathlib import Path
import unittest
from neural.tactical_optimization import settings,schedule_allowed,stop_allowed,components,gradient_diagnostics,candidate_ok
class OptimizationTests(unittest.TestCase):
    def test_schedule(self):
        cfg=settings()
        self.assertFalse(schedule_allowed(5,cfg));self.assertTrue(schedule_allowed(6,cfg))
        self.assertFalse(stop_allowed(19,cfg));self.assertTrue(stop_allowed(20,cfg))
        with self.assertRaises(ValueError):settings(replay_weight=-1)
    def test_losses(self):
        import torch
        from neural.model import ChessNet
        from neural.encoding import INPUT_CHANNELS
        torch.set_num_threads(1);model=ChessNet(8,1).eval()
        logits,value=model(torch.randn(2,INPUT_CHANNELS,8,8))
        lp=logits[:,:3].log_softmax(1)
        target=torch.tensor([[1.,0.,0.],[0.,1.,0.]])
        accepted=target.bool();negative=torch.tensor([[False,True,True],[True,False,True]])
        p,v,t=components(lp,target,accepted,negative,value,torch.zeros(2),torch.ones(2,3)/3,torch.zeros(2),torch.ones(2),settings())
        d=gradient_diagnostics(p,v,model)
        self.assertGreater(d['policy_backbone_norm'],0)
        self.assertLessEqual(abs(d['cosine']),1)
        (p+v).backward()
        self.assertTrue(all(torch.isfinite(x.grad).all() for x in model.parameters() if x.grad is not None))
    def test_candidate(self):
        base={'top1':.2,'top3':.4,'mrr':.3,'value_mse':.2,'target_nll':3.,'negative_mass':.7,'teacher_regret_cp':800}
        self.assertTrue(candidate_ok(dict(base,top1=.3),base))
        self.assertFalse(candidate_ok(dict(base,top1=.3,negative_mass=.72),base))
        self.assertFalse(candidate_ok(dict(base,top1=.3,teacher_regret_cp=810),base))
    @unittest.skipUnless(os.environ.get('CHESSAI_TACTICAL_TEST_ENGINE'),'Set engine for integration smoke')
    def test_optimization_train_resume(self):
        import torch
        from neural.tactical_optimization import settings
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
            train(source,ds,out,engine,2,2,1e-4,'cpu',932,6,False,replay,settings(min_epochs=2))
            r=json.loads((out/'training_report.json').read_text())
            self.assertEqual(r['status'],'complete');self.assertEqual(r['optimizer_steps'],4)
            self.assertEqual(r['schema'],'tactical_train_v4')
            self.assertIn('value_mse',r['baseline']['all'])
            self.assertIn('accepted_nll',r['epochs'][0]['loss_components'])
            self.assertTrue(r['epochs'][0]['gradient_samples'])
            self.assertTrue(r['epochs'][1]['augmented_epoch'])
            train(source,ds,out,engine,2,2,1e-4,'cpu',932,6,True,replay,settings(min_epochs=2))
            self.assertEqual(json.loads((out/'training_report.json').read_text())['optimizer_steps'],4)
            self.assertEqual(hash_file(source),h)


if __name__=='__main__':unittest.main()
