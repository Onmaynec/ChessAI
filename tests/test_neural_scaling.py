import unittest
import os,json,tempfile
from pathlib import Path
from neural.scaling import family_id,family_split,verify_families,quotas,guard_categories,indices
from neural.mastery import transform_row

class ScalingTests(unittest.TestCase):
    def test_family_symmetries(self):
        r={'fen':'7k/8/6K1/8/8/8/8/R7 w - - 0 1','legal':[],'accepted':[]}
        for flip in (False,True):
            for mirror in (False,True):
                self.assertEqual(family_id(r['fen']),family_id(transform_row(r,flip,mirror)['fen']))
        self.assertEqual(family_id(r['fen']),family_id('7k/8/6K1/8/8/8/R7/8 w - - 0 1'))
    def test_group_split(self):
        from neural.mastery import fen_from_board
        rows=[]
        for k in range(0,48,2):
            for p in (48,49):
                b=['.']*64;b[k]='K';b[63]='k';b[p]='R'
                rows.append({'fen':fen_from_board(b),'category':'mate1' if k%4 else 'capture','source':str(len(rows))})
        split=family_split(rows,12,934)
        self.assertEqual(split,family_split(rows,12,934))
        groups={s:[r for r in split if r['split']==s] for s in ('train','validation')}
        self.assertTrue(all(verify_families(groups).values()))
        self.assertFalse({r['family_id'] for r in groups['train']}&{r['family_id'] for r in groups['validation']})
        row=dict(groups['train'][0],split='validation')
        with self.assertRaises(ValueError):verify_families({'train':groups['train'],'validation':[row]})
    def test_quotas(self):
        self.assertEqual(sum(quotas(6000).values()),6000)
        self.assertEqual(sum(quotas(60001).values()),60001)
        self.assertEqual(quotas(6000)['mate1'],1200)
    def test_guard(self):
        base={c:{'top1':.5} for c in ('mate1','check_evasion','promotion')}
        self.assertTrue(guard_categories(base,base))
        self.assertFalse(guard_categories(dict(base,mate1={'top1':.4}),base))
        self.assertFalse(guard_categories({},base))
    def test_curriculum(self):
        rows=[{'category':'fork','legal':['a1a2'],'source':str(i)} for i in range(10)]
        metrics=[{'target_mass':i/10} for i in range(10)]
        self.assertEqual(indices(rows,metrics,1),[9,8])
        self.assertEqual(indices(rows,metrics,6),list(range(10)))

    @unittest.skipUnless(os.environ.get('CHESSAI_TACTICAL_TEST_ENGINE'),'Set engine for integration smoke')
    def test_scaling_train_resume(self):
        import torch
        from neural.model import ChessNet
        from neural.encoding import FEATURE_VERSION
        from neural.selfplay import ChessBridge
        from neural.tactical_data import hash_file
        from neural.tactical_learning import atomic_json
        from neural.tactical_train import train
        from neural.tactical_optimization import settings as opt
        from neural.scaling import settings
        engine=Path(os.environ['CHESSAI_TACTICAL_TEST_ENGINE'])
        with tempfile.TemporaryDirectory(prefix='scaling-smoke-') as td:
            p=Path(td);source=p/'source.pt';reference=p/'reference.pt'
            for path,channels in ((source,8),(reference,16)):
                model=ChessNet(channels,1)
                torch.save({'model':model.state_dict(),'config':model.config,'feature_version':FEATURE_VERSION},path)
            rows=[]
            with ChessBridge(engine) as bridge:
                for i,(fen,split) in enumerate([
                    ('4k3/8/8/8/8/2Q5/8/2K5 w - - 0 1','train'),
                    ('4k3/8/8/8/8/2R5/8/2K5 w - - 0 1','train'),
                    ('4k3/8/8/8/8/2B5/1P6/2K5 w - - 0 1','validation'),
                    ('4k3/8/8/8/8/2N5/1P6/2K5 w - - 0 1','validation')]):
                    s=bridge.new(934001,fen);legal=s['legal_moves']
                    scores={m:0 for m in legal};scores[legal[0]]=300
                    rows.append({'fen':s['fen'],'legal':legal,'accepted':[legal[0]],'move_scores':scores,'teacher_cp':300,
                                 'category':'capture','source':f'smoke:{i}','split':split,'family_id':family_id(s['fen'])})
            ds=p/'dataset.jsonl';ds.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
            atomic_json(p/'dataset_meta.json',{'schema':'tactical_data_v3','complete':True,'scaling':'family_v1',
                        'dataset_sha256':hash_file(ds),'engine_sha256':hash_file(engine)})
            out=p/'train';out.mkdir()
            args=(source,ds,out,engine,2,2,1e-4,'cpu',934,6)
            cfg=settings(reference,hash_file(reference))
            train(*args,False,None,opt(2),cfg)
            r=json.loads((out/'training_report.json').read_text(encoding='utf-8'))
            self.assertEqual(r['schema'],'tactical_train_v5');self.assertEqual(r['optimizer_steps'],2)
            self.assertIn('reference_distill',r['epochs'][0]['loss_components'])
            self.assertIsNotNone(r['reference_baseline'])
            train(*args,True,None,opt(2),cfg)
            self.assertEqual(json.loads((out/'training_report.json').read_text())['optimizer_steps'],2)
            self.assertEqual(hash_file(source),r['source_sha256'])
            self.assertEqual(hash_file(reference),cfg['reference_sha256'])

if __name__=='__main__':unittest.main()
