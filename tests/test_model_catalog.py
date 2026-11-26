import json,tempfile,unittest
from pathlib import Path
from neural.model_catalog import inventory,vision_entries,run_label
class CatalogTests(unittest.TestCase):
    def test_catalog(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);run=root/'runs'/'run_20261123_072154_abcdef';cp=run/'checkpoints';cp.mkdir(parents=True)
            (run/'run_metadata.json').write_text(json.dumps({'version':'0.7.0','architecture':{'channels':32,'blocks':2},'name':run.name}))
            for name,data in [('latest.pt',b'a'),('best.pt',b'a'),('skillboost.pt',b'b'),('skillboost_v2.pt',b'c')]:
                (cp/name).write_bytes(data)
            ex=root/'tactical_experiments'/'test';ex.mkdir(parents=True)
            (ex/'candidate.pt').write_bytes(b'candidate')
            (ex/'training_report.json').write_text(json.dumps({'status':'complete','schema':'tactical_train_v4','candidate':'candidate.pt','selected_epoch':24,'model_config':{'channels':128,'blocks':15}}))
            rows=inventory(root);by={r['id'].split('/')[-1]:r for r in rows}
            self.assertEqual(by['latest.pt']['name'],'ChessNet Core')
            self.assertEqual(by['best.pt']['status'],'duplicate')
            self.assertEqual(by['skillboost.pt']['status'],'archive')
            self.assertEqual(by['candidate.pt']['version'],'0.9.3.3')
            self.assertIn('Advanced',by['candidate.pt']['name'])
            self.assertEqual({r['key'] for r in vision_entries(run,root)},{'latest.pt','skillboost_v2.pt','tactical_experiments/test/candidate.pt'})
            self.assertNotIn('run_',run_label(run))
            self.assertTrue((cp/'best.pt').is_file())
            (ex/'training_report.json').write_text('{"status":"running"}')
            self.assertFalse(next(r for r in inventory(root) if r['id'].endswith('/candidate.pt'))['selectable'])
if __name__=='__main__':unittest.main()
