import unittest
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

if __name__=='__main__':unittest.main()
