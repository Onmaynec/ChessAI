import unittest
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from benchmark.stats import score, summary, paired_rows, fit_ratings, rating_report, percentile
from benchmark.suite import load_suite, signature, prove_mate, audit_sources

def pair(a,b,opening,result1='1-0',result2='0-1'):
    return [dict(a=a,b=b,opening=opening,white=a,start_fen='fen'+str(opening),result=result1),
            dict(a=a,b=b,opening=opening,white=b,start_fen='fen'+str(opening),result=result2)]

class BenchmarkTests(unittest.TestCase):
    def test_unfinished_not_draw(self):
        self.assertIsNone(score('*',True))
        self.assertEqual(summary([1.,.5,None])['score'],.75)
        self.assertEqual(summary([None])['completed'],0)
        self.assertEqual(paired_rows(pair('a','b',0,'1-0','*')),[])

    def test_exchange_colors(self):
        rows=paired_rows(pair('a','b',0))
        self.assertEqual(rows,[('a','b',0,1.)])
        self.assertEqual(paired_rows(pair('a','b',0,'1-0','1-0'))[0][3],.5)

    def test_no_rating_disconnected(self):
        self.assertIsNone(fit_ratings(['a','b','c'],[('a','b',0,1.)]))

    def test_ratings_and_ci(self):
        records=[]
        for i in range(6):
            records.extend(pair('a','b',i))
        report=rating_report(['a','b'],records,bootstrap=60)
        self.assertGreater(report['agents']['a']['rating'],report['agents']['b']['rating'])
        self.assertIsNotNone(report['agents']['a']['ci95'])
        self.assertEqual(report['agents']['a']['colors']['black']['wins'],6)
        self.assertIsNone(rating_report(['a','b'],records[:2])['agents']['a']['ci95'])

    def test_percentile(self):
        self.assertEqual(percentile([1,3],.5),2)
        self.assertIsNone(percentile([],.5))

    def test_suite_identity(self):
        payload,digest=load_suite()
        self.assertEqual(len(payload['cases']),18)
        self.assertEqual(len(digest),64)
        self.assertEqual(len({signature(c['fen']) for c in payload['cases']}),18)
        self.assertEqual({c['category'] for c in payload['cases']},{'mate1','mate2','fork','pin','sacrifice','defense','endgame'})

    def test_audit_plain_and_gzip_progress(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            plain=root/'experience.jsonl'
            archive=root/'segment.jsonl.gz'
            fen='8/8/8/8/8/8/4P3/8 w - - 0 1'
            cases=[{'id':'target','fen':fen}]
            plain.write_text(json.dumps({'fen':fen})+'\ninvalid\n',encoding='utf-8')
            with gzip.open(archive,'wt',encoding='utf-8') as f:
                f.write(json.dumps({'fen':fen.replace('0 1','3 5')})+'\n')
            messages=[]
            result=audit_sources([archive,plain],cases,progress=messages.append)
            self.assertEqual(result['records_checked'],2)
            self.assertEqual(result['malformed_records'],1)
            self.assertEqual(result['overlapping_ids'],['target'])
            self.assertIn('partial',result['status'])
            self.assertTrue(any('Finished 2/2' in m for m in messages))

    def test_empty_audit_is_not_certified(self):
        self.assertEqual(audit_sources([],[],progress=lambda _:None)['status'],'no readable experience')

    def test_mate_terminal_sign(self):
        state={'finished':True,'result':'0-1'}
        self.assertTrue(prove_mate(None,state,'b',0,{}))
        self.assertFalse(prove_mate(None,state,'w',0,{}))

if __name__=='__main__':unittest.main()
